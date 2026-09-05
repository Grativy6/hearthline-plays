#!/usr/bin/env python3
"""Fail-closed, offline verification for the ROSETTA-001 preparation station."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath

try:
    from tools.verify_public_playground import (
        PlaygroundVerificationError,
        verify_public_playground,
    )
except ModuleNotFoundError:  # Direct execution from the tools directory.
    from verify_public_playground import (  # type: ignore[no-redef]
        PlaygroundVerificationError,
        verify_public_playground,
    )

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "ROSETTA-001"
BRANCH = "kaggle/titles/rosetta"
ANCHOR = "c6077763fedb768e599031982a840ad324eb1051"
SELECTION_SEED = "cf11bdacd7729ac263dd7684b27ce1adc33dbf83f268d02cbe087aceb718d5e6"
SELECTION_METHOD = "sha256-rank-with-frozen-exclusions-v2"
EXCLUSION_MANIFEST_SHA256 = "da455a01dd2c8efc40734e7ded03efe5a8e1ebb45a2fed4cec3777b52e68d389"
DEVELOPMENT_EXCLUDED_IDS = ["abc357_b"]
ROSETTABENCH_COMMIT = "099b4837252becbd2c650ca54b206ac1a6bc3470"
KAGGLE_BENCHMARKS_COMMIT = "ab291417d9a4c731ccfbfb03ac0b8316cb843683"
DATASET_COMMIT = "87567193229336fae36f0da95c4af6a2a46bf90f"
CONDITIONS = (
    ("C01_BARE_SOL_PYTHON", "bare", "python"),
    ("C02_BARE_SOL_CORE", "bare", "core"),
    ("C03_HEARTHLINE_SOL_PYTHON", "hearthline", "python"),
    ("C04_HEARTHLINE_SOL_CORE", "hearthline", "core"),
    ("C05_HEARTHLINE_SOL_TASK_GLOSS_PYTHON", "hearthline_gloss", "python"),
    ("C06_HEARTHLINE_SOL_TASK_GLOSS_CORE", "hearthline_gloss", "core"),
)
OUTCOME_CODES = [
    "PASS",
    "NO_CODE",
    "PYTHON_LEAK",
    "SYNTAX_ERROR",
    "RUNTIME_ERROR",
    "WRONG_ANSWER",
]
COUNTERS = {
    "source_repository_clones",
    "sdk_installs",
    "dataset_files_downloaded",
    "dataset_bytes_downloaded",
    "benchmark_task_identifiers_selected",
    "benchmark_task_prompts_opened",
    "evaluator_test_cases_opened",
    "benchmark_model_calls",
    "evaluator_runs",
    "kaggle_task_pushes",
    "kaggle_hosted_runs",
    "publications",
}
REQUIRED_FILES = {
    ".gitattributes",
    ".github/workflows/verify-rosetta-station.yml",
    ".gitignore",
    "AGENTS.md",
    "LICENSE",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "calibration/rosetta_cal_001_task.py",
    "configs/rosetta-001.example.toml",
    "configs/rosetta-cal-001.toml",
    "docs/GETTING_STARTED.md",
    "docs/GLOSS_CONTRACT.md",
    "docs/KAGGLE_BENCHMARKS_SDK.md",
    "docs/PUBLIC_PLAYGROUND.md",
    "docs/ROSETTA_CAL_001.md",
    "docs/ROSETTA_001_PROTOCOL.md",
    "exclusions/development-tasks.v1.json",
    "metadata/public-observation.v1.json",
    "hearthline_learning/__init__.py",
    "hearthline_learning/ledger.py",
    "playground/micro/orientation-deck.v1.json",
    "playground/public-resources.v1.json",
    "playground/routes.example.toml",
    "pyproject.toml",
    "source-lock.v1.json",
    "status/station-status.v1.json",
    "status/rosetta-cal-001-status.v1.json",
    "templates/pilot-selection.v1.json",
    "templates/public-learning-session.v1.json",
    "templates/result-bundle.v1.json",
    "tools/bootstrap_environment.ps1",
    "tools/fetch_pinned_code.py",
    "tools/new_public_learning_session.py",
    "tools/select_pilot.py",
    "tools/show_public_micro_episode.py",
    "tools/validate_result_bundle.py",
    "tools/validate_public_learning_session.py",
    "tools/verify_calibration.py",
    "tools/verify_public_playground.py",
    "tools/verify_station.py",
    "tests/test_fetch_pinned_code.py",
    "tests/test_learning_ledger.py",
    "tests/test_public_learning_session.py",
    "tests/test_select_pilot.py",
    "tests/test_show_public_micro_episode.py",
    "tests/test_validate_result_bundle.py",
    "tests/test_rosetta_cal_001_task.py",
    "tests/test_verify_calibration.py",
    "tests/test_verify_public_playground.py",
    "tests/test_verify_station.py",
}
PROHIBITED_DIRECTORIES = {
    ".cache",
    ".kaggle",
    "benchmark-data",
    "checkpoints",
    "data",
    "datasets",
    "hidden-tests",
    "results",
    "responses",
    "runs",
    "task-material",
}
PROHIBITED_SUFFIXES = {
    ".arrow",
    ".ckpt",
    ".feather",
    ".gguf",
    ".ipynb",
    ".key",
    ".log",
    ".onnx",
    ".p12",
    ".parquet",
    ".pem",
    ".pfx",
    ".pickle",
    ".pkl",
    ".pt",
    ".pth",
    ".safetensors",
}
PROHIBITED_ENDINGS = (".run.json", ".task.json")
PROHIBITED_NAMES = {
    ".git-credentials",
    ".netrc",
    "_netrc",
    "access_token",
    "credentials.json",
    "kaggle.json",
}
MAX_FILE_BYTES = 5 * 1024 * 1024


class VerificationError(ValueError):
    """Raised when the station is not a preparation-only scaffold."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _load_json(path: Path) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise VerificationError(f"{path}: duplicate JSON key {key}")
            result[key] = value
        return result

    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot parse {path}: {exc}") from exc


