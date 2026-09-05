#!/usr/bin/env python3
"""Create one offline public-playground learning-session scaffold.

The generator never reads benchmark data, uses the network, calls a model or
evaluator, or executes candidate code. Output uses exclusive creation and
refuses to overwrite an existing file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath

try:
    from tools.validate_public_learning_session import (
        CLAIM_CEILING,
        EXPERIMENT_ID,
        MICRO_DECK_SHA256,
        MICRO_EPISODE_IDS,
        MODES,
        OPAQUE_ID,
        SCHEMA_VERSION,
        SOURCES,
        STATUS,
        SessionError,
        validate_session,
    )
except ModuleNotFoundError:  # Direct execution from the tools directory.
    from validate_public_learning_session import (  # type: ignore[no-redef]
        CLAIM_CEILING,
        EXPERIMENT_ID,
        MICRO_DECK_SHA256,
        MICRO_EPISODE_IDS,
        MODES,
        OPAQUE_ID,
        SCHEMA_VERSION,
        SOURCES,
        STATUS,
        SessionError,
        validate_session,
    )


class CreationError(ValueError):
    """Raised when a session scaffold cannot be safely created."""


def _is_e_drive_path(value: str) -> bool:
    windows_drive = PureWindowsPath(value).drive.rstrip(":").casefold()
    normalized = value.replace("\\", "/").casefold().rstrip("/")
    return windows_drive == "e" or normalized == "/mnt/e" or normalized.startswith("/mnt/e/")


def validate_output_root(value: str, *, platform_name: str | None = None) -> Path:
    """Resolve an explicit absolute root and reject Windows E: destinations."""

    del platform_name  # Compatibility seam for cross-platform policy tests.
    if _is_e_drive_path(value):
        raise CreationError("E: destinations are forbidden for public-learning sessions")
    root = Path(value)
    if not root.is_absolute():
        raise CreationError("--output-root must be an explicit absolute path")
    resolved = root.resolve(strict=False)
    if os.name == "nt" and _is_e_drive_path(str(resolved)):
        raise CreationError("E: destinations are forbidden for public-learning sessions")
    return resolved


def build_session(args: argparse.Namespace, *, created_at_utc: str | None = None) -> dict[str, object]:
    if OPAQUE_ID.fullmatch(args.session_id) is None:
        raise CreationError(
            "--session-id must be opaque and use only letters, numbers, dot, underscore, or hyphen"
        )
    if OPAQUE_ID.fullmatch(args.problem_id) is None:
        raise CreationError(
            "--problem-id must be opaque and use only letters, numbers, dot, underscore, or hyphen"
        )
    if args.mode == "micro_fixture" and args.problem_id not in MICRO_EPISODE_IDS:
        raise CreationError("micro_fixture --problem-id must name an orientation-deck episode")
    if type(args.model_calls) is not int or args.model_calls not in {0, 1}:
        raise CreationError("the public-playground future model-call ceiling is one")
    if args.model_calls and not args.future_plan:
        raise CreationError(
            "nonzero budgets require --future-plan to describe a future-only, not-run plan"
        )
    source = dict(SOURCES[args.mode])
    source_is_public = args.mode != "micro_fixture"
    timestamp = created_at_utc or datetime.now(UTC).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "session_mode": args.mode,
        "source": source,
        "exercise": {
            "session_id": args.session_id,
            "problem_id": args.problem_id,
            "learning_goal": args.learning_goal,
        },
        "budgets": {
            "model_calls": args.model_calls,
            "evaluator_runs": 0,
            "candidate_code_executions": 0,
        },
        "activity": {
            "model_calls_completed": 0,
            "evaluator_runs_completed": 0,
            "candidate_code_executions_completed": 0,
        },
        "future_plan": {
            "status": "FUTURE_ONLY_NOT_RUN" if args.future_plan else "NO_RUN_PLANNED",
            "description": args.future_plan,
        },
        "learning_trace": {
            "observations": [],
            "hypotheses": [],
            "requests": [],
            "reformulations": [],
            "reflections": [],
            "evidence_ids_used": [],
            "assumptions_withheld": [],
            "receipt_bindings": {
                "verification": "RECEIPTS_UNBOUND",
                "source_sha256": MICRO_DECK_SHA256 if args.mode == "micro_fixture" else None,
                "ledger_receipt_sha256": None,
                "reset_receipt_sha256": None,
            },
            "episode_control": {
                "learner_view_opened": False,
                "answer_sealed_before_coach_view": False,
                "coach_view_opened": False,
                "state_reset_confirmed": False,
            },
            "score_or_match": None,
            "what_changed_next_time": None,
        },
        "provenance": {
            "created_at_utc": timestamp,
            "created_by": "tools/new_public_learning_session.py",
            "source_is_public": source_is_public,
            "network_accessed_by_generator": False,
            "model_invoked_by_generator": False,
            "evaluator_invoked_by_generator": False,
            "candidate_code_executed_by_generator": False,
        },
        "formal_pilot": {"experiment_id": EXPERIMENT_ID, "consumed": False},
        "claim_ceiling": CLAIM_CEILING,
    }
    try:
        validate_session(document)
    except SessionError as exc:
        raise CreationError(str(exc)) from exc
    return document


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, help="absolute non-E: output directory")
    parser.add_argument("--mode", required=True, choices=sorted(MODES))
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--learning-goal", required=True)
    parser.add_argument("--model-calls", type=int, default=0)
    parser.add_argument(
        "--future-plan",
        help="explicit description required when any future budget is nonzero",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        output_root = validate_output_root(args.output_root)
        document = build_session(args)
        output_root.mkdir(parents=True, exist_ok=True)
        output_path = output_root / f"{args.session_id}.public-learning-session.v1.json"
        payload = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        with output_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    except (CreationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"created {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
