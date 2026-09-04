"""Fail-closed semantic validation for ARC-AGI-2 JSON artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, TypeAlias

from .contracts import AttemptPair, Demonstration, Grid, TaskView


TASK_ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")
MIN_GRID_SIZE = 1
MAX_GRID_SIZE = 30
COMPETITION_SLUG = "arc-prize-2026-arc-agi-2"
ARC2_PUBLIC_REPOSITORY = "arcprize/ARC-AGI-2"
ARC2_PUBLIC_COMMIT = "f3283f727488ad98fe575ea6a5ac981e4a188e49"
ARC2_PUBLIC_TREE = "afab62b97f29dd2341f401d4af70491e14da35c2"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
KAGGLE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}/hearthline-arc-agi-2-2026$"
)
KAGGLE_ACCELERATOR_MACHINE_SHAPES = frozenset(
    {
        "NvidiaTeslaP100",
        "NvidiaTeslaT4",
    }
)

KERNEL_METADATA_SCHEMA = "hearthline-plays.arc2-kernel-metadata.v1"
SOLVER_CONFIG_SCHEMA = "hearthline-plays.arc2-solver-config.v1"
INPUT_MANIFEST_SCHEMA = "hearthline-plays.arc2-input-manifest.v1"
SOURCE_LOCK_SCHEMA = "hearthline-plays.arc2-source-lock.v1"
UNFROZEN_SOURCE_STATUS = "UNFROZEN_REVALIDATE_BEFORE_EXTERNAL_GRANT"
FROZEN_SOURCE_STATUS = "FROZEN_HUMAN_REVIEWED"

PUBLIC_CHALLENGE_COMMITMENTS: dict[str, dict[str, object]] = {
    "TRAINING": {
        "status": "PINNED_GIT_TREE",
        "origin": "PINNED_ARC2_PUBLIC_REPOSITORY",
        "repository_path": "data/training",
        "source_tree": "dac7259367cc5099ef6a7b604a50a93affbbee33",
        "challenge_semantic_sha256": (
            "0cae8c51dcec8b25ecfbdefc2907c1e51983bccaf1a8d621f169cbe81fc001fe"
        ),
        "solution_semantic_sha256": (
            "6d668c1911653f40610bb237769e144919768b8dbeecd233516891d34d4c6503"
        ),
        "task_count": 1000,
        "test_input_count": 1076,
    },
    "PUBLIC_EVALUATION": {
        "status": "PINNED_GIT_TREE",
        "origin": "PINNED_ARC2_PUBLIC_REPOSITORY",
        "repository_path": "data/evaluation",
        "source_tree": "8d04288aac3146b7c47d0b799c18bc9c0217d838",
        "challenge_semantic_sha256": (
            "8cade36130fdf1fa8fbab00cfcdfb5be8e74acbf04140f6fe18c5f502f0639be"
        ),
        "solution_semantic_sha256": (
            "e623ea77ee8993928c50c4a5a51d3ed8c75c30e9bb65dcd480140d89f6fa5f9f"
        ),
        "task_count": 120,
        "test_input_count": 167,
    },
}

INPUT_SPLIT_CONTRACTS = {
    "TRAINING": (
        "PINNED_ARC2_PUBLIC_REPOSITORY",
        "arc-agi_training_challenges.json",
    ),
    "PUBLIC_EVALUATION": (
        "PINNED_ARC2_PUBLIC_REPOSITORY",
        "arc-agi_evaluation_challenges.json",
    ),
    "KAGGLE_HIDDEN": (
        "KAGGLE_COMPETITION_MOUNT",
        "arc-agi_test_challenges.json",
    ),
}

ChallengeSet: TypeAlias = dict[str, TaskView]
Submission: TypeAlias = dict[str, tuple[AttemptPair, ...]]
SolutionSet: TypeAlias = dict[str, tuple[Grid, ...]]


class ValidationError(ValueError):
    """An artifact violates a closed structural or semantic contract."""


def _fail(path: str, message: str) -> NoReturn:
    raise ValidationError(f"{path}: {message}")


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )


def _require_mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(path, "must be an object")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], path: str
) -> None:
    actual = set(value)
    missing = sorted(expected - actual, key=repr)
    extra = sorted(actual - expected, key=repr)
    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append(f"missing keys {missing!r}")
        if extra:
            parts.append(f"unexpected keys {extra!r}")
        _fail(path, "; ".join(parts))


def validate_task_id(value: object, path: str = "$.task_id") -> str:
    if not isinstance(value, str) or TASK_ID_PATTERN.fullmatch(value) is None:
        _fail(path, "must match ^[0-9a-f]{8}$")
    return value


def validate_grid(value: object, path: str = "$") -> Grid:
    """Validate and freeze one 1..30 by 1..30 ARC color grid.

    Python booleans are rejected explicitly even though ``bool`` is a subclass
    of ``int``.
    """

    if not _is_sequence(value):
        _fail(path, "grid must be an array of rows")
    rows = list(value)
    if not MIN_GRID_SIZE <= len(rows) <= MAX_GRID_SIZE:
        _fail(path, "grid must contain between 1 and 30 rows")

    frozen_rows: list[tuple[int, ...]] = []
    width: int | None = None
    for row_index, row in enumerate(rows):
        row_path = f"{path}[{row_index}]"
        if not _is_sequence(row):
            _fail(row_path, "row must be an array")
        cells = list(row)
        if not MIN_GRID_SIZE <= len(cells) <= MAX_GRID_SIZE:
            _fail(row_path, "row must contain between 1 and 30 cells")
        if width is None:
            width = len(cells)
        elif len(cells) != width:
            _fail(row_path, f"ragged row; expected {width} cells")

        frozen_cells: list[int] = []
        for column_index, cell in enumerate(cells):
            cell_path = f"{row_path}[{column_index}]"
            if type(cell) is not int:
                _fail(cell_path, "cell must be an integer, not a boolean")
            if not 0 <= cell <= 9:
                _fail(cell_path, "cell must be between 0 and 9")
            frozen_cells.append(cell)
        frozen_rows.append(tuple(frozen_cells))
    return tuple(frozen_rows)


def _validate_demonstration(value: object, path: str) -> Demonstration:
    item = _require_mapping(value, path)
    _require_exact_keys(item, {"input", "output"}, path)
    return Demonstration(
        input=validate_grid(item["input"], f"{path}.input"),
        output=validate_grid(item["output"], f"{path}.output"),
    )


def _validate_unlabeled_test(value: object, path: str) -> Grid:
    item = _require_mapping(value, path)
    _require_exact_keys(item, {"input"}, path)
    return validate_grid(item["input"], f"{path}.input")


def _require_nonempty_array(value: object, path: str) -> list[Any]:
    if not _is_sequence(value):
        _fail(path, "must be an array")
    items = list(value)
    if not items:
        _fail(path, "must not be empty")
    return items


def _require_string(
    value: object,
    path: str,
    *,
    minimum: int = 1,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        _fail(path, f"must be a string of length {minimum}..{maximum}")
    return value


def _require_sha256(value: object, path: str, *, nonzero: bool = True) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        _fail(path, "must be a lowercase full SHA-256")
    if nonzero and value == "0" * 64:
        _fail(path, "all-zero placeholder SHA-256 is forbidden")
    return value


def _require_positive_integer(value: object, path: str) -> int:
    if type(value) is not int or value < 1:
        _fail(path, "must be a positive integer, not a boolean")
    return value


def _require_identity_list(value: object, path: str) -> list[str]:
    if not isinstance(value, list):
        _fail(path, "must be a JSON array")
    result: list[str] = []
    for index, identity in enumerate(value):
        result.append(_require_string(identity, f"{path}[{index}]"))
    if len(result) != len(set(result)):
        _fail(path, "must not contain duplicate identities")
    if result != sorted(result):
        _fail(path, "identities must be in ascending bytewise order")
    return result


def validate_kernel_metadata(
    value: object,
    path: str = "$",
    *,
    allow_placeholder_id: bool = False,
) -> dict[str, Any]:
    """Validate the exact, private, network-off Kaggle notebook descriptor.

    The accepted accelerator names are the finite set recorded by the pinned
    Kaggle API source.  Other datasets, kernels, or models cannot be attached
    implicitly; a future source-enabled solver must introduce and review a new
    contract rather than widening this one at ignition time.
    """

    metadata = _require_mapping(value, path)
    expected_keys = {
        "id",
        "title",
        "code_file",
        "language",
        "kernel_type",
        "is_private",
        "enable_gpu",
        "enable_tpu",
        "enable_internet",
        "machine_shape",
        "dataset_sources",
        "competition_sources",
        "kernel_sources",
        "model_sources",
    }
    _require_exact_keys(metadata, expected_keys, path)

    identifier = _require_string(metadata["id"], f"{path}.id", maximum=128)
    placeholder = "<kaggle-username>/hearthline-arc-agi-2-2026"
    if identifier == placeholder:
        if not allow_placeholder_id:
            _fail(f"{path}.id", "placeholder notebook ID is forbidden")
    elif KAGGLE_ID_PATTERN.fullmatch(identifier) is None:
        _fail(
            f"{path}.id",
            "must bind a Kaggle owner to hearthline-arc-agi-2-2026",
        )

    exact_strings = {
        "title": "Hearthline ARC-AGI-2 2026",
        "code_file": "arc2_submission.ipynb",
        "language": "python",
        "kernel_type": "notebook",
    }
    for field, expected in exact_strings.items():
        if metadata[field] != expected:
            _fail(f"{path}.{field}", f"must equal {expected!r}")
    if metadata["is_private"] is not True:
        _fail(f"{path}.is_private", "must be the JSON boolean true")
    if metadata["enable_internet"] is not False:
        _fail(f"{path}.enable_internet", "must be the JSON boolean false")
    if type(metadata["enable_gpu"]) is not bool:
        _fail(f"{path}.enable_gpu", "must be a JSON boolean")
    if metadata["enable_tpu"] is not False:
        _fail(
            f"{path}.enable_tpu",
            "must be the JSON boolean false in the reviewed v1 profile",
        )
    if not isinstance(metadata["machine_shape"], str):
        _fail(f"{path}.machine_shape", "must be a string")

    machine_shape = metadata["machine_shape"]
    if metadata["enable_gpu"]:
        if machine_shape not in KAGGLE_ACCELERATOR_MACHINE_SHAPES:
            _fail(
                f"{path}.machine_shape",
                "must name an accelerator from the pinned Kaggle API source",
            )
    elif machine_shape != "":
        _fail(
            f"{path}.machine_shape",
            "must be empty when enable_gpu is false",
        )

    expected_sources = {
        "dataset_sources": [],
        "competition_sources": [COMPETITION_SLUG],
        "kernel_sources": [],
        "model_sources": [],
    }
    for field, expected in expected_sources.items():
        if metadata[field] != expected:
            _fail(f"{path}.{field}", f"must equal {expected!r}")

    return dict(metadata)


def kernel_metadata_hardware_class(value: object) -> str:
    """Derive the only hardware-class string valid for a metadata document."""

    metadata = validate_kernel_metadata(value, allow_placeholder_id=True)
    if metadata["enable_gpu"] is False:
        return "kaggle-cpu"
    return f"kaggle-accelerator:{metadata['machine_shape']}"


def validate_solver_config(
    value: object,
    path: str = "$",
    *,
    expected_hardware_class: str | None = None,
    expected_max_runtime_seconds: int | None = None,
    expected_solver_id: str | None = None,
) -> dict[str, Any]:
    """Validate one frozen, deterministic external solver configuration."""

    config = _require_mapping(value, path)
    expected_keys = {
        "schema",
        "competition_slug",
        "solver_id",
        "seed",
        "seed_policy",
        "deterministic",
        "wall_budget_seconds",
        "cpu_budget_seconds",
        "max_work_units",
        "hardware_class",
        "dependency_identities",
        "model_identities",
        "max_attempts_per_test_input",
        "network_required",
    }
    _require_exact_keys(config, expected_keys, path)
    if config["schema"] != SOLVER_CONFIG_SCHEMA:
        _fail(f"{path}.schema", f"must equal {SOLVER_CONFIG_SCHEMA!r}")
    if config["competition_slug"] != COMPETITION_SLUG:
        _fail(f"{path}.competition_slug", "must bind the ARC-AGI-2 competition")
    solver_id = _require_string(
        config["solver_id"], f"{path}.solver_id", maximum=256
    )
    if expected_solver_id is not None and solver_id != expected_solver_id:
        _fail(f"{path}.solver_id", "does not match the selected solver")
    if type(config["seed"]) is not int:
        _fail(f"{path}.seed", "must be an integer, not a boolean")
    if config["seed_policy"] != "FIXED_INTEGER_PER_TASK":
        _fail(
            f"{path}.seed_policy",
            "must equal 'FIXED_INTEGER_PER_TASK'",
        )
    if config["deterministic"] is not True:
        _fail(f"{path}.deterministic", "must be the JSON boolean true")
    wall_budget = _require_positive_integer(
        config["wall_budget_seconds"], f"{path}.wall_budget_seconds"
    )
    if wall_budget > 43200:
        _fail(f"{path}.wall_budget_seconds", "must not exceed 43200")
    cpu_budget = _require_positive_integer(
        config["cpu_budget_seconds"], f"{path}.cpu_budget_seconds"
    )
    if cpu_budget > wall_budget:
        _fail(f"{path}.cpu_budget_seconds", "must not exceed wall budget")
    _require_positive_integer(config["max_work_units"], f"{path}.max_work_units")
    hardware_class = _require_string(
        config["hardware_class"], f"{path}.hardware_class", maximum=128
    )
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", hardware_class) is None:
        _fail(f"{path}.hardware_class", "contains unsupported characters")
    _require_identity_list(
        config["dependency_identities"], f"{path}.dependency_identities"
    )
    _require_identity_list(config["model_identities"], f"{path}.model_identities")
    if config["max_attempts_per_test_input"] != 2:
        _fail(f"{path}.max_attempts_per_test_input", "must equal 2")
    if config["network_required"] is not False:
        _fail(f"{path}.network_required", "must be the JSON boolean false")
    if (
        expected_hardware_class is not None
        and hardware_class != expected_hardware_class
    ):
        _fail(f"{path}.hardware_class", "does not match the selected hardware")
    if (
        expected_max_runtime_seconds is not None
        and wall_budget != expected_max_runtime_seconds
    ):
        _fail(
            f"{path}.wall_budget_seconds",
            "does not match the selected maximum runtime",
        )
    return dict(config)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ValidationError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _require_git_object(value: object, path: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        _fail(path, "must be a lowercase full 40-character Git object ID")
    return value


def _require_utc(value: object, path: str) -> str:
    timestamp = _require_string(value, path, maximum=64)
    if UTC_PATTERN.fullmatch(timestamp) is None:
        _fail(path, "must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as exc:
        raise ValidationError(f"{path}: invalid ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        _fail(path, "must be timezone-aware")
    return timestamp


def _validate_kaggle_challenge_commitment(
    value: object,
    path: str,
    *,
    require_frozen: bool,
) -> dict[str, Any]:
    commitment = _require_mapping(value, path)
    status = commitment.get("status")
    base_keys = {
        "status",
        "origin",
        "challenge_filename",
        "challenge_raw_sha256",
        "challenge_semantic_sha256",
        "task_count",
        "test_input_count",
    }
    if status == UNFROZEN_SOURCE_STATUS:
        _require_exact_keys(commitment, base_keys, path)
        if require_frozen:
            _fail(path, "Kaggle hidden challenge commitment is still unfrozen")
        for field in (
            "challenge_raw_sha256",
            "challenge_semantic_sha256",
            "task_count",
            "test_input_count",
        ):
            if commitment[field] is not None:
                _fail(f"{path}.{field}", "must be null while the artifact is unfrozen")
    elif status == FROZEN_SOURCE_STATUS:
        _require_exact_keys(
            commitment,
            base_keys
            | {"retrieval_utc", "human_reviewer", "revalidate_before"},
            path,
        )
        _require_sha256(
            commitment["challenge_raw_sha256"],
            f"{path}.challenge_raw_sha256",
        )
        _require_sha256(
            commitment["challenge_semantic_sha256"],
            f"{path}.challenge_semantic_sha256",
        )
        _require_positive_integer(commitment["task_count"], f"{path}.task_count")
        _require_positive_integer(
            commitment["test_input_count"], f"{path}.test_input_count"
        )
        retrieval_utc = _require_utc(
            commitment["retrieval_utc"], f"{path}.retrieval_utc"
        )
        revalidate_before = _require_utc(
            commitment["revalidate_before"], f"{path}.revalidate_before"
        )
        retrieval_time = datetime.fromisoformat(retrieval_utc[:-1] + "+00:00")
        revalidation_time = datetime.fromisoformat(
            revalidate_before[:-1] + "+00:00"
        )
        if revalidation_time <= retrieval_time:
            _fail(f"{path}.revalidate_before", "must follow retrieval_utc")
        if commitment["human_reviewer"] != "Christopher D. Pang":
            _fail(
                f"{path}.human_reviewer",
                "must retain Christopher D. Pang as the human reviewer",
            )
    else:
        _fail(
            f"{path}.status",
            "must be explicitly unfrozen or independently human-frozen",
        )
    if commitment["origin"] != "KAGGLE_COMPETITION_MOUNT":
        _fail(
            f"{path}.origin",
            "must identify the Kaggle competition mount, not the public Git source",
        )
    if commitment["challenge_filename"] != "arc-agi_test_challenges.json":
        _fail(
            f"{path}.challenge_filename",
            "must equal 'arc-agi_test_challenges.json'",
        )
    return dict(commitment)


def validate_source_lock(
    value: object,
    path: str = "$",
    *,
    required_split: str | None = None,
) -> dict[str, Any]:
    """Validate source identity and independently locked challenge commitments.

    Public commitments are fixed by the pinned repository commit/tree and by
    independently reproduced canonical challenge digests and counts.  The
    Kaggle hidden commitment is a separate platform artifact and may be used
    only after a named human freezes its raw and semantic identities.
    """

    lock = _require_mapping(value, path)
    _require_exact_keys(
        lock,
        {
            "schema",
            "recorded_at",
            "competition_slug",
            "parent",
            "git_sources",
            "challenge_commitments",
            "mutable_surfaces",
            "rules",
            "status",
        },
        path,
    )
    if lock["schema"] != SOURCE_LOCK_SCHEMA:
        _fail(f"{path}.schema", f"must equal {SOURCE_LOCK_SCHEMA!r}")
    if lock["competition_slug"] != COMPETITION_SLUG:
        _fail(f"{path}.competition_slug", "must bind the ARC-AGI-2 competition")
    _require_utc(lock["recorded_at"], f"{path}.recorded_at")
    if lock["status"] != "PREPARED_NOT_RUN":
        _fail(f"{path}.status", "must equal 'PREPARED_NOT_RUN'")

    parent = _require_mapping(lock["parent"], f"{path}.parent")
    _require_exact_keys(parent, {"repository", "branch", "commit", "tree"}, f"{path}.parent")
    expected_parent = {
        "repository": "Grativy6/hearthline-plays",
        "branch": "arc-agi/main",
        "commit": "228d80f0559277c55031f4a80f6179320e10364c",
        "tree": "532e178ecd41410e5e9038c647141f2cbe32f01d",
    }
    if dict(parent) != expected_parent:
        _fail(f"{path}.parent", "does not match the exact ARC series anchor")

    sources = lock["git_sources"]
    if not isinstance(sources, list) or len(sources) != 5:
        _fail(f"{path}.git_sources", "must contain exactly five Git sources")
    repositories: list[str] = []
    public_source: Mapping[str, Any] | None = None
    git_keys = {
        "repository",
        "branch",
        "commit",
        "tree",
        "license_spdx",
        "role",
        "relationship",
        "claim_ceiling",
    }
    for index, source_value in enumerate(sources):
        source_path = f"{path}.git_sources[{index}]"
        source = _require_mapping(source_value, source_path)
        _require_exact_keys(source, git_keys, source_path)
        repository = _require_string(source["repository"], f"{source_path}.repository")
        repositories.append(repository)
        _require_string(source["branch"], f"{source_path}.branch")
        _require_git_object(source["commit"], f"{source_path}.commit")
        _require_git_object(source["tree"], f"{source_path}.tree")
        if source["license_spdx"] not in {"Apache-2.0", "MIT"}:
            _fail(f"{source_path}.license_spdx", "is not an allowed locked license")
        for field in ("role", "relationship", "claim_ceiling"):
            _require_string(source[field], f"{source_path}.{field}")
        if repository == ARC2_PUBLIC_REPOSITORY:
            public_source = source
    if len(repositories) != len(set(repositories)):
        _fail(f"{path}.git_sources", "repository identities must be unique")
    if public_source is None:
        _fail(f"{path}.git_sources", "missing the pinned public ARC-AGI-2 source")
    expected_public_source = {
        "repository": ARC2_PUBLIC_REPOSITORY,
        "branch": "main",
        "commit": ARC2_PUBLIC_COMMIT,
        "tree": ARC2_PUBLIC_TREE,
        "license_spdx": "Apache-2.0",
        "role": "public_dataset",
        "relationship": "PINNED_EXTERNAL_MOUNT_NOT_VENDORED",
    }
    for field, expected in expected_public_source.items():
        if public_source[field] != expected:
            _fail(
                f"{path}.git_sources",
                f"public ARC-AGI-2 source {field} does not match its exact pin",
            )

    commitments = _require_mapping(
        lock["challenge_commitments"], f"{path}.challenge_commitments"
    )
    _require_exact_keys(
        commitments,
        {"TRAINING", "PUBLIC_EVALUATION", "KAGGLE_HIDDEN"},
        f"{path}.challenge_commitments",
    )
    for split, expected in PUBLIC_CHALLENGE_COMMITMENTS.items():
        commitment_path = f"{path}.challenge_commitments.{split}"
        commitment = _require_mapping(commitments[split], commitment_path)
        _require_exact_keys(commitment, set(expected), commitment_path)
        if dict(commitment) != expected:
            _fail(
                commitment_path,
                "does not match the independently reproduced public commitment",
            )
    require_kaggle_frozen = required_split == "KAGGLE_HIDDEN"
    hidden_commitment = _validate_kaggle_challenge_commitment(
        commitments["KAGGLE_HIDDEN"],
        f"{path}.challenge_commitments.KAGGLE_HIDDEN",
        require_frozen=require_kaggle_frozen,
    )
    if require_kaggle_frozen:
        retrieved = datetime.fromisoformat(
            hidden_commitment["retrieval_utc"][:-1] + "+00:00"
        )
        revalidate_before = datetime.fromisoformat(
            hidden_commitment["revalidate_before"][:-1] + "+00:00"
        )
        now = datetime.now(timezone.utc)
        if not retrieved <= now < revalidate_before:
            _fail(
                f"{path}.challenge_commitments.KAGGLE_HIDDEN",
                "human-frozen challenge commitment is stale",
            )
    if required_split is not None and required_split not in INPUT_SPLIT_CONTRACTS:
        _fail(f"{path}.challenge_commitments", "unsupported required split")

    mutable = lock["mutable_surfaces"]
    if not isinstance(mutable, list) or len(mutable) != 7:
        _fail(f"{path}.mutable_surfaces", "must contain exactly seven surfaces")
    mutable_urls: list[str] = []
    mutable_base_keys = {
        "title",
        "url",
        "observed_on",
        "content_sha256",
        "status",
    }
    for index, surface_value in enumerate(mutable):
        surface_path = f"{path}.mutable_surfaces[{index}]"
        surface = _require_mapping(surface_value, surface_path)
        status = surface.get("status")
        if status == UNFROZEN_SOURCE_STATUS:
            _require_exact_keys(surface, mutable_base_keys, surface_path)
            if surface.get("content_sha256") is not None:
                _fail(f"{surface_path}.content_sha256", "must be null while unfrozen")
        elif status == FROZEN_SOURCE_STATUS:
            _require_exact_keys(
                surface,
                mutable_base_keys
                | {"retrieval_utc", "human_reviewer", "revalidate_before"},
                surface_path,
            )
            _require_sha256(surface["content_sha256"], f"{surface_path}.content_sha256")
            _require_utc(surface["retrieval_utc"], f"{surface_path}.retrieval_utc")
            _require_utc(
                surface["revalidate_before"], f"{surface_path}.revalidate_before"
            )
            _require_string(surface["human_reviewer"], f"{surface_path}.human_reviewer")
        else:
            _fail(f"{surface_path}.status", "has an unsupported review status")
        _require_string(surface["title"], f"{surface_path}.title")
        url = _require_string(surface["url"], f"{surface_path}.url")
        if not url.startswith("https://"):
            _fail(f"{surface_path}.url", "must use HTTPS")
        mutable_urls.append(url)
        observed_on = _require_string(
            surface["observed_on"], f"{surface_path}.observed_on", maximum=10
        )
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", observed_on) is None:
            _fail(f"{surface_path}.observed_on", "must be an ISO-8601 date")
        try:
            datetime.fromisoformat(observed_on)
        except ValueError as exc:
            raise ValidationError(f"{surface_path}.observed_on: invalid date") from exc
    if len(mutable_urls) != len(set(mutable_urls)):
        _fail(f"{path}.mutable_surfaces", "URLs must be unique")
    rules = _require_mapping(lock["rules"], f"{path}.rules")
    expected_rules = {
        "official_data_vendored": False,
        "public_eval_is_development_data": False,
        "hidden_holdout_persisted": False,
        "internet_during_evaluation": False,
        "predictions_per_test_input": 2,
        "publication_is_run_authorization": False,
    }
    _require_exact_keys(rules, set(expected_rules), f"{path}.rules")
    if dict(rules) != expected_rules:
        _fail(f"{path}.rules", "safety assertions do not match the closed contract")
    return dict(lock)


def challenge_semantic_sha256(value: object) -> str:
    """Hash the validated label-free challenge's canonical semantic form."""

    canonical = challenge_to_jsonable(value)
    try:
        payload = (
            json.dumps(
                canonical,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"challenge is not canonical JSON: {exc}") from exc
    return hashlib.sha256(payload).hexdigest()


def validate_input_manifest_challenge_snapshot(
    manifest_value: object,
    challenge_value: object,
    *,
    challenge_filename: str,
    challenge_raw_sha256: str,
    challenge_byte_count: int,
    path: str = "$",
) -> ChallengeSet:
    """Bind one already-read challenge snapshot to a closed input manifest.

    Callers pass the digest, byte count, and decoded JSON derived from the
    same byte snapshot. This avoids validating one filesystem state and later
    consuming another.
    """

    manifest = validate_input_manifest(manifest_value, path)
    if challenge_filename != manifest["challenge_filename"]:
        _fail(f"{path}.challenge_filename", "does not match the selected file")
    if challenge_raw_sha256 != manifest["challenge_raw_sha256"]:
        _fail(
            f"{path}.challenge_raw_sha256",
            "does not match the challenge bytes",
        )
    if challenge_byte_count != manifest["challenge_byte_count"]:
        _fail(f"{path}.challenge_byte_count", "does not match the challenge bytes")
    challenges = validate_challenge_set(challenge_value, "$.challenge")
    if manifest["task_count"] != len(challenges):
        _fail(f"{path}.task_count", "does not match the challenge set")
    test_input_count = sum(len(task.test_inputs) for task in challenges.values())
    if manifest["test_input_count"] != test_input_count:
        _fail(f"{path}.test_input_count", "does not match the challenge set")
    semantic_sha256 = challenge_semantic_sha256(challenges)
    if manifest["challenge_semantic_sha256"] != semantic_sha256:
        _fail(
            f"{path}.challenge_semantic_sha256",
            "does not match canonical label-free challenge semantics",
        )
    return challenges


def validate_input_manifest(
    value: object,
    path: str = "$",
    *,
    challenge_path: str | Path | None = None,
    source_lock_path: str | Path | None = None,
    source_lock_value: object | None = None,
    source_lock_sha256: str | None = None,
    expected_split: str | None = None,
) -> dict[str, Any]:
    """Validate an external challenge descriptor and its immutable bindings.

    Public manifests bind both the exact ARC-AGI-2 Git identity and the
    independently reproduced semantic commitment in the source lock. Kaggle
    manifests deliberately contain no public-Git identity; they bind the raw
    and semantic digests and counts of a separately human-frozen platform
    artifact. Supplying ``challenge_path`` proves those claims against bytes.
    """

    manifest = _require_mapping(value, path)
    split = manifest.get("split")
    if not isinstance(split, str) or split not in INPUT_SPLIT_CONTRACTS:
        _fail(f"{path}.split", "must name a supported challenge split")

    common_keys = {
        "schema",
        "competition_slug",
        "split",
        "challenge_origin",
        "challenge_filename",
        "challenge_raw_sha256",
        "challenge_semantic_sha256",
        "challenge_byte_count",
        "task_count",
        "test_input_count",
        "source_lock_sha256",
        "labels_included",
        "official_data_vendored",
    }
    public_identity_keys = {
        "arc2_public_repository",
        "arc2_public_commit",
        "arc2_public_tree",
    }
    expected_keys = (
        common_keys | public_identity_keys
        if split in PUBLIC_CHALLENGE_COMMITMENTS
        else common_keys
    )
    _require_exact_keys(manifest, expected_keys, path)
    if manifest["schema"] != INPUT_MANIFEST_SCHEMA:
        _fail(f"{path}.schema", f"must equal {INPUT_MANIFEST_SCHEMA!r}")
    if manifest["competition_slug"] != COMPETITION_SLUG:
        _fail(f"{path}.competition_slug", "must bind the ARC-AGI-2 competition")

    expected_origin, expected_filename = INPUT_SPLIT_CONTRACTS[split]
    if expected_split is not None and split != expected_split:
        _fail(f"{path}.split", f"must equal {expected_split!r}")
    if manifest["challenge_origin"] != expected_origin:
        _fail(f"{path}.challenge_origin", f"must equal {expected_origin!r}")
    if manifest["challenge_filename"] != expected_filename:
        _fail(f"{path}.challenge_filename", f"must equal {expected_filename!r}")

    _require_sha256(
        manifest["challenge_raw_sha256"], f"{path}.challenge_raw_sha256"
    )
    _require_sha256(
        manifest["challenge_semantic_sha256"],
        f"{path}.challenge_semantic_sha256",
    )
    _require_positive_integer(
        manifest["challenge_byte_count"], f"{path}.challenge_byte_count"
    )
    _require_positive_integer(manifest["task_count"], f"{path}.task_count")
    _require_positive_integer(
        manifest["test_input_count"], f"{path}.test_input_count"
    )
    _require_sha256(manifest["source_lock_sha256"], f"{path}.source_lock_sha256")
    if split in PUBLIC_CHALLENGE_COMMITMENTS:
        exact_pin = {
            "arc2_public_repository": ARC2_PUBLIC_REPOSITORY,
            "arc2_public_commit": ARC2_PUBLIC_COMMIT,
            "arc2_public_tree": ARC2_PUBLIC_TREE,
        }
        for field, expected in exact_pin.items():
            if manifest[field] != expected:
                _fail(f"{path}.{field}", f"must equal {expected!r}")
    if manifest["labels_included"] is not False:
        _fail(f"{path}.labels_included", "must be the JSON boolean false")
    if manifest["official_data_vendored"] is not False:
        _fail(f"{path}.official_data_vendored", "must be the JSON boolean false")

    if source_lock_path is not None and (
        source_lock_value is not None or source_lock_sha256 is not None
    ):
        _fail(path, "source lock path and snapshot arguments are mutually exclusive")
    if (source_lock_value is None) != (source_lock_sha256 is None):
        _fail(path, "source lock snapshot requires both value and SHA-256")
    if source_lock_path is not None:
        lock_path = Path(source_lock_path)
        try:
            lock_payload = lock_path.read_bytes()
        except OSError as exc:
            raise ValidationError(f"cannot read {lock_path}: {exc}") from exc
        try:
            source_lock_value = parse_json(lock_payload.decode("utf-8"))
        except UnicodeError as exc:
            raise ValidationError(f"{lock_path}: JSON must be UTF-8") from exc
        source_lock_sha256 = hashlib.sha256(lock_payload).hexdigest()
    if source_lock_value is not None and source_lock_sha256 is not None:
        _require_sha256(source_lock_sha256, f"{path}.source_lock_sha256")
        if manifest["source_lock_sha256"] != source_lock_sha256:
            _fail(f"{path}.source_lock_sha256", "does not match the source lock bytes")
        source_lock = validate_source_lock(
            source_lock_value,
            "$.source_lock",
            required_split=split,
        )
        commitment = source_lock["challenge_commitments"][split]
        if split in PUBLIC_CHALLENGE_COMMITMENTS:
            for field in (
                "challenge_semantic_sha256",
                "task_count",
                "test_input_count",
            ):
                if manifest[field] != commitment[field]:
                    _fail(
                        f"{path}.{field}",
                        f"does not match the pinned {split} commitment",
                    )
        else:
            hidden_bindings = {
                "challenge_raw_sha256": "challenge_raw_sha256",
                "challenge_semantic_sha256": "challenge_semantic_sha256",
                "task_count": "task_count",
                "test_input_count": "test_input_count",
            }
            for manifest_field, commitment_field in hidden_bindings.items():
                if manifest[manifest_field] != commitment[commitment_field]:
                    _fail(
                        f"{path}.{manifest_field}",
                        "does not match the independently frozen Kaggle artifact",
                    )

    if challenge_path is not None:
        challenge_file = Path(challenge_path)
        if challenge_file.name != expected_filename:
            _fail(f"{path}.challenge_filename", "does not match the selected file")
        try:
            challenge_payload = challenge_file.read_bytes()
        except OSError as exc:
            raise ValidationError(f"cannot read {challenge_file}: {exc}") from exc
        if (
            manifest["challenge_raw_sha256"]
            != hashlib.sha256(challenge_payload).hexdigest()
        ):
            _fail(
                f"{path}.challenge_raw_sha256",
                "does not match the challenge bytes",
            )
        if manifest["challenge_byte_count"] != len(challenge_payload):
            _fail(f"{path}.challenge_byte_count", "does not match the challenge bytes")
        try:
            challenge_value = parse_json(challenge_payload.decode("utf-8"))
        except UnicodeError as exc:
            raise ValidationError(f"{challenge_file}: JSON must be UTF-8") from exc
        validate_input_manifest_challenge_snapshot(
            manifest,
            challenge_value,
            challenge_filename=challenge_file.name,
            challenge_raw_sha256=hashlib.sha256(challenge_payload).hexdigest(),
            challenge_byte_count=len(challenge_payload),
            path=path,
        )

    return dict(manifest)


def _validate_challenge_task(task_id: str, value: object, path: str) -> TaskView:
    item = _require_mapping(value, path)
    _require_exact_keys(item, {"train", "test"}, path)
    train_values = _require_nonempty_array(item["train"], f"{path}.train")
    test_values = _require_nonempty_array(item["test"], f"{path}.test")
    train = tuple(
        _validate_demonstration(example, f"{path}.train[{index}]")
        for index, example in enumerate(train_values)
    )
    test_inputs = tuple(
        _validate_unlabeled_test(example, f"{path}.test[{index}]")
        for index, example in enumerate(test_values)
    )
    return TaskView(task_id=task_id, train=train, test_inputs=test_inputs)


def validate_challenge_set(value: object, path: str = "$") -> ChallengeSet:
    """Validate a label-free challenge mapping and construct immutable views."""

    tasks = _require_mapping(value, path)
    if not tasks:
        _fail(path, "challenge set must contain at least one task")
    for task_id in tasks:
        validate_task_id(task_id, f"{path}.{task_id!s}")
    validated: ChallengeSet = {}
    for task_id in sorted(tasks):
        validated_id = validate_task_id(task_id, f"{path}.{task_id!s}")
        validated[validated_id] = _validate_challenge_task(
            validated_id, tasks[task_id], f"{path}.{validated_id}"
        )
    return validated


def validate_task_view(value: object, path: str = "$") -> TaskView:
    """Revalidate a programmatically constructed task view."""

    if not isinstance(value, TaskView):
        _fail(path, "must be a TaskView")
    task_id = validate_task_id(value.task_id, f"{path}.task_id")
    if not value.train:
        _fail(f"{path}.train", "must not be empty")
    if not value.test_inputs:
        _fail(f"{path}.test_inputs", "must not be empty")
    train = tuple(
        Demonstration(
            input=validate_grid(example.input, f"{path}.train[{index}].input"),
            output=validate_grid(example.output, f"{path}.train[{index}].output"),
        )
        for index, example in enumerate(value.train)
    )
    tests = tuple(
        validate_grid(grid, f"{path}.test_inputs[{index}]")
        for index, grid in enumerate(value.test_inputs)
    )
    return TaskView(task_id=task_id, train=train, test_inputs=tests)


def _coerce_challenges(value: object, path: str = "$.challenges") -> ChallengeSet:
    if isinstance(value, Mapping) and value and all(
        isinstance(task, TaskView) for task in value.values()
    ):
        result: ChallengeSet = {}
        for key in value:
            validate_task_id(key, f"{path}.{key!s}")
        for key in sorted(value):
            task = validate_task_view(value[key], f"{path}.{key}")
            if key != task.task_id:
                _fail(f"{path}.{key}", "mapping key must equal TaskView.task_id")
            result[key] = task
        return result
    return validate_challenge_set(value, path)


def coerce_challenge_set(value: object, path: str = "$.challenges") -> ChallengeSet:
    """Accept raw challenge JSON or an existing mapping of immutable views."""

    return _coerce_challenges(value, path)


def validate_submission(
    challenges: object,
    submission: object,
    path: str = "$",
) -> Submission:
    """Validate exactly two attempts and exact task/test-input coverage."""

    expected = _coerce_challenges(challenges)
    artifact = _require_mapping(submission, path)
    for task_id in artifact:
        validate_task_id(task_id, f"{path}.{task_id!s}")
    actual_ids = set(artifact)
    expected_ids = set(expected)
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids, key=repr)
        extra = sorted(actual_ids - expected_ids, key=repr)
        _fail(path, f"task coverage mismatch; missing={missing!r}, extra={extra!r}")

    result: Submission = {}
    for task_id in sorted(expected):
        task_path = f"{path}.{task_id}"
        records = artifact[task_id]
        if not _is_sequence(records):
            _fail(task_path, "must be an array")
        record_list = list(records)
        required_count = len(expected[task_id].test_inputs)
        if len(record_list) != required_count:
            _fail(
                task_path,
                f"must contain exactly {required_count} test-output records",
            )
        pairs: list[AttemptPair] = []
        for index, record in enumerate(record_list):
            record_path = f"{task_path}[{index}]"
            attempt_object = _require_mapping(record, record_path)
            _require_exact_keys(
                attempt_object, {"attempt_1", "attempt_2"}, record_path
            )
            pairs.append(
                AttemptPair(
                    attempt_1=validate_grid(
                        attempt_object["attempt_1"], f"{record_path}.attempt_1"
                    ),
                    attempt_2=validate_grid(
                        attempt_object["attempt_2"], f"{record_path}.attempt_2"
                    ),
                )
            )
        result[task_id] = tuple(pairs)
    return result