def _require_object(value: object, label: str) -> dict[str, object]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _require_exact_keys(
    value: object, expected: set[str], label: str
) -> dict[str, object]:
    result = _require_object(value, label)
    _require(set(result) == expected, f"{label} fields mismatch")
    return result


def validate_development_exclusions(path: Path) -> None:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise VerificationError(f"cannot read development exclusions: {exc}") from exc
    _require(
        hashlib.sha256(raw).hexdigest() == EXCLUSION_MANIFEST_SHA256,
        "development exclusion manifest digest mismatch",
    )
    document = _require_exact_keys(
        _load_json(path),
        {"schema_version", "experiment_id", "status", "source_dataset_commit", "excluded"},
        "development exclusion manifest",
    )
    _require(document.get("schema_version") == "1.0", "development exclusion schema mismatch")
    _require(document.get("experiment_id") == EXPERIMENT_ID, "development exclusion experiment mismatch")
    _require(
        document.get("status") == "FROZEN_DEVELOPMENT_EXCLUSIONS",
        "development exclusions are not frozen",
    )
    _require(
        document.get("source_dataset_commit") == DATASET_COMMIT,
        "development exclusion dataset mismatch",
    )
    rows = document.get("excluded")
    _require(isinstance(rows, list) and len(rows) == 1, "development exclusion count mismatch")
    row = _require_exact_keys(
        rows[0], {"question_id", "reason", "public_source"}, "development exclusion row"
    )
    _require(row.get("question_id") == "abc357_b", "development exclusion ID mismatch")
    _require(
        row.get("reason") == "ROSETTA-CAL-001_PUBLICLY_DISCLOSED_DEVELOPMENT_TASK",
        "development exclusion reason mismatch",
    )


