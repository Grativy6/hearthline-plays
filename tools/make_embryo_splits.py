#!/usr/bin/env python3
"""Create deterministic leave-one-embryo-out splits from sample names only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Iterable, Sequence


class SplitError(ValueError):
    """Raised when sample names cannot form a safe embryo-level split."""


def canonical_sample(sample: str) -> str:
    normalized = sample.strip().replace("\\", "/")
    if not normalized:
        raise SplitError("sample names must not be empty")
    leaf = PurePosixPath(normalized).name
    if leaf.lower().endswith(".zarr"):
        leaf = leaf[:-5]
    if not leaf:
        raise SplitError(f"sample name has no usable basename: {sample!r}")
    if "_" not in leaf:
        raise SplitError(f"sample name must use {{embryo}}_{{sample}} form: {sample!r}")
    embryo, remainder = leaf.split("_", 1)
    if not embryo or not remainder:
        raise SplitError(f"sample name must have non-empty embryo and sample parts: {sample!r}")
    return leaf


def embryo_id(sample: str) -> str:
    """Derive the embryo prefix before the first underscore in the basename."""

    prefix = canonical_sample(sample).split("_", 1)[0]
    if not prefix:
        raise SplitError(f"sample name has an empty embryo prefix: {sample!r}")
    return prefix


def load_samples_file(path: Path) -> list[str]:
    """Read a small text/JSON name manifest; never inspect referenced samples."""

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SplitError(f"invalid JSON sample manifest: {exc}") from exc
        if isinstance(document, dict):
            document = document.get("samples")
        if not isinstance(document, list) or not all(
            isinstance(item, str) for item in document
        ):
            raise SplitError("JSON sample manifest must be a string list or {samples: [...]}")
        return list(document)
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def build_splits(samples: Iterable[str]) -> list[dict[str, object]]:
    raw = [sample.strip() for sample in samples]
    normalized = [canonical_sample(sample) for sample in raw]
    if not normalized:
        raise SplitError("at least one sample name is required")
    if any(not sample for sample in normalized):
        raise SplitError("sample names must not be empty")
    if len(normalized) != len(set(normalized)):
        raise SplitError("duplicate canonical sample names are not allowed")

    ordered_samples = sorted(normalized)
    grouped: dict[str, list[str]] = {}
    for sample in ordered_samples:
        grouped.setdefault(embryo_id(sample), []).append(sample)

    embryos = sorted(grouped)
    if len(embryos) < 2:
        raise SplitError("leave-one-embryo-out validation requires at least 2 embryos")

    folds: list[dict[str, object]] = []
    for index, held_out in enumerate(embryos):
        validation = list(grouped[held_out])
        training = [
            sample
            for embryo in embryos
            if embryo != held_out
            for sample in grouped[embryo]
        ]
        folds.append(
            {
                "split": index,
                "held_out_embryo": held_out,
                "train": training,
                "test": validation,
            }
        )
    return folds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples", nargs="*", help="sample names (not image paths to read)")
    parser.add_argument(
        "--samples-file",
        type=Path,
        help="UTF-8 line list or JSON manifest containing sample names",
    )
    parser.add_argument("--output", type=Path, help="write JSON here instead of stdout")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    samples = list(args.samples)
    try:
        if args.samples_file is not None:
            samples.extend(load_samples_file(args.samples_file))
        document = build_splits(samples)
    except (OSError, SplitError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    encoded = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.write_text(encoded, encoding="utf-8", newline="\n")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
