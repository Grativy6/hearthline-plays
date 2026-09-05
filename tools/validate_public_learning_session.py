#!/usr/bin/env python3
"""Validate a public-playground learning-session record without running it.

This dependency-free tool only reads and validates a small JSON document. It
does not use the network, call a model or evaluator, or execute candidate code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

SCHEMA_VERSION = "public-learning-session.v1"
STATUS = "PUBLIC_PLAYGROUND_NOT_FORMAL_EXPERIMENT"
MODES = {"micro_fixture", "public_core", "public_python"}
EXPERIMENT_ID = "ROSETTA-001"
CLAIM_CEILING = (
    "Learning-oriented public playground record only; not a formal experiment, "
    "Rosetta score, learning tax, or leaderboard result."
)
MAX_BYTES = 512 * 1024
MAX_TRACE_ITEMS = 100
MAX_TEXT_LENGTH = 8_000
OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MICRO_DECK_SHA256 = "b88a0bc011378e69449315384e675edc263427457b39c8606d9c994f67a0920c"
SOURCES = {
    "micro_fixture": {
        "kind": "REPOSITORY_LOCAL_ORIGINAL",
        "locator": "playground/micro/orientation-deck.v1.json",
        "version": "v1",
    },
    "public_core": {
        "kind": "PUBLIC_HTTP_REFERENCE",
        "locator": "https://www.kaggle.com/benchmarks/tasks/namanbnsl/rosettabench-core",
        "version": "1",
    },
    "public_python": {
        "kind": "PUBLIC_HTTP_REFERENCE",
        "locator": "https://www.kaggle.com/benchmarks/tasks/namanbnsl/rosettabench-python-baseline-control",
        "version": "1",
    },
}

ROOT_KEYS = {
    "schema_version",
    "status",
    "session_mode",
    "source",
    "exercise",
    "budgets",
    "activity",
    "future_plan",
    "learning_trace",
    "provenance",
    "formal_pilot",
    "claim_ceiling",
}
SOURCE_KEYS = {"kind", "locator", "version"}
EXERCISE_KEYS = {"session_id", "problem_id", "learning_goal"}
BUDGET_KEYS = {"model_calls", "evaluator_runs", "candidate_code_executions"}
ACTIVITY_KEYS = {
    "model_calls_completed",
    "evaluator_runs_completed",
    "candidate_code_executions_completed",
}
FUTURE_PLAN_KEYS = {"status", "description"}
TRACE_ARRAY_KEYS = {
    "observations",
    "hypotheses",
    "requests",
    "reformulations",
    "reflections",
    "evidence_ids_used",
    "assumptions_withheld",
}
TRACE_KEYS = TRACE_ARRAY_KEYS | {
    "receipt_bindings",
    "episode_control",
    "score_or_match",
    "what_changed_next_time",
}
RECEIPT_BINDING_KEYS = {
    "verification",
    "source_sha256",
    "ledger_receipt_sha256",
    "reset_receipt_sha256",
}
RECEIPT_BINDING_STATES = {"RECEIPTS_UNBOUND", "VERIFIED_WITH_SUPPLIED_RECEIPTS"}
LEDGER_OUTCOMES = {
    "SUPPORTED_RENDER",
    "AMBIGUOUS",
    "CONFLICTING",
    "UNRESOLVED",
    "CONTRACT_ERROR",
}
LEDGER_EVIDENCE_KINDS = {"SUPPORTED", "AMBIGUOUS"}
LEDGER_SOURCE_KINDS = {
    "SUPPLIED_DEMONSTRATION",
    "ORIGINAL_MICRO_FIXTURE",
    "PUBLIC_SOURCE",
}
LEDGER_CONTRACT_ERRORS = {
    "SCOPE_MUST_BE_LEARNING_SCOPE",
    "CROSS_SCOPE_REQUEST_REFUSED",
    "REQUESTED_FORM_MUST_BE_NONEMPTY_STRING",
    "DIRECTION_MUST_BE_OPAQUE_ID",
}
EPISODE_CONTROL_KEYS = {
    "learner_view_opened",
    "answer_sealed_before_coach_view",
    "coach_view_opened",
    "state_reset_confirmed",
}
MICRO_EPISODE_IDS = {
    "LANTERN-LEDGER-01",
    "LANTERN-REFORMULATE-01",
    "LANTERN-RESET-01",
}
PROVENANCE_KEYS = {
    "created_at_utc",
    "created_by",
    "source_is_public",
    "network_accessed_by_generator",
    "model_invoked_by_generator",
    "evaluator_invoked_by_generator",
    "candidate_code_executed_by_generator",
}
FORMAL_PILOT_KEYS = {"experiment_id", "consumed"}

FORBIDDEN_FIELD_NAMES = {
    "private_test",
    "private_tests",
    "private_test_cases",
    "hidden_test",
    "hidden_tests",
    "hidden_test_cases",
    "all_tests",
    "lang_seed",
    "language_seed",
    "generator_seed",
    "mapping_seed",
    "full_map",
    "full_maps",
    "generator_map",
    "reverse_map",
    "credential",
    "credentials",
    "password",
    "api_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "cookie",
}
FORBIDDEN_TEXT = (
    re.compile(r"\b(?:private|hidden)[ _-]?test(?:s|[ _-]?cases?)?\b", re.IGNORECASE),
    re.compile(
        r"\b(?:generator|language|lang|mapping)[ _-]?seed\b", re.IGNORECASE
    ),
    re.compile(
        r"\bfull[ _-]?(?:(?:generator|mapping)[ _-]?)?maps?\b", re.IGNORECASE
    ),
    re.compile(r"\breverse[ _-]?maps?\b", re.IGNORECASE),
)
CREDENTIAL_TEXT = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~-]{12,}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:api[ _-]?key|access[ _-]?token|client[ _-]?secret|password)\s*[:=]",
        re.IGNORECASE,
    ),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


class SessionError(ValueError):
    """Raised when a session record violates the public-playground boundary."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SessionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json_document(path: Path, label: str) -> object:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SessionError(f"cannot read {label}: {exc}") from exc
    if len(raw) > MAX_BYTES:
        raise SessionError(f"{label} exceeds the 512 KiB safety ceiling")
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionError(f"invalid UTF-8 {label} JSON: {exc}") from exc