def validate_source_lock(document: object) -> None:
    root = _require_exact_keys(
        document,
        {
            "schema_version",
            "generated_at_utc",
            "experiment_id",
            "station_status",
            "lineage",
            "materialization",
            "sources",
            "kaggle_benchmark",
            "kaggle_writeup",
            "license_resolution",
            "selection",
            "claims_not_earned",
        },
        "source lock",
    )
    _require(
        set(root)
        == {
            "schema_version",
            "generated_at_utc",
            "experiment_id",
            "station_status",
            "lineage",
            "materialization",
            "sources",
            "kaggle_benchmark",
            "kaggle_writeup",
            "license_resolution",
            "selection",
            "claims_not_earned",
        },
        "source-lock top-level fields mismatch",
    )
    _require(root.get("schema_version") == "source-lock.v1", "source-lock schema mismatch")
    _require(root.get("experiment_id") == EXPERIMENT_ID, "source-lock experiment mismatch")
    _require(root.get("station_status") == "PREPARED_NOT_RUN", "source lock is not inert")
    lineage = _require_exact_keys(
        root.get("lineage"),
        {"repository", "series_anchor_commit", "branch"},
        "source-lock lineage",
    )
    _require(lineage.get("repository") == "hearthline-plays", "source-lock repository mismatch")
    _require(lineage.get("series_anchor_commit") == ANCHOR, "source-lock anchor mismatch")
    _require(lineage.get("branch") == BRANCH, "source-lock branch mismatch")
    materialization = _require_object(root.get("materialization"), "materialization")
    expected_materialization = {
        "source_repositories_cloned": False,
        "benchmark_data_downloaded": False,
        "benchmark_task_content_downloaded": False,
        "model_or_evaluator_invoked": False,
    }
    _require(materialization == expected_materialization, "source lock records materialization")

    sources = _require_object(root.get("sources"), "sources")
    _require(
        set(sources)
        == {
            "rosettabench",
            "kaggle_benchmarks",
            "rosetta_dataset_hf",
            "rosetta_dataset_kaggle",
            "kaggle_cli_docs",
        },
        "source lock has an unexpected source inventory",
    )
    rosetta = _require_exact_keys(
        sources["rosettabench"],
        {
            "repository",
            "ref",
            "commit",
            "commit_time_utc",
            "fetch_class",
            "files_observed_as_metadata",
            "license",
            "fetched",
        },
        "sources.rosettabench",
    )
    _require(
        rosetta.get("repository") == "https://github.com/namanbnsl/RosettaBench.git",
        "RosettaBench repository mismatch",
    )
    _require(rosetta.get("commit") == ROSETTABENCH_COMMIT, "RosettaBench commit mismatch")
    _require(rosetta.get("fetch_class") == "public_code", "RosettaBench fetch class mismatch")
    _require(rosetta.get("fetched") is False, "RosettaBench must remain unfetched")
    rosetta_license = _require_object(rosetta.get("license"), "RosettaBench license")
    _require(
        rosetta_license.get("status") == "UNRESOLVED_NO_LICENSE_FILE",
        "RosettaBench reuse license must remain unresolved",
    )
    sdk = _require_exact_keys(
        sources["kaggle_benchmarks"],
        {
            "repository",
            "ref",
            "commit",
            "commit_time_utc",
            "fetch_class",
            "source_version",
            "requires_python",
            "license",
            "fetched",
        },
        "sources.kaggle_benchmarks",
    )
    _require(sdk.get("repository") == "https://github.com/Kaggle/kaggle-benchmarks.git", "SDK repository mismatch")
    _require(sdk.get("commit") == KAGGLE_BENCHMARKS_COMMIT, "SDK commit mismatch")
    _require(sdk.get("ref") == "refs/heads/ci", "SDK branch must be ci")
    _require(sdk.get("fetch_class") == "public_code", "SDK fetch class mismatch")
    _require(sdk.get("license") == "Apache-2.0", "SDK license mismatch")
    _require(sdk.get("fetched") is False, "SDK must remain unfetched")

    hf = _require_exact_keys(
        sources["rosetta_dataset_hf"],
        {
            "repository",
            "ref",
            "commit",
            "last_modified_utc",
            "fetch_class",
            "public",
            "gated",
            "parquet",
            "license",
            "fetched",
        },
        "HF dataset",
    )
    _require(hf.get("commit") == DATASET_COMMIT, "HF dataset commit mismatch")
    _require(hf.get("fetch_class") == "metadata_only_non_fetchable", "HF data must be non-fetchable")
    _require(hf.get("fetched") is False, "HF data must remain unfetched")
    parquet = _require_exact_keys(
        hf.get("parquet"),
        {"path", "bytes", "lfs_sha256", "decoded_dataset_bytes_reported", "examples"},
        "HF parquet metadata",
    )
    _require(parquet.get("bytes") == 737192984, "HF parquet byte count mismatch")
    _require(
        parquet.get("lfs_sha256")
        == "f88cc5fe128b6fca5cb7103479b3ba253ff8989162c2c273ccc2fa2160f2a0ab",
        "HF parquet digest mismatch",
    )
    _require(parquet.get("examples") == 150, "HF example count mismatch")
    hf_license = _require_object(hf.get("license"), "HF license")
    _require(hf_license.get("declared_label") == "cc", "HF license label mismatch")
    _require(
        hf_license.get("status") == "UNRESOLVED_UNSPECIFIED_CC_VARIANT",
        "HF license ambiguity must be preserved",
    )
    kaggle_data = _require_exact_keys(
        sources["rosetta_dataset_kaggle"],
        {
            "repository",
            "dataset_id",
            "version",
            "status",
            "last_updated_utc",
            "fetch_class",
            "metadata_api",
            "metadata_total_bytes",
            "license",
            "fetched",
        },
        "Kaggle dataset",
    )
    _require(kaggle_data.get("dataset_id") == 10026136, "Kaggle dataset ID mismatch")
    _require(kaggle_data.get("version") == 1, "Kaggle dataset version mismatch")
    _require(kaggle_data.get("license") == "MIT", "Kaggle dataset license mismatch")
    _require(kaggle_data.get("fetch_class") == "metadata_only_non_fetchable", "Kaggle data must be non-fetchable")
    _require(kaggle_data.get("fetched") is False, "Kaggle data must remain unfetched")
    cli_docs = _require_exact_keys(
        sources["kaggle_cli_docs"],
        {"repository", "commit", "path", "permalink", "fetch_class", "purpose", "fetched"},
        "Kaggle CLI docs",
    )
    _require(
        cli_docs.get("repository") == "https://github.com/Kaggle/kaggle-cli.git",
        "Kaggle CLI repository mismatch",
    )
    _require(
        cli_docs.get("commit") == "db63063b817cfbc0abe0e001870edda462e569da",
        "Kaggle CLI docs commit mismatch",
    )
    _require(cli_docs.get("path") == "docs/benchmarks.md", "Kaggle CLI docs path mismatch")
    _require(cli_docs.get("fetch_class") == "metadata_only_non_fetchable", "CLI docs must not be fetched")
    _require(cli_docs.get("fetched") is False, "CLI docs must remain unfetched")

    benchmark = _require_exact_keys(
        root.get("kaggle_benchmark"),
        {
            "slug",
            "url",
            "public_leaderboard_api",
            "tasks",
            "task_content_downloaded",
            "run_scheduled",
        },
        "Kaggle benchmark",
    )
    _require(benchmark.get("slug") == "namanbnsl/rosetta", "benchmark slug mismatch")
    _require(benchmark.get("task_content_downloaded") is False, "task content was downloaded")
    _require(benchmark.get("run_scheduled") is False, "benchmark run was scheduled")
    tasks = benchmark.get("tasks")
    _require(isinstance(tasks, list) and len(tasks) == 2, "benchmark task inventory mismatch")
    expected_tasks = (
        ("namanbnsl/rosettabench-core", "UNVERIFIED_FOR_THIS_TASK"),
        (
            "namanbnsl/rosettabench-python-baseline-control",
            "APACHE-2.0_DECLARED_ON_TASK_PAGE",
        ),
    )
    for index, (task, expected) in enumerate(zip(tasks, expected_tasks, strict=True)):
        task_record = _require_exact_keys(
            task,
            {"name", "slug", "version", "url", "license_status"},
            f"benchmark task {index + 1}",
        )
        expected_slug, expected_license = expected
        _require(task_record.get("slug") == expected_slug, "benchmark task slug mismatch")
        _require(task_record.get("version") == 1, "benchmark task version mismatch")
        _require(
            task_record.get("license_status") == expected_license,
            "benchmark task license status mismatch",
        )

    writeup = _require_exact_keys(
        root.get("kaggle_writeup"),
        {"url", "published_date", "license"},
        "Kaggle writeup",
    )
    _require(writeup.get("license") == "CC0_FOR_WRITEUP_ONLY", "writeup license mismatch")
    license_resolution = _require_exact_keys(
        root.get("license_resolution"), {"status", "notes"}, "license resolution"
    )
    _require(
        license_resolution.get("status") == "UNRESOLVED_CROSS_SURFACE",
        "cross-surface license ambiguity must be preserved",
    )
    _require(
        isinstance(license_resolution.get("notes"), list)
        and len(license_resolution["notes"]) == 4,
        "license-resolution notes mismatch",
    )

    selection = _require_exact_keys(
        root.get("selection"),
        {
            "target_pilot_size",
            "target_strata",
            "method",
            "development_exclusion_manifest",
            "status",
            "selected_task_ids",
            "task_set_digest",
        },
        "source-lock selection",
    )
    _require(selection.get("target_pilot_size") == 15, "source lock pilot size mismatch")
    _require(
        selection.get("target_strata") == {"easy": 5, "medium": 5, "hard": 5},
        "source lock pilot strata mismatch",
    )
    _require(selection.get("method") == SELECTION_METHOD, "source lock selection method mismatch")
    exclusion = _require_exact_keys(
        selection.get("development_exclusion_manifest"),
        {"path", "sha256", "excluded_task_ids"},
        "source-lock development exclusion manifest",
    )
    _require(
        exclusion.get("path") == "exclusions/development-tasks.v1.json",
        "source lock exclusion path mismatch",
    )
    _require(
        exclusion.get("sha256") == EXCLUSION_MANIFEST_SHA256,
        "source lock exclusion digest mismatch",
    )
    _require(
        exclusion.get("excluded_task_ids") == DEVELOPMENT_EXCLUDED_IDS,
        "source lock exclusion identifiers mismatch",
    )
    _require(selection.get("status") == "PILOT_UNSELECTED_UNCONSUMED", "source lock selects a pilot")
    _require(selection.get("selected_task_ids") == [], "source lock contains selected IDs")
    _require(selection.get("task_set_digest") is None, "source lock contains a task-set digest")
    claims = _require_exact_keys(
        root.get("claims_not_earned"),
        {
            "sol_available_for_both_tasks",
            "astra_exclusion_attested",
            "systems_frozen",
            "pilot_selected",
            "benchmark_run",
            "public_leaderboard_comparability",
            "scientific_result",
        },
        "claims_not_earned",
    )
    _require(
        set(claims)
        == {
            "sol_available_for_both_tasks",
            "astra_exclusion_attested",
            "systems_frozen",
            "pilot_selected",
            "benchmark_run",
            "public_leaderboard_comparability",
            "scientific_result",
        },
        "claims_not_earned inventory mismatch",
    )
    _require(all(value is False for value in claims.values()), "source lock earns a run claim")


