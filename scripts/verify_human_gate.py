#!/usr/bin/env python3
"""Validate and consume a human gate without performing an external effect.

Both gates bind the exact content-addressed candidate snapshot. Gate B also
binds the canonical Gate-A ledger record, account, kernel, private run receipt,
and submission hash. The local ledger is a fail-closed procedural attestation,
not a signature or proof that a human actually performed an external action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUILD = ROOT / "build"
CONSUMED_ROOT = ROOT / ".hearthline/receipts/gate-consumption"
LEDGER_PATH_NAME = "ledger.json"
RULES_URL = "https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/rules"
COMMON_GRANT_KEYS = {
    "schema", "grant_id", "phase", "decision", "human_actor", "issued_at",
    "expires_at", "nonce", "candidate", "rules", "acknowledgements",
    "stage_evidence",
}
CANDIDATE_KEYS = {
    "commit", "tree", "account_slug", "kernel_id", "accelerator",
    "agent_sha256", "builder_sha256", "notebook_sha256",
    "kernel_metadata_sha256", "source_lock_sha256",
    "candidate_manifest_sha256", "verified_snapshot_sha256",
}
CONSUMPTION_KEYS = {
    "schema", "sequence", "previous_record_sha256", "phase", "grant_id",
    "nonce", "grant_sha256", "candidate", "gate_context", "consumed_at",
    "external_effect_performed_by_this_tool",
}
LEDGER_KEYS = {"schema", "record_count", "head_sha256", "records"}
LEDGER_ENTRY_KEYS = {"sequence", "path", "sha256"}
_VALIDATION_TOKEN = object()


class GateError(RuntimeError):
    """Raised when a gate or ledger invariant fails closed."""


def utc_now() -> datetime:
    """Sample current UTC time at the point an invariant is consumed."""
    return datetime.now(UTC)


def secure_dirfd_available() -> bool:
    """Return whether this host can hold and traverse directories safely."""
    return (
        hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.rename in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and os.rmdir in os.supports_dir_fd
    )


@dataclass(frozen=True)
class ValidatedGate:
    phase: str
    candidate: Mapping[str, Any]
    grant_id: str
    nonce: str
    gate_context: Mapping[str, Any]
    grant_semantic_sha256: str
    issued_at: datetime
    expires_at: datetime
    rules_checked_day: str
    submission_sha256: str | None = None
    _token: object = field(default=None, repr=False, compare=False)
    _seal: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate", MappingProxyType(dict(self.candidate)))
        object.__setattr__(self, "gate_context", MappingProxyType(dict(self.gate_context)))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_environment() -> dict[str, str]:
    """Return a Git environment that cannot consult ambient hooks or remotes."""
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
    return environment


def _git_command(*arguments: str) -> list[str]:
    return [
        "git",
        "-c", "core.fsmonitor=false",
        "-c", f"core.hooksPath={os.devnull}",
        *arguments,
    ]


def _git_identity() -> dict[str, Any]:
    try:
        commit = subprocess.check_output(
            _git_command("rev-parse", "HEAD"),
            cwd=ROOT,
            text=True,
            env=_git_environment(),
        ).strip()
        tree = subprocess.check_output(
            _git_command("rev-parse", "HEAD^{tree}"),
            cwd=ROOT,
            text=True,
            env=_git_environment(),
        ).strip()
        status = subprocess.check_output(
            _git_command("status", "--porcelain", "--untracked-files=normal"),
            cwd=ROOT,
            text=True,
            env=_git_environment(),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GateError("cannot bind the candidate verifier to committed Git") from exc
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "invalid current Git commit")
    require(re.fullmatch(r"[0-9a-f]{40}", tree) is not None, "invalid current Git tree")
    return {"commit": commit, "tree": tree, "worktree_clean": status == ""}


def _git_blob(commit: str, relative: str) -> bytes:
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "invalid verifier commit")
    require(relative == "scripts/verify_candidate.py", "unexpected verifier Git path")
    try:
        return subprocess.check_output(
            _git_command("show", f"{commit}:{relative}"),
            cwd=ROOT,
            env=_git_environment(),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GateError("cannot read the committed candidate verifier") from exc


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GateError(f"value cannot be canonically encoded: {exc}") from exc


def _gate_seal(
    *,
    phase: str,
    candidate: Mapping[str, Any],
    grant_id: str,
    nonce: str,
    gate_context: Mapping[str, Any],
    grant_semantic_sha256: str,
    issued_at: datetime,
    expires_at: datetime,
    rules_checked_day: str,
    submission_sha256: str | None,
) -> str:
    return sha256(canonical_json({
        "phase": phase,
        "candidate": dict(candidate),
        "grant_id": grant_id,
        "nonce": nonce,
        "gate_context": dict(gate_context),
        "grant_semantic_sha256": grant_semantic_sha256,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "rules_checked_day": rules_checked_day,
        "submission_sha256": submission_sha256,
    }))


def make_validated_gate(
    *,
    grant: dict[str, Any],
    phase: str,
    candidate: dict[str, Any],
    gate_context: dict[str, Any],
    issued_at: datetime,
    expires_at: datetime,
    submission_sha256: str | None = None,
) -> ValidatedGate:
    semantic_hash = sha256(canonical_json(grant))
    seal = _gate_seal(
        phase=phase,
        candidate=candidate,
        grant_id=grant["grant_id"],
        nonce=grant["nonce"],
        gate_context=gate_context,
        grant_semantic_sha256=semantic_hash,
        issued_at=issued_at,
        expires_at=expires_at,
        rules_checked_day=grant["rules"]["checked_at"],
        submission_sha256=submission_sha256,
    )
    return ValidatedGate(
        phase=phase,
        candidate=candidate,
        grant_id=grant["grant_id"],
        nonce=grant["nonce"],
        gate_context=gate_context,
        grant_semantic_sha256=semantic_hash,
        issued_at=issued_at,
        expires_at=expires_at,
        rules_checked_day=grant["rules"]["checked_at"],
        submission_sha256=submission_sha256,
        _token=_VALIDATION_TOKEN,
        _seal=seal,
    )


def require_exact_keys(value: Any, keys: Iterable[str], label: str) -> None:
    require(isinstance(value, dict), f"{label} must be an object")
    expected = set(keys)
    actual = set(value)
    require(actual == expected, f"{label} fields: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise GateError(f"non-finite JSON number is forbidden: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise GateError(f"non-finite JSON number is forbidden: {value}")
    return parsed


def loads_strict(data: bytes, label: str) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"{label}: invalid strict UTF-8 JSON: {exc}") from exc


def _open_directory_chain(path: Path, *, create: bool = False) -> int:
    """Open every absolute path component without following a symlink."""
    require(secure_dirfd_available(), "human gates require Linux/POSIX no-follow directory-descriptor support")
    absolute = Path(os.path.abspath(path))
    require(absolute.is_absolute(), "secure directory path must be absolute")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(absolute.anchor, flags)
    try:
        for component in absolute.parts[1:]:
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(component, flags, dir_fd=descriptor)
            info = os.fstat(child)
            require(stat.S_ISDIR(info.st_mode), f"directory component is not real: {component}")
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_regular_at(directory_fd: int, name: str, label: str) -> bytes:
    require("/" not in name and "\\" not in name and name not in {"", ".", ".."}, f"unsafe {label} leaf")
    before_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    require(stat.S_ISREG(before_path.st_mode), f"{label} must be a regular file")
    require(before_path.st_nlink == 1, f"{label} must not be a hard-linked alias")
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        require(
            (before_path.st_dev, before_path.st_ino, before_path.st_size, before_path.st_mtime_ns)
            == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
            f"{label} changed before open",
        )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            f"{label} changed while being read",
        )
        data = b"".join(chunks)
        require(len(data) == after.st_size, f"{label} short read")
        after_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        require(
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            == (after_path.st_dev, after_path.st_ino, after_path.st_size, after_path.st_mtime_ns),
            f"{label} path changed while being read",
        )
        return data
    finally:
        os.close(descriptor)


def _assert_named_directory(path: Path, expected_fd: int, label: str) -> None:
    """Prove that a lexical directory path still names a held directory."""
    check_fd = _open_directory_chain(path)
    try:
        expected = os.fstat(expected_fd)
        actual = os.fstat(check_fd)
        require(
            (expected.st_dev, expected.st_ino) == (actual.st_dev, actual.st_ino),
            f"{label} path was rebound",
        )
    finally:
        os.close(check_fd)


def _private_record_location(path: Path, area: str, label: str) -> tuple[Path, str, str]:
    absolute = Path(os.path.abspath(path))
    root_absolute = Path(os.path.abspath(ROOT))
    try:
        relative = absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise GateError(f"{label} must be inside this repository") from exc
    require(
        len(relative.parts) == 3 and relative.parts[:2] == (".hearthline", area),
        f"{label} must be one direct JSON file in .hearthline/{area}",
    )
    leaf = relative.parts[2]
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,126}\.json", leaf) is not None, f"{label} filename")
    return root_absolute / ".hearthline" / area, leaf, relative.as_posix()


def read_private_record(path: Path, area: str, label: str) -> tuple[bytes, str]:
    directory, leaf, reference = _private_record_location(path, area, label)
    directory_fd = _open_directory_chain(directory)
    try:
        data = _read_regular_at(directory_fd, leaf, label)
        _assert_named_directory(directory, directory_fd, f"{label} directory")
        return data, reference
    finally:
        os.close(directory_fd)


def parse_time(value: Any, label: str) -> datetime:
    require(isinstance(value, str), f"{label} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GateError(f"{label} is not an ISO timestamp") from exc
    require(parsed.tzinfo is not None, f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def validate_candidate(candidate: Any, label: str = "candidate") -> dict[str, Any]:
    require_exact_keys(candidate, CANDIDATE_KEYS, label)
    for key in ("commit", "tree"):
        require(isinstance(candidate[key], str) and re.fullmatch(r"[0-9a-f]{40}", candidate[key]) is not None, f"{label} {key}")
    for key in CANDIDATE_KEYS - {"commit", "tree", "account_slug", "kernel_id", "accelerator"}:
        require(isinstance(candidate[key], str) and re.fullmatch(r"[0-9a-f]{64}", candidate[key]) is not None, f"{label} {key}")
    account = candidate["account_slug"]
    require(isinstance(account, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,62}", account) is not None, f"{label} account_slug")
    require(candidate["kernel_id"] == f"{account}/hearthline-arc3-readiness", f"{label} kernel/account mismatch")
    require(candidate["accelerator"] in {"cpu", "t4", "p100", "rtx6000"}, f"{label} accelerator")
    return dict(candidate)


def candidate_from_verification(verification: dict[str, Any]) -> dict[str, Any]:
    require(verification.get("structural_verification") == "PASS", "candidate verification did not pass")
    require(verification.get("kaggle_stage_ready") is True, "candidate is not ready for Kaggle staging")
    snapshot = verification.get("verified_snapshot")
    require(isinstance(snapshot, dict), "verified candidate snapshot missing")
    candidate = validate_candidate(snapshot.get("candidate_binding"), "verified candidate")
    require(snapshot.get("sha256") == candidate["verified_snapshot_sha256"], "verified snapshot hash mismatch")
    return candidate


def expected_agents_files(verification: dict[str, Any]) -> dict[str, str]:
    """Use only the verifier's committed source-lock projection, never worktree bytes."""
    candidate = candidate_from_verification(verification)
    inputs = verification.get("verified_inputs")
    require_exact_keys(
        inputs,
        {
            "source_lock_sha256", "agents_repository", "agents_commit",
            "agents_files", "agents_license_file", "runtime_versions",
            "runtime_closure_status",
        },
        "verified source inputs",
    )
    require(inputs["source_lock_sha256"] == candidate["source_lock_sha256"], "verified source-lock binding")
    require(inputs["agents_repository"] == "arcprize/ARC-AGI-3-Agents", "verified Agents repository")
    require(inputs["agents_commit"] == "4743e7d0aaae0ded0d98a89a7e282e63564cd58b", "verified Agents commit")
    files = inputs["agents_files"]
    require_exact_keys(
        files,
        {
            "agents/agent.py", "agents/recorder.py", "agents/swarm.py",
            "agents/tracing.py", "main.py",
        },
        "verified Agents files",
    )
    for path, digest in files.items():
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None, f"verified Agents hash: {path}")
    return dict(files)


