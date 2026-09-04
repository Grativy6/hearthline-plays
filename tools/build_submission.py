#!/usr/bin/env python3
"""Build a structurally complete baseline submission without opening labels.

The bundled identity/zero implementation is a packaging baseline only.  This
tool does not score, contact Kaggle, use a provider, or accept a solution path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from hearthline_arc2.contracts import IdentityZeroBaseline, SolveBudget  # noqa: E402
from hearthline_arc2.runner import (  # noqa: E402
    RunnerError,
    canonical_json_bytes,
    create_run_manifest,
    run_solver,
    write_run_manifest,
    write_submission,
)
from hearthline_arc2.synthetic import (  # noqa: E402
    SyntheticFixtureError,
    load_synthetic_artifact,
)
from hearthline_arc2.validation import (  # noqa: E402
    ValidationError,
    challenge_to_jsonable,
    parse_json,
    validate_challenge_set,
    validate_input_manifest,
    validate_input_manifest_challenge_snapshot,
    validate_solver_config,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise RunnerError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _read_json_snapshot(path: Path) -> tuple[object, str, int]:
    """Read, hash, and decode one immutable-in-memory byte snapshot."""

    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RunnerError(f"cannot read {path}: {exc}") from exc
    try:
        value = parse_json(payload.decode("utf-8"))
    except UnicodeError as exc:
        raise RunnerError(f"{path} is not UTF-8 JSON") from exc
    return value, hashlib.sha256(payload).hexdigest(), len(payload)


def _sha256_sources(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError as exc:
            raise RunnerError(f"cannot hash solver source {path}: {exc}") from exc
        digest.update(b"\0")
    return digest.hexdigest()


def _git_object(revision: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", revision],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RunnerError(f"cannot resolve Git object {revision!r}: {exc}") from exc
    value = completed.stdout.strip()
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise RunnerError(f"Git returned a non-full object ID for {revision!r}")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build an ARC-AGI-2 identity/zero structural baseline and run manifest. "
            "This command never loads solutions or scores predictions."
        )
    )
    parser.add_argument("--challenges", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="operator-selected runtime directory for submission.json and run-manifest.json",
    )
    parser.add_argument(
        "--source-lock",
        type=Path,
        default=REPOSITORY_ROOT / "provenance" / "official-sources.lock.json",
    )
    parser.add_argument(
        "--input-manifest",
        type=Path,
        help=(
            "TRAIN_CV-only closed manifest binding the actual challenge digest, "
            "bytes, counts, split/filename, source lock, and ARC-AGI-2 Git pin"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=(
            "closed solver-config JSON; mandatory for TRAIN_CV and omitted only "
            "for the inline synthetic baseline"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("SYNTHETIC", "TRAIN_CV"),
        default="SYNTHETIC",
        help="external evaluation modes are deliberately unavailable here",
    )
    parser.add_argument("--fold-id")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--wall-budget-seconds", type=int, default=60)
    parser.add_argument("--cpu-budget-seconds", type=int, default=60)
    parser.add_argument("--max-work-units", type=int, default=1)
    parser.add_argument("--run-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.wall_budget_seconds <= 0 or args.cpu_budget_seconds <= 0:
        raise SystemExit("budget seconds must be positive")
    if args.max_work_units < 1:
        raise SystemExit("max work units must be at least 1")
    if args.mode == "TRAIN_CV" and not args.fold_id:
        raise SystemExit("--fold-id is required for TRAIN_CV")
    if args.mode != "TRAIN_CV" and args.fold_id is not None:
        raise SystemExit("--fold-id is permitted only for TRAIN_CV")
    if args.mode == "SYNTHETIC" and args.input_manifest is not None:
        raise SystemExit("--input-manifest is forbidden in SYNTHETIC mode")
    if args.mode == "TRAIN_CV" and args.input_manifest is None:
        raise SystemExit("--input-manifest is required for TRAIN_CV")
    if args.mode == "TRAIN_CV" and args.config is None:
        raise SystemExit("--config is required for TRAIN_CV")

    try:
        started_at = _utc_now()
        if args.mode == "SYNTHETIC":
            challenge_data, _, _ = load_synthetic_artifact(
                args.challenges,
                REPOSITORY_ROOT / "tests" / "fixtures" / "synthetic",
                "challenges.json",
            )
            challenges = validate_challenge_set(challenge_data)
        else:
            challenge_data, challenge_sha256, challenge_byte_count = (
                _read_json_snapshot(args.challenges)
            )
        source_lock, source_lock_sha256, _ = _read_json_snapshot(args.source_lock)
        if args.mode == "SYNTHETIC":
            input_manifest_sha256 = hashlib.sha256(
                canonical_json_bytes(challenge_to_jsonable(challenges))
            ).hexdigest()
        else:
            input_manifest, input_manifest_sha256, _ = _read_json_snapshot(
                args.input_manifest
            )
            validate_input_manifest(
                input_manifest,
                "$.input_manifest",
                source_lock_value=source_lock,
                source_lock_sha256=source_lock_sha256,
                expected_split="TRAINING",
            )
            challenges = validate_input_manifest_challenge_snapshot(
                input_manifest,
                challenge_data,
                challenge_filename=args.challenges.name,
                challenge_raw_sha256=challenge_sha256,
                challenge_byte_count=challenge_byte_count,
                path="$.input_manifest",
            )

        solver = IdentityZeroBaseline()
        inline_config = {
            "schema": "hearthline-plays.arc2-solver-config.v1",
            "competition_slug": "arc-prize-2026-arc-agi-2",
            "solver_id": solver.solver_id,
            "seed": args.seed,
            "seed_policy": "FIXED_INTEGER_PER_TASK",
            "deterministic": True,
            "wall_budget_seconds": args.wall_budget_seconds,
            "cpu_budget_seconds": args.cpu_budget_seconds,
            "max_work_units": args.max_work_units,
            "hardware_class": "local-cpu",
            "dependency_identities": [],
            "model_identities": [],
            "max_attempts_per_test_input": 2,
            "network_required": False,
        }
        if args.config is None:
            config = validate_solver_config(
                inline_config,
                "$.config",
                expected_solver_id=solver.solver_id,
            )
            config_sha256 = hashlib.sha256(canonical_json_bytes(config)).hexdigest()
        else:
            config_value, config_sha256, _ = _read_json_snapshot(args.config)
            config = validate_solver_config(
                config_value,
                "$.config",
                expected_solver_id=solver.solver_id,
            )
            require_equal = {
                "solver_id": solver.solver_id,
                "seed": args.seed,
                "wall_budget_seconds": args.wall_budget_seconds,
                "cpu_budget_seconds": args.cpu_budget_seconds,
                "max_work_units": args.max_work_units,
                "hardware_class": "local-cpu",
            }
            for field, expected in require_equal.items():
                if config[field] != expected:
                    raise ValidationError(
                        f"$.config.{field}: does not match the selected build value"
                    )
        budget = SolveBudget(
            deadline_monotonic=time.monotonic() + args.wall_budget_seconds,
            max_work_units=args.max_work_units,
        )
        result = run_solver(challenges, solver, seed=args.seed, budget=budget)
        output_dir = args.output_dir.resolve()
        submission_path = output_dir / "submission.json"
        manifest_path = output_dir / "run-manifest.json"
        submission_sha256 = write_submission(
            submission_path, challenges, result.submission
        )

        solver_code_sha256 = _sha256_sources(
            [
                SOURCE_ROOT / "hearthline_arc2" / "contracts.py",
                SOURCE_ROOT / "hearthline_arc2" / "runner.py",
                SOURCE_ROOT / "hearthline_arc2" / "validation.py",
            ]
        )
        finished_at = _utc_now()
        run_id = args.run_id or f"arc2-{submission_sha256[:16]}"
        runtime_identity = (
            f"{platform.python_implementation()}-{platform.python_version()}-"
            f"{platform.system()}-{platform.machine()}"
        )
        manifest = create_run_manifest(
            run_id=run_id,
            mode=args.mode,
            source_lock_sha256=source_lock_sha256,
            branch_commit=_git_object("HEAD"),
            branch_tree=_git_object("HEAD^{tree}"),
            solver_id=solver.solver_id,
            solver_code_sha256=solver_code_sha256,
            config_sha256=config_sha256,
            seed_policy=f"fixed integer seed {args.seed}; identical seed passed once per task",
            input_manifest_sha256=input_manifest_sha256,
            fold_id=args.fold_id,
            started_at=started_at,
            finished_at=finished_at,
            wall_budget_seconds=args.wall_budget_seconds,
            cpu_budget_seconds=args.cpu_budget_seconds,
            runtime_identity=runtime_identity,
            dependency_identities=config["dependency_identities"],
            model_identities=config["model_identities"],
            submission_sha256=submission_sha256,
            discovered_task_count=result.task_count,
            discovered_test_input_count=result.test_input_count,
        )
        manifest_sha256 = write_run_manifest(manifest_path, manifest)
    except (RunnerError, SyntheticFixtureError, ValidationError) as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 2

    summary = {
        "baseline_only": True,
        "manifest_sha256": manifest_sha256,
        "solver_id": solver.solver_id,
        "submission_sha256": submission_sha256,
        "task_count": result.task_count,
        "test_input_count": result.test_input_count,
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
