#!/usr/bin/env python3
"""Build one deterministic Morrow proposal from a frozen ready-only view.

The program reads one bounded JSON document from standard input and writes one
proposal to standard output. It has no filesystem, network, clock, randomness,
subprocess, persistence, heartbeat, local-module, Thulia, custody, carry, or
admission surface. The controller privately binds the opaque invocation token
to its full snapshot and remains responsible for eligibility and admission.
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any


INPUT_SCHEMA = "hearthline-plays.morrow-scheduling-view.v1"
OUTPUT_SCHEMA = "hearthline-plays.morrow-proposal.v1"
POLICY_REF = "STABLE_EFFECTIVE_PRIORITY_THEN_APPROVED_COST_THEN_ARRIVAL_V2"
PRIORITY_RANKS = frozenset(range(4))
MAX_READY_ITEMS = 256
MAX_INPUT_CHARACTERS = 1_000_000
MAX_OPAQUE_TOKEN_CHARACTERS = 256
MAX_OVERTAKES = 1_000_000
MAX_CONTROLLER_APPROVED_PROCESSING_COST = 1_000_000


class MorrowInputError(ValueError):
    """Raised before any proposal exists when the frozen view is malformed."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MorrowInputError("duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise MorrowInputError(f"non-finite JSON number: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if parsed in (float("inf"), float("-inf")):
        _reject_nonfinite(value)
    return parsed


def loads_strict_json(raw: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        )
    except (json.JSONDecodeError, MorrowInputError, ValueError, RecursionError, OverflowError) as exc:
        if isinstance(exc, MorrowInputError):
            raise
        raise MorrowInputError(f"invalid JSON: {exc}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MorrowInputError(message)


def _require_exact_keys(value: Any, expected: list[str], label: str) -> None:
    _require(isinstance(value, dict), f"{label}: expected object")
    missing = sorted(set(expected) - set(value))
    extra = sorted(set(value) - set(expected))
    _require(not missing and not extra, f"{label}: missing={missing}, extra={extra}")


def _is_safe_opaque_token(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= MAX_OPAQUE_TOKEN_CHARACTERS
        and value.isascii()
        and all(character.isalnum() or character in "_.:-" for character in value)
    )


def _opaque_token_key(value: str) -> str:
    return value.casefold()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def scheduling_view_projection(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": document["schema"],
        "status": document["status"],
        "invocation_cut_binding": document["invocation_cut_binding"],
        "policy_ref": document["policy_ref"],
        "maximum_overtakes": document["maximum_overtakes"],
        "ready_scheduling_view": document["ready_scheduling_view"],
    }


def propose(document: Any) -> dict[str, Any]:
    """Return the pure proposal for one controller-frozen ready-only view."""
    top_keys = [
        "schema",
        "status",
        "invocation_cut_binding",
        "policy_ref",
        "maximum_overtakes",
        "ready_scheduling_view",
    ]
    _require_exact_keys(document, top_keys, "Morrow input")
    _require(document["schema"] == INPUT_SCHEMA, "Morrow input: schema")
    _require(
        document["status"] == "CONTROLLER_FROZEN_READY_ONLY_VIEW",
        "Morrow input: controller-frozen status",
    )
    token = document["invocation_cut_binding"]
    _require(_is_safe_opaque_token(token), "Morrow input: safe opaque invocation cut binding")
    _require(document["policy_ref"] == POLICY_REF, "Morrow input: policy")
    maximum_overtakes = document["maximum_overtakes"]
    _require(
        type(maximum_overtakes) is int
        and 1 <= maximum_overtakes <= MAX_OVERTAKES,
        "Morrow input: bounded maximum overtakes",
    )
    item_keys = [
        "opaque_queue_item_binding",
        "ready_arrival_rank",
        "effective_priority_rank",
        "controller_approved_processing_cost",
        "overtake_count",
    ]
    items = document["ready_scheduling_view"]
    _require(
        isinstance(items, list) and 1 <= len(items) <= MAX_READY_ITEMS,
        "Morrow input: bounded nonempty ready array",
    )
    bindings: set[str] = set()
    arrival_ranks: set[int] = set()
    for index, item in enumerate(items, start=1):
        _require_exact_keys(item, item_keys, f"Morrow scheduling item {index}")
        binding = item["opaque_queue_item_binding"]
        _require(
            _is_safe_opaque_token(binding)
            and _opaque_token_key(binding)
            not in {_opaque_token_key(existing) for existing in bindings},
            f"Morrow scheduling item {index}: unique opaque binding",
        )
        bindings.add(binding)
        arrival = item["ready_arrival_rank"]
        _require(
            type(arrival) is int and arrival >= 1 and arrival not in arrival_ranks,
            f"Morrow scheduling item {index}: unique ready-arrival rank",
        )
        arrival_ranks.add(arrival)
        _require(
            type(item["effective_priority_rank"]) is int
            and item["effective_priority_rank"] in PRIORITY_RANKS,
            f"Morrow scheduling item {index}: effective priority rank",
        )
        cost = item["controller_approved_processing_cost"]
        _require(
            type(cost) is int
            and 1 <= cost <= MAX_CONTROLLER_APPROVED_PROCESSING_COST,
            f"Morrow scheduling item {index}: bounded processing cost",
        )
        overtake_count = item["overtake_count"]
        _require(
            type(overtake_count) is int and 0 <= overtake_count <= maximum_overtakes,
            f"Morrow scheduling item {index}: overtake count",
        )
    _require(
        [item["ready_arrival_rank"] for item in items]
        == list(range(1, len(items) + 1)),
        "Morrow input: ready-arrival ranks must be canonical, contiguous, and ordered",
    )
    _require(
        _opaque_token_key(token)
        not in {_opaque_token_key(binding) for binding in bindings},
        "Morrow input: cut binding must not alias an item binding",
    )

    due = sorted(
        (item for item in items if item["overtake_count"] >= maximum_overtakes),
        key=lambda item: item["ready_arrival_rank"],
    )
    not_due = sorted(
        (item for item in items if item["overtake_count"] < maximum_overtakes),
        key=lambda item: (
            item["effective_priority_rank"],
            item["controller_approved_processing_cost"],
            item["ready_arrival_rank"],
        ),
    )
    order = [item["opaque_queue_item_binding"] for item in [*due, *not_due]]
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "PROPOSAL_ONLY_NO_ADMISSION",
        "invocation_cut_binding": token,
        "scheduling_view_sha256": canonical_sha256(scheduling_view_projection(document)),
        "policy_ref": POLICY_REF,
        "ready_order": order,
        "reason_codes": [
            "MAXIMUM_OVERTAKES_DUE_OLDEST_FIRST",
            "PRIORITY_RANK_ASCENDING_ZERO_FIRST",
            "CONTROLLER_APPROVED_COST_ASCENDING_WITHIN_PRIORITY",
            "READY_ARRIVAL_RANK_ASCENDING_TIE_BREAK",
        ],
        "pure_metadata_only": True,
        "deterministic_stateless": True,
        "persistent_state_ref": None,
        "external_effect_count": 0,
    }


def main() -> int:
    try:
        raw = sys.stdin.read(MAX_INPUT_CHARACTERS + 1)
        if len(raw) > MAX_INPUT_CHARACTERS:
            raise MorrowInputError("input exceeds the bounded character limit")
        proposal = propose(loads_strict_json(raw))
    except MorrowInputError as exc:
        sys.stderr.write(f"MORROW_INPUT_REJECTED: {exc}\n")
        return 2
    sys.stdout.write(json.dumps(proposal, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
