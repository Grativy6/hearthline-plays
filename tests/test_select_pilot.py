from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools import select_pilot as selector


def make_index(counts: dict[str, int]) -> list[dict[str, str]]:
    return [
        {"question_id": f"{difficulty}-{offset:03d}", "difficulty": difficulty}
        for difficulty in selector.DIFFICULTY_ORDER
        for offset in range(counts[difficulty])
    ]


def make_full_index_with_exclusion() -> list[dict[str, str]]:
    index = make_index(selector.EXPECTED_COUNTS)
    index[0]["question_id"] = "abc357_b"
    return index


class SelectPilotTests(unittest.TestCase):
    def test_validates_synthetic_counts_and_selects_deterministically(self) -> None:
        counts = {"easy": 6, "medium": 7, "hard": 8}
        grouped = selector.validate_index(make_index(counts), expected_counts=counts)
        requested = {"easy": 2, "medium": 2, "hard": 2}
        first = selector.select_pilot(grouped, requested_counts=requested)
        second = selector.select_pilot(grouped, requested_counts=requested)
        self.assertEqual(first, second)
        self.assertEqual([row["difficulty"] for row in first], ["easy"] * 2 + ["medium"] * 2 + ["hard"] * 2)
        self.assertEqual([row["order"] for row in first], list(range(6)))
        self.assertEqual(len({row["question_id"] for row in first}), 6)

    def test_rank_is_independent_of_input_order(self) -> None:
        counts = {"easy": 6, "medium": 6, "hard": 6}
        index = make_index(counts)
        forward = selector.select_pilot(
            selector.validate_index(index, expected_counts=counts),
            requested_counts={key: 2 for key in counts},
        )
        reverse = selector.select_pilot(
            selector.validate_index(list(reversed(index)), expected_counts=counts),
            requested_counts={key: 2 for key in counts},
        )
        self.assertEqual(forward, reverse)

    def test_rejects_prompt_test_or_other_extra_fields(self) -> None:
        counts = {"easy": 1, "medium": 1, "hard": 1}
        for extra in ("prompt", "tests", "all_tests", "starter_code"):
            with self.subTest(extra=extra):
                index = make_index(counts)
                index[0][extra] = "forbidden"
                with self.assertRaisesRegex(selector.SelectionError, "only question_id"):
                    selector.validate_index(index, expected_counts=counts)

    def test_rejects_duplicate_or_untrimmed_ids(self) -> None:
        counts = {"easy": 1, "medium": 1, "hard": 1}
        duplicate = make_index(counts)
        duplicate[1]["question_id"] = duplicate[0]["question_id"]
        with self.assertRaisesRegex(selector.SelectionError, "duplicate"):
            selector.validate_index(duplicate, expected_counts=counts)
        untrimmed = make_index(counts)
        untrimmed[0]["question_id"] = " bad "
        with self.assertRaisesRegex(selector.SelectionError, "trimmed"):
            selector.validate_index(untrimmed, expected_counts=counts)

    def test_rejects_wrong_total_and_strata(self) -> None:
        full = make_index(selector.EXPECTED_COUNTS)
        with self.assertRaisesRegex(selector.SelectionError, "exactly 150"):
            selector.validate_index(full[:-1])
        wrong_strata = make_index({"easy": 41, "medium": 49, "hard": 60})
        with self.assertRaisesRegex(selector.SelectionError, "difficulty counts"):
            selector.validate_index(wrong_strata)

    def test_frozen_development_task_is_removed_before_ranking(self) -> None:
        grouped = selector.validate_index(make_full_index_with_exclusion())
        eligible = selector.apply_exclusions(grouped, frozenset({"abc357_b"}))
        self.assertNotIn("abc357_b", eligible["easy"])
        selected = selector.select_pilot(eligible)
        self.assertNotIn("abc357_b", {row["question_id"] for row in selected})

    def test_missing_frozen_exclusion_fails_closed(self) -> None:
        grouped = selector.validate_index(make_index(selector.EXPECTED_COUNTS))
        with self.assertRaisesRegex(selector.SelectionError, "absent from the source index"):
            selector.apply_exclusions(grouped, frozenset({"abc357_b"}))

    def test_exclusion_manifest_is_digest_bound(self) -> None:
        excluded, digest = selector.load_exclusions()
        self.assertEqual(excluded, frozenset({"abc357_b"}))
        self.assertEqual(digest, selector.EXCLUSION_MANIFEST_SHA256)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tampered.json"
            path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(selector.SelectionError, "SHA-256 mismatch"):
                selector.load_exclusions(path)

    def test_cli_writes_only_the_explicit_new_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "metadata-index.json"
            output_path = root / "pilot.json"
            input_path.write_text(json.dumps(make_full_index_with_exclusion()), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    selector.main([str(input_path), "--output", str(output_path)]), 0
                )
            self.assertIn("selected 15 metadata-only IDs", output.getvalue())
            self.assertEqual({path.name for path in root.iterdir()}, {input_path.name, output_path.name})
            manifest = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "SELECTED_IDS_ONLY_NOT_RUN")
            self.assertEqual(len(manifest["selection"]["selected"]), 15)
            self.assertEqual(manifest["development_excluded_question_ids"], ["abc357_b"])
            self.assertEqual(
                manifest["development_exclusion_manifest_sha256"],
                selector.EXCLUSION_MANIFEST_SHA256,
            )
            self.assertNotIn(
                "abc357_b",
                {row["question_id"] for row in manifest["selection"]["selected"]},
            )
            self.assertFalse(manifest["task_material_opened_during_selection"])
            expected_digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
            self.assertIn(f"pilot_manifest_sha256={expected_digest}", output.getvalue())
            self.assertNotIn("manifest_sha256", manifest)

    def test_cli_never_overwrites_an_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "metadata-index.json"
            output_path = root / "pilot.json"
            input_path.write_text(json.dumps(make_full_index_with_exclusion()), encoding="utf-8")
            output_path.write_text("keep me", encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    selector.main([str(input_path), "--output", str(output_path)]), 1
                )
            self.assertEqual(output_path.read_text(encoding="utf-8"), "keep me")


if __name__ == "__main__":
    unittest.main()
