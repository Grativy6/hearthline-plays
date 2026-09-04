#!/usr/bin/env python3
"""Statically verify the authorized pre-dispatch ROSETTA-CAL-001 package.

This verifier imports neither the calibration task nor Kaggle Benchmarks. It
performs no authentication, network, data, model, evaluator, or dispatch work.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path("configs/rosetta-cal-001.toml")
TASK_PATH = Path("calibration/rosetta_cal_001_task.py")
EXCLUSION_PATH = Path("exclusions/development-tasks.v1.json")
STATUS_PATH = Path("status/rosetta-cal-001-status.v1.json")

EXPERIMENT_ID = "ROSETTA-CAL-001"
FORMAL_EXPERIMENT_ID = "ROSETTA-001"
TASK_ID = "abc357_b"
TASK_SLUG = "hearthline-rosetta-cal-001-abc357b"
DATASET_SLUG = "namanbnsl/rosettabench-150-stratified-compressed"
DATASET_VERSION = 1
DATASET_TOTAL_BYTES = 736_965_670
SDK_COMMIT = "ab291417d9a4c731ccfbfb03ac0b8316cb843683"
ROSETTABENCH_COMMIT = "099b4837252becbd2c650ca54b206ac1a6bc3470"
DATASET_COMMIT = "87567193229336fae36f0da95c4af6a2a46bf90f"
EXCLUSION_SHA256 = "da455a01dd2c8efc40734e7ded03efe5a8e1ebb45a2fed4cec3777b52e68d389"
ENVIRONMENT_FREEZE_SHA256 = "e9428d7ebb71e514f3afb4aba28259ead1101b904afb5599e4d70d2677f0918b"
CALIBRATION_MODEL = "gpt-5.6-terra"
FORMAL_MODEL = "gpt-5.6-sol"
REASONING = "low"
MAX_COMPLETION_TOKENS = 2048
MAX_MODEL_CALLS = 4
EXPECTED_CELLS = [
    {"id": "CAL01_BARE_PYTHON", "system": "bare", "task_form": "python"},
    {"id": "CAL02_BARE_CORE", "system": "bare", "task_form": "core"},
    {"id": "CAL03_HEARTHLINE_CORE", "system": "hearthline", "task_form": "core"},
    {
        "id": "CAL04_HEARTHLINE_TASK_GLOSS_CORE",
        "system": "hearthline_task_gloss",
        "task_form": "core",
    },
]
EXPECTED_SOURCE_CELLS = [
    ("CAL01_BARE_PYTHON", "PYTHON", "BARE", False),
    ("CAL02_BARE_CORE", "CORE", "BARE", False),
    ("CAL03_HEARTHLINE_CORE", "CORE", "HEARTHLINE", False),
    (
        "CAL04_HEARTHLINE_TASK_GLOSS_CORE",
        "CORE",
        "HEARTHLINE_TASK_LOCAL_GLOSS",
        True,
    ),
]
LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
CLAIM_CEILING = (
    "One final same-private-task repair update and one four-call Terra run are authorized but "
    "not yet dispatched; no model call, evaluator run, score, learning tax, Gloss benefit, "
    "ARC-AGI-3 result, or public leaderboard claim exists."
)


class CalibrationVerificationError(ValueError):
    """Raised when the static calibration package violates its frozen boundary."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CalibrationVerificationError(message)


def _exact_object(value: object, keys: set[str], label: str) -> dict[str, object]:
    _require(isinstance(value, dict), f"{label} must be an object")
    result = value
    _require(set(result) == keys, f"{label} fields mismatch")
    return result


def _load_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CalibrationVerificationError(f"cannot read calibration config: {exc}") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CalibrationVerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, label: str) -> object:
    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalibrationVerificationError(f"cannot read {label}: {exc}") from exc


