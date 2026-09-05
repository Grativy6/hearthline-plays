#!/usr/bin/env python3
"""Verify the Rosetta public-learning playground without using the network.

This verifier checks only repository-local policy, original micro fixtures,
session scaffolding, and the evidence-bounded learning-ledger API. It does not
open a public task, download data, call a model, run an evaluator, or execute
candidate code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hearthline_learning import (  # noqa: E402
    LearningLedger,
    LearningScope,
    Provenance,
    ResolutionOutcome,
)
from tools.validate_public_learning_session import (  # noqa: E402
    SessionError,
    load_session,
    validate_session,
)

CATALOG_PATH = Path("playground/public-resources.v1.json")
ROUTES_PATH = Path("playground/routes.example.toml")
DECK_PATH = Path("playground/micro/orientation-deck.v1.json")
SESSION_TEMPLATE_PATH = Path("templates/public-learning-session.v1.json")
PUBLIC_STATUS = "PUBLIC_PLAYGROUND_NOT_FORMAL_EVALUATION"
FORMAL_STATUS = "PREPARED_NOT_RUN"
PILOT_STATUS = "PILOT_UNSELECTED_UNCONSUMED"
CALIBRATION_STATUS = "BLOCKED_EXTERNAL_HOSTED_PARQUET_ENGINE_MISSING"
ROSETTABENCH_COMMIT = "099b4837252becbd2c650ca54b206ac1a6bc3470"
DATASET_COMMIT = "87567193229336fae36f0da95c4af6a2a46bf90f"
MICRO_DECK_SHA256 = "b88a0bc011378e69449315384e675edc263427457b39c8606d9c994f67a0920c"
PUBLIC_OBSERVED_AT = "2026-09-04T23:15:42Z"
EXPECTED_SURFACE_IDS = {
    "kaggle_benchmark",
    "kaggle_leaderboard_api",
    "kaggle_core_v1",
    "kaggle_python_control_v1",
    "kaggle_writeup",
    "github_repository",
    "github_core_notebook",
    "github_python_notebook",
    "github_dataset_builder_notebook",
    "kaggle_dataset_v1",
    "hugging_face_dataset_pin",
}
EXPECTED_SURFACE_URLS = {
    "kaggle_benchmark": "https://www.kaggle.com/benchmarks/namanbnsl/rosetta",
    "kaggle_leaderboard_api": "https://www.kaggle.com/api/v1/benchmarks/namanbnsl/rosetta/leaderboard",
    "kaggle_core_v1": "https://www.kaggle.com/benchmarks/tasks/namanbnsl/rosettabench-core",
    "kaggle_python_control_v1": "https://www.kaggle.com/benchmarks/tasks/namanbnsl/rosettabench-python-baseline-control",
    "kaggle_writeup": "https://www.kaggle.com/competitions/kaggle-measuring-agi/writeups/rosettabench",
    "github_repository": (
        "https://github.com/namanbnsl/RosettaBench/tree/"
        "099b4837252becbd2c650ca54b206ac1a6bc3470"
    ),
    "github_core_notebook": (
        "https://github.com/namanbnsl/RosettaBench/blob/"
        "099b4837252becbd2c650ca54b206ac1a6bc3470/rosetta-core.ipynb"
    ),
    "github_python_notebook": (
        "https://github.com/namanbnsl/RosettaBench/blob/"
        "099b4837252becbd2c650ca54b206ac1a6bc3470/rosetta-baselines.ipynb"
    ),
    "github_dataset_builder_notebook": (
        "https://github.com/namanbnsl/RosettaBench/blob/"
        "099b4837252becbd2c650ca54b206ac1a6bc3470/rosetta-dataset-builder.ipynb"
    ),
    "kaggle_dataset_v1": (
        "https://www.kaggle.com/datasets/namanbnsl/"
        "rosettabench-150-stratified-compressed"
    ),
    "hugging_face_dataset_pin": (
        "https://huggingface.co/datasets/namanbnsl/"
        "rosettabench-150-stratified-compressed/tree/"
        "87567193229336fae36f0da95c4af6a2a46bf90f"
    ),
}
EXPECTED_SURFACE_FIELDS = {
    "kaggle_benchmark": {"id", "kind", "url", "visibility", "use"},
    "kaggle_leaderboard_api": {"id", "kind", "url", "visibility", "use"},
    "kaggle_core_v1": {
        "id",
        "kind",
        "url",
        "version",
        "visibility",
        "default_route_enabled",
        "reason_disabled",
    },
    "kaggle_python_control_v1": {
        "id",
        "kind",
        "url",
        "version",
        "visibility",
        "default_route_enabled",
        "reason_disabled",
    },
    "kaggle_writeup": {"id", "kind", "url", "visibility", "materialization"},
    "github_repository": {
        "id",
        "kind",
        "url",
        "visibility",
        "materialization",
        "license_status",
    },
    "github_core_notebook": {"id", "kind", "url", "visibility", "materialization"},
    "github_python_notebook": {"id", "kind", "url", "visibility", "materialization"},
    "github_dataset_builder_notebook": {
        "id",
        "kind",
        "url",
        "visibility",
        "materialization",
    },
    "kaggle_dataset_v1": {
        "id",
        "kind",
        "url",
        "version",
        "visibility",
        "materialization",
        "declared_license",
    },
    "hugging_face_dataset_pin": {
        "id",
        "kind",
        "url",
        "visibility",
        "materialization",
        "license_status",
    },
}
EXPECTED_SURFACE_KINDS = {
    "kaggle_benchmark": "benchmark_collection_and_leaderboard",
    "kaggle_leaderboard_api": "public_metadata_api",
    "kaggle_core_v1": "public_runnable_task_reference",
    "kaggle_python_control_v1": "public_runnable_task_reference",
    "kaggle_writeup": "public_description",
    "github_repository": "public_source_reference",
    "github_core_notebook": "public_notebook_reference",
    "github_python_notebook": "public_notebook_reference",
    "github_dataset_builder_notebook": "public_notebook_reference",
    "kaggle_dataset_v1": "public_bulk_dataset_reference",
    "hugging_face_dataset_pin": "public_bulk_dataset_mirror_reference",
}
EXPECTED_EPISODES = {
    "LANTERN-LEDGER-01",
    "LANTERN-REFORMULATE-01",
    "LANTERN-RESET-01",
}


class PlaygroundVerificationError(ValueError):
    """Raised when public-playground state exceeds its declared boundary."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlaygroundVerificationError(message)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PlaygroundVerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> object:
    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlaygroundVerificationError(f"cannot parse {path}: {exc}") from exc


