#!/usr/bin/env python3
"""Select Rosetta pilot identifiers from a metadata-only index."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Mapping, Sequence


EXPERIMENT_ID = "ROSETTA-001"
DATASET_COMMIT = "87567193229336fae36f0da95c4af6a2a46bf90f"
SELECTION_METHOD = "sha256-rank-v1"
FIXED_SEED_SHA256 = "cf11bdacd7729ac263dd7684b27ce1adc33dbf83f268d02cbe087aceb718d5e6"
EXPECTED_COUNTS = {"easy": 40, "medium": 50, "hard": 60}
PILOT_COUNTS = {"easy": 5, "medium": 5, "hard": 5}
DIFFICULTY_ORDER = ("easy", "medium", "hard")


class SelectionError(ValueError):
    """Raised when an index cannot support the predeclared pilot selection."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SelectionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_index(path: Path) -> tuple[list[object], str]:
    raw = path.read_bytes()
    if len(raw) > 256 * 1024:
        raise SelectionError("metadata index exceeds the 256 KiB safety ceiling")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SelectionError("metadata index must be UTF-8") from exc
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise SelectionError(f"invalid index JSON: {exc}") from exc
    if not isinstance(document, list):
        raise SelectionError("index root must be a JSON list")
    return document, hashlib.sha256(raw).hexdigest()


def validate_index(
    document: list[object], *, expected_counts: Mapping[str, int] = EXPECTED_COUNTS
) -> dict[str, list[str]]:
    if set(expected_counts) != set(DIFFICULTY_ORDER) or any(
        type(count) is not int or count <= 0 for count in expected_counts.values()
    ):
        raise SelectionError("expected counts must define positive easy/medium/hard totals")
    expected_total = sum(expected_counts.values())
    if len(document) != expected_total:
        raise SelectionError(f"index must contain exactly {expected_total} objects")

    grouped = {difficulty: [] for difficulty in DIFFICULTY_ORDER}
    observed_ids: set[str] = set()
    for offset, item in enumerate(document):
        row_number = offset + 1
        if not isinstance(item, dict):
            raise SelectionError(f"index row {row_number} must be an object")
        if set(item) != {"question_id", "difficulty"}:
            extra = sorted(set(item) - {"question_id", "difficulty"})
            missing = sorted({"question_id", "difficulty"} - set(item))
            raise SelectionError(
                f"index row {row_number} must contain only question_id/difficulty; "
                f"missing={missing}, extra={extra}"
            )
        question_id = item["question_id"]
        difficulty = item["difficulty"]
        if not isinstance(question_id, str) or not question_id or question_id.strip() != question_id:
            raise SelectionError(f"index row {row_number}: question_id must be a trimmed string")
        if question_id in observed_ids:
            raise SelectionError(f"duplicate question_id: {question_id}")
        if difficulty not in DIFFICULTY_ORDER:
            raise SelectionError(
                f"index row {row_number}: difficulty must be easy, medium, or hard"
            )
        observed_ids.add(question_id)
        grouped[difficulty].append(question_id)

    actual_counts = {difficulty: len(grouped[difficulty]) for difficulty in DIFFICULTY_ORDER}
    if actual_counts != dict(expected_counts):
        raise SelectionError(
            f"difficulty counts must be {dict(expected_counts)}; observed {actual_counts}"
        )
    return grouped


def rank_digest(question_id: str, difficulty: str, *, seed: str = FIXED_SEED_SHA256) -> str:
    if not isinstance(seed, str) or len(seed) != 64 or any(c not in "0123456789abcdef" for c in seed):
        raise SelectionError("selection seed must be 64 lowercase hexadecimal characters")
    payload = f"{seed}\0{difficulty}\0{question_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def select_pilot(
    grouped: Mapping[str, list[str]],
    *,
    requested_counts: Mapping[str, int] = PILOT_COUNTS,
    seed: str = FIXED_SEED_SHA256,
) -> list[dict[str, object]]:
    if set(grouped) != set(DIFFICULTY_ORDER):
        raise SelectionError("grouped index must define exactly easy, medium, and hard")
    if set(requested_counts) != set(DIFFICULTY_ORDER):
        raise SelectionError("requested counts must define exactly easy, medium, and hard")

    selected: list[dict[str, object]] = []
    for difficulty in DIFFICULTY_ORDER:
        count = requested_counts[difficulty]
        if type(count) is not int or count <= 0:
            raise SelectionError("requested counts must be positive integers")
        candidates = grouped[difficulty]
        if len(candidates) < count:
            raise SelectionError(f"not enough {difficulty} identifiers for requested pilot")
        ranked = sorted(
            ((rank_digest(question_id, difficulty, seed=seed), question_id) for question_id in candidates),
            key=lambda pair: (pair[0], pair[1]),
        )
        for digest, question_id in ranked[:count]:
            selected.append(
                {
                    "order": len(selected),
                    "question_id": question_id,
                    "difficulty": difficulty,
                    "rank_sha256": digest,
                }
            )
    return selected


def build_manifest(document: list[object], *, source_index_sha256: str) -> dict[str, object]:
    grouped = validate_index(document)
    selected = select_pilot(grouped)
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "experiment_id": EXPERIMENT_ID,
        "status": "SELECTED_IDS_ONLY_NOT_RUN",
        "source_dataset_commit": DATASET_COMMIT,
        "source_index_sha256": source_index_sha256,
        "selection": {
            "method": SELECTION_METHOD,
            "seed_sha256": FIXED_SEED_SHA256,
            "rank_input": "seed_sha256 + NUL + difficulty + NUL + question_id",
            "population_by_difficulty": dict(EXPECTED_COUNTS),
            "requested_by_difficulty": dict(PILOT_COUNTS),
            "selected": selected,
        },
        "task_material_opened_during_selection": False,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="metadata-only JSON index")
    parser.add_argument("--output", type=Path, required=True, help="new manifest path to create")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.index.resolve(strict=True) == args.output.resolve(strict=False):
            raise SelectionError("output must not replace the input index")
        document, source_hash = load_index(args.index)
        manifest = build_manifest(document, source_index_sha256=source_hash)
        encoded = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        with args.output.open("xb") as handle:
            handle.write(encoded)
    except (OSError, SelectionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    manifest_sha256 = hashlib.sha256(encoded).hexdigest()
    print(
        f"selected 15 metadata-only IDs into {args.output}; "
        f"pilot_manifest_sha256={manifest_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