def _sha256_bytes(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CalibrationVerificationError(f"cannot hash {path}: {exc}") from exc


def validate_config(document: object, *, task_sha256: str) -> dict[str, object]:
    root = _exact_object(
        document,
        {"calibration", "storage", "sources", "hosted_task", "model", "execution", "cells"},
        "calibration config",
    )
    calibration = _exact_object(
        root["calibration"],
        {
            "experiment_id",
            "status",
            "classification",
            "question_ids",
            "formal_pilot_exclusion_sha256",
        },
        "calibration identity",
    )
    _require(calibration["experiment_id"] == EXPERIMENT_ID, "calibration experiment mismatch")
    _require(
        calibration["status"] == "AUTHORIZED_FINAL_REPAIR_PENDING",
        "calibration is not at the authorized final-repair boundary",
    )
    _require(
        calibration["classification"] == "ROSETTA_DERIVED_FRESH_SALT_ORIENTATION",
        "calibration classification mismatch",
    )
    _require(calibration["question_ids"] == [TASK_ID], "calibration task ID mismatch")
    _require(
        calibration["formal_pilot_exclusion_sha256"] == EXCLUSION_SHA256,
        "calibration exclusion digest mismatch",
    )

    storage = _exact_object(
        root["storage"],
        {"execution_root", "drive", "filesystem", "forbidden_data_drive"},
        "storage",
    )
    _require(
        storage["execution_root"] == r"C:\Users\cdpan\HearthlineData\RosettaBench",
        "execution root mismatch",
    )
    _require(
        storage["drive"] == "C:" and storage["filesystem"] == "NTFS",
        "fixed-drive storage mismatch",
    )
    _require(storage["forbidden_data_drive"] == "E:", "forbidden data drive mismatch")

    sources = _exact_object(
        root["sources"],
        {
            "kaggle_benchmarks_commit",
            "rosettabench_inspection_commit",
            "kaggle_dataset",
            "kaggle_dataset_expected_version",
            "kaggle_dataset_expected_total_bytes",
        },
        "sources",
    )
    _require(sources["kaggle_benchmarks_commit"] == SDK_COMMIT, "SDK commit mismatch")
    _require(
        sources["rosettabench_inspection_commit"] == ROSETTABENCH_COMMIT,
        "RosettaBench commit mismatch",
    )
    _require(sources["kaggle_dataset"] == DATASET_SLUG, "dataset slug mismatch")
    _require(
        sources["kaggle_dataset_expected_version"] == DATASET_VERSION,
        "dataset version mismatch",
    )
    _require(
        sources["kaggle_dataset_expected_total_bytes"] == DATASET_TOTAL_BYTES,
        "dataset size mismatch",
    )

    hosted = _exact_object(
        root["hosted_task"],
        {"slug", "private", "persistent", "publication_enabled", "source_sha256"},
        "hosted task",
    )
    _require(hosted["slug"] == TASK_SLUG, "hosted task slug mismatch")
    _require(
        hosted["private"] is True and hosted["persistent"] is True,
        "hosted task privacy/persistence mismatch",
    )
    _require(hosted["publication_enabled"] is False, "publication must remain disabled")
    _require(
        isinstance(hosted["source_sha256"], str)
        and LOWER_SHA256.fullmatch(hosted["source_sha256"]),
        "task source SHA-256 is not frozen",
    )
    _require(hosted["source_sha256"] == task_sha256, "task source SHA-256 mismatch")

    model = _exact_object(
        root["model"],
        {
            "requested_formal_model",
            "requested_formal_model_status",
            "calibration_model",
            "reasoning",
            "max_completion_tokens",
        },
        "model",
    )
    _require(model["requested_formal_model"] == FORMAL_MODEL, "formal model identity mismatch")
    _require(
        model["requested_formal_model_status"]
        == "ABSENT_FROM_AUTHENTICATED_KAGGLE_MODEL_LIST",
        "formal model status mismatch",
    )
    _require(model["calibration_model"] == CALIBRATION_MODEL, "calibration model mismatch")
    _require(model["reasoning"] == REASONING, "reasoning setting mismatch")
    _require(
        model["max_completion_tokens"] == MAX_COMPLETION_TOKENS,
        "completion-token cap mismatch",
    )

    execution = _exact_object(
        root["execution"],
        {
            "fresh_chat_per_cell",
            "max_model_calls",
            "max_attempts_per_cell",
            "automatic_retries",
            "model_tools_enabled",
            "retrieval_enabled",
            "cross_cell_memory_enabled",
            "local_generated_code_execution",
        },
        "execution",
    )
    expected_execution = {
        "fresh_chat_per_cell": True,
        "max_model_calls": MAX_MODEL_CALLS,
        "max_attempts_per_cell": 1,
        "automatic_retries": False,
        "model_tools_enabled": False,
        "retrieval_enabled": False,
        "cross_cell_memory_enabled": False,
        "local_generated_code_execution": False,
    }
    _require(execution == expected_execution, "execution policy mismatch")
    _require(root["cells"] == EXPECTED_CELLS, "calibration cells or order mismatch")
    return root


def validate_exclusion(path: Path) -> None:
    _require(
        _sha256_bytes(path) == EXCLUSION_SHA256,
        "development exclusion SHA-256 mismatch",
    )
    root = _exact_object(
        _load_json(path, "development exclusion"),
        {"schema_version", "experiment_id", "status", "source_dataset_commit", "excluded"},
        "development exclusion",
    )
    _require(root["schema_version"] == "1.0", "development exclusion schema mismatch")
    _require(
        root["experiment_id"] == FORMAL_EXPERIMENT_ID,
        "development exclusion experiment mismatch",
    )
    _require(
        root["status"] == "FROZEN_DEVELOPMENT_EXCLUSIONS",
        "development exclusion is not frozen",
    )
    _require(
        root["source_dataset_commit"] == DATASET_COMMIT,
        "development exclusion dataset mismatch",
    )
    rows = root["excluded"]
    _require(isinstance(rows, list) and len(rows) == 1, "development exclusion count mismatch")
    row = _exact_object(
        rows[0],
        {"question_id", "reason", "public_source"},
        "development exclusion row",
    )
    _require(row["question_id"] == TASK_ID, "development exclusion task mismatch")
    _require(
        row["reason"] == "ROSETTA-CAL-001_PUBLICLY_DISCLOSED_DEVELOPMENT_TASK",
        "development exclusion reason mismatch",
    )


def _assignments(tree: ast.Module) -> dict[str, ast.expr]:
    result: dict[str, ast.expr] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            result[node.targets[0].id] = node.value
    return result


def _literal_assignment(assignments: Mapping[str, ast.expr], name: str) -> object:
    _require(name in assignments, f"task source is missing {name}")
    try:
        return ast.literal_eval(assignments[name])
    except (ValueError, TypeError) as exc:
        raise CalibrationVerificationError(f"task source {name} is not a literal") from exc


def _literal_frozenset_assignment(
    assignments: Mapping[str, ast.expr], name: str
) -> frozenset[object]:
    _require(name in assignments, f"task source is missing {name}")
    node = assignments[name]
    _require(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "frozenset"
        and len(node.args) == 1
        and not node.keywords,
        f"task source {name} must be a literal frozenset",
    )
    try:
        return frozenset(ast.literal_eval(node.args[0]))
    except (ValueError, TypeError) as exc:
        raise CalibrationVerificationError(
            f"task source {name} must contain literals"
        ) from exc


def _parse_source_cells(node: ast.expr) -> list[tuple[str, str, str, bool]]:
    _require(
        isinstance(node, (ast.Tuple, ast.List)),
        "task source CELLS must be a literal sequence",
    )
    cells: list[tuple[str, str, str, bool]] = []
    for item in node.elts:
        _require(
            isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == "CellSpec",
            "task source CELLS must contain only CellSpec calls",
        )
        _require(len(item.args) == 3, "task source CellSpec positional fields mismatch")
        try:
            cell_id, task_form, treatment = (ast.literal_eval(value) for value in item.args)
        except (ValueError, TypeError) as exc:
            raise CalibrationVerificationError(
                "task source CellSpec fields must be literals"
            ) from exc
        gloss_enabled = False
        _require(
            all(keyword.arg == "gloss_enabled" for keyword in item.keywords),
            "task source CellSpec keyword mismatch",
        )
        if item.keywords:
            _require(len(item.keywords) == 1, "task source CellSpec has duplicate keywords")
            gloss_enabled = ast.literal_eval(item.keywords[0].value)
        cells.append((cell_id, task_form, treatment, gloss_enabled))
    return cells


def _attribute_chain(node: ast.AST) -> tuple[str, ...] | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return tuple(reversed(parts))


def validate_task_source(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        tree = ast.parse(text, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise CalibrationVerificationError(
            f"cannot parse calibration task source: {exc}"
        ) from exc
    assignments = _assignments(tree)
    expected_literals = {
        "EXPERIMENT_ID": EXPERIMENT_ID,
        "TASK_ID": TASK_ID,
        "DATASET_SLUG": DATASET_SLUG,
        "DATASET_EXPECTED_VERSION": DATASET_VERSION,
        "DATASET_EXPECTED_TOTAL_BYTES": DATASET_TOTAL_BYTES,
        "MAX_LLM_CALLS": MAX_MODEL_CALLS,
        "ATTEMPTS_PER_CELL": 1,
        "REASONING_EFFORT": REASONING,
        "MAX_COMPLETION_TOKENS": MAX_COMPLETION_TOKENS,
    }
    for name, expected in expected_literals.items():
        _require(
            _literal_assignment(assignments, name) == expected,
            f"task source {name} mismatch",
        )
    salt = _literal_assignment(assignments, "DIALECT_SALT_HEX")
    _require(
        isinstance(salt, str) and LOWER_SHA256.fullmatch(salt),
        "task dialect salt is not frozen",
    )
    domain = _literal_assignment(assignments, "DIALECT_DOMAIN")
    _require(
        domain == "hearthline/rosetta-cal-001/abc357_b/hash-identifiers-v1",
        "task dialect domain mismatch",
    )
    _require("CELLS" in assignments, "task source is missing CELLS")
    _require(
        _parse_source_cells(assignments["CELLS"]) == EXPECTED_SOURCE_CELLS,
        "task source cells mismatch",
    )
    expected_model_slugs = _literal_frozenset_assignment(assignments, "EXPECTED_MODEL_SLUGS")
    _require(
        expected_model_slugs
        == frozenset({CALIBRATION_MODEL, f"openai/{CALIBRATION_MODEL}"}),
        "task source model allowlist mismatch",
    )

    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    prompt_calls = [call for call in calls if _attribute_chain(call.func) == ("llm", "prompt")]
    chat_calls = [
        call for call in calls if _attribute_chain(call.func) == ("kbench", "chats", "new")
    ]
    run_calls = [call for call in calls if _attribute_chain(call.func) == ("task", "run")]
    _require(len(prompt_calls) == 1, "task source must have one model prompt callsite")
    _require(
        {keyword.arg for keyword in prompt_calls[0].keywords}
        == {"reasoning", "extra_api_params"},
        "model prompt keyword policy mismatch",
    )
    _require(
        len(chat_calls) == 1 and len(chat_calls[0].args) == 1,
        "fresh-chat callsite mismatch",
    )
    _require(
        isinstance(chat_calls[0].args[0], ast.Name)
        and chat_calls[0].args[0].id == "cell_id",
        "fresh-chat ID mismatch",
    )
    _require(
        len(run_calls) == 1 and not run_calls[0].args,
        "hosted task run callsite mismatch",
    )
    _require(
        len(run_calls[0].keywords) == 1 and run_calls[0].keywords[0].arg == "llm",
        "hosted task llm injection mismatch",
    )
    _require(
        _attribute_chain(run_calls[0].keywords[0].value) == ("kbench", "llm"),
        "hosted task must use supplied kbench.llm",
    )
    _require("kbench.llms" not in text, "task source must not select a model internally")
    _require(
        not any(
            _attribute_chain(call.func) is not None
            and _attribute_chain(call.func)[-1] in {"publish", "push"}
            for call in calls
        ),
        "task source must not contain publication or task-push callsites",
    )

    hosted_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "rosetta_cal_001_task"
    ]
    _require(len(hosted_functions) == 1, "hosted calibration function mismatch")
    hosted_function = hosted_functions[0]
    model_guards = [
        node
        for node in ast.walk(hosted_function)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "actor_model"
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.NotIn)
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Name)
        and node.comparators[0].id == "EXPECTED_MODEL_SLUGS"
    ]
    data_loads = [
        call
        for call in ast.walk(hosted_function)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "load_attached_calibration_data"
    ]
    _require(len(model_guards) == 1, "hosted task model guard mismatch")
    _require(len(data_loads) == 1, "hosted task dataset load callsite mismatch")
    _require(
        model_guards[0].lineno < data_loads[0].lineno,
        "hosted task must reject the wrong model before loading data",
    )

    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    _require("CallBudget" in classes, "task source is missing CallBudget")
    invoke = next(
        (
            node
            for node in classes["CallBudget"].body
            if isinstance(node, ast.FunctionDef) and node.name == "invoke"
        ),
        None,
    )
    _require(invoke is not None, "task source is missing CallBudget.invoke")
    caller_calls = [
        call
        for call in ast.walk(invoke)
        if isinstance(call, ast.Call) and _attribute_chain(call.func) == ("self", "_caller")
    ]
    _require(len(caller_calls) == 1, "CallBudget must have one caller invocation")
    keywords = {keyword.arg: keyword.value for keyword in caller_calls[0].keywords}
    _require(
        set(keywords) == {"cell_id", "messages", "reasoning", "extra_api_params"},
        "CallBudget caller arguments mismatch",
    )
    _require(
        isinstance(keywords["reasoning"], ast.Name)
        and keywords["reasoning"].id == "REASONING_EFFORT",
        "CallBudget reasoning is not frozen",
    )
    params = keywords["extra_api_params"]
    _require(
        isinstance(params, ast.Dict) and len(params.keys) == 1,
        "CallBudget completion parameters mismatch",
    )
    _require(
        ast.literal_eval(params.keys[0]) == "max_completion_tokens",
        "CallBudget completion parameter name mismatch",
    )
    _require(
        isinstance(params.values[0], ast.Name)
        and params.values[0].id == "MAX_COMPLETION_TOKENS",
        "CallBudget completion cap is not frozen",
    )
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "cells": len(EXPECTED_CELLS),
        "model_prompt_callsites": len(prompt_calls),
        "fresh_chat_callsites": len(chat_calls),
        "task_run_callsites": len(run_calls),
    }