def _object(value: object, label: str) -> dict[str, object]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _exact_object(value: object, keys: set[str], label: str) -> dict[str, object]:
    result = _object(value, label)
    _require(set(result) == keys, f"{label} fields mismatch")
    return result


def validate_catalog(document: object) -> dict[str, object]:
    root = _exact_object(
        document,
        {
            "schema_version",
            "recorded_at_utc",
            "purpose",
            "classification",
            "boundaries",
            "benchmark_shape",
            "pins",
            "public_surfaces",
            "public_observations",
            "publicness_caveat",
            "local_original_resources",
            "storage_policy",
            "license_boundary",
            "claim_ceiling",
        },
        "public resource catalog",
    )
    _require(root["schema_version"] == "hearthline-public-resources.v1", "catalog schema mismatch")
    _require(root["classification"] == PUBLIC_STATUS, "catalog status mismatch")
    _require(root["recorded_at_utc"] == PUBLIC_OBSERVED_AT, "catalog timestamp mismatch")

    boundaries = _exact_object(
        root["boundaries"],
        {
            "upstream_material_copied",
            "dataset_downloaded",
            "model_invoked",
            "evaluator_invoked",
            "external_write_performed",
            "rosetta_001_status",
            "rosetta_001_pilot_status",
            "rosetta_cal_001_status",
        },
        "catalog boundaries",
    )
    for key in (
        "upstream_material_copied",
        "dataset_downloaded",
        "model_invoked",
        "evaluator_invoked",
        "external_write_performed",
    ):
        _require(boundaries[key] is False, f"catalog boundary {key} must remain false")
    _require(boundaries["rosetta_001_status"] == FORMAL_STATUS, "formal status drift")
    _require(boundaries["rosetta_001_pilot_status"] == PILOT_STATUS, "pilot status drift")
    _require(boundaries["rosetta_cal_001_status"] == CALIBRATION_STATUS, "calibration status drift")

    shape = _exact_object(
        root["benchmark_shape"],
        {
            "public_task_forms",
            "documented_public_hidden_split",
            "problem_count",
            "difficulty_counts",
            "note",
        },
        "benchmark shape",
    )
    _require(shape.get("public_task_forms") == 2, "public task-form count mismatch")
    _require(shape.get("documented_public_hidden_split") is False, "catalog invents a hidden split")
    _require(shape.get("problem_count") == 150, "public problem count mismatch")
    _require(
        shape.get("difficulty_counts") == {"easy": 40, "medium": 50, "hard": 60},
        "public difficulty counts mismatch",
    )

    pins = _exact_object(
        root["pins"],
        {
            "rosettabench_commit",
            "hugging_face_dataset_commit",
            "kaggle_dataset_version",
            "kaggle_core_task_version",
            "kaggle_python_task_version",
        },
        "catalog pins",
    )
    _require(pins.get("rosettabench_commit") == ROSETTABENCH_COMMIT, "RosettaBench pin mismatch")
    _require(pins.get("hugging_face_dataset_commit") == DATASET_COMMIT, "dataset pin mismatch")
    _require(pins.get("kaggle_core_task_version") == 1, "Core task version mismatch")
    _require(pins.get("kaggle_python_task_version") == 1, "Python task version mismatch")
    _require(pins.get("kaggle_dataset_version") == 1, "Kaggle dataset version mismatch")

    surfaces = root["public_surfaces"]
    _require(isinstance(surfaces, list), "public surfaces must be an array")
    indexed: dict[str, dict[str, object]] = {}
    for item in surfaces:
        surface = _object(item, "public surface")
        surface_id = surface.get("id")
        _require(isinstance(surface_id, str) and surface_id not in indexed, "surface IDs must be unique strings")
        _require(surface_id in EXPECTED_SURFACE_FIELDS, f"unknown public surface: {surface_id}")
        surface = _exact_object(
            surface,
            EXPECTED_SURFACE_FIELDS[surface_id],
            f"public surface {surface_id}",
        )
        _require(surface.get("kind") == EXPECTED_SURFACE_KINDS[surface_id], f"{surface_id}: kind mismatch")
        _require(surface.get("visibility") == "PUBLIC", f"{surface_id}: visibility mismatch")
        url = surface.get("url")
        _require(url == EXPECTED_SURFACE_URLS.get(surface_id), f"{surface_id}: pinned URL mismatch")
        indexed[surface_id] = surface
    _require(set(indexed) == EXPECTED_SURFACE_IDS, "public surface inventory mismatch")
    for surface_id in ("kaggle_core_v1", "kaggle_python_control_v1"):
        _require(indexed[surface_id].get("default_route_enabled") is False, f"{surface_id} must stay disabled")
        _require(indexed[surface_id].get("version") == 1, f"{surface_id} version mismatch")
    _require(indexed["kaggle_dataset_v1"].get("version") == 1, "Kaggle dataset surface version mismatch")
    for surface_id in ("kaggle_dataset_v1", "hugging_face_dataset_pin"):
        _require(indexed[surface_id].get("materialization") == "DISABLED", f"{surface_id} materialization enabled")
    for surface_id in (
        "kaggle_writeup",
        "github_repository",
        "github_core_notebook",
        "github_python_notebook",
        "github_dataset_builder_notebook",
    ):
        _require(indexed[surface_id].get("materialization") == "LINK_ONLY", f"{surface_id} is not link-only")

    observations = root["public_observations"]
    _require(isinstance(observations, list) and len(observations) == 1, "public observation count mismatch")
    observation = _exact_object(
        observations[0],
        {
            "observation_id",
            "classification",
            "source_surface_id",
            "observed_at_utc",
            "model_display_name",
            "task_versions",
            "scores",
            "not_our_run",
            "not_rosetta_cal_001_evidence",
            "drift_warning",
        },
        "public observation",
    )
    _require(
        observation.get("observation_id") == f"KAGGLE_PUBLIC_TERRA_{PUBLIC_OBSERVED_AT}",
        "observation ID mismatch",
    )
    _require(observation.get("classification") == "PUBLIC_OBSERVATION", "observation classification mismatch")
    _require(observation.get("not_our_run") is True, "public row is presented as our run")
    _require(observation.get("not_rosetta_cal_001_evidence") is True, "public row substitutes for calibration")
    _require(observation.get("source_surface_id") == "kaggle_leaderboard_api", "observation source mismatch")
    _require(observation.get("observed_at_utc") == root["recorded_at_utc"], "observation timestamp mismatch")
    _require(observation.get("model_display_name") == "GPT-5.6 Terra", "observation model mismatch")
    _require(observation.get("task_versions") == {"core": 1, "python_control": 1}, "observation task versions mismatch")
    scores = _object(observation.get("scores"), "public observation scores")
    _require(
        scores
        == {
            "core": 0.49333333333333335,
            "python_control": 0.8933333333333333,
            "python_minus_core": 0.4,
            "units": "proportion",
        },
        "public observation scores mismatch",
    )

    originals = root["local_original_resources"]
    _require(isinstance(originals, list) and len(originals) == 1, "original resource inventory mismatch")
    original = _exact_object(
        originals[0],
        {
            "id",
            "path",
            "origin",
            "sha256",
            "upstream_task_rows_used",
            "default_model_calls",
            "optional_model_call_ceiling",
        },
        "original resource",
    )
    _require(original.get("id") == "orientation_deck_v1", "original deck ID mismatch")
    _require(original.get("path") == DECK_PATH.as_posix(), "original deck path mismatch")
    _require(original.get("origin") == "ORIGINAL_HEARTHLINE_PRACTICE_MATERIAL", "deck origin mismatch")
    _require(original.get("sha256") == MICRO_DECK_SHA256, "original deck digest pin mismatch")
    _require(original.get("upstream_task_rows_used") == 0, "original deck contains upstream rows")
    _require(original.get("default_model_calls") == 0, "original deck default invokes a model")
    _require(original.get("optional_model_call_ceiling") == 1, "micro call ceiling mismatch")

    storage = _exact_object(
        root["storage_policy"],
        {
            "bulk_data_enabled",
            "bulk_data_root",
            "allowed_destination_classes_after_separate_authorization",
            "forbidden_roots",
            "path_configuration_is_authority",
        },
        "storage policy",
    )
    _require(storage.get("bulk_data_enabled") is False, "bulk data route enabled")
    _require(storage.get("bulk_data_root") is None, "bulk data root must remain unset")
    _require(storage.get("forbidden_roots") == ["E:\\"], "E: must remain forbidden for bulk data")
    _require(storage.get("path_configuration_is_authority") is False, "path configuration grants authority")
    _require(
        storage.get("allowed_destination_classes_after_separate_authorization")
        == ["FIXED_INTERNAL_DRIVE", "EXPLICIT_EXTERNAL_STORAGE"],
        "allowed storage classes mismatch",
    )
    publicness = _exact_object(
        root["publicness_caveat"],
        {
            "mapping_generator_public",
            "fixed_seed_procedure_public",
            "distributed_dataset_has_private_test_cases_field",
            "sealed_rosetta_holdout_documented",
            "interpretation",
        },
        "publicness caveat",
    )
    _require(publicness["mapping_generator_public"] is True, "mapping-generator publicness drift")
    _require(publicness["fixed_seed_procedure_public"] is True, "fixed-seed publicness drift")
    _require(
        publicness["distributed_dataset_has_private_test_cases_field"] is True,
        "public dataset field inventory drift",
    )
    _require(publicness["sealed_rosetta_holdout_documented"] is False, "catalog invents a holdout")
    license_boundary = _exact_object(
        root["license_boundary"],
        {"status", "policy", "excluded_from_repository"},
        "license boundary",
    )
    _require(license_boundary.get("status") == "UNRESOLVED_CROSS_SURFACE", "license ambiguity was erased")
    _require(license_boundary.get("policy") == "LINK_AND_PIN_ONLY", "license boundary is not link-only")
    _require(
        license_boundary.get("excluded_from_repository")
        == [
            "upstream code",
            "upstream notebooks",
            "task rows",
            "test cases",
            "generated mappings",
            "model outputs",
        ],
        "license exclusion inventory mismatch",
    )
    _require(
        root["claim_ceiling"]
        == (
            "Practice may evidence rule-ledger, uncertainty, reformulation, reset, and reflection "
            "behavior; it does not earn a Rosetta, Gloss, durable-learning, contamination, "
            "ARC-AGI-3, or formal-experiment claim."
        ),
        "catalog claim ceiling mismatch",
    )
    return {"surface_count": len(indexed), "observation_count": len(observations)}


