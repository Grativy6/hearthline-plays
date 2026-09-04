"""Synthetic-only tests for the label-free static solver contract."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hearthline_arc2.contracts import (  # noqa: E402
    AttemptPair,
    Demonstration,
    IdentityZeroBaseline,
    SolveBudget,
    StaticSolver,
    TaskView,
)


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = TaskView(
            task_id="a0000001",
            train=(Demonstration(input=((1, 0),), output=((0, 1),)),),
            test_inputs=(((1, 2), (3, 4)),),
        )

    def test_task_view_is_label_free_and_immutable(self) -> None:
        self.assertFalse(hasattr(self.task, "solutions"))
        self.assertFalse(hasattr(self.task, "test_outputs"))
        self.assertEqual(self.task.test_inputs, (((1, 2), (3, 4)),))
        with self.assertRaises(AttributeError):
            self.task.task_id = "a0000002"  # type: ignore[misc]

    def test_identity_zero_baseline_is_a_static_solver(self) -> None:
        solver = IdentityZeroBaseline()
        self.assertIsInstance(solver, StaticSolver)
        result = solver.solve(
            self.task,
            seed=7,
            budget=SolveBudget(
                deadline_monotonic=time.monotonic() + 1,
                max_work_units=1,
            ),
        )
        self.assertEqual(
            result,
            (
                AttemptPair(
                    attempt_1=((1, 2), (3, 4)),
                    attempt_2=((0, 0), (0, 0)),
                ),
            ),
        )

    def test_baseline_is_seed_independent_and_deterministic(self) -> None:
        solver = IdentityZeroBaseline()
        budget = SolveBudget(
            deadline_monotonic=time.monotonic() + 1,
            max_work_units=1,
        )
        self.assertEqual(
            solver.solve(self.task, seed=0, budget=budget),
            solver.solve(self.task, seed=999, budget=budget),
        )

    def test_expired_budget_uses_complete_label_free_format_fallback(self) -> None:
        result = IdentityZeroBaseline().solve(
            self.task,
            seed=0,
            budget=SolveBudget(
                deadline_monotonic=time.monotonic() - 1,
                max_work_units=1,
            ),
        )
        self.assertEqual(len(result), len(self.task.test_inputs))
        self.assertIsInstance(result[0], AttemptPair)

    def test_budget_rejects_boolean_and_nonpositive_work(self) -> None:
        with self.assertRaises(TypeError):
            SolveBudget(deadline_monotonic=True, max_work_units=1)
        with self.assertRaises(ValueError):
            SolveBudget(deadline_monotonic=float("nan"), max_work_units=1)
        with self.assertRaises(ValueError):
            SolveBudget(deadline_monotonic=0, max_work_units=1)
        with self.assertRaises(TypeError):
            SolveBudget(deadline_monotonic=1.0, max_work_units=True)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            SolveBudget(deadline_monotonic=1.0, max_work_units=0)


if __name__ == "__main__":
    unittest.main()
