#!/usr/bin/env python3
"""Fail-closed, standard-library checks for the Hearthline ARC launchpad."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

SOURCE_LOCK_V4_SHA256 = "bc14dfc3e849518177c48066a3df5782f66bc00525e4ef6b7a9dde60ddebcdbd"
SOURCE_LOCK_V3_SHA256 = "900965eb497a0260e165976c80793c97c605e15f38ec89b55afef593a5c0478d"
RUNTIME_INVENTORY_SHA256 = "17bfcc2ab86fd8cd3ba4a664ce0220f93c5cab008dd7336e0b7db7b88941b2ce"
RUNTIME_REVIEW_RECEIPT_SHA256 = "ad351aefdc18461bcf297d7095f8a77daa2641c583498cfad1b9f9b25a64206b"
RUNTIME_EVIDENCE_MANIFEST_SHA256 = "b4dd87fe2a0a17e8083bdcfb81a1be2b191fb45776e33e234d369c8918e93b06"
RUNTIME_LOGS_SHA256 = "1471812acc99ca75ca234ea7defd727128a43869bea26e4e91a8577dd062eb53"
RUNTIME_REVIEW_RECEIPT = "launch/receipts/20260907T002817Z-stage-v4-runtime-review.json"
RUNTIME_INVENTORY = "launch/runtime/kaggle-stage-v4-runtime-inventory.json"

PUBLIC_AGENTS_FILES = {
    "agents/agent.py": "49f1a349cd5e2123fceb266aec4a3a758d18ef5520e0212e808f695905d9e073",
    "agents/recorder.py": "0a08d89f4067a760012767c05d4406bd2bf409f426e29a1193106abfcbb696c8",
    "agents/swarm.py": "d9dc48f710f1b90a6552db0921293c7e89c8a925ed00a3faefa07ae19998ad39",
    "agents/tracing.py": "951ca56508c524504e116303f7c64f4eb5cf723c72cab892d4d1a3292b1cc51f",
    "main.py": "864254c750bbbd12a211f2d8aa1b1025d0609283f07dea4ede83722f2435301b",
}
RUNTIME_AGENTS_FILES = {
    **PUBLIC_AGENTS_FILES,
    "agents/agent.py": "85655f7a11a105e50bba76efd00bebf8056d02ddbae827a8f8a5b46e849fc087",
}
AGENTS_LICENSE_SHA256 = "75c4276c506fd93082b38ad39f67ee97aa859574401ef978e701710c7a40af04"
RUNTIME_REQUIRED_VERSIONS = {
    "arc-agi": "0.9.8",
    "arcengine": "0.9.3",
    "python-dotenv": "1.2.2",
}


class ValidationError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{path}: {exc}") from exc


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValidationError(f"non-finite JSON number is forbidden: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if parsed == float("inf") or parsed == float("-inf"):
        _reject_nonfinite(value)
    return parsed


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def unique(values: list[Any], label: str) -> None:
    require(len(values) == len(set(values)), f"{label} must be unique")


def exact_keys(value: Any, expected: set[str], label: str) -> None:
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) == expected, f"{label} fields")


def canonical_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _validate_runtime_inventory(inventory: dict[str, Any]) -> None:
    exact_keys(
        inventory,
        {"agents_files", "agents_license_file", "distributions", "python_version"},
        "runtime inventory",
    )
    require(inventory["python_version"] == "3.12.13", "runtime inventory Python version")
    require(inventory["agents_files"] == RUNTIME_AGENTS_FILES, "runtime inventory Agents files")
    require(
        inventory["agents_license_file"] == {"LICENSE": AGENTS_LICENSE_SHA256},
        "runtime inventory Agents LICENSE",
    )
    distributions = inventory["distributions"]
    require(isinstance(distributions, list), "runtime distributions must be a list")
    require(len(distributions) == 875, "runtime distribution count")
    for index, row in enumerate(distributions):
        exact_keys(row, {"name", "version"}, f"runtime distribution {index}")
        require(isinstance(row["name"], str) and row["name"], f"runtime distribution {index} name")
        require(isinstance(row["version"], str) and row["version"], f"runtime distribution {index} version")
        require(
            row["name"] == canonical_distribution_name(row["name"]),
            f"runtime distribution {index} name must be canonical",
        )
    names = [row["name"] for row in distributions]
    unique(names, "runtime distribution canonical names")
    require(names == sorted(names), "runtime distribution canonical names must be sorted")
    versions = {row["name"]: row["version"] for row in distributions}
    require(
        {name: versions.get(name) for name in RUNTIME_REQUIRED_VERSIONS}
        == RUNTIME_REQUIRED_VERSIONS,
        "runtime required distribution versions",
    )


def _validate_source_lock(
    data: dict[str, Any],
    inventory: dict[str, Any],
    review_receipt: dict[str, Any],
    *,
    inventory_digest: str,
    review_receipt_digest: str,
) -> None:
    exact_keys(
        data,
        {
            "schema", "recorded_at", "status", "steward", "predecessor",
            "candidate_base", "official_software", "competition_contract",
            "credential_contract", "dependency_resolution",
            "bounded_context_sources", "run_rules", "residuals",
        },
        "source lock",
    )
    require(data["schema"] == "hearthline-plays.arc3-launch-source-lock.v4", "source lock schema")
    require(data["status"] == "FROZEN_POST_STAGE_SUCCESSOR_LOCAL_REPAIR_ONLY", "source lock status")
    require(
        data["predecessor"]
        == {
            "path": "launch/source-lock.v3.json",
            "sha256": SOURCE_LOCK_V3_SHA256,
            "treatment": "pre-stage runtime-closure lock; preserved byte-for-byte",
        },
        "source lock predecessor",
    )
    repos = data["official_software"]
    require(isinstance(repos, list) and len(repos) == 6, "official software inventory")
    unique([row["repository"] for row in repos], "official_software.repository")
    starter = next(row for row in repos if row["repository"] == "arcprize/ARC-AGI-3-Kaggle-Starter")
    require(starter["upstream_file_vendored"] is False, "official starter file must not be vendored")
    require(starter["interoperability_literals_reexpressed"] is True, "starter interface provenance")
    require(starter["license_or_notice_file_observed_at_pin"] is False, "starter license observation")
    require(
        all(
            row.get("bytes_copied") is False
            for row in repos
            if row is not starter
            and row.get("repository") != "arcprize/ARC-AGI-3-Agents"
        ),
        "non-Agents official source bytes must not be copied",
    )
    identities = {row["repository"]: row["commit"] for row in repos}
    require(identities["arcprize/ARC-AGI-3-Kaggle-Starter"] == "eeb1535404f321d280a8f9194bbc1d7aca5f05fc", "starter commit")
    require(identities["arcprize/ARC-AGI"] == "f12822c4d550121c35a275008d964afbbed47d2f", "ARC-AGI public source commit")
    require(identities["arcprize/ARC-AGI-3-Agents"] == "4743e7d0aaae0ded0d98a89a7e282e63564cd58b", "Agents commit")
    require(identities["arcprize/arc-agi-3-benchmarking"] == "1aa78da7e3058e0ead572ede7cd97065d1e5befc", "benchmark commit")
    require(identities["Kaggle/kaggle-api"] == "659469c4185cfca0fb3be01edad6f50277528d9d", "Kaggle CLI commit")
    toolkit = next(row for row in repos if row["repository"] == "arcprize/ARC-AGI")
    require(toolkit["tree"] == "9ee140e4183df0df109cec50b7cd0d2531c47168", "ARC-AGI public source tree")
    require(toolkit["version"] == "0.9.9", "ARC-AGI public source version")
    require(
        data["dependency_resolution"]["required_runtime_versions"]
        == RUNTIME_REQUIRED_VERSIONS,
        "contest wheelhouse runtime versions",
    )
    agents = next(row for row in repos if row["repository"] == "arcprize/ARC-AGI-3-Agents")
    require(
        {path: binding["sha256"] for path, binding in agents["inspected_file_bindings"].items()}
        == PUBLIC_AGENTS_FILES,
        "Agents controlling-file bindings",
    )
    require(
        agents["license_file_binding"] == {
            "path": "LICENSE",
            "git_blob": "d8e1cd42ac40338c6c76a8a6ac18eea0eaf95fbe",
            "sha256": "75c4276c506fd93082b38ad39f67ee97aa859574401ef978e701710c7a40af04",
            "spdx": "MIT",
            "copyright_notice": "Copyright (c) 2025 ARC Prize",
        },
        "Agents MIT license binding",
    )
    require("LICENSE" in agents["runtime_license_preservation"], "Agents runtime license preservation")
    require(agents.get("bytes_copied") is True, "Agents test fixture copy must be disclosed")
    require(
        (ROOT / ".gitattributes").read_text(encoding="utf-8")
        == (
            "tests/fixtures/*.blob -text\n"
            "launch/source-lock.v4.json -text\n"
            "launch/runtime/kaggle-stage-v4-runtime-inventory.json -text\n"
            "launch/receipts/20260907T002817Z-stage-v4-runtime-review.json -text\n"
            "launch/gates/stage-result.v4.template.json -text\n"
            "launch/schemas/v4/stage-result.schema.json -text\n"
        ),
        "sealed evidence and fixture line-ending policy",
    )
    fixture = agents.get("repository_fixture")
    require(
        fixture == {
            "path": "tests/fixtures/agents-main-4743e7d0.blob",
            "sha256": "864254c750bbbd12a211f2d8aa1b1025d0609283f07dea4ede83722f2435301b",
            "upstream_git_blob": "4a071bc3a4ce1dab94f754a617e5c1e70d9f907b",
            "purpose": "non-executable exact-byte fixture for offline Git-blob/SHA-256 pairing regression only",
            "license_copy": "tests/fixtures/ARC-AGI-3-Agents-LICENSE.txt",
            "license_copy_sha256": "cd95f6fb04cbe8f172890cf3746bb57295d131eb110bb78c1a0a528ea8acf87d",
            "license_copy_note": "MIT license text with one terminal POSIX newline",
        },
        "Agents exact-byte fixture disclosure",
    )
    fixture_bytes = (ROOT / fixture["path"]).read_bytes()
    require(sha256(ROOT / fixture["path"]) == fixture["sha256"], "Agents fixture SHA-256")
    framed = b"blob " + str(len(fixture_bytes)).encode("ascii") + b"\0" + fixture_bytes
    require(hashlib.sha1(framed).hexdigest() == fixture["upstream_git_blob"], "Agents fixture Git blob")
    require(
        sha256(ROOT / fixture["license_copy"]) == fixture["license_copy_sha256"],
        "Agents fixture license copy",
    )
    context = {row["source_id"]: row for row in data["bounded_context_sources"]}
    for source_id in ("fbt-synthesis-v0.1", "gold-v0.1"):
        require(
            context[source_id]["registry_commit"] == "f78e95a02fea16a7bd23ac01acbff4040a01bcd6",
            f"{source_id}: public registry commit",
        )
        require(
            context[source_id]["registry_blob"] == "bd6fa84302d53ea5ae54e5e7ac4bdc3ed8162ed9",
            f"{source_id}: public registry blob",
        )
    competition = data["competition_contract"]
    require(competition["authoritative_safe_assumption"]["submissions_per_day"] == 1, "one submission per day")
    require(competition["authoritative_safe_assumption"]["final_submissions"] == 2, "two final submissions")
    dependency = data["dependency_resolution"]
    exact_keys(
        dependency,
        {
            "starter_ranges_observed", "required_runtime_versions",
            "runtime_closure_status", "candidate_policy", "reviewed_stage_runtime",
            "successor_requirement", "current_blocker",
        },
        "dependency resolution",
    )
    require(
        dependency["runtime_closure_status"] == "FROZEN_POST_STAGE_SUCCESSOR",
        "reviewed Stage-A runtime closure",
    )
    require(
        dependency["current_blocker"].startswith("NO_EXTERNAL_EFFECT_AUTHORITY:"),
        "successor external-effect blocker",
    )
    require(
        "exact clean-commit successor snapshot" in dependency["successor_requirement"]
        and "ignored post-commit verification receipt" in dependency["successor_requirement"]
        and "fresh prospective Gate-A grant" in dependency["successor_requirement"]
        and "Gate B remains a separate human-authorized action" in dependency["successor_requirement"],
        "successor restage and Gate B requirements",
    )
    runtime = dependency["reviewed_stage_runtime"]
    exact_keys(
        runtime,
        {
            "schema", "stage_identity", "output", "python_version", "inventory",
            "runtime_file_bindings", "runtime_license_binding",
            "official_historical_provenance", "machine_evidence", "human_review",
        },
        "reviewed stage runtime",
    )
    require(runtime["schema"] == "hearthline-plays.arc3-reviewed-stage-runtime.v1", "reviewed runtime schema")
    require(
        runtime["stage_identity"]
        == {
            "kernel_slug": "grativy6/hearthline-arc3-readiness",
            "kernel_version": 4,
            "status": "COMPLETE",
            "visibility": "private",
            "internet_enabled": False,
            "accelerator": "cpu",
            "candidate_snapshot_sha256": "823cd5c7a99b16141959a09f011e361b2c03615ea37e72a65880a9eb5e8db4d0",
            "machine_evidence_recorded_at_utc": "2026-09-06T23:53:42Z",
        },
        "reviewed Stage-A identity",
    )
    require(runtime["python_version"] == "3.12.13", "reviewed runtime Python version")
    require(runtime["runtime_file_bindings"] == RUNTIME_AGENTS_FILES, "reviewed runtime file bindings")
    require(
        runtime["runtime_license_binding"]
        == {
            "path": "LICENSE",
            "sha256": AGENTS_LICENSE_SHA256,
            "spdx": "MIT",
            "copyright_notice": "Copyright (c) 2025 ARC Prize",
        },
        "reviewed runtime LICENSE binding",
    )
    require(
        runtime["inventory"]
        == {
            "path": RUNTIME_INVENTORY,
            "sha256": RUNTIME_INVENTORY_SHA256,
            "distribution_count": 875,
            "canonical_names_unique": True,
            "canonical_names_sorted": True,
        },
        "reviewed runtime inventory binding",
    )
    require(inventory_digest == RUNTIME_INVENTORY_SHA256, "runtime inventory byte hash")
    _validate_runtime_inventory(inventory)
    require(
        runtime["machine_evidence"]
        == {
            "evidence_manifest_sha256": RUNTIME_EVIDENCE_MANIFEST_SHA256,
            "logs_sha256": RUNTIME_LOGS_SHA256,
            "recorded_at_utc": "2026-09-06T23:53:42Z",
            "private_artifact_paths_committed": False,
        },
        "reviewed runtime machine evidence",
    )

    provenance = runtime["official_historical_provenance"]
    require(provenance["kind"] == "KAGGLE_PLATFORM_COMPETITION_INPUT", "runtime provenance kind")
    require(provenance["repository"] == "arcprize/ARC-AGI-3-Agents", "runtime provenance repository")
    require(provenance["commit"] == "135f20aaf44f13341ebc425666bf03b5cac58d3c", "runtime provenance commit")
    require(provenance["tree"] == "d7fbafe6e2ed191189db89e5b571fd26da3dc375", "runtime provenance tree")
    require(
        {path: binding["sha256"] for path, binding in provenance["inspected_file_bindings"].items()}
        == RUNTIME_AGENTS_FILES,
        "runtime provenance file bindings",
    )
    require(provenance["license_file_binding"]["sha256"] == AGENTS_LICENSE_SHA256, "runtime provenance LICENSE")
    require(agents["commit"] != provenance["commit"], "public/runtime Agents commits must remain separate")
    require(
        agents["inspected_file_bindings"]["agents/agent.py"]["sha256"]
        != provenance["inspected_file_bindings"]["agents/agent.py"]["sha256"],
        "public/runtime agents/agent.py hashes must remain separate",
    )

    human_review = runtime["human_review"]
    require(
        human_review
        == {
            "receipt_path": RUNTIME_REVIEW_RECEIPT,
            "receipt_sha256": RUNTIME_REVIEW_RECEIPT_SHA256,
            "reviewed_by": "Christopher D. Pang",
            "reviewed_at_utc": "2026-09-07T00:28:17Z",
            "attestation_sha256": "d721087df9ad28f26da262cddb066a7273b42f61d7fd96f7bb641c0840393dc2",
            "public_source_pin_retained": True,
            "runtime_binding_accepted": True,
        },
        "runtime human review binding",
    )
    require(review_receipt_digest == RUNTIME_REVIEW_RECEIPT_SHA256, "runtime review receipt byte hash")
    _validate_runtime_review_receipt(review_receipt, data, inventory)

    rules = data["run_rules"]
    require(rules["offline_by_default"] is True, "offline default")
    require(rules["credential_use_authorized"] is False, "credentials must be forbidden")
    require(rules["paid_provider_calls_authorized"] is False, "paid providers must be forbidden")
    require(rules["competition_mode_authorized"] is False, "competition mode forbidden")
    require(rules["kaggle_contact_authorized"] is False, "Kaggle contact forbidden")
    require(rules["automatic_push_or_submit_permitted"] is False, "automatic push/submit forbidden")


def _validate_runtime_review_receipt(
    receipt: dict[str, Any],
    source_lock: dict[str, Any],
    inventory: dict[str, Any],
) -> None:
    exact_keys(receipt, {"schema", "recorded_at", "status", "review", "binding", "authority_boundary"}, "runtime review receipt")
    require(receipt["schema"] == "hearthline-plays.arc3-stage-runtime-review-receipt.v1", "runtime review receipt schema")
    require(receipt["status"] == "HUMAN_REVIEW_ACCEPTED_FOR_LOCAL_SUCCESSOR_REPAIR", "runtime review receipt status")
    review = receipt["review"]
    require(review["reviewed_by"] == "Christopher D. Pang", "runtime review human")
    require(review["reviewed_at"] == "2026-09-07T00:28:17Z", "runtime review time")
    require(review["attestation_sha256"] == "d721087df9ad28f26da262cddb066a7273b42f61d7fd96f7bb641c0840393dc2", "runtime review attestation")
    binding = receipt["binding"]
    runtime = source_lock["dependency_resolution"]["reviewed_stage_runtime"]
    require(binding["runtime_inventory"]["path"] == RUNTIME_INVENTORY, "review receipt inventory path")
    require(binding["runtime_inventory"]["sha256"] == RUNTIME_INVENTORY_SHA256, "review receipt inventory hash")
    require(binding["runtime_inventory"]["distribution_count"] == len(inventory["distributions"]) == 875, "review receipt inventory count")
    require(binding["runtime_inventory"]["required_versions"] == RUNTIME_REQUIRED_VERSIONS, "review receipt runtime versions")
    require(binding["runtime_file_bindings"] == runtime["runtime_file_bindings"] == RUNTIME_AGENTS_FILES, "review receipt runtime files")
    require(binding["runtime_license_binding"]["sha256"] == AGENTS_LICENSE_SHA256, "review receipt runtime LICENSE")
    require(
        binding["machine_evidence"]
        == {
            "evidence_manifest_sha256": RUNTIME_EVIDENCE_MANIFEST_SHA256,
            "logs_sha256": RUNTIME_LOGS_SHA256,
            "private_artifact_paths_committed": False,
        },
        "review receipt machine evidence",
    )
    public = binding["public_source_pin"]
    require(public["commit"] == "4743e7d0aaae0ded0d98a89a7e282e63564cd58b", "review receipt public Agents commit")
    require(public["agents_agent_sha256"] == PUBLIC_AGENTS_FILES["agents/agent.py"], "review receipt public Agents hash")
    require(public["arc_agi_source_version"] == "0.9.9", "review receipt public ARC-AGI version")
    observed = binding["observed_runtime_provenance"]
    require(observed["official_historical_commit"] == "135f20aaf44f13341ebc425666bf03b5cac58d3c", "review receipt runtime commit")
    require(
        {path: item["sha256"] for path, item in observed["inspected_file_bindings"].items()}
        == RUNTIME_AGENTS_FILES,
        "review receipt runtime file provenance",
    )
    authority = receipt["authority_boundary"]
    require(authority["local_repair_authorized"] is True, "local repair review authority")
    require(authority["expired_grant_may_be_edited_or_reused"] is False, "expired grant immutability")
    for field in (
        "grant_creation_or_consumption_authorized", "remote_git_push_authorized",
        "kaggle_contact_or_stage_authorized", "gate_b_authorized",
        "competition_submission_authorized",
    ):
        require(authority[field] is False, f"review receipt must not authorize {field}")


def check_source_lock() -> None:
    source_lock_path = ROOT / "launch/source-lock.v4.json"
    inventory_path = ROOT / RUNTIME_INVENTORY
    review_receipt_path = ROOT / RUNTIME_REVIEW_RECEIPT
    require(sha256(source_lock_path) == SOURCE_LOCK_V4_SHA256, "source lock v4 byte hash")
    require(sha256(ROOT / "launch/source-lock.v3.json") == SOURCE_LOCK_V3_SHA256, "source lock v3 predecessor byte hash")
    _validate_source_lock(
        read_json(source_lock_path),
        read_json(inventory_path),
        read_json(review_receipt_path),
        inventory_digest=sha256(inventory_path),
        review_receipt_digest=sha256(review_receipt_path),
    )


def _validate_status(data: dict[str, Any]) -> None:
    exact_keys(
        data,
        {
            "schema", "updated_at", "phase", "readiness", "predecessor",
            "source_lock", "last_reconciliation", "reviewed_stage_evidence",
            "public_orientation", "competition", "candidate", "authority",
            "open_residuals", "reopening",
        },
        "current status",
    )
    require(data["schema"] == "hearthline-plays.arc3-launch-status.v3", "current status schema")
    require(
        data["updated_at"] == "2026-09-07T00:43:46Z",
        "current status update timestamp",
    )
    predecessor = data["predecessor"]
    expected_predecessor = {
        "path": "launch/status.json",
        "sha256": "21e907e181d24fda6e392a2d6ed5209f033d2b2383396d3c5edb8944e6963adb",
        "preserved": True,
    }
    exact_keys(predecessor, set(expected_predecessor), "current status predecessor")
    require(predecessor == expected_predecessor, "current status predecessor binding")
    require(predecessor["preserved"] is True, "current status predecessor preservation")
    require(
        data["last_reconciliation"]
        == "launch/receipts/20260904T070000Z-orientation-reconciliation.v2.json",
        "current status reconciliation pointer",
    )
    require(data["phase"] == "FROZEN_POST_STAGE_SUCCESSOR_LOCAL_REPAIR_ONLY", "current status phase")
    require(data["readiness"] == "NO_EXTERNAL_EFFECT_AUTHORITY", "current status authority ceiling")
    require(
        data["source_lock"]
        == {
            "path": "launch/source-lock.v4.json",
            "sha256": SOURCE_LOCK_V4_SHA256,
            "predecessor_path": "launch/source-lock.v3.json",
            "predecessor_sha256": SOURCE_LOCK_V3_SHA256,
            "runtime_closure_status": "FROZEN_POST_STAGE_SUCCESSOR",
        },
        "current status source-lock pointer",
    )
    expected_evidence = {
        "scope": "PREDECESSOR_VERSION_4_MACHINE_EVIDENCE_FOR_LOCAL_SUCCESSOR_REPAIR_ONLY",
        "kernel_slug": "grativy6/hearthline-arc3-readiness",
        "kernel_version": 4,
        "status": "COMPLETE",
        "visibility": "private",
        "internet_enabled": False,
        "accelerator": "cpu",
        "candidate_snapshot_sha256": "823cd5c7a99b16141959a09f011e361b2c03615ea37e72a65880a9eb5e8db4d0",
        "output_path": "submission.parquet",
        "output_sha256": "71bfd543030e339d87bd9ff744d466218398a1259650b2c255626d27049c88bb",
        "runtime_inventory_path": RUNTIME_INVENTORY,
        "runtime_inventory_sha256": RUNTIME_INVENTORY_SHA256,
        "runtime_distribution_count": 875,
        "machine_evidence_manifest_sha256": RUNTIME_EVIDENCE_MANIFEST_SHA256,
        "machine_logs_sha256": RUNTIME_LOGS_SHA256,
        "human_review_receipt_path": RUNTIME_REVIEW_RECEIPT,
        "human_review_receipt_sha256": RUNTIME_REVIEW_RECEIPT_SHA256,
        "successor_snapshot_verified_by_this_evidence": False,
    }
    evidence = data["reviewed_stage_evidence"]
    exact_keys(evidence, set(expected_evidence), "reviewed stage evidence")
    require(evidence == expected_evidence, "reviewed stage evidence binding")
    require(evidence["internet_enabled"] is False, "reviewed stage internet setting")
    require(evidence["successor_snapshot_verified_by_this_evidence"] is False, "predecessor evidence must not verify successor")
    expected_public_orientation = {
        "workflow_runs": 5,
        "public_arc_contact_count": 5,
        "requested_action_ceiling": 27,
        "observed_environment_action_count": 27,
        "captured_frame_record_count": 36,
        "scorecards_opened": 5,
        "scorecard_close_calls_returning_records": 5,
        "grant_disposition": "EXPIRED_AND_SPENT",
        "automatic_trigger_enabled": False,
        "new_contact_authorized": False,
    }
    public_orientation = data["public_orientation"]
    exact_keys(public_orientation, set(expected_public_orientation), "current public orientation")
    require(
        public_orientation == expected_public_orientation,
        "current public orientation binding",
    )
    require(public_orientation["new_contact_authorized"] is False, "public replay must remain closed")
    require(public_orientation["automatic_trigger_enabled"] is False, "automatic replay trigger forbidden")
    expected_competition = {
        "bounded_observation": (
            "Private kernel version 4 COMPLETE machine evidence, output, logs, and runtime "
            "metadata were previously retrieved and reviewed; no claim is made about "
            "unobserved API calls or platform state after that evidence cut."
        ),
        "current_kaggle_contact_authorized": False,
        "successor_kaggle_stage_authorized": False,
        "competition_ignition_authorized": False,
        "competition_submission_observed": False,
        "private_holdout_access": False,
        "paid_provider_calls_authorized": False,
        "daily_submission_limit_safe_assumption": 1,
        "limit_must_be_rechecked_at_human_gate": True,
    }
    competition = data["competition"]
    exact_keys(competition, set(expected_competition), "current competition status")
    require(competition == expected_competition, "current competition status binding")
    require("kaggle_contact_count" not in competition, "current status must not invent an exact Kaggle contact count")
    require(competition["current_kaggle_contact_authorized"] is False, "Kaggle contact must remain closed")
    require(competition["successor_kaggle_stage_authorized"] is False, "successor Kaggle stage must remain closed")
    require(competition["competition_ignition_authorized"] is False, "competition ignition must remain closed")
    require(competition["competition_submission_observed"] is False, "competition submission must remain unobserved")
    require(competition["private_holdout_access"] is False, "private holdout must remain false")
    require(competition["paid_provider_calls_authorized"] is False, "paid provider calls must remain closed")
    expected_candidate = {
        "repo_prepared": True,
        "agent_source": "agent/my_agent.py",
        "context_profile": "A0_MINIMAL",
        "official_starter_contract": "PASS_EEB153_ORDERED_STRUCTURAL_PROJECTION",
        "runtime_closure": "FROZEN_POST_STAGE_SUCCESSOR",
        "generated_artifacts_tracked": False,
        "clean_commit_manifest_required_at_handoff": True,
        "post_commit_successor_verification": (
            "IGNORED_LOCAL_RECEIPT_REQUIRED_HASH_NOT_EMBEDDED_IN_TRACKED_STATUS"
        ),
        "fresh_gate_a_grant_required": True,
        "fresh_private_restage_required_before_gate_b": True,
        "human_gate_a": "CLOSED",
        "human_gate_b": "CLOSED",
        "claim_ceiling": (
            "The reviewed version-4 evidence closes the observed predecessor runtime only. "
            "It does not verify, authorize, or stage the repaired successor snapshot and does "
            "not establish a competition score or generalization."
        ),
    }
    candidate = data["candidate"]
    exact_keys(candidate, set(expected_candidate), "current candidate")
    require(candidate == expected_candidate, "current candidate binding")
    require(candidate["repo_prepared"] is True, "candidate source preparation")
    require(candidate["generated_artifacts_tracked"] is False, "generated candidate must remain ignored")
    require(candidate["clean_commit_manifest_required_at_handoff"] is True, "clean commit manifest requirement")
    require(candidate["fresh_gate_a_grant_required"] is True, "fresh Gate-A grant requirement")
    require(candidate["fresh_private_restage_required_before_gate_b"] is True, "successor restage requirement")
    require(candidate["human_gate_a"] == candidate["human_gate_b"] == "CLOSED", "human gates must remain closed")
    expected_authority = {
        "expired_gate_a_grants": "IMMUTABLE_NOT_REUSABLE",
        "current_gate_a_grant": "ABSENT",
        "current_gate_b_grant": "ABSENT",
        "credential_use_authorized": False,
        "kaggle_contact_authorized": False,
        "remote_git_push_authorized_by_runtime_review": False,
        "gate_b_authorized": False,
        "competition_submission_authorized": False,
    }
    authority = data["authority"]
    exact_keys(authority, set(expected_authority), "current authority")
    require(authority == expected_authority, "current authority binding")
    for field in (
        "credential_use_authorized", "kaggle_contact_authorized",
        "remote_git_push_authorized_by_runtime_review", "gate_b_authorized",
        "competition_submission_authorized",
    ):
        require(authority[field] is False, f"current status must not authorize {field}")
    expected_residuals = [
        "Any external handoff must use the ignored local verification receipt generated "
        "from this exact clean successor commit; the snapshot hash is not embedded in "
        "this self-referential tracked projection.",
        "A fresh prospective Gate-A grant and one exact private restage of the newly "
        "verified successor snapshot are required before any Stage-A successor evidence "
        "can exist.",
        "Gate B remains closed until the successor stage completes, its exact v4 result "
        "is reviewed and recorded, and a separate current human Gate-B grant is issued.",
        "Competition rules must be rechecked by a human immediately before each "
        "separately authorized external gate.",
    ]
    require(data["open_residuals"] == expected_residuals, "current status residuals")
    require(
        data["reopening"]
        == (
            "Append a new receipt and replace only this mutable current projection. "
            "Never edit predecessor status, source locks, expired grants, or sealed receipts."
        ),
        "current status reopening boundary",
    )


def check_status() -> None:
    legacy = ROOT / "launch/status.json"
    require(
        sha256(legacy) == "21e907e181d24fda6e392a2d6ed5209f033d2b2383396d3c5edb8944e6963adb",
        "legacy status bytes changed",
    )
    _validate_status(read_json(ROOT / "launch/status/current.json"))


def check_schemas_and_templates() -> None:
    schema_paths = sorted((ROOT / "schemas").glob("*.json"))
    schema_paths += sorted((ROOT / "launch/schemas").glob("**/*.json"))
    for path in schema_paths:
        data = read_json(path)
        require(data.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"{path}: draft")
        require(isinstance(data.get("$id"), str), f"{path}: id")
    expected = {
        "templates/spark-a.static.json": "hearthline.spark-static.v1",
        "templates/spark-b.static.json": "hearthline.spark-static.v1",
        "templates/pair.static.json": "hearthline.pair-static.v1",
        "templates/world-model.json": "hearthline.arc3-world-model.v1",
        "templates/action-plan.json": "hearthline.arc3-action-plan.v1",
        "practice/ls20/world-model.json": "hearthline.arc3-world-model.v1",
        "practice/ls20/action-plan.json": "hearthline.arc3-action-plan.v1",
        "launch/templates/v2/spark-static.blank.json": "hearthline.arc3.spark-static.v2",
        "practice/ls20/world-model.v2.json": "hearthline.arc3.world-model.v2",
    }
    for rel, schema in expected.items():
        data = read_json(ROOT / rel)
        require(data.get("schema") == schema, f"{rel}: wrong schema")
    _validate_stage_v4_contract(
        read_json(ROOT / "launch/schemas/v4/stage-result.schema.json"),
        read_json(ROOT / "launch/gates/stage-result.v4.template.json"),
    )


def _validate_stage_v4_contract(schema: dict[str, Any], template: dict[str, Any]) -> None:
    top_level = {
        "schema", "status", "candidate", "kernel_id", "kernel_run_id",
        "kernel_visibility", "internet_enabled", "output_reviewed", "submission",
        "recorded_by_human", "credential_material_recorded",
        "external_effect_performed_by_gate_tool", "gate_a", "public_sources",
        "accepted_runtime_binding", "stage_evidence", "kaggle_runtime",
        "recorded_at", "claim_ceiling",
    }
    require(
        schema["$id"]
        == "https://github.com/Grativy6/hearthline-plays/launch/schemas/v4/stage-result.schema.json",
        "stage-result v4 schema $id",
    )
    require(schema["additionalProperties"] is False, "stage-result v4 schema closure")
    require(set(schema["required"]) == top_level, "stage-result v4 required fields")
    require(set(schema["properties"]) == top_level, "stage-result v4 property fields")
    require(
        schema["properties"]["schema"] == {"const": "hearthline.arc3.kaggle-stage-result.v4"},
        "stage-result v4 schema literal",
    )
    definitions = schema["$defs"]
    require(set(definitions) == {"sha256", "agentsPublicFiles", "agentsRuntimeFiles", "agentsLicense"}, "stage-result v4 definitions")
    require(
        {path: rule["const"] for path, rule in definitions["agentsPublicFiles"]["properties"].items()}
        == PUBLIC_AGENTS_FILES,
        "stage-result schema public Agents files",
    )
    require(
        {path: rule["const"] for path, rule in definitions["agentsRuntimeFiles"]["properties"].items()}
        == RUNTIME_AGENTS_FILES,
        "stage-result schema runtime Agents files",
    )
    require(
        definitions["agentsLicense"]["properties"] == {"LICENSE": {"const": AGENTS_LICENSE_SHA256}},
        "stage-result schema Agents LICENSE",
    )
    schema_public = schema["properties"]["public_sources"]["properties"]
    require(schema_public["arc_agi"]["properties"]["version"] == {"const": "0.9.9"}, "stage-result schema public ARC-AGI version")
    require(schema_public["agents"]["properties"]["commit"] == {"const": "4743e7d0aaae0ded0d98a89a7e282e63564cd58b"}, "stage-result schema public Agents commit")
    schema_binding = schema["properties"]["accepted_runtime_binding"]["properties"]
    require(schema_binding["status"] == {"const": "FROZEN_POST_STAGE_SUCCESSOR"}, "stage-result schema accepted runtime")
    require(schema_binding["inventory_sha256"] == {"const": RUNTIME_INVENTORY_SHA256}, "stage-result schema inventory hash")
    require(schema_binding["human_review_receipt_sha256"] == {"const": RUNTIME_REVIEW_RECEIPT_SHA256}, "stage-result schema review receipt hash")
    require(schema_binding["baseline_evidence_manifest_sha256"] == {"const": RUNTIME_EVIDENCE_MANIFEST_SHA256}, "stage-result schema baseline evidence manifest hash")
    require(schema_binding["baseline_logs_sha256"] == {"const": RUNTIME_LOGS_SHA256}, "stage-result schema baseline logs hash")
    require(
        schema["properties"]["stage_evidence"]["properties"]
        == {
            "evidence_manifest_sha256": {"$ref": "#/$defs/sha256"},
            "logs_sha256": {"$ref": "#/$defs/sha256"},
        },
        "stage-result schema new-run evidence",
    )
    schema_runtime = schema["properties"]["kaggle_runtime"]["properties"]
    distributions = schema_runtime["distributions"]
    require(distributions["minItems"] == distributions["maxItems"] == 875, "stage-result schema distribution count")
    require(distributions["uniqueItems"] is True, "stage-result schema distribution uniqueness")
    required_version_rules = {
        rule["contains"]["properties"]["name"]["const"]:
        rule["contains"]["properties"]["version"]["const"]
        for rule in distributions["allOf"]
    }
    require(required_version_rules == RUNTIME_REQUIRED_VERSIONS, "stage-result schema required runtime versions")
    runtime_provenance = schema_runtime["agents"]["properties"]["provenance"]["properties"]
    require(runtime_provenance["commit"] == {"const": "135f20aaf44f13341ebc425666bf03b5cac58d3c"}, "stage-result schema runtime Agents commit")
    require(schema["properties"]["recorded_by_human"] == {"const": True}, "stage-result schema human review")
    require(schema["properties"]["credential_material_recorded"] == {"const": False}, "stage-result schema credential exclusion")
    require(schema["properties"]["external_effect_performed_by_gate_tool"] == {"const": False}, "stage-result schema gate-tool effect exclusion")
    exact_keys(template, top_level, "stage-result v4 template")
    require(template["schema"] == "hearthline.arc3.kaggle-stage-result.v4", "stage-result v4 template schema")
    public = template["public_sources"]
    exact_keys(public, {"arc_agi", "agents"}, "stage-result public sources")
    require(
        public["arc_agi"]
        == {
            "repository": "arcprize/ARC-AGI",
            "commit": "f12822c4d550121c35a275008d964afbbed47d2f",
            "version": "0.9.9",
        },
        "stage-result public ARC-AGI pin",
    )
    exact_keys(public["agents"], {"repository", "commit", "tree", "files", "license_file"}, "stage-result public Agents")
    require(public["agents"]["commit"] == "4743e7d0aaae0ded0d98a89a7e282e63564cd58b", "stage-result public Agents commit")
    require(public["agents"]["tree"] == "6878fdfdd0156059323b541fc229b6329ad4fd28", "stage-result public Agents tree")
    require(public["agents"]["files"] == PUBLIC_AGENTS_FILES, "stage-result public Agents files")
    require(public["agents"]["license_file"] == {"LICENSE": AGENTS_LICENSE_SHA256}, "stage-result public Agents LICENSE")
    require(
        template["accepted_runtime_binding"]
        == {
            "status": "FROZEN_POST_STAGE_SUCCESSOR",
            "inventory_sha256": RUNTIME_INVENTORY_SHA256,
            "human_review_receipt_sha256": RUNTIME_REVIEW_RECEIPT_SHA256,
            "baseline_evidence_manifest_sha256": RUNTIME_EVIDENCE_MANIFEST_SHA256,
            "baseline_logs_sha256": RUNTIME_LOGS_SHA256,
        },
        "stage-result accepted runtime binding",
    )
    require(
        template["stage_evidence"]
        == {
            "evidence_manifest_sha256": "REPLACE_WITH_NEW_RUN_EVIDENCE_MANIFEST_SHA256",
            "logs_sha256": "REPLACE_WITH_NEW_RUN_LOGS_SHA256",
        },
        "stage-result new-run evidence placeholders",
    )
    kaggle = template["kaggle_runtime"]
    exact_keys(kaggle, {"captured_from", "complete", "python_version", "distributions", "agents", "reviewed_by_human"}, "stage-result Kaggle runtime")
    require(kaggle["captured_from"] == "HEARTHLINE_STAGE_INVENTORY", "stage-result inventory source")
    require(kaggle["complete"] is False and kaggle["reviewed_by_human"] is False, "stage-result template must not self-attest")
    require(kaggle["python_version"] == "3.12.13" and kaggle["distributions"] == [], "stage-result empty runtime inventory template")
    runtime_agents = kaggle["agents"]
    exact_keys(runtime_agents, {"provenance", "files", "license_file"}, "stage-result runtime Agents")
    require(
        runtime_agents["provenance"]
        == {
            "kind": "KAGGLE_PLATFORM_COMPETITION_INPUT",
            "repository": "arcprize/ARC-AGI-3-Agents",
            "commit": "135f20aaf44f13341ebc425666bf03b5cac58d3c",
            "tree": "d7fbafe6e2ed191189db89e5b571fd26da3dc375",
        },
        "stage-result runtime Agents provenance",
    )
    require(runtime_agents["files"] == RUNTIME_AGENTS_FILES, "stage-result runtime Agents files")
    require(runtime_agents["license_file"] == {"LICENSE": AGENTS_LICENSE_SHA256}, "stage-result runtime Agents LICENSE")
    require(
        public["agents"]["commit"] != runtime_agents["provenance"]["commit"]
        and public["agents"]["files"]["agents/agent.py"] != runtime_agents["files"]["agents/agent.py"],
        "stage-result public/runtime identities must remain separate",
    )


def check_requests() -> None:
    req_dir = ROOT / "practice/requests"
    if not req_dir.exists():
        return
    ids = []
    for path in sorted(req_dir.glob("*.json")):
        data = read_json(path)
        require(data.get("schema") == "hearthline.arc3-orientation-request.v1", f"{path}: schema")
        rid = data.get("request_id")
        require(isinstance(rid, str) and rid.startswith("ORIENT-"), f"{path}: request_id")
        ids.append(rid)
        require(data.get("mode") == "PUBLIC_ORIENTATION", f"{path}: mode")
        require(data.get("status") == "AUTHORIZED", f"{path}: preserved historical status")
        require(data.get("grant_ref") == "launch/RUN_GRANT_2026-09-03.md", f"{path}: historical grant reference")
        require(rid in {f"ORIENT-{index:04d}" for index in range(1, 6)}, f"{path}: request is outside the closed archive")
        require(data.get("game_id") in {"ls20", "ft09", "vc33"}, f"{path}: public game")
        require(data.get("close_scorecard") is True, f"{path}: scorecard must close")
        actions = data.get("actions")
        require(isinstance(actions, list), f"{path}: actions")
        max_actions = data.get("max_actions")
        require(type(max_actions) is int and len(actions) <= max_actions <= 64, f"{path}: action bound")
        for action in actions:
            require(action.get("action") in {f"ACTION{i}" for i in range(1, 8)}, f"{path}: action")
            require(len(action.get("hypothesis", "")) <= 400, f"{path}: hypothesis too long")
            require(len(action.get("expected_observable", "")) <= 400, f"{path}: expected too long")
    unique(ids, "request IDs")
    require(set(ids) == {f"ORIENT-{index:04d}" for index in range(1, 6)}, "closed orientation archive inventory")
    readme = (ROOT / "practice/README.md").read_text(encoding="utf-8")
    require("EXPIRED, SPENT, AND NON-EXECUTABLE" in readme, "practice archive retirement banner")
    require("They are not replayable instructions" in readme, "practice requests must not be presented as live")


def check_workflow_boundary() -> None:
    path = ROOT / ".github/workflows/arc3-orientation-probe.yml"
    text = path.read_text(encoding="utf-8")
    for required in (
        "workflow_dispatch:",
        "permissions:",
        "contents: read",
        "test_reconciliation.py",
        "hearthline-repository-guard.py",
        '--root "$GITHUB_WORKSPACE"',
    ):
        require(required in text, f"workflow missing {required!r}")
    for forbidden in ("push:", "arc3_replay_probe.py", "pip install", "three.arcprize.org"):
        require(forbidden not in text, f"workflow contains forbidden token {forbidden!r}")


def check_reconciliation() -> None:
    index = read_json(ROOT / "launch/receipts/20260904T070000Z-orientation-reconciliation.v2.json")
    receipts = []
    for binding in index["admitted_receipts"]:
        path = ROOT / binding["path"]
        require(sha256(path) == binding["sha256"], f"admitted receipt hash: {path}")
        receipts.append(read_json(path))
    totals = index["verified_totals"]
    require(len(receipts) == totals["public_arc_contacts"] == 5, "reconciled public contacts")
    require(sum(row["admitted_execution"]["observed_environment_actions"] for row in receipts) == totals["observed_environment_actions"] == 27, "reconciled action total")
    require(sum(row["admitted_execution"]["captured_frame_records"] for row in receipts) == totals["captured_frame_records"] == 36, "reconciled frame total")
    require(all(row["admitted_execution"]["competition_mode"] is False for row in receipts), "orientation must be non-competition")


def check_candidate_surface() -> None:
    agent_path = ROOT / "agent/my_agent.py"
    source = agent_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(agent_path))
    imports = set()
    classes = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = node
    require(not imports & {"os", "subprocess", "socket", "requests", "urllib", "kaggle"}, "agent effect-capable import")
    require("MyAgent" in classes, "MyAgent missing")
    methods = {node.name for node in classes["MyAgent"].body if isinstance(node, ast.FunctionDef)}
    require({"is_done", "choose_action"} <= methods, "official Agent methods missing")

    metadata = read_json(ROOT / "notebooks/kernel-metadata.template.json")
    require(set(metadata) == {
        "id", "title", "code_file", "language", "kernel_type", "is_private",
        "enable_gpu", "enable_tpu", "enable_internet", "keywords",
        "dataset_sources", "kernel_sources", "competition_sources", "model_sources",
    }, "kernel template fields")
    require(metadata["code_file"] == "submission.ipynb", "kernel template code file")
    require(metadata["is_private"] is True, "kernel template private")
    require(metadata["enable_internet"] is False, "kernel template offline")
    require(metadata["dataset_sources"] == metadata["kernel_sources"] == metadata["model_sources"] == [], "kernel template extra sources")
    require(metadata["competition_sources"] == ["arc-prize-2026-arc-agi-3"], "kernel competition source")

    contract = read_json(ROOT / "launch/contracts/official-starter-eeb153.contract.json")
    lock = read_json(ROOT / "launch/source-lock.v4.json")
    starter = next(row for row in lock["official_software"] if row["repository"] == "arcprize/ARC-AGI-3-Kaggle-Starter")
    require(contract["source"]["commit"] == starter["commit"], "starter contract commit")
    require(
        contract["source"]["build_script_sha256"]
        == starter["inspected_file_bindings"]["scripts/build_notebook.py"]["sha256"],
        "starter contract script hash",
    )
    require(contract["projection"]["install"]["packages"] == ["arc-agi", "python-dotenv"], "starter package projection")
    require(contract["source"]["license_observation"].startswith("No LICENSE or NOTICE"), "starter license observation")

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    for forbidden in ("kaggle kernels", "kaggle competitions", "curl ", "KAGGLE_API_TOKEN", ".kaggle/access_token"):
        require(forbidden not in makefile, f"Makefile external-effect surface: {forbidden}")
    gate_source = (ROOT / "scripts/verify_human_gate.py").read_text(encoding="utf-8")
    for forbidden in ("import requests", "import webbrowser", "kaggle kernels"):
        require(forbidden not in gate_source, f"gate effect surface: {forbidden}")
    for required in (
        "grant_id is already consumed",
        "grant nonce is already consumed",
        "os.rename",
        "_assert_gate_seal(result)",
        "sealed Gate A parent missing or duplicated under ledger lock",
        "verify_current_candidate(args.build_dir)",
        "runtime inventory must be complete",
        "a Gate B grant was already consumed on this UTC day",
        "GIT_NO_REPLACE_OBJECTS",
        "worktree candidate verifier differs from committed Git object",
        "Git identity changed during candidate verification",
        "candidate verification result differs from the bound Git identity",
        "Local procedural gate consumed",
    ):
        require(required in gate_source, f"gate single-use surface missing: {required}")
    require(not (ROOT / "tools/arc3_replay_probe.py").exists(), "legacy replay broker must be absent")
    archive_guard = (ROOT / "tools/orientation_archive_guard.py").read_text(encoding="utf-8")
    require("CLOSED_EXPIRED_AND_SPENT" in archive_guard, "orientation archive closure guard")
    require("import arc_agi" not in archive_guard, "archive guard must have no ARC adapter")

    stage = read_json(ROOT / "launch/gates/kaggle-stage-grant.v2.template.json")
    competition = read_json(ROOT / "launch/gates/competition-ignition-grant.v2.template.json")
    require(stage["rules"]["submissions_per_day"] == 1, "Gate A daily limit")
    require(competition["rules"]["submissions_per_day"] == 1, "Gate B daily limit")
    require(stage["schema"] == competition["schema"] == "hearthline.arc3.human-grant.v3", "gate template schema")
    require(competition["acknowledgements"]["account_slug"] == "REPLACE_FROM_CONSUMED_GATE_A", "Gate B account binding")
    require(stage["human_actor"]["attested_by_human"] is False, "Gate A template must not self-attest")
    require(competition["human_actor"]["attested_by_human"] is False, "Gate B template must not self-attest")


def _validate_context_roles(context: dict[str, Any]) -> None:
    require(context["schema"] == "hearthline.arc3.compact-context.v2", "compact context schema")
    require(context["source_lock"] == "launch/source-lock.v4.json", "compact context current source-lock pointer")
    roles = {row["role_id"] for row in context["roles"]}
    require(len(roles) == 8, "compact context role inventory")
    require(all(not row["default_enabled"] for row in context["roles"]), "compact context roles default off")
    require(context["common_safety_shell"]["ablatable"] is False, "compact context safety shell")


def check_current_documents() -> None:
    _validate_context_roles(read_json(ROOT / "launch/context/roles.v2.json"))
    required_by_path = {
        "README.md": (
            "FROZEN_POST_STAGE_SUCCESSOR_LOCAL_REPAIR_ONLY",
            "launch/source-lock.v4.json",
            "875",
            "fresh Gate-A grant",
            "Gate B",
        ),
        "LAUNCHPAD.md": (
            "FROZEN_POST_STAGE_SUCCESSOR_LOCAL_REPAIR_ONLY",
            "launch/source-lock.v4.json",
            "875",
            "fresh Gate-A grant",
            "Gate B",
        ),
        "LAUNCH.md": (
            "FROZEN_POST_STAGE_SUCCESSOR_LOCAL_REPAIR_ONLY",
            "launch/source-lock.v4.json",
            "fresh Gate-A grant",
            "Gate B",
        ),
        "THIRD_PARTY_NOTICES.md": (
            "launch/source-lock.v4.json",
            "4743e7d0aaae0ded0d98a89a7e282e63564cd58b",
            "135f20aaf44f13341ebc425666bf03b5cac58d3c",
            PUBLIC_AGENTS_FILES["agents/agent.py"],
            RUNTIME_AGENTS_FILES["agents/agent.py"],
        ),
        "launch/README.md": (
            "launch/source-lock.v4.json",
            "launch/source-lock.v3.json",
            "FROZEN_POST_STAGE_SUCCESSOR",
            "fresh Gate-A grant",
            "Gate B",
        ),
        "launch/context/ARC3_COMPACT_CONTEXT_V2.md": (
            "launch/source-lock.v4.json",
            "FROZEN_POST_STAGE_SUCCESSOR",
            "fresh Gate-A grant",
            "Gate B",
        ),
        "launch/gates/README.md": (
            "launch/source-lock.v4.json",
            "stage-result.v4.template.json",
            "FROZEN_POST_STAGE_SUCCESSOR",
            "fresh Gate-A grant",
            "Gate B",
        ),
        "launch/receipts/README.md": (
            "20260907T002817Z-stage-v4-runtime-review.json",
            "875-entry runtime inventory",
            "raw logs",
            "competition-submission authority",
        ),
    }
    for relative, required in required_by_path.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for token in required:
            require(token in text, f"{relative}: stale current documentation missing {token!r}")


def check_protected_history() -> None:
    expected = {
        "launch/FOUNDER_SENDOFF.md": "c5edc23c8f8d9affb84924088b92d22d5914a1e2be98d036e3c79390edd036cc",
        "launch/status.json": "21e907e181d24fda6e392a2d6ed5209f033d2b2383396d3c5edb8944e6963adb",
        "launch/source-lock.v2.json": "3747d76566df1415547ede25b541141063e10120e00076e8961a4debaaa5922a",
        "launch/source-lock.v3.json": SOURCE_LOCK_V3_SHA256,
        "launch/gates/stage-result.v2.template.json": "262cb026ed8bc12e80b05bcd7d4eef0c4b166ed8919cd65766176d6ad09fa206",
        "launch/schemas/v2/stage-result.schema.json": "e2e876518f834567a1bf6518d3ce2fd99cc568b178bd02fc753d8243036b639a",
        "launch/receipts/20260904T001827Z-pre-astra-lineage-seal.json": "375aa8b834a5b17fb1dc5e74883160b1266a441df86aa6c385a076a8434cec8f",
        "launch/receipts/20260904T001827Z-pre-astra-lineage-seal.md": "6951e2b75460927ea3fec5f53eddcd32847e75bd7b3728ec8f7db4dc99ce45d1",
    }
    for relative, digest in expected.items():
        require(sha256(ROOT / relative) == digest, f"protected history changed: {relative}")
    grant = (ROOT / "launch/RUN_GRANT_2026-09-03.md").read_bytes()
    marker = "# Run grant — public ARC-AGI-3 orientation, 3 September 2026\n".encode("utf-8")
    require(grant.startswith(b"> **Present-day status (4 September 2026): EXPIRED, SPENT, ARCHIVE-ONLY.**"), "historical grant retirement banner")
    require(marker in grant, "historical grant body marker")
    historical_body = grant[grant.index(marker):]
    require(
        hashlib.sha256(historical_body).hexdigest()
        == "4cbd09a55ecb18c6a3c571ed54ab94f8fee1c2c52ba57c99867e6930822e08d8",
        "historical run grant body changed",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    checks = [
        check_source_lock,
        check_status,
        check_schemas_and_templates,
        check_requests,
        check_workflow_boundary,
        check_reconciliation,
        check_candidate_surface,
        check_current_documents,
        check_protected_history,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    print("LAUNCHPAD_CONFORMANT")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"FAIL {exc}")
        raise SystemExit(1)