def validate_routes(document: object) -> dict[str, object]:
    root = _exact_object(
        document,
        {
            "schema_version",
            "default_route",
            "formal_experiment_enabled",
            "calibration_retry_enabled",
            "publication_enabled",
            "session",
            "tooling",
            "storage",
            "routes",
            "separation",
        },
        "route policy",
    )
    _require(root.get("schema_version") == "hearthline-public-routes.v1", "route schema mismatch")
    _require(root.get("default_route") == "micro_original", "micro route is not the default")
    for key in ("formal_experiment_enabled", "calibration_retry_enabled", "publication_enabled"):
        _require(root.get(key) is False, f"{key} must remain false")

    session = _exact_object(
        root.get("session"),
        {
            "default_model_calls",
            "optional_model_call_ceiling",
            "attempts_per_episode",
            "fresh_context_per_episode",
            "cross_episode_memory",
            "score_is_primary_goal",
            "reflection_required",
        },
        "route session defaults",
    )
    _require(session.get("default_model_calls") == 0, "default model calls must be zero")
    _require(session.get("optional_model_call_ceiling") == 1, "optional call ceiling mismatch")
    _require(session.get("attempts_per_episode") == 1, "episode retry policy mismatch")
    _require(session.get("fresh_context_per_episode") is True, "fresh context must be required")
    _require(session.get("cross_episode_memory") is False, "cross-episode memory must be disabled")
    _require(session.get("score_is_primary_goal") is False, "score must remain a byproduct")
    _require(session.get("reflection_required") is True, "reflection must remain required")

    tooling = _object(root.get("tooling"), "route tooling")
    _require(
        tooling
        == {
            "learning_library": "hearthline_learning",
            "micro_viewer": "tools/show_public_micro_episode.py",
            "session_generator": "tools/new_public_learning_session.py",
            "session_validator": "tools/validate_public_learning_session.py",
            "playground_verifier": "tools/verify_public_playground.py",
            "all_offline": True,
        },
        "public-playground tool routes mismatch",
    )

    storage = _exact_object(
        root.get("storage"),
        {
            "bulk_data_enabled",
            "bulk_data_root",
            "storage_class",
            "allowed_storage_classes",
            "forbidden_roots",
            "configuration_grants_download_authority",
        },
        "route storage",
    )
    _require(storage.get("bulk_data_enabled") is False, "bulk data enabled in routes")
    _require(storage.get("bulk_data_root") == "", "bulk data destination must remain unset")
    _require(storage.get("forbidden_roots") == ["E:\\"], "route policy must forbid E:")
    _require(storage.get("storage_class") == "", "storage class must remain unset")
    _require(
        storage.get("allowed_storage_classes")
        == ["FIXED_INTERNAL_DRIVE", "EXPLICIT_EXTERNAL_STORAGE"],
        "route storage classes mismatch",
    )
    _require(
        storage.get("configuration_grants_download_authority") is False,
        "route configuration grants download authority",
    )

    routes = _object(root.get("routes"), "routes")
    _require(
        set(routes)
        == {
            "micro_original",
            "public_source_read",
            "public_leaderboard_observe",
            "public_core_reference",
            "public_python_reference",
            "bulk_dataset",
        },
        "route inventory mismatch",
    )
    micro = _exact_object(
        routes["micro_original"],
        {
            "enabled",
            "kind",
            "fixture",
            "fixture_sha256",
            "materialization",
            "external_calls",
            "default_model_calls",
            "optional_model_call_ceiling",
            "learner_context_field",
            "coach_context_field",
            "objectives",
        },
        "micro route",
    )
    _require(micro.get("enabled") is True, "micro route disabled")
    _require(micro.get("kind") == "LOCAL_ORIGINAL_PRACTICE", "micro route kind mismatch")
    _require(micro.get("fixture") == DECK_PATH.as_posix(), "micro fixture path mismatch")
    _require(micro.get("fixture_sha256") == MICRO_DECK_SHA256, "micro fixture digest mismatch")
    _require(micro.get("external_calls") == 0, "micro route has external calls")
    _require(micro.get("default_model_calls") == 0, "micro route invokes a model by default")
    _require(micro.get("optional_model_call_ceiling") == 1, "micro route call ceiling mismatch")
    _require(micro.get("materialization") == "NONE", "micro route materializes content")
    _require(micro.get("learner_context_field") == "learner_view", "learner field mismatch")
    _require(micro.get("coach_context_field") == "coach_view", "coach field mismatch")
    _require(
        micro.get("objectives")
        == [
            "rule_acquisition",
            "evidence_vs_assumption",
            "supported_reformulation",
            "task_local_reset",
            "reflection",
        ],
        "micro objective inventory mismatch",
    )
    source_read = _exact_object(
        routes["public_source_read"],
        {
            "enabled",
            "kind",
            "catalog",
            "allowed_surface_ids",
            "authentication",
            "downloads",
            "model_calls",
            "evaluator_calls",
        },
        "source-read route",
    )
    _require(source_read.get("enabled") is True, "source-read route disabled")
    _require(source_read.get("kind") == "LINK_ONLY_STUDY", "source-read route kind mismatch")
    _require(source_read.get("catalog") == CATALOG_PATH.as_posix(), "source-read catalog mismatch")
    _require(
        source_read.get("allowed_surface_ids")
        == [
            "kaggle_writeup",
            "github_repository",
            "github_core_notebook",
            "github_python_notebook",
            "github_dataset_builder_notebook",
        ],
        "source-read surface inventory mismatch",
    )
    _require(source_read.get("downloads") is False, "source-read route permits downloads")
    _require(source_read.get("authentication") is False, "source-read route permits authentication")
    _require(source_read.get("model_calls") == 0, "source-read route invokes a model")
    _require(source_read.get("evaluator_calls") == 0, "source-read route invokes an evaluator")
    observe = _exact_object(
        routes["public_leaderboard_observe"],
        {
            "enabled",
            "kind",
            "surface_id",
            "authentication",
            "external_writes",
            "model_calls",
            "evaluator_calls",
            "refresh_required_for_current_claim",
        },
        "leaderboard route",
    )
    _require(observe.get("enabled") is True, "leaderboard route disabled")
    _require(observe.get("kind") == "PUBLIC_OBSERVATION", "leaderboard route kind mismatch")
    _require(observe.get("surface_id") == "kaggle_leaderboard_api", "leaderboard surface mismatch")
    _require(observe.get("authentication") is False, "leaderboard route permits authentication")
    _require(observe.get("external_writes") is False, "leaderboard route permits writes")
    _require(observe.get("model_calls") == 0, "leaderboard route invokes a model")
    _require(observe.get("evaluator_calls") == 0, "leaderboard route invokes an evaluator")
    _require(observe.get("refresh_required_for_current_claim") is True, "leaderboard drift gate missing")
    reference_fields = {"enabled", "kind", "surface_id", "task_version", "reason", "requires_separate_authorization"}
    core = _exact_object(routes["public_core_reference"], reference_fields, "Core reference route")
    python = _exact_object(
        routes["public_python_reference"],
        reference_fields,
        "Python reference route",
    )
    bulk = _exact_object(
        routes["bulk_dataset"],
        {
            "enabled",
            "kind",
            "surface_ids",
            "destination",
            "forbidden_roots",
            "requires_separate_authorization",
            "copy_into_repository",
        },
        "bulk route",
    )
    for route_name, route in (
        ("public_core_reference", core),
        ("public_python_reference", python),
        ("bulk_dataset", bulk),
    ):
        _require(route.get("enabled") is False, f"{route_name} must remain disabled")
        _require(
            route.get("requires_separate_authorization") is True,
            f"{route_name} lacks an authority gate",
        )
    _require(core.get("kind") == "PUBLIC_RUNNABLE_TASK_REFERENCE", "Core route kind mismatch")
    _require(python.get("kind") == "PUBLIC_RUNNABLE_TASK_REFERENCE", "Python route kind mismatch")
    _require(bulk.get("kind") == "PUBLIC_BULK_DATA_REFERENCE", "bulk route kind mismatch")
    _require(core.get("surface_id") == "kaggle_core_v1", "Core route surface mismatch")
    _require(core.get("task_version") == 1, "Core route task version mismatch")
    _require(python.get("surface_id") == "kaggle_python_control_v1", "Python route surface mismatch")
    _require(python.get("task_version") == 1, "Python route task version mismatch")
    _require(
        bulk.get("surface_ids") == ["kaggle_dataset_v1", "hugging_face_dataset_pin"],
        "bulk route surface inventory mismatch",
    )
    _require(bulk.get("destination") == "", "bulk route destination must remain unset")
    _require(bulk.get("forbidden_roots") == ["E:\\"], "bulk route must forbid E:")
    _require(bulk.get("copy_into_repository") is False, "bulk route permits repository copying")

    separation = _exact_object(
        root.get("separation"),
        {"rosetta_001", "rosetta_cal_001"},
        "route separation",
    )
    formal = _exact_object(
        separation.get("rosetta_001"),
        {"status", "pilot", "playground_consumes_pilot"},
        "formal separation",
    )
    _require(formal.get("status") == FORMAL_STATUS, "formal route status drift")
    _require(formal.get("pilot") == PILOT_STATUS, "formal pilot route drift")
    _require(formal.get("playground_consumes_pilot") is False, "playground consumes formal pilot")
    calibration = _exact_object(
        separation.get("rosetta_cal_001"),
        {"status", "repair_or_retry_authorized", "public_observation_substitutes_for_result"},
        "calibration separation",
    )
    _require(calibration.get("status") == CALIBRATION_STATUS, "calibration route status drift")
    _require(calibration.get("repair_or_retry_authorized") is False, "calibration retry enabled")
    _require(
        calibration.get("public_observation_substitutes_for_result") is False,
        "public result substitutes for calibration",
    )
    return {"default_route": "micro_original", "route_count": len(routes)}


