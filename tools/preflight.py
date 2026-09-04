#!/usr/bin/env python3
"""Offline, fail-closed verification for Hearthline ARC-AGI-2 readiness.

This program has no external-service operation.  Development mode inspects
only repository contracts and authored synthetic fixtures.  External modes
also require frozen mutable sources and a narrow human grant, but still do not
open official data or contact Kaggle.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hearthline_arc2.contracts import IdentityZeroBaseline, StaticSolver  # noqa: E402
from hearthline_arc2.authorization import (  # noqa: E402
    AuthorizationError,
    assert_unspent,
    complete_preflight_consumption,
    record_preflight_consumption,
)
from hearthline_arc2.runner import (  # noqa: E402
    RunnerError,
    build_submission,
    canonical_json_bytes,
    validate_run_manifest,
)
from hearthline_arc2.scoring import score_submission  # noqa: E402
from hearthline_arc2.validation import (  # noqa: E402
    ValidationError,
    kernel_metadata_hardware_class,
    load_json,
    validate_challenge_set,
    validate_input_manifest,
    validate_kernel_metadata,
    validate_solver_config,
    validate_source_lock,
    validate_solution_set,
    validate_submission,
)

ANCHOR_COMMIT = "228d80f0559277c55031f4a80f6179320e10364c"
ANCHOR_TREE = "532e178ecd41410e5e9038c647141f2cbe32f01d"
COMPETITION_SLUG = "arc-prize-2026-arc-agi-2"
UNFROZEN = "UNFROZEN_REVALIDATE_BEFORE_EXTERNAL_GRANT"
FROZEN = "FROZEN_HUMAN_REVIEWED"
CANONICAL_LEDGER = ROOT / "ignition" / "consumption-ledger"
UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
PUBLIC_ACKNOWLEDGEMENT = (
    "I authorize exactly one sealed public-evaluation audit; its aggregate "
    "result will not be used for tuning."
)
KAGGLE_RUN_ACKNOWLEDGEMENT = (
    "I reviewed the current rules and authorize exactly one bound Kaggle "
    "notebook run; this is not submission authorization."
)
KAGGLE_SUBMIT_ACKNOWLEDGEMENT = (
    "I authorize exactly one submission of this notebook version and output; "
    "no later version or retry is covered."
)
GRANT_BASE_KEYS = {
    "schema",
    "grant_id",
    "scope",
    "competition_slug",
    "branch_commit",
    "branch_tree",
    "source_lock_sha256",
    "notebook_sha256",
    "solver_code_sha256",
    "config_sha256",
    "input_manifest_sha256",
    "hardware_class",
    "max_runtime_seconds",
    "issued_at",
    "expires_at",
    "nonce",
    "human_approver",
    "acknowledgement",
}
GRANT_SCOPE_FIELDS = {
    "PUBLIC_EVAL_ONCE": {
        "run_manifest_sha256",
        "submission_sha256",
        "solution_semantic_sha256",
    },
    "KAGGLE_NOTEBOOK_RUN_ONCE": {"rules_sha256", "notebook_metadata_sha256"},
    "KAGGLE_SUBMIT_ONCE": {
        "rules_sha256",
        "notebook_metadata_sha256",
        "kaggle_notebook_version_id",
        "output_sha256",
    },
}

EXPECTED_GIT_SOURCES = {
    "arcprize/ARC-AGI-2": (
        "main",
        "f3283f727488ad98fe575ea6a5ac981e4a188e49",
        "afab62b97f29dd2341f401d4af70491e14da35c2",
        "Apache-2.0",
        "public_dataset",
        "PINNED_EXTERNAL_MOUNT_NOT_VENDORED",
    ),
    "arcprize/arc-agi-benchmarking": (
        "main",
        "28e67d54b05df5be10281892243c509a42a874f1",
        "fa89cb240ddf434f9d4d143d2411772f79809acc",
        "MIT",
        "official_benchmarking_reference",
        "INSPECTED_NOT_COPIED_NOT_SCORING_AUTHORITY",
    ),
    "Kaggle/kaggle-api": (
        "main",
        "659469c4185cfca0fb3be01edad6f50277528d9d",
        "71ae8e6abf6dc780907416316b68f5315f96b856",
        "Apache-2.0",
        "notebook_metadata_reference",
        "INSPECTED_NOT_VENDORED",
    ),
    "actions/checkout": (
        "PINNED_ACTION",
        "11d5960a326750d5838078e36cf38b85af677262",
        "f8a7b72dc00648d050099727d25ca92a43ad1162",
        "MIT",
        "ci_checkout",
        "EXECUTED_IN_READ_ONLY_CI",
    ),
    "actions/setup-python": (
        "PINNED_ACTION",
        "a26af69be951a213d495a4c3e4e4022e16d87065",
        "568c6310706725a8b725497dbe6b3b909cbcf6cd",
        "MIT",
        "ci_python_setup",
        "EXECUTED_IN_READ_ONLY_CI",
    ),
}

EXPECTED_MUTABLE_URLS = {
    "https://arcprize.org/competitions/2026/arc-agi-2",
    "https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-2",
    "https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-2/rules",
    "https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-2/data",
    "https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-2/overview/abstract",
    "https://arcprize.org/guide/1",
    "https://arcprize.org/policy",
}

EXPECTED_PUBLIC_CHALLENGE_COMMITMENTS = {
    "TRAINING": {
        "status": "PINNED_GIT_TREE",
        "origin": "PINNED_ARC2_PUBLIC_REPOSITORY",
        "repository_path": "data/training",
        "source_tree": "dac7259367cc5099ef6a7b604a50a93affbbee33",
        "challenge_semantic_sha256": "0cae8c51dcec8b25ecfbdefc2907c1e51983bccaf1a8d621f169cbe81fc001fe",
        "solution_semantic_sha256": "6d668c1911653f40610bb237769e144919768b8dbeecd233516891d34d4c6503",
        "task_count": 1000,
        "test_input_count": 1076,
    },
    "PUBLIC_EVALUATION": {
        "status": "PINNED_GIT_TREE",
        "origin": "PINNED_ARC2_PUBLIC_REPOSITORY",
        "repository_path": "data/evaluation",
        "source_tree": "8d04288aac3146b7c47d0b799c18bc9c0217d838",
        "challenge_semantic_sha256": "8cade36130fdf1fa8fbab00cfcdfb5be8e74acbf04140f6fe18c5f502f0639be",
        "solution_semantic_sha256": "e623ea77ee8993928c50c4a5a51d3ed8c75c30e9bb65dcd480140d89f6fa5f9f",
        "task_count": 120,
        "test_input_count": 167,
    },
}

REQUIRED_PATHS = {
    ".github/workflows/verify-arc2-readiness.yml",
    ".gitignore",
    "README.md",
    "LICENSE",
    "docs/PREFLIGHT.md",
    "docs/CONTEXT_MAP.md",
    "docs/ARC2_METHOD_MAP.md",
    "ignition/README.md",
    "ignition/kaggle-run-grant.template.json",
    "ignition/kaggle-submit-grant.template.json",
    "ignition/public-eval-grant.template.json",
    "notebook/arc2_submission.ipynb",
    "notebook/kernel-metadata.template.json",
    "provenance/official-sources.lock.json",
    "schemas/challenge-set.v1.schema.json",
    "schemas/input-manifest.v1.schema.json",
    "schemas/ignition-grant.v1.schema.json",
    "schemas/kernel-metadata.v1.schema.json",
    "schemas/run-manifest.v1.schema.json",
    "schemas/score-receipt.v1.schema.json",
    "schemas/source-lock.v1.schema.json",
    "schemas/solver-config.v1.schema.json",
    "schemas/submission.v1.schema.json",
    "src/hearthline_arc2/contracts.py",
    "src/hearthline_arc2/authorization.py",
    "src/hearthline_arc2/__init__.py",
    "src/hearthline_arc2/runner.py",
    "src/hearthline_arc2/scoring.py",
    "src/hearthline_arc2/synthetic.py",
    "src/hearthline_arc2/validation.py",
    "tests/fixtures/synthetic/challenges.json",
    "tests/fixtures/synthetic/fixture-manifest.json",
    "tests/fixtures/synthetic/solutions.json",
    "tests/fixtures/synthetic/submission.json",
    "tests/test_contracts.py",
    "tests/test_authorization.py",
    "tests/test_cli_safety.py",
    "tests/test_metadata_contracts.py",
    "tests/test_notebook_contract.py",
    "tests/test_preflight.py",
    "tests/test_scoring.py",
    "tests/test_validation.py",
    "tools/build_submission.py",
    "tools/preflight.py",
    "tools/score_local.py",
}


class PreflightError(RuntimeError):
    """A readiness assertion failed."""


@dataclass(frozen=True, slots=True)
class ExternalBindings:
    """Operator-selected artifacts to which an external grant is bound."""

    config: Path | None = None
    input_manifest: Path | None = None
    challenge_file: Path | None = None
    notebook_metadata: Path | None = None
    output_dir: Path | None = None
    hardware_class: str | None = None
    max_runtime_seconds: int | None = None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreflightError(message)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def check_required_paths() -> None:
    missing = sorted(path for path in REQUIRED_PATHS if not (ROOT / path).is_file())
    require(not missing, f"required paths missing: {missing}")


def check_lineage(mode: str) -> None:
    result = git("merge-base", "--is-ancestor", ANCHOR_COMMIT, "HEAD", check=False)
    require(result.returncode == 0, "HEAD must descend from the exact ARC series anchor")
    anchor_tree = git("show", "-s", "--format=%T", ANCHOR_COMMIT).stdout.strip()
    require(anchor_tree == ANCHOR_TREE, "anchor tree does not match the recorded identity")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    require(ANCHOR_COMMIT in readme and ANCHOR_TREE in readme, "README lineage missing")
    require("Christopher D. Pang" in readme, "human stewardship is not explicit")
    require("PREPARED_NOT_RUN" in readme, "README status is not prepared-not-run")
    if mode != "dev":
        require(not git("status", "--porcelain").stdout, "external modes require a clean worktree")


def check_json_and_schema_surfaces() -> None:
    # Inspect only files eligible for this commit.  Never recurse through an
    # ignored runtime/data mount merely because it happens to sit below ROOT.
    json_paths = sorted(path for path in committable_paths() if path.suffix == ".json")
    require(json_paths, "no JSON contracts found")
    for path in json_paths:
        load_json(path)

    schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
    require(len(schemas) == 9, "exactly nine owned schemas are required")
    ids: list[str] = []
    for path in schemas:
        schema = load_json(path)
        require(
            schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
            f"{path.relative_to(ROOT)} has the wrong JSON Schema draft",
        )
        schema_id = schema.get("$id")
        require(isinstance(schema_id, str) and schema_id, f"{path.relative_to(ROOT)} lacks $id")
        require(schema.get("additionalProperties") is False, f"{path.relative_to(ROOT)} is not closed")
        definitions = schema.get("$defs", {})
        require(isinstance(definitions, dict), f"{path.relative_to(ROOT)} has invalid $defs")
        stack: list[object] = [schema]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("type") == "object":
                    require(
                        node.get("additionalProperties") is False,
                        f"{path.relative_to(ROOT)} contains an open owned object",
                    )
                reference = node.get("$ref")
                if isinstance(reference, str) and reference.startswith("#/$defs/"):
                    require(
                        reference.removeprefix("#/$defs/") in definitions,
                        f"{path.relative_to(ROOT)} has an unresolved local reference",
                    )
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        ids.append(schema_id)
    require(len(ids) == len(set(ids)), "schema IDs must be unique")


def check_source_lock(mode: str) -> None:
    lock = load_json(ROOT / "provenance" / "official-sources.lock.json")
    try:
        validate_source_lock(
            lock,
            required_split="KAGGLE_HIDDEN" if mode == "kaggle" else None,
        )
    except ValidationError as exc:
        raise PreflightError(str(exc)) from exc
    require(lock.get("schema") == "hearthline-plays.arc2-source-lock.v1", "source lock schema")
    require(lock.get("recorded_at") == "2026-09-04T06:45:40Z", "source lock recording identity")
    require(lock.get("competition_slug") == COMPETITION_SLUG, "competition slug")
    require(lock.get("status") == "PREPARED_NOT_RUN", "source lock status")
    parent = lock.get("parent", {})
    require(parent.get("repository") == "Grativy6/hearthline-plays", "parent repository")
    require(parent.get("branch") == "arc-agi/main", "parent branch")
    require(parent.get("commit") == ANCHOR_COMMIT, "parent commit")
    require(parent.get("tree") == ANCHOR_TREE, "parent tree")

    sources = lock.get("git_sources")
    require(isinstance(sources, list) and len(sources) == 5, "five Git sources required")
    by_repository = {item.get("repository"): item for item in sources if isinstance(item, dict)}
    require(set(by_repository) == set(EXPECTED_GIT_SOURCES), "Git source identity set mismatch")
    require(len(by_repository) == len(sources), "Git repositories must be unique")
    for repository, expected in EXPECTED_GIT_SOURCES.items():
        source = by_repository[repository]
        observed = (
            source.get("branch"),
            source.get("commit"),
            source.get("tree"),
            source.get("license_spdx"),
            source.get("role"),
            source.get("relationship"),
        )
        require(observed == expected, f"source pin mismatch for {repository}")
        require(bool(source.get("claim_ceiling")), f"claim ceiling missing for {repository}")

    now = datetime.now(timezone.utc)
    commitments = lock.get("challenge_commitments")
    require(
        isinstance(commitments, dict)
        and set(commitments) == {"TRAINING", "PUBLIC_EVALUATION", "KAGGLE_HIDDEN"},
        "challenge commitment split set mismatch",
    )
    for split, expected in EXPECTED_PUBLIC_CHALLENGE_COMMITMENTS.items():
        require(commitments.get(split) == expected, f"source commitment mismatch for {split}")
    hidden = commitments["KAGGLE_HIDDEN"]
    require(isinstance(hidden, dict), "hidden challenge commitment must be an object")
    hidden_is_frozen = hidden.get("status") == FROZEN
    if mode == "kaggle" or (mode == "dev" and hidden_is_frozen):
        require(hidden.get("status") == FROZEN, "hidden artifact must be human-frozen")
        require(hidden.get("origin") == "KAGGLE_COMPETITION_MOUNT", "hidden origin mismatch")
        require(
            hidden.get("challenge_filename") == "arc-agi_test_challenges.json",
            "hidden challenge filename mismatch",
        )
        for field in ("challenge_raw_sha256", "challenge_semantic_sha256"):
            require(
                is_sha256(hidden.get(field)) and hidden[field] != "0" * 64,
                f"hidden {field} must be frozen",
            )
        for field in ("task_count", "test_input_count"):
            require(
                type(hidden.get(field)) is int and hidden[field] > 0,
                f"hidden {field} must be a positive integer",
            )
        require(
            hidden.get("human_reviewer") == "Christopher D. Pang",
            "hidden commitment must retain human stewardship",
        )
        retrieved = parse_utc(hidden.get("retrieval_utc"), "hidden retrieval_utc")
        revalidate_before = parse_utc(
            hidden.get("revalidate_before"), "hidden revalidate_before"
        )
        require(
            retrieved <= now < revalidate_before,
            "hidden challenge commitment is stale",
        )
    else:
        require(
            hidden
            == {
                "status": UNFROZEN,
                "origin": "KAGGLE_COMPETITION_MOUNT",
                "challenge_filename": "arc-agi_test_challenges.json",
                "challenge_raw_sha256": None,
                "challenge_semantic_sha256": None,
                "task_count": None,
                "test_input_count": None,
            },
            "non-Kaggle state must keep the hidden artifact visibly unfrozen",
        )

    rules = lock.get("rules", {})
    expected_rules = {
        "official_data_vendored": False,
        "public_eval_is_development_data": False,
        "hidden_holdout_persisted": False,
        "internet_during_evaluation": False,
        "predictions_per_test_input": 2,
        "publication_is_run_authorization": False,
    }
    require(rules == expected_rules, "source-lock rule assertions changed")

    mutable = lock.get("mutable_surfaces")
    require(isinstance(mutable, list) and len(mutable) == 7, "seven mutable sources required")
    urls = [item.get("url") for item in mutable if isinstance(item, dict)]
    require(len(urls) == len(set(urls)) == 7, "mutable source URLs must be unique")
    require(set(urls) == EXPECTED_MUTABLE_URLS, "mutable source URL set mismatch")
    mutable_statuses = {
        item.get("status") for item in mutable if isinstance(item, dict)
    }
    if mode == "dev":
        require(
            mutable_statuses in ({UNFROZEN}, {FROZEN}),
            "development inspection requires one coherent mutable-source state",
        )
    for item in mutable:
        require(isinstance(item, dict), "mutable source must be an object")
        if mode == "dev" and item.get("status") == UNFROZEN:
            require(item.get("status") == UNFROZEN, "development lock must remain visibly unfrozen")
            require(item.get("content_sha256") is None, "unreviewed web content must not have a digest")
        else:
            digest = item.get("content_sha256")
            require(item.get("status") == FROZEN, "external mode requires human-reviewed web sources")
            require(
                isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                "external mode requires exact web-source digests",
            )
            require(digest != "0" * 64, "external mode rejects placeholder web digests")
            for field in ("retrieval_utc", "human_reviewer", "revalidate_before"):
                require(bool(item.get(field)), f"frozen mutable source missing {field}")
            require(
                item.get("human_reviewer") == "Christopher D. Pang",
                "mutable source review must retain named human stewardship",
            )
            retrieved = parse_utc(item["retrieval_utc"], "mutable retrieval_utc")
            revalidate_before = parse_utc(
                item["revalidate_before"], "mutable revalidate_before"
            )
            require(retrieved <= now < revalidate_before, "mutable source review is stale")


def check_synthetic_fixtures() -> None:
    fixture_root = ROOT / "tests" / "fixtures" / "synthetic"
    manifest = load_json(fixture_root / "fixture-manifest.json")
    require(manifest.get("origin") == "SYNTHETIC_AUTHORED_FOR_CONTRACT_TESTS", "fixture origin")
    require(manifest.get("authored_by") == "Christopher D. Pang", "fixture authorship")
    require(manifest.get("official_task_bytes_copied") is False, "official fixture bytes forbidden")
    require(manifest.get("official_task_transform_used") is False, "official task transforms forbidden")
    entries = manifest.get("files")
    require(isinstance(entries, list) and len(entries) == 3, "fixture manifest file count")
    for entry in entries:
        path = fixture_root / entry["path"]
        require(path.is_file(), f"fixture file missing: {entry['path']}")
        require(sha256_path(path) == entry.get("sha256"), f"fixture digest mismatch: {entry['path']}")

    challenges = validate_challenge_set(load_json(fixture_root / "challenges.json"))
    validate_solution_set(challenges, load_json(fixture_root / "solutions.json"))
    validate_submission(challenges, load_json(fixture_root / "submission.json"))
    require(sum(len(task.test_inputs) for task in challenges.values()) == 3, "synthetic weighting fixture changed")


def check_grant_templates() -> None:
    templates = {
        "public-eval-grant.template.json": (
            "PUBLIC_EVAL_ONCE",
            PUBLIC_ACKNOWLEDGEMENT,
        ),
        "kaggle-run-grant.template.json": (
            "KAGGLE_NOTEBOOK_RUN_ONCE",
            KAGGLE_RUN_ACKNOWLEDGEMENT,
        ),
        "kaggle-submit-grant.template.json": (
            "KAGGLE_SUBMIT_ONCE",
            KAGGLE_SUBMIT_ACKNOWLEDGEMENT,
        ),
    }
    for filename, (scope, acknowledgement) in templates.items():
        grant = load_json(ROOT / "ignition" / filename)
        require(isinstance(grant, dict), f"{filename} must be an object")
        require(
            set(grant) == GRANT_BASE_KEYS | GRANT_SCOPE_FIELDS[scope],
            f"{filename} fields do not match {scope}",
        )
        require(grant.get("scope") == scope, f"{filename} scope mismatch")
        require(
            grant.get("acknowledgement") == acknowledgement,
            f"{filename} acknowledgement mismatch",
        )
        require(
            str(grant.get("grant_id", "")).startswith("TEMPLATE_"),
            f"{filename} must retain an obvious placeholder ID",
        )
        require(grant.get("nonce") == "0" * 64, f"{filename} nonce must be a placeholder")
        if scope == "PUBLIC_EVAL_ONCE":
            require(
                grant.get("solution_semantic_sha256")
                == EXPECTED_PUBLIC_CHALLENGE_COMMITMENTS["PUBLIC_EVALUATION"][
                    "solution_semantic_sha256"
                ],
                "public-eval template solution commitment mismatch",
            )


def check_method_map() -> None:
    text = (ROOT / "docs" / "ARC2_METHOD_MAP.md").read_text(encoding="utf-8")
    required = {
        "every method is off by",
        "A0BK advisory gate",
        "FBT continuation split",
        "GOLD `1+5` / new-geometry lens",
        "PAL role ledger",
        "Single Cut checkpoint",
        "Distinction grouping",
        "`advance` atomic promotion",
        "Paired Sparks",
        "Thulia custody",
        "no executable method switch",
        "not implemented solver features",
    }
    missing = sorted(marker for marker in required if marker not in text)
    require(not missing, f"bounded method-map markers missing: {missing}")


def check_synthetic_pipeline() -> None:
    """Exercise build, canonical serialization, and score twice without public data."""

    fixture_root = ROOT / "tests" / "fixtures" / "synthetic"
    challenge_json = load_json(fixture_root / "challenges.json")
    solutions = load_json(fixture_root / "solutions.json")
    committed_submission = load_json(fixture_root / "submission.json")
    solver = IdentityZeroBaseline()

    first = build_submission(challenge_json, solver, seed=0)
    second = build_submission(
        dict(reversed(list(challenge_json.items()))), solver, seed=0
    )
    first_bytes = canonical_json_bytes(first)
    second_bytes = canonical_json_bytes(second)
    require(first_bytes == second_bytes, "synthetic output is not byte-deterministic")
    require(first == committed_submission, "committed synthetic submission drifted from baseline")

    result = score_submission(challenge_json, solutions, first)
    require(
        (result.numerator, result.denominator) == (1, 3),
        "scorer must weight test outputs as exactly 1/3 in the regression fixture",
    )
    require(result.score_numerator == 1 and result.score_denominator == 3, "exact score drift")


def check_unit_tests() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_*.py",
        ],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    require(
        completed.returncode == 0,
        "synthetic unit tests failed: "
        + (completed.stderr.strip() or completed.stdout.strip()),
    )


def check_python_compiles() -> None:
    paths = sorted(
        [*(ROOT / "src").rglob("*.py"), *(ROOT / "tools").glob("*.py"), *(ROOT / "tests").glob("*.py")]
    )
    require(paths, "no Python implementation found")
    for path in paths:
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")


def committable_paths() -> list[Path]:
    result = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return [
        ROOT / item
        for item in result.stdout.split("\0")
        if item and (ROOT / item).is_file()
    ]


def check_repository_boundary() -> None:
    candidates = committable_paths()
    require(candidates, "no committable repository paths found")
    forbidden_roots = {
        "data",
        "environment_files",
        "models",
        "outputs",
        "receipts",
        "reference",
        "references",
        "runs",
        "vendor",
    }
    forbidden_names = {
        ".env",
        "arc-agi_training_challenges.json",
        "arc-agi_training_solutions.json",
        "arc-agi_evaluation_challenges.json",
        "arc-agi_evaluation_solutions.json",
        "arc-agi_test_challenges.json",
        "arc-agi_test_solutions.json",
        "sample_submission.json",
        "kernel-metadata.json",
    }
    violations: list[str] = []
    secret_patterns = (
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"(?m)^(?:KAGGLE_KEY|OPENAI_API_KEY|ARC_API_KEY)\s*=\s*\S+"),
    )
    for path in candidates:
        relative = path.relative_to(ROOT)
        if relative.parts and relative.parts[0] in forbidden_roots:
            violations.append(f"forbidden runtime root: {relative}")
        if path.name in forbidden_names:
            violations.append(f"forbidden artifact filename: {relative}")
        if relative.parts[:2] == ("ignition", "grants"):
            violations.append(f"forbidden runtime grant: {relative}")
        if relative.parts[:2] == ("ignition", "consumption-ledger"):
            violations.append(f"forbidden consumption record: {relative}")
        if path.name.startswith(".env"):
            violations.append(f"forbidden environment file: {relative}")
        if relative.parts and relative.parts[0].startswith(".venv-"):
            violations.append(f"forbidden virtual environment: {relative}")
        if path.suffix.lower() in {".pem", ".key"}:
            violations.append(f"forbidden key file: {relative}")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for pattern in secret_patterns:
            if pattern.search(text):
                violations.append(f"secret-like material: {relative}")
    require(not violations, "; ".join(violations))


def notebook_code(notebook: dict[str, Any]) -> str:
    parts: list[str] = []
    for cell in notebook.get("cells", []):
        require(isinstance(cell, dict), "notebook cell must be an object")
        if cell.get("cell_type") != "code":
            continue
        require(cell.get("execution_count") is None, "notebook execution counts must be clear")
        require(cell.get("outputs") == [], "notebook outputs must be clear")
        source = cell.get("source", [])
        require(isinstance(source, list) and all(isinstance(line, str) for line in source), "notebook source")
        parts.extend(source)
    return "".join(parts)


def check_notebook(
    mode: str,
    metadata_path: Path | None = None,
    *,
    hardware_class: str | None = None,
    max_runtime_seconds: int | None = None,
) -> None:
    if mode in {"dev", "public-eval"}:
        require(
            metadata_path is None,
            f"{mode} mode uses only the tracked metadata template",
        )
        selected_metadata = ROOT / "notebook" / "kernel-metadata.template.json"
    else:
        require(metadata_path is not None, "external mode requires --notebook-metadata")
        selected_metadata = metadata_path
    try:
        metadata = validate_kernel_metadata(
            load_json(selected_metadata),
            "$.kernel_metadata",
            allow_placeholder_id=mode in {"dev", "public-eval"},
        )
    except ValidationError as exc:
        raise PreflightError(str(exc)) from exc
    if mode == "kaggle":
        expected_hardware = kernel_metadata_hardware_class(metadata)
        require(
            hardware_class == expected_hardware,
            "selected hardware class does not match Kaggle metadata",
        )
        if metadata["enable_gpu"]:
            require(
                type(max_runtime_seconds) is int
                and 1 <= max_runtime_seconds < 43200,
                "accelerator runs require a runtime below the 12-hour ceiling",
            )

    notebook = load_json(ROOT / "notebook" / "arc2_submission.ipynb")
    require(notebook.get("nbformat") == 4, "notebook must use nbformat 4")
    kaggle_metadata = notebook.get("metadata", {}).get("kaggle", {})
    require(kaggle_metadata.get("isInternetEnabled") is False, "embedded notebook internet must be disabled")
    require(type(kaggle_metadata.get("isGpuEnabled")) is bool, "embedded GPU flag must be boolean")
    require(
        kaggle_metadata.get("isGpuEnabled") == metadata["enable_gpu"],
        "notebook and external metadata accelerator settings differ",
    )
    require(
        kaggle_metadata.get("accelerator")
        == ("gpu" if metadata["enable_gpu"] else "none"),
        "embedded notebook accelerator class differs from external metadata",
    )
    require(
        kaggle_metadata.get("dataSources")
        == [{"sourceId": COMPETITION_SLUG, "sourceType": "competition"}],
        "embedded notebook competition source mismatch",
    )
    code = notebook_code(notebook)
    compile(code, "notebook/arc2_submission.ipynb", "exec")
    forbidden = (
        "pip" + " install",
        "curl" + " ",
        "wget" + " ",
        "git" + " clone",
        "import " + "requests",
        "import " + "socket",
        "url" + "lib",
        "kaggle " + "competitions",
        "kaggle " + "kernels",
    )
    require(not any(token in code for token in forbidden), "notebook contains a network or platform action")
    require("print(" not in code, "notebook must not print task or prediction material")
    require("/kaggle/working/submission.json" in code, "notebook output path is not exact")
    require("attempt_1" in code and "attempt_2" in code, "two-attempt contract absent from notebook")
    require("validate_submission(challenges, sample)" in code, "sample two-attempt validation absent")
    require("if not SAMPLE_PATH.is_file()" in code, "sample submission must be mandatory")
    require("if SAMPLE_PATH.exists()" not in code, "sample submission cannot be optional")
    require("11 * 60 * 60" in code, "notebook lacks margin below the observed 12-hour ceiling")


def check_no_external_capability() -> None:
    paths = sorted([*(ROOT / "src").rglob("*.py"), *(ROOT / "tools").glob("*.py")])
    forbidden_imports = (
        re.compile(r"(?m)^\s*(?:from|import)\s+(?:requests|urllib|httpx|socket|kaggle)\b"),
    )
    for path in paths:
        if path.name == "preflight.py":
            continue
        text = path.read_text(encoding="utf-8")
        require(
            not any(pattern.search(text) for pattern in forbidden_imports),
            f"external-capability import in {path.relative_to(ROOT)}",
        )
        require("hearthline_arc2.scoring" not in text or path.name == "score_local.py", f"scoring import crosses runner boundary in {path.relative_to(ROOT)}")

    for relative in (
        Path("src/hearthline_arc2/contracts.py"),
        Path("src/hearthline_arc2/runner.py"),
    ):
        path = ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                require(
                    not (node.module or "").endswith("scoring"),
                    f"solver-side scoring import in {relative}",
                )
            elif isinstance(node, ast.Import):
                require(
                    all(not alias.name.endswith("scoring") for alias in node.names),
                    f"solver-side scoring import in {relative}",
                )

    parameters = inspect.signature(StaticSolver.solve).parameters
    require(
        tuple(parameters) == ("self", "task", "seed", "budget"),
        "StaticSolver.solve surface changed",
    )
    forbidden_parameters = {"solution", "solutions", "label", "labels", "score", "correctness"}
    require(
        forbidden_parameters.isdisjoint(parameters),
        "StaticSolver.solve accepts correctness information",
    )
    builder = (ROOT / "tools" / "build_submission.py").read_text(encoding="utf-8")
    require(
        'choices=("SYNTHETIC", "TRAIN_CV")' in builder,
        "generic builder must not expose public or hidden evaluation modes",
    )
    scorer = (ROOT / "tools" / "score_local.py").read_text(encoding="utf-8")
    require('"--mode"' in scorer and 'required=True' in scorer, "score mode must be explicit")
    require("--synthetic" not in scorer, "legacy inferred score mode remains available")
    own_source = Path(__file__).read_text(encoding="utf-8")
    redirect_option = "--consumption" + "-dir"
    require(
        redirect_option not in own_source,
        "preflight ledger location must not be CLI-redirectable",
    )


def parse_utc(value: object, field: str) -> datetime:
    require(
        isinstance(value, str) and UTC_PATTERN.fullmatch(value) is not None,
        f"{field} must be an RFC-3339 UTC Z time",
    )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PreflightError(f"{field} is not an ISO-8601 time") from exc
    require(parsed.tzinfo is not None, f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def sha256_named_sources(paths: list[Path]) -> str:
    """Match the builder's deterministic solver-source identity algorithm."""

    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def check_external_bindings(mode: str, bindings: ExternalBindings) -> None:
    require(bindings.config is not None and bindings.config.is_file(), "external mode requires --config")
    require(
        bindings.input_manifest is not None and bindings.input_manifest.is_file(),
        "external mode requires --input-manifest",
    )
    require(
        bindings.challenge_file is not None and bindings.challenge_file.is_file(),
        "external mode requires --challenge-file",
    )
    require(
        isinstance(bindings.hardware_class, str) and bool(bindings.hardware_class.strip()),
        "external mode requires --hardware-class",
    )
    require(
        type(bindings.max_runtime_seconds) is int
        and 1 <= bindings.max_runtime_seconds <= 43200,
        "external mode requires --max-runtime-seconds in 1..43200",
    )
    require(bindings.config is not None, "external mode requires --config")
    require(bindings.input_manifest is not None, "external mode requires --input-manifest")
    require(bindings.challenge_file is not None, "external mode requires --challenge-file")
    try:
        config = validate_solver_config(
            load_json(bindings.config),
            "$.config",
            expected_hardware_class=bindings.hardware_class,
            expected_max_runtime_seconds=bindings.max_runtime_seconds,
            expected_solver_id=IdentityZeroBaseline.solver_id,
        )
        validate_input_manifest(
            load_json(bindings.input_manifest),
            "$.input_manifest",
            source_lock_path=ROOT / "provenance" / "official-sources.lock.json",
            expected_split=(
                "PUBLIC_EVALUATION"
                if mode == "public-eval"
                else "KAGGLE_HIDDEN"
            ),
        )
    except ValidationError as exc:
        raise PreflightError(str(exc)) from exc
    if mode == "public-eval":
        require(
            bindings.notebook_metadata is None,
            "public-eval does not accept notebook metadata",
        )
        require(bindings.output_dir is not None, "public-eval requires --output-dir")
        output = bindings.output_dir.resolve()
        try:
            output.relative_to(ROOT.resolve())
        except ValueError:
            pass
        else:
            raise PreflightError("public-eval output directory must be outside repository")
    else:
        require(
            bindings.notebook_metadata is not None
            and bindings.notebook_metadata.is_file(),
            "kaggle mode requires --notebook-metadata",
        )
        try:
            metadata = validate_kernel_metadata(
                load_json(bindings.notebook_metadata),
                "$.kernel_metadata",
            )
        except ValidationError as exc:
            raise PreflightError(str(exc)) from exc
        require(
            kernel_metadata_hardware_class(metadata) == bindings.hardware_class,
            "selected hardware class does not match Kaggle metadata",
        )
        require(
            config["model_identities"] == metadata["model_sources"] == [],
            "baseline model identities and Kaggle model sources must remain frozen empty",
        )
        require(
            bindings.max_runtime_seconds is not None
            and bindings.max_runtime_seconds < 43200,
            "Kaggle runs require shutdown margin below the observed 12-hour ceiling",
        )
        require(bindings.output_dir is None, "kaggle packaging does not accept --output-dir")


