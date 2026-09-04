"""Deterministic, label-free execution and artifact writing for ARC-AGI-2."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import AttemptPair, SolveBudget, StaticSolver
from .validation import (
    ChallengeSet,
    Submission,
    ValidationError,
    coerce_challenge_set,
    grid_to_jsonable,
    validate_grid,
    validate_submission,
)


RUN_MANIFEST_SCHEMA = "hearthline-plays.arc2-run-manifest.v1"
RUN_MODES = frozenset({"SYNTHETIC", "TRAIN_CV", "PUBLIC_EVAL", "KAGGLE_HIDDEN"})
RUN_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "run_id",
        "mode",
        "source_lock_sha256",
        "branch_commit",
        "branch_tree",
        "solver_id",
        "solver_code_sha256",
        "config_sha256",
        "seed_policy",
        "input_manifest_sha256",
        "fold_id",
        "started_at",
        "finished_at",
        "wall_budget_seconds",
        "cpu_budget_seconds",
        "runtime_identity",
        "dependency_identities",
        "model_identities",
        "submission_sha256",
        "discovered_task_count",
        "discovered_test_input_count",
        "ground_truth_exposed_to_solver",
        "attempts_generated_before_scoring",
        "max_attempts_per_test_input",
        "network_required",
    }
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)


class RunnerError(RuntimeError):
    """A solver or artifact write failed without consulting correctness data."""


@dataclass(frozen=True, slots=True)
class RunResult:
    """A complete in-memory prediction artifact and discovered input counts."""

    submission: Submission
    task_count: int
    test_input_count: int
    solver_id: str


def canonical_json_bytes(value: object) -> bytes:
    """Return deterministic UTF-8 JSON bytes terminated by one newline."""

    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RunnerError(f"value is not canonical-JSON serializable: {exc}") from exc
    return (text + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_sha256(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def submission_to_jsonable(
    challenges: object, submission: object
) -> dict[str, list[dict[str, list[list[int]]]]]:
    """Validate and convert immutable attempt pairs to the closed JSON shape."""

    candidate = submission
    if isinstance(submission, Mapping) and all(
        isinstance(records, Sequence)
        and not isinstance(records, (str, bytes, bytearray))
        and all(isinstance(pair, AttemptPair) for pair in records)
        for records in submission.values()
    ):
        candidate = {
            task_id: [
                {
                    "attempt_1": grid_to_jsonable(pair.attempt_1),
                    "attempt_2": grid_to_jsonable(pair.attempt_2),
                }
                for pair in records
            ]
            for task_id, records in submission.items()
        }
    validated = validate_submission(challenges, candidate)
    return {
        task_id: [
            {
                "attempt_1": grid_to_jsonable(pair.attempt_1),
                "attempt_2": grid_to_jsonable(pair.attempt_2),
            }
            for pair in pairs
        ]
        for task_id, pairs in validated.items()
    }


def run_solver(
    challenges: object,
    solver: StaticSolver,
    *,
    seed: int = 0,
    budget: SolveBudget | None = None,
) -> RunResult:
    """Invoke ``solver.solve`` exactly once per task, without labels or retries."""

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise RunnerError("seed must be an integer")
    solver_id = getattr(solver, "solver_id", None)
    if not isinstance(solver_id, str) or not solver_id.strip():
        raise RunnerError("solver must expose a nonempty solver_id")
    solve = getattr(solver, "solve", None)
    if not callable(solve):
        raise RunnerError("solver must expose a callable solve method")

    task_views: ChallengeSet = coerce_challenge_set(challenges)
    active_budget = budget or SolveBudget(
        deadline_monotonic=float("inf"),
        max_work_units=(1 << 63) - 1,
    )
    output: Submission = {}

    for task_id in sorted(task_views):
        task = task_views[task_id]
        if time.monotonic() >= active_budget.deadline_monotonic:
            raise RunnerError("solver deadline reached before the next task")
        try:
            raw_pairs = solve(task, seed=seed, budget=active_budget)
        except Exception as exc:
            raise RunnerError(
                f"solver {solver_id!r} failed for task {task_id}; no retry was made"
            ) from exc
        if time.monotonic() >= active_budget.deadline_monotonic:
            raise RunnerError("solver deadline reached; late outputs were discarded")
        if isinstance(raw_pairs, (str, bytes, bytearray)) or not isinstance(
            raw_pairs, Sequence
        ):
            raise RunnerError(
                f"solver {solver_id!r} returned a non-sequence for task {task_id}"
            )
        pairs = tuple(raw_pairs)
        expected_count = len(task.test_inputs)
        if len(pairs) != expected_count:
            raise RunnerError(
                f"solver {solver_id!r} returned {len(pairs)} attempt pairs for "
                f"task {task_id}; expected {expected_count}"
            )

        normalized: list[AttemptPair] = []
        for index, pair in enumerate(pairs):
            if not isinstance(pair, AttemptPair):
                raise RunnerError(
                    f"solver {solver_id!r} result {task_id}[{index}] is not "
                    "an AttemptPair"
                )
            try:
                normalized.append(
                    AttemptPair(
                        attempt_1=validate_grid(
                            pair.attempt_1,
                            f"solver[{task_id}][{index}].attempt_1",
                        ),
                        attempt_2=validate_grid(
                            pair.attempt_2,
                            f"solver[{task_id}][{index}].attempt_2",
                        ),
                    )
                )
            except ValidationError as exc:
                raise RunnerError(
                    f"solver {solver_id!r} returned an invalid grid: {exc}"
                ) from exc
        output[task_id] = tuple(normalized)

    # A final whole-artifact check prevents a partially valid artifact from
    # crossing the runner boundary.
    validated_output = validate_submission(
        task_views,
        {
            task_id: [
                {
                    "attempt_1": grid_to_jsonable(pair.attempt_1),
                    "attempt_2": grid_to_jsonable(pair.attempt_2),
                }
                for pair in pairs
            ]
            for task_id, pairs in output.items()
        },
    )
    return RunResult(
        submission=validated_output,
        task_count=len(task_views),
        test_input_count=sum(len(task.test_inputs) for task in task_views.values()),
        solver_id=solver_id,
    )


def build_submission(
    challenges: object,
    solver: StaticSolver,
    seed: int = 0,
    *,
    budget: SolveBudget | None = None,
) -> dict[str, list[dict[str, list[list[int]]]]]:
    """Build a complete deterministic JSON submission in memory."""

    result = run_solver(challenges, solver, seed=seed, budget=budget)
    return submission_to_jsonable(challenges, result.submission)


def _atomic_write_bytes(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
        try:
            directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        except OSError:
            directory_descriptor = None
        if directory_descriptor is not None:
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    except OSError as exc:
        raise RunnerError(f"could not atomically write {destination}: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def write_json_atomic(destination: str | Path, value: object) -> str:
    """Atomically replace one file with canonical JSON and return its SHA-256."""

    payload = canonical_json_bytes(value)
    _atomic_write_bytes(Path(destination), payload)
    return sha256_bytes(payload)


def write_submission(
    destination: str | Path,
    challenges: object,
    submission: object,
) -> str:
    """Validate and atomically write the required ``submission.json`` artifact."""

    output_path = Path(destination)
    if output_path.name != "submission.json":
        raise RunnerError("submission destination basename must be submission.json")
    jsonable = submission_to_jsonable(challenges, submission)
    return write_json_atomic(output_path, jsonable)


def _manifest_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or _UTC_PATTERN.fullmatch(value) is None:
        raise RunnerError(f"{field} must be an RFC-3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RunnerError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise RunnerError(f"{field} must be timezone-aware")
    return parsed


def _manifest_string(
    value: object,
    field: str,
    *,
    maximum: int,
    pattern: re.Pattern[str] | None = None,
) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise RunnerError(f"{field} must be a nonempty string of at most {maximum} characters")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise RunnerError(f"{field} has an invalid identity format")
    return value


def _manifest_positive_number(value: object, field: str) -> int | float:
    if isinstance(value, bool) or type(value) not in {int, float}:
        raise RunnerError(f"{field} must be a JSON number, not a boolean")
    if not math.isfinite(float(value)) or value <= 0:
        raise RunnerError(f"{field} must be finite and positive")
    return value


def _manifest_identities(value: object, field: str) -> list[str]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise RunnerError(f"{field} must be an array")
    result = [
        _manifest_string(item, f"{field}[{index}]", maximum=512)
        for index, item in enumerate(value)
    ]
    if len(result) != len(set(result)):
        raise RunnerError(f"{field} must not contain duplicate identities")
    return result


def validate_run_manifest(value: object) -> dict[str, Any]:
    """Fail closed on the complete run-manifest schema and its relationships."""

    if not isinstance(value, Mapping):
        raise RunnerError("run manifest must be an object")
    if not all(isinstance(field, str) for field in value):
        raise RunnerError("run manifest field names must be strings")
    actual_fields = set(value)
    if actual_fields != RUN_MANIFEST_FIELDS:
        missing = sorted(RUN_MANIFEST_FIELDS - actual_fields)
        extra = sorted(actual_fields - RUN_MANIFEST_FIELDS)
        raise RunnerError(
            f"run manifest field mismatch; missing={missing!r}, extra={extra!r}"
        )
    if value["schema"] != RUN_MANIFEST_SCHEMA:
        raise RunnerError("run manifest schema identity mismatch")

    _manifest_string(value["run_id"], "run_id", maximum=128, pattern=_RUN_ID_PATTERN)
    mode = value["mode"]
    if not isinstance(mode, str) or mode not in RUN_MODES:
        raise RunnerError(f"unsupported run mode: {mode!r}")
    for field in (
        "source_lock_sha256",
        "solver_code_sha256",
        "config_sha256",
        "input_manifest_sha256",
        "submission_sha256",
    ):
        digest = _manifest_string(
            value[field], field, maximum=64, pattern=_SHA256_PATTERN
        )
        if digest == "0" * 64:
            raise RunnerError(f"{field} cannot be an all-zero placeholder")
    for field in ("branch_commit", "branch_tree"):
        identity = _manifest_string(
            value[field], field, maximum=40, pattern=_GIT_OBJECT_PATTERN
        )
        if identity == "0" * 40:
            raise RunnerError(f"{field} cannot be an all-zero placeholder")
    _manifest_string(value["solver_id"], "solver_id", maximum=256)
    _manifest_string(value["seed_policy"], "seed_policy", maximum=512)
    _manifest_string(value["runtime_identity"], "runtime_identity", maximum=512)

    fold_id = value["fold_id"]
    if mode == "TRAIN_CV":
        _manifest_string(fold_id, "fold_id", maximum=128)
    elif fold_id is not None:
        raise RunnerError(f"fold_id must be null in {mode} mode")

    started_at = _manifest_utc(value["started_at"], "started_at")
    finished_at = _manifest_utc(value["finished_at"], "finished_at")
    if finished_at < started_at:
        raise RunnerError("finished_at must not precede started_at")
    wall_budget = _manifest_positive_number(
        value["wall_budget_seconds"], "wall_budget_seconds"
    )
    cpu_budget = _manifest_positive_number(
        value["cpu_budget_seconds"], "cpu_budget_seconds"
    )
    if cpu_budget > wall_budget:
        raise RunnerError("cpu_budget_seconds must not exceed wall_budget_seconds")
    elapsed_seconds = (finished_at - started_at).total_seconds()
    if elapsed_seconds > wall_budget:
        raise RunnerError("run elapsed time must not exceed wall_budget_seconds")
    dependencies = _manifest_identities(
        value["dependency_identities"], "dependency_identities"
    )
    models = _manifest_identities(value["model_identities"], "model_identities")

    for field in ("discovered_task_count", "discovered_test_input_count"):
        count = value[field]
        if isinstance(count, bool) or type(count) is not int or count < 1:
            raise RunnerError(f"{field} must be a positive integer, not a boolean")
    if value["discovered_test_input_count"] < value["discovered_task_count"]:
        raise RunnerError("test-input count cannot be smaller than task count")
    expected_constants = {
        "ground_truth_exposed_to_solver": False,
        "attempts_generated_before_scoring": True,
        "max_attempts_per_test_input": 2,
        "network_required": False,
    }
    for field, expected in expected_constants.items():
        if value[field] is not expected and value[field] != expected:
            raise RunnerError(f"run manifest safety assertion {field} changed")
        if field == "max_attempts_per_test_input" and type(value[field]) is not int:
            raise RunnerError("max_attempts_per_test_input must be integer 2")
        if field != "max_attempts_per_test_input" and type(value[field]) is not bool:
            raise RunnerError(f"{field} must be a JSON boolean")

    validated = dict(value)
    validated["dependency_identities"] = dependencies
    validated["model_identities"] = models
    return validated


def create_run_manifest(
    *,
    run_id: str,
    mode: str,
    source_lock_sha256: str,
    branch_commit: str,
    branch_tree: str,
    solver_id: str,
    solver_code_sha256: str,
    config_sha256: str,
    seed_policy: str,
    input_manifest_sha256: str,
    fold_id: str | None,
    started_at: str,
    finished_at: str,
    wall_budget_seconds: float,
    cpu_budget_seconds: float,
    runtime_identity: str,
    dependency_identities: Sequence[str],
    model_identities: Sequence[str],
    submission_sha256: str,
    discovered_task_count: int,
    discovered_test_input_count: int,
) -> dict[str, Any]:
    """Create the closed provenance record for an already-built submission."""

    manifest = {
        "schema": RUN_MANIFEST_SCHEMA,
        "run_id": run_id,
        "mode": mode,
        "source_lock_sha256": source_lock_sha256,
        "branch_commit": branch_commit,
        "branch_tree": branch_tree,
        "solver_id": solver_id,
        "solver_code_sha256": solver_code_sha256,
        "config_sha256": config_sha256,
        "seed_policy": seed_policy,
        "input_manifest_sha256": input_manifest_sha256,
        "fold_id": fold_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "wall_budget_seconds": wall_budget_seconds,
        "cpu_budget_seconds": cpu_budget_seconds,
        "runtime_identity": runtime_identity,
        "dependency_identities": list(dependency_identities),
        "model_identities": list(model_identities),
        "submission_sha256": submission_sha256,
        "discovered_task_count": discovered_task_count,
        "discovered_test_input_count": discovered_test_input_count,
        "ground_truth_exposed_to_solver": False,
        "attempts_generated_before_scoring": True,
        "max_attempts_per_test_input": 2,
        "network_required": False,
    }
    return validate_run_manifest(manifest)


def write_run_manifest(destination: str | Path, manifest: Mapping[str, Any]) -> str:
    """Atomically write deterministic manifest bytes supplied by the caller."""

    return write_json_atomic(destination, validate_run_manifest(manifest))
