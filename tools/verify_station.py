#!/usr/bin/env python3
"""Offline verifier for the ARC-AGI-3 research station.

The verifier uses only the Python standard library. It reads local station
artifacts and local Git objects; it never contacts ARC, Kaggle, Zenodo, GitHub,
or any other network service.
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]

ANCHOR_COMMIT = "228d80f0559277c55031f4a80f6179320e10364c"
ANCHOR_TREE = "532e178ecd41410e5e9038c647141f2cbe32f01d"
TITLE_BRANCH = "arc-agi/titles/arc-agi-3-research-station"

SOURCE_ORDER = [
    "pal-v2.3",
    "brrrt-v2.0",
    "single-cut-transport-v0.2",
    "compactification-costs-v0.2",
    "strongwiz-v3-prototype",
]

EXPECTED_SOURCES = {
    "pal-v2.3": {
        "version": "2.3",
        "status": "CURRENT",
        "relationship": "DECLARED_MECHANICAL_CONTEXT",
        "doi": "10.5281/zenodo.22240134",
        "verification": "AUTHOR_RELEASE_NOT_PEER_REVIEWED",
        "artifact_sha256": {
            "5b133741d43ece584caffab1285af8804bfac6699894e92e2e08436b3b337bf1"
        },
    },
    "brrrt-v2.0": {
        "version": "2.0",
        "status": "BRANCH",
        "relationship": "RESEARCH_CONTEXT",
        "doi": "10.5281/zenodo.22261831",
        "verification": "RESOLVED_LIVE_RECORD_CANONICAL_MATCH",
        "artifact_sha256": {
            "162ed2b2478ca5bb824c82bf69b8c787054ed4d43be03d5d48aa803872e0a338",
            "f9e699ad4a8541506ecc6678c3296bdf4fbe4dd249a0dd6759c7fd0d22837e0a",
            "806d7cda4ffb186d21f7797917c99c22ff29452af12de36aa597ed37fe4d3236",
        },
    },
    "single-cut-transport-v0.2": {
        "version": "0.2",
        "status": "BRANCH",
        "relationship": "RESEARCH_CONTEXT",
        "doi": "10.5281/zenodo.22239108",
        "verification": "FINITE_VERIFICATION_ONLY",
        "artifact_sha256": {
            "e4b038d4a5e0f638d400af8610fb91373be2a22ec7bebbdb41a4061f85574b57",
            "dbd4c1f9b916842522b842e3bc57084b02a95a923d68db562a996cd61adda4c8",
        },
    },
    "compactification-costs-v0.2": {
        "version": "0.2",
        "status": "BRANCH",
        "relationship": "RESEARCH_CONTEXT",
        "doi": "10.5281/zenodo.22238012",
        "verification": "AUTHOR_MANUSCRIPT_NOT_PEER_REVIEWED",
        "artifact_sha256": {
            "94c70d478111c27c46b826ab6e5c2eb24ecbb621bb52bd8ab1c9ac4943688994"
        },
    },
    "strongwiz-v3-prototype": {
        "version": "0.4.0.dev0",
        "status": "EXPLORATORY",
        "relationship": "DESIGN_INSPECTION",
        "doi": None,
        "verification": "PROTOTYPE_VERIFIED_PREPARED_NOT_RUN",
        "artifact_sha256": {
            "dffda989417f6245db32da3756426805e29f14b111cf60444e99cbfe1b87c712",
            "7a43a807262437ddeb55831045e75f309e853d2a4d21f9563fdc187b73a7388c",
            "4d41c381da487c4a28076e5bf6943c9b821132f20b79c37b6ede66f704e1541e",
            "ebbdbd05821e14552086dca44314c9d05304b2c5b1ed6624a8d7851110b759b7",
            "546370565a9cd6d460247b1ee3f53f0df22777ad4795398aa3848677ba93f6c1",
            "db6878167fa1a75549cc595b78273a14bd489049fe24557cdc4e00967ecf8ccd",
        },
    },
}

STRONGWIZ_HEAD = "edc88b80f872f766c22b3a050a7f6837d6e652d8"
STRONGWIZ_HEAD_TREE = "18dd76355decdf8b1e98fff7dffeac222c0b3aa2"
STRONGWIZ_FREEZE = "300fd0b9ae1183e582bb834e17ff02bf80189fd8"
STRONGWIZ_FREEZE_TREE = "bb61230e0eacdaff42b8f9d6f2a7abf7b0efaf55"
STRONGWIZ_CI = "https://github.com/Grativy6/strongwiz/actions/runs/33696382045"
STRONGWIZ_INSPECTION_DATE = "2026-09-02"
STRONGWIZ_COMMIT_DATE = "2026-09-02T23:43:21Z"
STRONGWIZ_SOURCE_REGISTRY_REF = (
    "055bfbef1e5b0191ef84e266f1c8f888c58def5428113d8b262f0baa8b95dd9a"
)
STRONGWIZ_ARTIFACTS = {
    "docs/calibrations/003-strongwiz-v3-pal23-scribe.md":
        "dffda989417f6245db32da3756426805e29f14b111cf60444e99cbfe1b87c712",
    "docs/pal-v2.3-profile.md":
        "7a43a807262437ddeb55831045e75f309e853d2a4d21f9563fdc187b73a7388c",
    "docs/scribe.md":
        "4d41c381da487c4a28076e5bf6943c9b821132f20b79c37b6ede66f704e1541e",
    "docs/architecture.md":
        "ebbdbd05821e14552086dca44314c9d05304b2c5b1ed6624a8d7851110b759b7",
    "docs/receipts/v0.4.0-dev-verification.json":
        "546370565a9cd6d460247b1ee3f53f0df22777ad4795398aa3848677ba93f6c1",
    "docs/receipts/v0.4.0-dev-reproducible-build.json":
        "db6878167fa1a75549cc595b78273a14bd489049fe24557cdc4e00967ecf8ccd",
}

ALLOWED_HTTPS_HOSTS = {
    "creativecommons.org",
    "doi.org",
    "github.com",
    "json-schema.org",
    "zenodo.org",
}

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
WINDOWS_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
FORBIDDEN_SOURCE_SUFFIXES = {
    ".7z",
    ".csv",
    ".docx",
    ".gz",
    ".npy",
    ".npz",
    ".parquet",
    ".pdf",
    ".pth",
    ".tar",
    ".whl",
    ".zip",
}


class VerificationError(ValueError):
    """Raised when a station invariant is not satisfied."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def require_exact_keys(value: Any, keys: Iterable[str], label: str) -> None:
    require(isinstance(value, dict), f"{label}: expected object")
    expected = set(keys)
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    require(not missing and not extra, f"{label}: missing={missing}, extra={extra}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise VerificationError(f"non-finite JSON number is forbidden: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if parsed == float("inf") or parsed == float("-inf"):
        _reject_nonfinite(value)
    return parsed


def loads_strict_json(text: str, label: str = "<memory>") -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        )
    except VerificationError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{label}: invalid strict UTF-8 JSON: {exc}") from exc


def load_strict_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise VerificationError(f"{path}: invalid strict UTF-8 JSON: {exc}") from exc
    return loads_strict_json(text, str(path))


