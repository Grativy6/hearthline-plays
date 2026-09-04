#!/usr/bin/env python3
"""Score an explicit synthetic run or one preflight-completed public audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from hearthline_arc2.scoring import (  # noqa: E402
    create_score_receipt,
    score_submission,
)
from hearthline_arc2.contracts import IdentityZeroBaseline  # noqa: E402
from hearthline_arc2.authorization import (  # noqa: E402
    AuthorizationError,
    canonical_grant_sha256,
    claim_public_evaluation,
)
from hearthline_arc2.runner import RunnerError, validate_run_manifest  # noqa: E402
from hearthline_arc2.synthetic import (  # noqa: E402
    SyntheticFixtureError,
    load_synthetic_artifact,
)
from hearthline_arc2.validation import (  # noqa: E402
    ValidationError,
    load_json,
    solutions_to_jsonable,
    validate_input_manifest,
    validate_input_manifest_challenge_snapshot,
    validate_solver_config,
)


CANONICAL_LEDGER = REPOSITORY_ROOT / "ignition" / "consumption-ledger"
SOURCE_LOCK = REPOSITORY_ROOT / "provenance" / "official-sources.lock.json"
UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
PUBLIC_GRANT_FIELDS = {
    "schema",
    "grant_id",
    "scope",
    "competition_slug",
    "branch_commit",
    "branch_tree",
    "source_lock_sha256",
    "notebook_sha256",
    "solver_code_sha256",
    "config_sha256",
    "input_manifest_sha256",
    "run_manifest_sha256",
    "submission_sha256",
    "solution_semantic_sha256",
    "hardware_class",
    "max_runtime_seconds",
    "issued_at",
    "expires_at",
    "nonce",
    "human_approver",
    "acknowledgement",
}
PUBLIC_ACKNOWLEDGEMENT = (
    "I authorize exactly one sealed public-evaluation audit; its aggregate "
    "result will not be used for tuning."
)
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "synthetic"


def _read_and_hash(path: Path) -> tuple[object, str, int]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{path} is not UTF-8 JSON") from exc
    from hearthline_arc2.validation import parse_json

    return parse_json(text), hashlib.sha256(payload).hexdigest(), len(payload)


def _canonical_bytes(value: object) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"receipt is not JSON serializable: {exc}") from exc
    return (text + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise ValidationError(f"cannot atomically write receipt {path}: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and output-pair-weight score an already-closed ARC-AGI-2 "
            "submission. This command never loads or runs a solver."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("synthetic", "public-eval"),
        required=True,
        help="mode is mandatory and is never inferred from omitted flags",
    )
    parser.add_argument("--challenges", type=Path, required=True)
    parser.add_argument("--solutions", type=Path, required=True)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument(
        "--grant",
        type=Path,
        help="preflight-completed PUBLIC_EVAL_ONCE grant; forbidden in synthetic mode",
    )
    parser.add_argument(
        "--input-manifest",
        type=Path,
        help=(
            "public-eval manifest binding challenge digest, bytes, counts, exact "
            "split/filename, source lock, and ARC-AGI-2 Git pin"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="public-eval solver configuration; forbidden in synthetic mode",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        help="public-eval frozen run manifest; forbidden in synthetic mode",
    )
    return parser


def _git_object(revision: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", revision],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuthorizationError("cannot verify the bound local revision") from exc
    return completed.stdout.strip()


def _git_is_clean() -> bool:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuthorizationError("cannot verify clean public-evaluation state") from exc
    return not completed.stdout


def _grant_time(value: object) -> datetime:
    if not isinstance(value, str) or UTC_PATTERN.fullmatch(value) is None:
        raise AuthorizationError("grant time is invalid")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise AuthorizationError("grant time is invalid") from exc


def _sha256_named_sources(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _semantic_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[0-9a-f]{64}", value) is None
        or value == "0" * 64
    ):
        raise AuthorizationError(f"invalid {field}")
    return value


def _require_fresh_public_source_reviews(source_lock: dict, now: datetime) -> None:
    surfaces = source_lock.get("mutable_surfaces")
    if not isinstance(surfaces, list) or len(surfaces) != 7:
        raise AuthorizationError("public source reviews are incomplete")
    for surface in surfaces:
        if (
            not isinstance(surface, dict)
            or surface.get("status") != "FROZEN_HUMAN_REVIEWED"
            or surface.get("human_reviewer") != "Christopher D. Pang"
        ):
            raise AuthorizationError("public source reviews are not human-frozen")
        _require_sha256(surface.get("content_sha256"), "source review digest")
        retrieved = _grant_time(surface.get("retrieval_utc"))
        revalidate_before = _grant_time(surface.get("revalidate_before"))
        if not retrieved <= now < revalidate_before:
            raise AuthorizationError("public source review is stale")


def _authorize_public_evaluation(
    args: argparse.Namespace,
) -> tuple[dict, dict, dict, str, str]:
    """Verify safe metadata and claim the one-shot key before task-file access."""

    if any(
        item is None
        for item in (args.grant, args.input_manifest, args.config, args.run_manifest)
    ):
        raise AuthorizationError(
            "public evaluation requires grant, config, input manifest, and run manifest"
        )
    grant = load_json(args.grant)
    if not isinstance(grant, dict) or set(grant) != PUBLIC_GRANT_FIELDS:
        raise AuthorizationError("public-evaluation grant must be an object")
    if (
        grant.get("schema") != "hearthline-plays.arc2-ignition-grant.v1"
        or grant.get("scope") != "PUBLIC_EVAL_ONCE"
        or grant.get("competition_slug") != "arc-prize-2026-arc-agi-2"
        or grant.get("human_approver") != "Christopher D. Pang"
        or grant.get("acknowledgement") != PUBLIC_ACKNOWLEDGEMENT
    ):
        raise AuthorizationError("public-evaluation grant has the wrong scope")
    for field in (
        "source_lock_sha256",
        "notebook_sha256",
        "solver_code_sha256",
        "config_sha256",
        "input_manifest_sha256",
        "run_manifest_sha256",
        "submission_sha256",
        "solution_semantic_sha256",
        "nonce",
    ):
        _require_sha256(grant.get(field), field)
    if type(grant.get("max_runtime_seconds")) is not int or not (
        1 <= grant["max_runtime_seconds"] <= 43200
    ):
        raise AuthorizationError("invalid public-evaluation runtime")
    now = datetime.now(timezone.utc)
    issued_at = _grant_time(grant.get("issued_at"))
    expires_at = _grant_time(grant.get("expires_at"))
    if not issued_at <= now < expires_at:
        raise AuthorizationError("public-evaluation grant is not currently valid")
    if issued_at >= expires_at:
        raise AuthorizationError("public-evaluation grant time range is invalid")
    if not _git_is_clean():
        raise AuthorizationError("public evaluation requires a clean worktree")
    manifest, manifest_sha256, _ = _read_and_hash(args.input_manifest)
    if not isinstance(manifest, dict):
        raise AuthorizationError("input manifest must be an object")
    source_lock, source_lock_sha256, _ = _read_and_hash(SOURCE_LOCK)
    if grant.get("source_lock_sha256") != source_lock_sha256:
        raise AuthorizationError("grant does not bind the source lock")
    if not isinstance(source_lock, dict):
        raise AuthorizationError("source lock is invalid")
    validate_input_manifest(
        manifest,
        "$.input_manifest",
        source_lock_value=source_lock,
        source_lock_sha256=source_lock_sha256,
        expected_split="PUBLIC_EVALUATION",
    )
    if grant.get("input_manifest_sha256") != manifest_sha256:
        raise AuthorizationError("grant does not bind the input manifest")
    _require_fresh_public_source_reviews(source_lock, now)
    public_commitment = source_lock.get("challenge_commitments", {}).get(
        "PUBLIC_EVALUATION", {}
    )
    if (
        not isinstance(public_commitment, dict)
        or grant["solution_semantic_sha256"]
        != public_commitment.get("solution_semantic_sha256")
    ):
        raise AuthorizationError("grant does not bind the public solution identity")
    if grant.get("branch_commit") != _git_object("HEAD"):
        raise AuthorizationError("grant does not bind the current commit")
    if grant.get("branch_tree") != _git_object("HEAD^{tree}"):
        raise AuthorizationError("grant does not bind the current tree")

    config, config_sha256, _ = _read_and_hash(args.config)
    if grant["config_sha256"] != config_sha256:
        raise AuthorizationError("grant does not bind the solver config")
    validated_config = validate_solver_config(
        config,
        "$.config",
        expected_hardware_class=grant.get("hardware_class"),
        expected_max_runtime_seconds=grant["max_runtime_seconds"],
        expected_solver_id=IdentityZeroBaseline.solver_id,
    )
    solver_sha256 = _sha256_named_sources(
        [
            SOURCE_ROOT / "hearthline_arc2" / "contracts.py",
            SOURCE_ROOT / "hearthline_arc2" / "runner.py",
            SOURCE_ROOT / "hearthline_arc2" / "validation.py",
        ]
    )
    if grant["solver_code_sha256"] != solver_sha256:
        raise AuthorizationError("grant does not bind the executable solver code")
    notebook_sha256 = hashlib.sha256(
        (REPOSITORY_ROOT / "notebook" / "arc2_submission.ipynb").read_bytes()
    ).hexdigest()
    if grant["notebook_sha256"] != notebook_sha256:
        raise AuthorizationError("grant does not bind the reviewed notebook")

    run_manifest, run_manifest_sha256, _ = _read_and_hash(args.run_manifest)
    if grant["run_manifest_sha256"] != run_manifest_sha256:
        raise AuthorizationError("grant does not bind the run manifest")
    validated_run = validate_run_manifest(run_manifest)
    exact_run_bindings = {
        "mode": "PUBLIC_EVAL",
        "source_lock_sha256": source_lock_sha256,
        "branch_commit": grant["branch_commit"],
        "branch_tree": grant["branch_tree"],
        "solver_id": validated_config["solver_id"],
        "solver_code_sha256": solver_sha256,
        "config_sha256": config_sha256,
        "input_manifest_sha256": manifest_sha256,
        "submission_sha256": grant["submission_sha256"],
        "wall_budget_seconds": validated_config["wall_budget_seconds"],
        "cpu_budget_seconds": validated_config["cpu_budget_seconds"],
        "dependency_identities": validated_config["dependency_identities"],
        "model_identities": validated_config["model_identities"],
        "discovered_task_count": manifest["task_count"],
        "discovered_test_input_count": manifest["test_input_count"],
    }
    for field, expected in exact_run_bindings.items():
        if validated_run.get(field) != expected:
            raise AuthorizationError(f"run manifest does not bind {field}")
    expected_seed_policy = (
        f"fixed integer seed {validated_config['seed']}; identical seed passed once per task"
    )
    if validated_run["seed_policy"] != expected_seed_policy:
        raise AuthorizationError("run manifest does not bind the solver seed policy")
    run_started = _grant_time(validated_run["started_at"])
    run_finished = _grant_time(validated_run["finished_at"])
    if not run_started <= run_finished <= issued_at:
        raise AuthorizationError("public run must be frozen before its grant is issued")
    grant_sha256 = canonical_grant_sha256(grant)
    claim_public_evaluation(grant, CANONICAL_LEDGER)
    return grant, manifest, validated_run, grant_sha256, run_manifest_sha256


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    public_mode = args.mode == "public-eval"
    if not public_mode and any(
        item is not None
        for item in (args.grant, args.input_manifest, args.config, args.run_manifest)
    ):
        print("score failed: synthetic mode forbids external authorization inputs", file=sys.stderr)
        return 2
    grant_sha256: str | None = None
    run_manifest_sha256: str | None = None
    try:
        input_manifest: dict | None = None
        run_manifest: dict | None = None
        if public_mode:
            (
                grant,
                input_manifest,
                run_manifest,
                grant_sha256,
                run_manifest_sha256,
            ) = _authorize_public_evaluation(args)
        else:
            challenges, challenge_sha256, _ = load_synthetic_artifact(
                args.challenges, FIXTURE_ROOT, "challenges.json"
            )
            solutions, solution_sha256, _ = load_synthetic_artifact(
                args.solutions, FIXTURE_ROOT, "solutions.json"
            )
            submission, submission_sha256, _ = load_synthetic_artifact(
                args.submission, FIXTURE_ROOT, "submission.json"
            )
        if public_mode:
            if args.input_manifest is None or input_manifest is None:
                raise AuthorizationError("public input binding disappeared")
            challenges, challenge_sha256, challenge_byte_count = _read_and_hash(
                args.challenges
            )
            challenges = validate_input_manifest_challenge_snapshot(
                input_manifest,
                challenges,
                challenge_filename=args.challenges.name,
                challenge_raw_sha256=challenge_sha256,
                challenge_byte_count=challenge_byte_count,
                path="$.input_manifest",
            )
            solutions, solution_sha256, _ = _read_and_hash(args.solutions)
            submission, submission_sha256, _ = _read_and_hash(args.submission)
            if run_manifest is None:
                raise AuthorizationError("public run binding disappeared")
            if submission_sha256 != grant["submission_sha256"]:
                raise AuthorizationError("scored submission differs from the authorized run")
            solution_semantic_sha256 = _semantic_sha256(
                solutions_to_jsonable(challenges, solutions)
            )
            if solution_semantic_sha256 != grant["solution_semantic_sha256"]:
                raise AuthorizationError("solution set differs from its locked identity")
        result = score_submission(challenges, solutions, submission)
        scorer_sha256 = hashlib.sha256(
            (SOURCE_ROOT / "hearthline_arc2" / "scoring.py").read_bytes()
        ).hexdigest()
        receipt = create_score_receipt(
            result,
            scorer_sha256=scorer_sha256,
            challenge_sha256=challenge_sha256,
            solution_sha256=solution_sha256,
            submission_sha256=submission_sha256,
            mode="PUBLIC_EVAL" if public_mode else "SYNTHETIC",
            authorization_grant_sha256=grant_sha256,
            run_manifest_sha256=run_manifest_sha256,
        )
        receipt_bytes = _canonical_bytes(receipt)
        if args.receipt is not None:
            _atomic_write(args.receipt, receipt_bytes)
    except (
        AuthorizationError,
        OSError,
        RunnerError,
        SyntheticFixtureError,
        ValidationError,
        RuntimeError,
        ValueError,
    ) as exc:
        if public_mode:
            # No task identifier, artifact path, grid, or per-task detail may cross
            # the sealed scorer boundary, including validation failures.
            print("score failed: sealed public-evaluation audit failed", file=sys.stderr)
        else:
            print(f"score failed: {exc}", file=sys.stderr)
        return 2

    # The terminal surface remains aggregate-only in content even for
    # fabricated-fixture mode: no task IDs, predictions, or labels are logged.
    print(receipt_bytes.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
