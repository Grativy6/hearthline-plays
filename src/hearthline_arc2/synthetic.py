"""Exact authored-fixture lock used by the only unrestricted local lane."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


FIXTURE_MANIFEST_SHA256 = (
    "2b92c05893dd371bbcabcea2d9aac772adbd129a8ff646d7d58421f451d12d91"
)
_FIXTURE_NAMES = frozenset({"challenges.json", "solutions.json", "submission.json"})
_MANIFEST_FIELDS = {
    "schema",
    "origin",
    "authored_by",
    "tooling_note",
    "created_on",
    "official_task_bytes_copied",
    "official_task_transform_used",
    "purpose",
    "files",
}


class SyntheticFixtureError(ValueError):
    """An input is not exactly one of the committed synthetic fixtures."""


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SyntheticFixtureError("synthetic fixture cannot be verified") from exc


def _fixture_hashes(fixture_root: Path) -> dict[str, str]:
    manifest_path = fixture_root / "fixture-manifest.json"
    manifest_bytes = _read(manifest_path)
    if hashlib.sha256(manifest_bytes).hexdigest() != FIXTURE_MANIFEST_SHA256:
        raise SyntheticFixtureError("synthetic fixture lock does not match the commit")
    try:
        manifest: Any = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SyntheticFixtureError("synthetic fixture lock is invalid") from exc
    if (
        not isinstance(manifest, dict)
        or set(manifest) != _MANIFEST_FIELDS
        or manifest.get("schema")
        != "hearthline-plays.arc2-synthetic-fixture-manifest.v1"
        or manifest.get("origin") != "SYNTHETIC_AUTHORED_FOR_CONTRACT_TESTS"
        or manifest.get("authored_by") != "Christopher D. Pang"
        or manifest.get("official_task_bytes_copied") is not False
        or manifest.get("official_task_transform_used") is not False
        or not isinstance(manifest.get("files"), list)
    ):
        raise SyntheticFixtureError("synthetic fixture lock is invalid")
    entries: dict[str, str] = {}
    for entry in manifest["files"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "sha256"}
            or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("sha256"), str)
            or len(entry["sha256"]) != 64
        ):
            raise SyntheticFixtureError("synthetic fixture lock is invalid")
        entries[entry["path"]] = entry["sha256"]
    if set(entries) != _FIXTURE_NAMES or len(entries) != len(manifest["files"]):
        raise SyntheticFixtureError("synthetic fixture lock is invalid")
    return entries


def load_synthetic_artifact(
    selected_path: str | Path,
    fixture_root: str | Path,
    role: str,
) -> tuple[Any, str, int]:
    """Verify and parse one exact fixture byte snapshot without reopening it."""

    if role not in _FIXTURE_NAMES:
        raise SyntheticFixtureError("unsupported synthetic fixture role")
    expected = _fixture_hashes(Path(fixture_root))[role]
    payload = _read(Path(selected_path))
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected:
        raise SyntheticFixtureError("only the committed synthetic fixture is permitted")
    try:
        from .validation import parse_json

        value = parse_json(payload.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise SyntheticFixtureError("committed synthetic fixture is invalid") from exc
    return value, digest, len(payload)
