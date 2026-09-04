#!/usr/bin/env python3
"""Deterministic, standard-library diagnostics for ARC-style integer grids.

The probe reports direct structural facts only: dimensions, palette counts,
background-relative components, and exact changed cells. Semantic roles such as
"player", "wall", or "goal" belong in a later Static and are not inferred here.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, deque
from pathlib import Path
from typing import Any, Iterable, Sequence

Grid = list[list[int]]


class GridError(ValueError):
    """Raised when an input cannot be interpreted as one rectangular grid."""


def _is_row(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(cell, int) for cell in value)


def _is_grid(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_is_row(row) for row in value)
    )


def extract_last_grid(value: Any) -> Grid:
    """Extract the last rectangular integer grid from common JSON envelopes."""
    if _is_grid(value):
        grid = value
    elif isinstance(value, list) and value and all(_is_grid(item) for item in value):
        grid = value[-1]
    elif isinstance(value, dict):
        for key in ("frame_grids", "frame", "frames", "grid", "last_frame"):
            if key in value:
                return extract_last_grid(value[key])
        if "data" in value:
            return extract_last_grid(value["data"])
        raise GridError("object contains no recognized grid field")
    else:
        raise GridError("input is not a rectangular integer grid or known envelope")

    width = len(grid[0])
    if width == 0 or any(len(row) != width for row in grid):
        raise GridError("grid must be nonempty and rectangular")
    return [[int(cell) for cell in row] for row in grid]


def load_grid(path: str | Path) -> Grid:
    with Path(path).open("r", encoding="utf-8") as handle:
        return extract_last_grid(json.load(handle))


def _bbox(points: Sequence[tuple[int, int]]) -> dict[str, int] | None:
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "x_min": min(xs),
        "y_min": min(ys),
        "x_max": max(xs),
        "y_max": max(ys),
        "width": max(xs) - min(xs) + 1,
        "height": max(ys) - min(ys) + 1,
    }


def _component_summary(points: Sequence[tuple[int, int]]) -> dict[str, Any]:
    size = len(points)
    return {
        "size": size,
        "bbox": _bbox(points),
        "centroid": {
            "x": sum(point[0] for point in points) / size,
            "y": sum(point[1] for point in points) / size,
        },
        "anchor": {
            "x": min(point[0] for point in points),
            "y": min(point[1] for point in points),
        },
    }


def connected_components(grid: Grid, colors: Iterable[int]) -> dict[str, list[dict[str, Any]]]:
    """Return four-neighbor components for the selected colors."""
    height = len(grid)
    width = len(grid[0])
    selected = set(colors)
    visited: set[tuple[int, int]] = set()
    out: dict[str, list[dict[str, Any]]] = {str(color): [] for color in sorted(selected)}

    for y in range(height):
        for x in range(width):
            color = grid[y][x]
            if color not in selected or (x, y) in visited:
                continue
            queue: deque[tuple[int, int]] = deque([(x, y)])
            visited.add((x, y))
            points: list[tuple[int, int]] = []
            while queue:
                cx, cy = queue.popleft()
                points.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if not (0 <= nx < width and 0 <= ny < height):
                        continue
                    if (nx, ny) in visited or grid[ny][nx] != color:
                        continue
                    visited.add((nx, ny))
                    queue.append((nx, ny))
            out[str(color)].append(_component_summary(points))

    for summaries in out.values():
        summaries.sort(
            key=lambda item: (
                -int(item["size"]),
                int(item["anchor"]["y"]),
                int(item["anchor"]["x"]),
            )
        )
    return out


def diff_grids(previous: Grid, current: Grid) -> dict[str, Any]:
    if len(previous) != len(current) or len(previous[0]) != len(current[0]):
        return {
            "comparable": False,
            "reason": "dimension_mismatch",
            "previous_shape": [len(previous), len(previous[0])],
            "current_shape": [len(current), len(current[0])],
        }

    changed: list[tuple[int, int]] = []
    transitions: Counter[tuple[int, int]] = Counter()
    for y, row in enumerate(current):
        for x, cell in enumerate(row):
            before = previous[y][x]
            if before != cell:
                changed.append((x, y))
                transitions[(before, cell)] += 1

    return {
        "comparable": True,
        "changed_cells": len(changed),
        "changed_fraction": len(changed) / (len(current) * len(current[0])),
        "changed_bbox": _bbox(changed),
        "transitions": [
            {"from": before, "to": after, "count": count}
            for (before, after), count in sorted(transitions.items())
        ],
    }


def summarize_grid(
    grid: Grid,
    previous: Grid | None = None,
    background: int | None = None,
) -> dict[str, Any]:
    height = len(grid)
    width = len(grid[0])
    palette = Counter(cell for row in grid for cell in row)
    background_was_explicit = background is not None
    if background is None:
        max_count = max(palette.values())
        background = min(color for color, count in palette.items() if count == max_count)

    non_background_colors = sorted(color for color in palette if color != background)
    result: dict[str, Any] = {
        "shape": {"height": height, "width": width},
        "cell_count": height * width,
        "palette": [
            {"value": color, "count": palette[color], "fraction": palette[color] / (height * width)}
            for color in sorted(palette)
        ],
        "background_candidate": {
            "value": background,
            "basis": "explicit" if background_was_explicit else "most_frequent_then_lowest",
        },
        "non_background_bbox": _bbox(
            [
                (x, y)
                for y, row in enumerate(grid)
                for x, cell in enumerate(row)
                if cell != background
            ]
        ),
        "components_4_neighbor": connected_components(grid, non_background_colors),
    }
    if previous is not None:
        result["diff"] = diff_grids(previous, grid)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON file containing a grid or frame envelope")
    parser.add_argument("--previous", help="optional previous grid/frame JSON")
    parser.add_argument("--background", type=int, help="explicit background value")
    parser.add_argument("--output", help="write JSON to this path instead of stdout")
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        current = load_grid(args.input)
        previous = load_grid(args.previous) if args.previous else None
        result = summarize_grid(current, previous=previous, background=args.background)
    except (OSError, json.JSONDecodeError, GridError, ValueError) as exc:
        raise SystemExit(f"frame_probe: {exc}") from exc

    text = json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":") if args.compact else None,
        indent=None if args.compact else 2,
    ) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