def validate_public_observation(document: object) -> None:
    root = _require_exact_keys(
        document,
        {
            "schema_version",
            "observed_at_utc",
            "experiment_id",
            "collection_boundary",
            "station_state",
            "benchmark_shape",
            "dataset_metadata_discrepancies",
            "licensing_observation",
            "author_static_snapshot",
            "live_kaggle_leaderboard",
            "interpretation_boundaries",
        },
        "public observation",
    )
    _require(
        root.get("schema_version") == "public-observation.v1",
        "public-observation schema mismatch",
    )
    _require(root.get("experiment_id") == EXPERIMENT_ID, "public-observation experiment mismatch")
    collection = _require_exact_keys(
        root.get("collection_boundary"),
        {
            "public_unauthenticated_metadata_only",
            "kaggle_auth_attempted",
            "dataset_downloaded",
            "benchmark_task_content_downloaded",
            "source_repository_cloned",
            "model_invoked",
            "evaluator_invoked",
            "pilot_tasks_selected_or_consumed",
        },
        "public-observation collection boundary",
    )
    _require(
        collection.get("public_unauthenticated_metadata_only") is True,
        "metadata boundary missing",
    )
    _require(
        all(
            value is False
            for key, value in collection.items()
            if key != "public_unauthenticated_metadata_only"
        ),
        "public observation records a prohibited action",
    )
    station = _require_exact_keys(
        root.get("station_state"),
        {
            "preparation",
            "authentication",
            "data",
            "sol_model_availability",
            "pilot",
            "astra_exclusion",
        },
        "public-observation station state",
    )
    _require(
        station
        == {
            "preparation": "PREPARED_NOT_RUN",
            "authentication": "AUTH_NOT_ATTEMPTED",
            "data": "DATA_NOT_DOWNLOADED",
            "sol_model_availability": "SOL_MODEL_AVAILABILITY_UNVERIFIED",
            "pilot": "PILOT_UNSELECTED_UNCONSUMED",
            "astra_exclusion": "REQUIRED_UNATTESTED_NOT_FROZEN",
        },
        "public-observation station state mismatch",
    )
    shape = _require_object(root.get("benchmark_shape"), "public benchmark shape")
    _require(shape.get("benchmark_slug") == "namanbnsl/rosetta", "public benchmark slug mismatch")
    _require(
        shape.get("task_versions")
        == {"rosettabench-core": 1, "rosettabench-python-baseline-control": 1},
        "public task versions mismatch",
    )
    _require(shape.get("problem_count") == 150, "public problem count mismatch")
    _require(
        shape.get("strata") == {"easy": 40, "medium": 50, "hard": 60},
        "public strata mismatch",
    )
    _require(shape.get("few_shot_pairs_per_core_problem") == 6, "demonstration count mismatch")
    _require(
        shape.get("unique_problem_local_languages_reported") == 150,
        "language count mismatch",
    )
    _require(shape.get("llm_judge_reported") is False, "LLM judge metadata mismatch")
    _require(shape.get("outcome_codes_reported") == OUTCOME_CODES, "outcome taxonomy mismatch")

    discrepancies = _require_object(
        root.get("dataset_metadata_discrepancies"), "dataset metadata discrepancies"
    )
    actual_schema = _require_object(
        discrepancies.get("actual_hugging_face_schema"), "actual Hugging Face schema"
    )
    _require(actual_schema.get("lang_seed_present") is False, "schema incorrectly claims lang_seed")
    _require(actual_schema.get("all_tests_type") == "string", "all_tests schema mismatch")

    licensing = _require_object(root.get("licensing_observation"), "licensing observation")
    _require(
        licensing.get("cross_surface_status") == "UNRESOLVED_CROSS_SURFACE",
        "license ambiguity must be preserved",
    )
    _require(
        licensing.get("rosettabench_git_repository") == "UNRESOLVED_NO_LICENSE_FILE",
        "RosettaBench repository license status mismatch",
    )
    author_snapshot = _require_object(root.get("author_static_snapshot"), "author snapshot")
    _require(
        author_snapshot.get("source_commit") == ROSETTABENCH_COMMIT,
        "author snapshot pin mismatch",
    )
    _require(
        author_snapshot.get("independent_recalculation_performed") is False,
        "static author table must not claim independent recalculation",
    )

    leaderboard = _require_object(root.get("live_kaggle_leaderboard"), "live leaderboard")
    rows = leaderboard.get("selected_rows")
    _require(isinstance(rows, list), "live leaderboard selected_rows must be a list")
    sol_rows = [
        row for row in rows if isinstance(row, dict) and row.get("model") == "GPT-5.6 Sol"
    ]
    _require(len(sol_rows) == 1, "live leaderboard must contain one GPT-5.6 Sol observation")
    sol = sol_rows[0]
    _require(sol.get("core_result_case") == "booleanResult", "Sol Core result case mismatch")
    _require(sol.get("core_boolean") is False, "Sol Core boolean observation mismatch")
    _require(sol.get("core_numeric") is None, "Sol Core must remain non-numeric")
    _require(sol.get("python_result_case") == "none", "Sol Python result case mismatch")
    _require(sol.get("python_numeric") is None, "Sol Python result must remain absent")

    interpretation = _require_object(
        root.get("interpretation_boundaries"), "interpretation boundaries"
    )
    _require(
        interpretation.get("contamination_free")
        == "AUTHOR_DESCRIPTION_NOT_VERIFIED_CURRENT_PROPERTY",
        "contamination claim boundary mismatch",
    )
    _require(
        interpretation.get("gloss")
        == (
            "Task-local Gloss is a Hearthline experimental adapter, not a RosettaBench "
            "component and not canonical Bridge Gloss."
        ),
        "Gloss identity boundary mismatch",
    )


