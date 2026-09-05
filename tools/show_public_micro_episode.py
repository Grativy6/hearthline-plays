#!/usr/bin/env python3
"""Show one view from the fixed, repo-local public micro-learning deck.

The tool is read-only and offline. It never calls a model or evaluator, runs
candidate code, or accepts an alternate deck path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

DECK_PATH = (
    Path(__file__).resolve().parents[1]
    / "playground"
    / "micro"
    / "orientation-deck.v1.json"
)
MAX_DECK_BYTES = 64 * 1024
EXPECTED_DECK_SHA256 = "b88a0bc011378e69449315384e675edc263427457b39c8606d9c994f67a0920c"
ROOT_KEYS = {
    "schema_version",
    "deck_id",
    "title",
    "origin",
    "classification",
    "upstream_material",
    "use",
    "episodes",
    "reflection_template",
    "claim_ceiling",
}
EPISODE_KEYS = {"episode_id", "lesson", "learner_view", "coach_view"}


class DeckError(ValueError):
    """Raised when the fixed deck or requested view is invalid."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DeckError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_deck() -> dict[str, object]:
    """Load only the fixed public orientation deck."""

    try:
        raw = DECK_PATH.read_bytes()
    except OSError as exc:
        raise DeckError(f"cannot read fixed public deck: {exc}") from exc
    if len(raw) > MAX_DECK_BYTES:
        raise DeckError("fixed public deck exceeds the 64 KiB safety ceiling")
    if hashlib.sha256(raw).hexdigest() != EXPECTED_DECK_SHA256:
        raise DeckError("fixed public deck digest mismatch")
    try:
        document = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeckError(f"invalid fixed public deck JSON: {exc}") from exc
    if not isinstance(document, dict) or set(document) != ROOT_KEYS:
        raise DeckError("fixed public deck root schema drift")
    if document["schema_version"] != "hearthline-public-micro.v1":
        raise DeckError("fixed public deck schema version mismatch")
    if document["classification"] != "PRACTICE_NOT_BENCHMARK":
        raise DeckError("fixed public deck classification mismatch")
    episodes = document["episodes"]
    if not isinstance(episodes, list) or not episodes:
        raise DeckError("fixed public deck must contain episodes")
    identifiers: list[str] = []
    for position, episode in enumerate(episodes):
        if not isinstance(episode, dict) or set(episode) != EPISODE_KEYS:
            raise DeckError(f"fixed public deck episode {position} schema drift")
        episode_id = episode["episode_id"]
        if not isinstance(episode_id, str) or not episode_id:
            raise DeckError(f"fixed public deck episode {position} has no ID")
        if not isinstance(episode["learner_view"], dict):
            raise DeckError(f"fixed public deck episode {episode_id} has no learner view")
        if not isinstance(episode["coach_view"], dict):
            raise DeckError(f"fixed public deck episode {episode_id} has no coach view")
        identifiers.append(episode_id)
    if len(identifiers) != len(set(identifiers)):
        raise DeckError("fixed public deck contains duplicate episode IDs")
    return document


def render_view(
    deck: dict[str, object],
    episode_id: str | None,
    *,
    coach_view: bool = False,
    answer_sealed: bool = False,
) -> dict[str, object]:
    """Return an index, learner view, or explicitly unlocked coach view."""

    episodes = deck["episodes"]
    if episode_id is None:
        if coach_view or answer_sealed:
            raise DeckError("an episode ID is required for view flags")
        return {
            "deck_id": deck["deck_id"],
            "episode_ids": [episode["episode_id"] for episode in episodes],
            "view": "index",
        }
    match = next(
        (episode for episode in episodes if episode["episode_id"] == episode_id),
        None,
    )
    if match is None:
        raise DeckError(f"unknown episode ID: {episode_id}")
    if coach_view and not answer_sealed:
        raise DeckError("--coach-view requires explicit --answer-sealed")
    if answer_sealed and not coach_view:
        raise DeckError("--answer-sealed is only valid with --coach-view")
    selected_view = "coach_view" if coach_view else "learner_view"
    result = {
        "deck_id": deck["deck_id"],
        "episode_id": match["episode_id"],
        "lesson": match["lesson"],
        "view": selected_view,
        selected_view: match[selected_view],
    }
    if coach_view:
        result["answer_sealed"] = True
    return result


def deterministic_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode_id", nargs="?", help="opaque public micro-episode ID")
    parser.add_argument("--coach-view", action="store_true")
    parser.add_argument("--answer-sealed", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output = render_view(
            load_deck(),
            args.episode_id,
            coach_view=args.coach_view,
            answer_sealed=args.answer_sealed,
        )
    except DeckError as exc:
        print(deterministic_json({"error": str(exc)}), file=sys.stderr)
        return 1
    print(deterministic_json(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