def validate_deck(document: object) -> dict[str, object]:
    root = _exact_object(
        document,
        {
            "schema_version",
            "deck_id",
            "title",
            "origin",
            "classification",
            "upstream_material",
            "use",
            "episodes",
            "reflection_template",
            "claim_ceiling",
        },
        "orientation deck",
    )
    _require(root["schema_version"] == "hearthline-public-micro.v1", "deck schema mismatch")
    _require(root["deck_id"] == "PUBLIC-ORIENTATION-001", "deck ID mismatch")
    _require(root["origin"] == "ORIGINAL_HEARTHLINE_PRACTICE_MATERIAL", "deck origin mismatch")
    _require(root["classification"] == "PRACTICE_NOT_BENCHMARK", "deck classification mismatch")
    upstream = _exact_object(
        root["upstream_material"],
        {"task_rows", "test_cases", "maps", "code_fragments"},
        "deck upstream-material counts",
    )
    _require(all(value == 0 and type(value) is int for value in upstream.values()), "deck records upstream material")
    use = _object(root["use"], "deck use")
    _require(use.get("default_model_calls") == 0, "deck invokes a model by default")
    _require(use.get("optional_model_call_ceiling") == 1, "deck optional call ceiling mismatch")
    _require(use.get("attempts_per_episode") == 1, "deck retry policy mismatch")
    _require(use.get("show_learner_view_first") is True, "deck learner-first gate missing")
    _require(use.get("reveal_coach_view_after_answer_is_sealed") is True, "deck answer-key gate missing")
    _require(use.get("reset_between_episodes") is True, "deck reset gate missing")

    episodes = root["episodes"]
    _require(isinstance(episodes, list) and len(episodes) == 3, "deck episode count mismatch")
    episode_ids: set[str] = set()
    for episode in episodes:
        item = _exact_object(
            episode,
            {"episode_id", "lesson", "learner_view", "coach_view"},
            "deck episode",
        )
        episode_id = item["episode_id"]
        _require(isinstance(episode_id, str) and episode_id not in episode_ids, "episode IDs must be unique")
        episode_ids.add(episode_id)
        _require(isinstance(item["lesson"], str) and item["lesson"], f"{episode_id}: lesson missing")
        _require(isinstance(item["learner_view"], dict), f"{episode_id}: learner view missing")
        _require(isinstance(item["coach_view"], dict), f"{episode_id}: coach view missing")
    _require(episode_ids == EXPECTED_EPISODES, "deck episode inventory mismatch")
    serialized = json.dumps(root, sort_keys=True).casefold()
    for forbidden in ("https://", "atcoder", "abc357_b", "private_test_cases"):
        _require(forbidden not in serialized, f"orientation deck contains upstream marker: {forbidden}")
    reflection = _object(root["reflection_template"], "reflection template")
    _require(reflection.get("answer_sealed_before_coach_view") is False, "reflection template claims a sealed answer")
    _require(reflection.get("state_reset_confirmed") is False, "reflection template claims a reset")
    return {"episode_count": len(episodes)}


