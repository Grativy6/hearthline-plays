#!/usr/bin/env python3
"""Reject every legacy public-orientation request before any adapter call.

This module deliberately contains no ARC client, network import, credential
reader, action dispatcher, or dynamic plugin loader. The historical request
documents remain provenance only even though their original status field says
``AUTHORIZED``; the controlling grant is expired and spent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable


ARCHIVED_REQUEST_IDS = {f"ORIENT-{index:04d}" for index in range(1, 6)}


class ClosedOrientationArchive(RuntimeError):
    """Raised unconditionally for any legacy request."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClosedOrientationArchive(f"duplicate JSON key in archived request: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ClosedOrientationArchive(f"non-finite JSON number in archived request: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if parsed == float("inf") or parsed == float("-inf"):
        _reject_nonfinite(value)
    return parsed


def reject_archived_request(
    path: Path,
    effect_adapter: Callable[[dict[str, Any]], object] | None = None,
) -> None:
    """Inspect identity for the rejection receipt, then stop before adapter use."""
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClosedOrientationArchive(f"archived request unreadable; fail closed: {path.name}") from exc
    request_id = data.get("request_id") if isinstance(data, dict) else None
    if request_id not in ARCHIVED_REQUEST_IDS:
        raise ClosedOrientationArchive("request is not a recognized legacy archive item; fail closed")
    # `effect_adapter` is intentionally never called. It exists only so tests
    # can prove the boundary with a trap adapter.
    del effect_adapter
    raise ClosedOrientationArchive(
        f"{request_id} is CLOSED_EXPIRED_AND_SPENT; create a separately reviewed successor before any contact"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    try:
        reject_archived_request(args.request)
    except ClosedOrientationArchive as exc:
        print(f"REJECTED_BEFORE_CONTACT {exc}")
        return 2
    raise AssertionError("closed orientation request unexpectedly passed")


if __name__ == "__main__":
    raise SystemExit(main())