def expected_agents_license_file(verification: dict[str, Any]) -> dict[str, str]:
    candidate = candidate_from_verification(verification)
    inputs = verification.get("verified_inputs")
    require(isinstance(inputs, dict), "verified source inputs missing")
    require(
        inputs.get("source_lock_sha256") == candidate["source_lock_sha256"],
        "verified source-lock binding",
    )
    license_file = inputs.get("agents_license_file")
    require_exact_keys(license_file, {"LICENSE"}, "verified Agents license file")
    require(
        license_file["LICENSE"]
        == "75c4276c506fd93082b38ad39f67ee97aa859574401ef978e701710c7a40af04",
        "verified Agents license hash",
    )
    return dict(license_file)


def expected_runtime_versions(verification: dict[str, Any]) -> dict[str, str]:
    candidate = candidate_from_verification(verification)
    inputs = verification.get("verified_inputs")
    require(isinstance(inputs, dict), "verified source inputs missing")
    require(inputs.get("source_lock_sha256") == candidate["source_lock_sha256"], "verified source-lock binding")
    versions = inputs.get("runtime_versions")
    require_exact_keys(versions, {"arc-agi", "arcengine"}, "verified runtime versions")
    require(versions == {"arc-agi": "0.9.9", "arcengine": "0.9.3"}, "verified runtime version pins")
    return dict(versions)