def validate_status(document: object, *, task_sha256: str) -> None:
    root = _exact_object(
        document,
        {
            "schema_version",
            "experiment_id",
            "status",
            "recorded_at_utc",
            "authorization",
            "host_setup",
            "platform_preflight",
            "source_binding",
            "dispatch",
            "formal_experiment",
            "pending_action",
            "claim_ceiling",
        },
        "calibration status",
    )
    _require(
        root["schema_version"] == "rosetta-cal-status.v1",
        "calibration status schema mismatch",
    )
    _require(root["experiment_id"] == EXPERIMENT_ID, "calibration status experiment mismatch")
    _require(
        root["status"] == "AUTHORIZED_FINAL_REPAIR_PENDING",
        "calibration status is not at the authorized final-repair boundary",
    )
    _require(
        isinstance(root["recorded_at_utc"], str)
        and UTC_TIMESTAMP.fullmatch(root["recorded_at_utc"]),
        "calibration status timestamp mismatch",
    )
    authorization = _exact_object(
        root["authorization"],
        {
            "private_task_pushes_authorized",
            "same_task_build_repair_pushes_authorized",
            "same_task_build_repair_pushes_remaining",
            "additional_task_versions_authorized",
            "hosted_runs_authorized",
            "model_calls_authorized_maximum",
            "automatic_retries_authorized",
            "publication_authorized",
            "formal_pilot_consumption_authorized",
        },
        "calibration authorization",
    )
    _require(
        authorization
        == {
            "private_task_pushes_authorized": 1,
            "same_task_build_repair_pushes_authorized": 2,
            "same_task_build_repair_pushes_remaining": 1,
            "additional_task_versions_authorized": True,
            "hosted_runs_authorized": 1,
            "model_calls_authorized_maximum": MAX_MODEL_CALLS,
            "automatic_retries_authorized": False,
            "publication_authorized": False,
            "formal_pilot_consumption_authorized": False,
        },
        "calibration authorization mismatch",
    )
    host = _exact_object(
        root["host_setup"],
        {
            "execution_root",
            "fixed_drive",
            "filesystem",
            "forbidden_data_drive",
            "python_version",
            "kaggle_cli_version",
            "sdk_version",
            "sdk_commit",
            "environment_freeze_sha256",
            "environment_package_count",
            "rosettabench_commit",
            "local_dataset_files",
            "local_dataset_bytes",
        },
        "calibration host setup",
    )
    _require(
        host["execution_root"] == r"C:\Users\cdpan\HearthlineData\RosettaBench",
        "status execution root mismatch",
    )
    _require(
        host["fixed_drive"] == "C:" and host["filesystem"] == "NTFS",
        "status fixed-drive mismatch",
    )
    _require(host["forbidden_data_drive"] == "E:", "status forbidden drive mismatch")
    _require(host["python_version"] == "3.12.14", "status Python version mismatch")
    _require(host["kaggle_cli_version"] == "2.2.4", "status Kaggle CLI version mismatch")
    _require(
        host["sdk_version"] == "0.6.1" and host["sdk_commit"] == SDK_COMMIT,
        "status SDK binding mismatch",
    )
    _require(
        host["environment_freeze_sha256"] == ENVIRONMENT_FREEZE_SHA256,
        "status environment freeze mismatch",
    )
    _require(host["environment_package_count"] == 146, "status environment package count mismatch")
    _require(
        host["rosettabench_commit"] == ROSETTABENCH_COMMIT,
        "status RosettaBench commit mismatch",
    )
    _require(
        host["local_dataset_files"] == 0 and host["local_dataset_bytes"] == 0,
        "local dataset materialization detected",
    )

    preflight = _exact_object(
        root["platform_preflight"],
        {
            "authentication",
            "requested_formal_model",
            "requested_formal_model_status",
            "calibration_model",
            "calibration_model_status",
            "dataset",
            "dataset_version_observed",
            "dataset_total_bytes_observed",
            "duplicate_private_task_matches",
            "recheck_immediately_before_push",
        },
        "platform preflight",
    )
    expected_preflight = {
        "authentication": "AUTHENTICATED",
        "requested_formal_model": FORMAL_MODEL,
        "requested_formal_model_status": "ABSENT_FROM_AUTHENTICATED_KAGGLE_MODEL_LIST",
        "calibration_model": CALIBRATION_MODEL,
        "calibration_model_status": "AVAILABLE",
        "dataset": DATASET_SLUG,
        "dataset_version_observed": DATASET_VERSION,
        "dataset_total_bytes_observed": DATASET_TOTAL_BYTES,
        "duplicate_private_task_matches": 1,
        "recheck_immediately_before_push": True,
    }
    _require(preflight == expected_preflight, "platform preflight mismatch")

    binding = _exact_object(root["source_binding"], {"path", "sha256"}, "source binding")
    _require(binding["path"] == TASK_PATH.as_posix(), "status task source path mismatch")
    _require(binding["sha256"] == task_sha256, "status task source SHA-256 mismatch")
    dispatch = _exact_object(
        root["dispatch"],
        {
            "task_slug",
            "private",
            "client_side_creation_rejections",
            "client_side_last_error",
            "server_side_creation_failures",
            "server_side_last_error",
            "task_pushes",
            "task_versions_created",
            "hosted_run_requests_rejected_pre_dispatch",
            "hosted_runs",
            "model_calls",
            "evaluator_runs",
            "publications",
            "task_reference",
            "run_reference",
            "uncertain_external_effect",
        },
        "dispatch",
    )
    _require(
        dispatch["task_slug"] == TASK_SLUG and dispatch["private"] is True,
        "dispatch target mismatch",
    )
    _require(
        dispatch["client_side_creation_rejections"] == 2
        and dispatch["client_side_last_error"]
        == "OWNER_QUALIFIED_SLUG_REJECTED_BEFORE_EXTERNAL_WRITE",
        "client-side creation rejection record mismatch",
    )
    _require(
        dispatch["server_side_creation_failures"] == 2
        and dispatch["server_side_last_error"]
        == "BUILD_ACTOR_REJECTED_BEFORE_DATA_OR_MODEL_ACCESS",
        "server-side creation failure record mismatch",
    )
    _require(dispatch["task_pushes"] == 2, "two exhausted task pushes must be recorded")
    _require(
        dispatch["task_versions_created"] == 2,
        "exactly two errored task versions must be recorded",
    )
    _require(
        dispatch["hosted_run_requests_rejected_pre_dispatch"] == 1,
        "rejected pre-dispatch run request mismatch",
    )
    for key in ("hosted_runs", "model_calls", "evaluator_runs", "publications"):
        _require(
            type(dispatch[key]) is int and dispatch[key] == 0,
            f"repair-boundary {key} must be zero",
        )
    _require(
        dispatch["task_reference"] == "PRIVATE_TASK_VERSION_2_WITHHELD"
        and dispatch["run_reference"] is None,
        "repair-boundary references mismatch",
    )
    _require(dispatch["uncertain_external_effect"] is False, "uncertain external effect recorded")

    pending_action = _exact_object(
        root["pending_action"],
        {
            "code",
            "prepared_source_is_pushed",
            "next_external_action",
            "hosted_runs_remaining",
            "model_calls_so_far",
        },
        "calibration pending action",
    )
    _require(
        pending_action
        == {
            "code": "FINAL_SAME_PRIVATE_TASK_UPDATE_AND_SINGLE_TERRA_RUN_AUTHORIZED",
            "prepared_source_is_pushed": False,
            "next_external_action": "ONE_SAME_PRIVATE_TASK_VERSION_UPDATE",
            "hosted_runs_remaining": 1,
            "model_calls_so_far": 0,
        },
        "calibration pending action mismatch",
    )

    formal = _exact_object(
        root["formal_experiment"],
        {
            "experiment_id",
            "status",
            "pilot_status",
            "pilot_identifiers_selected",
            "model_calls",
            "evaluator_runs",
        },
        "formal experiment boundary",
    )
    _require(
        formal
        == {
            "experiment_id": FORMAL_EXPERIMENT_ID,
            "status": "PREPARED_NOT_RUN",
            "pilot_status": "PILOT_UNSELECTED_UNCONSUMED",
            "pilot_identifiers_selected": 0,
            "model_calls": 0,
            "evaluator_runs": 0,
        },
        "formal experiment boundary mismatch",
    )
    _require(root["claim_ceiling"] == CLAIM_CEILING, "calibration claim ceiling mismatch")


