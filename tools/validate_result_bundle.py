#!/usr/bin/env python3
"""Validate and summarize a completed ROSETTA-001 result bundle structurally.

This is an offline receipt validator. It can also verify the exact bytes bound
as the pilot manifest and source lock. It never imports, compiles, executes, or
scores submitted code and is not the RosettaBench evaluator.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Mapping, Sequence


EXPERIMENT_ID = "ROSETTA-001"
DATASET_COMMIT = "87567193229336fae36f0da95c4af6a2a46bf90f"
SELECTION_SEED = "cf11bdacd7729ac263dd7684b27ce1adc33dbf83f268d02cbe087aceb718d5e6"
SELECTION_METHOD = "sha256-rank-with-frozen-exclusions-v2"
EXCLUSION_MANIFEST_SHA256 = "da455a01dd2c8efc40734e7ded03efe5a8e1ebb45a2fed4cec3777b52e68d389"
DEVELOPMENT_EXCLUDED_IDS = ["abc357_b"]
RESULT_STATUS = "RESULTS_RECORDED_NOT_PUBLIC"
CLAIM_CEILING = (
    "Structural validation only; not a public leaderboard result or scientific conclusion."
)
DIFFICULTY_ORDER = ("easy", "medium", "hard")
EXPECTED_DIFFICULTIES = [difficulty for difficulty in DIFFICULTY_ORDER for _ in range(5)]
UPSTREAM_OUTCOMES = {
    "PASS",
    "NO_CODE",
    "PYTHON_LEAK",
    "SYNTAX_ERROR",
    "RUNTIME_ERROR",
    "WRONG_ANSWER",
}
DISPOSITIONS = {"COMPLETED", "INFRASTRUCTURE_FAILURE", "TIMEOUT"}
CONDITIONS = (
    ("C01_BARE_SOL_PYTHON", "bare", "python"),
    ("C02_BARE_SOL_CORE", "bare", "core"),
    ("C03_HEARTHLINE_SOL_PYTHON", "hearthline", "python"),
    ("C04_HEARTHLINE_SOL_CORE", "hearthline", "core"),
    ("C05_HEARTHLINE_SOL_TASK_GLOSS_PYTHON", "hearthline_gloss", "python"),
    ("C06_HEARTHLINE_SOL_TASK_GLOSS_CORE", "hearthline_gloss", "core"),
)
ROW_KEYS = {
    "question_id",
    "difficulty",
    "outcome",
    "disposition",
    "input_tokens",
    "output_tokens",
    "latency_ms",
    "gloss_telemetry",
}
GLOSS_KEYS = {
    "availability",
    "mappings_used",
    "unresolved_mappings",
    "unsupported_mappings_invented",
    "reformulations",
}
GLOSS_COUNTERS = GLOSS_KEYS - {"availability"}
ROOT_KEYS = {
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
}
MODEL_KEYS = {
    "family",
    "platform_slug",
    "snapshot",
    "reasoning_setting",
    "sampling_configuration_sha256",
    "provider_seed_effective",
    "provider_temperature_effective",
}
SYSTEM_KEYS = {
    "hearthline_commit",
    "hearthline_sha256",
    "gloss_commit",
    "gloss_sha256",
    "astra_exclusion_attestation_sha256",
}
EXECUTION_KEYS = {
    "n_jobs",
    "max_attempts",
    "on_failure",
    "internet_enabled",
    "retrieval_enabled",
    "model_tools_enabled",
    "llm_judge_enabled",
}
SUMMARY_KEYS = {
    "bare_learning_tax",
    "hearthline_learning_tax",
    "hearthline_gloss_learning_tax",
}
LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class BundleError(ValueError):
    """Raised when a result bundle cannot support the declared comparison."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BundleError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_bundle(path: Path) -> object:
    raw = path.read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise BundleError("result bundle exceeds the 2 MiB safety ceiling")
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"invalid UTF-8 result JSON: {exc}") from exc


def _nonnegative_integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise BundleError(f"{label} must be a nonnegative integer")
    return value


def _nonnegative_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BundleError(f"{label} must be a nonnegative finite number")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise BundleError(f"{label} must be a nonnegative finite number")
    return numeric


def _optional_nonnegative_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_integer(value, label)


def _optional_nonnegative_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    return _nonnegative_number(value, label)