def _committed_verifier_bytes() -> tuple[bytes, dict[str, Any]]:
    """Bind one no-follow worktree read to an unchanged, clean Git object."""
    before = _git_identity()
    require(before["worktree_clean"] is True, "worktree must be clean before loading candidate verifier")
    committed = _git_blob(before["commit"], "scripts/verify_candidate.py")
    scripts_fd = _open_directory_chain(ROOT / "scripts")
    try:
        worktree = _read_regular_at(
            scripts_fd,
            "verify_candidate.py",
            "candidate verifier",
        )
    finally:
        os.close(scripts_fd)
    require(worktree == committed, "worktree candidate verifier differs from committed Git object")
    after = _git_identity()
    require(
        after == before and after["worktree_clean"] is True,
        "Git identity changed while binding the candidate verifier",
    )
    return committed, before


def verify_current_candidate(build_dir: Path) -> dict[str, Any]:
    """Execute only exact committed verifier bytes; its snapshot is the gate input."""
    path = ROOT / "scripts/verify_candidate.py"
    verifier_bytes, bound_identity = _committed_verifier_bytes()
    module = ModuleType("hearthline_gate_candidate_verifier")
    module.__file__ = str(path)
    try:
        exec(
            compile(verifier_bytes, str(path), "exec"),
            module.__dict__,
        )
        result = module.verify(build_dir, require_clean=True, materialize=True)
    except Exception as exc:
        raise GateError(f"independent candidate verification failed: {exc}") from exc
    final_verifier_bytes, final_identity = _committed_verifier_bytes()
    require(final_verifier_bytes == verifier_bytes, "candidate verifier changed during gate validation")
    require(final_identity == bound_identity, "Git identity changed during candidate verification")
    candidate = candidate_from_verification(result)
    require(
        candidate["commit"] == bound_identity["commit"]
        and candidate["tree"] == bound_identity["tree"],
        "candidate verification result differs from the bound Git identity",
    )
    return result


def empty_ledger() -> dict[str, Any]:
    return {
        "schema": "hearthline.arc3.gate-consumption-ledger.v1",
        "record_count": 0,
        "head_sha256": None,
        "records": [],
    }


def canonical_consumption_reference(grant_id: str) -> str:
    return f".hearthline/receipts/gate-consumption/{sha256(grant_id.encode('utf-8'))}.json"