def validate_learning_ledger() -> dict[str, object]:
    ledger = LearningLedger(LearningScope("public-playground-verifier", "micro-episode-1"))
    provenance = Provenance("micro-demonstration-1", ordinal=1)
    ledger.observe_supported("mark", "sela", provenance)
    supported = ledger.resolve("mark")
    unresolved = ledger.resolve("reverse")
    _require(supported.outcome is ResolutionOutcome.SUPPORTED_RENDER, "ledger lost supported evidence")
    _require(unresolved.outcome is ResolutionOutcome.UNRESOLVED, "ledger invented unsupported evidence")
    closed = ledger.close()
    boundary = closed["implementation_boundary"]
    _require(
        boundary["scope"] == "LEDGER_MODULE_OPERATIONS_ONLY_NOT_CALLER_ACTIVITY",
        "ledger receipt overstates its attestation scope",
    )
    _require(boundary["caller_evidence_origin_verified"] is False, "ledger claims to verify caller evidence")
    module_performs = boundary["module_performs"]
    _require(
        module_performs["cross_scope_learning_state"] is False,
        "ledger carries learning state across scopes",
    )
    _require(
        module_performs["cross_scope_receipt_lineage"] is True,
        "ledger does not disclose its cross-scope receipt linkage",
    )
    for capability in (
        "external_access",
        "generated_code_execution",
        "mapping_invention",
        "model_calls",
        "strategy_selection",
    ):
        _require(module_performs[capability] is False, f"ledger module capability widened: {capability}")
    reset = ledger.reset(LearningScope("public-playground-verifier", "micro-episode-2"))
    _require(reset["prior_observations_cleared"] is True, "ledger reset did not clear observations")
    _require(ledger.resolve("mark").outcome is ResolutionOutcome.UNRESOLVED, "ledger leaked state across episodes")
    return {
        "supported_outcome": supported.outcome.value,
        "unsupported_outcome": unresolved.outcome.value,
        "reset_verified": True,
    }


