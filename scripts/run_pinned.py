#!/usr/bin/env python3
"""Run one Hearthline-versus-starter season through the pinned interpreter."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import agent  # noqa: E402
from hearthline_farm.upstream_runner import UpstreamSimulator, starter_agent  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--seat", type=int, choices=(0, 1), default=0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    agents = [agent, starter_agent] if args.seat == 0 else [starter_agent, agent]
    sim = UpstreamSimulator(agents, seed=args.seed)
    result = sim.run()
    summary = {
        "seed": args.seed,
        "hearthline_seat": args.seat,
        "hearthline_bank": result["final_bank"][args.seat],
        "starter_bank": result["final_bank"][1 - args.seat],
        "advantage": result["final_bank"][args.seat] - result["final_bank"][1 - args.seat],
        "steps_processed": result["steps_processed"],
        "statuses": result["statuses"],
        "rewards": result["rewards"],
        "remaining_inventory": result["remaining_inventory"][args.seat],
        "agent_exceptions": result["agent_exceptions"][args.seat],
        "malformed_actions": result["malformed_actions"][args.seat],
        "maximum_action_seconds": result["max_agent_runtime_seconds"][args.seat],
        "final_state_sha256": result["canonical_state_hash"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.out:
        out = ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"summary": summary, "actions": sim.actions}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