def validate_status(document: object) -> None:
    root = _require_exact_keys(
        document,
        {
            "schema_version",
            "station_status",
            "experiment_id",
            "experiment_status",
            "recorded_at_utc",
            "lineage",
            "platform",
            "experiment_bindings",
            "authorization",
            "astra_exclusion",
            "counters",
            "claim_ceiling",
        },
        "station status",
    )
    _require(
        set(root)
        == {
            "schema_version",
            "station_status",
            "experiment_id",
            "experiment_status",
            "recorded_at_utc",
            "lineage",
            "platform",
            "experiment_bindings",
            "authorization",
            "astra_exclusion",
            "counters",
            "claim_ceiling",
        },
        "status top-level fields mismatch",
    )
    _require(root.get("schema_version") == "1.0", "status schema mismatch")
    _require(root.get("station_status") == "PREPARED_NOT_RUN", "station status mismatch")
    _require(root.get("experiment_id") == EXPERIMENT_ID, "status experiment mismatch")
    _require(root.get("experiment_status") == "UNFROZEN_UNSELECTED", "experiment is not inert")
    lineage = _require_exact_keys(
        root.get("lineage"),
        {"title_branch", "parent_series_branch", "parent_anchor_commit"},
        "status lineage",
    )
    _require(lineage.get("title_branch") == BRANCH, "status branch mismatch")
    _require(lineage.get("parent_series_branch") == "kaggle/main", "status parent branch mismatch")
    _require(lineage.get("parent_anchor_commit") == ANCHOR, "status anchor mismatch")
    platform = _require_object(root.get("platform"), "status platform")
    _require(
        platform
        == {
            "authentication": "NOT_ATTEMPTED",
            "benchmark_initialization": "NOT_ATTEMPTED",
            "sol_model_availability": "UNVERIFIED",
            "task_push": "NOT_ATTEMPTED",
            "hosted_execution": "NOT_ATTEMPTED",
            "publication": "NOT_AUTHORIZED",
        },
        "status platform gates are not inert",
    )
    bindings = _require_object(root.get("experiment_bindings"), "experiment bindings")
    _require(
        bindings
        == {
            "sdk_runtime": "UNBOUND",
            "model_snapshot": "UNBOUND",
            "hearthline_artifact": "UNBOUND",
            "gloss_artifact": "UNBOUND",
            "pilot_manifest": "UNBOUND",
            "astra_exclusion_attestation": "UNATTESTED_NOT_FROZEN",
        },
        "experiment bindings must remain unbound",
    )
    astra = _require_exact_keys(
        root.get("astra_exclusion"),
        {"required_for_experiment", "status", "claim_currently_earned"},
        "Astra exclusion",
    )
    _require(astra.get("required_for_experiment") is True, "Astra exclusion must be required")
    _require(astra.get("status") == "UNATTESTED_NOT_FROZEN", "Astra status mismatch")
    _require(astra.get("claim_currently_earned") is False, "Astra exclusion claim is not earned")
    authorization = _require_exact_keys(
        root.get("authorization"), {"allowed", "requires_new_instruction"}, "authorization"
    )
    expected_allowed = [
        "create and verify the lightweight public branch scaffold",
        "record public source and platform metadata",
        "run standard-library-only synthetic and structural tests",
    ]
    expected_closed = [
        "authenticate to Kaggle or initialize Kaggle Benchmarks credentials",
        "install or execute the Kaggle Benchmarks SDK",
        "download or open Rosetta benchmark task material or evaluator tests",
        "select or expose the ROSETTA-001 pilot identifiers",
        "call a model or execute Rosetta code and tests",
        "push a Kaggle task or schedule a hosted benchmark run",
        "publish a task, notebook, benchmark, result, or leaderboard entry",
    ]
    _require(authorization.get("allowed") == expected_allowed, "allowed actions mismatch")
    _require(
        authorization.get("requires_new_instruction") == expected_closed,
        "closed actions mismatch",
    )
    counters = _require_object(root.get("counters"), "status counters")
    _require(set(counters) == COUNTERS, "status counter inventory mismatch")
    _require(
        all(type(value) is int and value == 0 for value in counters.values()),
        "status counters must be integer zero",
    )
    _require(
        root.get("claim_ceiling")
        == (
            "Branch preparation only; no pilot, model, benchmark, learning-tax, Gloss benefit, "
            "or Astra-exclusion result exists."
        ),
        "status claim ceiling mismatch",
    )