def verify_public_playground(repo_root: Path = REPO_ROOT) -> dict[str, object]:
    root = repo_root.resolve(strict=True)
    required = (
        CATALOG_PATH,
        ROUTES_PATH,
        DECK_PATH,
        SESSION_TEMPLATE_PATH,
        Path("hearthline_learning/__init__.py"),
        Path("hearthline_learning/ledger.py"),
        Path("tools/new_public_learning_session.py"),
        Path("tools/show_public_micro_episode.py"),
        Path("tools/validate_public_learning_session.py"),
    )
    missing = [path.as_posix() for path in required if not (root / path).is_file()]
    _require(not missing, "missing public-playground files: " + ", ".join(missing))
    catalog = validate_catalog(_load_json(root / CATALOG_PATH))
    try:
        with (root / ROUTES_PATH).open("rb") as handle:
            routes_document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PlaygroundVerificationError(f"cannot parse {ROUTES_PATH}: {exc}") from exc
    routes = validate_routes(routes_document)
    deck_raw = (root / DECK_PATH).read_bytes()
    deck_file_sha256 = hashlib.sha256(deck_raw).hexdigest()
    _require(deck_file_sha256 == MICRO_DECK_SHA256, "orientation deck file digest mismatch")
    deck = validate_deck(_load_json(root / DECK_PATH))
    deck["file_sha256"] = deck_file_sha256
    try:
        session = validate_session(load_session(root / SESSION_TEMPLATE_PATH))
    except SessionError as exc:
        raise PlaygroundVerificationError(f"invalid public session template: {exc}") from exc
    ledger = validate_learning_ledger()
    return {
        "verdict": "PASS_PUBLIC_PLAYGROUND_READY",
        "status": PUBLIC_STATUS,
        "required_files_checked": len(required),
        "catalog": catalog,
        "routes": routes,
        "deck": deck,
        "session_template": session,
        "learning_ledger": ledger,
        "verification_side_effects": {
            "network_calls": 0,
            "data_downloads": 0,
            "model_calls": 0,
            "evaluator_runs": 0,
            "candidate_code_executions": 0,
        },
        "claims_earned": {
            "benchmark_result": False,
            "learning_tax": False,
            "formal_pilot_consumed": False,
            "arc_agi_3_transfer": False,
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = verify_public_playground(args.repo_root)
    except (OSError, PlaygroundVerificationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
