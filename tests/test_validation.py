"""Synthetic-only tests for closed ARC-AGI-2 artifact validation."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"

from hearthline_arc2.validation import (  # noqa: E402
    ValidationError,
    load_json,
    parse_json,
    split_labeled_task,
    validate_challenge_set,
    validate_grid,
    validate_solution_set,
    validate_submission,
)


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.challenge_json = load_json(FIXTURES / "challenges.json")
        cls.solution_json = load_json(FIXTURES / "solutions.json")
        cls.submission_json = load_json(FIXTURES / "submission.json")

    def test_synthetic_fixture_is_valid_and_complete(self) -> None:
        challenges = validate_challenge_set(self.challenge_json)
        solutions = validate_solution_set(challenges, self.solution_json)
        submission = validate_submission(challenges, self.submission_json)
        self.assertEqual(set(challenges), {"a0000001", "a0000002"})
        self.assertEqual(len(solutions["a0000002"]), 2)
        self.assertEqual(len(submission["a0000002"]), 2)

    def test_grid_rejects_bool_ragged_empty_and_out_of_range(self) -> None:
        for value in (
            [[True]],
            [[0], [0, 1]],
            [],
            [[]],
            [[-1]],
            [[10]],
            [["0"]],
            [[0] * 31],
            [[0] for _ in range(31)],
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_grid(value)

    def test_solver_challenge_rejects_test_output(self) -> None:
        invalid = copy.deepcopy(self.challenge_json)
        invalid["a0000001"]["test"][0]["output"] = [[1]]
        with self.assertRaisesRegex(ValidationError, "unexpected keys"):
            validate_challenge_set(invalid)

    def test_submission_requires_exact_two_attempt_keys(self) -> None:
        challenges = validate_challenge_set(self.challenge_json)
        for mutation in ("missing", "third", "metadata"):
            invalid = copy.deepcopy(self.submission_json)
            if mutation == "missing":
                del invalid["a0000001"][0]["attempt_2"]
            elif mutation == "third":
                invalid["a0000001"][0]["attempt_3"] = [[0]]
            else:
                invalid["a0000001"][0]["confidence"] = 1
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValidationError):
                    validate_submission(challenges, invalid)

    def test_submission_requires_exact_task_and_test_coverage(self) -> None:
        challenges = validate_challenge_set(self.challenge_json)
        missing_task = copy.deepcopy(self.submission_json)
        del missing_task["a0000001"]
        with self.assertRaisesRegex(ValidationError, "coverage mismatch"):
            validate_submission(challenges, missing_task)

        missing_test = copy.deepcopy(self.submission_json)
        missing_test["a0000002"].pop()
        with self.assertRaisesRegex(ValidationError, "exactly 2"):
            validate_submission(challenges, missing_test)

        extra_task = copy.deepcopy(self.submission_json)
        extra_task["a0000003"] = extra_task["a0000001"]
        with self.assertRaisesRegex(ValidationError, "coverage mismatch"):
            validate_submission(challenges, extra_task)

    def test_task_ids_and_solution_counts_are_closed(self) -> None:
        wrong_id = copy.deepcopy(self.challenge_json)
        wrong_id["A0000001"] = wrong_id.pop("a0000001")
        with self.assertRaisesRegex(ValidationError, "must match"):
            validate_challenge_set(wrong_id)

        challenges = validate_challenge_set(self.challenge_json)
        missing_solution = copy.deepcopy(self.solution_json)
        missing_solution["a0000002"].pop()
        with self.assertRaisesRegex(ValidationError, "exactly 2"):
            validate_solution_set(challenges, missing_solution)

    def test_identical_attempts_are_allowed(self) -> None:
        challenges = validate_challenge_set(self.challenge_json)
        duplicate = copy.deepcopy(self.submission_json)
        duplicate["a0000001"][0]["attempt_2"] = duplicate["a0000001"][0][
            "attempt_1"
        ]
        validate_submission(challenges, duplicate)

    def test_labeled_task_is_split_before_solver_view(self) -> None:
        labeled = {
            "train": [{"input": [[1]], "output": [[2]]}],
            "test": [{"input": [[3]], "output": [[4]]}],
        }
        task, labels = split_labeled_task("a00000aa", labeled)
        self.assertEqual(task.test_inputs, (((3,),),))
        self.assertFalse(hasattr(task, "test_outputs"))
        self.assertEqual(labels, (((4,),),))

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate JSON"):
            parse_json('{"a": 1, "a": 2}')
        with self.assertRaisesRegex(ValidationError, "non-finite"):
            parse_json('{"a": NaN}')


if __name__ == "__main__":
    unittest.main()