def validate_config(document: Mapping[str, object]) -> None:
    _require(
        set(document)
        == {"station", "lineage", "kaggle", "benchmark", "pilot", "execution", "systems", "conditions"},
        "config top-level fields mismatch",
    )
    _require(
        set(document)
        == {"station", "lineage", "kaggle", "benchmark", "pilot", "execution", "systems", "conditions"},
        "config top-level fields mismatch",
    )
    station = _require_object(document.get("station"), "config station")
    _require(
        station == {"experiment_id": EXPERIMENT_ID, "station_status": "PREPARED_NOT_RUN", "run_enabled": False},
        "station config is not inert",
    )
    lineage = _require_exact_keys(
        document.get("lineage"),
        {
            "title_branch",
            "series_anchor_commit",
            "astra_exclusion_required",
            "astra_attestation_status",
        },
        "config lineage",
    )
    _require(lineage.get("title_branch") == BRANCH, "config branch mismatch")
    _require(lineage.get("series_anchor_commit") == ANCHOR, "config anchor mismatch")
    _require(lineage.get("astra_exclusion_required") is True, "config must require Astra exclusion")
    _require(lineage.get("astra_attestation_status") == "UNATTESTED_NOT_FROZEN", "config Astra status mismatch")
    kaggle = _require_exact_keys(
        document.get("kaggle"),
        {
            "authentication_enabled",
            "benchmark_init_enabled",
            "task_push_enabled",
            "hosted_run_enabled",
            "publication_enabled",
            "sol_model_availability",
        },
        "config kaggle",
    )
    for key in (
        "authentication_enabled",
        "benchmark_init_enabled",
        "task_push_enabled",
        "hosted_run_enabled",
        "publication_enabled",
    ):
        _require(kaggle.get(key) is False, f"config must disable kaggle.{key}")
    _require(kaggle.get("sol_model_availability") == "UNVERIFIED", "Sol availability must be unverified")
    benchmark = _require_exact_keys(
        document.get("benchmark"),
        {
            "public_benchmark",
            "public_core_task_version",
            "public_python_task_version",
            "dataset_materialized",
            "task_material_opened",
            "evaluator_executed",
            "public_leaderboard_comparability_claimed",
        },
        "config benchmark",
    )
    _require(benchmark.get("public_benchmark") == "namanbnsl/rosetta", "benchmark slug mismatch")
    _require(benchmark.get("public_core_task_version") == 1, "core task version mismatch")
    _require(benchmark.get("public_python_task_version") == 1, "Python task version mismatch")
    for key in (
        "dataset_materialized",
        "task_material_opened",
        "evaluator_executed",
        "public_leaderboard_comparability_claimed",
    ):
        _require(benchmark.get(key) is False, f"config must disable benchmark.{key}")
    pilot = _require_exact_keys(
        document.get("pilot"),
        {
            "status",
            "selection_method",
            "selection_seed_sha256",
            "development_exclusion_manifest_sha256",
            "easy",
            "medium",
            "hard",
        },
        "config pilot",
    )
    _require(pilot.get("status") == "UNSELECTED_UNCONSUMED", "config pilot must be unselected")
    _require(pilot.get("selection_method") == SELECTION_METHOD, "selection method mismatch")
    _require(pilot.get("selection_seed_sha256") == SELECTION_SEED, "selection seed mismatch")
    _require(
        pilot.get("development_exclusion_manifest_sha256") == EXCLUSION_MANIFEST_SHA256,
        "config exclusion digest mismatch",
    )
    _require(
        {key: pilot.get(key) for key in ("easy", "medium", "hard")}
        == {"easy": 5, "medium": 5, "hard": 5},
        "pilot strata mismatch",
    )
    execution = _require_exact_keys(
        document.get("execution"),
        {
            "model_family",
            "model_slug",
            "model_snapshot",
            "reasoning_setting",
            "sampling_configuration",
            "provider_seed_effective",
            "provider_temperature_effective",
            "n_jobs",
            "max_attempts",
            "on_failure",
            "internet_enabled",
            "retrieval_enabled",
            "model_tools_enabled",
            "llm_judge_enabled",
        },
        "config execution",
    )
    _require(execution.get("model_family") == "GPT-5.6 Sol", "model family mismatch")
    for key in ("model_slug", "model_snapshot", "reasoning_setting", "sampling_configuration"):
        _require(execution.get(key) == "UNBOUND", f"execution.{key} must remain UNBOUND")
    _require(execution.get("provider_seed_effective") == "UNVERIFIED", "provider seed must remain unverified")
    _require(execution.get("provider_temperature_effective") == "UNVERIFIED", "temperature must remain unverified")
    _require(
        execution.get("n_jobs") == 1 and execution.get("max_attempts") == 1,
        "execution concurrency/retry mismatch",
    )
    _require(execution.get("on_failure") == "continue", "on_failure mismatch")
    for key in ("internet_enabled", "retrieval_enabled", "model_tools_enabled", "llm_judge_enabled"):
        _require(execution.get(key) is False, f"config must disable execution.{key}")
    systems = _require_exact_keys(
        document.get("systems"), {"bare", "hearthline", "gloss"}, "config systems"
    )
    bare = _require_object(systems.get("bare"), "systems.bare")
    _require(bare == {"artifact": "UNBOUND", "frozen": False}, "bare system is bound")
    for name in ("hearthline", "gloss"):
        system = _require_object(systems.get(name), f"systems.{name}")
        _require(system.get("artifact_commit") == "UNBOUND", f"{name} commit is bound")
        _require(system.get("artifact_sha256") == "UNBOUND", f"{name} digest is bound")
        _require(system.get("frozen") is False, f"{name} is frozen")
    gloss = _require_object(systems.get("gloss"), "systems.gloss")
    _require(
        set(_require_object(systems.get("hearthline"), "systems.hearthline"))
        == {"artifact_commit", "artifact_sha256", "frozen"},
        "Hearthline system fields mismatch",
    )
    _require(
        set(gloss)
        == {
            "artifact_commit",
            "artifact_sha256",
            "frozen",
            "mapping_scope",
            "hidden_map_access",
            "evaluator_test_access",
        },
        "Gloss system fields mismatch",
    )
    _require(gloss.get("mapping_scope") == "PROBLEM_LOCAL", "Gloss scope mismatch")
    _require(gloss.get("hidden_map_access") is False, "Gloss hidden-map access enabled")
    _require(gloss.get("evaluator_test_access") is False, "Gloss test access enabled")
    conditions = document.get("conditions")
    _require(isinstance(conditions, list), "config conditions must be a list")
    actual = []
    for item in conditions:
        condition = _require_object(item, "config condition")
        _require(set(condition) == {"id", "system", "task_form"}, "config condition fields mismatch")
        actual.append((condition["id"], condition["system"], condition["task_form"]))
    _require(tuple(actual) == CONDITIONS, "config condition order/identity mismatch")


