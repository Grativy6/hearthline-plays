"""Fail-closed, local single-use authorization ledger primitives.

The command-line tools choose the repository's one canonical ignored ledger
path. One locked append reserves and spends the coupled grant-ID/nonce pair;
a separate exclusive completion proof says the artifact-binding phase passed.
A partial, uncertain, or corrupt state remains spent and fails later checks
closed. This is a replay/concurrency guard, not a cryptographic defense
against a malicious filesystem owner.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


_GRANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_NONCE_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
_VALID_SCOPES = {
    "PUBLIC_EVAL_ONCE",
    "KAGGLE_NOTEBOOK_RUN_ONCE",
    "KAGGLE_SUBMIT_ONCE",
}
_RECORD_FIELDS = {
    "schema",
    "grant_id",
    "nonce",
    "scope",
    "grant_sha256",
    "validated_by",
    "consumed_at",
}
_COMPLETION_FIELDS = {
    "schema",
    "grant_id",
    "nonce",
    "scope",
    "grant_sha256",
    "validated_by",
    "completed_at",
}
_VALIDATED_BY = "tools/preflight.py:arc2.external.v1"


class AuthorizationError(RuntimeError):
    """A grant is malformed, absent, already spent, or already claimed."""


def canonical_json_bytes(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AuthorizationError("authorization record is not canonical JSON") from exc
    return (encoded + "\n").encode("utf-8")


def canonical_grant_sha256(grant: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(grant))).hexdigest()


def _identity(grant: Mapping[str, Any]) -> tuple[str, str, str]:
    grant_id = grant.get("grant_id")
    nonce = grant.get("nonce")
    scope = grant.get("scope")
    if not isinstance(grant_id, str) or _GRANT_ID_PATTERN.fullmatch(grant_id) is None:
        raise AuthorizationError("invalid grant identity")
    if not isinstance(nonce, str) or _NONCE_PATTERN.fullmatch(nonce) is None:
        raise AuthorizationError("invalid grant nonce")
    if nonce == "0" * 64:
        raise AuthorizationError("placeholder grant nonce is forbidden")
    if scope not in _VALID_SCOPES:
        raise AuthorizationError("invalid grant scope")
    return grant_id, nonce, scope


def _ledger_file(ledger_root: Path) -> Path:
    return ledger_root / "consumed-grants.jsonl"


def _claim_file(ledger_root: Path, nonce: str) -> Path:
    return ledger_root / "claims" / f"{nonce}.used"


def _completion_file(ledger_root: Path, nonce: str) -> Path:
    return ledger_root / "completions" / f"{nonce}.ready"


def _validate_record(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
        raise AuthorizationError("consumption ledger record is not closed")
    if value.get("schema") != "hearthline-plays.arc2-consumed-grant.v1":
        raise AuthorizationError("consumption ledger record schema is invalid")
    if (
        not isinstance(value.get("grant_id"), str)
        or _GRANT_ID_PATTERN.fullmatch(value["grant_id"]) is None
        or not isinstance(value.get("nonce"), str)
        or _NONCE_PATTERN.fullmatch(value["nonce"]) is None
        or value["nonce"] == "0" * 64
        or value.get("scope") not in _VALID_SCOPES
        or not isinstance(value.get("grant_sha256"), str)
        or _SHA256_PATTERN.fullmatch(value["grant_sha256"]) is None
        or value.get("validated_by") != _VALIDATED_BY
        or not isinstance(value.get("consumed_at"), str)
        or _UTC_PATTERN.fullmatch(value["consumed_at"]) is None
    ):
        raise AuthorizationError("consumption ledger record has invalid identities")
    return value


def _validate_completion(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _COMPLETION_FIELDS:
        raise AuthorizationError("preflight completion proof is not closed")
    if value.get("schema") != "hearthline-plays.arc2-preflight-completion.v1":
        raise AuthorizationError("preflight completion proof schema is invalid")
    if (
        not isinstance(value.get("grant_id"), str)
        or _GRANT_ID_PATTERN.fullmatch(value["grant_id"]) is None
        or not isinstance(value.get("nonce"), str)
        or _NONCE_PATTERN.fullmatch(value["nonce"]) is None
        or value["nonce"] == "0" * 64
        or value.get("scope") not in _VALID_SCOPES
        or not isinstance(value.get("grant_sha256"), str)
        or _SHA256_PATTERN.fullmatch(value["grant_sha256"]) is None
        or value.get("validated_by") != _VALIDATED_BY
        or not isinstance(value.get("completed_at"), str)
        or _UTC_PATTERN.fullmatch(value["completed_at"]) is None
    ):
        raise AuthorizationError("preflight completion proof has invalid identities")
    return value


def _strict_json_from_bytes(payload: bytes, *, label: str) -> object:
    """Decode one strict JSON value while rejecting ambiguous object keys."""

    def object_without_duplicate_keys(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AuthorizationError(f"{label} contains a duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise AuthorizationError(f"{label} contains a non-finite JSON number")

    try:
        text = payload.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=object_without_duplicate_keys,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AuthorizationError(f"{label} contains invalid JSON") from exc


def _records_from_bytes(payload: bytes) -> list[dict[str, Any]]:
    if not payload:
        return []
    if not payload.endswith(b"\n"):
        raise AuthorizationError("consumption ledger has a partial record")
    records: list[dict[str, Any]] = []
    for line in payload[:-1].split(b"\n"):
        record = _validate_record(
            _strict_json_from_bytes(line, label="consumption ledger")
        )
        if line + b"\n" != canonical_json_bytes(record):
            raise AuthorizationError("consumption ledger record is not canonical JSON")
        records.append(record)
    grant_ids = [record["grant_id"] for record in records]
    nonces = [record["nonce"] for record in records]
    if len(grant_ids) != len(set(grant_ids)) or len(nonces) != len(set(nonces)):
        raise AuthorizationError("consumption ledger contains duplicate identities")
    return records


def _read_locked(descriptor: int) -> list[dict[str, Any]]:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    return _records_from_bytes(b"".join(chunks))


def _reject_duplicate(
    records: list[dict[str, Any]], grant_id: str, nonce: str
) -> None:
    if any(
        record["grant_id"] == grant_id or record["nonce"] == nonce
        for record in records
    ):
        raise AuthorizationError("grant identity or nonce is already spent")


def assert_unspent(grant: Mapping[str, Any], ledger_root: Path) -> None:
    """Reject duplicate grant IDs or nonces in the append-only ledger."""

    grant_id, nonce, _ = _identity(grant)
    path = _ledger_file(ledger_root)
    if not path.exists():
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError as exc:
        raise AuthorizationError("cannot open the consumption ledger") from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        _reject_duplicate(_read_locked(descriptor), grant_id, nonce)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def record_preflight_consumption(
    grant: Mapping[str, Any],
    ledger_root: Path,
    *,
    consumed_at: datetime | None = None,
) -> Path:
    """Durably spend a preflight-validated grant ID and nonce as one record."""

    grant_id, nonce, scope = _identity(grant)
    ledger_root.mkdir(parents=True, exist_ok=True)
    path = _ledger_file(ledger_root)
    instant = (consumed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    record = {
        "schema": "hearthline-plays.arc2-consumed-grant.v1",
        "grant_id": grant_id,
        "nonce": nonce,
        "scope": scope,
        "grant_sha256": canonical_grant_sha256(grant),
        "validated_by": _VALIDATED_BY,
        "consumed_at": instant.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    payload = canonical_json_bytes(_validate_record(record))
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise AuthorizationError("cannot open the consumption ledger") from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        _reject_duplicate(_read_locked(descriptor), grant_id, nonce)
        os.lseek(descriptor, 0, os.SEEK_END)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written < 1:
                raise AuthorizationError("consumption ledger append did not complete")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return path


def _exclusive_write(path: Path, payload: bytes, *, exists_message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AuthorizationError(exists_message) from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        # A partial exclusive marker is retained: uncertainty never restores permission.
        raise


def _matching_record(
    grant: Mapping[str, Any], ledger_root: Path
) -> tuple[str, str, str, str]:
    grant_id, nonce, scope = _identity(grant)
    path = _ledger_file(ledger_root)
    if not path.is_file():
        raise AuthorizationError("grant was not recorded by canonical preflight")
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError as exc:
        raise AuthorizationError("cannot open the consumption ledger") from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        records = _read_locked(descriptor)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    expected_hash = canonical_grant_sha256(grant)
    matching = [
        record
        for record in records
        if record["grant_id"] == grant_id and record["nonce"] == nonce
    ]
    if (
        len(matching) != 1
        or matching[0]["scope"] != scope
        or matching[0]["grant_sha256"] != expected_hash
    ):
        raise AuthorizationError("preflight consumption does not match grant")
    return grant_id, nonce, scope, expected_hash


def complete_preflight_consumption(
    grant: Mapping[str, Any],
    ledger_root: Path,
    *,
    completed_at: datetime | None = None,
) -> Path:
    """Record that post-reservation external artifact checks all succeeded."""

    grant_id, nonce, scope, grant_sha256 = _matching_record(grant, ledger_root)
    instant = (completed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    completion = {
        "schema": "hearthline-plays.arc2-preflight-completion.v1",
        "grant_id": grant_id,
        "nonce": nonce,
        "scope": scope,
        "grant_sha256": grant_sha256,
        "validated_by": _VALIDATED_BY,
        "completed_at": instant.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    completion_path = _completion_file(ledger_root, nonce)
    _exclusive_write(
        completion_path,
        canonical_json_bytes(_validate_completion(completion)),
        exists_message="preflight completion proof already exists",
    )
    return completion_path


def _require_completion(
    grant_id: str,
    nonce: str,
    scope: str,
    grant_sha256: str,
    ledger_root: Path,
) -> None:
    path = _completion_file(ledger_root, nonce)
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise AuthorizationError("preflight completion proof is absent") from exc
    if not payload.endswith(b"\n"):
        raise AuthorizationError("preflight completion proof has a partial record")
    completion = _validate_completion(
        _strict_json_from_bytes(payload, label="preflight completion proof")
    )
    if payload != canonical_json_bytes(completion):
        raise AuthorizationError("preflight completion proof is not canonical JSON")
    expected = {
        "grant_id": grant_id,
        "nonce": nonce,
        "scope": scope,
        "grant_sha256": grant_sha256,
    }
    if any(completion[field] != value for field, value in expected.items()):
        raise AuthorizationError("preflight completion proof does not match grant")


def claim_public_evaluation(grant: Mapping[str, Any], ledger_root: Path) -> Path:
    """Claim a completed public-evaluation preflight exactly once."""

    grant_id, nonce, scope = _identity(grant)
    if scope != "PUBLIC_EVAL_ONCE":
        raise AuthorizationError("public evaluation requires PUBLIC_EVAL_ONCE")
    _, _, _, expected_hash = _matching_record(grant, ledger_root)
    _require_completion(grant_id, nonce, scope, expected_hash, ledger_root)
    claim = {
        "schema": "hearthline-plays.arc2-public-eval-claim.v1",
        "grant_id": grant_id,
        "nonce": nonce,
        "grant_sha256": expected_hash,
        "claimed_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }
    claim_path = _claim_file(ledger_root, nonce)
    _exclusive_write(
        claim_path,
        canonical_json_bytes(claim),
        exists_message="public-evaluation grant is already claimed",
    )
    return claim_path