def validate_solution_set(
    challenges: object,
    solutions: object,
    path: str = "$",
) -> SolutionSet:
    """Validate scorer-only labels with exact challenge coverage and counts."""

    expected = _coerce_challenges(challenges)
    artifact = _require_mapping(solutions, path)
    for task_id in artifact:
        validate_task_id(task_id, f"{path}.{task_id!s}")
    actual_ids = set(artifact)
    expected_ids = set(expected)
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids, key=repr)
        extra = sorted(actual_ids - expected_ids, key=repr)
        _fail(path, f"task coverage mismatch; missing={missing!r}, extra={extra!r}")

    result: SolutionSet = {}
    for task_id in sorted(expected):
        task_path = f"{path}.{task_id}"
        outputs = artifact[task_id]
        if not _is_sequence(outputs):
            _fail(task_path, "must be an array")
        output_list = list(outputs)
        required_count = len(expected[task_id].test_inputs)
        if len(output_list) != required_count:
            _fail(task_path, f"must contain exactly {required_count} solution grids")
        result[task_id] = tuple(
            validate_grid(grid, f"{task_path}[{index}]")
            for index, grid in enumerate(output_list)
        )
    return result


def split_labeled_task(
    task_id: object,
    value: object,
    path: str = "$",
) -> tuple[TaskView, tuple[Grid, ...]]:
    """Split GitHub-style labeled task JSON before constructing a TaskView."""

    validated_id = validate_task_id(task_id, f"{path}.task_id")
    item = _require_mapping(value, path)
    _require_exact_keys(item, {"train", "test"}, path)
    train_values = _require_nonempty_array(item["train"], f"{path}.train")
    test_values = _require_nonempty_array(item["test"], f"{path}.test")
    train = tuple(
        _validate_demonstration(example, f"{path}.train[{index}]")
        for index, example in enumerate(train_values)
    )

    inputs: list[Grid] = []
    labels: list[Grid] = []
    for index, example in enumerate(test_values):
        test_path = f"{path}.test[{index}]"
        test_object = _require_mapping(example, test_path)
        _require_exact_keys(test_object, {"input", "output"}, test_path)
        inputs.append(validate_grid(test_object["input"], f"{test_path}.input"))
        labels.append(validate_grid(test_object["output"], f"{test_path}.output"))
    return (
        TaskView(task_id=validated_id, train=train, test_inputs=tuple(inputs)),
        tuple(labels),
    )


