"""Provider-independent contracts for static ARC-AGI-2 task solving.

This module deliberately has no filesystem, network, provider, or scoring
dependencies.  A solver sees demonstration pairs and test inputs only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar, Protocol, Sequence, TypeAlias, runtime_checkable


Grid: TypeAlias = tuple[tuple[int, ...], ...]


def _freeze_grid(value: Sequence[Sequence[int]]) -> Grid:
    """Make the nested sequence immutable without interpreting its semantics."""

    try:
        return tuple(tuple(row) for row in value)
    except TypeError as exc:
        raise TypeError("a grid must be a sequence of row sequences") from exc


@dataclass(frozen=True, slots=True)
class Demonstration:
    """One immutable training input/output example."""

    input: Grid
    output: Grid

    def __post_init__(self) -> None:
        object.__setattr__(self, "input", _freeze_grid(self.input))
        object.__setattr__(self, "output", _freeze_grid(self.output))


@dataclass(frozen=True, slots=True)
class TaskView:
    """The complete, label-free information made available to a solver."""

    task_id: str
    train: tuple[Demonstration, ...]
    test_inputs: tuple[Grid, ...]

    def __post_init__(self) -> None:
        frozen_train = tuple(self.train)
        if not all(isinstance(item, Demonstration) for item in frozen_train):
            raise TypeError("TaskView.train must contain Demonstration values")
        object.__setattr__(self, "train", frozen_train)
        object.__setattr__(
            self,
            "test_inputs",
            tuple(_freeze_grid(grid) for grid in self.test_inputs),
        )


@dataclass(frozen=True, slots=True)
class AttemptPair:
    """Exactly two complete candidate grids for one test input."""

    attempt_1: Grid
    attempt_2: Grid

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempt_1", _freeze_grid(self.attempt_1))
        object.__setattr__(self, "attempt_2", _freeze_grid(self.attempt_2))


@dataclass(frozen=True, slots=True)
class SolveBudget:
    """A monotonic deadline and a solver-defined deterministic work limit."""

    deadline_monotonic: float
    max_work_units: int

    def __post_init__(self) -> None:
        if isinstance(self.deadline_monotonic, bool) or type(
            self.deadline_monotonic
        ) not in {int, float}:
            raise TypeError("deadline_monotonic must be a number")
        if math.isnan(float(self.deadline_monotonic)) or self.deadline_monotonic <= 0:
            raise ValueError("deadline_monotonic must be positive and not NaN")
        if isinstance(self.max_work_units, bool) or not isinstance(
            self.max_work_units, int
        ):
            raise TypeError("max_work_units must be an integer")
        if self.max_work_units < 1:
            raise ValueError("max_work_units must be at least 1")


@runtime_checkable
class StaticSolver(Protocol):
    """A one-call, non-interactive solver for a single static ARC task."""

    solver_id: str

    def solve(
        self,
        task: TaskView,
        *,
        seed: int,
        budget: SolveBudget,
    ) -> Sequence[AttemptPair]:
        """Return one already-complete attempt pair per test input."""


@dataclass(frozen=True, slots=True)
class IdentityZeroBaseline:
    """Deterministic structural baseline, not a competitive ARC solver.

    Attempt 1 copies the test input.  Attempt 2 is an all-zero grid with the
    same dimensions.  It exists to exercise packaging and scoring contracts.
    It does not infer a transformation and makes no performance claim.
    """

    solver_id: ClassVar[str] = "baseline.identity-zero.v1"

    def solve(
        self,
        task: TaskView,
        *,
        seed: int,
        budget: SolveBudget,
    ) -> Sequence[AttemptPair]:
        del seed, budget
        return tuple(
            AttemptPair(
                attempt_1=grid,
                attempt_2=tuple(tuple(0 for _ in row) for row in grid),
            )
            for grid in task.test_inputs
        )


# Descriptive compatibility names; all identify the same baseline-only class.
IdentityZeroSolver = IdentityZeroBaseline
FormatBaseline = IdentityZeroBaseline
