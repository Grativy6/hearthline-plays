#!/usr/bin/env python3
"""Validate Biohub submission CSV structure without invoking an official scorer."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys
from typing import Iterable, Sequence


COLUMNS = [
    "id",
    "dataset",
    "row_type",
    "node_id",
    "t",
    "z",
    "y",
    "x",
    "source_id",
    "target_id",
]
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


class SubmissionError(ValueError):
    """Raised when a submission fails a local structural gate."""


def parse_integral(value: str | None, *, field: str, row_number: int) -> int:
    if value is None or not value.strip():
        raise SubmissionError(f"row {row_number}: {field} is empty")
    try:
        number = Decimal(value.strip())
    except InvalidOperation as exc:
        raise SubmissionError(
            f"row {row_number}: {field} must be a finite integer"
        ) from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise SubmissionError(f"row {row_number}: {field} must be a finite integer")
    integer = int(number)
    if integer < INT64_MIN or integer > INT64_MAX:
        raise SubmissionError(f"row {row_number}: {field} is outside signed Int64 range")
    return integer


def load_expected_datasets(path: Path) -> set[str]:
    """Load an exact expected set from JSON, a dataset-column CSV, or line text."""

    text = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()
    values: Iterable[object]
    if suffix == ".json":
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SubmissionError(f"invalid expected-dataset JSON: {exc}") from exc
        if isinstance(document, dict):
            values = document.get("datasets", [])
        else:
            values = document
        if not isinstance(values, list):
            raise SubmissionError("expected-dataset JSON must be a list or {datasets: [...]}")
    elif suffix == ".csv":
        reader = csv.DictReader(text.splitlines())
        if reader.fieldnames is None or "dataset" not in reader.fieldnames:
            raise SubmissionError("expected-dataset CSV must contain a dataset column")
        values = [row.get("dataset") for row in reader]
    else:
        values = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    if not isinstance(values, list) or not values or not all(
        isinstance(value, str) and value.strip() for value in values
    ):
        raise SubmissionError("expected dataset list must contain non-empty strings")
    normalized = [str(value).strip() for value in values]
    if any(value.lower().endswith(".zarr") for value in normalized):
        raise SubmissionError("expected dataset names must omit the .zarr suffix")
    if len(normalized) != len(set(normalized)):
        raise SubmissionError("expected dataset list contains duplicates")
    return set(normalized)


def validate_rows(
    fieldnames: list[str] | None,
    rows: Iterable[dict[str, str]],
    *,
    expected_datasets: set[str] | None = None,
) -> dict[str, object]:
    if fieldnames != COLUMNS:
        raise SubmissionError(
            "header must exactly match this ordered schema: " + ",".join(COLUMNS)
        )

    nodes: dict[str, dict[int, int]] = {}
    edges: list[tuple[str, int, int, int]] = []
    seen_edges: set[tuple[str, int, int]] = set()
    indegree: dict[tuple[str, int], int] = {}
    outdegree: dict[tuple[str, int], int] = {}
    observed_datasets: set[str] = set()
    row_count = 0
    node_count = 0
    edge_count = 0

    for expected_id, row in enumerate(rows):
        row_count += 1
        csv_row_number = expected_id + 2
        if None in row:
            raise SubmissionError(f"row {csv_row_number}: contains extra CSV fields")
        row_id = parse_integral(row.get("id"), field="id", row_number=csv_row_number)
        if row_id != expected_id:
            raise SubmissionError(
                f"row {csv_row_number}: id must be consecutive from 0; expected {expected_id}"
            )

        raw_dataset = row.get("dataset") or ""
        dataset = raw_dataset.strip()
        if not dataset:
            raise SubmissionError(f"row {csv_row_number}: dataset is empty")
        if dataset != raw_dataset:
            raise SubmissionError(
                f"row {csv_row_number}: dataset must not have surrounding whitespace"
            )
        if dataset.lower().endswith(".zarr"):
            raise SubmissionError(
                f"row {csv_row_number}: dataset must be the test folder name without .zarr"
            )
        observed_datasets.add(dataset)
        raw_row_type = row.get("row_type") or ""
        row_type = raw_row_type.strip()
        if row_type != raw_row_type:
            raise SubmissionError(
                f"row {csv_row_number}: row_type must not have surrounding whitespace"
            )

        parsed = {
            field: parse_integral(row.get(field), field=field, row_number=csv_row_number)
            for field in ("node_id", "t", "z", "y", "x", "source_id", "target_id")
        }

        if row_type == "node":
            for field in ("node_id", "t", "z", "y", "x"):
                if parsed[field] < 0:
                    raise SubmissionError(
                        f"row {csv_row_number}: node {field} must be a non-negative integer"
                    )
            if parsed["source_id"] != -1 or parsed["target_id"] != -1:
                raise SubmissionError(
                    f"row {csv_row_number}: node rows require source_id=target_id=-1"
                )
            dataset_nodes = nodes.setdefault(dataset, {})
            node_id = parsed["node_id"]
            if node_id in dataset_nodes:
                raise SubmissionError(
                    f"row {csv_row_number}: duplicate node_id {node_id} in dataset {dataset}"
                )
            dataset_nodes[node_id] = parsed["t"]
            node_count += 1
        elif row_type == "edge":
            for field in ("node_id", "t", "z", "y", "x"):
                if parsed[field] != -1:
                    raise SubmissionError(
                        f"row {csv_row_number}: edge rows require {field}=-1"
                    )
            source_id = parsed["source_id"]
            target_id = parsed["target_id"]
            if source_id < 0 or target_id < 0:
                raise SubmissionError(
                    f"row {csv_row_number}: edge source_id and target_id must be non-negative"
                )
            if source_id == target_id:
                raise SubmissionError(f"row {csv_row_number}: self-edges are not allowed")
            edge_key = (dataset, source_id, target_id)
            if edge_key in seen_edges:
                raise SubmissionError(f"row {csv_row_number}: duplicate edge {edge_key}")
            seen_edges.add(edge_key)
            source_key = (dataset, source_id)
            target_key = (dataset, target_id)
            outdegree[source_key] = outdegree.get(source_key, 0) + 1
            indegree[target_key] = indegree.get(target_key, 0) + 1
            if outdegree[source_key] > 2:
                raise SubmissionError(
                    f"row {csv_row_number}: node {source_id} in {dataset} has outdegree above 2"
                )
            if indegree[target_key] > 1:
                raise SubmissionError(
                    f"row {csv_row_number}: node {target_id} in {dataset} has indegree above 1"
                )
            edges.append((dataset, source_id, target_id, csv_row_number))
            edge_count += 1
        else:
            raise SubmissionError(
                f"row {csv_row_number}: row_type must be exactly 'node' or 'edge'"
            )

    if row_count == 0:
        raise SubmissionError("submission must contain at least one row")

    for dataset, source_id, target_id, csv_row_number in edges:
        dataset_nodes = nodes.get(dataset, {})
        if source_id not in dataset_nodes or target_id not in dataset_nodes:
            raise SubmissionError(
                f"row {csv_row_number}: edge endpoints must reference nodes in dataset {dataset}"
            )
        source_t = dataset_nodes[source_id]
        target_t = dataset_nodes[target_id]
        if target_t != source_t + 1:
            raise SubmissionError(
                f"row {csv_row_number}: edge must link adjacent frames "
                f"(target t {target_t}, source t {source_t})"
            )

    if expected_datasets is not None and observed_datasets != expected_datasets:
        missing = sorted(expected_datasets - observed_datasets)
        unexpected = sorted(observed_datasets - expected_datasets)
        raise SubmissionError(
            f"dataset set mismatch; missing={missing}, unexpected={unexpected}"
        )

    return {
        "schema_version": "1.0",
        "status": "PASS",
        "scope": "STRUCTURAL_ONLY",
        "official_scorer_executed": False,
        "kaggle_acceptance_proven": False,
        "coordinate_bounds_checked": False,
        "required_filename_checked": False,
        "row_count": row_count,
        "node_count": node_count,
        "edge_count": edge_count,
        "datasets": sorted(observed_datasets),
    }


def validate_submission(
    path: Path,
    *,
    expected_datasets: set[str] | None = None,
    require_filename: bool = True,
) -> dict[str, object]:
    if require_filename and path.name != "submission.csv":
        raise SubmissionError("submission filename must be exactly submission.csv")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        report = validate_rows(reader.fieldnames, reader, expected_datasets=expected_datasets)
    report["required_filename_checked"] = require_filename
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument(
        "--expected-datasets",
        type=Path,
        help="exact expected dataset set (JSON, CSV, or one name per line)",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        expected = (
            load_expected_datasets(args.expected_datasets)
            if args.expected_datasets is not None
            else None
        )
        report = validate_submission(args.submission, expected_datasets=expected)
    except (OSError, SubmissionError) as exc:
        print(f"STRUCTURAL_ONLY FAIL: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            "STRUCTURAL_ONLY PASS: "
            f"{report['row_count']} rows, {report['node_count']} nodes, "
            f"{report['edge_count']} edges, {len(report['datasets'])} datasets; "
            "official scorer not run"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