def check_external_challenge_binding(mode: str, bindings: ExternalBindings) -> None:
    """Open the label-free challenge only after the relevant grant is spent."""

    require(mode in {"public-eval", "kaggle"}, "challenge binding is external-only")
    require(bindings.input_manifest is not None, "missing input-manifest binding")
    require(bindings.challenge_file is not None, "missing challenge-file binding")
    try:
        validate_input_manifest(
            load_json(bindings.input_manifest),
            "$.input_manifest",
            challenge_path=bindings.challenge_file,
            source_lock_path=ROOT / "provenance" / "official-sources.lock.json",
            expected_split=(
                "PUBLIC_EVALUATION" if mode == "public-eval" else "KAGGLE_HIDDEN"
            ),
        )
    except ValidationError as exc:
        raise PreflightError(
            "external challenge does not match its sealed input manifest"
        ) from exc


def check_grant(
    mode: str,
    grant_path: Path | None,
    bindings: ExternalBindings,
) -> dict[str, Any] | None:
    if mode == "dev":
        require(grant_path is None, "development mode does not consume a human grant")
        return None

    check_external_bindings(mode, bindings)
    require(grant_path is not None and grant_path.is_file(), f"{mode} mode requires --grant")
    grant = load_json(grant_path)
    require(isinstance(grant, dict), "grant must be an object")
    expected_scope = (
        "PUBLIC_EVAL_ONCE" if mode == "public-eval" else "KAGGLE_NOTEBOOK_RUN_ONCE"
    )
    expected_keys = GRANT_BASE_KEYS | GRANT_SCOPE_FIELDS[expected_scope]
    require(set(grant) == expected_keys, "grant keys do not exactly match its narrow scope")
    require(
        grant.get("schema") == "hearthline-plays.arc2-ignition-grant.v1",
        "grant schema",
    )
    require(grant.get("scope") == expected_scope, "grant scope mismatch")
    require(grant.get("competition_slug") == COMPETITION_SLUG, "grant competition mismatch")
    require(grant.get("human_approver") == "Christopher D. Pang", "human approver mismatch")
    expected_acknowledgement = (
        PUBLIC_ACKNOWLEDGEMENT if mode == "public-eval" else KAGGLE_RUN_ACKNOWLEDGEMENT
    )
    require(
        grant.get("acknowledgement") == expected_acknowledgement,
        "grant acknowledgement does not match scope",
    )
    require(
        isinstance(grant.get("grant_id"), str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", grant["grant_id"])
        is not None,
        "invalid grant ID",
    )
    for field in (
        "source_lock_sha256",
        "notebook_sha256",
        "solver_code_sha256",
        "config_sha256",
        "input_manifest_sha256",
        "nonce",
    ):
        require(is_sha256(grant.get(field)), f"grant {field} is not a SHA-256")
        require(grant[field] != "0" * 64, f"placeholder grant {field} is forbidden")

    now = datetime.now(timezone.utc)
    issued_at = parse_utc(grant.get("issued_at"), "grant issued_at")
    expires_at = parse_utc(grant.get("expires_at"), "grant expires_at")
    require(issued_at < expires_at, "grant expiry must follow issue time")
    require(issued_at <= now < expires_at, "grant is not currently valid")

    head_commit = git("rev-parse", "HEAD").stdout.strip()
    head_tree = git("rev-parse", "HEAD^{tree}").stdout.strip()
    require(grant.get("branch_commit") == head_commit, "grant branch commit mismatch")
    require(grant.get("branch_tree") == head_tree, "grant branch tree mismatch")
    require(
        grant.get("source_lock_sha256")
        == sha256_path(ROOT / "provenance" / "official-sources.lock.json"),
        "grant source-lock hash mismatch",
    )
    require(
        grant.get("notebook_sha256")
        == sha256_path(ROOT / "notebook" / "arc2_submission.ipynb"),
        "grant notebook hash mismatch",
    )
    solver_hash = sha256_named_sources(
        [
            ROOT / "src" / "hearthline_arc2" / "contracts.py",
            ROOT / "src" / "hearthline_arc2" / "runner.py",
            ROOT / "src" / "hearthline_arc2" / "validation.py",
        ]
    )
    require(grant.get("solver_code_sha256") == solver_hash, "grant solver hash mismatch")
    require(bindings.config is not None, "missing config binding")
    require(bindings.input_manifest is not None, "missing input-manifest binding")
    require(grant.get("config_sha256") == sha256_path(bindings.config), "grant config hash mismatch")
    require(
        grant.get("input_manifest_sha256") == sha256_path(bindings.input_manifest),
        "grant input-manifest hash mismatch",
    )
    require(grant.get("hardware_class") == bindings.hardware_class, "grant hardware mismatch")
    require(
        type(grant.get("max_runtime_seconds")) is int
        and grant["max_runtime_seconds"] == bindings.max_runtime_seconds,
        "grant runtime mismatch",
    )
    if mode == "kaggle":
        require(
            is_sha256(grant.get("notebook_metadata_sha256")),
            "grant notebook metadata hash is missing",
        )
        require(
            grant["notebook_metadata_sha256"] != "0" * 64,
            "placeholder notebook metadata hash is forbidden",
        )
        require(bindings.notebook_metadata is not None, "missing notebook metadata binding")
        require(
            grant["notebook_metadata_sha256"]
            == sha256_path(bindings.notebook_metadata),
            "grant notebook metadata hash mismatch",
        )
        require(is_sha256(grant.get("rules_sha256")), "grant rules hash is missing")
        require(grant["rules_sha256"] != "0" * 64, "placeholder rules hash is forbidden")
        source_lock = load_json(ROOT / "provenance" / "official-sources.lock.json")
        rules_surface = next(
            item
            for item in source_lock["mutable_surfaces"]
            if item["url"].endswith("/rules")
        )
        require(
            grant["rules_sha256"] == rules_surface["content_sha256"],
            "grant rules hash mismatch",
        )
    else:
        require(bindings.output_dir is not None, "missing public-evaluation output directory")
        run_manifest_path = bindings.output_dir / "run-manifest.json"
        submission_path = bindings.output_dir / "submission.json"
        require(run_manifest_path.is_file(), "public-eval run manifest is missing")
        require(submission_path.is_file(), "public-eval submission is missing")
        for field, artifact in (
            ("run_manifest_sha256", run_manifest_path),
            ("submission_sha256", submission_path),
        ):
            require(is_sha256(grant.get(field)), f"grant {field} is not a SHA-256")
            require(grant[field] != "0" * 64, f"placeholder grant {field} is forbidden")
            require(grant[field] == sha256_path(artifact), f"grant {field} mismatch")
        try:
            run_manifest = validate_run_manifest(load_json(run_manifest_path))
            config = validate_solver_config(
                load_json(bindings.config),
                "$.config",
                expected_hardware_class=bindings.hardware_class,
                expected_max_runtime_seconds=bindings.max_runtime_seconds,
                expected_solver_id=IdentityZeroBaseline.solver_id,
            )
            input_manifest = validate_input_manifest(
                load_json(bindings.input_manifest),
                "$.input_manifest",
                source_lock_path=ROOT / "provenance" / "official-sources.lock.json",
                expected_split="PUBLIC_EVALUATION",
            )
        except (RunnerError, ValidationError) as exc:
            raise PreflightError("public-evaluation run binding is invalid") from exc
        expected_run = {
            "mode": "PUBLIC_EVAL",
            "source_lock_sha256": grant["source_lock_sha256"],
            "branch_commit": grant["branch_commit"],
            "branch_tree": grant["branch_tree"],
            "solver_id": config["solver_id"],
            "solver_code_sha256": grant["solver_code_sha256"],
            "config_sha256": grant["config_sha256"],
            "input_manifest_sha256": grant["input_manifest_sha256"],
            "submission_sha256": grant["submission_sha256"],
            "wall_budget_seconds": config["wall_budget_seconds"],
            "cpu_budget_seconds": config["cpu_budget_seconds"],
            "dependency_identities": config["dependency_identities"],
            "model_identities": config["model_identities"],
            "discovered_task_count": input_manifest["task_count"],
            "discovered_test_input_count": input_manifest["test_input_count"],
        }
        for field, expected in expected_run.items():
            require(run_manifest.get(field) == expected, f"run manifest {field} mismatch")
        require(
            run_manifest["seed_policy"]
            == f"fixed integer seed {config['seed']}; identical seed passed once per task",
            "run manifest seed policy mismatch",
        )
        run_started = parse_utc(run_manifest["started_at"], "run started_at")
        run_finished = parse_utc(run_manifest["finished_at"], "run finished_at")
        require(
            run_started <= run_finished <= issued_at,
            "public run must be frozen before its grant is issued",
        )
        require(
            is_sha256(grant.get("solution_semantic_sha256"))
            and grant["solution_semantic_sha256"] != "0" * 64,
            "grant solution semantic hash is invalid",
        )
        source_lock = load_json(ROOT / "provenance" / "official-sources.lock.json")
        public_commitment = source_lock.get("challenge_commitments", {}).get(
            "PUBLIC_EVALUATION", {}
        )
        require(
            grant["solution_semantic_sha256"]
            == public_commitment.get("solution_semantic_sha256"),
            "grant solution identity does not match the source lock",
        )

    assert_unspent(grant, CANONICAL_LEDGER)
    return grant


def run(
    mode: str,
    grant_path: Path | None,
    bindings: ExternalBindings | None = None,
) -> None:
    selected_bindings = bindings or ExternalBindings()
    checks = (
        ("required_paths", check_required_paths),
        ("lineage", lambda: check_lineage(mode)),
        ("json_and_schemas", check_json_and_schema_surfaces),
        ("source_lock", lambda: check_source_lock(mode)),
        ("synthetic_fixtures", check_synthetic_fixtures),
        ("grant_templates", check_grant_templates),
        ("bounded_method_map", check_method_map),
        ("python_compile", check_python_compiles),
        ("synthetic_unit_tests", check_unit_tests),
        ("deterministic_build_and_score", check_synthetic_pipeline),
        ("repository_boundary", check_repository_boundary),
        (
            "notebook",
            lambda: check_notebook(
                mode,
                selected_bindings.notebook_metadata,
                hardware_class=selected_bindings.hardware_class,
                max_runtime_seconds=selected_bindings.max_runtime_seconds,
            ),
        ),
        ("no_external_capability", check_no_external_capability),
    )
    for name, check in checks:
        check()
        print(f"PASS {name}")
    grant = check_grant(mode, grant_path, selected_bindings)
    print("PASS human_grant")
    if mode == "dev":
        print("ARC2_READINESS_CONFORMANT_PREPARED_NOT_RUN")
    else:
        require(grant is not None, "external grant disappeared")
        record_preflight_consumption(grant, CANONICAL_LEDGER)
        print("PASS grant_reserved")
        check_external_challenge_binding(mode, selected_bindings)
        print("PASS challenge_binding")
        complete_preflight_consumption(grant, CANONICAL_LEDGER)
        print("PASS grant_completed")
        print(f"ARC2_{mode.upper().replace('-', '_')}_PACKAGE_CONFORMANT_NOT_RUN")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("dev", "public-eval", "kaggle"), default="dev")
    parser.add_argument("--grant", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        help="closed solver identity, deterministic budget, hardware, and source config",
    )
    parser.add_argument(
        "--input-manifest",
        type=Path,
        help=(
            "closed external manifest binding raw/semantic challenge identity, "
            "counts, split/filename, and the split-specific source commitment"
        ),
    )
    parser.add_argument(
        "--challenge-file",
        type=Path,
        help=(
            "label-free challenge whose raw and semantic digests, byte count, "
            "exact filename, task count, and test-input count must match the manifest"
        ),
    )
    parser.add_argument("--notebook-metadata", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--hardware-class")
    parser.add_argument("--max-runtime-seconds", type=int)
    args = parser.parse_args()
    try:
        run(
            args.mode,
            args.grant,
            ExternalBindings(
                config=args.config,
                input_manifest=args.input_manifest,
                challenge_file=args.challenge_file,
                notebook_metadata=args.notebook_metadata,
                output_dir=args.output_dir,
                hardware_class=args.hardware_class,
                max_runtime_seconds=args.max_runtime_seconds,
            ),
        )
    except (
        AuthorizationError,
        PreflightError,
        OSError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