def validate_templates(pilot_document: object, result_document: object) -> None:
    pilot = _require_object(pilot_document, "pilot template")
    _require(
        set(pilot)
        == {
            "schema_version",
            "experiment_id",
            "status",
            "source_dataset_commit",
            "source_index_sha256",
            "development_exclusion_manifest_sha256",
            "development_excluded_question_ids",
            "selection",
            "task_material_opened_during_selection",
            "frozen_at_utc",
        },
        "pilot template fields mismatch",
    )
    _require(pilot.get("schema_version") == "1.0", "pilot template schema mismatch")
    _require(pilot.get("experiment_id") == EXPERIMENT_ID, "pilot template experiment mismatch")
    _require(pilot.get("status") == "TEMPLATE_UNSELECTED", "pilot template is selected")
    _require(pilot.get("source_dataset_commit") == DATASET_COMMIT, "pilot dataset pin mismatch")
    for key in ("source_index_sha256", "frozen_at_utc"):
        _require(pilot.get(key) is None, f"pilot template {key} must be null")
    _require(
        pilot.get("development_exclusion_manifest_sha256") == EXCLUSION_MANIFEST_SHA256,
        "pilot template exclusion digest mismatch",
    )
    _require(
        pilot.get("development_excluded_question_ids") == DEVELOPMENT_EXCLUDED_IDS,
        "pilot template exclusion identifiers mismatch",
    )
    _require(pilot.get("task_material_opened_during_selection") is False, "pilot template records material access")
    selection = _require_object(pilot.get("selection"), "pilot selection")
    _require(
        set(selection)
        == {
            "method",
            "seed_sha256",
            "population_by_difficulty",
            "eligible_by_difficulty",
            "requested_by_difficulty",
            "selected",
        },
        "pilot selection fields mismatch",
    )
    _require(selection.get("method") == SELECTION_METHOD, "pilot template method mismatch")
    _require(selection.get("seed_sha256") == SELECTION_SEED, "pilot template seed mismatch")
    _require(
        selection.get("population_by_difficulty") == {"easy": 40, "medium": 50, "hard": 60},
        "pilot template population mismatch",
    )
    _require(selection.get("eligible_by_difficulty") is None, "pilot template eligible counts must be null")
    _require(
        selection.get("requested_by_difficulty") == {"easy": 5, "medium": 5, "hard": 5},
        "pilot template strata mismatch",
    )
    _require(selection.get("selected") == [], "pilot template contains selected IDs")

    result = _require_object(result_document, "result template")
    _require(
        set(result)
        == {
            "schema_version",
            "experiment_id",
            "status",
            "pilot_manifest_sha256",
            "source_lock_sha256",
            "model",
            "systems",
            "execution",
            "conditions",
            "summary",
            "claim_ceiling",
        },
        "result template fields mismatch",
    )
    _require(result.get("schema_version") == "1.0", "result template schema mismatch")
    _require(result.get("experiment_id") == EXPERIMENT_ID, "result template experiment mismatch")
    _require(result.get("status") == "TEMPLATE_NOT_A_RUN", "result template claims a run")
    _require(result.get("pilot_manifest_sha256") is None, "result template binds a pilot")
    _require(result.get("source_lock_sha256") is None, "result template binds a source lock")
    model = _require_object(result.get("model"), "result model")
    _require(model.get("family") == "GPT-5.6 Sol", "result model family mismatch")
    _require(all(value is None for key, value in model.items() if key != "family"), "result template model is bound")
    systems = _require_object(result.get("systems"), "result systems")
    _require(systems and all(value is None for value in systems.values()), "result template systems are bound")
    execution = _require_object(result.get("execution"), "result execution")
    _require(
        execution
        == {
            "n_jobs": 1,
            "max_attempts": 1,
            "on_failure": "continue",
            "internet_enabled": False,
            "retrieval_enabled": False,
            "model_tools_enabled": False,
            "llm_judge_enabled": False,
        },
        "result execution defaults mismatch",
    )
    conditions = result.get("conditions")
    _require(isinstance(conditions, list), "result conditions must be a list")
    actual = []
    for item in conditions:
        condition = _require_object(item, "result condition")
        _require(set(condition) == {"id", "system", "task_form", "results"}, "result condition fields mismatch")
        _require(condition.get("results") == [], "result template contains results")
        actual.append((condition["id"], condition["system"], condition["task_form"]))
    _require(tuple(actual) == CONDITIONS, "result condition order/identity mismatch")
    summary = _require_object(result.get("summary"), "result summary")
    _require(
        set(summary)
        == {"bare_learning_tax", "hearthline_learning_tax", "hearthline_gloss_learning_tax"},
        "result summary fields mismatch",
    )
    _require(all(value is None for value in summary.values()), "result template contains scores")
    _require(
        result.get("claim_ceiling")
        == "Structural validation only; not a public leaderboard result or scientific conclusion.",
        "result template claim ceiling mismatch",
    )