def load_session(path: Path) -> object:
    return _load_json_document(path, "session")


def load_receipt(path: Path) -> object:
    return _load_json_document(path, "receipt")


def _normalized_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _scan_for_protected_material(value: object, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_field_name(key)
            if normalized in FORBIDDEN_FIELD_NAMES:
                raise SessionError(f"{path}.{key} is a forbidden protected-data field")
            _scan_for_protected_material(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_for_protected_material(child, f"{path}[{index}]")
    elif isinstance(value, str):
        for pattern in FORBIDDEN_TEXT:
            if pattern.search(value):
                raise SessionError(f"{path} refers to forbidden evaluator or generator material")
        for pattern in CREDENTIAL_TEXT:
            if pattern.search(value):
                raise SessionError(f"{path} appears to contain a credential")


def _exact_object(value: object, keys: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise SessionError(f"{label} schema drift: expected exactly {sorted(keys)}, got {actual}")
    return value


def _trimmed_string(value: object, label: str, *, maximum: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SessionError(f"{label} must be a nonempty trimmed string")
    if len(value) > maximum:
        raise SessionError(f"{label} exceeds {maximum} characters")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SessionError(f"{label} must be a nonnegative integer")
    return value


def _public_url(value: object) -> str:
    url = _trimmed_string(value, "source.locator", maximum=2_048)
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SessionError("source.locator must be an absolute public HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise SessionError("source.locator must not contain credentials")
    if parsed.fragment:
        raise SessionError("source.locator must not contain a fragment")
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        normalized = _normalized_field_name(key)
        if any(marker in normalized for marker in ("token", "secret", "key", "auth")):
            raise SessionError("source.locator query must not contain credential-like parameters")
    return url


def _validate_timestamp(value: object) -> None:
    timestamp = _trimmed_string(value, "provenance.created_at_utc", maximum=40)
    if not timestamp.endswith("Z"):
        raise SessionError("provenance.created_at_utc must be an RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as exc:
        raise SessionError(
            "provenance.created_at_utc must be an RFC 3339 UTC timestamp"
        ) from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise SessionError("provenance.created_at_utc must use UTC")


def _validate_trace(
    value: object, session_mode: str
) -> tuple[dict[str, object], dict[str, object]]:
    trace = _exact_object(value, TRACE_KEYS, "learning_trace")
    for key in sorted(TRACE_ARRAY_KEYS):
        items = trace[key]
        if not isinstance(items, list):
            raise SessionError(f"learning_trace.{key} must be an array")
        if len(items) > MAX_TRACE_ITEMS:
            raise SessionError(f"learning_trace.{key} exceeds {MAX_TRACE_ITEMS} items")
        for index, item in enumerate(items):
            _trimmed_string(item, f"learning_trace.{key}[{index}]")
    bindings = _exact_object(
        trace["receipt_bindings"],
        RECEIPT_BINDING_KEYS,
        "learning_trace.receipt_bindings",
    )
    verification = bindings["verification"]
    if verification not in RECEIPT_BINDING_STATES:
        raise SessionError(
            "learning_trace.receipt_bindings.verification must be RECEIPTS_UNBOUND "
            "or VERIFIED_WITH_SUPPLIED_RECEIPTS"
        )
    for key in ("source_sha256", "ledger_receipt_sha256", "reset_receipt_sha256"):
        digest = bindings[key]
        if digest is not None and (
            not isinstance(digest, str) or SHA256.fullmatch(digest) is None
        ):
            raise SessionError(
                f"learning_trace.receipt_bindings.{key} must be null or lowercase SHA-256"
            )
    if session_mode == "micro_fixture" and bindings["source_sha256"] != MICRO_DECK_SHA256:
        raise SessionError("micro_fixture source_sha256 must bind the original deck")
    if session_mode != "micro_fixture" and bindings["source_sha256"] is not None:
        raise SessionError("link-only public references must leave source_sha256 null")
    controls = _exact_object(
        trace["episode_control"],
        EPISODE_CONTROL_KEYS,
        "learning_trace.episode_control",
    )
    for key in sorted(EPISODE_CONTROL_KEYS):
        if type(controls[key]) is not bool:
            raise SessionError(f"learning_trace.episode_control.{key} must be boolean")
    if controls["coach_view_opened"] and not controls["answer_sealed_before_coach_view"]:
        raise SessionError("coach_view_opened requires answer_sealed_before_coach_view")
    if trace["score_or_match"] not in {None, "MATCH", "NO_MATCH", "NOT_SCORED"}:
        raise SessionError(
            "learning_trace.score_or_match must be null, MATCH, NO_MATCH, or NOT_SCORED"
        )
    if trace["what_changed_next_time"] is not None:
        _trimmed_string(
            trace["what_changed_next_time"],
            "learning_trace.what_changed_next_time",
        )
    return bindings, controls


def _verified_self_digest(
    document: object,
    *,
    digest_field: str,
    schema_version: str,
    label: str,
) -> tuple[dict[str, object], str]:
    receipt = _exact_receipt_object(document, label)
    if receipt.get("schema_version") != schema_version:
        raise SessionError(f"{label} schema_version mismatch")
    digest = receipt.get(digest_field)
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        raise SessionError(f"{label}.{digest_field} must be a lowercase SHA-256")
    unsigned = {key: value for key, value in receipt.items() if key != digest_field}
    try:
        canonical = json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SessionError(f"{label} is not canonical UTF-8 JSON data") from exc
    if actual != digest:
        raise SessionError(f"{label} self-digest mismatch")
    return receipt, digest


def _exact_receipt_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SessionError(f"{label} must be a JSON object")
    return value


def _receipt_sha256(value: object, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise SessionError(f"{label} must be a lowercase SHA-256")
    return value


def _receipt_nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SessionError(f"{label} must be a nonempty string")
    return value


def _receipt_nonnegative_integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SessionError(f"{label} must be a nonnegative integer")
    return value


def _validate_ledger_provenance(
    value: object,
    *,
    receipt_mode: str,
    label: str,
) -> bool:
    common = {
        "source_kind",
        "ordinal",
        "source_sha256",
        "caller_declared_not_verified",
    }
    identity_key = "source_id_sha256" if receipt_mode == "DIGESTS" else "source_id"
    provenance = _exact_object(value, common | {identity_key}, label)
    if (
        not isinstance(provenance["source_kind"], str)
        or provenance["source_kind"] not in LEDGER_SOURCE_KINDS
    ):
        raise SessionError(f"{label}.source_kind mismatch")
    ordinal = provenance["ordinal"]
    if ordinal is not None:
        _receipt_nonnegative_integer(ordinal, f"{label}.ordinal")
    source_digest = _receipt_sha256(
        provenance["source_sha256"],
        f"{label}.source_sha256",
        optional=True,
    )
    if provenance["caller_declared_not_verified"] is not True:
        raise SessionError(f"{label} must mark caller provenance unverified")
    if receipt_mode == "DIGESTS":
        _receipt_sha256(provenance[identity_key], f"{label}.{identity_key}")
    else:
        source_id = provenance[identity_key]
        if not isinstance(source_id, str) or OPAQUE_ID.fullmatch(source_id) is None:
            raise SessionError(f"{label}.{identity_key} must be an opaque ID")
    return source_digest is not None


def _validate_ledger_observations(
    value: object,
    *,
    receipt_mode: str,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    if not isinstance(value, list):
        raise SessionError("ledger receipt observations must be an array")
    observations: list[dict[str, object]] = []
    source_digest_count = 0
    signatures: list[tuple[str, str, tuple[str, ...]]] = []
    common = {"observation_id", "kind", "provenance"}
    mode_keys = (
        {"direction_sha256", "requested_form_sha256", "candidate_sha256"}
        if receipt_mode == "DIGESTS"
        else {"direction", "requested_form", "candidates"}
    )
    for index, item in enumerate(value, start=1):
        label = f"ledger receipt observations[{index - 1}]"
        observation = _exact_object(item, common | mode_keys, label)
        expected_id = f"observation-{index:04d}"
        if observation["observation_id"] != expected_id:
            raise SessionError(f"{label}.observation_id is not sequential")
        kind = observation["kind"]
        if not isinstance(kind, str) or kind not in LEDGER_EVIDENCE_KINDS:
            raise SessionError(f"{label}.kind mismatch")
        source_digest_count += _validate_ledger_provenance(
            observation["provenance"],
            receipt_mode=receipt_mode,
            label=f"{label}.provenance",
        )
        if receipt_mode == "DIGESTS":
            direction = _receipt_sha256(
                observation["direction_sha256"], f"{label}.direction_sha256"
            )
            requested = _receipt_sha256(
                observation["requested_form_sha256"],
                f"{label}.requested_form_sha256",
            )
            candidates_value = observation["candidate_sha256"]
            candidate_label = f"{label}.candidate_sha256"
        else:
            direction_value = observation["direction"]
            if not isinstance(direction_value, str) or OPAQUE_ID.fullmatch(direction_value) is None:
                raise SessionError(f"{label}.direction must be an opaque ID")
            direction = direction_value
            requested = _receipt_nonempty_string(
                observation["requested_form"], f"{label}.requested_form"
            )
            candidates_value = observation["candidates"]
            candidate_label = f"{label}.candidates"
        if not isinstance(candidates_value, list):
            raise SessionError(f"{candidate_label} must be an array")
        candidates: list[str] = []
        for candidate_index, candidate in enumerate(candidates_value):
            if receipt_mode == "DIGESTS":
                checked = _receipt_sha256(
                    candidate,
                    f"{candidate_label}[{candidate_index}]",
                )
            else:
                checked = _receipt_nonempty_string(
                    candidate,
                    f"{candidate_label}[{candidate_index}]",
                )
            if checked in candidates:
                raise SessionError(f"{candidate_label} contains a duplicate")
            candidates.append(checked)
        expected_minimum = 1 if kind == "SUPPORTED" else 2
        if len(candidates) < expected_minimum or (kind == "SUPPORTED" and len(candidates) != 1):
            raise SessionError(f"{candidate_label} count does not match {kind}")
        if receipt_mode == "RAW" and candidates != sorted(candidates):
            raise SessionError(f"{candidate_label} must be deterministically sorted")
        normalized = {
            "observation_id": expected_id,
            "kind": kind,
            "direction": direction,
            "requested_form": requested,
            "candidates": candidates,
        }
        observations.append(normalized)
        signatures.append((direction, requested, tuple(candidates)))

    signature_counts = Counter(signatures)
    return observations, {
        "source_digest_count": source_digest_count,
        "repeated_claim_groups": sum(count > 1 for count in signature_counts.values()),
        "repeated_claim_observations": sum(
            count - 1 for count in signature_counts.values() if count > 1
        ),
    }


def _validate_ledger_requests(
    value: object,
    *,
    receipt_mode: str,
    observations: list[dict[str, object]],
) -> tuple[list[dict[str, object]], Counter[str]]:
    if not isinstance(value, list):
        raise SessionError("ledger receipt requests must be an array")
    requests: list[dict[str, object]] = []
    outcome_counts: Counter[str] = Counter()
    common = {
        "request_id",
        "outcome",
        "accepted",
        "refused",
        "evidence_ids",
        "refusal_reason",
    }
    mode_keys = (
        {
            "direction_sha256",
            "requested_form_sha256",
            "rendering_sha256",
            "candidate_sha256",
        }
        if receipt_mode == "DIGESTS"
        else {"direction", "requested_form", "rendering", "candidates"}
    )
    observation_ids = {item["observation_id"] for item in observations}
    for index, item in enumerate(value, start=1):
        label = f"ledger receipt requests[{index - 1}]"
        request = _exact_object(item, common | mode_keys, label)
        expected_id = f"request-{index:04d}"
        if request["request_id"] != expected_id:
            raise SessionError(f"{label}.request_id is not sequential")
        outcome = request["outcome"]
        if not isinstance(outcome, str) or outcome not in LEDGER_OUTCOMES:
            raise SessionError(f"{label}.outcome mismatch")
        expected_accepted = outcome == "SUPPORTED_RENDER"
        if type(request["accepted"]) is not bool or request["accepted"] is not expected_accepted:
            raise SessionError(f"{label}.accepted does not match outcome")
        if type(request["refused"]) is not bool or request["refused"] is not (not expected_accepted):
            raise SessionError(f"{label}.refused does not match outcome")
        expected_reason: str | None
        if outcome == "SUPPORTED_RENDER":
            expected_reason = None
        elif outcome == "AMBIGUOUS":
            expected_reason = "MULTIPLE_EVIDENCE_SUPPORTED_RENDERINGS"
        elif outcome == "CONFLICTING":
            expected_reason = "EVIDENCE_INTERSECTION_EMPTY"
        elif outcome == "UNRESOLVED":
            expected_reason = "NO_SUPPORTING_OBSERVATION"
        else:
            expected_reason = request["refusal_reason"]
            if not isinstance(expected_reason, str) or expected_reason not in LEDGER_CONTRACT_ERRORS:
                raise SessionError(f"{label}.refusal_reason is not a contract error")
        if request["refusal_reason"] != expected_reason:
            raise SessionError(f"{label}.refusal_reason does not match outcome")

        evidence_value = request["evidence_ids"]
        if not isinstance(evidence_value, list) or any(
            not isinstance(evidence_id, str) or evidence_id not in observation_ids
            for evidence_id in evidence_value
        ):
            raise SessionError(f"{label}.evidence_ids contains an unknown observation")
        if len(evidence_value) != len(set(evidence_value)):
            raise SessionError(f"{label}.evidence_ids contains a duplicate")

        if receipt_mode == "DIGESTS":
            direction = _receipt_sha256(
                request["direction_sha256"],
                f"{label}.direction_sha256",
                optional=outcome == "CONTRACT_ERROR",
            )
            requested = _receipt_sha256(
                request["requested_form_sha256"],
                f"{label}.requested_form_sha256",
                optional=outcome == "CONTRACT_ERROR",
            )
            rendering = _receipt_sha256(
                request["rendering_sha256"],
                f"{label}.rendering_sha256",
                optional=True,
            )
            candidates_value = request["candidate_sha256"]
            candidate_label = f"{label}.candidate_sha256"
        else:
            direction_value = request["direction"]
            requested_value = request["requested_form"]
            if outcome != "CONTRACT_ERROR":
                if not isinstance(direction_value, str) or OPAQUE_ID.fullmatch(direction_value) is None:
                    raise SessionError(f"{label}.direction must be an opaque ID")
                direction = direction_value
                requested = _receipt_nonempty_string(
                    requested_value, f"{label}.requested_form"
                )
            else:
                if direction_value is not None and not isinstance(direction_value, str):
                    raise SessionError(f"{label}.direction must be a string or null")
                if requested_value is not None and not isinstance(requested_value, str):
                    raise SessionError(f"{label}.requested_form must be a string or null")
                direction = direction_value
                requested = requested_value
            rendering_value = request["rendering"]
            if rendering_value is not None and (
                not isinstance(rendering_value, str) or not rendering_value
            ):
                raise SessionError(f"{label}.rendering must be a nonempty string or null")
            rendering = rendering_value
            candidates_value = request["candidates"]
            candidate_label = f"{label}.candidates"
        if not isinstance(candidates_value, list):
            raise SessionError(f"{candidate_label} must be an array")
        candidates: list[str] = []
        for candidate_index, candidate in enumerate(candidates_value):
            if receipt_mode == "DIGESTS":
                checked = _receipt_sha256(candidate, f"{candidate_label}[{candidate_index}]")
            else:
                checked = _receipt_nonempty_string(
                    candidate, f"{candidate_label}[{candidate_index}]"
                )
            if checked in candidates:
                raise SessionError(f"{candidate_label} contains a duplicate")
            candidates.append(checked)
        if receipt_mode == "RAW" and candidates != sorted(candidates):
            raise SessionError(f"{candidate_label} must be deterministically sorted")

        if outcome == "CONTRACT_ERROR":
            if evidence_value or candidates or rendering is not None:
                raise SessionError(f"{label} contract error carries unsupported evidence")
        else:
            matches = [
                observation
                for observation in observations
                if observation["direction"] == direction
                and observation["requested_form"] == requested
            ]
            expected_evidence = [observation["observation_id"] for observation in matches]
            if evidence_value != expected_evidence:
                raise SessionError(f"{label}.evidence_ids do not match observations")
            if not matches:
                derived_outcome = "UNRESOLVED"
                derived_candidates: set[str] = set()
                derived_rendering = None
            else:
                candidate_sets = [set(observation["candidates"]) for observation in matches]
                common_candidates = set.intersection(*candidate_sets)
                all_candidates = set.union(*candidate_sets)
                if not common_candidates:
                    derived_outcome = "CONFLICTING"
                    derived_candidates = all_candidates
                    derived_rendering = None
                elif len(common_candidates) > 1:
                    derived_outcome = "AMBIGUOUS"
                    derived_candidates = common_candidates
                    derived_rendering = None
                else:
                    derived_outcome = "SUPPORTED_RENDER"
                    derived_candidates = common_candidates
                    derived_rendering = next(iter(common_candidates))
            if outcome != derived_outcome:
                raise SessionError(f"{label}.outcome does not match observations")
            if set(candidates) != derived_candidates or len(candidates) != len(derived_candidates):
                raise SessionError(f"{candidate_label} does not match observations")
            if rendering != derived_rendering:
                raise SessionError(f"{label}.rendering does not match observations")

        requests.append({"outcome": outcome, "accepted": expected_accepted})
        outcome_counts[outcome] += 1
    return requests, outcome_counts


def _validate_ledger_counts(
    value: object,
    *,
    observations: list[dict[str, object]],
    observation_stats: dict[str, int],
    requests: list[dict[str, object]],
    outcome_counts: Counter[str],
) -> None:
    expected_keys = {
        "observations",
        "supported_observations",
        "ambiguous_observations",
        "observations_with_source_sha256",
        "repeated_claim_groups",
        "repeated_claim_observations",
        "requests",
        "accepted",
        "refused",
        "outcomes",
    }
    counts = _exact_object(value, expected_keys, "ledger receipt counts")
    expected = {
        "observations": len(observations),
        "supported_observations": sum(
            observation["kind"] == "SUPPORTED" for observation in observations
        ),
        "ambiguous_observations": sum(
            observation["kind"] == "AMBIGUOUS" for observation in observations
        ),
        "observations_with_source_sha256": observation_stats["source_digest_count"],
        "repeated_claim_groups": observation_stats["repeated_claim_groups"],
        "repeated_claim_observations": observation_stats["repeated_claim_observations"],
        "requests": len(requests),
        "accepted": sum(request["accepted"] is True for request in requests),
        "refused": sum(request["accepted"] is False for request in requests),
    }
    for key, expected_value in expected.items():
        actual = _receipt_nonnegative_integer(counts[key], f"ledger receipt counts.{key}")
        if actual != expected_value:
            raise SessionError(f"ledger receipt counts.{key} does not match content")
    outcomes = _exact_object(
        counts["outcomes"],
        LEDGER_OUTCOMES,
        "ledger receipt counts.outcomes",
    )
    for outcome in LEDGER_OUTCOMES:
        actual = _receipt_nonnegative_integer(
            outcomes[outcome], f"ledger receipt counts.outcomes.{outcome}"
        )
        if actual != outcome_counts[outcome]:
            raise SessionError(
                f"ledger receipt counts.outcomes.{outcome} does not match requests"
            )


def _validate_implementation_boundary(value: object, *, receipt_mode: str) -> None:
    boundary = _exact_object(
        value,
        {
            "scope",
            "caller_evidence_origin_verified",
            "public_release_review_required",
            "raw_content_included",
            "module_performs",
        },
        "ledger receipt implementation_boundary",
    )
    if boundary["scope"] != "LEDGER_MODULE_OPERATIONS_ONLY_NOT_CALLER_ACTIVITY":
        raise SessionError("ledger receipt implementation boundary scope mismatch")
    if boundary["caller_evidence_origin_verified"] is not False:
        raise SessionError("ledger receipt cannot verify caller evidence origin")
    if boundary["public_release_review_required"] is not True:
        raise SessionError("ledger receipt must retain public-release review")
    if boundary["raw_content_included"] is not (receipt_mode == "RAW"):
        raise SessionError("ledger receipt raw-content boundary mismatches mode")
    expected_capabilities = {
        "cross_scope_learning_state": False,
        "cross_scope_receipt_lineage": True,
        "external_access": False,
        "generated_code_execution": False,
        "mapping_invention": False,
        "model_calls": False,
        "strategy_selection": False,
    }
    capabilities = _exact_object(
        boundary["module_performs"],
        set(expected_capabilities),
        "ledger receipt implementation_boundary.module_performs",
    )
    if capabilities != expected_capabilities:
        raise SessionError("ledger receipt implementation capabilities mismatch")


def _validate_ledger_receipt_schema(ledger: dict[str, object]) -> tuple[str, int]:
    configuration = _exact_object(
        ledger["configuration"],
        {"normalization", "receipt_mode", "resolution_rule"},
        "ledger receipt configuration",
    )
    if configuration["normalization"] != "EXACT":
        raise SessionError("ledger receipt normalization mismatch")
    receipt_mode = configuration["receipt_mode"]
    if not isinstance(receipt_mode, str) or receipt_mode not in {"DIGESTS", "RAW"}:
        raise SessionError("ledger receipt mode mismatch")
    if configuration["resolution_rule"] != "candidate_set_intersection_v1":
        raise SessionError("ledger receipt resolution rule mismatch")

    lifecycle = _exact_object(
        ledger["lifecycle"],
        {
            "state",
            "generation",
            "reset_from_receipt_sha256",
            "reset_required_before_new_scope",
        },
        "ledger receipt lifecycle",
    )
    if lifecycle["state"] != "CLOSED":
        raise SessionError("ledger receipt must be CLOSED")
    generation = _receipt_nonnegative_integer(
        lifecycle["generation"], "ledger receipt lifecycle.generation"
    )
    reset_from = _receipt_sha256(
        lifecycle["reset_from_receipt_sha256"],
        "ledger receipt lifecycle.reset_from_receipt_sha256",
        optional=True,
    )
    if (generation == 0) is not (reset_from is None):
        raise SessionError("ledger receipt lifecycle reset lineage mismatch")
    if lifecycle["reset_required_before_new_scope"] is not True:
        raise SessionError("ledger receipt lifecycle reset guard mismatch")

    observations, observation_stats = _validate_ledger_observations(
        ledger["observations"], receipt_mode=receipt_mode
    )
    requests, outcome_counts = _validate_ledger_requests(
        ledger["requests"],
        receipt_mode=receipt_mode,
        observations=observations,
    )
    _validate_ledger_counts(
        ledger["counts"],
        observations=observations,
        observation_stats=observation_stats,
        requests=requests,
        outcome_counts=outcome_counts,
    )
    _validate_implementation_boundary(
        ledger["implementation_boundary"], receipt_mode=receipt_mode
    )
    return receipt_mode, generation


def _validate_receipt_bindings(
    bindings: dict[str, object],
    controls: dict[str, object],
    *,
    session_id: str,
    problem_id: str,
    ledger_receipt: object | None,
    reset_receipt: object | None,
) -> str:
    supplied = ledger_receipt is not None or reset_receipt is not None
    if not supplied:
        if bindings["verification"] != "RECEIPTS_UNBOUND":
            raise SessionError("verified receipt bindings require supplied receipt documents")
        if bindings["ledger_receipt_sha256"] is not None:
            raise SessionError("ledger_receipt_sha256 requires the supplied ledger receipt")
        if bindings["reset_receipt_sha256"] is not None:
            raise SessionError("reset_receipt_sha256 requires the supplied reset receipt")
        if controls["answer_sealed_before_coach_view"]:
            raise SessionError("a sealed answer requires the supplied ledger receipt")
        if controls["state_reset_confirmed"]:
            raise SessionError("a confirmed reset requires the supplied reset receipt")
        return "RECEIPTS_UNBOUND"

    if ledger_receipt is None:
        raise SessionError("a supplied reset receipt requires its ledger receipt")
    if bindings["verification"] != "VERIFIED_WITH_SUPPLIED_RECEIPTS":
        raise SessionError("supplied receipts require VERIFIED_WITH_SUPPLIED_RECEIPTS")
    ledger, ledger_digest = _verified_self_digest(
        ledger_receipt,
        digest_field="receipt_sha256",
        schema_version="hearthline-learning-ledger.v1",
        label="ledger receipt",
    )
    expected_ledger_keys = {
        "schema_version",
        "identity",
        "scope",
        "configuration",
        "lifecycle",
        "observations",
        "requests",
        "counts",
        "implementation_boundary",
        "receipt_sha256",
    }
    if set(ledger) != expected_ledger_keys:
        raise SessionError("ledger receipt fields mismatch")
    if ledger.get("identity") != "experimental_evidence_bounded_learning_ledger_not_canonical_gloss":
        raise SessionError("ledger receipt identity mismatch")
    receipt_mode, ledger_generation = _validate_ledger_receipt_schema(ledger)
    if receipt_mode == "DIGESTS":
        expected_scope = {
            "session_id_sha256": hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
            "problem_id_sha256": hashlib.sha256(problem_id.encode("utf-8")).hexdigest(),
        }
    elif receipt_mode == "RAW":
        expected_scope = {"session_id": session_id, "problem_id": problem_id}
    else:
        raise SessionError("ledger receipt mode mismatch")
    if ledger.get("scope") != expected_scope:
        raise SessionError("ledger receipt scope does not match the session and problem")
    if bindings["ledger_receipt_sha256"] != ledger_digest:
        raise SessionError("session ledger_receipt_sha256 does not match supplied receipt")
    if not controls["answer_sealed_before_coach_view"]:
        raise SessionError("a supplied ledger receipt requires a sealed-answer record")

    if reset_receipt is None:
        if bindings["reset_receipt_sha256"] is not None or controls["state_reset_confirmed"]:
            raise SessionError("reset binding requires the supplied reset receipt")
        return "VERIFIED_WITH_SUPPLIED_LEDGER_RECEIPT"

    reset, reset_digest = _verified_self_digest(
        reset_receipt,
        digest_field="reset_receipt_sha256",
        schema_version="hearthline-learning-reset.v1",
        label="reset receipt",
    )
    expected_reset_keys = {
        "schema_version",
        "from_scope",
        "to_scope",
        "from_receipt_sha256",
        "generation",
        "prior_observations_cleared",
        "prior_requests_cleared",
        "reset_receipt_sha256",
    }
    if set(reset) != expected_reset_keys:
        raise SessionError("reset receipt fields mismatch")
    if reset.get("from_receipt_sha256") != ledger_digest:
        raise SessionError("reset receipt does not link to the supplied ledger receipt")
    if reset.get("from_scope") != ledger.get("scope"):
        raise SessionError("reset receipt from_scope does not match the ledger receipt")
    reset_to_scope = reset.get("to_scope")
    if not isinstance(reset_to_scope, dict):
        raise SessionError("reset receipt to_scope must be an object")
    if receipt_mode == "DIGESTS":
        if set(reset_to_scope) != {"session_id_sha256", "problem_id_sha256"} or any(
            not isinstance(value, str) or SHA256.fullmatch(value) is None
            for value in reset_to_scope.values()
        ):
            raise SessionError("reset receipt to_scope digest fields mismatch")
    elif set(reset_to_scope) != {"session_id", "problem_id"} or any(
        not isinstance(value, str) or OPAQUE_ID.fullmatch(value) is None
        for value in reset_to_scope.values()
    ):
        raise SessionError("reset receipt to_scope raw fields mismatch")
    if reset_to_scope == reset.get("from_scope"):
        raise SessionError("reset receipt does not move to a different scope")
    reset_generation = reset.get("generation")
    if type(reset_generation) is not int or reset_generation != ledger_generation + 1:
        raise SessionError("reset receipt generation does not follow the ledger receipt")
    if reset.get("prior_observations_cleared") is not True:
        raise SessionError("reset receipt does not clear prior observations")
    if reset.get("prior_requests_cleared") is not True:
        raise SessionError("reset receipt does not clear prior requests")
    if bindings["reset_receipt_sha256"] != reset_digest:
        raise SessionError("session reset_receipt_sha256 does not match supplied receipt")
    if controls["state_reset_confirmed"] is not True:
        raise SessionError("a supplied reset receipt requires state_reset_confirmed")
    return "VERIFIED_WITH_SUPPLIED_LEDGER_AND_RESET_RECEIPTS"


def validate_session(
    document: object,
    *,
    ledger_receipt: object | None = None,
    reset_receipt: object | None = None,
) -> dict[str, object]:
    """Validate and return a compact, non-evaluative summary."""

    _scan_for_protected_material(document)
    root = _exact_object(document, ROOT_KEYS, "session root")
    if root["schema_version"] != SCHEMA_VERSION:
        raise SessionError(f"schema_version must be {SCHEMA_VERSION}")
    if root["status"] != STATUS:
        raise SessionError(f"status must be {STATUS}")
    if root["session_mode"] not in MODES:
        raise SessionError(f"session_mode must be one of {sorted(MODES)}")

    source = _exact_object(root["source"], SOURCE_KEYS, "source")
    expected_source = SOURCES[root["session_mode"]]
    if source != expected_source:
        raise SessionError("source must match the pinned locator and version for session_mode")
    if source["kind"] == "PUBLIC_HTTP_REFERENCE":
        _public_url(source["locator"])

    exercise = _exact_object(root["exercise"], EXERCISE_KEYS, "exercise")
    session_id = _trimmed_string(exercise["session_id"], "exercise.session_id", maximum=64)
    problem_id = _trimmed_string(exercise["problem_id"], "exercise.problem_id", maximum=64)
    if OPAQUE_ID.fullmatch(session_id) is None:
        raise SessionError(
            "exercise.session_id must use only letters, numbers, dot, underscore, or hyphen"
        )
    if OPAQUE_ID.fullmatch(problem_id) is None:
        raise SessionError(
            "exercise.problem_id must use only letters, numbers, dot, underscore, or hyphen"
        )
    if root["session_mode"] == "micro_fixture" and problem_id not in MICRO_EPISODE_IDS:
        raise SessionError("micro_fixture exercise.problem_id must name an orientation-deck episode")
    _trimmed_string(exercise["learning_goal"], "exercise.learning_goal")

    budgets = _exact_object(root["budgets"], BUDGET_KEYS, "budgets")
    budget_values = {
        key: _nonnegative_integer(budgets[key], f"budgets.{key}")
        for key in BUDGET_KEYS
    }
    if budget_values["model_calls"] > 1:
        raise SessionError("budgets.model_calls exceeds the public-playground ceiling of one")
    if budget_values["evaluator_runs"] != 0:
        raise SessionError("budgets.evaluator_runs must remain zero")
    if budget_values["candidate_code_executions"] != 0:
        raise SessionError("budgets.candidate_code_executions must remain zero")
    activity = _exact_object(root["activity"], ACTIVITY_KEYS, "activity")
    for key in ACTIVITY_KEYS:
        if _nonnegative_integer(activity[key], f"activity.{key}") != 0:
            raise SessionError(
                f"activity.{key} must remain zero; this scaffold is not a run receipt"
            )

    future_plan = _exact_object(root["future_plan"], FUTURE_PLAN_KEYS, "future_plan")
    plan_status = future_plan["status"]
    description = future_plan["description"]
    if plan_status == "NO_RUN_PLANNED":
        if description is not None or any(budget_values.values()):
            raise SessionError(
                "nonzero run budgets require FUTURE_ONLY_NOT_RUN and an explicit future-plan description"
            )
    elif plan_status == "FUTURE_ONLY_NOT_RUN":
        _trimmed_string(description, "future_plan.description")
    else:
        raise SessionError(
            "future_plan.status must be NO_RUN_PLANNED or FUTURE_ONLY_NOT_RUN"
        )

    bindings, controls = _validate_trace(root["learning_trace"], root["session_mode"])
    receipt_binding_result = _validate_receipt_bindings(
        bindings,
        controls,
        session_id=session_id,
        problem_id=problem_id,
        ledger_receipt=ledger_receipt,
        reset_receipt=reset_receipt,
    )

    provenance = _exact_object(root["provenance"], PROVENANCE_KEYS, "provenance")
    _validate_timestamp(provenance["created_at_utc"])
    if provenance["created_by"] != "tools/new_public_learning_session.py":
        raise SessionError("provenance.created_by must identify the offline generator")
    expected_provenance = {
        "source_is_public": root["session_mode"] != "micro_fixture",
        "network_accessed_by_generator": False,
        "model_invoked_by_generator": False,
        "evaluator_invoked_by_generator": False,
        "candidate_code_executed_by_generator": False,
    }
    for key, expected in expected_provenance.items():
        if provenance[key] is not expected:
            raise SessionError(f"provenance.{key} must be {str(expected).lower()}")

    formal = _exact_object(root["formal_pilot"], FORMAL_PILOT_KEYS, "formal_pilot")
    if formal["experiment_id"] != EXPERIMENT_ID:
        raise SessionError(f"formal_pilot.experiment_id must be {EXPERIMENT_ID}")
    if formal["consumed"] is not False:
        raise SessionError("formal_pilot.consumed must remain false")
    if root["claim_ceiling"] != CLAIM_CEILING:
        raise SessionError("claim_ceiling does not match the public-playground boundary")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "session_mode": root["session_mode"],
        "session_id": session_id,
        "problem_id": problem_id,
        "planned_model_calls": budget_values["model_calls"],
        "receipt_binding_result": receipt_binding_result,
        "formal_pilot_consumed": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="public learning-session JSON")
    parser.add_argument("--ledger-receipt", type=Path)
    parser.add_argument("--reset-receipt", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        ledger_receipt = load_receipt(args.ledger_receipt) if args.ledger_receipt else None
        reset_receipt = load_receipt(args.reset_receipt) if args.reset_receipt else None
        summary = validate_session(
            load_session(args.session),
            ledger_receipt=ledger_receipt,
            reset_receipt=reset_receipt,
        )
    except SessionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
