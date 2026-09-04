#!/usr/bin/env python3
"""Offline integrity and claim-boundary checks for the Millennium Playground."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MILLENNIUM = ROOT / "millennium"
RECEIPTS = MILLENNIUM / "receipts"
GENESIS_PATH = RECEIPTS / "20260904T073424Z-genesis.json"
SOURCE_LOCK_PATH = MILLENNIUM / "research" / "clay-official-sources.lock.json"
SUMS_PATH = MILLENNIUM / "SHA256SUMS"

EXPECTED_PARENT_COMMIT = "ef18554b2ca828b270dfb78512550b9b401ab6e4"
EXPECTED_PARENT_TREE = "d62bb6615ce651af6498294a73c7de6a73de1758"
EXPECTED_SOURCE_LOCK_SHA256 = (
    "94ffd76e537aadf44f54b17a623de6f3009a4484317e830308b3897a77c00896"
)
EXPECTED_PROBLEMS = {
    "Birch and Swinnerton-Dyer Conjecture",
    "Hodge Conjecture",
    "Navier-Stokes Equation",
    "P versus NP Problem",
    "Poincare Conjecture",
    "Riemann Hypothesis",
    "Yang-Mills and Mass Gap",
}
ACTIVE_ARENAS = ["riemann", "p-vs-np", "geometry"]
CLAIM_STATES = {
    "observation",
    "reproduced",
    "certified_finite",
    "conjectured",
    "proved_restricted",
    "proof_candidate",
    "externally_established",
}
ASTRA_RANK = {"session_declared_absent": 0, "unknown": 1, "present": 2}
EVENT_DOMAIN = b"HEARTHLINE-MILLENNIUM-EVENT-V1\0"
COMMITMENT_DOMAIN = b"HEARTHLINE-MILLENNIUM-PRIVATE-COMMITMENT-V1\0"
EVENT_SCHEME = (
    "sha256(UTF8(HEARTHLINE-MILLENNIUM-EVENT-V1\\0) || "
    "RFC8785_JCS(payload_without_event_id)); no floating-point values and "
    "ASCII object-member names"
)
VERIFIER_NOTICE = (
    "This seal verifies integrity and disclosed lineage of the public record. "
    "It does not establish mathematical correctness, originality, exclusive "
    "authorship, complete disclosure, absence of undisclosed assistance, prize "
    "eligibility, or CMI recognition."
)
ORIGINS = {
    "human_written",
    "model_drafted_pending_steward_review",
    "model_proposed_human_adopted",
    "human_model_coedited",
    "model_assembled_from_verified_sources_pending_steward_review",
    "mechanically_generated",
}
GENESIS_ARTIFACT_PATHS = {
    ".gitattributes",
    ".github/workflows/millennium-verify.yml",
    "README.md",
    "tests/test_millennium_genesis.py",
    "millennium/.gitignore",
    "millennium/README.md",
    "millennium/FOUNDING_BOUNDARY.md",
    "millennium/arenas/geometry/ARENA.md",
    "millennium/arenas/p-vs-np/ARENA.md",
    "millennium/arenas/riemann/ARENA.md",
    "millennium/attestations/README.md",
    "millennium/protocol/CLAIM_STATES.md",
    "millennium/protocol/PLAY_PROTOCOL.md",
    "millennium/receipts/README.md",
    "millennium/receipts/20260904T073424Z-genesis.md",
    "millennium/research/clay-official-sources.lock.json",
    "millennium/schemas/genesis-receipt.v1.schema.json",
    "millennium/schemas/run-receipt.v1.schema.json",
    "millennium/tools/verify_genesis.py",
}


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def require_exact_keys(value: object, keys: set[str], label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label} must be an object")
    actual = set(value)
    require(actual == keys, f"{label} keys differ: missing={sorted(keys - actual)}, extra={sorted(actual - keys)}")
    return value


def reject_constant(value: str) -> None:
    raise VerificationError(f"non-standard JSON constant: {value}")


def reject_float(value: str) -> None:
    raise VerificationError(f"floating-point JSON value is forbidden: {value}")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"duplicate JSON object member: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except VerificationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot load {path}: {exc}") from exc
    require(isinstance(value, dict), f"top-level JSON value must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise VerificationError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def is_event_id(value: object) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and is_sha256(value[7:])


def assert_jcs_profile(value: Any) -> None:
    if isinstance(value, float):
        raise VerificationError("event payload contains a floating-point value")
    if isinstance(value, int) and not isinstance(value, bool):
        require(-(2**53) + 1 <= value <= (2**53) - 1, "event integer exceeds I-JSON safe range")
    if isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise VerificationError("event string contains an unpaired surrogate") from exc
    if isinstance(value, dict):
        for key, child in value.items():
            require(key.isascii(), f"event object member name is not ASCII: {key!r}")
            assert_jcs_profile(child)
    elif isinstance(value, list):
        for child in value:
            assert_jcs_profile(child)


def compute_event_id(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_id", None)
    assert_jcs_profile(payload)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(EVENT_DOMAIN + canonical).hexdigest()


def safe_public_path(relative: object) -> Path:
    require(isinstance(relative, str) and relative, "artifact path is missing")
    candidate = Path(relative)
    require(not candidate.is_absolute(), f"absolute artifact path: {relative}")
    require(".." not in candidate.parts, f"unsafe artifact path: {relative}")
    require("private" not in {part.lower() for part in candidate.parts}, f"private path is public: {relative}")
    require(".private." not in candidate.name.lower(), f"private filename is public: {relative}")
    unresolved = ROOT / candidate
    cursor = ROOT
    for part in candidate.parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), f"symlink component is forbidden: {relative}")
    resolved = unresolved.resolve()
    require(resolved == ROOT or ROOT in resolved.parents, f"artifact escapes repository: {relative}")
    require(resolved.is_file(), f"missing public artifact: {relative}")
    return resolved


def verify_event_identity(event: dict[str, Any], label: str) -> None:
    require(is_event_id(event.get("event_id")), f"bad event ID: {label}")
    require(event.get("event_id_scheme") == EVENT_SCHEME, f"bad event scheme: {label}")
    calculated = compute_event_id(event)
    require(event["event_id"] == calculated, f"event ID mismatch: {label}")


def verify_source_lock(source_dir: Path | None) -> dict[str, dict[str, Any]]:
    lock_digest = sha256_file(SOURCE_LOCK_PATH)
    require(lock_digest == EXPECTED_SOURCE_LOCK_SHA256, f"source lock digest mismatch: {lock_digest}")
    lock = load_json(SOURCE_LOCK_PATH)
    require(lock.get("schema") == "hearthline-plays.clay-source-lock.v1", "bad source schema")
    sources = lock.get("sources")
    require(isinstance(sources, list) and len(sources) == 8, "expected seven problems plus rules")
    require(all(isinstance(entry, dict) for entry in sources), "source entry is not an object")
    problems = {entry.get("problem") for entry in sources if entry.get("problem") is not None}
    require(problems == EXPECTED_PROBLEMS, "official problem set is incomplete or changed")
    require(sum(entry.get("role") == "revised_prize_rules" for entry in sources) == 1, "expected one rules source")
    by_id: dict[str, dict[str, Any]] = {}
    for entry in sources:
        source_id = entry.get("id")
        require(isinstance(source_id, str) and source_id not in by_id, "missing or duplicate source ID")
        by_id[source_id] = entry
        require(is_sha256(entry.get("sha256")), f"bad source digest for {source_id}")
        require(isinstance(entry.get("bytes"), int) and entry["bytes"] > 0, f"bad byte count for {source_id}")
        require(str(entry.get("url", "")).startswith("https://www.claymath.org/"), f"non-Clay URL: {source_id}")
        if source_dir is not None:
            path = source_dir / str(entry.get("local_verification_filename"))
            require(path.is_file() and not path.is_symlink(), f"missing downloaded source: {path}")
            require(path.stat().st_size == entry["bytes"], f"source byte mismatch: {path}")
            require(sha256_file(path) == entry["sha256"], f"source digest mismatch: {path}")
    return by_id


def verify_artifact_manifest(receipt: dict[str, Any]) -> None:
    credit = receipt.get("credit")
    require(isinstance(credit, dict), "missing credit record")
    relative = credit.get("artifact_origin_manifest_path")
    path = safe_public_path(relative)
    require(path.stat().st_size == credit.get("artifact_origin_manifest_bytes"), "artifact manifest byte mismatch")
    require(sha256_file(path) == credit.get("artifact_origin_manifest_sha256"), "artifact manifest digest mismatch")
    manifest = load_json(path)
    require_exact_keys(
        manifest,
        {
            "schema",
            "event",
            "human_author_and_steward",
            "review_state",
            "authorship_policy",
            "origin_definitions",
            "artifacts",
        },
        "artifact manifest",
    )
    require(manifest.get("schema") == "hearthline-plays.artifact-origins.v1", "bad artifact manifest schema")
    require(manifest.get("event") == receipt.get("receipt_id"), "artifact manifest event mismatch")
    require(manifest.get("review_state") == "PENDING_STEWARD_REVIEW", "steward review state overstated")
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, list) and artifacts, "empty artifact manifest")
    seen: set[str] = set()
    canonical_commit = canonical_genesis_commit_or_none()
    definitions = require_exact_keys(
        manifest.get("origin_definitions"),
        {
            "model_drafted_pending_steward_review",
            "model_assembled_from_verified_sources_pending_steward_review",
            "mechanically_generated",
        },
        "origin definitions",
    )
    allowed_origins = set(definitions)
    for artifact in artifacts:
        require(isinstance(artifact, dict), "artifact manifest entry is not an object")
        require_exact_keys(artifact, {"path", "change", "origin", "bytes", "sha256"}, "artifact manifest entry")
        artifact_path = artifact.get("path")
        require(isinstance(artifact_path, str) and artifact_path not in seen, "duplicate manifest path")
        seen.add(artifact_path)
        require(artifact.get("origin") in allowed_origins, f"unknown origin: {artifact_path}")
        require(artifact.get("change") in {"added", "modified"}, f"bad change type: {artifact_path}")
        require(isinstance(artifact.get("bytes"), int) and artifact["bytes"] >= 0, f"bad manifest bytes: {artifact_path}")
        require(is_sha256(artifact.get("sha256")), f"bad manifest digest: {artifact_path}")
        if canonical_commit is None:
            public_path = safe_public_path(artifact_path)
            payload = public_path.read_bytes()
        else:
            payload = git_blob(canonical_commit, artifact_path)
        require(len(payload) == artifact.get("bytes"), f"manifest byte mismatch: {artifact_path}")
        require(hashlib.sha256(payload).hexdigest() == artifact.get("sha256"), f"manifest digest mismatch: {artifact_path}")
    require(seen == GENESIS_ARTIFACT_PATHS, "artifact manifest does not cover the exact genesis payload")


def verify_genesis() -> dict[str, Any]:
    receipt = load_json(GENESIS_PATH)
    require_exact_keys(
        receipt,
        {
            "schema",
            "event_id",
            "event_id_scheme",
            "event_origin",
            "receipt_id",
            "status",
            "claimed_created_at_utc",
            "steward",
            "lineage",
            "credit",
            "scope",
            "claim_boundary",
            "official_sources",
            "private_checkpoint_commitment",
            "assistance_provenance",
            "attestation_status_at_creation",
            "verifier_notice",
        },
        "genesis receipt",
    )
    require(receipt.get("schema") == "hearthline-plays.millennium-genesis.v1", "bad receipt schema")
    verify_event_identity(receipt, "genesis")
    require(receipt.get("receipt_id") == "MILLENNIUM-GENESIS-20260904T073424Z", "bad genesis receipt ID")
    require(receipt.get("status") == "GENESIS_SEALED_PLAY_NOT_PROOF", "bad genesis status")
    require(receipt.get("event_origin") == "model_drafted_pending_steward_review", "genesis event origin changed")
    require(receipt.get("steward") == "Christopher D. Pang", "unexpected steward")
    parse_utc(receipt.get("claimed_created_at_utc"), "genesis creation")
    lineage = receipt.get("lineage")
    require_exact_keys(
        lineage,
        {
            "relationship",
            "parent_seal_id",
            "parent_commit",
            "parent_tree",
            "parent_public_branch",
            "genesis_public_branch",
            "self_commit_rule",
        },
        "genesis lineage",
    )
    require(lineage.get("relationship") == "append-only-successor", "lineage is not append-only")
    require(lineage.get("parent_commit") == EXPECTED_PARENT_COMMIT, "parent commit mismatch")
    require(lineage.get("parent_tree") == EXPECTED_PARENT_TREE, "parent tree mismatch")
    credit = receipt.get("credit")
    require_exact_keys(
        credit,
        {
            "human_author_and_steward",
            "hearthline_role",
            "pal_role",
            "ai_authorship",
            "ai_mathematical_authority",
            "artifact_level_provenance_controls",
            "artifact_origin_manifest_path",
            "artifact_origin_manifest_origin",
            "artifact_origin_manifest_bytes",
            "artifact_origin_manifest_sha256",
            "steward_review_state",
        },
        "genesis credit",
    )
    require(credit.get("ai_authorship") is False, "AI authorship boundary changed")
    require(credit.get("ai_mathematical_authority") is False, "AI authority boundary changed")
    require(credit.get("artifact_level_provenance_controls") is True, "artifact provenance disabled")
    require(credit.get("artifact_origin_manifest_origin") == "model_drafted_pending_steward_review", "manifest origin changed")
    require(credit.get("steward_review_state") == "PENDING_STEWARD_REVIEW", "review state overstated")
    scope = receipt.get("scope")
    require_exact_keys(scope, {"active_arenas", "geometry_resolution", "other_clay_problems"}, "genesis scope")
    require(scope.get("active_arenas") == ACTIVE_ARENAS, "active arenas changed")
    geometry = scope.get("geometry_resolution")
    require_exact_keys(geometry, {"control_lane", "open_frontier", "hodge_frontier_opened_by_genesis"}, "geometry split")
    require(geometry.get("control_lane") == "poincare-solved", "Poincare control changed")
    require(geometry.get("open_frontier") == "hodge-rational", "Hodge target changed")
    require(geometry.get("hodge_frontier_opened_by_genesis") is False, "Hodge silently opened")
    boundary = receipt.get("claim_boundary")
    require_exact_keys(
        boundary,
        {
            "steward_conceptual_satisfaction_is_proof_claim",
            "millennium_problem_solution_claimed",
            "proof_candidate_claimed",
            "external_acceptance_claimed",
            "cmi_prize_awarded_claimed",
            "initial_claim_state",
        },
        "genesis claim boundary",
    )
    for forbidden_claim in (
        "steward_conceptual_satisfaction_is_proof_claim",
        "millennium_problem_solution_claimed",
        "proof_candidate_claimed",
        "external_acceptance_claimed",
        "cmi_prize_awarded_claimed",
    ):
        require(boundary.get(forbidden_claim) is False, f"forbidden claim promoted: {forbidden_claim}")
    require(boundary.get("initial_claim_state") == "observation", "genesis claim state changed")
    source_record = receipt.get("official_sources")
    require_exact_keys(
        source_record,
        {"lock_path", "lock_sha256", "retrieved_at_utc", "source_bytes_committed_to_git"},
        "genesis official sources",
    )
    require(source_record.get("lock_sha256") == EXPECTED_SOURCE_LOCK_SHA256, "receipt source-lock mismatch")
    require(source_record.get("source_bytes_committed_to_git") is False, "source bytes marked public")
    commitment = receipt.get("private_checkpoint_commitment")
    require_exact_keys(
        commitment,
        {
            "public_label",
            "scheme",
            "domain_separator_utf8_with_terminal_nul",
            "commitment_sha256",
            "nonce_disclosed_in_git",
            "artifact_digest_disclosed_in_git",
            "artifact_bytes_committed_to_git",
            "private_reveal_receipt_committed_to_git",
            "historical_astra_provenance",
            "security_semantics",
        },
        "private checkpoint commitment",
    )
    require(is_sha256(commitment.get("commitment_sha256")), "bad private commitment")
    require(commitment.get("scheme") == "sha256(domain_separator || nonce_bytes || artifact_sha256_bytes)", "commitment scheme changed")
    require(commitment.get("domain_separator_utf8_with_terminal_nul") == "HEARTHLINE-MILLENNIUM-PRIVATE-COMMITMENT-V1", "commitment domain changed")
    for secret_flag in (
        "nonce_disclosed_in_git",
        "artifact_digest_disclosed_in_git",
        "artifact_bytes_committed_to_git",
        "private_reveal_receipt_committed_to_git",
    ):
        require(commitment.get(secret_flag) is False, f"private boundary failed: {secret_flag}")
    require(commitment.get("historical_astra_provenance") == "NOT_ATTESTED", "private ancestry guessed")
    assistance = receipt.get("assistance_provenance")
    require_exact_keys(
        assistance,
        {
            "surface",
            "workflow_labels",
            "runtime_model_identifier",
            "runtime_identity_evidence",
            "no_astra_output_knowingly_admitted",
            "no_astra_assurance",
            "no_astra_scope",
            "no_astra_limitations",
            "provenance_partitions",
            "aggregate_astra_state_for_public_genesis_bytes",
        },
        "genesis assistance provenance",
    )
    require(assistance.get("no_astra_output_knowingly_admitted") is True, "current Astra declaration changed")
    require(assistance.get("no_astra_assurance") == "SESSION_RECORD_DECLARED_NOT_PROVIDER_ATTESTED", "assurance overstated")
    require(assistance.get("no_astra_scope") == "public genesis construction only", "no-Astra scope changed")
    require(
        assistance.get("no_astra_limitations")
        == [
            "hidden provider routing is not excluded",
            "training or distillation ancestry is not excluded",
            "unrecorded outside interactions are not excluded",
            "the name Astra is not bound here to a provider-signed canonical identifier",
        ],
        "no-Astra limitations changed",
    )
    require(assistance.get("aggregate_astra_state_for_public_genesis_bytes") == "session_declared_absent", "bad aggregate Astra state")
    partitions = assistance.get("provenance_partitions")
    require(isinstance(partitions, list) and len(partitions) == 2, "bad provenance partitions")
    for partition in partitions:
        require(isinstance(partition, dict), "provenance partition is not an object")
        if partition.get("partition") == "public_genesis_construction":
            require_exact_keys(partition, {"partition", "materially_incorporated", "astra_state"}, "public provenance partition")
        elif partition.get("partition") == "private_checkpoint_history":
            require_exact_keys(
                partition,
                {"partition", "materially_incorporated", "reference_type", "astra_state"},
                "private provenance partition",
            )
        else:
            raise VerificationError("unknown provenance partition")
    by_partition = {part.get("partition"): part for part in partitions if isinstance(part, dict)}
    require(by_partition.get("public_genesis_construction", {}).get("astra_state") == "session_declared_absent", "public genesis state changed")
    private_partition = by_partition.get("private_checkpoint_history", {})
    require(private_partition.get("astra_state") == "unknown", "private history state upgraded")
    require(private_partition.get("materially_incorporated") is False, "private checkpoint marked incorporated")
    attestation = receipt.get("attestation_status_at_creation")
    require_exact_keys(
        attestation,
        {
            "human_cryptographic_signature_ref",
            "trusted_external_timestamp_ref",
            "later_attestations_are_append_only_sidecars",
        },
        "genesis attestation status",
    )
    require(attestation.get("human_cryptographic_signature_ref") is None, "unexpected human signature")
    require(attestation.get("trusted_external_timestamp_ref") is None, "unexpected trusted timestamp")
    require(attestation.get("later_attestations_are_append_only_sidecars") is True, "mutable attestation policy")
    require(receipt.get("verifier_notice") == VERIFIER_NOTICE, "verifier notice changed")
    verify_artifact_manifest(receipt)
    return receipt


def parse_utc(value: object, label: str) -> datetime:
    require(isinstance(value, str) and value.endswith("Z"), f"bad UTC time: {label}")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise VerificationError(f"bad UTC time {label}: {value}") from exc


def verify_run_receipt(
    receipt: dict[str, Any],
    path: Path,
    source_by_id: dict[str, dict[str, Any]],
) -> tuple[list[str], set[str]]:
    label = path.name
    require_exact_keys(
        receipt,
        {
            "schema",
            "event_id",
            "event_id_scheme",
            "event_origin",
            "receipt_id",
            "kind",
            "arena",
            "parents",
            "claimed_times",
            "steward",
            "target",
            "board",
            "sources",
            "runtime",
            "artifacts",
            "claim_delta",
            "claim_boundary",
            "known_gaps",
            "assistance",
            "disclosure_scope",
            "attestation_status_at_creation",
        },
        f"run receipt {label}",
    )
    require(receipt.get("schema") == "hearthline-plays.millennium-run.v1", f"unknown receipt schema: {label}")
    verify_event_identity(receipt, label)
    kind = receipt.get("kind")
    require(
        kind in {"run", "protocol_upgrade", "correction", "merge", "release"},
        f"bad event kind: {label}",
    )
    require(receipt.get("event_origin") == "model_drafted_pending_steward_review", f"run event origin changed: {label}")
    if kind in {"run", "correction"}:
        require(receipt.get("arena") in ACTIVE_ARENAS, f"bad run arena: {label}")
    elif kind == "protocol_upgrade":
        require(receipt.get("arena") == "protocol", f"bad protocol-upgrade arena: {label}")
    else:
        require(
            receipt.get("arena") in set(ACTIVE_ARENAS) | {"protocol", "project"},
            f"bad merge/release arena: {label}",
        )
    require(receipt.get("steward") == "Christopher D. Pang", f"unexpected steward: {label}")
    parents = receipt.get("parents")
    require(isinstance(parents, list) and parents and all(is_event_id(parent) for parent in parents), f"bad event parents: {label}")
    require(len(set(parents)) == len(parents), f"duplicate event parent: {label}")
    if kind == "merge":
        require(len(parents) >= 2, f"merge needs at least two parents: {label}")
    else:
        require(len(parents) == 1, f"non-merge event needs one parent: {label}")
    times = receipt.get("claimed_times")
    require_exact_keys(times, {"started_at_utc", "ended_at_utc"}, f"run times {label}")
    started = parse_utc(times.get("started_at_utc"), f"{label} start")
    ended = parse_utc(times.get("ended_at_utc"), f"{label} end")
    require(ended >= started, f"run ends before it starts: {label}")
    target = receipt.get("target")
    require_exact_keys(target, {"statement", "scope", "quantifiers", "promotion_ceiling"}, f"run target {label}")
    ceiling = target.get("promotion_ceiling")
    require(ceiling in CLAIM_STATES, f"bad promotion ceiling: {label}")
    board = require_exact_keys(
        receipt.get("board"),
        {"objects", "legal_moves", "adversary", "verifier"},
        f"run board {label}",
    )
    require(all(isinstance(value, str) and value for value in board.values()), f"empty board field: {label}")
    claim_delta = receipt.get("claim_delta")
    require_exact_keys(claim_delta, {"before", "after", "basis"}, f"run claim delta {label}")
    require(claim_delta.get("before") in CLAIM_STATES, f"bad prior claim state: {label}")
    after = claim_delta.get("after")
    require(after in CLAIM_STATES, f"bad resulting claim state: {label}")
    require(after == ceiling, f"result exceeds or does not match declared ceiling: {label}")
    gaps = receipt.get("known_gaps")
    require(isinstance(gaps, list) and all(isinstance(gap, str) for gap in gaps), f"bad gaps: {label}")
    if after == "proof_candidate":
        require(not gaps, f"proof candidate has known gaps: {label}")
    sources = receipt.get("sources")
    require(isinstance(sources, list) and sources, f"missing sources: {label}")
    for source in sources:
        require_exact_keys(source, {"id", "sha256"}, f"run source {label}")
        locked = source_by_id.get(source.get("id"))
        require(locked is not None, f"unlocked source: {label}")
        require(source.get("sha256") == locked.get("sha256"), f"source digest mismatch: {label}")
    artifacts = receipt.get("artifacts")
    require(isinstance(artifacts, list) and artifacts, f"missing artifacts: {label}")
    private_labels: list[str] = []
    public_artifact_paths: set[str] = set()
    for artifact in artifacts:
        require(isinstance(artifact, dict), f"bad artifact: {label}")
        visibility = artifact.get("visibility")
        if visibility == "public":
            require_exact_keys(artifact, {"visibility", "path", "bytes", "sha256", "origin"}, f"public artifact {label}")
            public_path = safe_public_path(artifact.get("path"))
            require(public_path.stat().st_size == artifact.get("bytes"), f"artifact byte mismatch: {label}")
            require(sha256_file(public_path) == artifact.get("sha256"), f"artifact digest mismatch: {label}")
            public_artifact_paths.add(artifact["path"])
        elif visibility == "private":
            require_exact_keys(
                artifact,
                {"visibility", "nonidentifying_label", "commitment_sha256", "commitment_scheme", "origin"},
                f"private artifact {label}",
            )
            require(isinstance(artifact.get("nonidentifying_label"), str), f"private label missing: {label}")
            require(is_sha256(artifact.get("commitment_sha256")), f"private commitment invalid: {label}")
            require(
                artifact.get("commitment_scheme")
                == "sha256(domain_separator || nonce_bytes || artifact_sha256_bytes)",
                f"private commitment scheme changed: {label}",
            )
            private_labels.append(artifact["nonidentifying_label"])
        else:
            raise VerificationError(f"bad artifact visibility: {label}")
        require(artifact.get("origin") in ORIGINS, f"bad artifact origin: {label}")
    runtime = require_exact_keys(
        receipt.get("runtime"),
        {"surface", "model_identifier", "identity_evidence", "environment", "environment_sha256"},
        f"run runtime {label}",
    )
    environment = require_exact_keys(
        runtime.get("environment"),
        {"implementation", "python_version", "platform", "byteorder", "algorithm"},
        f"run environment {label}",
    )
    environment_bytes = json.dumps(environment, sort_keys=True, separators=(",", ":")).encode("utf-8")
    require(hashlib.sha256(environment_bytes).hexdigest() == runtime.get("environment_sha256"), f"environment digest mismatch: {label}")
    require(runtime.get("identity_evidence") in {"provider_attested", "interface_observed", "self_reported", "unknown"}, f"bad runtime identity evidence: {label}")
    boundary = receipt.get("claim_boundary")
    require_exact_keys(
        boundary,
        {
            "official_problem_solution_claimed",
            "external_acceptance_claimed",
            "cmi_prize_awarded_claimed",
            "external_evidence",
        },
        f"run claim boundary {label}",
    )
    official_claim = boundary.get("official_problem_solution_claimed")
    external_claim = boundary.get("external_acceptance_claimed")
    prize_claim = boundary.get("cmi_prize_awarded_claimed")
    require(all(isinstance(flag, bool) for flag in (official_claim, external_claim, prize_claim)), f"non-boolean claim boundary: {label}")
    evidence = boundary.get("external_evidence")
    require(
        isinstance(evidence, list)
        and all(isinstance(item, str) and item for item in evidence),
        f"external evidence must contain only nonempty string references: {label}",
    )
    if official_claim:
        require(after in {"proof_candidate", "externally_established"} and not gaps, f"unsupported official claim: {label}")
    if external_claim:
        require(after == "externally_established" and evidence, f"unsupported external claim: {label}")
    if after == "externally_established":
        require(external_claim is True and evidence, f"external state lacks evidence: {label}")
    else:
        require(external_claim is False, f"external claim mismatches state: {label}")
    if prize_claim:
        require(
            external_claim
            and evidence
            and any(item.startswith("https://www.claymath.org/") for item in evidence),
            f"unsupported prize claim: {label}",
        )
    assistance = receipt.get("assistance")
    require_exact_keys(
        assistance,
        {"hearthline_used", "pal_used", "no_astra_state", "incorporated_contribution_states", "limitations"},
        f"run assistance {label}",
    )
    aggregate = assistance.get("no_astra_state")
    states = assistance.get("incorporated_contribution_states")
    require(aggregate in ASTRA_RANK, f"bad Astra aggregate: {label}")
    require(isinstance(states, list) and states and all(state in ASTRA_RANK for state in states), f"bad Astra inputs: {label}")
    require(ASTRA_RANK[aggregate] >= max(ASTRA_RANK[state] for state in states), f"Astra state improved over input: {label}")
    require(isinstance(assistance.get("hearthline_used"), bool), f"bad Hearthline flag: {label}")
    require(isinstance(assistance.get("pal_used"), bool), f"bad PAL flag: {label}")
    require(
        isinstance(assistance.get("limitations"), list)
        and all(isinstance(item, str) and item for item in assistance["limitations"]),
        f"bad assistance limitations: {label}",
    )
    disclosure = receipt.get("disclosure_scope")
    require_exact_keys(
        disclosure,
        {
            "deterministic_replay_inputs_complete",
            "research_provenance_complete",
            "known_omissions",
            "private_items",
        },
        f"run disclosure {label}",
    )
    require(disclosure.get("deterministic_replay_inputs_complete") is True, f"incomplete replay inputs: {label}")
    require(disclosure.get("research_provenance_complete") is False, f"research provenance overstated: {label}")
    omissions = disclosure.get("known_omissions")
    require(
        isinstance(omissions, list) and omissions and all(isinstance(item, str) and item for item in omissions),
        f"known provenance omissions missing: {label}",
    )
    listed_private = disclosure.get("private_items")
    require(isinstance(listed_private, list) and sorted(listed_private) == sorted(private_labels), f"private disclosure mismatch: {label}")
    attestation = receipt.get("attestation_status_at_creation")
    require_exact_keys(
        attestation,
        {"human_cryptographic_signature_ref", "trusted_external_timestamp_ref"},
        f"run attestation {label}",
    )
    require(attestation.get("human_cryptographic_signature_ref") is None, f"unexpected run signature: {label}")
    require(attestation.get("trusted_external_timestamp_ref") is None, f"unexpected run timestamp: {label}")
    return parents, public_artifact_paths


def verify_all_receipts(
    genesis: dict[str, Any],
    source_by_id: dict[str, dict[str, Any]],
) -> tuple[set[str], dict[str, str], dict[str, str]]:
    event_ids = {genesis["event_id"]}
    pending_parents: dict[str, list[str]] = {}
    authorized_paths: set[str] = set()
    artifact_owners: dict[str, str] = {}
    artifact_kinds: dict[str, str] = {}
    for path in sorted(RECEIPTS.glob("*.json")):
        require(
            re.fullmatch(r"\d{8}T\d{6}Z-[a-z0-9-]+\.json", path.name) is not None,
            f"bad receipt filename: {path.name}",
        )
        require(path.with_suffix(".md").is_file(), f"missing paired Markdown receipt: {path.name}")
        if path == GENESIS_PATH:
            continue
        receipt = load_json(path)
        require(path.name[:16] in str(receipt.get("receipt_id", "")), f"receipt filename/ID mismatch: {path.name}")
        parents, artifact_paths = verify_run_receipt(receipt, path, source_by_id)
        event_id = receipt["event_id"]
        require(event_id not in event_ids, f"duplicate event ID: {event_id}")
        event_ids.add(event_id)
        pending_parents[event_id] = parents
        receipt_relative = path.relative_to(ROOT).as_posix()
        authorized_paths.add(receipt_relative)
        for artifact_path in artifact_paths:
            require(artifact_path not in GENESIS_ARTIFACT_PATHS, f"run reuses a genesis artifact path: {artifact_path}")
            require(artifact_path not in artifact_owners, f"artifact path is reused by multiple receipts: {artifact_path}")
            artifact_owners[artifact_path] = receipt_relative
            artifact_kinds[artifact_path] = receipt["kind"]
        authorized_paths.update(artifact_paths)
    for event_id, parents in pending_parents.items():
        require(event_id not in parents, f"self-parenting event: {event_id}")
        require(all(parent in event_ids for parent in parents), f"unknown parent for event: {event_id}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(event_id: str) -> None:
        if event_id in visited:
            return
        require(event_id not in visiting, f"receipt DAG cycle at {event_id}")
        visiting.add(event_id)
        for parent in pending_parents.get(event_id, []):
            visit(parent)
        visiting.remove(event_id)
        visited.add(event_id)

    for event_id in event_ids:
        visit(event_id)
    return authorized_paths, artifact_owners, artifact_kinds


def verify_ci_execution_surface(artifact_kinds: dict[str, str]) -> None:
    discovered = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "tests").glob("test_millennium_*.py")
        if path.is_file()
    } | {
        path.relative_to(ROOT).as_posix()
        for path in (MILLENNIUM / "tools").glob("verify_upgrade_*.py")
        if path.is_file()
    }
    for relative in sorted(discovered):
        if relative in GENESIS_ARTIFACT_PATHS:
            continue
        require(
            artifact_kinds.get(relative) == "protocol_upgrade",
            f"CI-executed path is not genesis-bound or owned by a protocol-upgrade receipt: {relative}",
        )


def git_output(*args: str, check: bool = True) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        if check:
            raise VerificationError(f"git check failed: {exc}") from exc
        return ""
    if check and completed.returncode != 0:
        raise VerificationError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def git_blob(commit: str, relative: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "show", f"{commit}:{relative}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError(f"cannot read Git blob {commit}:{relative}: {exc}") from exc
    require(completed.returncode == 0, f"missing Git blob {commit}:{relative}")
    return completed.stdout


def canonical_genesis_commit_or_none() -> str | None:
    genesis_relative = GENESIS_PATH.relative_to(ROOT).as_posix()
    tracked = git_output("ls-files", "--error-unmatch", genesis_relative, check=False)
    if not tracked:
        return None
    added = git_output(
        "log",
        "--diff-filter=A",
        "--format=%H",
        "--reverse",
        "--",
        genesis_relative,
    ).splitlines()
    require(len(added) <= 1, "genesis receipt add history is ambiguous")
    return added[0] if added else None


def tracked_millennium_paths() -> set[str] | None:
    output = git_output("ls-files", "-z", "--", "millennium", check=False)
    if not output:
        return None
    return {item for item in output.split("\0") if item}


def verify_checksums(run_authorized_paths: set[str]) -> None:
    require(SUMS_PATH.is_file() and not SUMS_PATH.is_symlink(), "missing or symlinked SHA256SUMS")
    recorded: dict[str, str] = {}
    for line_number, line in enumerate(SUMS_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            continue
        parts = line.split("  ", 1)
        require(len(parts) == 2 and is_sha256(parts[0]), f"bad checksum line {line_number}")
        relative = parts[1]
        safe_public_path(relative)
        require(relative.startswith("millennium/"), f"out-of-scope checksum path: {relative}")
        require(relative not in recorded, f"duplicate checksum path: {relative}")
        recorded[relative] = parts[0]

    tracked = tracked_millennium_paths()
    if tracked is None:
        actual_paths = {
            path.relative_to(ROOT).as_posix()
            for path in MILLENNIUM.rglob("*")
            if path.is_file()
            and path != SUMS_PATH
            and "__pycache__" not in path.parts
            and "private" not in {part.lower() for part in path.relative_to(MILLENNIUM).parts}
            and ".private." not in path.name.lower()
        }
    else:
        require("millennium/SHA256SUMS" in tracked, "SHA256SUMS is not tracked")
        prohibited = [
            path for path in tracked
            if "private" in {part.lower() for part in Path(path).parts}
            or ".private." in Path(path).name.lower()
        ]
        require(not prohibited, f"tracked private paths: {prohibited}")
        actual_paths = tracked - {"millennium/SHA256SUMS"}
    require(set(recorded) == actual_paths, "SHA256SUMS file set differs from tracked public Millennium payload")
    authorized_paths = {
        path for path in GENESIS_ARTIFACT_PATHS if path.startswith("millennium/")
    } | {
        "millennium/provenance/artifact-origins.json",
        GENESIS_PATH.relative_to(ROOT).as_posix(),
    } | {path for path in run_authorized_paths if path.startswith("millennium/")}
    require(actual_paths == authorized_paths, "public Millennium file is not bound by a genesis or run receipt")
    for relative, expected in recorded.items():
        actual = sha256_file(ROOT / relative)
        require(actual == expected, f"checksum mismatch: {relative}")


def verify_git_lineage(
    run_authorized_paths: set[str],
    artifact_owners: dict[str, str],
    allow_uncommitted: bool,
) -> None:
    genesis_relative = GENESIS_PATH.relative_to(ROOT).as_posix()
    canonical_commit = canonical_genesis_commit_or_none()
    if canonical_commit is None:
        require(allow_uncommitted, "genesis receipt is not committed; use --allow-uncommitted only for draft verification")
        require(git_output("rev-parse", "HEAD") == EXPECTED_PARENT_COMMIT, "draft is not based directly on the expected parent")
        print("Millennium genesis Git-lineage check: DRAFT ONLY (explicitly allowed uncommitted)")
        return
    require(git_output("cat-file", "-t", EXPECTED_PARENT_COMMIT) == "commit", "parent commit is unavailable")
    require(git_output("show", "-s", "--format=%T", EXPECTED_PARENT_COMMIT) == EXPECTED_PARENT_TREE, "parent tree mismatch in Git")
    parents = git_output("show", "-s", "--format=%P", canonical_commit).split()
    require(parents == [EXPECTED_PARENT_COMMIT], "canonical genesis commit has the wrong parent")
    immutable_genesis_paths = set(GENESIS_ARTIFACT_PATHS) | {
        genesis_relative,
        "millennium/provenance/artifact-origins.json",
    }
    for relative in sorted(immutable_genesis_paths):
        require(
            git_blob(canonical_commit, relative) == (ROOT / relative).read_bytes(),
            f"genesis-bound artifact changed after canonical commit: {relative}",
        )
        later_touches = git_output(
            "log",
            "--format=%H",
            f"{canonical_commit}..HEAD",
            "--",
            relative,
        ).splitlines()
        require(not later_touches, f"genesis-bound artifact was touched later: {relative}")
    historical_output = git_output(
        "log",
        "--diff-filter=A",
        "--format=",
        "--name-only",
        f"{EXPECTED_PARENT_COMMIT}..HEAD",
        "--",
        "millennium/receipts",
    )
    historical_receipts = {
        line
        for line in historical_output.splitlines()
        if line
        and Path(line).suffix in {".json", ".md"}
        and line != "millennium/receipts/README.md"
    }
    current_receipts = {
        path.relative_to(ROOT).as_posix()
        for suffix in ("*.json", "*.md")
        for path in RECEIPTS.glob(suffix)
        if path.name != "README.md"
    }
    require(historical_receipts == current_receipts, "a historical receipt was deleted or an untracked receipt exists")
    for relative in sorted(historical_receipts):
        receipt_path = ROOT / relative
        added = git_output(
            "log",
            "--diff-filter=A",
            "--format=%H",
            "--reverse",
            "--",
            relative,
        ).splitlines()
        require(len(added) == 1, f"receipt add history is ambiguous: {relative}")
        require(
            git_blob(added[0], relative) == receipt_path.read_bytes(),
            f"receipt changed after its append event: {relative}",
        )
        later_touches = git_output(
            "log",
            "--format=%H",
            f"{added[0]}..HEAD",
            "--",
            relative,
        ).splitlines()
        require(not later_touches, f"receipt was touched after its append event: {relative}")
    for artifact_path, owner_receipt in sorted(artifact_owners.items()):
        owner_added = git_output(
            "log",
            "--diff-filter=A",
            "--format=%H",
            "--reverse",
            "--",
            owner_receipt,
        ).splitlines()
        artifact_added = git_output(
            "log",
            "--diff-filter=A",
            "--format=%H",
            "--reverse",
            "--",
            artifact_path,
        ).splitlines()
        require(len(owner_added) == 1, f"artifact owner receipt history is ambiguous: {owner_receipt}")
        require(artifact_added == owner_added, f"artifact was not added with its receipt: {artifact_path}")
        later_touches = git_output(
            "log",
            "--format=%H",
            f"{owner_added[0]}..HEAD",
            "--",
            artifact_path,
        ).splitlines()
        require(not later_touches, f"receipted artifact was touched later: {artifact_path}")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", canonical_commit, "HEAD"],
        cwd=ROOT,
        check=False,
        timeout=15,
    )
    require(ancestor.returncode == 0, "canonical genesis commit is not an ancestor of HEAD")
    print(f"Millennium canonical genesis commit: {canonical_commit}")


def verify_private_reveal(
    genesis: dict[str, Any],
    reveal_path: Path,
    artifact_path: Path | None,
) -> None:
    reveal = load_json(reveal_path)
    require(reveal.get("schema") == "hearthline-plays.millennium-private-reveal.v1", "bad reveal schema")
    public_genesis = require_exact_keys(
        reveal.get("public_genesis"),
        {
            "repository",
            "branch",
            "receipt_id",
            "event_id",
            "canonical_commit",
            "commitment_sha256",
        },
        "private reveal public-genesis binding",
    )
    require(public_genesis.get("receipt_id") == genesis.get("receipt_id"), "reveal receipt ID points elsewhere")
    require(public_genesis.get("event_id") == genesis.get("event_id"), "reveal event ID points elsewhere")
    private = reveal.get("private_artifact")
    require(isinstance(private, dict), "bad private artifact record")
    nonce_hex = private.get("nonce_hex")
    artifact_sha256 = private.get("sha256")
    require(is_sha256(nonce_hex), "bad reveal nonce")
    require(is_sha256(artifact_sha256), "bad revealed artifact digest")
    calculated = hashlib.sha256(
        COMMITMENT_DOMAIN + bytes.fromhex(nonce_hex) + bytes.fromhex(artifact_sha256)
    ).hexdigest()
    public_commitment = genesis["private_checkpoint_commitment"]["commitment_sha256"]
    require(calculated == public_commitment, "private reveal does not open public commitment")
    require(public_genesis.get("commitment_sha256") == public_commitment, "reveal points elsewhere")
    canonical_commit = canonical_genesis_commit_or_none()
    if canonical_commit is not None:
        require(public_genesis.get("canonical_commit") == canonical_commit, "reveal canonical commit points elsewhere")
    if artifact_path is not None:
        require(artifact_path.is_file() and not artifact_path.is_symlink(), f"missing private artifact: {artifact_path}")
        require(sha256_file(artifact_path) == artifact_sha256, "private artifact digest mismatch")
        require(artifact_path.stat().st_size == private.get("bytes"), "private artifact byte mismatch")

    sensitive_values = [private.get("filename"), artifact_sha256, nonce_hex]
    sensitive_bytes = [value.encode("utf-8") for value in sensitive_values if isinstance(value, str) and value]
    genesis_tracked = git_output(
        "ls-files", "--error-unmatch", GENESIS_PATH.relative_to(ROOT).as_posix(), check=False
    )
    tracked = git_output("ls-files", "-z", check=False)
    if genesis_tracked and tracked:
        public_paths = [ROOT / item for item in tracked.split("\0") if item]
    else:
        public_paths = [
            path for path in ROOT.rglob("*")
            if path.is_file()
            and ".git" not in path.parts
            and "__pycache__" not in path.parts
            and "private" not in {part.lower() for part in path.relative_to(ROOT).parts}
            and ".private." not in path.name.lower()
        ]
    for public_path in public_paths:
        if not public_path.is_file():
            continue
        try:
            payload = public_path.read_bytes()
        except OSError as exc:
            raise VerificationError(f"cannot scan public path {public_path}: {exc}") from exc
        for needle in sensitive_bytes:
            require(needle not in payload, f"private reveal value leaked into public file: {public_path.relative_to(ROOT)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, help="directory containing downloaded official PDFs")
    parser.add_argument("--private-reveal", type=Path, help="private reveal receipt held outside Git")
    parser.add_argument("--private-artifact", type=Path, help="artifact opened by the private reveal")
    parser.add_argument(
        "--allow-uncommitted",
        action="store_true",
        help="permit draft-only checks before the canonical genesis commit exists",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.private_artifact is not None and args.private_reveal is None:
        raise VerificationError("--private-artifact requires --private-reveal")
    source_by_id = verify_source_lock(args.source_dir)
    genesis = verify_genesis()
    run_authorized_paths, artifact_owners, artifact_kinds = verify_all_receipts(genesis, source_by_id)
    verify_ci_execution_surface(artifact_kinds)
    verify_checksums(run_authorized_paths)
    verify_git_lineage(run_authorized_paths, artifact_owners, args.allow_uncommitted)
    if args.private_reveal is not None:
        verify_private_reveal(genesis, args.private_reveal, args.private_artifact)
    print("Millennium genesis verification: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print(f"Millennium genesis verification: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
