#!/usr/bin/env python3
"""Compile two Spark Static records into a third, source-preserving Pair Static.

This utility performs deterministic structural comparison. It does not solve the
underlying task, infer independence, or average confidence estimates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterator


class StaticError(ValueError):
    """Raised when a Spark Static cannot be compared safely."""


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise StaticError(f"{path}: expected one JSON object")
    return value


def validate_static(value: dict[str, Any], label: str) -> None:
    required = {
        "schema",
        "static_id",
        "task_id",
        "spark_id",
        "lens",
        "observation_refs",
        "claims",
        "candidate_world_model",
        "proposed_action",
        "predicted_consequence",
        "residuals",
        "claim_ceiling",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise StaticError(f"{label}: missing fields: {', '.join(missing)}")
    if value["schema"] != "hearthline.spark-static.v1":
        raise StaticError(f"{label}: unsupported schema {value['schema']!r}")
    if not isinstance(value["claims"], list):
        raise StaticError(f"{label}: claims must be a list")
    if not isinstance(value["candidate_world_model"], dict):
        raise StaticError(f"{label}: candidate_world_model must be an object")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def flatten(value: Any, prefix: str = "$") -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        if not value:
            yield prefix, {}
        for key in sorted(value):
            yield from flatten(value[key], f"{prefix}.{key}")
    elif isinstance(value, list):
        if not value:
            yield prefix, []
        for index, item in enumerate(value):
            yield from flatten(item, f"{prefix}[{index}]")
    else:
        yield prefix, value


def claim_signature(claim: Any) -> str:
    if not isinstance(claim, dict):
        return canonical(claim)
    return canonical(
        {
            "status": claim.get("status"),
            "text": claim.get("text"),
        }
    )


def confidence_summary(value: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for claim in value.get("claims", []):
        if not isinstance(claim, dict) or claim.get("confidence") is None:
            continue
        out.append(
            {
                "claim_id": claim.get("claim_id"),
                "text": claim.get("text"),
                "confidence": claim.get("confidence"),
            }
        )
    return out


def compare_world_models(a: dict[str, Any], b: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    flat_a = dict(flatten(a))
    flat_b = dict(flatten(b))
    agreements: list[str] = []
    differences: list[dict[str, Any]] = []
    for key in sorted(set(flat_a) | set(flat_b)):
        has_a = key in flat_a
        has_b = key in flat_b
        if has_a and has_b and canonical(flat_a[key]) == canonical(flat_b[key]):
            agreements.append(f"world_model {key} = {canonical(flat_a[key])}")
        else:
            differences.append(
                {
                    "key": f"world_model {key}",
                    "spark_a": flat_a.get(key, {"status": "ABSENT"}),
                    "spark_b": flat_b.get(key, {"status": "ABSENT"}),
                }
            )
    return agreements, differences


def action_identity(action: Any) -> tuple[Any, Any] | None:
    if not isinstance(action, dict) or not action.get("action"):
        return None
    return action.get("action"), action.get("data", {})


def compile_pair(a: dict[str, Any], b: dict[str, Any], pair_id: str, pair_static_id: str) -> dict[str, Any]:
    validate_static(a, "spark_a")
    validate_static(b, "spark_b")
    if a["task_id"] != b["task_id"]:
        raise StaticError("source Statics have different task_id values")
    if a["static_id"] == b["static_id"]:
        raise StaticError("source Statics must have distinct identities")
    if a["spark_id"] == b["spark_id"]:
        raise StaticError("paired records must come from distinct Spark identities")

    claims_a = {claim_signature(claim): claim for claim in a["claims"]}
    claims_b = {claim_signature(claim): claim for claim in b["claims"]}
    shared_signatures = sorted(set(claims_a) & set(claims_b))
    agreements = [
        f"claim {claims_a[sig].get('status')}: {claims_a[sig].get('text')}"
        if isinstance(claims_a[sig], dict)
        else f"claim {sig}"
        for sig in shared_signatures
    ]

    differences: list[dict[str, Any]] = []
    for signature in sorted(set(claims_a) ^ set(claims_b)):
        differences.append(
            {
                "key": f"claim {signature}",
                "spark_a": claims_a.get(signature, {"status": "ABSENT"}),
                "spark_b": claims_b.get(signature, {"status": "ABSENT"}),
            }
        )

    world_agreements, world_differences = compare_world_models(
        a["candidate_world_model"], b["candidate_world_model"]
    )
    agreements.extend(world_agreements)
    differences.extend(world_differences)

    action_a = action_identity(a["proposed_action"])
    action_b = action_identity(b["proposed_action"])
    recommended: dict[str, Any] | None = None
    if action_a is not None and action_a == action_b:
        agreements.append(f"proposed_action = {canonical(action_a)}")
        source_action = a["proposed_action"]
        recommended = {
            "action": source_action["action"],
            "data": source_action.get("data", {}),
            "reason": "Both source Statics propose the same action; Hearthline must still validate it against the current observation, grant, and budget.",
            "expected_information_gain": "qualitative-medium",
        }
    elif action_a != action_b:
        differences.append(
            {
                "key": "proposed_action",
                "spark_a": a["proposed_action"],
                "spark_b": b["proposed_action"],
            }
        )

    if not agreements and not differences:
        comparison_class = "INSUFFICIENT_FOR_COMPARISON"
    elif world_differences:
        comparison_class = "CONFLICTING_WORLD_MODELS"
    elif action_a is not None and action_a == action_b and differences:
        comparison_class = "SAME_ACTION_DIFFERENT_REASONS"
    elif agreements:
        comparison_class = "AGREEMENT_WITH_DEPENDENT_SUPPORT"
    else:
        comparison_class = "COMPATIBLE_DIFFERENT_RESOLUTIONS"

    shared_dependencies = sorted(
        set(a.get("observation_refs", [])) & set(b.get("observation_refs", []))
    )
    unresolved = sorted(
        {str(item) for item in a.get("residuals", []) + b.get("residuals", [])}
    )

    return {
        "schema": "hearthline.pair-static.v1",
        "pair_static_id": pair_static_id,
        "predecessor_pair_static_id": None,
        "pair_id": pair_id,
        "task_id": a["task_id"],
        "source_statics": [a["static_id"], b["static_id"]],
        "comparison_class": comparison_class,
        "agreements": agreements,
        "differences": differences,
        "shared_dependencies": shared_dependencies,
        "estimates": {
            "spark_a": confidence_summary(a),
            "spark_b": confidence_summary(b),
            "pooling_rule": "NONE",
        },
        "recommended_discriminating_action": recommended,
        "unresolved": unresolved,
        "claim_ceiling": (
            "Deterministic structural comparison of two same-task Statics. "
            "The sources are not independent, estimates are not pooled, and "
            "this record does not choose or authorize an environment action."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spark_a")
    parser.add_argument("spark_b")
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--pair-static-id", required=True)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = compile_pair(
            load_json(args.spark_a),
            load_json(args.spark_b),
            pair_id=args.pair_id,
            pair_static_id=args.pair_static_id,
        )
    except (OSError, json.JSONDecodeError, StaticError) as exc:
        raise SystemExit(f"static_pair: {exc}") from exc

    text = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