def _exact_object(value: object, keys: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise BundleError(f"{label} must contain exactly {sorted(keys)}")
    return value


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise BundleError(f"{label} must be a nonempty trimmed string")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or LOWER_SHA256.fullmatch(value) is None:
        raise BundleError(f"{label} must be 64 lowercase hexadecimal characters")
    return value


def _recorded_provider_value(value: object, label: str) -> None:
    if isinstance(value, str):
        _nonempty_string(value, label)
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BundleError(f"{label} must record a finite value or an explicit status string")
    if not math.isfinite(float(value)):
        raise BundleError(f"{label} must be finite")


def verify_bound_file(path: Path, expected_sha256: object, label: str) -> dict[str, object]:
    expected = _sha256(expected_sha256, f"{label} expected digest")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BundleError(f"cannot read {label}: {exc}") from exc
    if len(raw) > 2 * 1024 * 1024:
        raise BundleError(f"{label} exceeds the 2 MiB verification ceiling")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise BundleError(f"{label} SHA-256 does not match the result bundle")
    return {"path": str(path), "bytes": len(raw), "sha256": actual}


def _load_bound_json(path: Path, label: str) -> object:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BundleError(f"cannot read {label}: {exc}") from exc
    if len(raw) > 2 * 1024 * 1024:
        raise BundleError(f"{label} exceeds the 2 MiB verification ceiling")
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"invalid UTF-8 {label} JSON: {exc}") from exc


