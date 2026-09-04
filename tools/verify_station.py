#!/usr/bin/env python3
"""Offline verifier for the ARC-AGI-3 research station.

The verifier uses only the Python standard library. It reads local station
artifacts and local Git objects; it never contacts ARC, Kaggle, Zenodo, GitHub,
or any other network service.
"""

from __future__ import annotations

import datetime as _datetime
import json
import os
import re
import subprocess
import sys
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
        "prep/ARC_AGI_3_NO_RUN_PREFLIGHT.md",
        "schemas/research-source.v1.schema.json",
        "schemas/creature-manifest.v1.schema.json",
        "schemas/objective-window.v1.schema.json",
        "fixtures/creature-manifest.synthetic.json",
        "fixtures/objective-window.synthetic.json",
    ]
    for relative in required_paths:
        require((root / relative).is_file(), f"missing station artifact: {relative}")

    parsed_json: dict[str, Any] = {}
    for path in sorted(root.rglob("*.json")):
        parsed_json[path.relative_to(root).as_posix()] = load_strict_json(path)

    source_ids = validate_sources(parsed_json["research/sources.lock.json"])
    validate_creature(parsed_json["fixtures/creature-manifest.synthetic.json"], source_ids)
    validate_objective_window(parsed_json["fixtures/objective-window.synthetic.json"])
    for relative in (
        "schemas/research-source.v1.schema.json",
        "schemas/creature-manifest.v1.schema.json",
        "schemas/objective-window.v1.schema.json",
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
        "synthetic_fixture_count": 2,
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
