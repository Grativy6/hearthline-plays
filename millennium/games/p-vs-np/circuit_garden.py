#!/usr/bin/env python3
"""Enumerate the exact two-input NAND circuit garden.

This is a finite circuit-complexity game, not evidence that P differs from NP.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from itertools import combinations_with_replacement
from pathlib import Path


SCHEMA = "hearthline-plays.circuit-garden-certificate.v1"
ASSIGNMENTS = ("00", "01", "10", "11")
INPUT_VALUES = (0b1100, 0b1010)
MASK = 0b1111
FUNCTION_NAMES = {
    0x0: "false",
    0x1: "nor",
    0x2: "not_x0_and_x1",
    0x3: "not_x0",
    0x4: "x0_and_not_x1",
    0x5: "not_x1",
    0x6: "xor",
    0x7: "nand",
    0x8: "and",
    0x9: "xnor",
    0xA: "x1",
    0xB: "x0_implies_x1",
    0xC: "x0",
    0xD: "x1_implies_x0",
    0xE: "or",
    0xF: "true",
}


class GardenError(RuntimeError):
    pass


def outputs_by_assignment(mask: int) -> str:
    return "".join(str((mask >> bit) & 1) for bit in range(4))


def signal_name(index: int) -> str:
    return f"x{index}" if index < 2 else f"g{index - 2}"


def witness(gates: tuple[tuple[int, int], ...], output_mask: int) -> dict:
    return {
        "output": signal_name(len(gates) + 1) if gates else FUNCTION_NAMES[output_mask],
        "gates": [
            {
                "out": f"g{gate_index}",
                "left": signal_name(left),
                "right": signal_name(right),
            }
            for gate_index, (left, right) in enumerate(gates)
        ],
    }


def enumerate_garden() -> tuple[dict[int, tuple[int, tuple[tuple[int, int], ...]]], dict[str, int]]:
    found: dict[int, tuple[int, tuple[tuple[int, int], ...]]] = {
        INPUT_VALUES[0]: (0, ()),
        INPUT_VALUES[1]: (0, ()),
    }
    frontier: list[tuple[tuple[tuple[int, int], ...], tuple[int, ...]]] = [
        ((), INPUT_VALUES)
    ]
    counts = {"0": 1}

    for gate_count in range(1, 16):
        next_frontier = []
        for gates, values in frontier:
            for left, right in combinations_with_replacement(range(len(values)), 2):
                value = (~(values[left] & values[right])) & MASK
                next_gates = gates + ((left, right),)
                next_values = values + (value,)
                next_frontier.append((next_gates, next_values))
                found.setdefault(value, (gate_count, next_gates))
        frontier = next_frontier
        counts[str(gate_count)] = len(frontier)
        if len(found) == 16:
            return found, counts
    raise GardenError("all sixteen functions were not reached within the search bound")


def build_certificate() -> dict:
    found, counts = enumerate_garden()
    results = []
    for mask in range(16):
        gate_count, gates = found[mask]
        results.append(
            {
                "mask_hex": f"{mask:x}",
                "name": FUNCTION_NAMES[mask],
                "outputs_for_00_01_10_11": outputs_by_assignment(mask),
                "minimum_nand_gates": gate_count,
                "witness": witness(gates, mask),
            }
        )

    core = {
        "schema": SCHEMA,
        "game_id": "PNP-CIRCUIT-GARDEN-N2-NAND-001",
        "claim_state": "certified_finite",
        "claim": "For each Boolean function of two inputs, the listed number is the exact minimum number of two-input NAND gates in the declared circuit model.",
        "not_claimed": [
            "P equals NP",
            "P differs from NP",
            "an asymptotic circuit lower bound",
            "a lower bound in any circuit model other than the one declared here"
        ],
        "model": {
            "inputs": ["x0", "x1"],
            "assignment_order": list(ASSIGNMENTS),
            "truth_table_encoding": "bit i of mask is the output for assignment_order[i]",
            "gate": "NAND(left, right) = NOT(left AND right)",
            "gate_fan_in": 2,
            "fan_out": "unbounded",
            "repeated_operand_allowed": True,
            "constants_free": False,
            "negated_inputs_free": False,
            "output": "either a primary input for size zero or the final gate",
            "gate_cost": 1
        },
        "enumeration": {
            "method": "Enumerate every topologically ordered gate sequence. For each gate, enumerate every unordered pair with repetition from the primary inputs and earlier gates.",
            "complete_for_model": True,
            "sequences_by_exact_gate_count": counts,
            "first_gate_count_reaching_all_16_functions": max(
                result[0] for result in found.values()
            ),
            "minimality_basis": "A function is absent from every complete sequence enumeration at smaller gate counts and has the supplied witness at its listed count."
        },
        "results": results,
    }
    canonical_core = json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        **core,
        "certificate_core_sha256": hashlib.sha256(canonical_core).hexdigest(),
    }


def verify_certificate(path: Path) -> None:
    try:
        supplied = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GardenError(f"cannot read certificate: {exc}") from exc
    expected = build_certificate()
    if supplied != expected:
        raise GardenError("certificate differs from deterministic exhaustive enumeration")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path, help="verify an existing certificate")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verify is not None:
        verify_certificate(args.verify)
        print("Circuit garden certificate: PASS")
    else:
        print(json.dumps(build_certificate(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GardenError as exc:
        print(f"Circuit garden: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
