#!/usr/bin/env python3
"""Reproduce Build 001's primary exact-interpreter bank comparison."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import agent  # noqa: E402
from hearthline_farm.upstream_runner import UpstreamSimulator, starter_agent  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="launch/evaluation-manifest-v1.json")
    parser.add_argument("--set", choices=("development", "unseen", "all"), default="unseen")
    args = parser.parse_args()

    manifest_path = ROOT / args.manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(ROOT / "main.py") != manifest["candidate"]["sha256"]:
        raise SystemExit("main.py does not match the frozen candidate hash")

    seeds: list[int] = []
    if args.set in ("development", "all"):
        seeds += manifest["seed_sets"]["development"]
    if args.set in ("unseen", "all"):
        seeds += manifest["seed_sets"]["unseen"]

    rows = []
    for seed in seeds:
        for seat in (0, 1):
            agents = [agent, starter_agent] if seat == 0 else [starter_agent, agent]
            result = UpstreamSimulator(agents, seed=seed).run()
            hbank = result["final_bank"][seat]
            sbank = result["final_bank"][1 - seat]
            rows.append({
                "seed": seed,
                "seat": seat,
                "hearthline_bank": hbank,
                "starter_bank": sbank,
                "advantage": hbank - sbank,
                "status": result["statuses"][seat],
                "steps": result["steps_processed"],
                "exceptions": result["agent_exceptions"][seat],
                "malformed_actions": result["malformed_actions"][seat],
                "max_action_seconds": result["max_agent_runtime_seconds"][seat],
                "remaining_inventory": result["remaining_inventory"][seat],
                "final_state_sha256": result["canonical_state_hash"],
            })

    advantages = [row["advantage"] for row in rows]
    summary = {
        "set": args.set,
        "games": len(rows),
        "wins": sum(row["advantage"] > 0 for row in rows),
        "losses": sum(row["advantage"] < 0 for row in rows),
        "ties": sum(row["advantage"] == 0 for row in rows),
        "hearthline_bank_median": statistics.median(row["hearthline_bank"] for row in rows),
        "starter_bank_median": statistics.median(row["starter_bank"] for row in rows),
        "median_advantage": statistics.median(advantages),
        "mean_advantage": statistics.mean(advantages),
        "min_advantage": min(advantages),
        "max_advantage": max(advantages),
        "maximum_action_seconds": max(row["max_action_seconds"] for row in rows),
        "all_complete": all(row["status"] == "DONE" and row["steps"] == 719 for row in rows),
        "zero_exceptions": all(row["exceptions"] == 0 for row in rows),
        "zero_malformed_actions": all(row["malformed_actions"] == 0 for row in rows),
        "zero_end_inventory": all(not any(row["remaining_inventory"][part] for part in ("shed", "field", "seeds")) for row in rows),
        "rows": rows,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["wins"] == len(rows) and summary["all_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
