"""Synthetic-only CLI regressions for mode and one-shot enforcement."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"

from hearthline_arc2 import validation as arc_validation  # noqa: E402
from hearthline_arc2.authorization import (  # noqa: E402
    complete_preflight_consumption,
    record_preflight_consumption,
)
from hearthline_arc2.contracts import IdentityZeroBaseline  # noqa: E402
from hearthline_arc2.runner import create_run_manifest  # noqa: E402
from hearthline_arc2.validation import (  # noqa: E402
    challenge_semantic_sha256,
    load_json,
    solutions_to_jsonable,
)
from tools import build_submission, score_local  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def git_object(revision: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--verify", revision],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build_public_bundle(
    runtime: Path,
    *,
    grant_id: str = "synthetic-public-score-test",
    run_finishes_after_grant: bool = False,
    stale_reviews: bool = False,
    complete_preflight: bool = True,
) -> dict[str, object]:
    """Create a fully bound fake public lane from authored synthetic bytes."""

    challenge_path = runtime / "arc-agi_evaluation_challenges.json"
    solution_path = runtime / "solutions.json"
    submission_path = runtime / "submission.json"
    challenge_path.write_bytes((FIXTURES / "challenges.json").read_bytes())
    solution_path.write_bytes((FIXTURES / "solutions.json").read_bytes())
    submission_path.write_bytes((FIXTURES / "submission.json").read_bytes())
    challenges = load_json(challenge_path)
    solutions = load_json(solution_path)
    challenge_semantic = challenge_semantic_sha256(challenges)
    solution_semantic = canonical_sha256(
        solutions_to_jsonable(challenges, solutions)
    )

    commitments = copy.deepcopy(arc_validation.PUBLIC_CHALLENGE_COMMITMENTS)
    commitments["PUBLIC_EVALUATION"] = {
        "status": "PINNED_GIT_TREE",
        "origin": "PINNED_ARC2_PUBLIC_REPOSITORY",
        "repository_path": "data/evaluation",
        "source_tree": "8d04288aac3146b7c47d0b799c18bc9c0217d838",
        "challenge_semantic_sha256": challenge_semantic,
        "solution_semantic_sha256": solution_semantic,
        "task_count": 2,
        "test_input_count": 3,
    }
    source_lock = copy.deepcopy(
        load_json(ROOT / "provenance" / "official-sources.lock.json")
    )
    source_lock["challenge_commitments"]["PUBLIC_EVALUATION"] = copy.deepcopy(
        commitments["PUBLIC_EVALUATION"]
    )
    review_now = datetime.now(timezone.utc)
    review_start = (
        review_now - timedelta(days=2)
        if stale_reviews
        else review_now - timedelta(minutes=1)
    )
    review_end = (
        review_now - timedelta(days=1)
        if stale_reviews
        else review_now + timedelta(minutes=5)
    )
    for surface in source_lock["mutable_surfaces"]:
        surface.update(
            {
                "content_sha256": hashlib.sha256(
                    surface["url"].encode("utf-8")
                ).hexdigest(),
                "status": "FROZEN_HUMAN_REVIEWED",
                "retrieval_utc": review_start
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                "human_reviewer": "Christopher D. Pang",
                "revalidate_before": review_end
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
            }
        )
    source_lock_path = runtime / "synthetic-public-source-lock.json"
    write_json(source_lock_path, source_lock)
    source_lock_sha = sha256_path(source_lock_path)

    input_manifest = {
        "schema": "hearthline-plays.arc2-input-manifest.v1",
        "competition_slug": "arc-prize-2026-arc-agi-2",
        "split": "PUBLIC_EVALUATION",
        "challenge_origin": "PINNED_ARC2_PUBLIC_REPOSITORY",
        "challenge_filename": challenge_path.name,
        "challenge_raw_sha256": sha256_path(challenge_path),
        "challenge_semantic_sha256": challenge_semantic,
        "challenge_byte_count": challenge_path.stat().st_size,
        "task_count": 2,
        "test_input_count": 3,
        "source_lock_sha256": source_lock_sha,
        "arc2_public_repository": "arcprize/ARC-AGI-2",
        "arc2_public_commit": "f3283f727488ad98fe575ea6a5ac981e4a188e49",
        "arc2_public_tree": "afab62b97f29dd2341f401d4af70491e14da35c2",
        "labels_included": False,
        "official_data_vendored": False,
    }
    input_manifest_path = runtime / "input-manifest.json"
    write_json(input_manifest_path, input_manifest)

    config = {
        "schema": "hearthline-plays.arc2-solver-config.v1",
        "competition_slug": "arc-prize-2026-arc-agi-2",
        "solver_id": IdentityZeroBaseline.solver_id,
        "seed": 0,
        "seed_policy": "FIXED_INTEGER_PER_TASK",
        "deterministic": True,
        "wall_budget_seconds": 60,
        "cpu_budget_seconds": 60,
        "max_work_units": 1,
        "hardware_class": "local-cpu",
        "dependency_identities": ["python:3.12-test"],
        "model_identities": [],
        "max_attempts_per_test_input": 2,
        "network_required": False,
    }
    config_path = runtime / "solver-config.json"
    write_json(config_path, config)

    head = git_object("HEAD")
    tree = git_object("HEAD^{tree}")
    solver_sha = score_local._sha256_named_sources(
        [
            ROOT / "src" / "hearthline_arc2" / "contracts.py",
            ROOT / "src" / "hearthline_arc2" / "runner.py",
            ROOT / "src" / "hearthline_arc2" / "validation.py",
        ]
    )
    now = datetime.now(timezone.utc)
    issued_at = now - timedelta(minutes=1)
    finished_at = issued_at + (
        timedelta(seconds=1)
        if run_finishes_after_grant
        else -timedelta(minutes=1)
    )
    started_at = finished_at - timedelta(seconds=30)

    run_manifest = create_run_manifest(
        run_id=f"run-{grant_id}",
        mode="PUBLIC_EVAL",
        source_lock_sha256=source_lock_sha,
        branch_commit=head,
        branch_tree=tree,
        solver_id=config["solver_id"],
        solver_code_sha256=solver_sha,
        config_sha256=sha256_path(config_path),
        seed_policy="fixed integer seed 0; identical seed passed once per task",
        input_manifest_sha256=sha256_path(input_manifest_path),
        fold_id=None,
        started_at=started_at.isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        finished_at=finished_at.isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        wall_budget_seconds=config["wall_budget_seconds"],
        cpu_budget_seconds=config["cpu_budget_seconds"],
        runtime_identity="synthetic-test-runtime",
        dependency_identities=config["dependency_identities"],
        model_identities=config["model_identities"],
        submission_sha256=sha256_path(submission_path),
        discovered_task_count=2,
        discovered_test_input_count=3,
    )
    run_manifest_path = runtime / "run-manifest.json"
    write_json(run_manifest_path, run_manifest)

    grant = {
        "schema": "hearthline-plays.arc2-ignition-grant.v1",
        "grant_id": grant_id,
        "scope": "PUBLIC_EVAL_ONCE",
        "competition_slug": "arc-prize-2026-arc-agi-2",
        "branch_commit": head,
        "branch_tree": tree,
        "source_lock_sha256": source_lock_sha,
        "notebook_sha256": sha256_path(ROOT / "notebook" / "arc2_submission.ipynb"),
        "solver_code_sha256": solver_sha,
        "config_sha256": sha256_path(config_path),
        "input_manifest_sha256": sha256_path(input_manifest_path),
        "run_manifest_sha256": sha256_path(run_manifest_path),
        "submission_sha256": sha256_path(submission_path),
        "solution_semantic_sha256": solution_semantic,
        "hardware_class": "local-cpu",
        "max_runtime_seconds": 60,
        "issued_at": issued_at.isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "expires_at": (now + timedelta(minutes=5))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "nonce": hashlib.sha256(grant_id.encode("utf-8")).hexdigest(),
        "human_approver": "Christopher D. Pang",
        "acknowledgement": score_local.PUBLIC_ACKNOWLEDGEMENT,
    }
    grant_path = runtime / "grant.json"
    write_json(grant_path, grant)
    ledger = runtime / "consumption-ledger"
    record_preflight_consumption(grant, ledger)
    if complete_preflight:
        complete_preflight_consumption(grant, ledger)
    arguments = [
        "--mode",
        "public-eval",
        "--grant",
        str(grant_path),
        "--config",
        str(config_path),
        "--input-manifest",
        str(input_manifest_path),
        "--run-manifest",
        str(run_manifest_path),
        "--challenges",
        str(challenge_path),
        "--solutions",
        str(solution_path),
        "--submission",
        str(submission_path),
    ]
    return {
        "arguments": arguments,
        "challenge_path": challenge_path,
        "solution_path": solution_path,
        "submission_path": submission_path,
        "source_lock_path": source_lock_path,
        "input_manifest_path": input_manifest_path,
        "config_path": config_path,
        "run_manifest_path": run_manifest_path,
        "grant_path": grant_path,
        "grant": grant,
        "ledger": ledger,
        "commitments": commitments,
    }


@contextlib.contextmanager
def patched_public_runtime(bundle: dict[str, object]):
    with mock.patch.object(
        score_local, "CANONICAL_LEDGER", bundle["ledger"]
    ), mock.patch.object(
        score_local, "SOURCE_LOCK", bundle["source_lock_path"]
    ), mock.patch.object(
        score_local, "_git_is_clean", return_value=True
    ), mock.patch.object(
        arc_validation,
        "PUBLIC_CHALLENGE_COMMITMENTS",
        bundle["commitments"],
    ):
        yield


class CliSafetyTests(unittest.TestCase):
    def test_score_mode_is_mandatory_and_old_boolean_flag_is_rejected(self) -> None:
        common = [
            "--challenges",
            str(FIXTURES / "challenges.json"),
            "--solutions",
            str(FIXTURES / "solutions.json"),
            "--submission",
            str(FIXTURES / "submission.json"),
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                score_local.main(common)
            with self.assertRaises(SystemExit):
                score_local.main(["--mode", "synthetic", *common, "--synthetic"])

    def test_synthetic_mode_is_explicit_and_cannot_accept_a_grant(self) -> None:
        common = [
            "--mode",
            "synthetic",
            "--challenges",
            str(FIXTURES / "challenges.json"),
            "--solutions",
            str(FIXTURES / "solutions.json"),
            "--submission",
            str(FIXTURES / "submission.json"),
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(score_local.main(common), 0)
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["mode"], "SYNTHETIC")
        self.assertEqual(receipt["status"], "VALID_SYNTHETIC")
        self.assertFalse(receipt["aggregate_only"])
        self.assertNotIn("authorization_grant_sha256", receipt)
        self.assertNotIn("run_manifest_sha256", receipt)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(score_local.main([*common, "--grant", "unused"]), 2)

    def test_synthetic_mode_accepts_only_exact_committed_fixture_bytes(self) -> None:
        sentinel = "deadbeef"
        fixture_paths = {
            "challenges": FIXTURES / "challenges.json",
            "solutions": FIXTURES / "solutions.json",
            "submission": FIXTURES / "submission.json",
        }
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            exact_copies: dict[str, Path] = {}
            for role, fixture_path in fixture_paths.items():
                exact_copies[role] = runtime / f"exact-copy-{role}.json"
                exact_copies[role].write_bytes(fixture_path.read_bytes())
            exact_stdout = io.StringIO()
            with contextlib.redirect_stdout(exact_stdout):
                self.assertEqual(
                    score_local.main(
                        [
                            "--mode",
                            "synthetic",
                            "--challenges",
                            str(exact_copies["challenges"]),
                            "--solutions",
                            str(exact_copies["solutions"]),
                            "--submission",
                            str(exact_copies["submission"]),
                        ]
                    ),
                    0,
                )

            for role, fixture_path in fixture_paths.items():
                with self.subTest(role=role):
                    candidate = runtime / f"modified-{role}.json"
                    value = copy.deepcopy(load_json(fixture_path))
                    first_task = next(iter(value))
                    value[sentinel] = value.pop(first_task)
                    write_json(candidate, value)
                    selected = dict(fixture_paths)
                    selected[role] = candidate
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        self.assertEqual(
                            score_local.main(
                                [
                                    "--mode",
                                    "synthetic",
                                    "--challenges",
                                    str(selected["challenges"]),
                                    "--solutions",
                                    str(selected["solutions"]),
                                    "--submission",
                                    str(selected["submission"]),
                                ]
                            ),
                            2,
                        )
                    self.assertIn("committed synthetic fixture", stderr.getvalue())
                    self.assertNotIn(sentinel, stderr.getvalue())

            role_swapped = io.StringIO()
            with contextlib.redirect_stderr(role_swapped):
                self.assertEqual(
                    score_local.main(
                        [
                            "--mode",
                            "synthetic",
                            "--challenges",
                            str(fixture_paths["challenges"]),
                            "--solutions",
                            str(fixture_paths["submission"]),
                            "--submission",
                            str(fixture_paths["solutions"]),
                        ]
                    ),
                    2,
                )
            self.assertIn("committed synthetic fixture", role_swapped.getvalue())

            whitespace_only = runtime / "whitespace-only-challenges.json"
            whitespace_only.write_bytes(
                fixture_paths["challenges"].read_bytes() + b" "
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(
                    build_submission.main(
                        [
                            "--challenges",
                            str(whitespace_only),
                            "--output-dir",
                            str(runtime / "output"),
                            "--mode",
                            "SYNTHETIC",
                        ]
                    ),
                    2,
                )
            self.assertIn("committed synthetic fixture", stderr.getvalue())
            self.assertNotIn("a0000001", stderr.getvalue())

    def test_synthetic_tools_consume_the_verified_byte_snapshot_without_reopen(self) -> None:
        score_arguments = [
            "--mode",
            "synthetic",
            "--challenges",
            str(FIXTURES / "challenges.json"),
            "--solutions",
            str(FIXTURES / "solutions.json"),
            "--submission",
            str(FIXTURES / "submission.json"),
        ]
        with mock.patch.object(
            score_local,
            "_read_and_hash",
            side_effect=AssertionError("synthetic artifact reopened"),
        ), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(score_local.main(score_arguments), 0)

        real_read = build_submission._read_json_snapshot

        def read_nonchallenge(path):
            if path == FIXTURES / "challenges.json":
                raise AssertionError("verified synthetic challenge reopened")
            return real_read(path)

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            build_submission,
            "_read_json_snapshot",
            side_effect=read_nonchallenge,
        ), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                build_submission.main(
                    [
                        "--challenges",
                        str(FIXTURES / "challenges.json"),
                        "--output-dir",
                        str(Path(directory) / "output"),
                        "--mode",
                        "SYNTHETIC",
                    ]
                ),
                0,
            )

    def test_builder_rejects_arbitrary_manifest_and_external_modes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arbitrary = Path(directory) / "arbitrary.txt"
            arbitrary.write_text("not a manifest\n", encoding="utf-8")
            arguments = [
                "--challenges",
                str(FIXTURES / "challenges.json"),
                "--output-dir",
                str(Path(directory) / "output"),
                "--mode",
                "SYNTHETIC",
                "--input-manifest",
                str(arbitrary),
            ]
            with self.assertRaisesRegex(SystemExit, "forbidden"):
                build_submission.main(arguments)
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    build_submission.main(
                        [
                            "--challenges",
                            str(FIXTURES / "challenges.json"),
                            "--output-dir",
                            str(Path(directory) / "output"),
                            "--mode",
                            "PUBLIC_EVAL",
                        ]
                    )
            with self.assertRaisesRegex(SystemExit, "--config is required"):
                build_submission.main(
                    [
                        "--challenges",
                        str(FIXTURES / "challenges.json"),
                        "--output-dir",
                        str(Path(directory) / "output"),
                        "--mode",
                        "TRAIN_CV",
                        "--fold-id",
                        "fold-0",
                        "--input-manifest",
                        str(arbitrary),
                    ]
                )

    def test_public_score_requires_closed_complete_authorization_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = build_public_bundle(Path(directory))
            grant = bundle["grant"]
            self.assertEqual(set(grant), score_local.PUBLIC_GRANT_FIELDS)
            grant_path = bundle["grant_path"]
            arguments = bundle["arguments"]

            with patched_public_runtime(bundle):
                for flag in ("--config", "--run-manifest"):
                    with self.subTest(missing=flag):
                        incomplete = list(arguments)
                        index = incomplete.index(flag)
                        del incomplete[index : index + 2]
                        stderr = io.StringIO()
                        with contextlib.redirect_stderr(stderr):
                            self.assertEqual(score_local.main(incomplete), 2)
                        self.assertEqual(
                            stderr.getvalue().strip(),
                            "score failed: sealed public-evaluation audit failed",
                        )

                for field in (
                    "run_manifest_sha256",
                    "submission_sha256",
                    "solution_semantic_sha256",
                ):
                    with self.subTest(missing_grant_field=field):
                        incomplete_grant = copy.deepcopy(grant)
                        del incomplete_grant[field]
                        write_json(grant_path, incomplete_grant)
                        stderr = io.StringIO()
                        with contextlib.redirect_stderr(stderr):
                            self.assertEqual(score_local.main(arguments), 2)
                        self.assertEqual(
                            stderr.getvalue().strip(),
                            "score failed: sealed public-evaluation audit failed",
                        )

                extra_grant = copy.deepcopy(grant)
                extra_grant["unexpected"] = True
                write_json(grant_path, extra_grant)
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(score_local.main(arguments), 2)

            write_json(grant_path, grant)
            self.assertFalse((bundle["ledger"] / "claims").exists())

    def test_public_score_is_bound_one_shot_and_opens_data_after_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = build_public_bundle(Path(directory))
            protected = {
                bundle["challenge_path"],
                bundle["solution_path"],
                bundle["submission_path"],
            }
            events: list[str] = []
            real_claim = score_local.claim_public_evaluation
            real_read = score_local._read_and_hash

            def claim(grant, ledger):
                events.append("claim")
                return real_claim(grant, ledger)

            def read_and_hash(path):
                if path in protected:
                    events.append(f"read:{path.name}")
                return real_read(path)

            first_stdout = io.StringIO()
            with patched_public_runtime(bundle), mock.patch.object(
                score_local, "claim_public_evaluation", side_effect=claim
            ), mock.patch.object(
                score_local, "_read_and_hash", side_effect=read_and_hash
            ), contextlib.redirect_stdout(first_stdout):
                self.assertEqual(score_local.main(bundle["arguments"]), 0)

            self.assertEqual(
                events,
                [
                    "claim",
                    "read:arc-agi_evaluation_challenges.json",
                    "read:solutions.json",
                    "read:submission.json",
                ],
            )
            receipt = json.loads(first_stdout.getvalue())
            self.assertEqual(receipt["mode"], "PUBLIC_EVAL")
            self.assertTrue(receipt["aggregate_only"])
            self.assertEqual(
                receipt["run_manifest_sha256"],
                sha256_path(bundle["run_manifest_path"]),
            )
            self.assertIn("authorization_grant_sha256", receipt)
            self.assertNotIn("diagnostics", receipt)
            self.assertNotIn("a0000001", first_stdout.getvalue())

            second_stderr = io.StringIO()
            with patched_public_runtime(bundle), contextlib.redirect_stderr(
                second_stderr
            ):
                self.assertEqual(score_local.main(bundle["arguments"]), 2)
            self.assertEqual(
                second_stderr.getvalue().strip(),
                "score failed: sealed public-evaluation audit failed",
            )
            self.assertNotIn("a0000001", second_stderr.getvalue())

    def test_public_score_rejects_run_not_frozen_before_grant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = build_public_bundle(
                Path(directory),
                grant_id="synthetic-public-late-run",
                run_finishes_after_grant=True,
            )
            stderr = io.StringIO()
            with patched_public_runtime(bundle), contextlib.redirect_stderr(stderr):
                self.assertEqual(score_local.main(bundle["arguments"]), 2)
            self.assertEqual(
                stderr.getvalue().strip(),
                "score failed: sealed public-evaluation audit failed",
            )
            self.assertFalse((bundle["ledger"] / "claims").exists())

    def test_public_score_requires_completed_preflight_not_only_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = build_public_bundle(
                Path(directory),
                grant_id="synthetic-public-incomplete-preflight",
                complete_preflight=False,
            )
            stderr = io.StringIO()
            with patched_public_runtime(bundle), contextlib.redirect_stderr(stderr):
                self.assertEqual(score_local.main(bundle["arguments"]), 2)
            self.assertEqual(
                stderr.getvalue().strip(),
                "score failed: sealed public-evaluation audit failed",
            )
            self.assertTrue(
                (bundle["ledger"] / "consumed-grants.jsonl").is_file()
            )
            self.assertFalse((bundle["ledger"] / "claims").exists())

    def test_public_score_rechecks_source_review_freshness_before_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = build_public_bundle(
                Path(directory),
                grant_id="synthetic-public-stale-source-review",
                stale_reviews=True,
            )
            stderr = io.StringIO()
            with patched_public_runtime(bundle), contextlib.redirect_stderr(stderr):
                self.assertEqual(score_local.main(bundle["arguments"]), 2)
            self.assertEqual(
                stderr.getvalue().strip(),
                "score failed: sealed public-evaluation audit failed",
            )
            self.assertFalse((bundle["ledger"] / "claims").exists())

    def test_public_artifact_mismatches_are_claimed_and_fully_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for role in ("challenge", "solution", "submission"):
                with self.subTest(role=role):
                    runtime = root / role
                    runtime.mkdir()
                    bundle = build_public_bundle(
                        runtime,
                        grant_id=f"synthetic-public-mismatch-{role}",
                    )
                    if role == "challenge":
                        value = load_json(bundle["challenge_path"])
                        value["deadbeef"] = value.pop(next(iter(value)))
                        write_json(bundle["challenge_path"], value)
                    elif role == "solution":
                        value = load_json(bundle["solution_path"])
                        first = next(iter(value))
                        value[first][0][0][0] = (value[first][0][0][0] + 1) % 10
                        write_json(bundle["solution_path"], value)
                    else:
                        bundle["submission_path"].write_bytes(
                            bundle["submission_path"].read_bytes() + b" "
                        )

                    stderr = io.StringIO()
                    with patched_public_runtime(bundle), contextlib.redirect_stderr(
                        stderr
                    ):
                        self.assertEqual(score_local.main(bundle["arguments"]), 2)
                    self.assertEqual(
                        stderr.getvalue().strip(),
                        "score failed: sealed public-evaluation audit failed",
                    )
                    for secret in (
                        "a0000001",
                        "deadbeef",
                        str(bundle[f"{role}_path"]),
                        "[[",
                    ):
                        self.assertNotIn(secret, stderr.getvalue())

                    nonce = bundle["grant"]["nonce"]
                    self.assertTrue(
                        (bundle["ledger"] / "claims" / f"{nonce}.used").is_file()
                    )
                    retry_stderr = io.StringIO()
                    with patched_public_runtime(bundle), contextlib.redirect_stderr(
                        retry_stderr
                    ):
                        self.assertEqual(score_local.main(bundle["arguments"]), 2)
                    self.assertEqual(
                        retry_stderr.getvalue().strip(),
                        "score failed: sealed public-evaluation audit failed",
                    )


if __name__ == "__main__":
    unittest.main()