def _validate_record(record: Any, path_name: str, previous_hash: str | None, sequence: int) -> None:
    require_exact_keys(record, CONSUMPTION_KEYS, f"consumption record {path_name}")
    require(record["schema"] == "hearthline.arc3.human-grant-consumption.v3", f"consumption record schema: {path_name}")
    require(type(record["sequence"]) is int and record["sequence"] == sequence, f"consumption record sequence: {path_name}")
    require(record["previous_record_sha256"] == previous_hash, f"consumption chain predecessor: {path_name}")
    require(record["phase"] in {"KAGGLE_STAGE", "COMPETITION_IGNITION"}, f"consumption phase: {path_name}")
    require(isinstance(record["grant_id"], str), f"consumption grant_id: {path_name}")
    require(isinstance(record["nonce"], str) and re.fullmatch(r"[0-9a-f]{32}", record["nonce"]) is not None, f"consumption nonce: {path_name}")
    require(isinstance(record["grant_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", record["grant_sha256"]) is not None, f"consumption grant hash: {path_name}")
    validate_candidate(record["candidate"], f"consumption candidate {path_name}")
    consumed = parse_time(record["consumed_at"], f"consumption consumed_at {path_name}")
    require(record["external_effect_performed_by_this_tool"] is False, f"consumption tool effect flag: {path_name}")
    context = record["gate_context"]
    if record["phase"] == "KAGGLE_STAGE":
        require_exact_keys(
            context,
            {
                "account_slug", "kernel_id", "verified_snapshot_sha256",
                "authorization_issued_at", "authorization_expires_at",
                "rules_checked_day",
            },
            f"Gate A context {path_name}",
        )
        require(context["account_slug"] == record["candidate"]["account_slug"], f"Gate A account context {path_name}")
        require(context["kernel_id"] == record["candidate"]["kernel_id"], f"Gate A kernel context {path_name}")
        require(context["verified_snapshot_sha256"] == record["candidate"]["verified_snapshot_sha256"], f"Gate A snapshot context {path_name}")
        authorization_issued = parse_time(context["authorization_issued_at"], f"Gate A issued_at {path_name}")
        authorization_expires = parse_time(context["authorization_expires_at"], f"Gate A expires_at {path_name}")
        require(authorization_issued <= consumed < authorization_expires, f"Gate A consumption outside authorization window {path_name}")
        require(
            authorization_issued.date() == consumed.date() == authorization_expires.date(),
            f"Gate A authorization spans a UTC day {path_name}",
        )
        require(context["rules_checked_day"] == consumed.date().isoformat(), f"Gate A rules day mismatch {path_name}")
    else:
        require_exact_keys(
            context,
            {
                "account_slug", "kernel_id", "gate_a_grant_id",
                "gate_a_grant_sha256", "gate_a_consumption_receipt_sha256",
                "stage_receipt_path", "stage_receipt_sha256",
                "submission_sha256", "utc_submission_day",
            },
            f"Gate B context {path_name}",
        )
        require(context["account_slug"] == record["candidate"]["account_slug"], f"Gate B account context {path_name}")
        require(context["kernel_id"] == record["candidate"]["kernel_id"], f"Gate B kernel context {path_name}")
        require(isinstance(context["gate_a_grant_id"], str), f"Gate B Gate-A ID {path_name}")
        require(re.fullmatch(r"[0-9a-f]{64}", str(context["gate_a_grant_sha256"])) is not None, f"Gate B Gate-A grant hash {path_name}")
        require(re.fullmatch(r"[0-9a-f]{64}", str(context["gate_a_consumption_receipt_sha256"])) is not None, f"Gate B Gate-A receipt hash {path_name}")
        require(
            isinstance(context["stage_receipt_path"], str)
            and re.fullmatch(r"\.hearthline/receipts/[A-Za-z0-9][A-Za-z0-9._-]{0,126}\.json", context["stage_receipt_path"]) is not None,
            f"Gate B stage receipt path {path_name}",
        )
        require(re.fullmatch(r"[0-9a-f]{64}", str(context["stage_receipt_sha256"])) is not None, f"Gate B stage hash {path_name}")
        require(re.fullmatch(r"[0-9a-f]{64}", str(context["submission_sha256"])) is not None, f"Gate B submission hash {path_name}")
        try:
            date.fromisoformat(context["utc_submission_day"])
        except (TypeError, ValueError) as exc:
            raise GateError(f"Gate B UTC day {path_name}") from exc
        require(context["utc_submission_day"] == consumed.date().isoformat(), f"Gate B UTC day/consumption mismatch {path_name}")


def _ledger_inventory(root_fd: int, *, lock_owned: bool) -> set[str]:
    inventory = set(os.listdir(root_fd))
    require(
        not any(name.startswith(".pending-") for name in inventory),
        "partial consumption record exists; fail closed for manual reconciliation",
    )
    allowed = {
        name for name in inventory
        if name == LEDGER_PATH_NAME or re.fullmatch(r"[0-9a-f]{64}\.json", name) is not None
    }
    if ".ledger.lock" in inventory:
        lock_info = os.stat(".ledger.lock", dir_fd=root_fd, follow_symlinks=False)
        require(stat.S_ISDIR(lock_info.st_mode), "consumption ledger lock must be a real directory")
        allowed.add(".ledger.lock")
    require(inventory == allowed, "consumption ledger contains an unrecognized entry; fail closed")
    require(lock_owned == (".ledger.lock" in inventory), "consumption ledger lock state mismatch; fail closed")
    return inventory


def load_consumption_ledger(
    *,
    lock_owned: bool = False,
    root_fd: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    close_root = False
    if root_fd is None:
        if not secure_dirfd_available() and not CONSUMED_ROOT.exists():
            return [], empty_ledger()
        try:
            root_fd = _open_directory_chain(CONSUMED_ROOT)
        except FileNotFoundError:
            return [], empty_ledger()
        close_root = True
    try:
        inventory = _ledger_inventory(root_fd, lock_owned=lock_owned)
        json_names = sorted(
            name for name in inventory
            if re.fullmatch(r"[0-9a-f]{64}\.json", name) is not None
        )
        if LEDGER_PATH_NAME not in inventory:
            require(not json_names, "consumption records exist without a ledger; fail closed")
            return [], empty_ledger()
        ledger_bytes = _read_regular_at(root_fd, LEDGER_PATH_NAME, "consumption ledger")
        ledger = loads_strict(ledger_bytes, "consumption ledger")
        require_exact_keys(ledger, LEDGER_KEYS, "consumption ledger")
        require(ledger["schema"] == "hearthline.arc3.gate-consumption-ledger.v1", "consumption ledger schema")
        require(type(ledger["record_count"]) is int and ledger["record_count"] >= 0, "consumption ledger count")
        require(isinstance(ledger["records"], list) and len(ledger["records"]) == ledger["record_count"], "consumption ledger records/count mismatch")
        require(ledger["head_sha256"] is None if not ledger["records"] else re.fullmatch(r"[0-9a-f]{64}", str(ledger["head_sha256"])) is not None, "consumption ledger head")
        listed_names: list[str] = []
        record_bytes_by_name: dict[str, bytes] = {}
        records: list[dict[str, Any]] = []
        previous_hash: str | None = None
        for sequence, entry in enumerate(ledger["records"], start=1):
            require_exact_keys(entry, LEDGER_ENTRY_KEYS, f"ledger entry {sequence}")
            require(type(entry["sequence"]) is int and entry["sequence"] == sequence, f"ledger entry sequence {sequence}")
            path_name = entry["path"]
            require(isinstance(path_name, str) and re.fullmatch(r"[0-9a-f]{64}\.json", path_name) is not None, f"ledger entry path {sequence}")
            require(isinstance(entry["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is not None, f"ledger entry hash {sequence}")
            require(path_name not in listed_names, f"duplicate ledger record path: {path_name}")
            listed_names.append(path_name)
            record_bytes = _read_regular_at(root_fd, path_name, f"consumption record {path_name}")
            record_bytes_by_name[path_name] = record_bytes
            record_hash = sha256(record_bytes)
            require(record_hash == entry["sha256"], f"consumption record hash mismatch: {path_name}")
            record = loads_strict(record_bytes, f"consumption record {path_name}")
            _validate_record(record, path_name, previous_hash, sequence)
            require(path_name == Path(canonical_consumption_reference(record["grant_id"])).name, f"noncanonical consumption record path: {path_name}")
            records.append(record)
            previous_hash = record_hash
        require(set(json_names) == set(listed_names), "consumption ledger inventory mismatch; fail closed")
        require(ledger["head_sha256"] == previous_hash, "consumption ledger head mismatch; fail closed")
        grant_ids = [record["grant_id"] for record in records]
        nonces = [record["nonce"] for record in records]
        require(len(grant_ids) == len(set(grant_ids)), "duplicate consumed grant_id in ledger")
        require(len(nonces) == len(set(nonces)), "duplicate consumed nonce in ledger")
        competition_days = [
            record["gate_context"]["utc_submission_day"]
            for record in records
            if record["phase"] == "COMPETITION_IGNITION"
        ]
        require(
            len(competition_days) == len(set(competition_days)),
            "duplicate Gate B UTC submission day in ledger",
        )

        # The lock is advisory to this tool, so prove the closed inventory and
        # bytes remained stable through the entire replay measurement.
        require(_ledger_inventory(root_fd, lock_owned=lock_owned) == inventory, "consumption ledger inventory changed while reading")
        require(_read_regular_at(root_fd, LEDGER_PATH_NAME, "consumption ledger") == ledger_bytes, "consumption ledger changed while reading")
        for path_name, record_bytes in record_bytes_by_name.items():
            require(_read_regular_at(root_fd, path_name, f"consumption record {path_name}") == record_bytes, f"consumption record changed while reading: {path_name}")

        # Every Gate B entry must refer to exactly one earlier Gate A entry.
        for index, record in enumerate(records):
            if record["phase"] != "COMPETITION_IGNITION":
                continue
            context = record["gate_context"]
            parents = [
                (parent_index, parent)
                for parent_index, parent in enumerate(records[:index])
                if parent["phase"] == "KAGGLE_STAGE"
                and parent["grant_id"] == context["gate_a_grant_id"]
            ]
            require(len(parents) == 1, "Gate B ledger record has no unique earlier Gate A parent")
            parent_index, parent = parents[0]
            require(parent["candidate"] == record["candidate"], "Gate B ledger candidate differs from Gate A")
            require(parent["grant_sha256"] == context["gate_a_grant_sha256"], "Gate B ledger Gate-A grant hash mismatch")
            require(
                ledger["records"][parent_index]["sha256"] == context["gate_a_consumption_receipt_sha256"],
                "Gate B ledger Gate-A receipt hash mismatch",
            )
            require(parent["gate_context"]["account_slug"] == context["account_slug"], "Gate B ledger account differs from Gate A")
            require(parent["gate_context"]["kernel_id"] == context["kernel_id"], "Gate B ledger kernel differs from Gate A")
        return records, ledger
    finally:
        if close_root:
            os.close(root_fd)


def consumption_records(*, lock_owned: bool = False) -> list[dict[str, Any]]:
    return load_consumption_ledger(lock_owned=lock_owned)[0]


def assert_not_consumed(grant_id: str, nonce: str, *, lock_owned: bool = False) -> None:
    for record in consumption_records(lock_owned=lock_owned):
        require(record["grant_id"] != grant_id, "grant_id is already consumed")
        require(record["nonce"] != nonce, "grant nonce is already consumed")


def assert_competition_day_unused(
    day: date,
    *,
    lock_owned: bool = False,
    records: list[dict[str, Any]] | None = None,
) -> None:
    selected = consumption_records(lock_owned=lock_owned) if records is None else records
    for record in selected:
        if record["phase"] == "COMPETITION_IGNITION":
            require(record["gate_context"]["utc_submission_day"] != day.isoformat(), "a Gate B grant was already consumed on this UTC day")


def validate_common(
    grant: dict[str, Any],
    expected_phase: str,
    expected_candidate: dict[str, Any],
    now: datetime,
    ledger_state: tuple[list[dict[str, Any]], dict[str, Any]] | None = None,
) -> tuple[datetime, datetime]:
    require_exact_keys(grant, COMMON_GRANT_KEYS, "grant")
    require(grant["schema"] == "hearthline.arc3.human-grant.v3", "grant schema")
    grant_id = grant["grant_id"]
    require(
        isinstance(grant_id, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}", grant_id) is not None
        and "REPLACE" not in grant_id,
        "concrete grant_id required",
    )
    require(grant["phase"] == expected_phase, "wrong grant phase")
    require(grant["decision"] == "AUTHORIZE_ONCE", "decision must be AUTHORIZE_ONCE")
    require_exact_keys(grant["human_actor"], {"name", "attested_by_human"}, "human_actor")
    require(isinstance(grant["human_actor"]["name"], str) and grant["human_actor"]["name"].strip() and "REPLACE" not in grant["human_actor"]["name"], "human actor name required")
    require(grant["human_actor"]["attested_by_human"] is True, "human attestation required")
    nonce = grant["nonce"]
    require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{32}", nonce) is not None, "nonce must be 32 lowercase hex characters")
    require(validate_candidate(grant["candidate"], "grant candidate") == expected_candidate, "grant candidate hashes do not match the verified snapshot")

    issued = parse_time(grant["issued_at"], "issued_at")
    expires = parse_time(grant["expires_at"], "expires_at")
    maximum = timedelta(hours=2 if expected_phase == "KAGGLE_STAGE" else 1)
    require(issued <= now < expires, "grant is not currently active")
    require(timedelta(0) < expires - issued <= maximum, "grant lifetime exceeds phase ceiling")
    require(
        issued.date() == now.date() == expires.date(),
        f"{expected_phase} issuance, consumption, and expiry must stay on one UTC day",
    )

    rules = grant["rules"]
    require_exact_keys(rules, {"locator", "checked_at", "submissions_per_day", "final_submissions"}, "rules")
    require(rules["locator"] == RULES_URL, "live rules locator mismatch")
    require(rules["checked_at"] == now.date().isoformat(), "live rules must be checked today in UTC")
    require(type(rules["submissions_per_day"]) is int and rules["submissions_per_day"] == 1, "safe daily limit must be integer one")
    require(type(rules["final_submissions"]) is int and rules["final_submissions"] == 2, "final submission count must be integer two")
    records = consumption_records() if ledger_state is None else ledger_state[0]
    for record in records:
        require(record["grant_id"] != grant_id, "grant_id is already consumed")
        require(record["nonce"] != nonce, "grant nonce is already consumed")
    if expected_phase == "COMPETITION_IGNITION":
        assert_competition_day_unused(now.date(), records=records)
    return issued, expires


def validate_stage(
    grant: dict[str, Any],
    verification: dict[str, Any],
    now: datetime,
    ledger_state: tuple[list[dict[str, Any]], dict[str, Any]] | None = None,
) -> ValidatedGate:
    expected = candidate_from_verification(verification)
    issued, expires = validate_common(grant, "KAGGLE_STAGE", expected, now, ledger_state)
    require(grant["stage_evidence"] is None, "Phase A cannot contain stage evidence")
    acknowledgements = grant["acknowledgements"]
    require_exact_keys(
        acknowledgements,
        {"terms_and_eligibility_reviewed", "private_kernel_stage_only", "stage_does_not_authorize_competition_ignition", "account_slug", "kernel_id"},
        "Phase A acknowledgements",
    )
    for key in ("terms_and_eligibility_reviewed", "private_kernel_stage_only", "stage_does_not_authorize_competition_ignition"):
        require(acknowledgements[key] is True, f"Phase A acknowledgement required: {key}")
    require(acknowledgements["account_slug"] == expected["account_slug"], "Phase A account differs from verified candidate")
    require(acknowledgements["kernel_id"] == expected["kernel_id"], "Phase A kernel differs from verified candidate")
    return make_validated_gate(
        grant=grant,
        phase="KAGGLE_STAGE",
        candidate=expected,
        gate_context={
            "account_slug": expected["account_slug"],
            "kernel_id": expected["kernel_id"],
            "verified_snapshot_sha256": expected["verified_snapshot_sha256"],
            "authorization_issued_at": issued.isoformat(),
            "authorization_expires_at": expires.isoformat(),
            "rules_checked_day": grant["rules"]["checked_at"],
        },
        issued_at=issued,
        expires_at=expires,
    )


def validate_gate_a_lineage(
    gate_a: Any,
    expected_candidate: dict[str, Any],
    kernel_id: str,
    stage_recorded: datetime,
    ledger_state: tuple[list[dict[str, Any]], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], str]:
    require_exact_keys(
        gate_a,
        {"grant_id", "nonce", "grant_sha256", "consumption_receipt_path", "consumption_receipt_sha256", "account_slug", "kernel_id"},
        "Gate A lineage",
    )
    grant_id = gate_a["grant_id"]
    nonce = gate_a["nonce"]
    require(isinstance(grant_id, str), "Gate A grant_id")
    require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{32}", nonce) is not None, "Gate A nonce")
    reference = canonical_consumption_reference(grant_id)
    require(gate_a["consumption_receipt_path"] == reference, "Gate A consumption path")
    records, ledger = load_consumption_ledger() if ledger_state is None else ledger_state
    matches = [
        (index, record)
        for index, record in enumerate(records)
        if record["grant_id"] == grant_id
    ]
    require(len(matches) == 1, "Gate A consumption record missing or duplicated")
    index, record = matches[0]
    receipt_sha = ledger["records"][index]["sha256"]
    require(gate_a["consumption_receipt_sha256"] == receipt_sha, "Gate A consumption receipt hash")
    require(record["phase"] == "KAGGLE_STAGE", "Gate A consumption phase")
    require(record["nonce"] == nonce, "Gate A nonce mismatch")
    require(record["grant_sha256"] == gate_a["grant_sha256"], "Gate A grant hash mismatch")
    require(record["candidate"] == expected_candidate, "Gate A candidate mismatch")
    require(gate_a["account_slug"] == record["gate_context"]["account_slug"] == expected_candidate["account_slug"], "Gate A account mismatch")
    require(gate_a["kernel_id"] == record["gate_context"]["kernel_id"] == kernel_id == expected_candidate["kernel_id"], "Gate A kernel mismatch")
    consumed = parse_time(record["consumed_at"], "Gate A consumed_at")
    authorization_expires = parse_time(
        record["gate_context"]["authorization_expires_at"],
        "Gate A authorization_expires_at",
    )
    require(consumed < stage_recorded, "stage result did not strictly follow Gate A consumption")
    require(stage_recorded < authorization_expires, "stage result was recorded at or after Gate A authorization expiry")
    require(
        stage_recorded.date().isoformat() == record["gate_context"]["rules_checked_day"],
        "stage result is outside Gate A rules UTC day",
    )
    return record, receipt_sha


def validate_competition(
    grant: dict[str, Any],
    verification: dict[str, Any],
    stage_receipt: dict[str, Any],
    stage_receipt_sha256: str,
    stage_receipt_reference: str,
    now: datetime,
    ledger_state: tuple[list[dict[str, Any]], dict[str, Any]] | None = None,
) -> ValidatedGate:
    expected = candidate_from_verification(verification)
    verified_inputs = verification.get("verified_inputs")
    require(
        isinstance(verified_inputs, dict)
        and verified_inputs.get("runtime_closure_status")
        == "FROZEN_POST_STAGE_SUCCESSOR",
        "RUNTIME_CLOSURE_UNFROZEN: Gate B requires a reviewed post-Stage-A successor candidate",
    )
    issued, expires = validate_common(
        grant, "COMPETITION_IGNITION", expected, now, ledger_state
    )
    require_exact_keys(grant["stage_evidence"], {"receipt_path", "receipt_sha256"}, "stage evidence")
    require(grant["stage_evidence"]["receipt_path"] == stage_receipt_reference, "stage receipt path mismatch")
    require(grant["stage_evidence"]["receipt_sha256"] == stage_receipt_sha256, "stage receipt hash mismatch")
    require_exact_keys(stage_receipt, {
        "schema", "status", "candidate", "kernel_id", "kernel_run_id",
        "kernel_visibility", "internet_enabled", "output_reviewed", "submission",
        "recorded_by_human", "credential_material_recorded",
        "external_effect_performed_by_gate_tool", "gate_a", "runtime_inventory",
        "recorded_at", "claim_ceiling",
    }, "stage receipt")
    require(stage_receipt["schema"] == "hearthline.arc3.kaggle-stage-result.v3", "stage receipt schema")
    require(stage_receipt["status"] == "COMPLETE", "private kernel stage is not complete")
    require(validate_candidate(stage_receipt["candidate"], "stage candidate") == expected, "stage receipt candidate mismatch")
    kernel_id = stage_receipt["kernel_id"]
    require(kernel_id == expected["kernel_id"], "stage kernel differs from verified candidate")
    require(isinstance(stage_receipt["kernel_run_id"], str) and stage_receipt["kernel_run_id"].strip() and "REPLACE" not in stage_receipt["kernel_run_id"], "stage kernel run ID")
    require(stage_receipt["kernel_visibility"] == "PRIVATE", "staged kernel must remain private")
    require(stage_receipt["internet_enabled"] is False, "staged kernel internet must remain disabled")
    require(stage_receipt["output_reviewed"] is True, "staged output must be reviewed")
    require_exact_keys(stage_receipt["submission"], {"name", "sha256"}, "stage submission")
    require(stage_receipt["submission"]["name"] == "submission.parquet", "exact submission output not selected")
    submission_sha = stage_receipt["submission"]["sha256"]
    require(isinstance(submission_sha, str) and re.fullmatch(r"[0-9a-f]{64}", submission_sha) is not None, "submission hash required")
    require(stage_receipt["recorded_by_human"] is True, "stage result must be recorded by a human")
    require(stage_receipt["credential_material_recorded"] is False, "stage receipt may not contain credentials")
    require(stage_receipt["external_effect_performed_by_gate_tool"] is False, "gate tool cannot claim the stage effect")
    require(isinstance(stage_receipt["claim_ceiling"], str) and stage_receipt["claim_ceiling"].strip(), "stage receipt claim ceiling")

    runtime = stage_receipt["runtime_inventory"]
    require_exact_keys(runtime, {
        "captured_from", "complete", "python_version", "distributions",
        "agents_repository", "agents_expected_commit", "agents_files",
        "agents_license_file", "reviewed_by_human",
    }, "runtime inventory")
    require(runtime["captured_from"] == "HEARTHLINE_STAGE_INVENTORY", "runtime inventory source")
    require(runtime["complete"] is True, "runtime inventory must be complete")
    require(re.fullmatch(r"3\.12\.\d+", str(runtime["python_version"])) is not None, "private runtime must use Python 3.12")
    require(isinstance(runtime["distributions"], list) and runtime["distributions"], "resolved distribution inventory required")
    names: list[str] = []
    for distribution in runtime["distributions"]:
        require_exact_keys(distribution, {"name", "version"}, "distribution record")
        require(
            isinstance(distribution["name"], str)
            and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", distribution["name"])
            is not None
            and distribution["name"]
            == re.sub(r"[-_.]+", "-", distribution["name"]).lower(),
            "PEP 503 canonical distribution name",
        )
        require(isinstance(distribution["version"], str) and distribution["version"].strip(), "resolved distribution version")
        names.append(distribution["name"])
    require(len(names) == len(set(names)), "resolved distribution names must be unique")
    versions = {row["name"]: row["version"] for row in runtime["distributions"]}
    require({"arc-agi", "arcengine", "python-dotenv"} <= set(names), "starter distributions missing from runtime inventory")
    for name, version in expected_runtime_versions(verification).items():
        require(versions.get(name) == version, f"private runtime version mismatch: {name}")
    require(runtime["agents_repository"] == "arcprize/ARC-AGI-3-Agents", "Agents repository identity")
    require(runtime["agents_expected_commit"] == "4743e7d0aaae0ded0d98a89a7e282e63564cd58b", "Agents expected commit")
    require(runtime["agents_files"] == expected_agents_files(verification), "platform Agents files differ from source lock")
    require(
        runtime["agents_license_file"]
        == expected_agents_license_file(verification),
        "platform Agents license differs from source lock",
    )
    require(runtime["reviewed_by_human"] is True, "runtime inventory human review required")

    recorded = parse_time(stage_receipt["recorded_at"], "stage recorded_at")
    gate_a_record, gate_a_receipt_sha = validate_gate_a_lineage(
        stage_receipt["gate_a"],
        expected,
        kernel_id,
        recorded,
        ledger_state,
    )
    require(recorded <= parse_time(grant["issued_at"], "issued_at"), "Phase B grant must follow the stage receipt")
    acknowledgements = grant["acknowledgements"]
    require_exact_keys(acknowledgements, {
        "stage_run_complete", "stage_output_reviewed", "remaining_daily_submission_confirmed",
        "manual_ui_only", "selected_output", "account_slug", "kernel_id",
    }, "Phase B acknowledgements")
    for key in ("stage_run_complete", "stage_output_reviewed", "remaining_daily_submission_confirmed", "manual_ui_only"):
        require(acknowledgements[key] is True, f"Phase B acknowledgement required: {key}")
    require(acknowledgements["selected_output"] == "submission.parquet", "Phase B must name submission.parquet")
    require(acknowledgements["account_slug"] == gate_a_record["gate_context"]["account_slug"] == expected["account_slug"], "Phase B account differs from Gate A")
    require(acknowledgements["kernel_id"] == gate_a_record["gate_context"]["kernel_id"] == kernel_id, "Phase B kernel differs from Gate A")
    return make_validated_gate(
        grant=grant,
        phase="COMPETITION_IGNITION",
        candidate=expected,
        gate_context={
            "account_slug": expected["account_slug"],
            "kernel_id": expected["kernel_id"],
            "gate_a_grant_id": gate_a_record["grant_id"],
            "gate_a_grant_sha256": gate_a_record["grant_sha256"],
            "gate_a_consumption_receipt_sha256": gate_a_receipt_sha,
            "stage_receipt_path": stage_receipt_reference,
            "stage_receipt_sha256": stage_receipt_sha256,
            "submission_sha256": submission_sha,
            "utc_submission_day": now.date().isoformat(),
        },
        issued_at=issued,
        expires_at=expires,
        submission_sha256=submission_sha,
    )


def _write_pending_at(root_fd: int, name: str, data: bytes) -> None:
    require("/" not in name and "\\" not in name and name not in {"", ".", ".."}, "unsafe pending ledger leaf")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, 0o600, dir_fd=root_fd)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _assert_gate_seal(result: ValidatedGate) -> None:
    expected = _gate_seal(
        phase=result.phase,
        candidate=result.candidate,
        grant_id=result.grant_id,
        nonce=result.nonce,
        gate_context=result.gate_context,
        grant_semantic_sha256=result.grant_semantic_sha256,
        issued_at=result.issued_at,
        expires_at=result.expires_at,
        rules_checked_day=result.rules_checked_day,
        submission_sha256=result.submission_sha256,
    )
    require(result._seal == expected, "validated gate was altered after validation")


def _assert_gate_a_locked(
    result: ValidatedGate,
    records: list[dict[str, Any]],
    ledger: dict[str, Any],
) -> None:
    context = result.gate_context
    matches = [
        (index, record)
        for index, record in enumerate(records)
        if record["phase"] == "KAGGLE_STAGE"
        and record["grant_id"] == context["gate_a_grant_id"]
    ]
    require(len(matches) == 1, "sealed Gate A parent missing or duplicated under ledger lock")
    index, record = matches[0]
    require(record["candidate"] == dict(result.candidate), "sealed Gate A candidate changed before Gate B consumption")
    require(record["grant_sha256"] == context["gate_a_grant_sha256"], "sealed Gate A grant hash changed before Gate B consumption")
    require(
        ledger["records"][index]["sha256"] == context["gate_a_consumption_receipt_sha256"],
        "sealed Gate A receipt hash changed before Gate B consumption",
    )
    require(record["gate_context"]["account_slug"] == context["account_slug"], "sealed Gate A account changed before Gate B consumption")
    require(record["gate_context"]["kernel_id"] == context["kernel_id"], "sealed Gate A kernel changed before Gate B consumption")


def consume(
    result: ValidatedGate,
    grant_bytes: bytes,
    build_dir: Path = DEFAULT_BUILD,
) -> Path:
    require(isinstance(result, ValidatedGate) and result._token is _VALIDATION_TOKEN, "gate result was not produced by this validation process")
    _assert_gate_seal(result)
    grant = loads_strict(grant_bytes, "consumed human grant")
    require(isinstance(grant, dict), "consumed human grant must be an object")
    require(
        sha256(canonical_json(grant)) == result.grant_semantic_sha256,
        "consumed grant bytes do not match the validated grant",
    )

    root_fd = _open_directory_chain(CONSUMED_ROOT, create=True)
    try:
        try:
            os.mkdir(".ledger.lock", mode=0o700, dir_fd=root_fd)
        except FileExistsError as exc:
            raise GateError("consumption ledger is locked; fail closed") from exc
        touched = False
        try:
            records, ledger = load_consumption_ledger(lock_owned=True, root_fd=root_fd)
            locked_now = utc_now()
            fresh_verification = verify_current_candidate(build_dir)
            require(
                candidate_from_verification(fresh_verification) == dict(result.candidate),
                "candidate changed after grant validation",
            )
            ledger_state = (records, ledger)
            stage_bytes: bytes | None = None
            stage_reference: str | None = None
            if result.phase == "KAGGLE_STAGE":
                revalidated = validate_stage(
                    grant,
                    fresh_verification,
                    locked_now,
                    ledger_state,
                )
            elif result.phase == "COMPETITION_IGNITION":
                evidence = grant.get("stage_evidence")
                require(isinstance(evidence, dict), "Gate B stage evidence missing during consumption")
                reference = evidence.get("receipt_path")
                require(isinstance(reference, str), "Gate B stage receipt path missing during consumption")
                stage_bytes, stage_reference = read_private_record(
                    ROOT / reference,
                    "receipts",
                    "stage receipt",
                )
                revalidated = validate_competition(
                    grant,
                    fresh_verification,
                    loads_strict(stage_bytes, "stage receipt"),
                    sha256(stage_bytes),
                    stage_reference,
                    locked_now,
                    ledger_state,
                )
            else:
                raise GateError("validated gate phase is not recognized")
            require(
                revalidated._seal == result._seal,
                "gate does not match a fresh full validation under the ledger lock",
            )
            if result.phase == "COMPETITION_IGNITION":
                _assert_gate_a_locked(result, records, ledger)
                locked_stage_bytes, locked_stage_reference = read_private_record(
                    ROOT / result.gate_context["stage_receipt_path"],
                    "receipts",
                    "stage receipt",
                )
                require(locked_stage_reference == stage_reference == result.gate_context["stage_receipt_path"], "sealed stage receipt path changed")
                require(locked_stage_bytes == stage_bytes, "sealed stage receipt changed during locked consumption")
                require(sha256(locked_stage_bytes) == result.gate_context["stage_receipt_sha256"], "sealed stage receipt bytes changed")
            sequence = len(records) + 1
            previous = ledger["head_sha256"]
            record = {
                "schema": "hearthline.arc3.human-grant-consumption.v3",
                "sequence": sequence,
                "previous_record_sha256": previous,
                "phase": result.phase,
                "grant_id": result.grant_id,
                "nonce": result.nonce,
                "grant_sha256": sha256(grant_bytes),
                "candidate": dict(result.candidate),
                "gate_context": dict(result.gate_context),
                "consumed_at": locked_now.isoformat(),
                "external_effect_performed_by_this_tool": False,
            }
            record_bytes = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
            record_hash = sha256(record_bytes)
            path_name = Path(canonical_consumption_reference(result.grant_id)).name
            require(path_name not in set(os.listdir(root_fd)), "canonical consumption path already exists")
            next_ledger = {
                "schema": "hearthline.arc3.gate-consumption-ledger.v1",
                "record_count": sequence,
                "head_sha256": record_hash,
                "records": [*ledger["records"], {"sequence": sequence, "path": path_name, "sha256": record_hash}],
            }
            ledger_bytes = (json.dumps(next_ledger, indent=2, sort_keys=True) + "\n").encode("utf-8")
            pending_record = f".pending-record-{sequence}-{path_name}"
            pending_ledger = f".pending-ledger-{sequence}.json"
            _write_pending_at(root_fd, pending_record, record_bytes)
            _write_pending_at(root_fd, pending_ledger, ledger_bytes)
            touched = True
            os.rename(pending_record, path_name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            os.rename(pending_ledger, LEDGER_PATH_NAME, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            os.fsync(root_fd)
            load_consumption_ledger(lock_owned=True, root_fd=root_fd)
            _assert_named_directory(CONSUMED_ROOT, root_fd, "consumption ledger root")
            touched = False
            return CONSUMED_ROOT / path_name
        finally:
            # Any interrupted two-file update retains its pending/lock markers
            # and therefore fails closed until a human reconciles it.
            if not touched:
                try:
                    os.rmdir(".ledger.lock", dir_fd=root_fd)
                except FileNotFoundError:
                    pass
    finally:
        os.close(root_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("stage", "competition"), required=True)
    parser.add_argument("--grant", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--stage-receipt", type=Path)
    parser.add_argument("--consume", action="store_true")
    args = parser.parse_args()

    if os.getenv("CI"):
        raise SystemExit("verify_human_gate: human gates are disabled in CI")
    ambient = [name for name in ("KAGGLE_API_TOKEN", "KAGGLE_USERNAME", "KAGGLE_KEY") if os.getenv(name)]
    if ambient:
        raise SystemExit("verify_human_gate: clear ambient Kaggle credentials before gate validation")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise SystemExit("verify_human_gate: an interactive human terminal is required")
    if not args.consume:
        raise SystemExit("verify_human_gate: --consume is required for a one-use gate")

    if not secure_dirfd_available():
        raise SystemExit(
            "verify_human_gate: operational gates require a Linux/POSIX host with no-follow directory-descriptor support"
        )
    try:
        grant_bytes, _ = read_private_record(args.grant, "grants", "human grant")
        grant = loads_strict(grant_bytes, "human grant")
        verification = verify_current_candidate(args.build_dir)
        now = utc_now()
        if args.phase == "stage":
            require(args.stage_receipt is None, "Phase A does not accept a stage receipt")
            result = validate_stage(grant, verification, now)
        else:
            require(args.stage_receipt is not None, "Phase B requires --stage-receipt")
            stage_bytes, stage_reference = read_private_record(args.stage_receipt, "receipts", "stage receipt")
            result = validate_competition(
                grant,
                verification,
                loads_strict(stage_bytes, "stage receipt"),
                sha256(stage_bytes),
                stage_reference,
                now,
            )
        path = consume(result, grant_bytes, args.build_dir)
    except (OSError, KeyError, GateError) as exc:
        raise SystemExit(f"verify_human_gate: {exc}") from exc

    candidate = result.candidate
    print(json.dumps({
        "status": "HUMAN_GATE_CONSUMED_NO_EXTERNAL_EFFECT",
        "phase": result.phase,
        "consumption_receipt": str(path.relative_to(ROOT)),
        "verified_snapshot_sha256": candidate["verified_snapshot_sha256"],
        "verified_snapshot_path": verification["verified_snapshot"]["path"],
        "authorized_effect_utc_day": result.rules_checked_day,
        "authorized_effect_deadline_utc": result.expires_at.isoformat(),
        "next_step": (
            "Human may separately stage only the exact content-addressed private-kernel snapshot; record its result before Phase B."
            if args.phase == "stage"
            else "Human may separately use the Kaggle UI to select the exact reviewed submission.parquet once, on the recorded UTC day and strictly before the printed deadline."
        ),
        "claim_ceiling": "Local procedural gate consumed; no external effect was performed or proven by this tool.",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