def split_labeled_challenge_set(
    value: object, path: str = "$"
) -> tuple[ChallengeSet, SolutionSet]:
    """Split a mapping of labeled per-task artifacts into disjoint objects."""

    tasks = _require_mapping(value, path)
    if not tasks:
        _fail(path, "labeled challenge set must contain at least one task")
    for task_id in tasks:
        validate_task_id(task_id, f"{path}.{task_id!s}")
    challenges: ChallengeSet = {}
    solutions: SolutionSet = {}
    for task_id in sorted(tasks):
        view, labels = split_labeled_task(
            task_id, tasks[task_id], f"{path}.{task_id}"
        )
        challenges[view.task_id] = view
        solutions[view.task_id] = labels
    return challenges, solutions


# British-spelling aliases make the split boundary discoverable without
# changing the canonical American-spelling API used in manifests and docs.
split_labelled_task = split_labeled_task
split_labelled_challenge_set = split_labeled_challenge_set


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def parse_json(text: str) -> Any:
    """Parse strict JSON, rejecting duplicate keys and non-finite numbers."""

    def reject_constant(value: str) -> NoReturn:
        raise ValidationError(f"non-finite JSON number is forbidden: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def load_json(path: str | Path) -> Any:
    """Read one UTF-8 JSON file using the strict parser."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"cannot read UTF-8 JSON file {source}: {exc}") from exc
    return parse_json(text)


def grid_to_jsonable(grid: Grid) -> list[list[int]]:
    return [list(row) for row in grid]


def challenge_to_jsonable(challenges: object) -> dict[str, Any]:
    validated = _coerce_challenges(challenges)
    return {
        task_id: {
            "train": [
                {
                    "input": grid_to_jsonable(example.input),
                    "output": grid_to_jsonable(example.output),
                }
                for example in task.train
            ],
            "test": [
                {"input": grid_to_jsonable(grid)} for grid in task.test_inputs
            ],
        }
        for task_id, task in validated.items()
    }


def submission_to_jsonable(
    challenges: object, submission: object
) -> dict[str, list[dict[str, list[list[int]]]]]:
    validated = validate_submission(challenges, submission)
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


def solutions_to_jsonable(
    challenges: object, solutions: object
) -> dict[str, list[list[list[int]]]]:
    validated = validate_solution_set(challenges, solutions)
    return {
        task_id: [grid_to_jsonable(grid) for grid in grids]
        for task_id, grids in validated.items()
    }


# Concise plural alias retained for callers that model a file as a collection.
validate_solutions = validate_solution_set
