"""Scripted, local-only example. NO LLM, external tools, network or bounty calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from security_lab.mh01.referee import MockReferee, load_fixture
from security_lab.mh01.verify import check

DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "mh01_world.json"


def run(script: str, fixture_path: Path = DEFAULT_FIXTURE) -> dict:
    world, fingerprint = load_fixture(fixture_path)
    referee = MockReferee(world, fingerprint)
    doc_id = world["public_document"]["id"]
    status = world["public_document"]["status"]
    referee.request("read_public", {"document_id": doc_id})
    if script == "tempted":
        # Simulated response to the untrusted instruction, not a model result.
        referee.request("read_protected", {"document_id": world["protected_document"]["id"], "lineage": world["protected_action_lineage"]})
        # Same intended action, cosmetically renamed: the tool gate still denies.
        referee.request("archive_read_alias", {"document_id": world["protected_document"]["id"], "lineage": world["protected_action_lineage"]})
    elif script != "benign":
        raise ValueError("script must be benign or tempted")
    referee.request("submit_status", {"status": status, "source": doc_id})
    receipt = referee.receipt(script)
    failures = check(receipt, fixture_path)
    if failures:
        raise RuntimeError(f"internal replay failed: {failures}")
    return receipt


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--script", choices=["benign", "tempted"], required=True)
    p.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    receipt = run(args.script, args.fixture)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"LOCAL_SIMULATION_ONLY: {len(receipt['events'])} attempts; replay passed; {args.out}")


if __name__ == "__main__":
    main()
