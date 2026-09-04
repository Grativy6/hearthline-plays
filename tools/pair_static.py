#!/usr/bin/env python3
"""Create a non-recursive Pair Static from two Hearthline Spark Statics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def claim_map(static: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for claim in static.get("claims", []):
        cid = claim.get("claim_id")
        if not isinstance(cid, str) or not cid:
            raise ValueError("every claim requires a nonempty claim_id")
        if cid in out:
            raise ValueError(f"duplicate claim_id: {cid}")
        out[cid] = claim
    return out


def build_pair(a: dict[str, Any], b: dict[str, Any], pair_id: str) -> dict[str, Any]:
    if a.get("schema") != "hearthline.spark-static.v1" or b.get("schema") != "hearthline.spark-static.v1":
        raise ValueError("both inputs must be hearthline.spark-static.v1")
    if a.get("task_id") != b.get("task_id"):
        raise ValueError("source Statics must address the same task_id")
    if a.get("static_id") == b.get("static_id"):
        raise ValueError("source Statics must have distinct identities")

    am = claim_map(a)
    bm = claim_map(b)
    agreements: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    unique: list[dict[str, Any]] = []
    estimates: list[dict[str, Any]] = []

    for cid in sorted(set(am) | set(bm)):
        ca, cb = am.get(cid), bm.get(cid)
        if ca is None:
            unique.append({"claim_id": cid, "source": b["static_id"], "claim": cb})
            continue
        if cb is None:
            unique.append({"claim_id": cid, "source": a["static_id"], "claim": ca})
            continue

        same_value = canonical(ca.get("value")) == canonical(cb.get("value"))
        if same_value:
            agreements.append({
                "claim_id": cid,
                "value": ca.get("value"),
                "source_claims": [a["static_id"], b["static_id"]],
                "dependency_warning": "Agreement does not establish independence."
            })
        else:
            disagreements.append({
                "claim_id": cid,
                "a": {"static_id": a["static_id"], "value": ca.get("value"), "confidence": ca.get("confidence")},
                "b": {"static_id": b["static_id"], "value": cb.get("value"), "confidence": cb.get("confidence")}
            })

        for source, claim in ((a["static_id"], ca), (b["static_id"], cb)):
            if claim.get("confidence") is not None:
                estimates.append({
                    "claim_id": cid,
                    "source_static": source,
                    "estimate": claim.get("confidence"),
                    "conditioning_account": {
                        "assumptions": claim.get("assumptions", []),
                        "evidence_refs": claim.get("evidence_refs", [])
                    }
                })

    shared_dependencies = sorted(set(a.get("dependencies", [])) & set(b.get("dependencies", [])))

    tests = []
    for src in (a, b):
        for test in src.get("proposed_tests", []):
            tests.append((src["static_id"], test))
    proposed = None
    if disagreements and tests:
        source, test = tests[0]
        proposed = {
            "source_static": source,
            "test": test,
            "selection_status": "FIRST_DECLARED_CANDIDATE_NOT_AUTHORIZED"
        }

    seam = disagreements[0]["claim_id"] if disagreements else None
    residuals = sorted(set(a.get("residuals", []) + b.get("residuals", [])))
    if shared_dependencies:
        residuals.append("Source Statics share dependencies; agreement is not independent corroboration.")
    if disagreements and proposed is None:
        residuals.append("Material disagreement exists without a declared discriminating test.")

    return {
        "schema": "hearthline.pair-static.v1",
        "pair_static_id": pair_id,
        "task_id": a["task_id"],
        "source_statics": [a["static_id"], b["static_id"]],
        "agreements": agreements,
        "disagreements": disagreements,
        "unique_claims": unique,
        "shared_dependencies": shared_dependencies,
        "estimates": estimates,
        "pooling_rule": "NONE",
        "load_bearing_seam": seam,
        "proposed_discriminating_test": proposed,
        "residuals": residuals,
        "status": "UNRESOLVED" if disagreements else "RETURNED"
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("static_a", type=Path)
    parser.add_argument("static_b", type=Path)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = build_pair(load(args.static_a), load(args.static_b), args.pair_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
