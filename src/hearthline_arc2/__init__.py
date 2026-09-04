"""Standard-library ARC-AGI-2 readiness contracts and local harness.

Exports are resolved lazily so importing a solver contract never imports the
scorer (and importing the scorer never imports or constructs a solver).
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "AuthorizationError",
    "AttemptPair",
    "Demonstration",
    "FormatBaseline",
    "Grid",
    "IdentityZeroBaseline",
    "IdentityZeroSolver",
    "RunResult",
    "RunnerError",
    "ScoreReceipt",
    "ScoreResult",
    "SolveBudget",
    "StaticSolver",
    "TaskView",
    "ValidationError",
    "build_submission",
    "claim_public_evaluation",
    "complete_preflight_consumption",
    "canonical_json_bytes",
    "challenge_semantic_sha256",
    "coerce_challenge_set",
    "create_run_manifest",
    "create_score_receipt",
    "record_preflight_consumption",
    "kernel_metadata_hardware_class",
    "load_json",
    "parse_json",
    "run_solver",
    "score_submission",
    "solutions_to_jsonable",
    "split_labeled_challenge_set",
    "split_labeled_task",
    "validate_challenge_set",
    "validate_grid",
    "validate_input_manifest",
    "validate_input_manifest_challenge_snapshot",
    "validate_kernel_metadata",
    "validate_run_manifest",
    "validate_solver_config",
    "validate_source_lock",
    "validate_solution_set",
    "validate_submission",
    "write_run_manifest",
    "write_submission",
]


_EXPORT_MODULE = {
    "AuthorizationError": "authorization",
    "AttemptPair": "contracts",
    "Demonstration": "contracts",
    "FormatBaseline": "contracts",
    "Grid": "contracts",
    "IdentityZeroBaseline": "contracts",
    "IdentityZeroSolver": "contracts",
    "SolveBudget": "contracts",
    "StaticSolver": "contracts",
    "TaskView": "contracts",
    "claim_public_evaluation": "authorization",
    "complete_preflight_consumption": "authorization",
    "record_preflight_consumption": "authorization",
    "RunResult": "runner",
    "RunnerError": "runner",
    "build_submission": "runner",
    "canonical_json_bytes": "runner",
    "create_run_manifest": "runner",
    "run_solver": "runner",
    "validate_run_manifest": "runner",
    "write_run_manifest": "runner",
    "write_submission": "runner",
    "ScoreReceipt": "scoring",
    "ScoreResult": "scoring",
    "create_score_receipt": "scoring",
    "score_submission": "scoring",
    "ValidationError": "validation",
    "challenge_semantic_sha256": "validation",
    "coerce_challenge_set": "validation",
    "kernel_metadata_hardware_class": "validation",
    "load_json": "validation",
    "parse_json": "validation",
    "solutions_to_jsonable": "validation",
    "split_labeled_challenge_set": "validation",
    "split_labeled_task": "validation",
    "validate_challenge_set": "validation",
    "validate_grid": "validation",
    "validate_input_manifest": "validation",
    "validate_input_manifest_challenge_snapshot": "validation",
    "validate_kernel_metadata": "validation",
    "validate_solver_config": "validation",
    "validate_source_lock": "validation",
    "validate_solution_set": "validation",
    "validate_submission": "validation",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULE.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(f".{module_name}", __name__), name)
    globals()[name] = value
    return value
