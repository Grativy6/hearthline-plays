from __future__ import annotations

import copy
import csv
from io import StringIO
import json
import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import validate_submission as subject  # noqa: E402


class ValidateSubmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = ROOT / "fixtures" / "submission.valid.synthetic.csv"
        with cls.fixture.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            cls.fieldnames = reader.fieldnames
            cls.rows = list(reader)

    def validate(self, rows: list[dict[str, str]]) -> dict[str, object]:
        return subject.validate_rows(list(self.fieldnames or []), rows)

    def changed(self, row_index: int, field: str, value: str) -> list[dict[str, str]]:
        rows = copy.deepcopy(self.rows)
        rows[row_index][field] = value
        return rows

    def test_valid_fixture_passes_as_structural_only(self) -> None:
        expected = subject.load_expected_datasets(ROOT / "fixtures" / "expected-datasets.json")
        report = subject.validate_submission(
            self.fixture, expected_datasets=expected, require_filename=False
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["scope"], "STRUCTURAL_ONLY")
        self.assertEqual(report["node_count"], 4)
        self.assertEqual(report["edge_count"], 2)
        self.assertFalse(report["official_scorer_executed"])
        self.assertFalse(report["coordinate_bounds_checked"])
        self.assertFalse(report["required_filename_checked"])

    def test_file_validator_requires_exact_submission_filename(self) -> None:
        with self.assertRaisesRegex(subject.SubmissionError, "exactly submission.csv"):
            subject.validate_submission(self.fixture)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "submission.csv"
            target.write_bytes(self.fixture.read_bytes())
            report = subject.validate_submission(target)
            self.assertTrue(report["required_filename_checked"])

    def test_header_must_match_exact_order(self) -> None:
        wrong = list(subject.COLUMNS)
        wrong[0], wrong[1] = wrong[1], wrong[0]
        with self.assertRaisesRegex(subject.SubmissionError, "header must exactly"):
            subject.validate_rows(wrong, self.rows)

    def test_id_must_be_consecutive_zero_based(self) -> None:
        with self.assertRaisesRegex(subject.SubmissionError, "consecutive from 0"):
            self.validate(self.changed(1, "id", "9"))

    def test_integral_fields_reject_nonfinite_fractional_and_out_of_int64(self) -> None:
        for value in ("NaN", "Infinity", "1.25", str(2**63)):
            with self.subTest(value=value), self.assertRaises(subject.SubmissionError):
                self.validate(self.changed(0, "x", value))

    def test_node_and_edge_sentinel_rules(self) -> None:
        with self.assertRaisesRegex(subject.SubmissionError, "source_id=target_id=-1"):
            self.validate(self.changed(0, "source_id", "0"))
        with self.assertRaisesRegex(subject.SubmissionError, "edge rows require z=-1"):
            self.validate(self.changed(3, "z", "0"))

    def test_node_ids_are_unique_within_each_dataset(self) -> None:
        with self.assertRaisesRegex(subject.SubmissionError, "duplicate node_id"):
            self.validate(self.changed(1, "node_id", "1"))

    def test_edges_must_reference_nodes_in_same_dataset(self) -> None:
        with self.assertRaisesRegex(subject.SubmissionError, "reference nodes in dataset"):
            self.validate(self.changed(3, "target_id", "10"))

    def test_edges_must_link_exactly_adjacent_frames(self) -> None:
        with self.assertRaisesRegex(subject.SubmissionError, "adjacent frames"):
            self.validate(self.changed(1, "t", "2"))
        with self.assertRaisesRegex(subject.SubmissionError, "adjacent frames"):
            rows = self.changed(0, "t", "2")
            self.validate(rows)

    def test_rejects_self_and_duplicate_edges(self) -> None:
        with self.assertRaisesRegex(subject.SubmissionError, "self-edges"):
            self.validate(self.changed(3, "target_id", "1"))
        rows = copy.deepcopy(self.rows)
        duplicate = dict(rows[3])
        duplicate["id"] = str(len(rows))
        rows.append(duplicate)
        with self.assertRaisesRegex(subject.SubmissionError, "duplicate edge"):
            self.validate(rows)

    def test_enforces_maximum_indegree_one(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows.append(
            {
                "id": "6", "dataset": "embryoA_fov01", "row_type": "node",
                "node_id": "4", "t": "0", "z": "1", "y": "1", "x": "1",
                "source_id": "-1", "target_id": "-1",
            }
        )
        rows.append(
            {
                "id": "7", "dataset": "embryoA_fov01", "row_type": "edge",
                "node_id": "-1", "t": "-1", "z": "-1", "y": "-1", "x": "-1",
                "source_id": "4", "target_id": "2",
            }
        )
        with self.assertRaisesRegex(subject.SubmissionError, "indegree above 1"):
            self.validate(rows)

    def test_enforces_maximum_outdegree_two(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows.append(
            {
                "id": "6", "dataset": "embryoA_fov01", "row_type": "node",
                "node_id": "4", "t": "1", "z": "1", "y": "1", "x": "1",
                "source_id": "-1", "target_id": "-1",
            }
        )
        rows.append(
            {
                "id": "7", "dataset": "embryoA_fov01", "row_type": "edge",
                "node_id": "-1", "t": "-1", "z": "-1", "y": "-1", "x": "-1",
                "source_id": "1", "target_id": "4",
            }
        )
        with self.assertRaisesRegex(subject.SubmissionError, "outdegree above 2"):
            self.validate(rows)

    def test_dataset_set_is_exact_when_expected_option_is_used(self) -> None:
        with self.assertRaisesRegex(subject.SubmissionError, "dataset set mismatch"):
            subject.validate_rows(
                list(self.fieldnames or []),
                self.rows,
                expected_datasets={"embryoA_fov01", "missing"},
            )

    def test_rejects_zarr_suffix_and_surrounding_whitespace(self) -> None:
        with self.assertRaisesRegex(subject.SubmissionError, "without .zarr"):
            self.validate(self.changed(0, "dataset", "embryoA_fov01.zarr"))
        with self.assertRaisesRegex(subject.SubmissionError, "surrounding whitespace"):
            self.validate(self.changed(0, "row_type", " node"))

    def test_rejects_extra_csv_fields_and_empty_file(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows[0][None] = ["unexpected"]  # DictReader representation of an extra cell.
        with self.assertRaisesRegex(subject.SubmissionError, "extra CSV fields"):
            self.validate(rows)
        with self.assertRaisesRegex(subject.SubmissionError, "at least one row"):
            subject.validate_rows(subject.COLUMNS, [])

    def test_expected_dataset_loaders_reject_duplicates_and_zarr_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            csv_path = base / "datasets.csv"
            text_path = base / "datasets.txt"
            duplicate_path = base / "duplicate.json"
            zarr_path = base / "zarr.txt"
            csv_path.write_text("dataset\na\nb\n", encoding="utf-8")
            text_path.write_text("# fixture\na\nb\n", encoding="utf-8")
            duplicate_path.write_text(json.dumps(["a", "a"]), encoding="utf-8")
            zarr_path.write_text("a.zarr\n", encoding="utf-8")
            self.assertEqual(subject.load_expected_datasets(csv_path), {"a", "b"})
            self.assertEqual(subject.load_expected_datasets(text_path), {"a", "b"})
            with self.assertRaises(subject.SubmissionError):
                subject.load_expected_datasets(duplicate_path)
            with self.assertRaises(subject.SubmissionError):
                subject.load_expected_datasets(zarr_path)


if __name__ == "__main__":
    unittest.main()