def verify_external_bindings(
    document: dict[str, object], pilot_path: Path, source_lock_path: Path
) -> dict[str, object]:
    pilot_receipt = verify_bound_file(
        pilot_path, document["pilot_manifest_sha256"], "pilot manifest"
    )
    source_receipt = verify_bound_file(
        source_lock_path, document["source_lock_sha256"], "source lock"
    )
    pilot = _exact_object(
        _load_bound_json(pilot_path, "pilot manifest"),
        {
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
        "pilot manifest",
    )
    if pilot.get("schema_version") != "1.0" or pilot.get("experiment_id") != EXPERIMENT_ID:
        raise BundleError("pilot manifest identity mismatch")
    if pilot.get("status") != "SELECTED_IDS_ONLY_NOT_RUN":
        raise BundleError("pilot manifest status mismatch")
    if pilot.get("source_dataset_commit") != DATASET_COMMIT:
        raise BundleError("pilot manifest dataset commit mismatch")
    _sha256(pilot.get("source_index_sha256"), "pilot manifest source_index_sha256")
    if pilot.get("development_exclusion_manifest_sha256") != EXCLUSION_MANIFEST_SHA256:
        raise BundleError("pilot manifest development exclusion digest mismatch")
    if pilot.get("development_excluded_question_ids") != DEVELOPMENT_EXCLUDED_IDS:
        raise BundleError("pilot manifest development exclusion identifiers mismatch")
    if pilot.get("task_material_opened_during_selection") is not False:
        raise BundleError("pilot manifest records task-material access during selection")
    selection = _exact_object(
        pilot.get("selection"),
        {
            "method",
            "seed_sha256",
            "rank_input",
            "population_by_difficulty",
            "eligible_by_difficulty",
            "requested_by_difficulty",
            "selected",
        },
        "pilot manifest selection",
    )
    if selection.get("method") != SELECTION_METHOD:
        raise BundleError("pilot manifest selection method mismatch")
    if selection.get("seed_sha256") != SELECTION_SEED:
        raise BundleError("pilot manifest selection seed mismatch")
    if selection.get("population_by_difficulty") != {"easy": 40, "medium": 50, "hard": 60}:
        raise BundleError("pilot manifest population mismatch")
    eligible = selection.get("eligible_by_difficulty")
    if not isinstance(eligible, dict) or set(eligible) != set(DIFFICULTY_ORDER):
        raise BundleError("pilot manifest eligible population mismatch")
    if any(type(eligible[key]) is not int or eligible[key] < 0 for key in DIFFICULTY_ORDER):
        raise BundleError("pilot manifest eligible counts must be nonnegative integers")
    population = {"easy": 40, "medium": 50, "hard": 60}
    if sum(eligible.values()) != 149 or sum(population[key] - eligible[key] for key in DIFFICULTY_ORDER) != 1:
        raise BundleError("pilot manifest must exclude exactly one development task")
    if any(eligible[key] > population[key] for key in DIFFICULTY_ORDER):
        raise BundleError("pilot manifest eligible counts exceed the source population")
    if selection.get("requested_by_difficulty") != {"easy": 5, "medium": 5, "hard": 5}:
        raise BundleError("pilot manifest requested strata mismatch")
    selected = selection.get("selected")
    if not isinstance(selected, list) or len(selected) != 15:
        raise BundleError("pilot manifest must contain exactly 15 selected identifiers")
    pilot_order: list[tuple[str, str]] = []
    for expected_order, item in enumerate(selected):
        row = _exact_object(
            item,
            {"order", "question_id", "difficulty", "rank_sha256"},
            f"pilot selected row {expected_order + 1}",
        )
        if row.get("order") != expected_order:
            raise BundleError("pilot manifest order field mismatch")
        question_id = _nonempty_string(
            row.get("question_id"), f"pilot selected row {expected_order + 1}.question_id"
        )
        difficulty = row.get("difficulty")
        if difficulty not in DIFFICULTY_ORDER:
            raise BundleError("pilot manifest difficulty mismatch")
        _sha256(row.get("rank_sha256"), f"pilot selected row {expected_order + 1}.rank_sha256")
        pilot_order.append((question_id, difficulty))
    if len({question_id for question_id, _ in pilot_order}) != 15:
        raise BundleError("pilot manifest contains duplicate question identifiers")
    if set(DEVELOPMENT_EXCLUDED_IDS) & {question_id for question_id, _ in pilot_order}:
        raise BundleError("pilot manifest contains a frozen development exclusion")
    if [difficulty for _, difficulty in pilot_order] != EXPECTED_DIFFICULTIES:
        raise BundleError("pilot manifest must order 5 easy, 5 medium, then 5 hard identifiers")

    conditions = document["conditions"]
    if not isinstance(conditions, list) or not conditions:
        raise BundleError("result bundle conditions are unavailable for pilot binding")
    first_condition = conditions[0]
    if not isinstance(first_condition, dict) or not isinstance(first_condition.get("results"), list):
        raise BundleError("result bundle first condition is unavailable for pilot binding")
    result_order = [
        (row.get("question_id"), row.get("difficulty"))
        for row in first_condition["results"]
        if isinstance(row, dict)
    ]
    if result_order != pilot_order:
        raise BundleError("pilot manifest identifiers/order do not match result rows")

    source_lock = _require_source_lock_binding(
        _load_bound_json(source_lock_path, "source lock"), pilot
    )
    return {
        "pilot_manifest": pilot_receipt,
        "source_lock": source_receipt,
        "semantic_checks": {
            "experiment_ids_match": source_lock.get("experiment_id") == EXPERIMENT_ID,
            "source_dataset_commit_matches": True,
            "pilot_identifiers_and_order_match_results": True,
            "development_exclusions_enforced": True,
        },
    }


def _require_source_lock_binding(document: object, pilot: dict[str, object]) -> dict[str, object]:
    source_lock = _exact_object(
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
    if source_lock.get("schema_version") != "source-lock.v1":
        raise BundleError("source-lock schema mismatch")
    if source_lock.get("experiment_id") != EXPERIMENT_ID:
        raise BundleError("source-lock experiment mismatch")
    sources = source_lock.get("sources")
    if not isinstance(sources, dict):
        raise BundleError("source lock has no sources object")
    hf = sources.get("rosetta_dataset_hf")
    if not isinstance(hf, dict) or hf.get("commit") != pilot.get("source_dataset_commit"):
        raise BundleError("source-lock dataset commit does not match the pilot manifest")
    selection = source_lock.get("selection")
    if not isinstance(selection, dict) or selection.get("method") != SELECTION_METHOD:
        raise BundleError("source-lock selection method does not match the pilot manifest")
    exclusion = selection.get("development_exclusion_manifest")
    if not isinstance(exclusion, dict):
        raise BundleError("source lock has no development exclusion binding")
    if exclusion.get("sha256") != pilot.get("development_exclusion_manifest_sha256"):
        raise BundleError("source-lock development exclusion digest mismatch")
    if exclusion.get("excluded_task_ids") != pilot.get("development_excluded_question_ids"):
        raise BundleError("source-lock development exclusion identifiers mismatch")
    return source_lock


def _validate_gloss_telemetry(
    value: object,
    *,
    is_gloss: bool,
    task_form: str,
    label: str,
) -> None:
    if not isinstance(value, dict) or set(value) != GLOSS_KEYS:
        raise BundleError(f"{label} must contain exactly {sorted(GLOSS_KEYS)}")
    availability = value["availability"]
    if is_gloss:
        if availability not in {"AVAILABLE", "UNAVAILABLE"}:
            raise BundleError(f"{label}.availability must be AVAILABLE or UNAVAILABLE")
        if availability == "AVAILABLE":
            for key in sorted(GLOSS_COUNTERS):
                _nonnegative_integer(value[key], f"{label}.{key}")
            if task_form == "python" and any(value[key] != 0 for key in GLOSS_COUNTERS):
                raise BundleError(f"{label} counters must all be zero for the Gloss Python no-op arm")
        elif any(value[key] is not None for key in GLOSS_COUNTERS):
            raise BundleError(f"{label} counters must be null when telemetry is UNAVAILABLE")
    else:
        if availability != "NOT_APPLICABLE":
            raise BundleError(f"{label}.availability must be NOT_APPLICABLE")
        if any(value[key] is not None for key in GLOSS_COUNTERS):
            raise BundleError(f"{label} counters must be null when not applicable")


def _validate_result_row(
    row: object,
    *,
    row_number: int,
    system: str,
    task_form: str,
) -> tuple[str, str, bool, str]:
    label = f"{system}/{task_form} result {row_number}"
    if not isinstance(row, dict) or set(row) != ROW_KEYS:
        actual = sorted(row) if isinstance(row, dict) else type(row).__name__
        raise BundleError(f"{label} has invalid fields: {actual}")
    question_id = row["question_id"]
    difficulty = row["difficulty"]
    if not isinstance(question_id, str) or not question_id or question_id.strip() != question_id:
        raise BundleError(f"{label}.question_id must be a nonempty trimmed string")
    if difficulty not in DIFFICULTY_ORDER:
        raise BundleError(f"{label}.difficulty must be easy, medium, or hard")
    disposition = row["disposition"]
    outcome = row["outcome"]
    if disposition not in DISPOSITIONS:
        raise BundleError(f"{label}.disposition is not recognized")
    if disposition == "COMPLETED":
        if outcome not in UPSTREAM_OUTCOMES:
            raise BundleError(f"{label}.outcome must be an upstream outcome when completed")
    elif outcome is not None:
        raise BundleError(f"{label}.outcome must be null for {disposition}")
    if task_form == "python" and outcome == "PYTHON_LEAK":
        raise BundleError(f"{label}: PYTHON_LEAK is invalid for the Python control")
    _optional_nonnegative_integer(row["input_tokens"], f"{label}.input_tokens")
    _optional_nonnegative_integer(row["output_tokens"], f"{label}.output_tokens")
    _optional_nonnegative_number(row["latency_ms"], f"{label}.latency_ms")
    _validate_gloss_telemetry(
        row["gloss_telemetry"],
        is_gloss=system == "hearthline_gloss",
        task_form=task_form,
        label=f"{label}.gloss_telemetry",
    )
    return question_id, difficulty, outcome == "PASS", disposition


def validate_bundle(document: object) -> dict[str, object]:
    document = _exact_object(document, ROOT_KEYS, "result bundle root")
    if document.get("schema_version") != "1.0":
        raise BundleError("schema_version must be 1.0")
    if document.get("experiment_id") != EXPERIMENT_ID:
        raise BundleError(f"experiment_id must be {EXPERIMENT_ID}")
    if document.get("status") != RESULT_STATUS:
        raise BundleError(f"status must be {RESULT_STATUS}")
    _sha256(document.get("pilot_manifest_sha256"), "pilot_manifest_sha256")
    _sha256(document.get("source_lock_sha256"), "source_lock_sha256")

    model = _exact_object(document.get("model"), MODEL_KEYS, "model")
    if model["family"] != "GPT-5.6 Sol":
        raise BundleError("model.family must be GPT-5.6 Sol")
    for key in ("platform_slug", "snapshot", "reasoning_setting"):
        _nonempty_string(model[key], f"model.{key}")
    _sha256(model["sampling_configuration_sha256"], "model.sampling_configuration_sha256")
    _recorded_provider_value(model["provider_seed_effective"], "model.provider_seed_effective")
    _recorded_provider_value(
        model["provider_temperature_effective"], "model.provider_temperature_effective"
    )

    systems_record = _exact_object(document.get("systems"), SYSTEM_KEYS, "systems")
    for key in ("hearthline_commit", "gloss_commit"):
        _nonempty_string(systems_record[key], f"systems.{key}")
    for key in (
        "hearthline_sha256",
        "gloss_sha256",
        "astra_exclusion_attestation_sha256",
    ):
        _sha256(systems_record[key], f"systems.{key}")

    execution = _exact_object(document.get("execution"), EXECUTION_KEYS, "execution")
    expected_execution = {
        "n_jobs": 1,
        "max_attempts": 1,
        "on_failure": "continue",
        "internet_enabled": False,
        "retrieval_enabled": False,
        "model_tools_enabled": False,
        "llm_judge_enabled": False,
    }
    if execution != expected_execution:
        raise BundleError("execution must match the frozen conservative policy")
    if document.get("claim_ceiling") != CLAIM_CEILING:
        raise BundleError("claim_ceiling exceeds or differs from the structural-only boundary")

    conditions = document.get("conditions")
    if not isinstance(conditions, list) or len(conditions) != len(CONDITIONS):
        raise BundleError("result bundle must contain exactly six conditions")

    reference_order: list[tuple[str, str]] | None = None
    condition_counts: dict[tuple[str, str], dict[str, object]] = {}
    for condition_number, (condition, expected) in enumerate(zip(conditions, CONDITIONS), start=1):
        condition_id, system, task_form = expected
        if not isinstance(condition, dict) or set(condition) != {"id", "system", "task_form", "results"}:
            raise BundleError(f"condition {condition_number} has invalid fields")
        if (condition["id"], condition["system"], condition["task_form"]) != expected:
            raise BundleError(
                f"condition {condition_number} must be {condition_id}/{system}/{task_form}"
            )
        results = condition["results"]
        if not isinstance(results, list) or len(results) != 15:
            raise BundleError(f"{condition_id} must contain exactly 15 results")
        order: list[tuple[str, str]] = []
        passes = 0
        dispositions: Counter[str] = Counter()
        for row_number, row in enumerate(results, start=1):
            question_id, difficulty, passed, disposition = _validate_result_row(
                row, row_number=row_number, system=system, task_form=task_form
            )
            order.append((question_id, difficulty))
            passes += int(passed)
            dispositions[disposition] += 1
        if len({question_id for question_id, _ in order}) != 15:
            raise BundleError(f"{condition_id} contains duplicate question_id values")
        if [difficulty for _, difficulty in order] != EXPECTED_DIFFICULTIES:
            raise BundleError(f"{condition_id} must order 5 easy, 5 medium, then 5 hard IDs")
        if reference_order is None:
            reference_order = order
        elif order != reference_order:
            raise BundleError(f"{condition_id} does not use the same ordered pilot IDs")
        complete = dispositions.get("COMPLETED", 0) == 15
        condition_counts[(system, task_form)] = {
            "passes": passes,
            "total": 15,
            "pass_rate": passes / 15 if complete else None,
            "dispositions": {key: dispositions.get(key, 0) for key in sorted(DISPOSITIONS)},
        }

    systems: dict[str, object] = {}
    for system in ("bare", "hearthline", "hearthline_gloss"):
        python_stats = condition_counts[(system, "python")]
        core_stats = condition_counts[(system, "core")]
        python_rate = python_stats["pass_rate"]
        core_rate = core_stats["pass_rate"]
        systems[system] = {
            "python": python_stats,
            "core": core_stats,
            "learning_tax": (
                python_rate - core_rate
                if isinstance(python_rate, float) and isinstance(core_rate, float)
                else None
            ),
        }
    supplied_summary = _exact_object(document.get("summary"), SUMMARY_KEYS, "summary")
    for system in ("bare", "hearthline", "hearthline_gloss"):
        key = f"{system}_learning_tax"
        expected = systems[system]["learning_tax"]
        supplied = supplied_summary[key]
        if expected is None:
            if supplied is not None:
                raise BundleError(f"summary.{key} must be null while paired cells are incomplete")
        elif (
            isinstance(supplied, bool)
            or not isinstance(supplied, (int, float))
            or not math.isfinite(float(supplied))
            or abs(float(supplied) - expected) > 1e-12
        ):
            raise BundleError(f"summary.{key} does not match the computed learning tax")
    return {
        "verdict": "STRUCTURAL_ONLY_PASS",
        "conditions_checked": 6,
        "ordered_pilot_ids_checked": 15,
        "difficulty_counts": {"easy": 5, "medium": 5, "hard": 5},
        "systems": systems,
        "code_executed": False,
        "model_calls": 0,
        "evaluator_runs": 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--pilot-manifest", type=Path)
    parser.add_argument("--source-lock", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if (args.pilot_manifest is None) != (args.source_lock is None):
            raise BundleError("--pilot-manifest and --source-lock must be supplied together")
        document = load_bundle(args.bundle)
        report = validate_bundle(document)
        if args.pilot_manifest is None:
            report["external_binding_files"] = "NOT_CHECKED_STRUCTURAL_ONLY"
        else:
            result_document = _exact_object(document, ROOT_KEYS, "result bundle root")
            report["external_binding_files"] = verify_external_bindings(
                result_document, args.pilot_manifest, args.source_lock
            )
    except (BundleError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