def verify_calibration(repo_root: Path = REPO_ROOT) -> dict[str, object]:
    root = repo_root.resolve(strict=True)
    required = (CONFIG_PATH, TASK_PATH, EXCLUSION_PATH, STATUS_PATH)
    missing = [path.as_posix() for path in required if not (root / path).is_file()]
    _require(not missing, "missing calibration files: " + ", ".join(missing))
    task_report = validate_task_source(root / TASK_PATH)
    task_sha256 = task_report["sha256"]
    _require(isinstance(task_sha256, str), "task source digest unavailable")
    validate_config(_load_toml(root / CONFIG_PATH), task_sha256=task_sha256)
    validate_exclusion(root / EXCLUSION_PATH)
    validate_status(
        _load_json(root / STATUS_PATH, "calibration status"),
        task_sha256=task_sha256,
    )
    return {
        "verdict": "PASS_STATIC_FINAL_REPAIR_AUTHORIZED",
        "experiment_id": EXPERIMENT_ID,
        "task_id": TASK_ID,
        "task_source_sha256": task_sha256,
        "cells": len(EXPECTED_CELLS),
        "maximum_model_calls": MAX_MODEL_CALLS,
        "model": CALIBRATION_MODEL,
        "publication_enabled": False,
        "formal_pilot_consumed": False,
        "verification_side_effects": {
            "network_calls": 0,
            "model_calls": 0,
            "evaluator_runs": 0,
            "external_writes": 0,
        },
        "task_static_checks": task_report,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--mode",
        choices=("pre-dispatch",),
        default="pre-dispatch",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = verify_calibration(args.repo_root)
    except (CalibrationVerificationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
