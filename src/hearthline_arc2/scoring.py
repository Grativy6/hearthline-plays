"""Exact output-pair-weighted pass@2 scoring, isolated from solver execution."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
import re
from typing import Any

from .validation import (
    coerce_challenge_set,
    validate_solution_set,
    validate_submission,
)


SCORER_VERSION = "hearthline-plays.arc2.output-pair-pass-at-2.v1"
SCORE_RECEIPT_SCHEMA = "hearthline-plays.arc2-score-receipt.v1"
SCORE_MODES = frozenset({"SYNTHETIC", "PUBLIC_EVAL"})
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """Aggregate-only official-metric result with an exact rational score."""

    numerator: int
    denominator: int
    duplicate_attempt_count: int
    malformed_count: int = 0

    @property
    def score(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    @property
    def score_numerator(self) -> int:
        return self.score.numerator

    @property
    def score_denominator(self) -> int:
        return self.score.denominator

    @property
    def score_decimal(self) -> str:
        if self.numerator == self.denominator:
            return "1.0"
        if self.numerator == 0:
            return "0.0"
        with localcontext() as context:
            context.prec = 16
            display = format(Decimal(self.numerator) / Decimal(self.denominator), "f")
        return display.rstrip("0").rstrip(".")

    def to_dict(self) -> dict[str, Any]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "score_numerator": self.score_numerator,
            "score_denominator": self.score_denominator,
            "score_decimal": self.score_decimal,
            "duplicate_attempt_count": self.duplicate_attempt_count,
            "malformed_count": self.malformed_count,
        }


def score_submission(
    challenges: object,
    solutions: object,
    submission: object,
) -> ScoreResult:
    """Validate all artifacts, then score each test-output pair equally.

    No comparison occurs until challenge, solution, and submission coverage is
    fully validated.  Either of the two exact grids earns one point; there is
    no partial-cell credit and no task-level averaging.
    """

    validated_challenges = coerce_challenge_set(challenges)
    validated_solutions = validate_solution_set(validated_challenges, solutions)
    validated_submission = validate_submission(validated_challenges, submission)

    numerator = 0
    denominator = 0
    duplicate_attempt_count = 0
    for task_id in sorted(validated_challenges):
        task_solutions = validated_solutions[task_id]
        task_attempts = validated_submission[task_id]
        for expected, attempts in zip(task_solutions, task_attempts, strict=True):
            denominator += 1
            if attempts.attempt_1 == attempts.attempt_2:
                duplicate_attempt_count += 1
            if attempts.attempt_1 == expected or attempts.attempt_2 == expected:
                numerator += 1

    # Challenge validation requires a nonempty task set with nonempty test
    # inputs, so a zero denominator would indicate an internal contract bug.
    if denominator < 1:
        raise RuntimeError("validated challenge unexpectedly has no test outputs")
    return ScoreResult(
        numerator=numerator,
        denominator=denominator,
        duplicate_attempt_count=duplicate_attempt_count,
        malformed_count=0,
    )


def create_score_receipt(
    result: ScoreResult,
    *,
    scorer_sha256: str,
    challenge_sha256: str,
    solution_sha256: str,
    submission_sha256: str,
    mode: str,
    authorization_grant_sha256: str | None = None,
    run_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Build a label-free score receipt from hashes and aggregate counts."""

    if mode not in SCORE_MODES:
        raise ValueError(f"unsupported score mode: {mode!r}")
    for field, value in {
        "scorer_sha256": scorer_sha256,
        "challenge_sha256": challenge_sha256,
        "solution_sha256": solution_sha256,
        "submission_sha256": submission_sha256,
    }.items():
        if (
            not isinstance(value, str)
            or _SHA256_PATTERN.fullmatch(value) is None
            or value == "0" * 64
        ):
            raise ValueError(f"{field} must be a full lowercase SHA-256")
    if mode == "PUBLIC_EVAL":
        if (
            not isinstance(authorization_grant_sha256, str)
            or _SHA256_PATTERN.fullmatch(authorization_grant_sha256) is None
            or authorization_grant_sha256 == "0" * 64
        ):
            raise ValueError("PUBLIC_EVAL receipt requires its exact grant SHA-256")
        if (
            not isinstance(run_manifest_sha256, str)
            or _SHA256_PATTERN.fullmatch(run_manifest_sha256) is None
            or run_manifest_sha256 == "0" * 64
        ):
            raise ValueError("PUBLIC_EVAL receipt requires its exact run-manifest SHA-256")
    elif authorization_grant_sha256 is not None or run_manifest_sha256 is not None:
        raise ValueError("SYNTHETIC receipt cannot claim external authorization")

    receipt = {
        "schema": SCORE_RECEIPT_SCHEMA,
        "mode": mode,
        "scorer_version": SCORER_VERSION,
        "scorer_sha256": scorer_sha256,
        "challenge_sha256": challenge_sha256,
        "solution_sha256": solution_sha256,
        "submission_sha256": submission_sha256,
        "numerator": result.numerator,
        "denominator": result.denominator,
        "score_numerator": result.score_numerator,
        "score_denominator": result.score_denominator,
        "score_decimal": result.score_decimal,
        "duplicate_attempt_count": result.duplicate_attempt_count,
        "malformed_count": result.malformed_count,
        "aggregate_only": mode == "PUBLIC_EVAL",
        "status": "VALID_AGGREGATE" if mode == "PUBLIC_EVAL" else "VALID_SYNTHETIC",
    }
    if authorization_grant_sha256 is not None:
        receipt["authorization_grant_sha256"] = authorization_grant_sha256
        receipt["run_manifest_sha256"] = run_manifest_sha256
    return receipt


# A receipt-like result name is convenient for callers that do not emit the
# provenance wrapper; the on-disk receipt remains the dict above with hashes.
ScoreReceipt = ScoreResult