def collect_candidate_paths(repo_root: Path) -> list[str]:
    command = [
        "git",
        "-c",
        f"safe.directory={repo_root.resolve(strict=True)}",
        "-C",
        str(repo_root),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=False,
        )
    except OSError as exc:
        raise VerificationError(f"cannot execute Git inventory: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise VerificationError(f"Git inventory failed: {detail}")
    try:
        return [part.decode("utf-8") for part in completed.stdout.split(b"\0") if part]
    except UnicodeDecodeError as exc:
        raise VerificationError("Git inventory contains a non-UTF-8 path") from exc


def _path_is_prohibited(relative: str) -> str | None:
    normalized = PurePosixPath(relative.replace("\\", "/"))
    lower_parts = [part.lower() for part in normalized.parts]
    name = normalized.name.lower()
    if any(part in PROHIBITED_DIRECTORIES for part in lower_parts):
        return "prohibited data/output directory"
    if name in PROHIBITED_NAMES:
        return "credential filename"
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return "environment-secret filename"
    if any(name.endswith(ending) for ending in PROHIBITED_ENDINGS):
        return "run artifact"
    if normalized.suffix.lower() in PROHIBITED_SUFFIXES:
        return "prohibited data/model/secret suffix"
    if len(lower_parts) >= 2 and lower_parts[0] == "evidence" and lower_parts[1] == "private":
        return "private evidence directory"
    return None


def _secret_patterns() -> tuple[re.Pattern[bytes], ...]:
    private_key_marker = rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    return (
        re.compile(rb"AKIA[0-9A-Z]{16}"),
        re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
        re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(private_key_marker),
        re.compile(
            rb"(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)"
            rb"\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{16,}"
        ),
        re.compile(rb"https://[^\s/:@]+:[^\s/@]+@"),
    )


def scan_inventory(repo_root: Path, relative_paths: Iterable[str]) -> dict[str, int]:
    root = repo_root.resolve(strict=True)
    paths = list(relative_paths)
    for relative in paths:
        reason = _path_is_prohibited(relative)
        _require(reason is None, f"{relative}: {reason}")
        lexical_candidate = root / relative
        _require(not lexical_candidate.is_symlink(), f"candidate must not be a symlink: {relative}")
        candidate = lexical_candidate.resolve(strict=True)
        _require(root == candidate or root in candidate.parents, f"path escapes repository: {relative}")
        _require(candidate.is_file(), f"candidate is not a regular file: {relative}")
        size = candidate.stat().st_size
        _require(size <= MAX_FILE_BYTES, f"file exceeds {MAX_FILE_BYTES} bytes: {relative}")
        raw = candidate.read_bytes()
        for pattern in _secret_patterns():
            _require(pattern.search(raw) is None, f"secret-like content found in {relative}")
    return {"candidate_files": len(paths), "large_files": 0, "secret_matches": 0, "prohibited_files": 0}


def validate_bootstrap(text: str) -> None:
    required = (
        "[switch]$Create",
        "if (-not $Create)",
        "--offline",
        "--no-python-downloads",
        "--no-project",
        "--no-config",
    )
    for fragment in required:
        _require(fragment in text, f"bootstrap is missing safety control: {fragment}")
    guard_position = text.index("if (-not $Create)")
    venv_position = text.index("uv venv")
    _require(guard_position < venv_position, "bootstrap creates an environment before the Create gate")
    lowered = text.lower()
    for forbidden in (
        "uv python install",
        "pip install",
        "kaggle benchmarks auth",
        "kaggle benchmarks init",
    ):
        _require(forbidden not in lowered, f"bootstrap contains forbidden action: {forbidden}")


def verify_station(repo_root: Path = REPO_ROOT, *, candidate_paths: Iterable[str] | None = None) -> dict[str, object]:
    root = repo_root.resolve(strict=True)
    missing = sorted(relative for relative in REQUIRED_FILES if not (root / relative).is_file())
    _require(not missing, "missing required files: " + ", ".join(missing))
    validate_development_exclusions(root / "exclusions" / "development-tasks.v1.json")
    validate_source_lock(_load_json(root / "source-lock.v1.json"))
    validate_public_observation(_load_json(root / "metadata" / "public-observation.v1.json"))
    validate_status(_load_json(root / "status" / "station-status.v1.json"))
    try:
        with (root / "configs" / "rosetta-001.example.toml").open("rb") as handle:
            config = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise VerificationError(f"cannot parse station config: {exc}") from exc
    validate_config(config)
    validate_templates(
        _load_json(root / "templates" / "pilot-selection.v1.json"),
        _load_json(root / "templates" / "result-bundle.v1.json"),
    )
    try:
        bootstrap_text = (root / "tools" / "bootstrap_environment.ps1").read_text(
            encoding="utf-8-sig"
        )
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read bootstrap script: {exc}") from exc
    validate_bootstrap(bootstrap_text)
    try:
        public_playground = verify_public_playground(root)
    except PlaygroundVerificationError as exc:
        raise VerificationError(f"public playground verification failed: {exc}") from exc
    inventory = scan_inventory(root, candidate_paths if candidate_paths is not None else collect_candidate_paths(root))
    return {
        "verdict": "PASS_PREPARATION_ONLY",
        "experiment_id": EXPERIMENT_ID,
        "station_status": "PREPARED_NOT_RUN",
        "required_files_checked": len(REQUIRED_FILES),
        "public_playground": public_playground,
        "inventory": inventory,
        "verification_side_effects": {
            "data_downloads": 0,
            "network_calls": 0,
            "model_calls": 0,
            "evaluator_runs": 0,
        },
        "claims_earned": {"benchmark_result": False, "learning_tax": False, "astra_exclusion": False},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = verify_station(args.repo_root)
    except (OSError, VerificationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