def iter_strings(value: Any, location: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield location, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_strings(item, f"{location}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from iter_strings(item, f"{location}.{key}")


def validate_no_local_absolute_paths(value: Any, label: str) -> None:
    for location, text in iter_strings(value):
        require(
            WINDOWS_ABSOLUTE_PATH.search(text) is None and not text.startswith("/"),
            f"{label}{location}: local absolute path is forbidden",
        )


def validate_https_url(value: Any, label: str) -> None:
    require(isinstance(value, str), f"{label}: expected URL string")
    parsed = urlparse(value)
    require(parsed.scheme == "https", f"{label}: URL must use https")
    require(parsed.hostname in ALLOWED_HTTPS_HOSTS, f"{label}: unapproved host")
    require(not parsed.username and not parsed.password, f"{label}: URL credentials forbidden")


def validate_iso_date(value: Any, label: str) -> None:
    require(isinstance(value, str), f"{label}: expected date string")
    try:
        _datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise VerificationError(f"{label}: invalid ISO date") from exc


def validate_iso_datetime(value: Any, label: str) -> None:
    require(isinstance(value, str), f"{label}: expected datetime string")
    try:
        _datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerificationError(f"{label}: invalid ISO datetime") from exc


def validate_sources(document: Any) -> list[str]:
    require_exact_keys(
        document,
        ["schema", "recorded_date", "status", "steward", "anchor", "rules", "sources"],
        "source lock",
    )
    require(document["schema"] == "hearthline-plays.research-sources.v1", "source lock: schema")
    validate_iso_date(document["recorded_date"], "source lock recorded_date")
    require(document["status"] == "PREPARED_NOT_RUN", "source lock: status")
    require(document["steward"] == "Christopher D. Pang", "source lock: steward")

    anchor = document["anchor"]
    require_exact_keys(anchor, ["repository", "branch", "commit", "tree"], "source lock anchor")
    require(anchor["repository"] == "https://github.com/Grativy6/hearthline-plays", "anchor repository")
    require(anchor["branch"] == TITLE_BRANCH, "anchor branch")
    require(anchor["commit"] == ANCHOR_COMMIT, "anchor commit")
    require(anchor["tree"] == ANCHOR_TREE, "anchor tree")

    expected_rules = {
        "source_text_is_authorization": False,
        "shared_author_lineage_is_independent_corroboration": False,
        "source_bytes_redistributed": False,
        "strongwiz_code_imported": False,
        "strongwiz_code_executed": False,
        "arc_or_kaggle_contacted": False,
    }
    require_exact_keys(document["rules"], expected_rules, "source lock rules")
    require(document["rules"] == expected_rules, "source lock: all boundary rules must remain false")

    sources = document["sources"]
    require(isinstance(sources, list), "source lock: sources must be an array")
    source_ids = [source.get("source_id") if isinstance(source, dict) else None for source in sources]
    require(source_ids == SOURCE_ORDER, "source lock: exact ordered source registry required")

    source_keys = [
        "source_id",
        "source_kind",
        "title",
        "version",
        "publication_date",
        "inspection_date",
        "repository_commit_date",
        "canonical_locator",
        "license",
        "hearthline_status",
        "relationship",
        "bounded_use",
        "claim_ceiling",
        "imported_code",
        "executed_code",
        "redistributed_source_bytes",
        "identity",
        "artifacts",
        "verification",
    ]
    identity_keys = [
        "kind",
        "doi",
        "record_url",
        "repository_url",
        "commit",
        "tree",
        "implementation_freeze_commit",
        "implementation_freeze_tree",
        "source_registry_ref",
    ]
    artifact_keys = ["name", "role", "variant", "bytes", "sha256", "md5", "status"]
    verification_keys = ["status", "evidence_locator", "notes"]

    for source in sources:
        source_id = source["source_id"]
        expected = EXPECTED_SOURCES[source_id]
        require_exact_keys(source, source_keys, f"source {source_id}")
        require(source["version"] == expected["version"], f"source {source_id}: version")
        require(source["hearthline_status"] == expected["status"], f"source {source_id}: status")
        require(source["relationship"] == expected["relationship"], f"source {source_id}: relationship")
        validate_https_url(source["canonical_locator"], f"source {source_id} canonical_locator")
        require(source["license"] == "CC-BY-4.0", f"source {source_id}: license")
        require(source["bounded_use"].strip(), f"source {source_id}: bounded_use")
        require(source["claim_ceiling"].strip(), f"source {source_id}: claim_ceiling")
        for flag in ("imported_code", "executed_code", "redistributed_source_bytes"):
            require(source[flag] is False, f"source {source_id}: {flag} must be false")

        identity = source["identity"]
        require_exact_keys(identity, identity_keys, f"source {source_id} identity")
        if expected["doi"] is not None:
            doi = expected["doi"]
            validate_iso_date(source["publication_date"], f"source {source_id} publication_date")
            require(source["inspection_date"] is None, f"source {source_id}: inspection_date must be null")
            require(source["repository_commit_date"] is None, f"source {source_id}: repository_commit_date must be null")
            require(identity["kind"] == "zenodo_record", f"source {source_id}: identity kind")
            require(identity["doi"] == doi, f"source {source_id}: DOI")
            require(identity["record_url"] == f"https://zenodo.org/records/{doi.rsplit('.', 1)[1]}", f"source {source_id}: record URL")
            require(source["canonical_locator"] == f"https://doi.org/{doi}", f"source {source_id}: DOI locator")
            for key in ("repository_url", "commit", "tree", "implementation_freeze_commit", "implementation_freeze_tree", "source_registry_ref"):
                require(identity[key] is None, f"source {source_id}: {key} must be null")
            validate_https_url(identity["record_url"], f"source {source_id} record_url")
        else:
            require(source["publication_date"] is None, "Strongwiz: publication_date must be null")
            validate_iso_date(source["inspection_date"], "Strongwiz inspection_date")
            validate_iso_datetime(source["repository_commit_date"], "Strongwiz repository_commit_date")
            require(source["inspection_date"] == STRONGWIZ_INSPECTION_DATE, "Strongwiz: inspection date")
            require(source["repository_commit_date"] == STRONGWIZ_COMMIT_DATE, "Strongwiz: commit date")
            require(identity == {
                "kind": "git_repository",
                "doi": None,
                "record_url": None,
                "repository_url": "https://github.com/Grativy6/strongwiz",
                "commit": STRONGWIZ_HEAD,
                "tree": STRONGWIZ_HEAD_TREE,
                "implementation_freeze_commit": STRONGWIZ_FREEZE,
                "implementation_freeze_tree": STRONGWIZ_FREEZE_TREE,
                "source_registry_ref": STRONGWIZ_SOURCE_REGISTRY_REF,
            }, "Strongwiz: exact repository identities")
            require(
                source["canonical_locator"]
                == f"https://github.com/Grativy6/strongwiz/tree/{STRONGWIZ_HEAD}",
                "Strongwiz: commit locator",
            )
            validate_https_url(identity["repository_url"], "Strongwiz repository_url")

        artifacts = source["artifacts"]
        require(isinstance(artifacts, list) and artifacts, f"source {source_id}: artifacts")
        observed_artifact_keys: set[tuple[str, str]] = set()
        observed_sha256: set[str] = set()
        for index, artifact in enumerate(artifacts):
            require_exact_keys(artifact, artifact_keys, f"source {source_id} artifact {index}")
            artifact_key = (artifact["name"], artifact["variant"])
            require(artifact_key not in observed_artifact_keys, f"source {source_id}: duplicate artifact identity")
            observed_artifact_keys.add(artifact_key)
            require(isinstance(artifact["sha256"], str) and HEX64.fullmatch(artifact["sha256"]), f"source {source_id}: invalid SHA-256")
            observed_sha256.add(artifact["sha256"])
            require(artifact["md5"] is None or (isinstance(artifact["md5"], str) and HEX32.fullmatch(artifact["md5"])), f"source {source_id}: invalid MD5")
            require(artifact["bytes"] is None or (isinstance(artifact["bytes"], int) and artifact["bytes"] > 0), f"source {source_id}: invalid byte count")
        require(observed_sha256 == expected["artifact_sha256"], f"source {source_id}: artifact digest set")

        verification = source["verification"]
        require_exact_keys(verification, verification_keys, f"source {source_id} verification")
        require(verification["status"] == expected["verification"], f"source {source_id}: verification status")
        validate_https_url(verification["evidence_locator"], f"source {source_id} evidence_locator")
        require(isinstance(verification["notes"], list) and verification["notes"], f"source {source_id}: verification notes")
        require(len(verification["notes"]) == len(set(verification["notes"])), f"source {source_id}: duplicate verification note")

    brrrt = sources[SOURCE_ORDER.index("brrrt-v2.0")]
    require(
        any(
            artifact["sha256"] == "f9e699ad4a8541506ecc6678c3296bdf4fbe4dd249a0dd6759c7fd0d22837e0a"
            and artifact["status"] == "CURRENT_CANONICAL_FILE"
            for artifact in brrrt["artifacts"]
        ),
        "BRRRT: live canonical PDF binding",
    )

    strongwiz = sources[-1]
    require(
        {artifact["name"]: artifact["sha256"] for artifact in strongwiz["artifacts"]}
        == STRONGWIZ_ARTIFACTS,
        "Strongwiz: exact inspected artifact identity map",
    )
    require(strongwiz["verification"]["evidence_locator"] == STRONGWIZ_CI, "Strongwiz: CI locator")
    notes = "\n".join(strongwiz["verification"]["notes"])
    for phrase in (
        "449 tests",
        "51 tests",
        "PREPARED, NOT RUN, and NOT PREREGISTERED",
        "0.4.0.dev0",
        "0.2.0 / v0.2",
        "omit the repository-local calibration_003 harness",
    ):
        require(phrase in notes, f"Strongwiz: missing residual note {phrase!r}")
    require("retained declaratively but not runner-wired" in strongwiz["claim_ceiling"], "Strongwiz: EvidenceYieldGate ceiling")
    require("complete cost telemetry is not established" in strongwiz["claim_ceiling"], "Strongwiz: telemetry ceiling")

    validate_no_local_absolute_paths(document, "source lock")
    return source_ids


def validate_creature(document: Any, source_ids: Iterable[str]) -> None:
    require_exact_keys(
        document,
        [
            "schema",
            "fixture_kind",
            "status",
            "claim_ceiling",
            "creature",
            "run_boundary",
            "controller",
            "members",
            "thulia",
            "comparison",
            "source_refs",
            "residuals",
        ],
        "Creature fixture",
    )
    require(document["schema"] == "hearthline-plays.creature-manifest.v1", "Creature fixture: schema")
    require(document["fixture_kind"] == "WHOLLY_SYNTHETIC_STRUCTURE_ONLY", "Creature fixture: synthetic marker")
    require(document["status"] == "PREPARED_NOT_RUN", "Creature fixture: status")
    require("fabricated" in document["claim_ceiling"].lower(), "Creature fixture: claim ceiling")

    creature = document["creature"]
    require_exact_keys(
        creature,
        [
            "creature_id",
            "profile_version",
            "purpose",
            "branch",
            "anchor_commit",
            "anchor_tree",
            "source_lock_ref",
            "design_ref",
            "model_identity",
            "runtime_identity",
        ],
        "Creature identity",
    )
    require(creature["creature_id"].startswith("synthetic-creature-"), "Creature fixture: synthetic ID")
    require(creature["branch"] == TITLE_BRANCH, "Creature fixture: branch")
    require(creature["anchor_commit"] == ANCHOR_COMMIT, "Creature fixture: anchor commit")
    require(creature["anchor_tree"] == ANCHOR_TREE, "Creature fixture: anchor tree")
    require(creature["source_lock_ref"] == "research/sources.lock.json", "Creature fixture: source lock ref")
    require(creature["design_ref"] == "design/CREATURES.md", "Creature fixture: design ref")
    require(creature["model_identity"] == creature["runtime_identity"] == "UNBOUND", "Creature fixture: model/runtime must be unbound")

    boundary = document["run_boundary"]
    require_exact_keys(
        boundary,
        [
            "authorized_to_run",
            "kaggle_contacted",
            "arc_environment_contacted",
            "private_or_sealed_holdout_accessed",
            "submission_attempted",
            "environment_calls",
            "holdout_consumption",
            "official_surfaces",
        ],
        "Creature run boundary",
    )
    for key in (
        "authorized_to_run",
        "kaggle_contacted",
        "arc_environment_contacted",
        "private_or_sealed_holdout_accessed",
        "submission_attempted",
    ):
        require(boundary[key] is False, f"Creature fixture: {key} must be false")
    require(boundary["environment_calls"] == 0, "Creature fixture: environment calls must be zero")
    require(boundary["holdout_consumption"] == 0, "Creature fixture: holdout consumption must be zero")
    surface_keys = ["arc_framework", "arc_package", "arc_game", "evaluator", "operator_model", "scribe_model", "budget"]
    require_exact_keys(boundary["official_surfaces"], surface_keys, "Creature official surfaces")
    require(all(value == "UNBOUND" for value in boundary["official_surfaces"].values()), "Creature fixture: official surfaces must be unbound")

    controller = document["controller"]
    require_exact_keys(
        controller,
        [
            "external_operator_control_ref",
            "external_operator_control_authority",
            "controller_ref",
            "controller_authority",
            "broker_domain_writer_ref",
            "broker_domain_writer_authority",
            "authorized_broker_count",
            "ambiguous_effect_policy",
            "terminal_authority_source_ref",
            "terminal_adapter_ref",
            "terminal_adapter_authority",
            "heartbeat_semantics",
            "heartbeat_can_keep_codex_workspace_alive",
        ],
        "Creature controller",
    )
    require(controller["external_operator_control_ref"] == "UNBOUND", "Creature fixture: external operator control must be unbound")
    require(controller["external_operator_control_authority"] == "GRANT_AND_REVOKE_ONLY", "Creature fixture: external authority boundary")
    require(controller["controller_ref"].startswith("SYNTHETIC_CONTROLLER_"), "Creature fixture: synthetic controller")
    require(controller["controller_authority"] == "ADMIT_AND_SERIALIZE_ONLY", "Creature fixture: controller authority ceiling")
    require(controller["broker_domain_writer_ref"] == "UNBOUND", "Creature fixture: broker/domain writer must be unbound")
    require(controller["broker_domain_writer_authority"] == "EXECUTE_AND_RECORD_SEPARATELY_AUTHORIZED_EFFECTS_ONLY", "Creature fixture: broker/domain writer ceiling")
    require(controller["authorized_broker_count"] == 0, "Creature fixture: no effect executor is authorized")
    require(controller["ambiguous_effect_policy"] == "STOP_RECONCILE_DO_NOT_RETRY", "Creature fixture: ambiguous effect policy")
    require(controller["terminal_authority_source_ref"] == "UNBOUND", "Creature fixture: terminal authority source")
    require(controller["terminal_adapter_ref"] == "UNBOUND", "Creature fixture: terminal adapter")
    require(controller["terminal_adapter_authority"] == "VALIDATE_AND_PROJECT_ONLY", "Creature fixture: terminal adapter ceiling")
    require(controller["heartbeat_semantics"] == "STATUS_AND_RECEIPT_ONLY", "Creature fixture: heartbeat semantics")
    require(controller["heartbeat_can_keep_codex_workspace_alive"] is False, "Creature fixture: heartbeat cannot keep workspace alive")

    member_keys = [
        "spark_id",
        "role",
        "job",
        "profile_ref",
        "provider_ref",
        "grant_ref",
        "budget_ref",
        "ledger_ref",
        "static_ref",
        "home_ref",
        "committed_view_ref",
        "action_port",
        "authority_port",
        "writes_other_spark_static",
        "receives_only_receipt_bound_derivations",
        "paired_ledger_scribe_ref",
        "recursive_scribe",
    ]
    members = document["members"]
    require(isinstance(members, list) and len(members) >= 2, "Creature fixture: members")
    for index, member in enumerate(members):
        require_exact_keys(member, member_keys, f"Creature member {index}")
        require(member["spark_id"].startswith("synthetic-spark-"), f"Creature member {index}: synthetic ID")
        require(member["provider_ref"] == "UNBOUND", f"Creature member {index}: provider")
        for key in ("action_port", "authority_port", "writes_other_spark_static", "recursive_scribe"):
            require(member[key] is False, f"Creature member {index}: {key} must be false")
    for field in ("spark_id", "profile_ref", "grant_ref", "budget_ref", "ledger_ref", "static_ref", "home_ref", "committed_view_ref"):
        values = [member[field] for member in members]
        require(len(values) == len(set(values)), f"Creature fixture: members must have separate {field}")

    scribes = [member for member in members if member["job"] == "LEDGER_SCRIBE"]
    workers = [member for member in members if member["job"] == "WORK"]
    require(len(scribes) == 1 and len(workers) == 1, "Creature fixture: one Work Spark and one Ledger Scribe required")
    scribe = scribes[0]
    worker = workers[0]
    require(scribe["receives_only_receipt_bound_derivations"] is True, "Creature fixture: Ledger Scribe input boundary")
    require(scribe["paired_ledger_scribe_ref"] is None, "Creature fixture: Ledger Scribe must not recurse")
    require(worker["paired_ledger_scribe_ref"] == scribe["spark_id"], "Creature fixture: Work/Scribe pairing")

    thulia = document["thulia"]
    require_exact_keys(
        thulia,
        [
            "interface_ref",
            "perch_index_ref",
            "observes_ledger_refs",
            "governing",
            "action_port",
            "authority_port",
            "merges_ledgers",
            "approves_carry",
            "writes_receiving_static",
        ],
        "Thulia",
    )
    for key in ("governing", "action_port", "authority_port", "merges_ledgers", "approves_carry", "writes_receiving_static"):
        require(thulia[key] is False, f"Thulia: {key} must be false")
    require(set(thulia["observes_ledger_refs"]) == {member["ledger_ref"] for member in members}, "Thulia: partitioned member ledger refs")

    comparison = document["comparison"]
    require_exact_keys(comparison, ["declaration_only", "physically_isolated_required", "shared_payload_ledger", "campaign_index", "arms"], "Creature comparison")
    require(comparison["declaration_only"] is True, "Creature comparison: declaration only")
    require(comparison["physically_isolated_required"] is True, "Creature comparison: physical isolation requirement")
    require(comparison["shared_payload_ledger"] is False, "Creature comparison: no shared payload ledger")
    index = comparison["campaign_index"]
    require_exact_keys(index, ["index_ref", "location", "identity_only", "payload_ledger"], "Creature campaign index")
    require(index["location"] == "EXTERNAL_TO_ARMS", "Creature comparison: campaign index location")
    require(index["identity_only"] is True and index["payload_ledger"] is False, "Creature comparison: identity-only campaign index")
    arms = comparison["arms"]
    require(isinstance(arms, list) and len(arms) == 2, "Creature comparison: exactly two arms")
    arm_keys = ["arm_id", "kind", "lab_root_ref", "ledger_ref", "initial_state", "shares_payload_state"]
    for index_number, arm in enumerate(arms):
        require_exact_keys(arm, arm_keys, f"Creature arm {index_number}")
        require(arm["initial_state"] == "ABSENT_OR_EMPTY", f"Creature arm {index_number}: initial state")
        require(arm["shares_payload_state"] is False, f"Creature arm {index_number}: shared payload state")
    require({arm["kind"] for arm in arms} == {"NO_CREATURE_CONTROL", "CREATURE_CANDIDATE"}, "Creature comparison: arm kinds")
    require(len({arm["arm_id"] for arm in arms}) == 2, "Creature comparison: separate arm IDs")
    require(len({arm["lab_root_ref"] for arm in arms}) == 2, "Creature comparison: separate roots")
    require(len({arm["ledger_ref"] for arm in arms}) == 2, "Creature comparison: separate ledgers")

    require(document["source_refs"] == list(source_ids), "Creature fixture: source refs must match source lock")
    required_residuals = {
        "NO_ARC_OR_KAGGLE_CONTACT",
        "OFFICIAL_ARC_SURFACES_UNBOUND",
        "CALIBRATION_003_PREPARED_NOT_RUN_NOT_PREREGISTERED",
        "EVIDENCE_YIELD_GATE_DECLARATIVE_NOT_RUNNER_WIRED",
        "FULL_COST_TELEMETRY_REQUIREMENT_NOT_ESTABLISHED",
        "NO_MULTI_CREATURE_COORDINATOR",
        "STRONGWIZ_VERSION_METADATA_CONFLICT_UNRESOLVED",
        "STRONGWIZ_DISTRIBUTION_OMITS_CALIBRATION_003_HARNESS",
        "STRONGWIZ_SOURCE_REGISTRY_OMITS_NEW_RESEARCH_NO_BACKDATING",
        "OPERATOR_CONTROLLER_BROKER_AUTHORITY_SEPARATED",
        "TERMINAL_SOURCE_AND_ADAPTER_SEPARATED",
        "HEARTBEAT_CANNOT_KEEP_CODEX_WORKSPACE_ALIVE",
    }
    require(set(document["residuals"]) == required_residuals, "Creature fixture: exact residual set")
    validate_no_local_absolute_paths(document, "Creature fixture")


def validate_objective_window(document: Any) -> None:
    require_exact_keys(
        document,
        ["schema", "fixture_kind", "status", "claim_ceiling", "window", "objectives", "events", "objective_set"],
        "objective-window fixture",
    )
    require(document["schema"] == "hearthline-plays.objective-window.v1", "objective window: schema")
    require(document["fixture_kind"] == "WHOLLY_SYNTHETIC_STRUCTURE_ONLY", "objective window: synthetic marker")
    require(document["status"] == "PREPARED_NOT_RUN_STATIC_VALIDATED", "objective window: status")
    require("static" in document["claim_ceiling"].lower() or "offline verifier" in document["claim_ceiling"].lower(), "objective window: bounded claim")

    window = document["window"]
    window_keys = [
        "window_id",
        "controller_ref",
        "external_operator_control_ref",
        "effect_admission_ref",
        "effect_executor_ref",
        "terminal_authority_source_ref",
        "accepts_new_objectives_while_another_is_suspended",
        "completion_order_may_differ_from_open_order",
        "heartbeat_semantics",
        "heartbeat_is_keepalive",
        "heartbeat_is_scheduler",
    ]
    require_exact_keys(window, window_keys, "objective window")
    require(window["window_id"].startswith("synthetic-objective-window-"), "objective window: synthetic ID")
    require(window["controller_ref"] == window["effect_admission_ref"], "objective window: controller owns effect admission")
    require(window["external_operator_control_ref"] == "UNBOUND", "objective window: external grant source is unbound")
    require(window["effect_executor_ref"] == "UNBOUND", "objective window: effect executor is unbound")
    require(window["terminal_authority_source_ref"] == "UNBOUND", "objective window: terminal authority source is unbound")
    require(window["accepts_new_objectives_while_another_is_suspended"] is True, "objective window: open intake")
    require(window["completion_order_may_differ_from_open_order"] is True, "objective window: out-of-order completion")
    require(window["heartbeat_semantics"] == "INTERRUPT_AND_CHECKPOINT_RECEIPT_ONLY", "objective window: heartbeat semantics")
    require(window["heartbeat_is_keepalive"] is False, "objective window: heartbeat is not keepalive")
    require(window["heartbeat_is_scheduler"] is False, "objective window: heartbeat is not scheduler")

    objective_keys = [
        "objective_id",
        "spark_or_creature_ref",
        "scope_ref",
        "grant_ref",
        "budget_ref",
        "ledger_ref",
        "heartbeat_ref",
        "homecoming_ref",
        "evaluation_rule_ref",
    ]
    objectives = document["objectives"]
    expected_ids = ["synthetic-objective-a", "synthetic-objective-b", "synthetic-objective-c"]
    require(isinstance(objectives, list) and len(objectives) == 3, "objective window: three objectives")
    require([objective.get("objective_id") for objective in objectives] == expected_ids, "objective window: exact A/B/C IDs")
    objective_by_id: dict[str, dict[str, Any]] = {}
    for index, objective in enumerate(objectives):
        require_exact_keys(objective, objective_keys, f"objective {index}")
        objective_by_id[objective["objective_id"]] = objective
    for field in objective_keys:
        values = [objective[field] for objective in objectives]
        require(len(values) == len(set(values)), f"objective window: separate {field}")

    event_keys = [
        "sequence",
        "event",
        "objective_id",
        "scope_ref",
        "grant_ref",
        "budget_ref",
        "ledger_ref",
        "heartbeat_ref",
        "homecoming_ref",
        "evaluation_rule_ref",
        "controller_ref",
        "lifecycle_receipt_ref",
        "checkpoint_receipt_ref",
        "homecoming_custody_state",
        "objective_disposition",
        "external_effect_receipt_ref",
    ]
    expected_lifecycle = [
        (1, "OPEN_OBJECTIVE", "synthetic-objective-a"),
        (2, "SUSPEND_OBJECTIVE", "synthetic-objective-a"),
        (3, "OPEN_OBJECTIVE", "synthetic-objective-b"),
        (4, "OPEN_OBJECTIVE", "synthetic-objective-c"),
        (5, "RETURN_OBJECTIVE", "synthetic-objective-c"),
        (6, "RETURN_OBJECTIVE", "synthetic-objective-b"),
        (7, "RESUME_OBJECTIVE", "synthetic-objective-a"),
        (8, "RETURN_OBJECTIVE", "synthetic-objective-a"),
        (9, "CLOSE_AGGREGATE_RESPONSE", None),
    ]
    events = document["events"]
    require(isinstance(events, list) and len(events) == 9, "objective window: nine-event lifecycle")
    require([(event.get("sequence"), event.get("event"), event.get("objective_id")) for event in events] == expected_lifecycle, "objective window: exact A/B/C lifecycle")

    states = {objective_id: "ABSENT" for objective_id in expected_ids}
    return_order: list[str] = []
    lifecycle_receipts: list[str] = []
    checkpoint_receipts: list[str] = []
    resource_fields = [
        "scope_ref",
        "grant_ref",
        "budget_ref",
        "ledger_ref",
        "heartbeat_ref",
        "homecoming_ref",
        "evaluation_rule_ref",
    ]
    for index, event in enumerate(events):
        require_exact_keys(event, event_keys, f"objective event {index}")
        require(event["controller_ref"] == window["controller_ref"], f"objective event {index}: controller")
        require(isinstance(event["lifecycle_receipt_ref"], str), f"objective event {index}: lifecycle receipt")
        lifecycle_receipts.append(event["lifecycle_receipt_ref"])
        require(event["external_effect_receipt_ref"] is None, f"objective event {index}: external effects must remain absent")
        objective_id = event["objective_id"]
        action = event["event"]
        if objective_id is None:
            require(action == "CLOSE_AGGREGATE_RESPONSE", "objective window: only aggregate close is objective-free")
            require(all(event[field] is None for field in resource_fields), "objective window: aggregate close carries no objective resources")
            require(event["checkpoint_receipt_ref"] is None, "objective window: aggregate close checkpoint")
            require(event["homecoming_custody_state"] is None, "objective window: close cannot assign Homecoming custody")
            require(event["objective_disposition"] is None, "objective window: close cannot assign task status")
            require(all(state == "RETURNED" for state in states.values()), "objective window: close requires explicit returns")
            continue

        require(objective_id in objective_by_id, f"objective event {index}: unknown objective")
        objective = objective_by_id[objective_id]
        for field in resource_fields:
            require(event[field] == objective[field], f"objective event {index}: {field} scope bleed")

        if action == "OPEN_OBJECTIVE":
            require(states[objective_id] == "ABSENT", f"objective {objective_id}: invalid open")
            states[objective_id] = "ACTIVE"
            require(event["homecoming_custody_state"] == "HOMECOMING:NOT_STARTED", f"objective event {index}: open custody")
            require(event["objective_disposition"] == "OBJECTIVE:ACTIVE", f"objective event {index}: open disposition")
        elif action == "SUSPEND_OBJECTIVE":
            require(states[objective_id] == "ACTIVE", f"objective {objective_id}: invalid suspend")
            states[objective_id] = "SUSPENDED"
            require(event["homecoming_custody_state"] == "HOMECOMING:NOT_STARTED", f"objective event {index}: suspension custody")
            require(event["objective_disposition"] == "OBJECTIVE:SUSPENDED", f"objective event {index}: suspension disposition")
        elif action == "RESUME_OBJECTIVE":
            require(states[objective_id] == "SUSPENDED", f"objective {objective_id}: invalid resume")
            states[objective_id] = "ACTIVE"
            require(event["homecoming_custody_state"] == "HOMECOMING:NOT_STARTED", f"objective event {index}: resume custody")
            require(event["objective_disposition"] == "OBJECTIVE:ACTIVE", f"objective event {index}: resume disposition")
        elif action == "RETURN_OBJECTIVE":
            require(states[objective_id] == "ACTIVE", f"objective {objective_id}: invalid return")
            states[objective_id] = "RETURNED"
            return_order.append(objective_id)
            require(event["homecoming_custody_state"] == "HOMECOMING:RECONCILED", f"objective event {index}: return custody")
            require(
                event["objective_disposition"]
                == f"{objective['evaluation_rule_ref']}:SATISFIED",
                f"objective event {index}: result must remain rule-owned",
            )
        else:
            raise VerificationError(f"objective event {index}: unexpected action")

        if action in {"SUSPEND_OBJECTIVE", "RESUME_OBJECTIVE"}:
            require(isinstance(event["checkpoint_receipt_ref"], str), f"objective event {index}: checkpoint receipt required")
            checkpoint_receipts.append(event["checkpoint_receipt_ref"])
        else:
            require(event["checkpoint_receipt_ref"] is None, f"objective event {index}: unexpected checkpoint receipt")
        if event["sequence"] in (3, 4):
            require(states["synthetic-objective-a"] == "SUSPENDED", "objective window: B/C open only while A is honestly suspended")

    require(len(lifecycle_receipts) == len(set(lifecycle_receipts)) == 9, "objective window: lifecycle receipts must be unique")
    require(len(checkpoint_receipts) == len(set(checkpoint_receipts)) == 2, "objective window: checkpoint receipts must be unique")

    objective_set = document["objective_set"]
    objective_set_keys = [
        "snapshot_ref",
        "expected_objective_ids",
        "return_order",
        "final_states",
        "all_objectives_explicitly_disposed",
        "aggregate_response_ref",
        "aggregate_response_closed",
        "close_basis",
        "external_effect_count",
    ]
    require_exact_keys(objective_set, objective_set_keys, "objective set")
    require(isinstance(objective_set["snapshot_ref"], str), "objective set: snapshot ref")
    require(objective_set["expected_objective_ids"] == expected_ids, "objective set: expected IDs")
    require(objective_set["return_order"] == return_order == [expected_ids[2], expected_ids[1], expected_ids[0]], "objective set: out-of-order return")
    final_states = objective_set["final_states"]
    require(isinstance(final_states, list) and len(final_states) == 3, "objective set: final states")
    for index, state in enumerate(final_states):
        require_exact_keys(
            state,
            ["objective_id", "homecoming_custody_state", "objective_disposition"],
            f"objective final state {index}",
        )
    require(
        {
            item["objective_id"]: (
                item["homecoming_custody_state"],
                item["objective_disposition"],
            )
            for item in final_states
        }
        == {
            objective_id: (
                "HOMECOMING:RECONCILED",
                f"{objective_by_id[objective_id]['evaluation_rule_ref']}:SATISFIED",
            )
            for objective_id in expected_ids
        },
        "objective set: custody and rule-owned disposition must remain separate",
    )
    require(objective_set["all_objectives_explicitly_disposed"] is True, "objective set: explicit disposition")
    require(objective_set["aggregate_response_closed"] is True, "objective set: aggregate close")
    require(objective_set["close_basis"] == "EXPLICIT_TYPED_CUSTODY_AND_OBJECTIVE_DISPOSITIONS", "objective set: close basis")
    require(objective_set["external_effect_count"] == 0, "objective set: no external effects")
    validate_no_local_absolute_paths(document, "objective-window fixture")


def _unique_string_ids(value: Any, label: str) -> list[str]:
    require(isinstance(value, list), f"{label}: expected array")
    require(all(isinstance(item, str) and item for item in value), f"{label}: non-empty string IDs")
    require(len(value) == len(set(value)), f"{label}: IDs must be unique")
    return list(value)


def _overtake_counts(value: Any, ready_ids: list[str], label: str) -> dict[str, int]:
    require(isinstance(value, list), f"{label}: expected array")
    result: dict[str, int] = {}
    for index, item in enumerate(value):
        require_exact_keys(item, ["queue_item_id", "count"], f"{label} {index}")
        queue_item_id = item["queue_item_id"]
        count = item["count"]
        require(isinstance(queue_item_id, str) and queue_item_id, f"{label} {index}: queue item ID")
        require(queue_item_id not in result, f"{label}: duplicate queue item ID")
        require(type(count) is int and count >= 0, f"{label} {index}: nonnegative integer count")
        result[queue_item_id] = count
    require(list(result) == ready_ids, f"{label}: must follow the exact ready arrival order")
    return result


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_surface_key(value: str) -> str:
    """Return the portable collision key used for authority-bearing refs."""
    return unicodedata.normalize("NFKC", value).casefold()


def _canonical_surface_keys(values: set[str]) -> set[str]:
    return {_canonical_surface_key(value) for value in values}


TRUSTED_PRIORITY_LEDGER_HEAD_KEYS = [
    "register_state",
    "ledger_length",
    "head_ref",
    "head_sha256",
]


def _require_trusted_current_priority_ledger_head(
    existing_receipts: list[dict[str, Any]],
    priority_genesis_head: dict[str, Any],
    trusted_current_priority_ledger_head: Any,
    label: str,
) -> None:
    """Bind a caller-supplied register to an independently trusted head."""
    require_exact_keys(
        trusted_current_priority_ledger_head,
        TRUSTED_PRIORITY_LEDGER_HEAD_KEYS,
        f"{label} trusted current priority-ledger head",
    )
    require(
        type(trusted_current_priority_ledger_head["ledger_length"]) is int
        and trusted_current_priority_ledger_head["ledger_length"] >= 0,
        f"{label}: trusted current priority-ledger length",
    )
    require(
        isinstance(trusted_current_priority_ledger_head["head_ref"], str)
        and trusted_current_priority_ledger_head["head_ref"],
        f"{label}: trusted current priority-ledger head ref",
    )
    require(
        isinstance(trusted_current_priority_ledger_head["head_sha256"], str)
        and HEX64.fullmatch(trusted_current_priority_ledger_head["head_sha256"])
        is not None,
        f"{label}: trusted current priority-ledger head digest",
    )
    if existing_receipts:
        current = existing_receipts[-1]
        require(
            trusted_current_priority_ledger_head["register_state"]
            == "DURABLE_PRIORITY_RECEIPT_HEAD"
            and trusted_current_priority_ledger_head["ledger_length"]
            == len(existing_receipts)
            and trusted_current_priority_ledger_head["head_ref"]
            == current["priority_receipt_ref"]
            and trusted_current_priority_ledger_head["head_sha256"]
            == _canonical_json_sha256(current),
            f"{label}: supplied register does not match authenticated current head",
        )
        return
    require(
        trusted_current_priority_ledger_head["register_state"]
        == "EMPTY_PRIORITY_LEDGER_AT_GENESIS"
        and trusted_current_priority_ledger_head["ledger_length"] == 0
        and trusted_current_priority_ledger_head["head_ref"]
        == priority_genesis_head["head_ref"]
        and trusted_current_priority_ledger_head["head_sha256"]
        == priority_genesis_head["head_sha256"],
        f"{label}: empty register must match authenticated genesis head",
    )


MORROW_POLICY_REF = "STABLE_EFFECTIVE_PRIORITY_THEN_APPROVED_COST_THEN_ARRIVAL_V2"
MAXIMUM_OVERTAKES = 1_000_000
MAXIMUM_CONTROLLER_APPROVED_PROCESSING_COST = 1_000_000
MAXIMUM_MORROW_READY_ITEMS = 256
MAXIMUM_OPAQUE_TOKEN_CHARACTERS = 256
MAXIMUM_MORROW_OUTPUT_BYTES = 1_000_000
MAXIMUM_PRIORITY_REVISIONS = 64
SAFE_OPAQUE_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]+$")


def _is_safe_opaque_token(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= MAXIMUM_OPAQUE_TOKEN_CHARACTERS
        and SAFE_OPAQUE_TOKEN.fullmatch(value) is not None
    )


PRIORITY_RANKS = {
    "P0_URGENT": 0,
    "P1_EXPEDITE": 1,
    "P2_ROUTINE": 2,
    "P3_BACKGROUND": 3,
}
PRIORITY_RECEIPT_KEYS = [
    "priority_receipt_ref",
    "idempotency_key",
    "ledger_ordinal",
    "receipt_kind",
    "queue_id",
    "profile_ref",
    "profile_epoch",
    "policy_ref",
    "task_ref",
    "tether_ref",
    "task_tether_core_sha256",
    "dispatch_ref",
    "priority_authorization_ref",
    "revision_ordinal",
    "supersedes_priority_receipt_ref",
    "assigned_by_ref",
    "recorded_by_controller_ref",
    "assignment_basis_ref",
    "priority_class",
    "priority_rank",
    "priority_ceiling_class",
    "priority_ceiling_rank",
    "maximum_priority_revisions",
    "scheduling_mark_binding",
    "observed_priority_ledger_head_ref",
    "observed_priority_ledger_head_sha256",
    "observed_snapshot_ordinal",
    "observed_snapshot_ref",
    "observed_snapshot_projection_sha256",
    "grant_ref",
    "scope_ref",
    "deadline_ref",
    "budget_ref",
    "grant_renewed",
    "scope_expanded",
    "deadline_extended",
    "budget_increased",
    "authority_mutated",
    "subject_state",
    "terminal_admission_ref",
    "external_effect_receipt_ref",
]
PRIORITY_AUTHORIZATION_KEYS = [
    "priority_authorization_ref",
    "queue_id",
    "profile_ref",
    "profile_epoch",
    "policy_ref",
    "task_ref",
    "tether_ref",
    "task_tether_core_sha256",
    "dispatch_ref",
    "authorized_assigner_ref",
    "recorded_by_controller_ref",
    "priority_ceiling_class",
    "priority_ceiling_rank",
    "maximum_priority_revisions",
    "grant_ref",
    "scope_ref",
    "deadline_ref",
    "budget_ref",
    "priority_is_sequencing_only",
    "external_effect_receipt_ref",
]
PRIORITY_APPEND_HOLD_KEYS = [
    "priority_append_hold_ref",
    "idempotency_key",
    "controller_ref",
    "queue_id",
    "profile_ref",
    "profile_epoch",
    "policy_ref",
    "priority_authorization_ref",
    "task_ref",
    "tether_ref",
    "task_tether_core_sha256",
    "dispatch_ref",
    "attempted_priority_receipt_ref",
    "attempted_priority_receipt_sha256",
    "attempted_receipt_kind",
    "attempted_revision_ordinal",
    "attempted_supersedes_priority_receipt_ref",
    "observed_priority_ledger_head_ref",
    "observed_priority_ledger_head_sha256",
    "observed_snapshot_ordinal",
    "observed_snapshot_ref",
    "observed_snapshot_projection_sha256",
    "persistence_outcome",
    "hold_state",
    "reconciliation_handle",
    "reconciliation_receipt_ref",
    "can_enter_ready",
    "external_effect_receipt_ref",
]
PRIORITY_APPEND_RECONCILIATION_KEYS = [
    "priority_append_reconciliation_receipt_ref",
    "priority_append_hold_ref",
    "controller_ref",
    "queue_id",
    "profile_ref",
    "profile_epoch",
    "policy_ref",
    "task_ref",
    "tether_ref",
    "task_tether_core_sha256",
    "dispatch_ref",
    "reconciliation_handle",
    "reconciled_persistence_outcome",
    "confirmed_priority_receipt_ref",
    "confirmed_priority_receipt_sha256",
    "revalidation_inputs_ref",
    "revalidation_result",
    "status",
    "can_enter_ready",
    "external_effect_receipt_ref",
]
RETRY_ROTATION_RELEASE_KEYS = [
    "retry_rotation_release_receipt_ref",
    "controller_ref",
    "queue_id",
    "profile_ref",
    "profile_epoch",
    "service_epoch",
    "source_service_disposition_receipt_ref",
    "source_reopen_handle",
    "queue_item_id",
    "release_mode",
    "intervening_service_record_ref",
    "intervening_queue_item_id",
    "intervening_service_ordinal",
    "pre_reopen_snapshot_id",
    "pre_reopen_snapshot_projection_sha256",
    "derived_other_ready_count",
    "preserved_overtake_count",
    "priority_mutated",
    "authority_mutated",
    "custody_mutated",
    "result_mutated",
    "deadline_mutated",
    "budget_mutated",
    "external_effect_receipt_ref",
]
SERVICE_RECONCILIATION_KEYS = [
    "service_reconciliation_receipt_ref",
    "controller_ref",
    "queue_id",
    "profile_ref",
    "profile_epoch",
    "service_epoch",
    "service_disposition_receipt_ref",
    "queue_item_id",
    "reopen_handle",
    "observed_outcome",
    "reconciled_outcome",
    "reconciliation_evidence_ref",
    "retry_permitted",
    "priority_mutated",
    "authority_mutated",
    "custody_mutated",
    "result_mutated",
    "deadline_mutated",
    "budget_mutated",
    "external_effect_receipt_ref",
]


def _require_priority_authorization_binding(
    receipt: dict[str, Any],
    authorization: Any,
    label: str,
) -> None:
    require_exact_keys(authorization, PRIORITY_AUTHORIZATION_KEYS, f"{label} authorization")
    field_pairs = (
        ("priority_authorization_ref", "priority_authorization_ref"),
        ("queue_id", "queue_id"),
        ("profile_ref", "profile_ref"),
        ("profile_epoch", "profile_epoch"),
        ("policy_ref", "policy_ref"),
        ("task_ref", "task_ref"),
        ("tether_ref", "tether_ref"),
        ("task_tether_core_sha256", "task_tether_core_sha256"),
        ("dispatch_ref", "dispatch_ref"),
        ("assigned_by_ref", "authorized_assigner_ref"),
        ("recorded_by_controller_ref", "recorded_by_controller_ref"),
        ("priority_ceiling_class", "priority_ceiling_class"),
        ("priority_ceiling_rank", "priority_ceiling_rank"),
        ("maximum_priority_revisions", "maximum_priority_revisions"),
        ("grant_ref", "grant_ref"),
        ("scope_ref", "scope_ref"),
        ("deadline_ref", "deadline_ref"),
        ("budget_ref", "budget_ref"),
    )
    for receipt_field, authorization_field in field_pairs:
        require(
            _canonical_json_bytes(receipt[receipt_field])
            == _canonical_json_bytes(authorization[authorization_field]),
            f"{label}: frozen authorization binding for {receipt_field}",
        )
    require(authorization["priority_is_sequencing_only"] is True, f"{label}: sequencing-only authorization")
    require(authorization["external_effect_receipt_ref"] is None, f"{label}: authorization cannot execute an effect")
    require(
        receipt["priority_rank"] >= authorization["priority_ceiling_rank"],
        f"{label}: priority exceeds authorization ceiling",
    )


def _validate_priority_receipt_ledger(
    receipts: Any,
    controller_ref: str,
    priority_assigner_ref: str,
    queue_id: str | None = None,
    profile_ref: str | None = None,
    profile_epoch: int | None = None,
    policy_ref: str | None = None,
    dispatch_basis_ref: str | None = None,
    revision_basis_ref: str | None = None,
    priority_genesis_head_ref: str | None = None,
    priority_genesis_head_sha256: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Validate the controller-owned append-only dispatch-priority register."""
    require(isinstance(receipts, list) and receipts, "priority register: nonempty receipt array")
    chains: dict[str, list[dict[str, Any]]] = {}
    receipt_refs: set[str] = set()
    idempotency_keys: set[str] = set()
    mark_bindings: set[str] = set()
    task_to_tether: dict[str, str] = {}
    for index, receipt in enumerate(receipts, start=1):
        require_exact_keys(receipt, PRIORITY_RECEIPT_KEYS, f"priority receipt {index}")
        require(
            type(receipt["ledger_ordinal"]) is int and receipt["ledger_ordinal"] == index,
            f"priority receipt {index}: append-only ledger ordinal",
        )
        for field, seen in (
            ("priority_receipt_ref", receipt_refs),
            ("idempotency_key", idempotency_keys),
            ("scheduling_mark_binding", mark_bindings),
        ):
            value = receipt[field]
            require(isinstance(value, str) and value and value not in seen, f"priority receipt {index}: unique {field}")
            seen.add(value)
        for field in (
            "queue_id",
            "profile_ref",
            "policy_ref",
            "task_ref",
            "tether_ref",
            "task_tether_core_sha256",
            "dispatch_ref",
            "priority_authorization_ref",
            "assigned_by_ref",
            "recorded_by_controller_ref",
            "assignment_basis_ref",
            "grant_ref",
            "scope_ref",
            "deadline_ref",
            "budget_ref",
        ):
            require(isinstance(receipt[field], str) and receipt[field], f"priority receipt {index}: {field}")
        require(receipt["assigned_by_ref"] == priority_assigner_ref, f"priority receipt {index}: Hearthline assignment source")
        require(receipt["recorded_by_controller_ref"] == controller_ref, f"priority receipt {index}: controller-owned persistence")
        if queue_id is not None:
            require(receipt["queue_id"] == queue_id, f"priority receipt {index}: queue binding")
        if profile_ref is not None:
            require(receipt["profile_ref"] == profile_ref, f"priority receipt {index}: profile binding")
        if profile_epoch is not None:
            require(receipt["profile_epoch"] == profile_epoch, f"priority receipt {index}: profile epoch binding")
        if policy_ref is not None:
            require(receipt["policy_ref"] == policy_ref, f"priority receipt {index}: policy binding")
        require(type(receipt["profile_epoch"]) is int and receipt["profile_epoch"] >= 1, f"priority receipt {index}: profile epoch")
        require(
            HEX64.fullmatch(receipt["task_tether_core_sha256"]) is not None,
            f"priority receipt {index}: TETHER core digest",
        )
        require(
            isinstance(receipt["observed_priority_ledger_head_ref"], str)
            and receipt["observed_priority_ledger_head_ref"],
            f"priority receipt {index}: observed priority-ledger head",
        )
        require(
            isinstance(receipt["observed_priority_ledger_head_sha256"], str)
            and HEX64.fullmatch(receipt["observed_priority_ledger_head_sha256"]) is not None,
            f"priority receipt {index}: observed priority-ledger head digest",
        )
        if index == 1:
            expected_head_ref = priority_genesis_head_ref or receipt["observed_priority_ledger_head_ref"]
            expected_head_sha256 = (
                priority_genesis_head_sha256
                or receipt["observed_priority_ledger_head_sha256"]
            )
        else:
            prior_global = receipts[index - 2]
            expected_head_ref = prior_global["priority_receipt_ref"]
            expected_head_sha256 = _canonical_json_sha256(prior_global)
        require(
            receipt["observed_priority_ledger_head_ref"] == expected_head_ref
            and receipt["observed_priority_ledger_head_sha256"] == expected_head_sha256,
            f"priority receipt {index}: stale or forked global priority-ledger head",
        )
        priority_class = receipt["priority_class"]
        require(priority_class in PRIORITY_RANKS, f"priority receipt {index}: priority class")
        require(
            type(receipt["priority_rank"]) is int
            and receipt["priority_rank"] == PRIORITY_RANKS[priority_class],
            f"priority receipt {index}: priority class/rank binding",
        )
        ceiling_class = receipt["priority_ceiling_class"]
        require(ceiling_class in PRIORITY_RANKS, f"priority receipt {index}: priority ceiling class")
        require(
            type(receipt["priority_ceiling_rank"]) is int
            and receipt["priority_ceiling_rank"] == PRIORITY_RANKS[ceiling_class],
            f"priority receipt {index}: priority ceiling binding",
        )
        require(receipt["priority_rank"] >= receipt["priority_ceiling_rank"], f"priority receipt {index}: priority exceeds dispatch ceiling")
        require(
            type(receipt["maximum_priority_revisions"]) is int
            and 0 <= receipt["maximum_priority_revisions"] <= MAXIMUM_PRIORITY_REVISIONS,
            f"priority receipt {index}: revision budget",
        )
        require(
            type(receipt["observed_snapshot_ordinal"]) is int
            and receipt["observed_snapshot_ordinal"] >= 0,
            f"priority receipt {index}: observed snapshot ordinal",
        )
        for field in (
            "grant_renewed",
            "scope_expanded",
            "deadline_extended",
            "budget_increased",
            "authority_mutated",
        ):
            require(receipt[field] is False, f"priority receipt {index}: {field} must remain false")
        require(receipt["external_effect_receipt_ref"] is None, f"priority receipt {index}: external effect forbidden")
        require(receipt["terminal_admission_ref"] is None, f"priority receipt {index}: terminal subject cannot be revised")

        tether_ref = receipt["tether_ref"]
        task_ref = receipt["task_ref"]
        prior_tether = task_to_tether.setdefault(task_ref, tether_ref)
        require(prior_tether == tether_ref, f"priority receipt {index}: task cannot change tether")
        chain = chains.setdefault(tether_ref, [])
        if receipt["receipt_kind"] == "DISPATCH_PRIORITY_MARK":
            require(not chain, f"priority receipt {index}: duplicate dispatch root")
            require(receipt["revision_ordinal"] == 0, f"priority receipt {index}: dispatch revision ordinal")
            require(receipt["supersedes_priority_receipt_ref"] is None, f"priority receipt {index}: dispatch cannot supersede")
            require(
                receipt["subject_state"] == "TASK_COMMISSIONED_DISPATCH_PENDING",
                f"priority receipt {index}: dispatch priority must be bound before release",
            )
            require(
                isinstance(receipt["observed_snapshot_ref"], str)
                and receipt["observed_snapshot_ref"],
                f"priority receipt {index}: dispatch observed snapshot head",
            )
            require(
                isinstance(receipt["observed_snapshot_projection_sha256"], str)
                and HEX64.fullmatch(receipt["observed_snapshot_projection_sha256"]) is not None,
                f"priority receipt {index}: dispatch observed snapshot digest",
            )
            if dispatch_basis_ref is not None:
                require(receipt["assignment_basis_ref"] == dispatch_basis_ref, f"priority receipt {index}: dispatch assignment basis")
        elif receipt["receipt_kind"] == "PRIORITY_REVISION":
            require(chain, f"priority receipt {index}: revision missing dispatch root")
            require(
                receipt["subject_state"] == "TASK_OUT_OR_RETURN_PENDING_NOT_ADMITTED",
                f"priority receipt {index}: revision subject must remain unadmitted",
            )
            prior = chain[-1]
            require(task_ref == prior["task_ref"], f"priority receipt {index}: revision task drift")
            require(receipt["revision_ordinal"] == prior["revision_ordinal"] + 1, f"priority receipt {index}: revision sequence")
            require(
                receipt["supersedes_priority_receipt_ref"] == prior["priority_receipt_ref"],
                f"priority receipt {index}: stale, replayed, or forked predecessor",
            )
            require(
                isinstance(receipt["observed_snapshot_ref"], str)
                and receipt["observed_snapshot_ref"],
                f"priority receipt {index}: observed snapshot identity",
            )
            require(
                isinstance(receipt["observed_snapshot_projection_sha256"], str)
                and HEX64.fullmatch(receipt["observed_snapshot_projection_sha256"]) is not None,
                f"priority receipt {index}: observed snapshot digest",
            )
            for field in ("grant_ref", "scope_ref", "deadline_ref", "budget_ref"):
                require(receipt[field] == chain[0][field], f"priority receipt {index}: revision mutated {field}")
            for field in (
                "queue_id",
                "profile_ref",
                "profile_epoch",
                "policy_ref",
                "dispatch_ref",
                "task_tether_core_sha256",
                "priority_authorization_ref",
                "priority_ceiling_class",
                "priority_ceiling_rank",
                "maximum_priority_revisions",
            ):
                require(receipt[field] == chain[0][field], f"priority receipt {index}: revision mutated {field}")
            require(
                receipt["revision_ordinal"] <= chain[0]["maximum_priority_revisions"],
                f"priority receipt {index}: revision budget exhausted",
            )
            require(
                (receipt["priority_class"], receipt["priority_rank"])
                != (prior["priority_class"], prior["priority_rank"]),
                f"priority receipt {index}: new no-op revision is forbidden",
            )
            if revision_basis_ref is not None:
                require(receipt["assignment_basis_ref"] == revision_basis_ref, f"priority receipt {index}: revision assignment basis")
        else:
            require(False, f"priority receipt {index}: receipt kind")
        require(
            type(receipt["revision_ordinal"]) is int and receipt["revision_ordinal"] >= 0,
            f"priority receipt {index}: revision ordinal",
        )
        chain.append(receipt)
    return chains


def append_dispatch_priority_mark(
    existing_receipts: list[dict[str, Any]],
    mark: dict[str, Any],
    trusted_controller_context: dict[str, Any] | None,
    trusted_current_priority_ledger_head: dict[str, Any] | None,
    observed_snapshot_head: dict[str, Any] | None,
    controller_lifecycle_evidence: dict[str, Any] | None,
    priority_authorization: dict[str, Any] | None,
    priority_genesis_head: dict[str, Any] | None,
    dispatch_assignment_basis_ref: str,
    revision_assignment_basis_ref: str,
) -> list[dict[str, Any]]:
    """Pure confirmed-append model for a required pre-dispatch root mark.

    The supplied register is first bound to an independently trusted current
    head. An exact accepted retry then resolves before candidate lifecycle or
    snapshot CAS checks. Changed-key conflicts and UNKNOWN persistence outcomes
    reject without mutation; a real controller must reconcile durable state
    before retrying.
    """
    require(isinstance(existing_receipts, list), "dispatch priority: existing register")
    candidate_keys = [field for field in PRIORITY_RECEIPT_KEYS if field != "ledger_ordinal"]
    require_exact_keys(mark, candidate_keys, "dispatch priority candidate")
    require(mark["receipt_kind"] == "DISPATCH_PRIORITY_MARK", "dispatch priority: root receipt kind")
    require(
        type(mark["revision_ordinal"]) is int and mark["revision_ordinal"] == 0,
        "dispatch priority: root revision ordinal",
    )
    require(mark["supersedes_priority_receipt_ref"] is None, "dispatch priority: root cannot supersede")
    require(mark["assignment_basis_ref"] == dispatch_assignment_basis_ref, "dispatch priority: assignment basis")
    require(mark["subject_state"] == "TASK_COMMISSIONED_DISPATCH_PENDING", "dispatch priority: receipt lifecycle claim")
    require_exact_keys(
        trusted_controller_context,
        [
            "controller_ref",
            "priority_assigner_ref",
            "queue_id",
            "profile_ref",
            "profile_epoch",
            "policy_ref",
        ],
        "dispatch priority trusted controller context",
    )
    for receipt_field, context_field in (
        ("recorded_by_controller_ref", "controller_ref"),
        ("assigned_by_ref", "priority_assigner_ref"),
        ("queue_id", "queue_id"),
        ("profile_ref", "profile_ref"),
        ("profile_epoch", "profile_epoch"),
        ("policy_ref", "policy_ref"),
    ):
        require(
            _canonical_json_bytes(mark[receipt_field])
            == _canonical_json_bytes(trusted_controller_context[context_field]),
            f"dispatch priority: trusted {receipt_field}",
        )
    require_exact_keys(
        priority_genesis_head,
        ["head_ref", "head_sha256"],
        "dispatch priority genesis head",
    )
    if existing_receipts:
        _validate_priority_receipt_ledger(
            existing_receipts,
            trusted_controller_context["controller_ref"],
            trusted_controller_context["priority_assigner_ref"],
            queue_id=trusted_controller_context["queue_id"],
            profile_ref=trusted_controller_context["profile_ref"],
            profile_epoch=trusted_controller_context["profile_epoch"],
            policy_ref=trusted_controller_context["policy_ref"],
            dispatch_basis_ref=dispatch_assignment_basis_ref,
            revision_basis_ref=revision_assignment_basis_ref,
            priority_genesis_head_ref=priority_genesis_head["head_ref"],
            priority_genesis_head_sha256=priority_genesis_head["head_sha256"],
        )
    _require_trusted_current_priority_ledger_head(
        existing_receipts,
        priority_genesis_head,
        trusted_current_priority_ledger_head,
        "dispatch priority",
    )
    by_key = {receipt.get("idempotency_key"): receipt for receipt in existing_receipts}
    prior_retry = by_key.get(mark["idempotency_key"])
    if prior_retry is not None:
        prior_without_ordinal = {
            field: value for field, value in prior_retry.items()
            if field != "ledger_ordinal"
        }
        require(
            _canonical_json_bytes(prior_without_ordinal) == _canonical_json_bytes(mark),
            "dispatch priority: idempotency key binding conflict",
        )
        return [dict(receipt) for receipt in existing_receipts]

    require_exact_keys(
        controller_lifecycle_evidence,
        ["task_ref", "tether_ref", "dispatch_ref", "state", "terminal_admission_ref"],
        "dispatch priority controller lifecycle evidence",
    )
    require(
        controller_lifecycle_evidence["task_ref"] == mark["task_ref"]
        and controller_lifecycle_evidence["tether_ref"] == mark["tether_ref"]
        and controller_lifecycle_evidence["dispatch_ref"] == mark["dispatch_ref"],
        "dispatch priority: canonical lifecycle subject mismatch",
    )
    require(
        controller_lifecycle_evidence["state"] == "TASK_COMMISSIONED_DISPATCH_PENDING"
        and controller_lifecycle_evidence["terminal_admission_ref"] is None,
        "dispatch priority: task must be commissioned and dispatch-pending",
    )
    _require_priority_authorization_binding(mark, priority_authorization, "dispatch priority")

    require_exact_keys(
        observed_snapshot_head,
        ["snapshot_id", "snapshot_ordinal", "snapshot_projection_sha256"],
        "dispatch priority observed snapshot head",
    )
    require(
        mark["observed_snapshot_ref"] == observed_snapshot_head["snapshot_id"]
        and mark["observed_snapshot_ordinal"] == observed_snapshot_head["snapshot_ordinal"]
        and mark["observed_snapshot_projection_sha256"]
        == observed_snapshot_head["snapshot_projection_sha256"],
        "dispatch priority: stale observed snapshot head",
    )
    require(
        mark["observed_priority_ledger_head_ref"]
        == trusted_current_priority_ledger_head["head_ref"]
        and mark["observed_priority_ledger_head_sha256"]
        == trusted_current_priority_ledger_head["head_sha256"],
        "dispatch priority: stale or forked global priority-ledger head",
    )
    require(
        mark["priority_receipt_ref"]
        not in {receipt.get("priority_receipt_ref") for receipt in existing_receipts},
        "dispatch priority: receipt reference replay",
    )
    require(
        mark["scheduling_mark_binding"]
        not in {receipt.get("scheduling_mark_binding") for receipt in existing_receipts},
        "dispatch priority: scheduling mark replay",
    )
    appended = [dict(receipt) for receipt in existing_receipts]
    appended.append({**mark, "ledger_ordinal": len(appended) + 1})
    _validate_priority_receipt_ledger(
        appended,
        mark["recorded_by_controller_ref"],
        mark["assigned_by_ref"],
        queue_id=mark["queue_id"],
        profile_ref=mark["profile_ref"],
        profile_epoch=mark["profile_epoch"],
        policy_ref=mark["policy_ref"],
        dispatch_basis_ref=dispatch_assignment_basis_ref,
        revision_basis_ref=revision_assignment_basis_ref,
        priority_genesis_head_ref=priority_genesis_head["head_ref"],
        priority_genesis_head_sha256=priority_genesis_head["head_sha256"],
    )
    return appended


def append_priority_revision(
    existing_receipts: list[dict[str, Any]],
    revision: dict[str, Any],
    trusted_controller_context: dict[str, Any] | None = None,
    priority_genesis_head: dict[str, Any] | None = None,
    trusted_current_priority_ledger_head: dict[str, Any] | None = None,
    dispatch_assignment_basis_ref: str | None = None,
    observed_snapshot_head: dict[str, Any] | None = None,
    controller_lifecycle_evidence: dict[str, Any] | None = None,
    priority_authorization: dict[str, Any] | None = None,
    revision_assignment_basis_ref: str | None = None,
) -> list[dict[str, Any]]:
    """Pure confirmed-append model; ambiguity is rejected with no mutation.

    The supplied register is first bound to an independently trusted current
    head. Exact idempotent retry resolution then precedes candidate snapshot and
    lifecycle CAS checks. A real persistent controller must reconcile an UNKNOWN
    append outcome before retrying; this offline helper never guesses.
    """
    require(isinstance(existing_receipts, list) and existing_receipts, "priority revision: existing register")
    require_exact_keys(
        trusted_controller_context,
        [
            "controller_ref",
            "priority_assigner_ref",
            "queue_id",
            "profile_ref",
            "profile_epoch",
            "policy_ref",
        ],
        "priority revision trusted controller context",
    )
    require_exact_keys(
        priority_genesis_head,
        ["head_ref", "head_sha256"],
        "priority revision genesis head",
    )
    controller_ref = trusted_controller_context["controller_ref"]
    assigner_ref = trusted_controller_context["priority_assigner_ref"]
    require(
        isinstance(dispatch_assignment_basis_ref, str)
        and dispatch_assignment_basis_ref,
        "priority revision: bounded dispatch assignment basis",
    )
    require(
        isinstance(revision_assignment_basis_ref, str)
        and revision_assignment_basis_ref,
        "priority revision: bounded revision assignment basis",
    )
    chains = _validate_priority_receipt_ledger(
        existing_receipts,
        controller_ref,
        assigner_ref,
        queue_id=trusted_controller_context["queue_id"],
        profile_ref=trusted_controller_context["profile_ref"],
        profile_epoch=trusted_controller_context["profile_epoch"],
        policy_ref=trusted_controller_context["policy_ref"],
        dispatch_basis_ref=dispatch_assignment_basis_ref,
        revision_basis_ref=revision_assignment_basis_ref,
        priority_genesis_head_ref=priority_genesis_head["head_ref"],
        priority_genesis_head_sha256=priority_genesis_head["head_sha256"],
    )
    _require_trusted_current_priority_ledger_head(
        existing_receipts,
        priority_genesis_head,
        trusted_current_priority_ledger_head,
        "priority revision",
    )
    candidate_keys = [field for field in PRIORITY_RECEIPT_KEYS if field != "ledger_ordinal"]
    require_exact_keys(revision, candidate_keys, "priority revision candidate")
    require(revision["receipt_kind"] == "PRIORITY_REVISION", "priority revision: revision receipt kind")
    require(
        type(revision["revision_ordinal"]) is int
        and revision["revision_ordinal"] >= 1,
        "priority revision: positive revision ordinal",
    )
    require(
        isinstance(revision["supersedes_priority_receipt_ref"], str)
        and revision["supersedes_priority_receipt_ref"],
        "priority revision: predecessor reference",
    )
    require(
        revision["assignment_basis_ref"] == revision_assignment_basis_ref,
        "priority revision: assignment basis",
    )
    require(
        revision["subject_state"] == "TASK_OUT_OR_RETURN_PENDING_NOT_ADMITTED",
        "priority revision: receipt lifecycle claim",
    )
    by_key = {receipt["idempotency_key"]: receipt for receipt in existing_receipts}
    prior_retry = by_key.get(revision["idempotency_key"])
    if prior_retry is not None:
        prior_without_ordinal = {
            field: value for field, value in prior_retry.items()
            if field != "ledger_ordinal"
        }
        require(
            _canonical_json_bytes(prior_without_ordinal) == _canonical_json_bytes(revision),
            "priority revision: idempotency key binding conflict",
        )
        return [dict(receipt) for receipt in existing_receipts]
    require_exact_keys(
        controller_lifecycle_evidence,
        ["task_ref", "tether_ref", "dispatch_ref", "state", "terminal_admission_ref"],
        "priority revision controller lifecycle evidence",
    )
    require(
        controller_lifecycle_evidence["task_ref"] == revision["task_ref"]
        and controller_lifecycle_evidence["tether_ref"] == revision["tether_ref"]
        and controller_lifecycle_evidence["dispatch_ref"] == revision["dispatch_ref"],
        "priority revision: canonical lifecycle subject mismatch",
    )
    require(
        controller_lifecycle_evidence["state"]
        in {"TASK_OUT", "RETURN_PENDING_NOT_SELECTED"}
        and controller_lifecycle_evidence["terminal_admission_ref"] is None,
        "priority revision: selected, in-service, admitted, or terminal subject",
    )
    _require_priority_authorization_binding(revision, priority_authorization, "priority revision")
    require(
        revision["observed_priority_ledger_head_ref"]
        == trusted_current_priority_ledger_head["head_ref"]
        and revision["observed_priority_ledger_head_sha256"]
        == trusted_current_priority_ledger_head["head_sha256"],
        "priority revision: stale or forked global priority-ledger head",
    )
    require_exact_keys(
        observed_snapshot_head,
        ["snapshot_id", "snapshot_ordinal", "snapshot_projection_sha256"],
        "priority revision observed snapshot head",
    )
    require(
        revision["observed_snapshot_ref"] == observed_snapshot_head["snapshot_id"]
        and revision["observed_snapshot_ordinal"] == observed_snapshot_head["snapshot_ordinal"]
        and revision["observed_snapshot_projection_sha256"]
        == observed_snapshot_head["snapshot_projection_sha256"],
        "priority revision: stale observed snapshot head",
    )
    require(
        revision["priority_receipt_ref"]
        not in {receipt["priority_receipt_ref"] for receipt in existing_receipts},
        "priority revision: receipt reference replay",
    )
    require(
        revision["scheduling_mark_binding"]
        not in {receipt["scheduling_mark_binding"] for receipt in existing_receipts},
        "priority revision: scheduling mark replay",
    )
    chain = chains.get(revision["tether_ref"])
    require(chain is not None, "priority revision: missing dispatch root")
    latest = chain[-1]
    require(revision["task_ref"] == latest["task_ref"], "priority revision: task drift")
    require(revision["assigned_by_ref"] == assigner_ref, "priority revision: Hearthline assignment source")
    require(revision["recorded_by_controller_ref"] == controller_ref, "priority revision: controller persistence")
    require(
        revision["revision_ordinal"] == latest["revision_ordinal"] + 1
        and revision["supersedes_priority_receipt_ref"] == latest["priority_receipt_ref"],
        "priority revision: stale, replayed, or forked predecessor",
    )
    appended = [dict(receipt) for receipt in existing_receipts]
    appended.append({**revision, "ledger_ordinal": len(appended) + 1})
    _validate_priority_receipt_ledger(
        appended,
        controller_ref,
        assigner_ref,
        queue_id=trusted_controller_context["queue_id"],
        profile_ref=trusted_controller_context["profile_ref"],
        profile_epoch=trusted_controller_context["profile_epoch"],
        policy_ref=trusted_controller_context["policy_ref"],
        dispatch_basis_ref=dispatch_assignment_basis_ref,
        revision_basis_ref=revision_assignment_basis_ref,
        priority_genesis_head_ref=priority_genesis_head["head_ref"],
        priority_genesis_head_sha256=priority_genesis_head["head_sha256"],
    )
    return appended


def _validate_priority_append_hold_record(
    hold: Any,
    trusted_controller_context: dict[str, Any] | None = None,
    label: str = "priority append hold",
) -> None:
    """Validate the closed controller record for an UNKNOWN append outcome."""
    require_exact_keys(hold, PRIORITY_APPEND_HOLD_KEYS, label)
    for field in (
        "priority_append_hold_ref",
        "idempotency_key",
        "controller_ref",
        "queue_id",
        "profile_ref",
        "policy_ref",
        "priority_authorization_ref",
        "task_ref",
        "tether_ref",
        "task_tether_core_sha256",
        "dispatch_ref",
        "attempted_priority_receipt_ref",
        "attempted_priority_receipt_sha256",
        "attempted_supersedes_priority_receipt_ref",
        "observed_priority_ledger_head_ref",
        "observed_priority_ledger_head_sha256",
        "observed_snapshot_ref",
        "observed_snapshot_projection_sha256",
        "reconciliation_handle",
    ):
        require(isinstance(hold[field], str) and hold[field], f"{label}: {field}")
    for field in (
        "task_tether_core_sha256",
        "attempted_priority_receipt_sha256",
        "observed_priority_ledger_head_sha256",
        "observed_snapshot_projection_sha256",
    ):
        require(HEX64.fullmatch(hold[field]) is not None, f"{label}: {field} digest")
    require(type(hold["profile_epoch"]) is int and hold["profile_epoch"] >= 1, f"{label}: profile epoch")
    require(
        type(hold["attempted_revision_ordinal"]) is int
        and hold["attempted_revision_ordinal"] >= 1,
        f"{label}: attempted revision ordinal",
    )
    require(
        type(hold["observed_snapshot_ordinal"]) is int
        and hold["observed_snapshot_ordinal"] >= 0,
        f"{label}: observed snapshot ordinal",
    )
    require(hold["attempted_receipt_kind"] == "PRIORITY_REVISION", f"{label}: attempted receipt kind")
    require(hold["persistence_outcome"] == "UNKNOWN", f"{label}: persistence outcome")
    require(hold["hold_state"] == "PRIORITY_APPEND_UNKNOWN_HELD", f"{label}: hold state")
    require(hold["reconciliation_receipt_ref"] is None, f"{label}: unresolved hold cannot name reconciliation")
    require(hold["can_enter_ready"] is False, f"{label}: UNKNOWN append cannot enter READY")
    require(hold["external_effect_receipt_ref"] is None, f"{label}: external effect forbidden")
    if trusted_controller_context is not None:
        require_exact_keys(
            trusted_controller_context,
            [
                "controller_ref",
                "priority_assigner_ref",
                "queue_id",
                "profile_ref",
                "profile_epoch",
                "policy_ref",
            ],
            f"{label} trusted controller context",
        )
        for hold_field, context_field in (
            ("controller_ref", "controller_ref"),
            ("queue_id", "queue_id"),
            ("profile_ref", "profile_ref"),
            ("profile_epoch", "profile_epoch"),
            ("policy_ref", "policy_ref"),
        ):
            require(
                _canonical_json_bytes(hold[hold_field])
                == _canonical_json_bytes(trusted_controller_context[context_field]),
                f"{label}: trusted {hold_field}",
            )


def stage_unknown_priority_revision(
    existing_receipts: list[dict[str, Any]],
    revision: dict[str, Any],
    hold_identity: dict[str, Any],
    trusted_controller_context: dict[str, Any],
    priority_genesis_head: dict[str, Any],
    trusted_current_priority_ledger_head: dict[str, Any],
    dispatch_assignment_basis_ref: str,
    observed_snapshot_head: dict[str, Any],
    controller_lifecycle_evidence: dict[str, Any],
    priority_authorization: dict[str, Any],
    revision_assignment_basis_ref: str,
) -> dict[str, Any]:
    """Create a fail-closed hold after an otherwise-valid append stays UNKNOWN.

    The returned record does not append the revision and does not make its
    priority effective. It commits the attempted closed revision by digest so
    the controller can reconcile durable state without guessing.
    """
    require_exact_keys(
        hold_identity,
        ["priority_append_hold_ref", "reconciliation_handle"],
        "priority append hold identity",
    )
    for field in ("priority_append_hold_ref", "reconciliation_handle"):
        require(isinstance(hold_identity[field], str) and hold_identity[field], f"priority append hold identity: {field}")
    require(
        not any(
            receipt.get("priority_receipt_ref") == revision.get("priority_receipt_ref")
            or receipt.get("idempotency_key") == revision.get("idempotency_key")
            for receipt in existing_receipts
        ),
        "priority append hold: attempted revision is already known durable",
    )
    append_priority_revision(
        existing_receipts,
        revision,
        trusted_controller_context=trusted_controller_context,
        priority_genesis_head=priority_genesis_head,
        trusted_current_priority_ledger_head=trusted_current_priority_ledger_head,
        dispatch_assignment_basis_ref=dispatch_assignment_basis_ref,
        observed_snapshot_head=observed_snapshot_head,
        controller_lifecycle_evidence=controller_lifecycle_evidence,
        priority_authorization=priority_authorization,
        revision_assignment_basis_ref=revision_assignment_basis_ref,
    )
    hold = {
        "priority_append_hold_ref": hold_identity["priority_append_hold_ref"],
        "idempotency_key": revision["idempotency_key"],
        "controller_ref": revision["recorded_by_controller_ref"],
        "queue_id": revision["queue_id"],
        "profile_ref": revision["profile_ref"],
        "profile_epoch": revision["profile_epoch"],
        "policy_ref": revision["policy_ref"],
        "priority_authorization_ref": revision["priority_authorization_ref"],
        "task_ref": revision["task_ref"],
        "tether_ref": revision["tether_ref"],
        "task_tether_core_sha256": revision["task_tether_core_sha256"],
        "dispatch_ref": revision["dispatch_ref"],
        "attempted_priority_receipt_ref": revision["priority_receipt_ref"],
        "attempted_priority_receipt_sha256": _canonical_json_sha256(revision),
        "attempted_receipt_kind": revision["receipt_kind"],
        "attempted_revision_ordinal": revision["revision_ordinal"],
        "attempted_supersedes_priority_receipt_ref": revision["supersedes_priority_receipt_ref"],
        "observed_priority_ledger_head_ref": revision["observed_priority_ledger_head_ref"],
        "observed_priority_ledger_head_sha256": revision["observed_priority_ledger_head_sha256"],
        "observed_snapshot_ordinal": revision["observed_snapshot_ordinal"],
        "observed_snapshot_ref": revision["observed_snapshot_ref"],
        "observed_snapshot_projection_sha256": revision["observed_snapshot_projection_sha256"],
        "persistence_outcome": "UNKNOWN",
        "hold_state": "PRIORITY_APPEND_UNKNOWN_HELD",
        "reconciliation_handle": hold_identity["reconciliation_handle"],
        "reconciliation_receipt_ref": None,
        "can_enter_ready": False,
        "external_effect_receipt_ref": None,
    }
    _validate_priority_append_hold_record(hold, trusted_controller_context)
    return hold


def resolve_priority_append_hold(
    hold: dict[str, Any],
    reconciliation: dict[str, Any],
    durable_priority_receipts: list[dict[str, Any]],
    trusted_controller_context: dict[str, Any],
    priority_genesis_head: dict[str, Any],
    dispatch_assignment_basis_ref: str,
    revision_assignment_basis_ref: str,
    trusted_current_priority_ledger_head: dict[str, Any],
    priority_authorization: dict[str, Any],
    trusted_observed_snapshot_head: dict[str, Any],
    trusted_priority_append_hold_head: dict[str, Any],
) -> dict[str, Any]:
    """Validate a durable NOT-APPENDED reconciliation before READY re-entry.

    Confirmed appended attempts must first appear as normal validated priority
    receipts. This narrow helper only releases the safe, confirmed-not-appended
    branch; it never guesses from an UNKNOWN persistence result.
    """
    _validate_priority_append_hold_record(hold, trusted_controller_context)
    require_exact_keys(
        trusted_priority_append_hold_head,
        ["hold_ref", "hold_sha256"],
        "priority append reconciliation trusted hold head",
    )
    require(
        trusted_priority_append_hold_head["hold_ref"]
        == hold["priority_append_hold_ref"]
        and trusted_priority_append_hold_head["hold_sha256"]
        == _canonical_json_sha256(hold),
        "priority append reconciliation: authenticated durable hold membership",
    )
    require_exact_keys(reconciliation, PRIORITY_APPEND_RECONCILIATION_KEYS, "priority append reconciliation")
    require(
        isinstance(durable_priority_receipts, list) and durable_priority_receipts,
        "priority append reconciliation: durable register",
    )
    require(
        all(isinstance(receipt, dict) for receipt in durable_priority_receipts),
        "priority append reconciliation: durable receipt objects",
    )
    require_exact_keys(priority_genesis_head, ["head_ref", "head_sha256"], "priority append reconciliation genesis")
    require_exact_keys(
        trusted_current_priority_ledger_head,
        TRUSTED_PRIORITY_LEDGER_HEAD_KEYS,
        "priority append reconciliation trusted current ledger head",
    )
    chains = _validate_priority_receipt_ledger(
        durable_priority_receipts,
        trusted_controller_context["controller_ref"],
        trusted_controller_context["priority_assigner_ref"],
        queue_id=trusted_controller_context["queue_id"],
        profile_ref=trusted_controller_context["profile_ref"],
        profile_epoch=trusted_controller_context["profile_epoch"],
        policy_ref=trusted_controller_context["policy_ref"],
        dispatch_basis_ref=dispatch_assignment_basis_ref,
        revision_basis_ref=revision_assignment_basis_ref,
        priority_genesis_head_ref=priority_genesis_head["head_ref"],
        priority_genesis_head_sha256=priority_genesis_head["head_sha256"],
    )
    _require_trusted_current_priority_ledger_head(
        durable_priority_receipts,
        priority_genesis_head,
        trusted_current_priority_ledger_head,
        "priority append reconciliation",
    )
    require_exact_keys(
        priority_authorization,
        PRIORITY_AUTHORIZATION_KEYS,
        "priority append reconciliation authorization",
    )
    for hold_field, authorization_field in (
        ("priority_authorization_ref", "priority_authorization_ref"),
        ("queue_id", "queue_id"),
        ("profile_ref", "profile_ref"),
        ("profile_epoch", "profile_epoch"),
        ("policy_ref", "policy_ref"),
        ("task_ref", "task_ref"),
        ("tether_ref", "tether_ref"),
        ("task_tether_core_sha256", "task_tether_core_sha256"),
        ("dispatch_ref", "dispatch_ref"),
        ("controller_ref", "recorded_by_controller_ref"),
    ):
        require(
            _canonical_json_bytes(hold[hold_field])
            == _canonical_json_bytes(priority_authorization[authorization_field]),
            f"priority append reconciliation: authorization {hold_field}",
        )
    chain = chains.get(hold["tether_ref"])
    require(chain is not None, "priority append reconciliation: authenticated tether chain")
    root = chain[0]
    _require_priority_authorization_binding(
        root,
        priority_authorization,
        "priority append reconciliation",
    )
    for hold_field, root_field in (
        ("priority_authorization_ref", "priority_authorization_ref"),
        ("queue_id", "queue_id"),
        ("profile_ref", "profile_ref"),
        ("profile_epoch", "profile_epoch"),
        ("policy_ref", "policy_ref"),
        ("task_ref", "task_ref"),
        ("tether_ref", "tether_ref"),
        ("task_tether_core_sha256", "task_tether_core_sha256"),
        ("dispatch_ref", "dispatch_ref"),
        ("controller_ref", "recorded_by_controller_ref"),
    ):
        require(
            _canonical_json_bytes(hold[hold_field])
            == _canonical_json_bytes(root[root_field]),
            f"priority append reconciliation: authenticated root {hold_field}",
        )
    latest = chain[-1]
    require(
        hold["attempted_revision_ordinal"] == latest["revision_ordinal"] + 1
        and hold["attempted_revision_ordinal"]
        <= priority_authorization["maximum_priority_revisions"]
        and hold["attempted_supersedes_priority_receipt_ref"]
        == latest["priority_receipt_ref"],
        "priority append reconciliation: exact authorized predecessor and revision budget",
    )
    observed_global = next(
        (
            receipt for receipt in durable_priority_receipts
            if receipt["priority_receipt_ref"]
            == hold["observed_priority_ledger_head_ref"]
        ),
        None,
    )
    require(
        observed_global is not None
        and observed_global["ledger_ordinal"] >= latest["ledger_ordinal"]
        and hold["observed_priority_ledger_head_sha256"]
        == _canonical_json_sha256(observed_global),
        "priority append reconciliation: authenticated observed global head",
    )
    require_exact_keys(
        trusted_observed_snapshot_head,
        ["snapshot_id", "snapshot_ordinal", "snapshot_projection_sha256"],
        "priority append reconciliation trusted observed snapshot",
    )
    require(
        hold["observed_snapshot_ref"]
        == trusted_observed_snapshot_head["snapshot_id"]
        and hold["observed_snapshot_ordinal"]
        == trusted_observed_snapshot_head["snapshot_ordinal"]
        and hold["observed_snapshot_projection_sha256"]
        == trusted_observed_snapshot_head["snapshot_projection_sha256"],
        "priority append reconciliation: authenticated observed snapshot head",
    )
    for field in (
        "priority_append_reconciliation_receipt_ref",
        "priority_append_hold_ref",
        "controller_ref",
        "queue_id",
        "profile_ref",
        "policy_ref",
        "task_ref",
        "tether_ref",
        "task_tether_core_sha256",
        "dispatch_ref",
        "reconciliation_handle",
        "revalidation_inputs_ref",
    ):
        require(isinstance(reconciliation[field], str) and reconciliation[field], f"priority append reconciliation: {field}")
    require(
        reconciliation["priority_append_reconciliation_receipt_ref"]
        not in {
            hold["priority_append_hold_ref"],
            hold["attempted_priority_receipt_ref"],
            *(receipt.get("priority_receipt_ref") for receipt in durable_priority_receipts),
        },
        "priority append reconciliation: record identity reuse",
    )
    for reconciliation_field, hold_field in (
        ("priority_append_hold_ref", "priority_append_hold_ref"),
        ("controller_ref", "controller_ref"),
        ("queue_id", "queue_id"),
        ("profile_ref", "profile_ref"),
        ("profile_epoch", "profile_epoch"),
        ("policy_ref", "policy_ref"),
        ("task_ref", "task_ref"),
        ("tether_ref", "tether_ref"),
        ("task_tether_core_sha256", "task_tether_core_sha256"),
        ("dispatch_ref", "dispatch_ref"),
        ("reconciliation_handle", "reconciliation_handle"),
    ):
        require(
            _canonical_json_bytes(reconciliation[reconciliation_field])
            == _canonical_json_bytes(hold[hold_field]),
            f"priority append reconciliation: {reconciliation_field} binding",
        )
    require(
        reconciliation["reconciled_persistence_outcome"] == "CONFIRMED_NOT_APPENDED",
        "priority append reconciliation: only confirmed-not-appended can use this release path",
    )
    require(reconciliation["confirmed_priority_receipt_ref"] is None, "priority append reconciliation: non-append receipt ref")
    require(reconciliation["confirmed_priority_receipt_sha256"] is None, "priority append reconciliation: non-append receipt digest")
    require(
        not any(
            receipt.get("priority_receipt_ref") == hold["attempted_priority_receipt_ref"]
            or receipt.get("idempotency_key") == hold["idempotency_key"]
            for receipt in durable_priority_receipts
        ),
        "priority append reconciliation: attempted revision is present in durable register",
    )
    require(reconciliation["revalidation_result"] == "PASS", "priority append reconciliation: current revalidation must pass")
    require(
        reconciliation["status"] == "PRIORITY_APPEND_RECONCILED_READY_ELIGIBLE"
        and reconciliation["can_enter_ready"] is True,
        "priority append reconciliation: READY eligibility",
    )
    require(reconciliation["external_effect_receipt_ref"] is None, "priority append reconciliation: external effect forbidden")
    return dict(reconciliation)


def linearize_return_intake(
    existing_intakes: list[dict[str, Any]],
    arrival_batch: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Assign controller-linearized ordinals while preserving idempotency."""
    require(isinstance(existing_intakes, list), "return intake: existing array")
    require(isinstance(arrival_batch, list) and arrival_batch, "return intake: nonempty batch")
    result = [dict(item) for item in existing_intakes]
    by_key: dict[str, dict[str, Any]] = {}
    identity_fields = (
        "queue_item_id",
        "return_id",
        "intake_receipt_ref",
        "enqueue_receipt_ref",
        "return_receipt_ref",
    )
    seen_identity = {field: set() for field in identity_fields}
    receipt_refs: set[str] = set()
    for expected_ordinal, item in enumerate(result, start=1):
        require(
            type(item.get("arrival_ordinal")) is int
            and item["arrival_ordinal"] == expected_ordinal,
            "return intake: existing ordinal chain",
        )
        key = item.get("idempotency_key")
        require(isinstance(key, str) and key and key not in by_key, "return intake: unique existing idempotency key")
        for field, seen in seen_identity.items():
            value = item.get(field)
            require(
                isinstance(value, str) and value and value not in seen,
                f"return intake: unique existing {field}",
            )
            seen.add(value)
            if field.endswith("receipt_ref"):
                require(value not in receipt_refs, "return intake: receipt reference reused across records")
                receipt_refs.add(value)
        by_key[key] = item

    for arrival in arrival_batch:
        require(isinstance(arrival, dict), "return intake: arrival object")
        require("arrival_ordinal" not in arrival, "return intake: controller alone assigns arrival ordinal")
        key = arrival.get("idempotency_key")
        require(isinstance(key, str) and key, "return intake: idempotency key")
        for field in identity_fields:
            value = arrival.get(field)
            require(isinstance(value, str) and value, f"return intake: {field}")
        prior = by_key.get(key)
        if prior is not None:
            prior_without_ordinal = {
                field: value for field, value in prior.items()
                if field != "arrival_ordinal"
            }
            require(
                _canonical_json_bytes(prior_without_ordinal)
                == _canonical_json_bytes(arrival),
                "return intake: idempotency key identity conflict",
            )
            continue
        arrival_receipts = [
            arrival[field]
            for field in identity_fields
            if field.endswith("receipt_ref")
        ]
        require(
            len(arrival_receipts) == len(set(arrival_receipts)),
            "return intake: receipt reference reused across records",
        )
        for field, seen in seen_identity.items():
            value = arrival[field]
            require(value not in seen, f"return intake: {field} reused with another idempotency key")
            if field.endswith("receipt_ref"):
                require(value not in receipt_refs, "return intake: receipt reference reused across records")
        admitted = {**arrival, "arrival_ordinal": len(result) + 1}
        result.append(admitted)
        by_key[key] = admitted
        for field, seen in seen_identity.items():
            seen.add(arrival[field])
            if field.endswith("receipt_ref"):
                receipt_refs.add(arrival[field])
    return result


def return_queue_snapshot_projection(
    snapshot: dict[str, Any],
    return_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return an opaque full-partition projection for controller binding."""
    scheduling_view = return_queue_scheduling_view_projection(snapshot, return_by_id)
    return {
        "queue_id": snapshot["queue_id"],
        "destination_ref": snapshot["destination_ref"],
        "synchronization_point_ref": snapshot["synchronization_point_ref"],
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_ordinal": snapshot["snapshot_ordinal"],
        "profile_ref": snapshot["profile_ref"],
        "profile_epoch": snapshot["profile_epoch"],
        "service_epoch": snapshot["service_epoch"],
        "policy_ref": snapshot["policy_ref"],
        "maximum_overtakes": snapshot["maximum_overtakes"],
        "maximum_snapshot_items": snapshot["maximum_snapshot_items"],
        "cut_arrival_ordinal": snapshot["cut_arrival_ordinal"],
        "priority_ledger_cut_ordinal": snapshot["priority_ledger_cut_ordinal"],
        "morrow_ready_view": scheduling_view,
        "service_reopen_receipts": snapshot["service_reopen_receipts"],
        "visible_bindings": [return_by_id[item]["scheduling_binding"] for item in snapshot["visible_ids"]],
        "ready_bindings": [return_by_id[item]["scheduling_binding"] for item in snapshot["ready_ids"]],
        "held_bindings": [return_by_id[item]["scheduling_binding"] for item in snapshot["held_ids"]],
        "previously_admitted_bindings": [
            return_by_id[item]["scheduling_binding"]
            for item in snapshot["previously_admitted_ids"]
        ],
        "effective_priority_marks": snapshot["effective_priority_marks"],
    }


def return_queue_scheduling_view_projection(
    snapshot: dict[str, Any],
    return_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return the closed, metadata-only view allowed to the Queue Steward."""
    priority_by_id = {
        item["queue_item_id"]: item
        for item in snapshot["effective_priority_marks"]
    }
    counts = {
        item["queue_item_id"]: item["count"]
        for item in snapshot["overtake_counts_before"]
    }
    opaque_binding_by_id = {
        item["queue_item_id"]: item["opaque_queue_item_binding"]
        for item in snapshot["morrow_ready_bindings"]
    }
    ready_projection = []
    for ready_arrival_rank, queue_item_id in enumerate(snapshot["ready_ids"], start=1):
        item = return_by_id[queue_item_id]
        priority = priority_by_id[queue_item_id]
        ready_projection.append({
            "opaque_queue_item_binding": opaque_binding_by_id[queue_item_id],
            "ready_arrival_rank": ready_arrival_rank,
            "effective_priority_rank": priority["priority_rank"],
            "controller_approved_processing_cost": item["controller_approved_processing_cost"],
            "overtake_count": counts[queue_item_id],
        })
    return {
        "schema": "hearthline-plays.morrow-scheduling-view.v1",
        "status": "CONTROLLER_FROZEN_READY_ONLY_VIEW",
        "invocation_cut_binding": snapshot["morrow_invocation_cut_binding"],
        "policy_ref": snapshot["policy_ref"],
        "maximum_overtakes": snapshot["maximum_overtakes"],
        "ready_scheduling_view": ready_projection,
    }


def return_queue_snapshot_sha256(
    snapshot: dict[str, Any],
    return_by_id: dict[str, dict[str, Any]],
) -> str:
    encoded = json.dumps(
        return_queue_snapshot_projection(snapshot, return_by_id),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def return_queue_scheduling_view_sha256(
    snapshot: dict[str, Any],
    return_by_id: dict[str, dict[str, Any]],
) -> str:
    encoded = json.dumps(
        return_queue_scheduling_view_projection(snapshot, return_by_id),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def expected_morrow_binding_order(
    snapshot: dict[str, Any],
    return_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Return the exact pure Morrow order for a controller-frozen view."""
    view = return_queue_scheduling_view_projection(snapshot, return_by_id)
    maximum_overtakes = view["maximum_overtakes"]
    items = view["ready_scheduling_view"]
    due = sorted(
        (item for item in items if item["overtake_count"] >= maximum_overtakes),
        key=lambda item: item["ready_arrival_rank"],
    )
    not_due = sorted(
        (item for item in items if item["overtake_count"] < maximum_overtakes),
        key=lambda item: (
            item["effective_priority_rank"],
            item["controller_approved_processing_cost"],
            item["ready_arrival_rank"],
        ),
    )
    return [
        item["opaque_queue_item_binding"]
        for item in [*due, *not_due]
    ]


def _map_queue_steward_order(
    raw_order: Any,
    binding_to_queue_item: dict[str, str],
) -> list[str] | None:
    if (
        not isinstance(raw_order, list)
        or not all(isinstance(binding, str) for binding in raw_order)
        or len(raw_order) != len(set(raw_order))
        or set(raw_order) != set(binding_to_queue_item)
    ):
        return None
    return [binding_to_queue_item[binding] for binding in raw_order]


def map_untrusted_morrow_output(
    output: Any,
    invocation_cut_binding: str,
    scheduling_view_sha256: str,
    policy_ref: str,
    binding_to_queue_item: dict[str, str],
    expected_ready_order: list[str],
) -> list[str] | None:
    """Parse one untrusted Morrow output; every malformed case returns None."""
    try:
        require_exact_keys(
            output,
            [
                "schema",
                "status",
                "invocation_cut_binding",
                "scheduling_view_sha256",
                "policy_ref",
                "ready_order",
                "reason_codes",
                "pure_metadata_only",
                "deterministic_stateless",
                "persistent_state_ref",
                "external_effect_count",
            ],
            "Morrow output",
        )
        require(output["schema"] == "hearthline-plays.morrow-proposal.v1", "Morrow output: schema")
        require(output["status"] == "PROPOSAL_ONLY_NO_ADMISSION", "Morrow output: status")
        require(output["invocation_cut_binding"] == invocation_cut_binding, "Morrow output: stale or replayed invocation cut")
        require(output["scheduling_view_sha256"] == scheduling_view_sha256, "Morrow output: stale or mutated ready-only view")
        require(output["policy_ref"] == policy_ref, "Morrow output: policy")
        require(
            output["reason_codes"]
            == [
                "MAXIMUM_OVERTAKES_DUE_OLDEST_FIRST",
                "PRIORITY_RANK_ASCENDING_ZERO_FIRST",
                "CONTROLLER_APPROVED_COST_ASCENDING_WITHIN_PRIORITY",
                "READY_ARRIVAL_RANK_ASCENDING_TIE_BREAK",
            ],
            "Morrow output: reason codes",
        )
        require(output["pure_metadata_only"] is True, "Morrow output: purity")
        require(output["deterministic_stateless"] is True, "Morrow output: statelessness")
        require(output["persistent_state_ref"] is None, "Morrow output: persistence forbidden")
        require(
            type(output["external_effect_count"]) is int
            and output["external_effect_count"] == 0,
            "Morrow output: external effect",
        )
        mapped = _map_queue_steward_order(output["ready_order"], binding_to_queue_item)
        require(mapped is not None, "Morrow output: order coverage")
        require(
            output["ready_order"] == expected_ready_order,
            "Morrow output: deterministic policy order",
        )
        return mapped
    except (VerificationError, KeyError, TypeError):
        return None


def ingest_morrow_output(
    raw_output: bytes,
    invocation_cut_binding: str,
    scheduling_view_sha256: str,
    policy_ref: str,
    binding_to_queue_item: dict[str, str],
    expected_ready_order: list[str],
    replayed_invocation_cut_bindings: set[str] | None = None,
) -> dict[str, Any]:
    """Normalize bounded raw Morrow bytes to a valid output or closed capture."""
    require(isinstance(raw_output, bytes), "Morrow ingress: raw output must be bytes")
    require(
        len(raw_output) <= MAXIMUM_MORROW_OUTPUT_BYTES,
        "Morrow ingress: raw output exceeds bounded byte limit",
    )
    raw_sha256 = hashlib.sha256(raw_output).hexdigest()
    parsed: Any = None
    failure_code = "MALFORMED"
    try:
        parsed = loads_strict_json(raw_output.decode("utf-8"), "Morrow output")
    except (VerificationError, UnicodeError, ValueError, RecursionError, OverflowError):
        pass
    else:
        mapped = map_untrusted_morrow_output(
            parsed,
            invocation_cut_binding,
            scheduling_view_sha256,
            policy_ref,
            binding_to_queue_item,
            expected_ready_order,
        )
        if mapped is not None:
            return parsed
        valid_keys = {
            "schema",
            "status",
            "invocation_cut_binding",
            "scheduling_view_sha256",
            "policy_ref",
            "ready_order",
            "reason_codes",
            "pure_metadata_only",
            "deterministic_stateless",
            "persistent_state_ref",
            "external_effect_count",
        }
        structural_candidate = (
            isinstance(parsed, dict)
            and set(parsed) == valid_keys
            and parsed.get("schema") == "hearthline-plays.morrow-proposal.v1"
            and parsed.get("status") == "PROPOSAL_ONLY_NO_ADMISSION"
            and _is_safe_opaque_token(parsed.get("invocation_cut_binding"))
            and isinstance(parsed.get("scheduling_view_sha256"), str)
            and HEX64.fullmatch(parsed["scheduling_view_sha256"]) is not None
            and isinstance(parsed.get("policy_ref"), str)
            and parsed["policy_ref"]
            and isinstance(parsed.get("ready_order"), list)
            and all(_is_safe_opaque_token(binding) for binding in parsed["ready_order"])
            and parsed.get("reason_codes")
            == [
                "MAXIMUM_OVERTAKES_DUE_OLDEST_FIRST",
                "PRIORITY_RANK_ASCENDING_ZERO_FIRST",
                "CONTROLLER_APPROVED_COST_ASCENDING_WITHIN_PRIORITY",
                "READY_ARRIVAL_RANK_ASCENDING_TIE_BREAK",
            ]
            and parsed.get("pure_metadata_only") is True
            and parsed.get("deterministic_stateless") is True
            and parsed.get("persistent_state_ref") is None
            and type(parsed.get("external_effect_count")) is int
            and parsed.get("external_effect_count") == 0
        )
        if structural_candidate:
            if parsed["policy_ref"] != policy_ref:
                failure_code = "POLICY_MISMATCH"
            elif parsed["invocation_cut_binding"] != invocation_cut_binding:
                if (
                    replayed_invocation_cut_bindings is not None
                    and parsed["invocation_cut_binding"]
                    in replayed_invocation_cut_bindings
                ):
                    failure_code = "REPLAYED"
                else:
                    failure_code = "STALE"
            elif parsed["scheduling_view_sha256"] != scheduling_view_sha256:
                failure_code = "STALE"
            elif isinstance(parsed["ready_order"], list):
                ready_order = parsed["ready_order"]
                if any(
                    not isinstance(binding, str)
                    or binding not in binding_to_queue_item
                    for binding in ready_order
                ):
                    failure_code = "UNKNOWN_BINDING"
                elif ready_order != expected_ready_order:
                    if len(ready_order) != len(set(ready_order)) or set(ready_order) != set(binding_to_queue_item):
                        failure_code = "INCOMPLETE_OR_DUPLICATE_ORDER"
                    else:
                        failure_code = "POLICY_MISMATCH"
                else:
                    failure_code = "INCOMPLETE_OR_DUPLICATE_ORDER"
    return {
        "schema": "hearthline-plays.morrow-invalid-output-capture.v1",
        "status": "INVALID_UNTRUSTED_OUTPUT_CAPTURED_FOR_FALLBACK",
        "invocation_cut_binding": invocation_cut_binding,
        "scheduling_view_sha256": scheduling_view_sha256,
        "policy_ref": policy_ref,
        "bounded_raw_output_sha256": raw_sha256,
        "bounded_raw_output_byte_count": len(raw_output),
        "failure_code": failure_code,
        "raw_output_retained": False,
    }


def reduce_return_queue_snapshot(
    ready_returns: list[dict[str, Any]],
    overtake_counts_before: dict[str, int],
    effective_priority_ranks: dict[str, int],
    proposal_order: Any,
    maximum_overtakes: int,
) -> dict[str, Any]:
    """Compute one pure, deterministic, single-head queue transition."""
    require(ready_returns, "return queue reducer: at least one ready return")
    require(
        type(maximum_overtakes) is int
        and 1 <= maximum_overtakes <= MAXIMUM_OVERTAKES,
        "return queue reducer: bounded maximum_overtakes",
    )
    require(all(isinstance(item, dict) for item in ready_returns), "return queue reducer: ready returns must be objects")
    ready_ids = [item.get("queue_item_id") for item in ready_returns]
    require(all(isinstance(item, str) and item for item in ready_ids), "return queue reducer: nonempty ready queue item IDs")
    require(len(ready_ids) == len(set(ready_ids)), "return queue reducer: duplicate ready ID")
    arrival_ordinals = [item.get("arrival_ordinal") for item in ready_returns]
    require(
        all(type(value) is int and value >= 1 for value in arrival_ordinals)
        and len(arrival_ordinals) == len(set(arrival_ordinals)),
        "return queue reducer: unique positive integer arrival ordinals",
    )
    require(
        all(
            type(item.get("controller_approved_processing_cost")) is int
            and 1 <= item["controller_approved_processing_cost"]
            <= MAXIMUM_CONTROLLER_APPROVED_PROCESSING_COST
            for item in ready_returns
        ),
        "return queue reducer: positive integer controller-approved costs",
    )
    require(set(overtake_counts_before) == set(ready_ids), "return queue reducer: overtake coverage")
    require(
        all(type(count) is int and 0 <= count <= maximum_overtakes for count in overtake_counts_before.values()),
        "return queue reducer: overtake count outside policy",
    )
    require(set(effective_priority_ranks) == set(ready_ids), "return queue reducer: effective priority coverage")
    require(
        all(
            type(rank) is int and rank in PRIORITY_RANKS.values()
            for rank in effective_priority_ranks.values()
        ),
        "return queue reducer: effective priority rank",
    )
    fifo_order = [
        item["queue_item_id"]
        for item in sorted(ready_returns, key=lambda item: item["arrival_ordinal"])
    ]
    priority_fifo_order = [
        item["queue_item_id"]
        for item in sorted(
            ready_returns,
            key=lambda item: (
                effective_priority_ranks[item["queue_item_id"]],
                item["arrival_ordinal"],
            ),
        )
    ]
    priority_cost_order = [
        item["queue_item_id"]
        for item in sorted(
            ready_returns,
            key=lambda item: (
                effective_priority_ranks[item["queue_item_id"]],
                item["controller_approved_processing_cost"],
                item["arrival_ordinal"],
            ),
        )
    ]
    due = [
        return_id for return_id in fifo_order
        if overtake_counts_before[return_id] >= maximum_overtakes
    ]
    expected_proposal_order = due + [
        return_id for return_id in priority_cost_order
        if return_id not in due
    ]
    proposal_valid = (
        isinstance(proposal_order, list)
        and all(isinstance(item, str) for item in proposal_order)
        and len(proposal_order) == len(set(proposal_order)) == len(ready_ids)
        and set(proposal_order) == set(ready_ids)
        and proposal_order == expected_proposal_order
    )
    if proposal_valid:
        proposed_schedule = list(proposal_order)
        proposal_status = "ACCEPTED_EXACT_PRIORITY_COST_FAIRNESS_PERMUTATION"
        schedule_basis = "VALID_MORROW_PRIORITY_COST_PROPOSAL"
    else:
        proposed_schedule = due + [
            return_id for return_id in priority_fifo_order
            if return_id not in due
        ]
        proposal_status = "FALLBACK_CONTROLLER_PRIORITY_FIFO_ABSENT_OR_INVALID_PROPOSAL"
        schedule_basis = "CONTROLLER_PRIORITY_THEN_FIFO_FALLBACK"

    return_by_id = {item["queue_item_id"]: item for item in ready_returns}
    forced_head = due[0] if due else None
    if forced_head is not None:
        schedule_order = [forced_head] + [
            return_id for return_id in proposed_schedule if return_id != forced_head
        ]
        schedule_basis = "MAXIMUM_OVERTAKES_FIFO_FORCED"
    else:
        schedule_order = proposed_schedule

    service_head = schedule_order[0]
    service_head_arrival = return_by_id[service_head]["arrival_ordinal"]
    overtake_counts_after: dict[str, int] = {}
    for return_id in fifo_order:
        if return_id == service_head:
            continue
        prior = overtake_counts_before[return_id]
        if return_by_id[return_id]["arrival_ordinal"] < service_head_arrival:
            prior += 1
        require(prior <= maximum_overtakes, "return queue reducer: maximum-overtakes fairness violated")
        overtake_counts_after[return_id] = prior

    return {
        "proposal_status": proposal_status,
        "schedule_basis": schedule_basis,
        "schedule_order": schedule_order,
        "forced_head_queue_item_id": forced_head,
        "service_head_queue_item_id": service_head,
        "overtake_counts_after": overtake_counts_after,
    }


def validate_no_other_retry_rotation_release(
    release: dict[str, Any],
    disposition: dict[str, Any],
    pre_reopen_snapshot: dict[str, Any],
    current_snapshot_ordinal: int,
    current_cut_arrival_ordinal: int,
) -> None:
    """Validate the zero-peer rotation branch against one exact prior cut."""
    require(
        release["release_mode"] == "NO_OTHER_ELIGIBLE_READY",
        "retry rotation NO_OTHER: release mode",
    )
    require(
        release["intervening_service_record_ref"] is None
        and release["intervening_queue_item_id"] is None
        and release["intervening_service_ordinal"] is None,
        "retry rotation NO_OTHER: cannot cite an intervening attempt",
    )
    require(
        type(current_snapshot_ordinal) is int and current_snapshot_ordinal > 1,
        "retry rotation NO_OTHER: current snapshot ordinal",
    )
    require(
        disposition["service_ordinal"] == current_snapshot_ordinal - 1
        and pre_reopen_snapshot["service_disposition"] is not None
        and pre_reopen_snapshot["service_disposition"]["service_disposition_receipt_ref"]
        == release["source_service_disposition_receipt_ref"]
        and pre_reopen_snapshot["service_disposition"]["queue_item_id"]
        == disposition["queue_item_id"],
        "retry rotation NO_OTHER: release must immediately follow its exact source disposition",
    )
    require(
        release["pre_reopen_snapshot_id"] == pre_reopen_snapshot["snapshot_id"]
        and release["pre_reopen_snapshot_projection_sha256"]
        == pre_reopen_snapshot["snapshot_projection_sha256"],
        "retry rotation NO_OTHER: exact pre-reopen snapshot head",
    )
    require(
        current_cut_arrival_ordinal == pre_reopen_snapshot["cut_arrival_ordinal"],
        "retry rotation NO_OTHER: unexamined arrival between bound head and reopen",
    )
    other_ready_after_bound_step = [
        ready_id for ready_id in pre_reopen_snapshot["ready_ids"]
        if ready_id != pre_reopen_snapshot["decision"]["service_head_queue_item_id"]
    ]
    require(
        type(release["derived_other_ready_count"]) is int
        and release["derived_other_ready_count"]
        == len(other_ready_after_bound_step)
        == 0,
        "retry rotation NO_OTHER: zero other eligible READY items",
    )


def validate_return_queue(document: Any) -> None:
    top_keys = [
        "schema",
        "fixture_kind",
        "status",
        "claim_ceiling",
        "queue",
        "priority_authorizations",
        "priority_receipts",
        "priority_append_holds",
        "retry_rotation_release_receipts",
        "service_reconciliation_receipts",
        "scheduling_attestations",
        "returns",
        "snapshots",
        "accounting",
    ]
    require_exact_keys(document, top_keys, "return queue")
    require(document["schema"] == "hearthline-plays.return-queue.v2", "return queue: schema")
    require(document["fixture_kind"] == "WHOLLY_SYNTHETIC_STRUCTURE_ONLY", "return queue: fixture kind")
    require(document["status"] == "OFFLINE_REFERENCE_IMPLEMENTED_NOT_WIRED", "return queue: status")
    claim_ceiling = document["claim_ceiling"]
    require(isinstance(claim_ceiling, str) and "not a hosted scheduler" in claim_ceiling, "return queue: claim ceiling")
    require("authority receipt" in claim_ceiling and "external effect" in claim_ceiling, "return queue: authority/effect ceiling")

    queue = document["queue"]
    require_exact_keys(
        queue,
        [
            "queue_id",
            "destination_ref",
            "synchronization_point_ref",
            "profile_ref",
            "profile_epoch",
            "service_epoch",
            "controller_ref",
            "effect_executor_ref",
            "queue_scope",
            "maximum_snapshot_items",
            "external_effect_count",
            "priority_assigner_ref",
            "priority_register_ref",
            "priority_authorization_register_ref",
            "priority_genesis_head_ref",
            "priority_genesis_head_sha256",
            "dispatch_priority_assignment_basis_ref",
            "priority_revision_assignment_basis_ref",
            "unmarked_return_rule",
            "invalid_revision_rule",
            "ambiguous_revision_rule",
            "queue_steward",
            "thulia_non_interference",
            "policy",
        ],
        "return queue control",
    )
    queue_id = queue["queue_id"]
    destination_ref = queue["destination_ref"]
    synchronization_point_ref = queue["synchronization_point_ref"]
    require(isinstance(queue_id, str) and queue_id, "return queue: queue ID")
    require(isinstance(destination_ref, str) and destination_ref, "return queue: destination")
    require(isinstance(synchronization_point_ref, str) and synchronization_point_ref, "return queue: synchronization point")
    profile_ref = queue["profile_ref"]
    profile_epoch = queue["profile_epoch"]
    service_epoch = queue["service_epoch"]
    require(isinstance(profile_ref, str) and profile_ref, "return queue: profile identity")
    require(type(profile_epoch) is int and profile_epoch >= 1, "return queue: profile epoch")
    require(type(service_epoch) is int and service_epoch >= 1, "return queue: service epoch")
    controller_ref = queue["controller_ref"]
    require(isinstance(controller_ref, str) and controller_ref, "return queue: controller")
    require(queue["priority_assigner_ref"] != controller_ref, "return queue: Hearthline assigner and controller persistence roles remain distinct")
    require(queue["effect_executor_ref"] == "UNBOUND", "return queue: effect executor must remain unbound")
    require(queue["queue_scope"] == "HOMECOMING_RETURN_BUNDLES_ONLY", "return queue: scope")
    maximum_snapshot_items = queue["maximum_snapshot_items"]
    require(
        type(maximum_snapshot_items) is int
        and 1 <= maximum_snapshot_items <= MAXIMUM_MORROW_READY_ITEMS,
        "return queue: maximum snapshot items must fit the bounded Morrow view",
    )
    require(type(queue["external_effect_count"]) is int and queue["external_effect_count"] == 0, "return queue: no external effects")
    for field in (
        "priority_assigner_ref",
        "priority_register_ref",
        "priority_authorization_register_ref",
        "priority_genesis_head_ref",
        "priority_genesis_head_sha256",
        "dispatch_priority_assignment_basis_ref",
        "priority_revision_assignment_basis_ref",
    ):
        require(isinstance(queue[field], str) and queue[field], f"return queue: {field}")
    require(queue["priority_assigner_ref"] == "SYNTHETIC_HEARTHLINE_0001", "return queue fixture: priority assigner must be Hearthline")
    require(HEX64.fullmatch(queue["priority_genesis_head_sha256"]) is not None, "return queue: priority genesis digest")
    require(queue["unmarked_return_rule"] == "HOLD_FOR_EXPLICIT_MIGRATION_OR_DISPATCH_MARK", "return queue: unmarked returns fail closed")
    require(queue["invalid_revision_rule"] == "REJECT_WITHOUT_MUTATION_KEEP_LAST_VALID_MARK", "return queue: invalid revision fail closed")
    require(
        queue["ambiguous_revision_rule"]
        == "HOLD_SUBJECT_UNTIL_PRIORITY_LEDGER_RECONCILIATION",
        "return queue: ambiguous priority append must hold the subject",
    )

    steward = queue["queue_steward"]
    steward_keys = [
        "name",
        "identity_ref",
        "legacy_queue_steward_creature_ref",
        "legacy_compatibility_status",
        "manifest_ref",
        "task_ref",
        "control_return_aperture_ref",
        "control_return_profile_ref",
        "control_return_scope",
        "scheduling_view_field_allowlist",
        "implementation_mode",
        "persistent_state_ref",
        "ledger_ref",
        "perch_ref",
        "bridge_gloss_ref",
        "direct_thulia_channel_ref",
        "liveness_contract_ref",
        "role",
        "authority",
        "allowed_output",
        "can_emit_heartbeat",
        "can_read_selected_carry",
        "can_read_homecoming_custody",
        "can_read_thulia_state",
        "can_write_thulia_state",
        "can_invoke_thulia",
        "can_impersonate_thulia",
        "depends_on_thulia",
        "operates_if_thulia_absent",
        "can_enter_data_queue_under_review",
        "can_admit",
        "can_mutate_return",
        "can_select_carry",
        "can_grant_or_renew",
        "can_execute_effect",
    ]
    require_exact_keys(steward, steward_keys, "return queue steward")
    require(steward["name"] == "Morrow", "return queue: named steward")
    require(isinstance(steward["identity_ref"], str) and steward["identity_ref"], "return queue: Morrow identity")
    require(steward["identity_ref"] != controller_ref, "return queue: Morrow and controller identities must remain distinct")
    require(isinstance(steward["legacy_queue_steward_creature_ref"], str) and steward["legacy_queue_steward_creature_ref"], "return queue: legacy steward provenance")
    require(steward["legacy_compatibility_status"] == "DESIGN_HISTORY_ONLY_NOT_RUNTIME_IDENTITY", "return queue: legacy Creature compatibility ceiling")
    require(isinstance(steward["manifest_ref"], str) and steward["manifest_ref"], "return queue: steward manifest")
    require(isinstance(steward["task_ref"], str) and steward["task_ref"], "return queue: steward task")
    require(
        isinstance(steward["control_return_aperture_ref"], str)
        and steward["control_return_aperture_ref"],
        "return queue: steward control-return aperture",
    )
    require(
        isinstance(steward["control_return_profile_ref"], str)
        and steward["control_return_profile_ref"]
        and steward["control_return_profile_ref"] != profile_ref,
        "return queue: steward control return must use a distinct profile",
    )
    require(
        steward["control_return_scope"] == "QUEUE_ORDER_PROPOSAL_ONLY",
        "return queue: steward control-return scope",
    )
    scheduling_view_field_allowlist = [
        "opaque_queue_item_binding",
        "ready_arrival_rank",
        "effective_priority_rank",
        "controller_approved_processing_cost",
        "overtake_count",
    ]
    require(
        steward["scheduling_view_field_allowlist"] == scheduling_view_field_allowlist,
        "return queue: steward scheduling view must use the closed allowlist",
    )
    require(steward["implementation_mode"] == "DETERMINISTIC_STATELESS_FROZEN_INPUT_TO_PROPOSAL", "return queue: Morrow implementation mode")
    for field in (
        "persistent_state_ref",
        "ledger_ref",
        "perch_ref",
        "bridge_gloss_ref",
        "direct_thulia_channel_ref",
        "liveness_contract_ref",
    ):
        require(steward[field] is None, f"return queue: Morrow {field} must remain unbound")
    require(steward["role"] == "TASK_SCOPED_METADATA_ONLY_PURE_PROPOSER", "return queue: steward role")
    require(steward["authority"] == "NONE", "return queue: Morrow has no authority")
    require(steward["allowed_output"] == "QUEUE_ORDER_PROPOSAL_ONLY", "return queue: Morrow output ceiling")
    for field in (
        "can_emit_heartbeat",
        "can_read_selected_carry",
        "can_read_homecoming_custody",
        "can_read_thulia_state",
        "can_write_thulia_state",
        "can_invoke_thulia",
        "can_impersonate_thulia",
        "depends_on_thulia",
        "can_enter_data_queue_under_review",
        "can_admit",
        "can_mutate_return",
        "can_select_carry",
        "can_grant_or_renew",
        "can_execute_effect",
    ):
        require(steward[field] is False, f"return queue: steward {field}")
    require(steward["operates_if_thulia_absent"] is True, "return queue: Morrow must operate if Thulia is absent")

    thulia = queue["thulia_non_interference"]
    require_exact_keys(
        thulia,
        [
            "thulia_ref",
            "state_ref",
            "ledger_ref",
            "perch_ref",
            "bridge_gloss_ref",
            "direct_morrow_channel_ref",
            "can_read_or_set_priority",
            "can_read_scheduling_view",
            "can_write_scheduling_view",
            "can_read_proposal",
            "can_write_proposal",
            "can_read_final_order",
            "can_read_admission_state",
            "can_set_controller_approved_processing_cost",
            "can_set_order",
            "can_admit",
            "can_invoke_morrow",
            "can_impersonate_morrow",
            "depends_on_morrow",
            "operates_if_morrow_absent",
        ],
        "return queue Thulia non-interference",
    )
    for field in ("thulia_ref", "state_ref", "ledger_ref", "perch_ref", "bridge_gloss_ref"):
        require(isinstance(thulia[field], str) and thulia[field], f"return queue: Thulia {field}")
    require(
        len(_canonical_surface_keys({thulia[field] for field in ("thulia_ref", "state_ref", "ledger_ref", "perch_ref", "bridge_gloss_ref")})) == 5,
        "return queue: Thulia identity/state/ledger/Perch/Bridge Gloss remain distinct",
    )
    thulia_refs = {thulia[field] for field in ("thulia_ref", "state_ref", "ledger_ref", "perch_ref", "bridge_gloss_ref")}
    morrow_refs = {
        steward[field]
        for field in (
            "identity_ref",
            "legacy_queue_steward_creature_ref",
            "manifest_ref",
            "task_ref",
            "control_return_aperture_ref",
            "control_return_profile_ref",
        )
    }
    require(len(_canonical_surface_keys(morrow_refs)) == 6, "return queue: Morrow runtime and bounded legacy references remain distinct")
    require(
        not _canonical_surface_keys(thulia_refs).intersection(_canonical_surface_keys(morrow_refs)),
        "return queue: Morrow and Thulia share no canonical identity, state, ledger, Perch, or Bridge Gloss reference",
    )
    require(
        _canonical_surface_key(thulia["thulia_ref"])
        != _canonical_surface_key(controller_ref),
        "return queue: Thulia and controller identities remain distinct",
    )
    require(
        _canonical_surface_key(queue["priority_assigner_ref"])
        not in _canonical_surface_keys(morrow_refs | thulia_refs),
        "return queue: Morrow and Thulia cannot assign or impersonate Hearthline",
    )
    require(thulia["direct_morrow_channel_ref"] is None, "return queue: no direct Morrow-Thulia channel")
    for field in (
        "can_read_or_set_priority",
        "can_read_scheduling_view",
        "can_write_scheduling_view",
        "can_read_proposal",
        "can_write_proposal",
        "can_read_final_order",
        "can_read_admission_state",
        "can_set_controller_approved_processing_cost",
        "can_set_order",
        "can_admit",
        "can_invoke_morrow",
        "can_impersonate_morrow",
        "depends_on_morrow",
    ):
        require(thulia[field] is False, f"return queue: Thulia {field}")
    require(thulia["operates_if_morrow_absent"] is True, "return queue: Thulia must operate if Morrow is absent")

    policy = queue["policy"]
    require_exact_keys(
        policy,
        [
            "policy_ref",
            "maximum_overtakes",
            "invalid_or_absent_proposal",
            "new_arrival_rule",
            "admission_width",
            "revalidate_head_before_admission",
            "failed_or_uncertain_head_rule",
            "maximum_controller_approved_processing_cost",
            "priority_classes",
        ],
        "return queue policy",
    )
    require(policy["policy_ref"] == MORROW_POLICY_REF, "return queue: policy identity")
    maximum_overtakes = policy["maximum_overtakes"]
    require(
        type(maximum_overtakes) is int
        and 1 <= maximum_overtakes <= MAXIMUM_OVERTAKES,
        "return queue: bounded maximum overtakes",
    )
    require(policy["invalid_or_absent_proposal"] == "CONTROLLER_EFFECTIVE_PRIORITY_THEN_FIFO_BY_ARRIVAL", "return queue: priority-aware fallback")
    require(policy["new_arrival_rule"] == "NEXT_SNAPSHOT_ONLY", "return queue: snapshot admission rule")
    require(type(policy["admission_width"]) is int and policy["admission_width"] == 1, "return queue: one head per controller step")
    require(policy["revalidate_head_before_admission"] is True, "return queue: head revalidation")
    require(
        policy["failed_or_uncertain_head_rule"]
        == "ATOMIC_READY_TO_HELD_WITH_SERVICE_DISPOSITION_RETRY_RECEIPT_REQUIRED",
        "return queue: failed or uncertain head must leave READY before another snapshot",
    )
    require(
        policy["maximum_controller_approved_processing_cost"]
        == MAXIMUM_CONTROLLER_APPROVED_PROCESSING_COST,
        "return queue: controller-approved processing cost bound",
    )
    require(policy["priority_classes"] == list(PRIORITY_RANKS), "return queue: priority class order")

    authorizations = document["priority_authorizations"]
    require(isinstance(authorizations, list) and authorizations, "priority authorization register: nonempty array")
    authorization_keys = PRIORITY_AUTHORIZATION_KEYS
    authorization_by_tether: dict[str, dict[str, Any]] = {}
    authorization_unique = {
        "priority_authorization_ref": set(),
        "task_ref": set(),
        "dispatch_ref": set(),
    }
    for index, authorization in enumerate(authorizations, start=1):
        require_exact_keys(authorization, authorization_keys, f"priority authorization {index}")
        tether_ref = authorization["tether_ref"]
        require(isinstance(tether_ref, str) and tether_ref and tether_ref not in authorization_by_tether, f"priority authorization {index}: unique tether")
        authorization_by_tether[tether_ref] = authorization
        for field, seen in authorization_unique.items():
            value = authorization[field]
            require(isinstance(value, str) and value and value not in seen, f"priority authorization {index}: unique {field}")
            seen.add(value)
        require(authorization["queue_id"] == queue_id, f"priority authorization {index}: queue binding")
        require(authorization["profile_ref"] == profile_ref, f"priority authorization {index}: profile binding")
        require(type(authorization["profile_epoch"]) is int and authorization["profile_epoch"] == profile_epoch, f"priority authorization {index}: profile epoch binding")
        require(authorization["policy_ref"] == policy["policy_ref"], f"priority authorization {index}: policy binding")
        require(
            isinstance(authorization["task_tether_core_sha256"], str)
            and HEX64.fullmatch(authorization["task_tether_core_sha256"]) is not None,
            f"priority authorization {index}: TETHER core digest",
        )
        require(authorization["authorized_assigner_ref"] == queue["priority_assigner_ref"], f"priority authorization {index}: Hearthline assignment source")
        require(authorization["recorded_by_controller_ref"] == controller_ref, f"priority authorization {index}: controller persistence")
        ceiling_class = authorization["priority_ceiling_class"]
        require(ceiling_class in PRIORITY_RANKS, f"priority authorization {index}: ceiling class")
        require(
            type(authorization["priority_ceiling_rank"]) is int
            and authorization["priority_ceiling_rank"] == PRIORITY_RANKS[ceiling_class],
            f"priority authorization {index}: ceiling binding",
        )
        require(
            type(authorization["maximum_priority_revisions"]) is int
            and 0 <= authorization["maximum_priority_revisions"] <= MAXIMUM_PRIORITY_REVISIONS,
            f"priority authorization {index}: revision budget",
        )
        for field in ("grant_ref", "scope_ref", "deadline_ref", "budget_ref"):
            require(isinstance(authorization[field], str) and authorization[field], f"priority authorization {index}: {field}")
        require(authorization["priority_is_sequencing_only"] is True, f"priority authorization {index}: priority cannot grant authority")
        require(authorization["external_effect_receipt_ref"] is None, f"priority authorization {index}: external effect forbidden")

    priority_chains = _validate_priority_receipt_ledger(
        document["priority_receipts"],
        controller_ref,
        queue["priority_assigner_ref"],
        queue_id=queue_id,
        profile_ref=profile_ref,
        profile_epoch=profile_epoch,
        policy_ref=policy["policy_ref"],
        dispatch_basis_ref=queue["dispatch_priority_assignment_basis_ref"],
        revision_basis_ref=queue["priority_revision_assignment_basis_ref"],
        priority_genesis_head_ref=queue["priority_genesis_head_ref"],
        priority_genesis_head_sha256=queue["priority_genesis_head_sha256"],
    )
    require(set(priority_chains) == set(authorization_by_tether), "priority register: every chain needs exactly one controller-frozen authorization")
    for tether_ref, chain in priority_chains.items():
        authorization = authorization_by_tether[tether_ref]
        root_mark = chain[0]
        for field in (
            "priority_authorization_ref",
            "task_ref",
            "tether_ref",
            "task_tether_core_sha256",
            "dispatch_ref",
            "priority_ceiling_class",
            "priority_ceiling_rank",
            "maximum_priority_revisions",
            "grant_ref",
            "scope_ref",
            "deadline_ref",
            "budget_ref",
        ):
            require(root_mark[field] == authorization[field], f"priority register {tether_ref}: authorization binding for {field}")

    trusted_priority_context = {
        "controller_ref": controller_ref,
        "priority_assigner_ref": queue["priority_assigner_ref"],
        "queue_id": queue_id,
        "profile_ref": profile_ref,
        "profile_epoch": profile_epoch,
        "policy_ref": policy["policy_ref"],
    }
    priority_append_holds = document["priority_append_holds"]
    require(isinstance(priority_append_holds, list), "priority append holds: expected array")
    priority_append_hold_by_tether: dict[str, dict[str, Any]] = {}
    priority_append_hold_refs: set[str] = set()
    priority_append_attempt_refs: set[str] = set()
    priority_append_idempotency_keys: set[str] = set()
    priority_append_reconciliation_handles: set[str] = set()
    durable_priority_refs = {
        receipt["priority_receipt_ref"] for receipt in document["priority_receipts"]
    }
    durable_priority_idempotency_keys = {
        receipt["idempotency_key"] for receipt in document["priority_receipts"]
    }
    durable_priority_by_ref = {
        receipt["priority_receipt_ref"]: receipt
        for receipt in document["priority_receipts"]
    }
    for index, hold in enumerate(priority_append_holds, start=1):
        label = f"priority append hold {index}"
        _validate_priority_append_hold_record(hold, trusted_priority_context, label)
        tether_ref = hold["tether_ref"]
        require(tether_ref not in priority_append_hold_by_tether, f"{label}: one unresolved append hold per tether")
        priority_append_hold_by_tether[tether_ref] = hold
        for field, seen in (
            ("priority_append_hold_ref", priority_append_hold_refs),
            ("attempted_priority_receipt_ref", priority_append_attempt_refs),
            ("idempotency_key", priority_append_idempotency_keys),
            ("reconciliation_handle", priority_append_reconciliation_handles),
        ):
            value = hold[field]
            require(value not in seen, f"{label}: unique {field}")
            seen.add(value)
        require(hold["priority_append_hold_ref"] not in durable_priority_refs, f"{label}: hold identity cannot alias durable priority receipt")
        require(hold["attempted_priority_receipt_ref"] not in durable_priority_refs, f"{label}: UNKNOWN attempted receipt cannot already be durable")
        require(hold["idempotency_key"] not in durable_priority_idempotency_keys, f"{label}: UNKNOWN attempted idempotency key cannot already be durable")
        authorization = authorization_by_tether.get(tether_ref)
        chain = priority_chains.get(tether_ref)
        require(authorization is not None and chain is not None, f"{label}: known authorized priority tether")
        latest = chain[-1]
        for hold_field, source in (
            ("priority_authorization_ref", authorization["priority_authorization_ref"]),
            ("task_ref", latest["task_ref"]),
            ("task_tether_core_sha256", latest["task_tether_core_sha256"]),
            ("dispatch_ref", latest["dispatch_ref"]),
        ):
            require(
                _canonical_json_bytes(hold[hold_field]) == _canonical_json_bytes(source),
                f"{label}: {hold_field} binding",
            )
        require(
            hold["attempted_revision_ordinal"] == latest["revision_ordinal"] + 1
            and hold["attempted_revision_ordinal"] <= chain[0]["maximum_priority_revisions"]
            and hold["attempted_supersedes_priority_receipt_ref"]
            == latest["priority_receipt_ref"],
            f"{label}: exact authorized predecessor and revision budget",
        )
        observed_global = durable_priority_by_ref.get(hold["observed_priority_ledger_head_ref"])
        require(
            observed_global is not None
            and observed_global["ledger_ordinal"] >= latest["ledger_ordinal"]
            and hold["observed_priority_ledger_head_sha256"]
            == _canonical_json_sha256(observed_global),
            f"{label}: observed global priority-ledger prefix head",
        )

    retry_rotation_releases = document["retry_rotation_release_receipts"]
    require(isinstance(retry_rotation_releases, list), "retry rotation releases: expected array")
    retry_rotation_release_by_ref: dict[str, dict[str, Any]] = {}
    for index, release in enumerate(retry_rotation_releases, start=1):
        label = f"retry rotation release {index}"
        require_exact_keys(release, RETRY_ROTATION_RELEASE_KEYS, label)
        release_ref = release["retry_rotation_release_receipt_ref"]
        require(
            isinstance(release_ref, str)
            and release_ref
            and release_ref not in retry_rotation_release_by_ref,
            f"{label}: unique receipt reference",
        )
        retry_rotation_release_by_ref[release_ref] = release
        for field, expected in (
            ("controller_ref", controller_ref),
            ("queue_id", queue_id),
            ("profile_ref", profile_ref),
            ("profile_epoch", profile_epoch),
            ("service_epoch", service_epoch),
        ):
            require(
                _canonical_json_bytes(release[field]) == _canonical_json_bytes(expected),
                f"{label}: {field} binding",
            )
        for field in (
            "source_service_disposition_receipt_ref",
            "source_reopen_handle",
            "queue_item_id",
        ):
            require(isinstance(release[field], str) and release[field], f"{label}: {field}")
        require(
            release["release_mode"]
            in {"OTHER_ITEM_SERVICE_ATTEMPTED", "NO_OTHER_ELIGIBLE_READY"},
            f"{label}: closed release mode",
        )
        require(
            type(release["preserved_overtake_count"]) is int
            and 0 <= release["preserved_overtake_count"] <= maximum_overtakes,
            f"{label}: preserved overtake count",
        )
        for field in (
            "priority_mutated",
            "authority_mutated",
            "custody_mutated",
            "result_mutated",
            "deadline_mutated",
            "budget_mutated",
        ):
            require(release[field] is False, f"{label}: {field} must remain false")
        require(release["external_effect_receipt_ref"] is None, f"{label}: external effect forbidden")

    service_reconciliations = document["service_reconciliation_receipts"]
    require(isinstance(service_reconciliations, list), "service reconciliations: expected array")
    service_reconciliation_by_ref: dict[str, dict[str, Any]] = {}
    for index, reconciliation in enumerate(service_reconciliations, start=1):
        label = f"service reconciliation {index}"
        require_exact_keys(reconciliation, SERVICE_RECONCILIATION_KEYS, label)
        reconciliation_ref = reconciliation["service_reconciliation_receipt_ref"]
        require(
            isinstance(reconciliation_ref, str)
            and reconciliation_ref
            and reconciliation_ref not in service_reconciliation_by_ref,
            f"{label}: unique receipt reference",
        )
        service_reconciliation_by_ref[reconciliation_ref] = reconciliation
        for field, expected in (
            ("controller_ref", controller_ref),
            ("queue_id", queue_id),
            ("profile_ref", profile_ref),
            ("profile_epoch", profile_epoch),
            ("service_epoch", service_epoch),
        ):
            require(
                _canonical_json_bytes(reconciliation[field])
                == _canonical_json_bytes(expected),
                f"{label}: {field} binding",
            )
        for field in (
            "service_disposition_receipt_ref",
            "queue_item_id",
            "reopen_handle",
            "reconciliation_evidence_ref",
        ):
            require(isinstance(reconciliation[field], str) and reconciliation[field], f"{label}: {field}")
        require(reconciliation["observed_outcome"] == "UNKNOWN", f"{label}: observed UNKNOWN outcome")
        require(
            reconciliation["reconciled_outcome"]
            == "CONFIRMED_NOT_ADMITTED_SAFE_TO_RETRY"
            and reconciliation["retry_permitted"] is True,
            f"{label}: explicit retry-permitting resolved outcome",
        )
        for field in (
            "priority_mutated",
            "authority_mutated",
            "custody_mutated",
            "result_mutated",
            "deadline_mutated",
            "budget_mutated",
        ):
            require(reconciliation[field] is False, f"{label}: {field} must remain false")
        require(reconciliation["external_effect_receipt_ref"] is None, f"{label}: external effect forbidden")

    scheduling_attestations = document["scheduling_attestations"]
    require(isinstance(scheduling_attestations, list) and scheduling_attestations, "return queue: scheduling attestations")
    scheduling_attestation_keys = [
        "scheduling_attestation_ref",
        "queue_id",
        "profile_ref",
        "profile_epoch",
        "policy_ref",
        "recorded_by_controller_ref",
        "task_ref",
        "tether_ref",
        "task_tether_core_sha256",
        "opaque_scheduling_binding",
        "controller_approved_processing_cost",
        "external_effect_receipt_ref",
    ]
    scheduling_attestation_by_ref: dict[str, dict[str, Any]] = {}
    scheduling_attestation_tethers: set[str] = set()
    scheduling_attestation_bindings: set[str] = set()
    for index, attestation in enumerate(scheduling_attestations, start=1):
        require_exact_keys(attestation, scheduling_attestation_keys, f"scheduling attestation {index}")
        attestation_ref = attestation["scheduling_attestation_ref"]
        require(
            isinstance(attestation_ref, str)
            and attestation_ref
            and attestation_ref not in scheduling_attestation_by_ref,
            f"scheduling attestation {index}: unique reference",
        )
        scheduling_attestation_by_ref[attestation_ref] = attestation
        require(attestation["queue_id"] == queue_id, f"scheduling attestation {index}: queue binding")
        require(
            attestation["profile_ref"] == profile_ref
            and type(attestation["profile_epoch"]) is int
            and attestation["profile_epoch"] == profile_epoch
            and attestation["policy_ref"] == policy["policy_ref"],
            f"scheduling attestation {index}: frozen profile/epoch/policy binding",
        )
        require(
            attestation["recorded_by_controller_ref"] == controller_ref,
            f"scheduling attestation {index}: controller-owned cost",
        )
        for field in ("task_ref", "tether_ref", "opaque_scheduling_binding"):
            require(isinstance(attestation[field], str) and attestation[field], f"scheduling attestation {index}: {field}")
        require(
            attestation["tether_ref"] not in scheduling_attestation_tethers,
            f"scheduling attestation {index}: one cost attestation per tether",
        )
        scheduling_attestation_tethers.add(attestation["tether_ref"])
        require(
            attestation["opaque_scheduling_binding"] not in scheduling_attestation_bindings,
            f"scheduling attestation {index}: unique opaque scheduling binding",
        )
        scheduling_attestation_bindings.add(attestation["opaque_scheduling_binding"])
        require(
            isinstance(attestation["task_tether_core_sha256"], str)
            and HEX64.fullmatch(attestation["task_tether_core_sha256"]) is not None,
            f"scheduling attestation {index}: TETHER core digest",
        )
        require(
            type(attestation["controller_approved_processing_cost"]) is int
            and 1 <= attestation["controller_approved_processing_cost"]
            <= policy["maximum_controller_approved_processing_cost"],
            f"scheduling attestation {index}: positive controller-approved cost",
        )
        require(attestation["external_effect_receipt_ref"] is None, f"scheduling attestation {index}: external effect forbidden")

    return_keys = [
        "queue_item_id",
        "return_id",
        "idempotency_key",
        "objective_id",
        "creature_ref",
        "task_ref",
        "tether_ref",
        "task_tether_core_sha256",
        "task_dispatch_ref",
        "dispatch_priority_receipt_ref",
        "dispatch_binding_state",
        "scheduling_binding",
        "scheduling_metadata_provenance_ref",
        "scheduling_metadata_binding",
        "intake_receipt_ref",
        "enqueue_receipt_ref",
        "return_receipt_ref",
        "arrival_ordinal",
        "available_snapshot_ordinal",
        "controller_approved_processing_cost",
        "content_sha256",
        "evaluation_rule_ref",
        "objective_disposition",
        "homecoming_custody_state",
        "carry_state",
        "initial_queue_state",
        "hold_reason",
        "hold_reopen_ref",
        "external_effect_receipt_ref",
    ]
    returns = document["returns"]
    require(isinstance(returns, list) and returns, "return queue: returns")
    return_by_id: dict[str, dict[str, Any]] = {}
    typed_record_refs = (
        [item["priority_authorization_ref"] for item in authorizations]
        + [item["priority_receipt_ref"] for item in document["priority_receipts"]]
        + [item["priority_append_hold_ref"] for item in priority_append_holds]
        + [item["attempted_priority_receipt_ref"] for item in priority_append_holds]
        + [item["retry_rotation_release_receipt_ref"] for item in retry_rotation_releases]
        + [item["service_reconciliation_receipt_ref"] for item in service_reconciliations]
        + [item["scheduling_attestation_ref"] for item in scheduling_attestations]
    )
    require(
        len(typed_record_refs) == len(set(typed_record_refs)),
        "return queue: authorization, priority, append-hold, attempted, and scheduling-attestation record identities must be globally distinct",
    )
    all_receipt_refs: set[str] = set(typed_record_refs)
    unique_fields = {
        "return_id": set(),
        "idempotency_key": set(),
        "objective_id": set(),
        "task_ref": set(),
        "tether_ref": set(),
        "task_dispatch_ref": set(),
        "scheduling_binding": set(),
        "scheduling_metadata_provenance_ref": set(),
        "scheduling_metadata_binding": set(),
        "intake_receipt_ref": set(),
        "enqueue_receipt_ref": set(),
        "return_receipt_ref": set(),
    }
    for index, item in enumerate(returns, start=1):
        require_exact_keys(item, return_keys, f"return queue item {index}")
        queue_item_id = item["queue_item_id"]
        require(isinstance(queue_item_id, str) and queue_item_id, f"return queue item {index}: queue item ID")
        require(queue_item_id not in return_by_id, "return queue: duplicate queue item ID")
        return_by_id[queue_item_id] = item
        require(
            type(item["arrival_ordinal"]) is int and item["arrival_ordinal"] == index,
            f"return queue item {queue_item_id}: controller-linearized arrival ordinal",
        )
        require(type(item["available_snapshot_ordinal"]) is int and item["available_snapshot_ordinal"] >= 1, f"return queue item {queue_item_id}: available snapshot")
        require(
            type(item["controller_approved_processing_cost"]) is int
            and 1 <= item["controller_approved_processing_cost"]
            <= policy["maximum_controller_approved_processing_cost"],
            f"return queue item {queue_item_id}: bounded controller-approved cost",
        )
        require(isinstance(item["content_sha256"], str) and HEX64.fullmatch(item["content_sha256"]) is not None, f"return queue item {queue_item_id}: content hash")
        require(
            isinstance(item["task_tether_core_sha256"], str)
            and HEX64.fullmatch(item["task_tether_core_sha256"]) is not None,
            f"return queue item {queue_item_id}: TETHER core digest",
        )
        for field, seen in unique_fields.items():
            value = item[field]
            require(isinstance(value, str) and value, f"return queue item {queue_item_id}: {field}")
            require(value not in seen, f"return queue: duplicate {field}")
            seen.add(value)
            if field.endswith("receipt_ref"):
                require(value not in all_receipt_refs, f"return queue: receipt reference reused across records ({value})")
                all_receipt_refs.add(value)
        require(isinstance(item["creature_ref"], str) and item["creature_ref"], f"return queue item {queue_item_id}: Creature")
        require(item["creature_ref"] != controller_ref, f"return queue item {queue_item_id}: controller cannot alias a data-return Creature")
        require(item["creature_ref"] != steward["identity_ref"], f"return queue item {queue_item_id}: Morrow cannot enter the data queue under review")
        require(item["creature_ref"] != queue["priority_assigner_ref"], f"return queue item {queue_item_id}: return Creature cannot assign its own priority")
        attestation = scheduling_attestation_by_ref.get(item["scheduling_metadata_provenance_ref"])
        require(attestation is not None, f"return queue item {queue_item_id}: missing controller scheduling attestation")
        for source_field, attestation_field in (
            ("task_ref", "task_ref"),
            ("tether_ref", "tether_ref"),
            ("task_tether_core_sha256", "task_tether_core_sha256"),
            ("scheduling_binding", "opaque_scheduling_binding"),
            ("controller_approved_processing_cost", "controller_approved_processing_cost"),
        ):
            require(
                item[source_field] == attestation[attestation_field],
                f"return queue item {queue_item_id}: controller scheduling attestation {source_field}",
            )
        require(
            item["scheduling_metadata_binding"] == _canonical_json_sha256(attestation),
            f"return queue item {queue_item_id}: scheduling attestation digest",
        )
        chain = priority_chains.get(item["tether_ref"])
        if chain is None:
            require(item["initial_queue_state"] == "HELD", f"return queue item {queue_item_id}: unmarked return cannot be ready")
            require(item["dispatch_priority_receipt_ref"] is None, f"return queue item {queue_item_id}: unmarked legacy receipt must be absent")
            require(
                item["dispatch_binding_state"] == "LEGACY_UNMARKED_HELD_FOR_EXPLICIT_MIGRATION",
                f"return queue item {queue_item_id}: unmarked return needs explicit migration hold",
            )
        else:
            root_mark = chain[0]
            require(root_mark["receipt_kind"] == "DISPATCH_PRIORITY_MARK", f"return queue item {queue_item_id}: priority root kind")
            require(root_mark["task_ref"] == item["task_ref"], f"return queue item {queue_item_id}: priority task binding")
            require(
                root_mark["task_tether_core_sha256"] == item["task_tether_core_sha256"],
                f"return queue item {queue_item_id}: priority TETHER core binding",
            )
            require(root_mark["dispatch_ref"] == item["task_dispatch_ref"], f"return queue item {queue_item_id}: task dispatch binding")
            require(
                item["dispatch_priority_receipt_ref"] == root_mark["priority_receipt_ref"],
                f"return queue item {queue_item_id}: dispatch priority receipt binding",
            )
            require(
                item["dispatch_binding_state"] == "PRIORITY_MARK_BOUND_BEFORE_TASK_RELEASE",
                f"return queue item {queue_item_id}: dispatch must be marked before release",
            )
        rule = item["evaluation_rule_ref"]
        disposition = item["objective_disposition"]
        require(isinstance(rule, str) and rule, f"return queue item {queue_item_id}: evaluation rule")
        require(isinstance(disposition, str) and disposition.startswith(f"{rule}:") and len(disposition) > len(rule) + 1, f"return queue item {queue_item_id}: evaluator-owned disposition")
        require(item["homecoming_custody_state"] == "HOMECOMING:RETURNED", f"return queue item {queue_item_id}: returned custody")
        require(item["carry_state"] == "CARRY:UNSELECTED", f"return queue item {queue_item_id}: carry remains unselected")
        require(item["initial_queue_state"] in {"READY", "HELD"}, f"return queue item {queue_item_id}: initial queue state")
        if item["initial_queue_state"] == "HELD":
            require(isinstance(item["hold_reason"], str) and item["hold_reason"], f"return queue item {queue_item_id}: hold reason")
            require(isinstance(item["hold_reopen_ref"], str) and item["hold_reopen_ref"], f"return queue item {queue_item_id}: hold reopen reference")
        else:
            require(item["hold_reason"] is None, f"return queue item {queue_item_id}: unexpected hold reason")
            require(item["hold_reopen_ref"] is None, f"return queue item {queue_item_id}: unexpected hold reopen reference")
        require(item["external_effect_receipt_ref"] is None, f"return queue item {queue_item_id}: external effect forbidden")

    for tether_ref, hold in priority_append_hold_by_tether.items():
        held_item = next(
            (item for item in returns if item["tether_ref"] == tether_ref),
            None,
        )
        require(held_item is not None, f"priority append hold {tether_ref}: return subject")
        require(
            held_item["initial_queue_state"] == "HELD"
            and held_item["hold_reason"] == "PRIORITY_APPEND_OUTCOME_UNKNOWN"
            and held_item["hold_reopen_ref"] == hold["reconciliation_handle"],
            f"priority append hold {tether_ref}: UNKNOWN subject must remain controller-held",
        )
    for release_ref, release in retry_rotation_release_by_ref.items():
        require(
            release["queue_item_id"] in return_by_id,
            f"retry rotation release {release_ref}: known queue subject",
        )

    snapshots = document["snapshots"]
    require(isinstance(snapshots, list) and snapshots, "return queue: snapshots")
    admitted_ids: list[str] = []
    admission_snapshot_by_id: dict[str, int] = {}
    admission_receipts: list[str] = []
    order_receipts: list[str] = []
    snapshot_ids: list[str] = []
    proposal_refs: list[str] = []
    morrow_cut_bindings: set[str] = set()
    morrow_item_bindings: set[str] = set()
    morrow_dynamic_bindings: set[str] = set()
    service_held_ids: set[str] = set()
    service_disposition_by_ref: dict[str, dict[str, Any]] = {}
    service_attempt_by_ref: dict[str, dict[str, Any]] = {}
    latest_service_disposition_ref_by_item: dict[str, str] = {}
    service_disposition_refs: set[str] = set()
    service_readiness_refs: set[str] = set()
    service_reopen_handles: set[str] = set()
    reopened_service_disposition_refs: set[str] = set()
    used_retry_rotation_release_refs: set[str] = set()
    used_service_reconciliation_refs: set[str] = set()
    first_visible_snapshot: dict[str, int] = {}
    first_priority_receipt_snapshot: dict[str, int] = {}
    prior_after: dict[str, int] = {}
    prior_cut = 0
    prior_priority_cut = 0
    snapshot_keys = [
        "queue_id",
        "destination_ref",
        "synchronization_point_ref",
        "snapshot_id",
        "snapshot_ordinal",
        "profile_ref",
        "profile_epoch",
        "service_epoch",
        "policy_ref",
        "maximum_overtakes",
        "maximum_snapshot_items",
        "priority_ledger_cut_ordinal",
        "morrow_invocation_cut_binding",
        "cut_arrival_ordinal",
        "visible_ids",
        "ready_ids",
        "held_ids",
        "previously_admitted_ids",
        "overtake_counts_before",
        "effective_priority_marks",
        "morrow_ready_bindings",
        "snapshot_projection_sha256",
        "proposal",
        "decision",
        "admission",
        "service_disposition",
        "service_reopen_receipts",
    ]
    projection_fields = [
        "objective_id",
        "creature_ref",
        "task_ref",
        "tether_ref",
        "task_tether_core_sha256",
        "task_dispatch_ref",
        "dispatch_priority_receipt_ref",
        "intake_receipt_ref",
        "enqueue_receipt_ref",
        "return_receipt_ref",
        "content_sha256",
        "evaluation_rule_ref",
        "objective_disposition",
        "homecoming_custody_state",
        "carry_state",
    ]
    for snapshot_index, snapshot in enumerate(snapshots, start=1):
        require_exact_keys(snapshot, snapshot_keys, f"return queue snapshot {snapshot_index}")
        require(snapshot["queue_id"] == queue_id, f"return queue snapshot {snapshot_index}: queue identity")
        require(snapshot["destination_ref"] == destination_ref, f"return queue snapshot {snapshot_index}: destination identity")
        require(snapshot["synchronization_point_ref"] == synchronization_point_ref, f"return queue snapshot {snapshot_index}: synchronization point identity")
        snapshot_id = snapshot["snapshot_id"]
        require(isinstance(snapshot_id, str) and snapshot_id and snapshot_id not in snapshot_ids, f"return queue snapshot {snapshot_index}: unique snapshot ID")
        snapshot_ids.append(snapshot_id)
        require(
            type(snapshot["snapshot_ordinal"]) is int
            and snapshot["snapshot_ordinal"] == snapshot_index,
            f"return queue snapshot {snapshot_index}: ordinal",
        )
        require(snapshot["profile_ref"] == profile_ref, f"return queue snapshot {snapshot_index}: profile identity")
        require(type(snapshot["profile_epoch"]) is int and snapshot["profile_epoch"] == profile_epoch, f"return queue snapshot {snapshot_index}: profile epoch")
        require(type(snapshot["service_epoch"]) is int and snapshot["service_epoch"] == service_epoch, f"return queue snapshot {snapshot_index}: service epoch")
        require(snapshot["policy_ref"] == policy["policy_ref"], f"return queue snapshot {snapshot_index}: policy identity")
        require(snapshot["maximum_overtakes"] == maximum_overtakes, f"return queue snapshot {snapshot_index}: maximum-overtakes binding")
        require(snapshot["maximum_snapshot_items"] == maximum_snapshot_items, f"return queue snapshot {snapshot_index}: maximum-snapshot-items binding")
        require(
            _is_safe_opaque_token(snapshot["morrow_invocation_cut_binding"])
            and _canonical_surface_key(snapshot["morrow_invocation_cut_binding"])
            not in _canonical_surface_keys(morrow_cut_bindings),
            f"return queue snapshot {snapshot_index}: opaque Morrow invocation cut binding",
        )
        require(
            _canonical_surface_key(snapshot["morrow_invocation_cut_binding"])
            not in _canonical_surface_keys(morrow_dynamic_bindings),
            f"return queue snapshot {snapshot_index}: opaque Morrow invocation cut binding",
        )
        morrow_cut_bindings.add(snapshot["morrow_invocation_cut_binding"])
        morrow_dynamic_bindings.add(snapshot["morrow_invocation_cut_binding"])
        priority_ledger_cut = snapshot["priority_ledger_cut_ordinal"]
        require(
            type(priority_ledger_cut) is int
            and prior_priority_cut <= priority_ledger_cut <= len(document["priority_receipts"]),
            f"return queue snapshot {snapshot_index}: priority ledger cut",
        )
        prior_priority_cut = priority_ledger_cut
        for receipt in document["priority_receipts"][:priority_ledger_cut]:
            first_priority_receipt_snapshot.setdefault(receipt["priority_receipt_ref"], snapshot_index)

        reopen_receipts = snapshot["service_reopen_receipts"]
        require(isinstance(reopen_receipts, list), f"return queue snapshot {snapshot_index}: service reopen receipts")
        require(
            len(reopen_receipts) <= 1,
            f"return queue snapshot {snapshot_index}: at most one atomic service reopen per snapshot",
        )
        for reopen_index, reopen in enumerate(reopen_receipts, start=1):
            require_exact_keys(
                reopen,
                [
                    "readiness_receipt_ref",
                    "service_disposition_receipt_ref",
                    "controller_ref",
                    "queue_id",
                    "snapshot_id",
                    "queue_item_id",
                    "reopen_handle",
                    "remedy_ref",
                    "reconciliation_receipt_ref",
                    "retry_rotation_release_receipt_ref",
                    "revalidation_inputs_ref",
                    "revalidation_result",
                    "status",
                    "external_effect_receipt_ref",
                ],
                f"return queue snapshot {snapshot_index} service reopen {reopen_index}",
            )
            readiness_ref = reopen["readiness_receipt_ref"]
            require(
                isinstance(readiness_ref, str)
                and readiness_ref
                and readiness_ref not in service_readiness_refs
                and readiness_ref not in all_receipt_refs,
                f"return queue snapshot {snapshot_index}: unique readiness receipt",
            )
            service_readiness_refs.add(readiness_ref)
            all_receipt_refs.add(readiness_ref)
            disposition = service_disposition_by_ref.get(reopen["service_disposition_receipt_ref"])
            require(disposition is not None, f"return queue snapshot {snapshot_index}: reopen requires prior Service Disposition")
            require(
                reopen["service_disposition_receipt_ref"]
                not in reopened_service_disposition_refs,
                f"return queue snapshot {snapshot_index}: Service Disposition may be reopened only once",
            )
            require(reopen["controller_ref"] == controller_ref and reopen["queue_id"] == queue_id, f"return queue snapshot {snapshot_index}: controller-owned reopen")
            require(reopen["snapshot_id"] == snapshot["snapshot_id"], f"return queue snapshot {snapshot_index}: reopen snapshot binding")
            queue_item_id = reopen["queue_item_id"]
            require(
                queue_item_id == disposition["queue_item_id"] and queue_item_id in service_held_ids,
                f"return queue snapshot {snapshot_index}: reopen subject must be held by its disposition",
            )
            require(
                latest_service_disposition_ref_by_item.get(queue_item_id)
                == reopen["service_disposition_receipt_ref"],
                f"return queue snapshot {snapshot_index}: reopen must bind the latest unresolved disposition for the subject",
            )
            require(
                reopen["reopen_handle"] == disposition["reopen_handle"],
                f"return queue snapshot {snapshot_index}: reopen handle binding",
            )
            require(
                reopen["remedy_ref"] == disposition["required_remedy_ref"],
                f"return queue snapshot {snapshot_index}: reopen remedy binding",
            )
            require(
                isinstance(reopen["revalidation_inputs_ref"], str)
                and reopen["revalidation_inputs_ref"]
                and reopen["revalidation_result"] == "PASS",
                f"return queue snapshot {snapshot_index}: current readiness revalidation",
            )
            if disposition["outcome"] == "UNKNOWN":
                reconciliation_ref = reopen["reconciliation_receipt_ref"]
                reconciliation = service_reconciliation_by_ref.get(reconciliation_ref)
                require(
                    isinstance(reconciliation_ref, str)
                    and reconciliation_ref
                    and reconciliation is not None
                    and reconciliation_ref not in used_service_reconciliation_refs,
                    f"return queue snapshot {snapshot_index}: UNKNOWN outcome requires durable reconciliation evidence",
                )
                require(
                    reconciliation["controller_ref"] == controller_ref
                    and reconciliation["queue_id"] == queue_id
                    and reconciliation["profile_ref"] == profile_ref
                    and type(reconciliation["profile_epoch"]) is int
                    and reconciliation["profile_epoch"] == profile_epoch
                    and type(reconciliation["service_epoch"]) is int
                    and reconciliation["service_epoch"] == service_epoch,
                    f"return queue snapshot {snapshot_index}: controller-owned service reconciliation",
                )
                require(
                    reconciliation["service_disposition_receipt_ref"]
                    == disposition["service_disposition_receipt_ref"]
                    and reconciliation["queue_item_id"] == queue_item_id
                    and reconciliation["reopen_handle"] == disposition["reopen_handle"]
                    and reconciliation["observed_outcome"] == disposition["outcome"]
                    and reconciliation["reconciled_outcome"]
                    == "CONFIRMED_NOT_ADMITTED_SAFE_TO_RETRY"
                    and reconciliation["retry_permitted"] is True,
                    f"return queue snapshot {snapshot_index}: service reconciliation source and outcome binding",
                )
                used_service_reconciliation_refs.add(reconciliation_ref)
                expected_reopen_status = "READY_REOPENED_AFTER_DURABLE_RECONCILIATION"
            else:
                require(
                    reopen["reconciliation_receipt_ref"] is None,
                    f"return queue snapshot {snapshot_index}: FAILED outcome does not invent reconciliation evidence",
                )
                expected_reopen_status = "READY_REOPENED_AFTER_CONTROLLER_REMEDY"
            release_ref = reopen["retry_rotation_release_receipt_ref"]
            release = retry_rotation_release_by_ref.get(release_ref)
            require(
                release is not None
                and release_ref not in used_retry_rotation_release_refs,
                f"return queue snapshot {snapshot_index}: unique controller Retry Rotation Release Receipt",
            )
            require(
                release["source_service_disposition_receipt_ref"]
                == reopen["service_disposition_receipt_ref"]
                and release["source_reopen_handle"] == disposition["reopen_handle"]
                and release["queue_item_id"] == queue_item_id,
                f"return queue snapshot {snapshot_index}: retry rotation subject/disposition binding",
            )
            preserved_disposition_counts = {
                item["queue_item_id"]: item["count"]
                for item in disposition["overtake_counts_after"]
            }
            require(
                release["preserved_overtake_count"]
                == preserved_disposition_counts[queue_item_id]
                == prior_after.get(queue_item_id),
                f"return queue snapshot {snapshot_index}: retry rotation cannot reset or increment the held subject's overtakes",
            )
            if release["release_mode"] == "OTHER_ITEM_SERVICE_ATTEMPTED":
                intervening_ref = release["intervening_service_record_ref"]
                intervening = service_attempt_by_ref.get(intervening_ref)
                require(intervening is not None, f"return queue snapshot {snapshot_index}: retry rotation requires a prior typed service attempt")
                require(
                    release["intervening_queue_item_id"]
                    == intervening["queue_item_id"]
                    and intervening["queue_item_id"] != queue_item_id
                    and type(release["intervening_service_ordinal"]) is int
                    and release["intervening_service_ordinal"]
                    == intervening["service_ordinal"]
                    and disposition["service_ordinal"]
                    < intervening["service_ordinal"]
                    < snapshot_index,
                    f"return queue snapshot {snapshot_index}: another item must receive a later service attempt before retry",
                )
                require(
                    release["pre_reopen_snapshot_id"] is None
                    and release["pre_reopen_snapshot_projection_sha256"] is None
                    and release["derived_other_ready_count"] is None,
                    f"return queue snapshot {snapshot_index}: OTHER_ITEM mode fields",
                )
            else:
                require(snapshot_index > 1, f"return queue snapshot {snapshot_index}: retry release needs a prior snapshot head")
                validate_no_other_retry_rotation_release(
                    release,
                    disposition,
                    snapshots[snapshot_index - 2],
                    snapshot_index,
                    snapshot["cut_arrival_ordinal"],
                )
            require(reopen["status"] == expected_reopen_status, f"return queue snapshot {snapshot_index}: reopen status")
            require(reopen["external_effect_receipt_ref"] is None, f"return queue snapshot {snapshot_index}: reopen external effect")
            used_retry_rotation_release_refs.add(release_ref)
            reopened_service_disposition_refs.add(reopen["service_disposition_receipt_ref"])
            service_held_ids.remove(queue_item_id)
        cut = snapshot["cut_arrival_ordinal"]
        require(type(cut) is int and prior_cut <= cut <= len(returns), f"return queue snapshot {snapshot_index}: cut")
        require(cut > 0, f"return queue snapshot {snapshot_index}: nonempty cut")
        prior_cut = cut
        visible = [
            item for item in returns
            if item["arrival_ordinal"] <= cut
        ]
        expected_visible = [item["queue_item_id"] for item in visible]
        expected_terminal = [queue_item_id for queue_item_id in admitted_ids if queue_item_id in expected_visible]
        pending = [item for item in visible if item["queue_item_id"] not in admitted_ids]
        expected_ready = [
            item["queue_item_id"] for item in pending
            if item["initial_queue_state"] == "READY"
            and item["queue_item_id"] not in service_held_ids
        ]
        expected_held = [
            item["queue_item_id"] for item in pending
            if item["initial_queue_state"] == "HELD"
            or item["queue_item_id"] in service_held_ids
        ]
        visible_ids = _unique_string_ids(snapshot["visible_ids"], f"return queue snapshot {snapshot_index} visible")
        ready_ids = _unique_string_ids(snapshot["ready_ids"], f"return queue snapshot {snapshot_index} ready")
        held_ids = _unique_string_ids(snapshot["held_ids"], f"return queue snapshot {snapshot_index} held")
        terminal_ids = _unique_string_ids(
            snapshot["previously_admitted_ids"],
            f"return queue snapshot {snapshot_index} previously admitted",
        )
        require(visible_ids == expected_visible, f"return queue snapshot {snapshot_index}: frozen visibility")
        require(ready_ids == expected_ready, f"return queue snapshot {snapshot_index}: ready IDs must follow intake order")
        require(held_ids == expected_held, f"return queue snapshot {snapshot_index}: held returns must remain visible")
        require(terminal_ids == expected_terminal, f"return queue snapshot {snapshot_index}: prior admissions stay visible without implying terminality")
        require(
            len(ready_ids) + len(held_ids) <= maximum_snapshot_items,
            f"return queue snapshot {snapshot_index}: pending capacity",
        )
        require(
            set(visible_ids) == set(ready_ids + held_ids + terminal_ids)
            and len(visible_ids) == len(ready_ids + held_ids + terminal_ids),
            f"return queue snapshot {snapshot_index}: visible partition conservation",
        )
        ready_binding_rows = snapshot["morrow_ready_bindings"]
        require(isinstance(ready_binding_rows, list), f"return queue snapshot {snapshot_index}: Morrow binding rows")
        require(
            [row.get("queue_item_id") for row in ready_binding_rows] == ready_ids,
            f"return queue snapshot {snapshot_index}: invocation bindings must follow ready order",
        )
        for row_index, row in enumerate(ready_binding_rows, start=1):
            require_exact_keys(
                row,
                ["queue_item_id", "opaque_queue_item_binding"],
                f"return queue snapshot {snapshot_index} Morrow binding {row_index}",
            )
            binding = row["opaque_queue_item_binding"]
            require(
                _is_safe_opaque_token(binding)
                and _canonical_surface_key(binding)
                not in _canonical_surface_keys(morrow_item_bindings),
                f"return queue snapshot {snapshot_index}: Morrow item binding must be fresh per invocation",
            )
            require(
                _canonical_surface_key(binding)
                not in _canonical_surface_keys(morrow_dynamic_bindings),
                f"return queue snapshot {snapshot_index}: Morrow item binding cannot alias any cut or item binding",
            )
            morrow_item_bindings.add(binding)
            morrow_dynamic_bindings.add(binding)
        for queue_item_id in visible_ids:
            first_visible_snapshot.setdefault(queue_item_id, snapshot_index)
        require(
            all(item["arrival_ordinal"] > cut for item in returns if item["queue_item_id"] not in visible_ids),
            f"return queue snapshot {snapshot_index}: future arrival leaked into frozen visibility",
        )

        pending_ids = [item["queue_item_id"] for item in pending]
        expected_priority_marks: list[dict[str, Any]] = []
        effective_priority_ranks: dict[str, int] = {}
        for queue_item_id in pending_ids:
            return_item = return_by_id[queue_item_id]
            chain = priority_chains.get(return_item["tether_ref"])
            if chain is None:
                require(queue_item_id in held_ids, f"return queue snapshot {snapshot_index}: unmarked return leaked into ready view")
                continue
            eligible_marks = [
                receipt
                for receipt in chain
                if receipt["ledger_ordinal"] <= priority_ledger_cut
            ]
            require(
                eligible_marks,
                f"return queue snapshot {snapshot_index}: unmarked return must remain held for migration",
            )
            effective_mark = eligible_marks[-1]
            expected_priority_marks.append({
                "queue_item_id": queue_item_id,
                "priority_receipt_ref": effective_mark["priority_receipt_ref"],
                "priority_class": effective_mark["priority_class"],
                "priority_rank": effective_mark["priority_rank"],
                "scheduling_mark_binding": effective_mark["scheduling_mark_binding"],
            })
            if queue_item_id in ready_ids:
                effective_priority_ranks[queue_item_id] = effective_mark["priority_rank"]
        require(
            snapshot["effective_priority_marks"] == expected_priority_marks,
            f"return queue snapshot {snapshot_index}: effective priority marks must follow the frozen controller ledger cut",
        )

        counts_before = _overtake_counts(
            snapshot["overtake_counts_before"],
            ready_ids,
            f"return queue snapshot {snapshot_index} overtake before",
        )
        expected_before = {
            return_id: prior_after.get(return_id, 0)
            for return_id in ready_ids
        }
        if snapshot_index == 1:
            require(all(count == 0 for count in counts_before.values()), "return queue: first snapshot overtakes start at zero")
        require(counts_before == expected_before, f"return queue snapshot {snapshot_index}: persisted overtake counts")
        require(
            snapshot["snapshot_projection_sha256"]
            == return_queue_snapshot_sha256(snapshot, return_by_id),
            f"return queue snapshot {snapshot_index}: stale or mutated controller snapshot projection",
        )

        ready_returns = [return_by_id[return_id] for return_id in ready_ids]
        binding_to_queue_item = {
            item["opaque_queue_item_binding"]: item["queue_item_id"]
            for item in ready_binding_rows
        }
        priority_state_by_id = {
            item["queue_item_id"]: item
            for item in snapshot["effective_priority_marks"]
        }
        proposal = snapshot["proposal"]
        mapped_proposal_order: Any = None
        if proposal is not None:
            require_exact_keys(
                proposal,
                ["proposal_ref", "morrow_output"],
                f"return queue snapshot {snapshot_index} proposal envelope",
            )
            proposal_ref = proposal["proposal_ref"]
            require(
                isinstance(proposal_ref, str)
                and proposal_ref
                and proposal_ref not in proposal_refs
                and proposal_ref not in all_receipt_refs,
                f"return queue snapshot {snapshot_index}: unambiguous proposal reference",
            )
            proposal_refs.append(proposal_ref)
            all_receipt_refs.add(proposal_ref)
            output = proposal["morrow_output"]
            if (
                isinstance(output, dict)
                and output.get("schema")
                == "hearthline-plays.morrow-invalid-output-capture.v1"
            ):
                require_exact_keys(
                    output,
                    [
                        "schema",
                        "status",
                        "invocation_cut_binding",
                        "scheduling_view_sha256",
                        "policy_ref",
                        "bounded_raw_output_sha256",
                        "bounded_raw_output_byte_count",
                        "failure_code",
                        "raw_output_retained",
                    ],
                    f"return queue snapshot {snapshot_index} invalid Morrow output capture",
                )
                require(
                    output["status"]
                    == "INVALID_UNTRUSTED_OUTPUT_CAPTURED_FOR_FALLBACK",
                    f"return queue snapshot {snapshot_index}: invalid-output capture status",
                )
                require(
                    output["invocation_cut_binding"]
                    == snapshot["morrow_invocation_cut_binding"]
                    and output["policy_ref"] == policy["policy_ref"]
                    and output["scheduling_view_sha256"]
                    == return_queue_scheduling_view_sha256(snapshot, return_by_id),
                    f"return queue snapshot {snapshot_index}: invalid-output capture context binding",
                )
                require(
                    isinstance(output["bounded_raw_output_sha256"], str)
                    and HEX64.fullmatch(output["bounded_raw_output_sha256"])
                    is not None
                    and type(output["bounded_raw_output_byte_count"]) is int
                    and 0 <= output["bounded_raw_output_byte_count"] <= 1_000_000,
                    f"return queue snapshot {snapshot_index}: bounded invalid-output evidence",
                )
                require(
                    output["failure_code"]
                    in {
                        "MALFORMED",
                        "STALE",
                        "REPLAYED",
                        "UNKNOWN_BINDING",
                        "INCOMPLETE_OR_DUPLICATE_ORDER",
                        "POLICY_MISMATCH",
                    }
                    and output["raw_output_retained"] is False,
                    f"return queue snapshot {snapshot_index}: closed invalid-output classification",
                )
                mapped_proposal_order = None
            else:
                mapped_proposal_order = map_untrusted_morrow_output(
                    output,
                    snapshot["morrow_invocation_cut_binding"],
                    return_queue_scheduling_view_sha256(snapshot, return_by_id),
                    policy["policy_ref"],
                    binding_to_queue_item,
                    expected_morrow_binding_order(snapshot, return_by_id),
                )
                require(
                    mapped_proposal_order is not None,
                    f"return queue snapshot {snapshot_index}: malformed/stale Morrow output must be normalized to a closed invalid-output capture before durable recording",
                )
        reduced = reduce_return_queue_snapshot(
            ready_returns,
            counts_before,
            effective_priority_ranks,
            mapped_proposal_order,
            maximum_overtakes,
        )

        decision = snapshot["decision"]
        require_exact_keys(
            decision,
            [
                "controller_ref",
                "queue_id",
                "profile_ref",
                "profile_epoch",
                "service_epoch",
                "snapshot_id",
                "proposal_validation",
                "controller_disposition",
                "schedule_basis",
                "schedule_order",
                "forced_head_queue_item_id",
                "order_receipt_ref",
                "service_head_queue_item_id",
            ],
            f"return queue snapshot {snapshot_index} decision",
        )
        require(decision["controller_ref"] == controller_ref, f"return queue snapshot {snapshot_index}: controller-only order")
        require(decision["queue_id"] == queue_id, f"return queue snapshot {snapshot_index}: order queue identity")
        require(decision["profile_ref"] == profile_ref, f"return queue snapshot {snapshot_index}: order profile identity")
        require(type(decision["profile_epoch"]) is int and decision["profile_epoch"] == profile_epoch, f"return queue snapshot {snapshot_index}: order profile epoch")
        require(type(decision["service_epoch"]) is int and decision["service_epoch"] == service_epoch, f"return queue snapshot {snapshot_index}: order service epoch")
        require(decision["snapshot_id"] == snapshot_id, f"return queue snapshot {snapshot_index}: order snapshot identity")
        expected_proposal_validation = (
            "VALID_EXACT_READY_PERMUTATION_AND_POLICY"
            if reduced["proposal_status"] == "ACCEPTED_EXACT_PRIORITY_COST_FAIRNESS_PERMUTATION"
            else "INVALID_OR_ABSENT_USED_CONTROLLER_PRIORITY_FIFO_FALLBACK"
        )
        expected_controller_disposition = (
            "ENFORCE_HEAD_MAXIMUM_OVERTAKES"
            if reduced["forced_head_queue_item_id"] is not None
            else (
                "USE_VALID_PROPOSAL"
                if reduced["proposal_status"] == "ACCEPTED_EXACT_PRIORITY_COST_FAIRNESS_PERMUTATION"
                else "USE_CONTROLLER_PRIORITY_FIFO_FALLBACK"
            )
        )
        require(decision["proposal_validation"] == expected_proposal_validation, f"return queue snapshot {snapshot_index}: proposal validation")
        require(decision["controller_disposition"] == expected_controller_disposition, f"return queue snapshot {snapshot_index}: controller disposition")
        for field in (
            "schedule_basis",
            "schedule_order",
            "forced_head_queue_item_id",
            "service_head_queue_item_id",
        ):
            require(decision[field] == reduced[field], f"return queue snapshot {snapshot_index}: deterministic {field}")
        schedule_ids = _unique_string_ids(decision["schedule_order"], f"return queue snapshot {snapshot_index} schedule")
        require(set(schedule_ids) == set(ready_ids), f"return queue snapshot {snapshot_index}: schedule must be exact ready permutation")
        require(decision["service_head_queue_item_id"] == schedule_ids[0], f"return queue snapshot {snapshot_index}: service head must be schedule head")
        order_receipt_ref = decision["order_receipt_ref"]
        require(isinstance(order_receipt_ref, str) and order_receipt_ref and order_receipt_ref not in order_receipts, f"return queue snapshot {snapshot_index}: unique order receipt")
        require(order_receipt_ref not in all_receipt_refs, f"return queue snapshot {snapshot_index}: order receipt must be a distinct record")
        order_receipts.append(order_receipt_ref)
        all_receipt_refs.add(order_receipt_ref)

        admission = snapshot["admission"]
        service_disposition = snapshot["service_disposition"]
        require(
            (admission is None) != (service_disposition is None),
            f"return queue snapshot {snapshot_index}: exactly one admission or Service Disposition is required",
        )
        if admission is None:
            require_exact_keys(
                service_disposition,
                [
                    "service_disposition_receipt_ref",
                    "controller_ref",
                    "queue_id",
                    "profile_ref",
                    "profile_epoch",
                    "service_epoch",
                    "snapshot_id",
                    "order_receipt_ref",
                    "service_ordinal",
                    "queue_item_id",
                    "outcome",
                    "next_state",
                    "blocker_ref",
                    "required_remedy_ref",
                    "reopen_handle",
                    "overtake_counts_before",
                    "overtake_counts_after",
                    "reopen_requires_retry_receipt",
                    "reconciliation_required",
                    "retry_receipt_ref",
                    "external_effect_receipt_ref",
                ],
                f"return queue snapshot {snapshot_index} Service Disposition",
            )
            disposition_ref = service_disposition["service_disposition_receipt_ref"]
            require(
                isinstance(disposition_ref, str)
                and disposition_ref
                and disposition_ref not in service_disposition_refs
                and disposition_ref not in all_receipt_refs,
                f"return queue snapshot {snapshot_index}: unique Service Disposition receipt",
            )
            service_disposition_refs.add(disposition_ref)
            all_receipt_refs.add(disposition_ref)
            require(
                service_disposition["controller_ref"] == controller_ref
                and service_disposition["queue_id"] == queue_id
                and service_disposition["profile_ref"] == profile_ref
                and type(service_disposition["profile_epoch"]) is int
                and service_disposition["profile_epoch"] == profile_epoch
                and type(service_disposition["service_epoch"]) is int
                and service_disposition["service_epoch"] == service_epoch,
                f"return queue snapshot {snapshot_index}: controller-owned Service Disposition",
            )
            require(
                service_disposition["snapshot_id"] == snapshot_id
                and service_disposition["order_receipt_ref"] == order_receipt_ref
                and type(service_disposition["service_ordinal"]) is int
                and service_disposition["service_ordinal"] == snapshot_index,
                f"return queue snapshot {snapshot_index}: Service Disposition cut/order binding",
            )
            service_head = reduced["service_head_queue_item_id"]
            require(service_disposition["queue_item_id"] == service_head, f"return queue snapshot {snapshot_index}: disposition must remove the selected READY head")
            outcome = service_disposition["outcome"]
            require(outcome in {"FAILED", "UNKNOWN"}, f"return queue snapshot {snapshot_index}: disposition outcome")
            expected_next_state = (
                "HELD_SERVICE_REMEDY_REQUIRED"
                if outcome == "FAILED"
                else "SERVICE_OUTCOME_UNKNOWN_RECONCILIATION_REQUIRED"
            )
            require(service_disposition["next_state"] == expected_next_state, f"return queue snapshot {snapshot_index}: uncertainty-preserving disposition state")
            for field in ("blocker_ref", "required_remedy_ref", "reopen_handle"):
                require(
                    isinstance(service_disposition[field], str)
                    and service_disposition[field],
                    f"return queue snapshot {snapshot_index}: Service Disposition {field}",
                )
            require(
                service_disposition["reopen_handle"] not in service_reopen_handles,
                f"return queue snapshot {snapshot_index}: unique Service Disposition reopen handle",
            )
            service_reopen_handles.add(service_disposition["reopen_handle"])
            require(service_disposition["reopen_requires_retry_receipt"] is True, f"return queue snapshot {snapshot_index}: retry receipt required")
            require(service_disposition["reconciliation_required"] is (outcome == "UNKNOWN"), f"return queue snapshot {snapshot_index}: UNKNOWN requires reconciliation")
            require(service_disposition["retry_receipt_ref"] is None, f"return queue snapshot {snapshot_index}: disposition cannot self-reopen")
            require(service_disposition["external_effect_receipt_ref"] is None, f"return queue snapshot {snapshot_index}: disposition external effect")
            disposition_before = _overtake_counts(
                service_disposition["overtake_counts_before"],
                ready_ids,
                f"return queue snapshot {snapshot_index} disposition overtake before",
            )
            require(disposition_before == counts_before, f"return queue snapshot {snapshot_index}: disposition pre-overtake binding")
            disposition_after = _overtake_counts(
                service_disposition["overtake_counts_after"],
                ready_ids,
                f"return queue snapshot {snapshot_index} disposition overtake after",
            )
            require(
                disposition_after == counts_before,
                f"return queue snapshot {snapshot_index}: failed or uncertain service cannot increment or reset overtakes",
            )
            prior_after = {
                **{
                    queue_item_id: count
                    for queue_item_id, count in prior_after.items()
                    if queue_item_id not in ready_ids
                },
                **disposition_after,
            }
            service_held_ids.add(service_head)
            service_disposition_by_ref[disposition_ref] = service_disposition
            latest_service_disposition_ref_by_item[service_head] = disposition_ref
            service_attempt_by_ref[disposition_ref] = {
                "record_kind": "SERVICE_DISPOSITION",
                "queue_item_id": service_head,
                "service_ordinal": snapshot_index,
            }
            continue
        require_exact_keys(
            admission,
            [
                "admission_receipt_ref",
                "controller_ref",
                "queue_id",
                "profile_ref",
                "profile_epoch",
                "service_epoch",
                "snapshot_id",
                "order_receipt_ref",
                "service_ordinal",
                "queue_item_id",
                "return_id",
                *projection_fields,
                "effective_priority_receipt_ref",
                "effective_priority_class",
                "effective_priority_rank",
                "scheduling_mark_binding",
                "overtake_counts_before",
                "overtake_counts_after",
                "revalidation",
                "custody_reconciliation_performed",
                "authority_or_grant_mutated",
                "validity_or_status_mutated",
                "carry_mutated",
                "external_effect_receipt_ref",
            ],
            f"return queue snapshot {snapshot_index} admission",
        )
        receipt_ref = admission["admission_receipt_ref"]
        require(isinstance(receipt_ref, str) and receipt_ref and receipt_ref not in admission_receipts, f"return queue snapshot {snapshot_index}: unique admission receipt")
        require(receipt_ref not in all_receipt_refs, f"return queue snapshot {snapshot_index}: admission receipt must be distinct from order and intake receipts")
        admission_receipts.append(receipt_ref)
        all_receipt_refs.add(receipt_ref)
        require(admission["controller_ref"] == controller_ref, f"return queue snapshot {snapshot_index}: controller-only admission")
        require(admission["queue_id"] == queue_id, f"return queue snapshot {snapshot_index}: admission queue identity")
        require(admission["profile_ref"] == profile_ref, f"return queue snapshot {snapshot_index}: admission profile identity")
        require(type(admission["profile_epoch"]) is int and admission["profile_epoch"] == profile_epoch, f"return queue snapshot {snapshot_index}: admission profile epoch")
        require(type(admission["service_epoch"]) is int and admission["service_epoch"] == service_epoch, f"return queue snapshot {snapshot_index}: admission service epoch")
        require(admission["snapshot_id"] == snapshot_id, f"return queue snapshot {snapshot_index}: admission snapshot identity")
        require(admission["order_receipt_ref"] == order_receipt_ref, f"return queue snapshot {snapshot_index}: admission order receipt binding")
        admitted_id = reduced["service_head_queue_item_id"]
        require(
            type(admission["service_ordinal"]) is int
            and admission["service_ordinal"] == snapshot_index,
            f"return queue snapshot {snapshot_index}: service ordinal",
        )
        require(admission["queue_item_id"] == admitted_id, f"return queue snapshot {snapshot_index}: admission queue identity")
        source = return_by_id[admitted_id]
        require(admission["return_id"] == source["return_id"], f"return queue snapshot {snapshot_index}: admission return identity")
        for field in projection_fields:
            require(admission[field] == source[field], f"return queue snapshot {snapshot_index}: {field} mutated")
        effective_admission_mark = priority_state_by_id[admitted_id]
        require(
            admission["effective_priority_receipt_ref"] == effective_admission_mark["priority_receipt_ref"]
            and admission["effective_priority_class"] == effective_admission_mark["priority_class"]
            and type(admission["effective_priority_rank"]) is int
            and admission["effective_priority_rank"] == effective_admission_mark["priority_rank"]
            and admission["scheduling_mark_binding"] == effective_admission_mark["scheduling_mark_binding"],
            f"return queue snapshot {snapshot_index}: admission effective priority evidence",
        )
        receipt_before = _overtake_counts(
            admission["overtake_counts_before"],
            ready_ids,
            f"return queue snapshot {snapshot_index} admission overtake before",
        )
        require(receipt_before == counts_before, f"return queue snapshot {snapshot_index}: admission pre-overtake binding")
        expected_after = reduced["overtake_counts_after"]
        after_ids = [return_id for return_id in ready_ids if return_id != admitted_id]
        counts_after = _overtake_counts(
            admission["overtake_counts_after"],
            after_ids,
            f"return queue snapshot {snapshot_index} admission overtake after",
        )
        require(counts_after == expected_after, f"return queue snapshot {snapshot_index}: deterministic overtake update on admission")
        prior_after = {
            **{
                queue_item_id: count
                for queue_item_id, count in prior_after.items()
                if queue_item_id not in ready_ids
            },
            **counts_after,
        }
        require(admission["revalidation"] == "INTAKE_PROJECTION_MATCH_PASS", f"return queue snapshot {snapshot_index}: revalidation")
        require(
            admission["custody_reconciliation_performed"] is False,
            f"return queue snapshot {snapshot_index}: custody_reconciliation_performed must remain false",
        )
        for field in ("authority_or_grant_mutated", "validity_or_status_mutated", "carry_mutated"):
            require(admission[field] is False, f"return queue snapshot {snapshot_index}: {field}")
        require(admission["external_effect_receipt_ref"] is None, f"return queue snapshot {snapshot_index}: external effect forbidden")
        admitted_ids.append(admitted_id)
        admission_snapshot_by_id[admitted_id] = snapshot_index
        service_attempt_by_ref[receipt_ref] = {
            "record_kind": "ADMISSION",
            "queue_item_id": admitted_id,
            "service_ordinal": snapshot_index,
        }

    tether_to_queue_item = {
        item["tether_ref"]: item["queue_item_id"]
        for item in returns
    }
    for tether_ref, hold in priority_append_hold_by_tether.items():
        held_queue_item_id = tether_to_queue_item[tether_ref]
        observed_ordinal = hold["observed_snapshot_ordinal"]
        require(observed_ordinal <= len(snapshots), f"priority append hold {tether_ref}: observed snapshot outside history")
        if observed_ordinal == 0:
            require(
                hold["observed_snapshot_ref"] == queue["priority_genesis_head_ref"]
                and hold["observed_snapshot_projection_sha256"]
                == queue["priority_genesis_head_sha256"],
                f"priority append hold {tether_ref}: stale priority genesis head",
            )
        else:
            observed = snapshots[observed_ordinal - 1]
            require(
                hold["observed_snapshot_ref"] == observed["snapshot_id"]
                and hold["observed_snapshot_projection_sha256"]
                == observed["snapshot_projection_sha256"],
                f"priority append hold {tether_ref}: stale observed snapshot head",
            )
        for snapshot_index, snapshot in enumerate(snapshots, start=1):
            if held_queue_item_id in snapshot["visible_ids"]:
                require(
                    held_queue_item_id in snapshot["held_ids"]
                    and held_queue_item_id not in snapshot["ready_ids"],
                    f"priority append hold {tether_ref}: unresolved UNKNOWN subject entered READY in snapshot {snapshot_index}",
                )
    for receipt in document["priority_receipts"]:
        first_effective_snapshot = first_priority_receipt_snapshot.get(receipt["priority_receipt_ref"])
        require(
            isinstance(first_effective_snapshot, int)
            and first_effective_snapshot > receipt["observed_snapshot_ordinal"],
            f"priority receipt {receipt['priority_receipt_ref']}: first effect must be a later controller snapshot whose ledger cut includes it",
        )
        observed_ordinal = receipt["observed_snapshot_ordinal"]
        require(observed_ordinal <= len(snapshots), f"priority receipt {receipt['priority_receipt_ref']}: observed snapshot outside history")
        if observed_ordinal == 0:
            require(
                receipt["observed_snapshot_ref"] == queue["priority_genesis_head_ref"]
                and receipt["observed_snapshot_projection_sha256"]
                == queue["priority_genesis_head_sha256"],
                f"priority receipt {receipt['priority_receipt_ref']}: stale priority genesis head",
            )
        else:
            observed = snapshots[observed_ordinal - 1]
            require(
                receipt["observed_snapshot_ref"] == observed["snapshot_id"]
                and receipt["observed_snapshot_projection_sha256"]
                == observed["snapshot_projection_sha256"],
                f"priority receipt {receipt['priority_receipt_ref']}: stale observed snapshot head",
            )
        if receipt["receipt_kind"] == "PRIORITY_REVISION":
            queue_item_id = tether_to_queue_item[receipt["tether_ref"]]
            admission_snapshot = admission_snapshot_by_id.get(queue_item_id)
            require(
                admission_snapshot is None
                or admission_snapshot > observed_ordinal,
                f"priority receipt {receipt['priority_receipt_ref']}: admitted return cannot be revised",
            )
            require(
                admission_snapshot is None
                or first_effective_snapshot <= admission_snapshot,
                f"priority receipt {receipt['priority_receipt_ref']}: revision first included after terminal admission",
            )

    require(
        used_retry_rotation_release_refs == set(retry_rotation_release_by_ref),
        "return queue: every Retry Rotation Release Receipt must be consumed exactly once by a readiness receipt",
    )
    require(
        used_service_reconciliation_refs == set(service_reconciliation_by_ref),
        "return queue: every Service Reconciliation Receipt must be consumed exactly once by an UNKNOWN readiness receipt",
    )

    for queue_item_id, item in return_by_id.items():
        require(
            first_visible_snapshot.get(queue_item_id) == item["available_snapshot_ordinal"],
            f"return queue item {queue_item_id}: first eligible snapshot",
        )

    require(len(snapshots) == 5, "return queue fixture: five self-contained scheduling snapshots")
    require(maximum_overtakes == 2, "return queue fixture: maximum overtakes witness")
    require(
        snapshots[0]["cut_arrival_ordinal"] == 4
        and snapshots[1]["cut_arrival_ordinal"] == len(returns),
        "return queue fixture: post-cut return must enter the immediate successor snapshot",
    )
    first_ready = [return_by_id[queue_item_id] for queue_item_id in snapshots[0]["ready_ids"]]
    require(
        [item["controller_approved_processing_cost"] for item in first_ready] == [10, 1, 2],
        "return queue fixture: controller-approved cost witness",
    )
    first_morrow_output = snapshots[0]["proposal"]["morrow_output"]
    if first_morrow_output["schema"] == "hearthline-plays.morrow-proposal.v1":
        require(
            first_morrow_output["ready_order"]
            == [
                snapshots[0]["morrow_ready_bindings"][1]["opaque_queue_item_binding"],
                snapshots[0]["morrow_ready_bindings"][0]["opaque_queue_item_binding"],
                snapshots[0]["morrow_ready_bindings"][2]["opaque_queue_item_binding"],
            ],
            "return queue fixture: short-medium-old proposal witness",
        )
    require(
        snapshots[2]["decision"]["forced_head_queue_item_id"] == first_ready[0]["queue_item_id"]
        and snapshots[2]["decision"]["controller_disposition"] == "ENFORCE_HEAD_MAXIMUM_OVERTAKES",
        "return queue fixture: persisted fairness forces old routine return ahead of later expedite work",
    )
    require(
        snapshots[2]["service_disposition"]["outcome"] == "UNKNOWN"
        and snapshots[2]["service_disposition"]["next_state"]
        == "SERVICE_OUTCOME_UNKNOWN_RECONCILIATION_REQUIRED"
        and snapshots[2]["service_disposition"]["overtake_counts_after"][0]["count"]
        == maximum_overtakes
        and snapshots[2]["admission"] is None,
        "return queue fixture: due UNKNOWN service outcome leaves READY without losing earned fairness or becoming failure/admission",
    )
    require(
        snapshots[3]["service_disposition"]["queue_item_id"]
        == "synthetic-queue-item-late"
        and snapshots[3]["service_disposition"]["outcome"] == "UNKNOWN"
        and snapshots[3]["admission"] is None
        and snapshots[2]["service_disposition"]["queue_item_id"]
        in snapshots[3]["held_ids"],
        "return queue fixture: another item receives a typed service attempt while the due UNKNOWN subject remains held",
    )
    require(
        snapshots[4]["service_reopen_receipts"][0]["revalidation_result"] == "PASS"
        and snapshots[4]["service_reopen_receipts"][0]["reconciliation_receipt_ref"]
        == "SYNTHETIC_SERVICE_RECONCILIATION_RECEIPT_OLD_0001"
        and snapshots[4]["service_reopen_receipts"][0]["retry_rotation_release_receipt_ref"]
        == "SYNTHETIC_RETRY_ROTATION_RELEASE_OLD_0001"
        and snapshots[4]["overtake_counts_before"][0]["count"] == maximum_overtakes
        and snapshots[4]["decision"]["forced_head_queue_item_id"]
        == snapshots[2]["service_disposition"]["queue_item_id"]
        and snapshots[4]["admission"]["queue_item_id"]
        == snapshots[2]["service_disposition"]["queue_item_id"],
        "return queue fixture: due UNKNOWN subject reopens only after reconciliation, current PASS, and one alternate attempt, then remains fairness-due",
    )

    accounting = document["accounting"]
    require_exact_keys(
        accounting,
        [
            "intake_order",
            "admission_order",
            "ready_residual_ids",
            "held_residual_ids",
            "unreconciled_admitted_ids",
            "dropped_ids",
            "merged_ids",
            "distinct_same_content_pair",
            "all_intakes_accounted",
            "carry_selection_performed",
            "custody_reconciliation_performed",
            "external_effect_count",
        ],
        "return queue accounting",
    )
    intake_order = [item["queue_item_id"] for item in returns]
    require(accounting["intake_order"] == intake_order, "return queue: immutable intake order")
    require(accounting["admission_order"] == admitted_ids, "return queue: separate admission order")
    expected_ready_residual = [
        return_id for return_id in intake_order
        if return_id not in admitted_ids
        and return_by_id[return_id]["initial_queue_state"] == "READY"
        and return_id not in service_held_ids
    ]
    expected_held_residual = [
        return_id for return_id in intake_order
        if return_id not in admitted_ids
        and (
            return_by_id[return_id]["initial_queue_state"] == "HELD"
            or return_id in service_held_ids
        )
    ]
    require(accounting["ready_residual_ids"] == expected_ready_residual, "return queue: ready residual conservation")
    require(accounting["held_residual_ids"] == expected_held_residual, "return queue: held residual conservation")
    require(accounting["unreconciled_admitted_ids"] == admitted_ids, "return queue: admitted custody remains unreconciled")
    require(accounting["dropped_ids"] == [], "return queue: no dropped returns")
    require(accounting["merged_ids"] == [], "return queue: no merged returns")
    pair = _unique_string_ids(accounting["distinct_same_content_pair"], "return queue same-content pair")
    require(len(pair) == 2 and all(return_id in admitted_ids for return_id in pair), "return queue: same-content pair separately admitted")
    require(return_by_id[pair[0]]["content_sha256"] == return_by_id[pair[1]]["content_sha256"], "return queue: declared same-content pair")
    require(
        all(return_by_id[return_id]["objective_disposition"].endswith(":SATISFIED") for return_id in pair),
        "return queue fixture: same-content evaluator wins remain separate",
    )
    require(accounting["all_intakes_accounted"] is True, "return queue: intake accounting")
    require(set(intake_order) == set(admitted_ids + expected_ready_residual + expected_held_residual), "return queue: no drop, merge, or duplicate accounting")
    require(accounting["carry_selection_performed"] is False, "return queue: queue cannot select carry")
    require(accounting["custody_reconciliation_performed"] is False, "return queue: queue cannot reconcile custody")
    require(type(accounting["external_effect_count"]) is int and accounting["external_effect_count"] == 0, "return queue: accounting external effect")

    def collect_strings(value: Any) -> set[str]:
        if isinstance(value, dict):
            result: set[str] = set()
            for nested in value.values():
                result.update(collect_strings(nested))
            return result
        if isinstance(value, list):
            result = set()
            for nested in value:
                result.update(collect_strings(nested))
            return result
        return {value} if isinstance(value, str) else set()

    non_thulia_queue = {
        key: value
        for key, value in queue.items()
        if key != "thulia_non_interference"
    }
    scheduling_surface_strings = collect_strings({
        "queue": non_thulia_queue,
        "priority_authorizations": authorizations,
        "priority_receipts": document["priority_receipts"],
        "priority_append_holds": priority_append_holds,
        "retry_rotation_release_receipts": retry_rotation_releases,
        "service_reconciliation_receipts": service_reconciliations,
        "scheduling_attestations": scheduling_attestations,
        "returns": returns,
        "snapshots": snapshots,
        "accounting": accounting,
    })
    non_morrow_queue = {
        key: value
        for key, value in queue.items()
        if key != "queue_steward"
    }
    controller_and_data_surface_strings = collect_strings({
        "queue": non_morrow_queue,
        "priority_authorizations": authorizations,
        "priority_receipts": document["priority_receipts"],
        "priority_append_holds": priority_append_holds,
        "retry_rotation_release_receipts": retry_rotation_releases,
        "service_reconciliation_receipts": service_reconciliations,
        "scheduling_attestations": scheduling_attestations,
        "returns": returns,
        "snapshots": snapshots,
        "accounting": accounting,
    })
    controller_snapshot_surfaces = []
    for snapshot in snapshots:
        controller_snapshot = {
            key: value
            for key, value in snapshot.items()
            if key not in {"morrow_invocation_cut_binding", "morrow_ready_bindings", "proposal"}
        }
        if isinstance(snapshot["proposal"], dict):
            morrow_output = snapshot["proposal"].get("morrow_output")
            static_output = (
                {
                    key: value
                    for key, value in morrow_output.items()
                    if key not in {"invocation_cut_binding", "ready_order"}
                }
                if isinstance(morrow_output, dict)
                else morrow_output
            )
            controller_snapshot["proposal"] = {
                "proposal_ref": snapshot["proposal"].get("proposal_ref"),
                "morrow_output": static_output,
            }
        controller_snapshot_surfaces.append(controller_snapshot)
    static_controller_and_data_strings = collect_strings({
        "document_metadata": {
            "schema": document["schema"],
            "fixture_kind": document["fixture_kind"],
            "status": document["status"],
            "claim_ceiling": document["claim_ceiling"],
        },
        "queue": queue,
        "priority_authorizations": authorizations,
        "priority_receipts": document["priority_receipts"],
        "priority_append_holds": priority_append_holds,
        "retry_rotation_release_receipts": retry_rotation_releases,
        "service_reconciliation_receipts": service_reconciliations,
        "scheduling_attestations": scheduling_attestations,
        "returns": returns,
        "snapshots": controller_snapshot_surfaces,
        "accounting": accounting,
    })
    require(
        not _canonical_surface_keys(morrow_dynamic_bindings).intersection(
            _canonical_surface_keys(static_controller_and_data_strings)
        ),
        "return queue: fresh opaque Morrow cut/item bindings must be disjoint from all durable controller, data, Thulia, and static Morrow surfaces",
    )
    require(
        not _canonical_surface_keys(thulia_refs).intersection(
            _canonical_surface_keys(scheduling_surface_strings)
        ),
        "return queue: no Thulia identity/state/ledger/Perch/Bridge Gloss may alias any scheduling surface",
    )
    require(
        not _canonical_surface_keys(morrow_refs).intersection(
            _canonical_surface_keys(controller_and_data_surface_strings)
        ),
        "return queue: no Morrow identity/legacy/manifest/task/aperture/profile reference may alias controller, Thulia, priority, return, snapshot, order, or admission state",
    )
    typed_cut_bodies = []
    typed_item_bodies = []
    for token in morrow_cut_bindings:
        match = re.fullmatch(r"mcut:([0-9a-f]{32})", token)
        require(match is not None, "return queue fixture: invocation cut uses a typed random-looking opaque token")
        typed_cut_bodies.append(match.group(1))
    for token in morrow_item_bindings:
        match = re.fullmatch(r"mitem:([0-9a-f]{32})", token)
        require(match is not None, "return queue fixture: ready item uses a typed random-looking opaque token")
        typed_item_bodies.append(match.group(1))
    opaque_bodies = [*typed_cut_bodies, *typed_item_bodies]
    require(
        len({body[:8] for body in opaque_bodies}) == len(opaque_bodies)
        and len({body[-8:] for body in opaque_bodies}) == len(opaque_bodies),
        "return queue fixture: opaque tokens cannot reuse a stable visible prefix or suffix across invocations",
    )
    durable_identifiers = {
        value
        for value in static_controller_and_data_strings
        if len(value) >= 8
    }
    require(
        not any(
            identifier in body or body in identifier
            for body in opaque_bodies
            for identifier in durable_identifiers
        ),
        "return queue fixture: opaque token bodies cannot contain durable/global identifiers",
    )
    validate_no_local_absolute_paths(document, "return-queue fixture")


def _resolve_local_ref(schema: dict[str, Any], reference: str, label: str) -> None:
    require(reference.startswith("#/"), f"{label}: only local schema refs are permitted")
    value: Any = schema
    for encoded_part in reference[2:].split("/"):
        part = encoded_part.replace("~1", "/").replace("~0", "~")
        require(isinstance(value, dict) and part in value, f"{label}: dangling schema ref {reference}")
        value = value[part]


def validate_schema(schema: Any, label: str) -> None:
    require(isinstance(schema, dict), f"{label}: schema root must be object")
    require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"{label}: draft identity")
    validate_https_url(schema.get("$id"), f"{label} $id")

    def walk(value: Any, location: str) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                require(value.get("additionalProperties") is False, f"{label}{location}: object must be closed")
                properties = value.get("properties")
                required = value.get("required", [])
                require(isinstance(properties, dict), f"{label}{location}: object properties missing")
                require(isinstance(required, list), f"{label}{location}: required must be an array")
                require(len(required) == len(set(required)), f"{label}{location}: duplicate required key")
                require(set(required) <= set(properties), f"{label}{location}: required key lacks a property schema")
            reference = value.get("$ref")
            if reference is not None:
                require(isinstance(reference, str), f"{label}{location}: non-string $ref")
                _resolve_local_ref(schema, reference, f"{label}{location}")
            for key, item in value.items():
                walk(item, f"{location}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{location}[{index}]")

    walk(schema, "$")


def validate_markdown_links(root: Path) -> int:
    count = 0
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        require(WINDOWS_ABSOLUTE_PATH.search(text) is None, f"{path}: local absolute path is forbidden")
        for match in MARKDOWN_LINK.finditer(text):
            target = match.group(1).strip()
            if target.startswith("https://"):
                validate_https_url(target, f"{path}: markdown link")
            elif target.startswith("#"):
                pass
            else:
                local_target = unquote(target.split("#", 1)[0])
                require(local_target and not local_target.startswith(("/", "\\")), f"{path}: local link must be relative")
                resolved = (path.parent / local_target).resolve()
                try:
                    resolved.relative_to(root.resolve())
                except ValueError as exc:
                    raise VerificationError(f"{path}: link escapes repository: {target}") from exc
                require(resolved.exists(), f"{path}: broken local link: {target}")
            count += 1
    return count


def validate_repository_hygiene(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        lower_name = path.name.lower()
        require(not any(lower_name.endswith(suffix) for suffix in FORBIDDEN_SOURCE_SUFFIXES), f"forbidden source/challenge binary: {path.relative_to(root)}")
        if path.suffix.lower() in {".json", ".md", ".py", ".yml", ".yaml"}:
            text = path.read_text(encoding="utf-8")
            for pattern in SECRET_PATTERNS:
                require(pattern.search(text) is None, f"possible secret material: {path.relative_to(root)}")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    })
    command = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        f"safe.directory={root.resolve().as_posix()}",
        "-C",
        str(root.resolve()),
        *args,
    ]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=environment,
    )


def validate_git_anchor(root: Path) -> None:
    tree = _git(root, "show", "-s", "--format=%T", ANCHOR_COMMIT)
    require(tree.returncode == 0, f"Git anchor is unavailable: {tree.stderr.strip()}")
    require(tree.stdout.strip() == ANCHOR_TREE, "Git anchor tree mismatch")
    ancestry = _git(root, "merge-base", "--is-ancestor", ANCHOR_COMMIT, "HEAD")
    require(ancestry.returncode == 0, "station HEAD must descend from the exact parent anchor")


def validate_required_text(root: Path) -> None:
    required = {
        "README.md": [
            "PREPARED_NOT_RUN",
            "Environment calls | `0`",
            "Holdout consumption | `0`",
            "cannot keep a Codex workspace alive",
        ],
        "research/STRONGWIZ_V3_INSPECTION.md": [
            STRONGWIZ_HEAD,
            STRONGWIZ_FREEZE,
            STRONGWIZ_FREEZE_TREE,
            "449 tests",
            "51 tests",
            "not wired into an ARC runner loop",
            "0.4.0.dev0",
            "Installing the package therefore does not supply Calibration 003",
        ],
        "design/CREATURES.md": [
            "Authenticated external operator control grants or revokes permission",
            "canonical controller admits and serializes proposals",
            "It does not execute an external effect",
            "separately authorized broker/domain writer",
            "frozen terminal-authority source",
            "uncertainty never authorizes retry",
            "physically isolated arms",
            "cannot keep a Codex workspace alive",
            "Morrow has no ledger, persistent state, Perch, Bridge Gloss",
            "Neither invokes, impersonates, depends on, or shares an identity/state surface",
        ],
        "design/RETURN_QUEUE.md": [
            "OFFLINE_REFERENCE_IMPLEMENTED_NOT_WIRED",
            "HOMECOMING:RETURNED",
            "controller-approved scheduling metadata",
            "Queue Steward",
            "does not queue human grants",
            "queue admission performs no reconciliation",
            "It has no filesystem, network, clock, randomness, subprocess, persistence",
            "Morrow and Thulia have symmetric non-interference boundaries",
        ],
        "design/MORROW_AND_THE_MARKED_TETHERS.md": [
            "DETERMINISTIC_STATELESS_PROPOSER_IMPLEMENTED_NOT_WIRED",
            "Morrow never read her Perch, ledger, Bridge Gloss",
            "Neither could invoke, impersonate, or depend upon the other",
        ],
        "prep/ARC_AGI_3_NO_RUN_PREFLIGHT.md": [
            "Kaggle contacts | 0",
            "Environment calls | 0",
            "Holdout consumption | 0",
            "NOT_FOUND",
            "non-retroactive",
        ],
    }
    for relative, phrases in required.items():
        text = " ".join((root / relative).read_text(encoding="utf-8").split())
        for phrase in phrases:
            require(phrase in text, f"{relative}: missing required boundary text {phrase!r}")


def verify_station(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    required_paths = [
        "README.md",
        "research/sources.lock.json",
        "research/INSPIRATION_MAP.md",
        "research/STRONGWIZ_V3_INSPECTION.md",
        "design/CREATURES.md",
        "design/RETURN_QUEUE.md",
        "design/MORROW_AND_THE_MARKED_TETHERS.md",
        "prep/ARC_AGI_3_NO_RUN_PREFLIGHT.md",
        "schemas/research-source.v1.schema.json",
        "schemas/creature-manifest.v1.schema.json",
        "schemas/objective-window.v1.schema.json",
        "schemas/return-queue.v1.schema.json",
        "schemas/return-queue.v2.schema.json",
        "schemas/morrow-scheduling-view.v1.schema.json",
        "schemas/morrow-proposal.v1.schema.json",
        "tools/morrow_queue.py",
        "fixtures/creature-manifest.synthetic.json",
        "fixtures/objective-window.synthetic.json",
        "fixtures/return-queue.synthetic.json",
        "examples/morrow-scheduling-view.synthetic.json",
        "examples/morrow-proposal.synthetic.json",
        "tests/test_morrow_priority_mechanics.py",
        "tests/test_morrow_queue.py",
    ]
    for relative in required_paths:
        require((root / relative).is_file(), f"missing station artifact: {relative}")

    parsed_json: dict[str, Any] = {}
    for path in sorted(root.rglob("*.json")):
        parsed_json[path.relative_to(root).as_posix()] = load_strict_json(path)

    source_ids = validate_sources(parsed_json["research/sources.lock.json"])
    validate_creature(parsed_json["fixtures/creature-manifest.synthetic.json"], source_ids)
    validate_objective_window(parsed_json["fixtures/objective-window.synthetic.json"])
    validate_return_queue(parsed_json["fixtures/return-queue.synthetic.json"])
    for relative in (
        "schemas/research-source.v1.schema.json",
        "schemas/creature-manifest.v1.schema.json",
        "schemas/objective-window.v1.schema.json",
        "schemas/return-queue.v1.schema.json",
        "schemas/return-queue.v2.schema.json",
        "schemas/morrow-scheduling-view.v1.schema.json",
        "schemas/morrow-proposal.v1.schema.json",
    ):
        validate_schema(parsed_json[relative], relative)

    markdown_link_count = validate_markdown_links(root)
    validate_repository_hygiene(root)
    validate_required_text(root)
    validate_git_anchor(root)

    return {
        "arc_environment_calls": 0,
        "external_network_calls_performed_by_verifier": 0,
        "holdout_consumption": 0,
        "markdown_links_checked": markdown_link_count,
        "source_count": len(source_ids),
        "station_status": "PREPARED_NOT_RUN",
        "status": "PASS",
        "synthetic_fixture_count": 3,
    }


def main() -> int:
    try:
        report = verify_station()
    except VerificationError as exc:
        print(json.dumps({"error": str(exc), "status": "FAIL"}, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
