#!/usr/bin/env python3
"""Canonical v2 Spark migration and Pair Static structural compiler.

This standard-library tool never imports an ARC runtime and never selects or
dispatches an environment action. It is the only canonical compiler for the
``hearthline.arc3.*.v2`` Static namespace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator


SPARK_SCHEMA = "hearthline.arc3.spark-static.v2"
PAIR_SCHEMA = "hearthline.arc3.pair-static.v2"


class StaticV2Error(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StaticV2Error(f"{path}: expected one JSON object")
    return value


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_spark(value: dict[str, Any], label: str = "spark") -> None:
    required = {
        "schema", "static_id", "predecessor_static_id", "task_id", "role_id",
        "lens", "observation_refs", "dependencies", "claims",
        "candidate_world_model", "recommendation", "residuals", "status",
        "claim_ceiling", "migration",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise StaticV2Error(f"{label}: missing fields: {', '.join(missing)}")
    if value["schema"] != SPARK_SCHEMA:
        raise StaticV2Error(f"{label}: unsupported schema {value['schema']!r}")
    for field in ("static_id", "task_id", "role_id", "lens", "claim_ceiling"):
        if not _nonempty_string(value[field]):
            raise StaticV2Error(f"{label}: {field} must be a nonempty string")
    for field in ("observation_refs", "dependencies", "claims", "residuals"):
        if not isinstance(value[field], list):
            raise StaticV2Error(f"{label}: {field} must be a list")
    if len(value["observation_refs"]) != len(set(value["observation_refs"])):
        raise StaticV2Error(f"{label}: observation_refs must be unique")
    if len(value["dependencies"]) != len(set(value["dependencies"])):
        raise StaticV2Error(f"{label}: dependencies must be unique")
    if not isinstance(value["candidate_world_model"], dict):
        raise StaticV2Error(f"{label}: candidate_world_model must be an object")
    if value["recommendation"] is not None and not isinstance(value["recommendation"], dict):
        raise StaticV2Error(f"{label}: recommendation must be an object or null")
    if value["status"] not in {"OPEN", "RETURNED", "BLOCKED", "UNRESOLVED"}:
        raise StaticV2Error(f"{label}: invalid status")

    seen: set[str] = set()
    epistemic = {"DIRECT_OBSERVATION", "DERIVED", "HYPOTHESIS", "ESTIMATE", "UNRESOLVED"}
    for index, claim in enumerate(value["claims"]):
        if not isinstance(claim, dict):
            raise StaticV2Error(f"{label}: claim {index} must be an object")
        claim_id = claim.get("claim_id")
        if not _nonempty_string(claim_id) or claim_id in seen:
            raise StaticV2Error(f"{label}: claim IDs must be nonempty and unique")
        seen.add(claim_id)
        if claim.get("epistemic_status") not in epistemic:
            raise StaticV2Error(f"{label}: claim {claim_id} has invalid epistemic_status")
        if not _nonempty_string(claim.get("proposition")):
            raise StaticV2Error(f"{label}: claim {claim_id} needs a proposition")
        if not isinstance(claim.get("evidence_refs"), list) or not isinstance(claim.get("assumptions"), list):
            raise StaticV2Error(f"{label}: claim {claim_id} refs/assumptions must be lists")
        confidence = claim.get("confidence")
        if confidence is not None and (not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
            raise StaticV2Error(f"{label}: claim {claim_id} confidence must be null or 0..1")


def _epistemic_from_root(kind: Any) -> str:
    return {
        "OBSERVATION": "DIRECT_OBSERVATION",
        "MEASUREMENT": "DIRECT_OBSERVATION",
        "INFERENCE": "DERIVED",
        "HYPOTHESIS": "HYPOTHESIS",
        "PLAN_CONSTRAINT": "DERIVED",
    }.get(str(kind), "UNRESOLVED")


def _epistemic_from_launch(status: Any) -> str:
    return {
        "OBSERVED": "DIRECT_OBSERVATION",
        "INFERRED": "DERIVED",
        "ESTIMATED": "ESTIMATE",
        "UNRESOLVED": "UNRESOLVED",
    }.get(str(status), "UNRESOLVED")


def migrate_v1_static(value: dict[str, Any], source_sha256: str) -> dict[str, Any]:
    """Map either incompatible v1 dialect into the explicit ARC v2 namespace."""
    if value.get("schema") != "hearthline.spark-static.v1":
        raise StaticV2Error("migration accepts only a v1 Spark Static")

    if "candidate_world_model" in value:
        dialect = "launch-v1"
        claims = [
            {
                "claim_id": claim.get("claim_id"),
                "epistemic_status": _epistemic_from_launch(claim.get("status")),
                "proposition": str(claim.get("text", "UNRESOLVED")),
                "value": None,
                "evidence_refs": list(claim.get("evidence_refs", [])),
                "assumptions": [],
                "confidence": claim.get("confidence"),
            }
            for claim in value.get("claims", [])
        ]
        action = value.get("proposed_action")
        recommendation = None if action is None else {
            "action": action.get("action"),
            "data": action.get("data", {}),
            "rationale": action.get("reason", "migrated launch-v1 recommendation"),
            "expected_observable": canonical(value.get("predicted_consequence")),
            "authorization": "NOT_AUTHORIZED",
        }
        observation_refs = list(value.get("observation_refs", []))
        dependencies = observation_refs.copy()
        candidate_world_model = dict(value.get("candidate_world_model", {}))
        status = "UNRESOLVED" if value.get("residuals") else "RETURNED"
        claim_ceiling = value.get("claim_ceiling") or "Migrated representation only."
    elif "source_snapshot" in value:
        dialect = "root-v1"
        claims = [
            {
                "claim_id": claim.get("claim_id"),
                "epistemic_status": _epistemic_from_root(claim.get("kind")),
                "proposition": str(claim.get("value")) if isinstance(claim.get("value"), str) else canonical(claim.get("value")),
                "value": claim.get("value"),
                "evidence_refs": list(claim.get("evidence_refs", [])),
                "assumptions": list(claim.get("assumptions", [])),
                "confidence": claim.get("confidence"),
            }
            for claim in value.get("claims", [])
        ]
        tests = value.get("proposed_tests", [])
        first_test = tests[0] if tests else None
        action = first_test.get("action", {}) if isinstance(first_test, dict) else {}
        recommendation = None if not action else {
            "action": action.get("action"),
            "data": action.get("data", {}),
            "rationale": first_test.get("question", "migrated root-v1 test"),
            "expected_observable": first_test.get("expected_discrimination", "unresolved"),
            "authorization": "NOT_AUTHORIZED",
        }
        observation_refs = list(value.get("source_snapshot", []))
        dependencies = list(value.get("dependencies", []))
        candidate_world_model = {}
        status = value.get("status", "UNRESOLVED")
        claim_ceiling = "One-way structural migration from root-v1; no claim, independence, or authority was added."
    else:
        raise StaticV2Error("unrecognized v1 dialect")

    migrated = {
        "schema": SPARK_SCHEMA,
        "static_id": value.get("static_id"),
        "predecessor_static_id": value.get("predecessor_static_id"),
        "task_id": value.get("task_id"),
        "role_id": value.get("spark_id"),
        "lens": value.get("lens"),
        "observation_refs": sorted(set(observation_refs)),
        "dependencies": sorted(set(dependencies)),
        "claims": claims,
        "candidate_world_model": candidate_world_model,
        "recommendation": recommendation,
        "residuals": sorted(set(value.get("residuals", []) + [f"Migrated from {dialect}; source v1 remains canonical history."])),
        "status": status,
        "claim_ceiling": claim_ceiling,
        "migration": {
            "source_schema": "hearthline.spark-static.v1",
            "source_dialect": dialect,
            "source_sha256": source_sha256,
            "direction": "ONE_WAY_V1_TO_V2",
        },
    }
    validate_spark(migrated, "migrated")
    return migrated


def _claim_map(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {claim["claim_id"]: claim for claim in value["claims"]}


def _claim_signature(claim: dict[str, Any]) -> str:
    return canonical({"proposition": claim["proposition"], "value": claim.get("value")})


def _flatten(value: Any, prefix: str = "$") -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        if not value:
            yield prefix, {}
        for key in sorted(value):
            yield from _flatten(value[key], f"{prefix}.{key}")
    elif isinstance(value, list):
        if not value:
            yield prefix, []
        for index, item in enumerate(value):
            yield from _flatten(item, f"{prefix}[{index}]")
    else:
        yield prefix, value


def _action_identity(value: Any) -> str | None:
    if not isinstance(value, dict) or not value.get("action"):
        return None
    return canonical({"action": value["action"], "data": value.get("data", {})})


def compile_pair(
    a: dict[str, Any],
    b: dict[str, Any],
    pair_id: str,
    pair_static_id: str,
) -> dict[str, Any]:
    validate_spark(a, "spark_a")
    validate_spark(b, "spark_b")
    if a["task_id"] != b["task_id"]:
        raise StaticV2Error("source Statics have different task_id values")
    if a["static_id"] == b["static_id"] or a["role_id"] == b["role_id"]:
        raise StaticV2Error("source static_id and role_id values must be distinct")

    am, bm = _claim_map(a), _claim_map(b)
    agreements: list[dict[str, Any]] = []
    differences: list[dict[str, Any]] = []
    unique_claims: list[dict[str, Any]] = []
    conditional_estimates: list[dict[str, Any]] = []

    for claim_id in sorted(set(am) | set(bm)):
        ca, cb = am.get(claim_id), bm.get(claim_id)
        if ca is None or cb is None:
            source, claim = (b["static_id"], cb) if ca is None else (a["static_id"], ca)
            unique_claims.append({"claim_id": claim_id, "source_static": source, "claim": claim})
        elif _claim_signature(ca) == _claim_signature(cb):
            agreements.append({
                "claim_id": claim_id,
                "proposition": ca["proposition"],
                "value": ca.get("value"),
                "source_statuses": [ca["epistemic_status"], cb["epistemic_status"]],
                "independence": "NOT_ESTABLISHED",
            })
        else:
            differences.append({"key": f"claim:{claim_id}", "spark_a": ca, "spark_b": cb})

        for source, claim in ((a["static_id"], ca), (b["static_id"], cb)):
            if claim is not None and claim.get("confidence") is not None:
                conditional_estimates.append({
                    "claim_id": claim_id,
                    "source_static": source,
                    "estimate": claim["confidence"],
                    "evidence_refs": claim["evidence_refs"],
                    "assumptions": claim["assumptions"],
                })

    flat_a, flat_b = dict(_flatten(a["candidate_world_model"])), dict(_flatten(b["candidate_world_model"]))
    for key in sorted(set(flat_a) | set(flat_b)):
        if key not in flat_a or key not in flat_b or canonical(flat_a[key]) != canonical(flat_b[key]):
            differences.append({
                "key": f"world_model:{key}",
                "spark_a": flat_a.get(key, {"status": "ABSENT"}),
                "spark_b": flat_b.get(key, {"status": "ABSENT"}),
            })

    action_a, action_b = _action_identity(a["recommendation"]), _action_identity(b["recommendation"])
    recommended = None
    if action_a is not None and action_a == action_b:
        source_action = a["recommendation"]
        recommended = {
            "action": source_action["action"],
            "data": source_action.get("data", {}),
            "rationale": "Both source Statics propose the same effect; validate against current state, grant, and budget.",
            "expected_information_gain": "QUALITATIVE_MEDIUM",
            "authorization": "NOT_AUTHORIZED",
        }
    elif action_a != action_b:
        differences.append({"key": "recommendation", "spark_a": a["recommendation"], "spark_b": b["recommendation"]})

    shared_dependencies = sorted(set(a["dependencies"]) & set(b["dependencies"]))
    unresolved = sorted(set(a["residuals"] + b["residuals"]))
    if shared_dependencies:
        unresolved.append("Shared dependencies prevent an independence claim.")

    if differences:
        comparison_class = "CONFLICTING_CONDITIONAL_ACCOUNTS"
    elif agreements:
        comparison_class = "AGREEMENT_WITH_DEPENDENCE_UNRESOLVED"
    else:
        comparison_class = "INSUFFICIENT_FOR_COMPARISON"

    return {
        "schema": PAIR_SCHEMA,
        "pair_static_id": pair_static_id,
        "predecessor_pair_static_id": None,
        "pair_id": pair_id,
        "task_id": a["task_id"],
        "source_statics": [a["static_id"], b["static_id"]],
        "comparison_class": comparison_class,
        "agreements": agreements,
        "differences": differences,
        "unique_claims": unique_claims,
        "shared_dependencies": shared_dependencies,
        "conditional_estimates": conditional_estimates,
        "pooling_rule": "NONE",
        "recommended_discriminating_action": recommended,
        "unresolved": unresolved,
        "status": "UNRESOLVED" if differences else "RETURNED",
        "claim_ceiling": "Deterministic comparison only. Sources remain distinct, estimates are not pooled, and no action is authorized.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spark_a", type=Path)
    parser.add_argument("spark_b", type=Path)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--pair-static-id", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = compile_pair(
            load_json(args.spark_a), load_json(args.spark_b),
            pair_id=args.pair_id, pair_static_id=args.pair_static_id,
        )
    except (OSError, json.JSONDecodeError, StaticV2Error) as exc:
        raise SystemExit(f"static_pair_v2: {exc}") from exc
    text = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
