"""Synthetic-only runner and output-pair scoring regression tests."""

from __future__ import annotations

import copy
import sys
import tempfile
import time
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"

from hearthline_arc2.contracts import (  # noqa: E402
    AttemptPair,
    IdentityZeroBaseline,
    SolveBudget,
)
from hearthline_arc2.runner import (  # noqa: E402
    RunnerError,
    build_submission,
    canonical_json_bytes,
    create_run_manifest,
    run_solver,
    validate_run_manifest,
    write_submission,
)
from hearthline_arc2.scoring import (  # noqa: E402
    create_score_receipt,
    score_submission,
)
from hearthline_arc2.validation import ValidationError, load_json  # noqa: E402


class ScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.challenges = load_json(FIXTURES / "challenges.json")
        cls.solutions = load_json(FIXTURES / "solutions.json")
        cls.submission = load_json(FIXTURES / "submission.json")

    def test_fixture_locks_output_pair_weighting_at_one_third(self) -> None:
        result = score_submission(self.challenges, self.solutions, self.submission)
        self.assertEqual((result.numerator, result.denominator), (1, 3))
        self.assertEqual(result.score, Fraction(1, 3))
        self.assertEqual(result.score_decimal, "0.3333333333333333")

    def test_only_second_attempt_can_earn_exact_credit(self) -> None:
        challenges = {
            "a00000aa": {
                "train": [{"input": [[1]], "output": [[2]]}],
                "test": [{"input": [[3]]}],
            }
        }
        solutions = {"a00000aa": [[[4, 4]]]}
        submission = {
            "a00000aa": [
                {"attempt_1": [[9]], "attempt_2": [[4, 4]]},
            ]
        }
        result = score_submission(challenges, solutions, submission)
        self.assertEqual((result.numerator, result.denominator), (1, 1))

    def test_identical_attempts_are_counted_but_not_rejected(self) -> None:
        challenges = {
            "a00000aa": {
                "train": [{"input": [[1]], "output": [[1]]}],
                "test": [{"input": [[2]]}],
            }
        }
        result = score_submission(
            challenges,
            {"a00000aa": [[[7]]]},
            {"a00000aa": [{"attempt_1": [[7]], "attempt_2": [[7]]}]},
        )
        self.assertEqual(result.numerator, 1)
        self.assertEqual(result.duplicate_attempt_count, 1)

    def test_partial_submission_fails_before_any_score(self) -> None:
        partial = copy.deepcopy(self.submission)
        del partial["a0000002"]
        with self.assertRaises(ValidationError):
            score_submission(self.challenges, self.solutions, partial)

    def test_aggregate_receipt_contains_no_task_or_grid_detail(self) -> None:
        result = score_submission(self.challenges, self.solutions, self.submission)
        receipt = create_score_receipt(
            result,
            scorer_sha256="1" * 64,
            challenge_sha256="2" * 64,
            solution_sha256="3" * 64,
            submission_sha256="4" * 64,
            mode="PUBLIC_EVAL",
            authorization_grant_sha256="5" * 64,
            run_manifest_sha256="6" * 64,
        )
        self.assertEqual(receipt["status"], "VALID_AGGREGATE")
        self.assertEqual(receipt["mode"], "PUBLIC_EVAL")
        self.assertNotIn("tasks", receipt)
        self.assertNotIn("diagnostics", receipt)
        self.assertNotIn("predictions", receipt)

    def test_receipt_mode_cannot_be_inferred_from_an_omitted_flag(self) -> None:
        result = score_submission(self.challenges, self.solutions, self.submission)
        common = {
            "scorer_sha256": "1" * 64,
            "challenge_sha256": "2" * 64,
            "solution_sha256": "3" * 64,
            "submission_sha256": "4" * 64,
        }
        with self.assertRaises(TypeError):
            create_score_receipt(result, **common)
        with self.assertRaises(ValueError):
            create_score_receipt(result, **common, mode="PUBLIC_EVAL")
        with self.assertRaises(ValueError):
            create_score_receipt(
                result,
                **common,
                mode="SYNTHETIC",
                authorization_grant_sha256="5" * 64,
            )
        with self.assertRaises(ValueError):
            create_score_receipt(
                result,
                **common,
                mode="SYNTHETIC",
                run_manifest_sha256="6" * 64,
            )


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.challenges = load_json(FIXTURES / "challenges.json")
        cls.expected = load_json(FIXTURES / "submission.json")

    def test_baseline_build_is_deterministic_across_mapping_order(self) -> None:
        normal = build_submission(self.challenges, IdentityZeroBaseline(), seed=9)
        reversed_challenges = dict(reversed(list(self.challenges.items())))
        reversed_output = build_submission(
            reversed_challenges, IdentityZeroBaseline(), seed=9
        )
        self.assertEqual(normal, self.expected)
        self.assertEqual(canonical_json_bytes(normal), canonical_json_bytes(reversed_output))

    def test_runner_calls_solver_once_per_task_in_stable_order(self) -> None:
        class RecordingSolver:
            solver_id = "synthetic.recording.v1"

            def __init__(self) -> None:
                self.calls: list[str] = []

            def solve(self, task, *, seed, budget):
                self.calls.append(task.task_id)
                self_outer.assertFalse(hasattr(task, "test_outputs"))
                return IdentityZeroBaseline().solve(
                    task, seed=seed, budget=budget
                )

        self_outer = self
        solver = RecordingSolver()
        result = run_solver(
            dict(reversed(list(self.challenges.items()))), solver, seed=0
        )
        self.assertEqual(solver.calls, ["a0000001", "a0000002"])
        self.assertEqual(result.task_count, 2)
        self.assertEqual(result.test_input_count, 3)

    def test_runner_never_retries_a_failure(self) -> None:
        class FailingSolver:
            solver_id = "synthetic.failure.v1"

            def __init__(self) -> None:
                self.calls = 0

            def solve(self, task, *, seed, budget):
                self.calls += 1
                raise RuntimeError("synthetic failure")

        solver = FailingSolver()
        with self.assertRaises(RunnerError):
            run_solver(self.challenges, solver)
        self.assertEqual(solver.calls, 1)

    def test_runner_rejects_an_expired_deadline_before_solver_access(self) -> None:
        class NeverCalledSolver:
            solver_id = "synthetic.never-called.v1"

            def __init__(self) -> None:
                self.calls = 0

            def solve(self, task, *, seed, budget):
                self.calls += 1
                return ()

        solver = NeverCalledSolver()
        with self.assertRaisesRegex(RunnerError, "deadline"):
            run_solver(
                self.challenges,
                solver,
                budget=SolveBudget(
                    deadline_monotonic=time.monotonic() - 1,
                    max_work_units=1,
                ),
            )
        self.assertEqual(solver.calls, 0)

    def test_runner_rejects_missing_attempt_pair(self) -> None:
        class TooShortSolver:
            solver_id = "synthetic.too-short.v1"

            def solve(self, task, *, seed, budget):
                return tuple(
                    AttemptPair(attempt_1=((0,),), attempt_2=((0,),))
                    for _ in task.test_inputs[:-1]
                )

        with self.assertRaises(RunnerError):
            run_solver(self.challenges, TooShortSolver())

    def test_submission_write_requires_exact_name_and_is_complete(self) -> None:
        submission = build_submission(self.challenges, IdentityZeroBaseline())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "submission.json"
            digest = write_submission(output, self.challenges, submission)
            self.assertEqual(load_json(output), self.expected)
            self.assertEqual(len(digest), 64)
            with self.assertRaises(RunnerError):
                write_submission(
                    Path(directory) / "predictions.json",
                    self.challenges,
                    submission,
                )

    @staticmethod
    def manifest_arguments() -> dict[str, object]:
        return {
            "run_id": "synthetic-run-1",
            "mode": "SYNTHETIC",
            "source_lock_sha256": "1" * 64,
            "branch_commit": "2" * 40,
            "branch_tree": "3" * 40,
            "solver_id": "synthetic.solver.v1",
            "solver_code_sha256": "4" * 64,
            "config_sha256": "5" * 64,
            "seed_policy": "fixed integer seed 0",
            "input_manifest_sha256": "6" * 64,
            "fold_id": None,
            "started_at": "2026-09-04T00:00:00Z",
            "finished_at": "2026-09-04T00:00:01Z",
            "wall_budget_seconds": 10.0,
            "cpu_budget_seconds": 9.0,
            "runtime_identity": "CPython-3.12-test",
            "dependency_identities": [],
            "model_identities": [],
            "submission_sha256": "7" * 64,
            "discovered_task_count": 2,
            "discovered_test_input_count": 3,
        }

    def test_run_manifest_accepts_only_closed_semantically_valid_values(self) -> None:
        manifest = create_run_manifest(**self.manifest_arguments())
        self.assertEqual(validate_run_manifest(manifest), manifest)
        self.assertFalse(manifest["ground_truth_exposed_to_solver"])
        self.assertEqual(manifest["max_attempts_per_test_input"], 2)

    def test_run_manifest_rejects_every_semantic_bypass(self) -> None:
        mutations = {
            "short_hash": {"config_sha256": "5" * 63},
            "placeholder_hash": {"config_sha256": "0" * 64},
            "short_commit": {"branch_commit": "2" * 39},
            "placeholder_commit": {"branch_commit": "0" * 40},
            "uppercase_tree": {"branch_tree": "A" * 40},
            "reversed_time": {
                "started_at": "2026-09-04T00:00:02Z",
                "finished_at": "2026-09-04T00:00:01Z",
            },
            "elapsed_over_wall_budget": {
                "finished_at": "2026-09-04T00:00:11Z",
            },
            "noncanonical_utc": {"started_at": "2026-09-04 00:00:00Z"},
            "zero_wall": {"wall_budget_seconds": 0},
            "boolean_cpu": {"cpu_budget_seconds": True},
            "nonfinite_cpu": {"cpu_budget_seconds": float("nan")},
            "boolean_count": {"discovered_task_count": True},
            "zero_count": {"discovered_test_input_count": 0},
            "impossible_counts": {
                "discovered_task_count": 4,
                "discovered_test_input_count": 3,
            },
            "cpu_over_wall": {"cpu_budget_seconds": 11.0},
            "synthetic_fold": {"fold_id": "fold-1"},
            "duplicate_dependency": {
                "dependency_identities": ["python-3.12", "python-3.12"]
            },
        }
        for label, mutation in mutations.items():
            arguments = self.manifest_arguments()
            arguments.update(mutation)
            with self.subTest(label=label):
                with self.assertRaises(RunnerError):
                    create_run_manifest(**arguments)

        train_without_fold = self.manifest_arguments()
        train_without_fold["mode"] = "TRAIN_CV"
        with self.assertRaises(RunnerError):
            create_run_manifest(**train_without_fold)

        extra = create_run_manifest(**self.manifest_arguments())
        extra["unexpected"] = True
        with self.assertRaisesRegex(RunnerError, "field mismatch"):
            validate_run_manifest(extra)


if __name__ == "__main__":
    unittest.main()
