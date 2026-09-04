#!/usr/bin/env python3
"""Offline verifier for the prepared-not-run Biohub Hearthline station."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tomllib
from typing import Callable, Iterable, Sequence
from urllib.parse import urlsplit


TITLE_BRANCH = "kaggle/titles/biohub-cell-tracking-during-development"
SOURCE_NAMES = {"organizer_baseline", "tracksdata"}
EXPECTED_SOURCES = {
    "organizer_baseline": {
        "repository": "https://github.com/royerlab/kaggle-cell-tracking-competition",
        "commit": "075fc5f5a52d11077f9dc2b074644618f26939e2",
    },
    "tracksdata": {
        "repository": "https://github.com/royerlab/tracksdata",
        "commit": "63a1912f3b6ebd1536a2e8a8adfdf7f5eb84efa4",
    },
}
SERIES_ANCHOR = "8e1bdfa38d4d3169efffdd0cda2c06799981fbfe"
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
REQUIRED_FILES = {
    ".gitignore",
    ".gitattributes",
    ".github/workflows/verify-biohub-station.yml",
    "AGENTS.md",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "configs/local.example.toml",
    "docs/EXPERIMENT_PROTOCOL.md",
    "docs/GETTING_STARTED.md",
    "pyproject.toml",
    "source-lock.v1.json",
    "status/station-status.v1.json",
    "templates/experiment-receipt.v1.json",
    "tools/check_data_home.py",
    "tools/bootstrap_environment.ps1",
    "tools/fetch_pinned_sources.py",
    "tools/make_embryo_splits.py",
    "tools/validate_submission.py",
    "tools/verify_station.py",
    "tests/test_check_data_home.py",
    "tests/test_fetch_pinned_sources.py",
    "tests/test_make_embryo_splits.py",
    "tests/test_validate_submission.py",
    "tests/test_verify_station.py",
}
PROHIBITED_TOP_LEVEL = {
    ".cache",
    ".kaggle",
    "checkpoints",
    "data",
    "datasets",
    "predictions",
    "results",
    "runs",
    "submissions",
    "weights",
}
PROHIBITED_SUFFIXES = {
    ".7z",
    ".ckpt",
    ".geff",
    ".h5",
    ".hdf5",
    ".npy",
    ".npz",
    ".onnx",
    ".parquet",
    ".pt",
    ".pth",
    ".tar",
    ".tif",
    ".tiff",
    ".zip",
}
PROHIBITED_SECRET_NAMES = {
    ".env",
    ".netrc",
    "_netrc",
    "credentials.json",
    "id_dsa",
    "id_ed25519",
    "id_rsa",
    "kaggle.json",
    "secrets.json",
}
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".csv",
    ".gitignore",
    ".ini",
    ".ipynb",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


class VerificationError(ValueError):
    """Raised when a station invariant is not satisfied."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise VerificationError(f"{path.name}: invalid JSON: {exc}") from exc
    require(isinstance(value, dict), f"{path.name}: root must be an object")
    return value


def _string_list(value: object, *, label: str) -> list[str]:
    require(
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() == item and item for item in value),
        f"{label} must be a non-empty list of trimmed strings",
    )
    result = list(value)
    require(len(result) == len(set(result)), f"{label} contains duplicates")
    return result


def _validate_public_github_url(value: object, *, label: str) -> None:
    require(isinstance(value, str), f"{label} must be a string")
    parsed = urlsplit(value)
    require(
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and len([part for part in parsed.path.split("/") if part]) == 2,
        f"{label} must be a credential-free public GitHub repository URL",
    )


def _normalized_repository(value: str) -> str:
    return value.removesuffix(".git").rstrip("/").lower()


def validate_source_lock(document: dict[str, object]) -> None:
    require(document.get("schema_version") == "1.0", "source lock schema_version")
    lineage = document.get("lineage")
    require(isinstance(lineage, dict), "source lock lineage must be an object")
    require(lineage.get("title_branch") == TITLE_BRANCH, "source lock title branch")
    require(lineage.get("series_branch") == "kaggle/main", "source lock series branch")
    require(lineage.get("series_anchor_commit") == SERIES_ANCHOR, "source lock series anchor")

    competition = document.get("competition")
    require(isinstance(competition, dict), "source lock competition must be an object")
    require(
        competition.get("slug") == "biohub-cell-tracking-during-development",
        "source lock competition slug",
    )

    sources = document.get("sources")
    require(isinstance(sources, dict), "source lock sources must be an object")
    require(set(sources) == SOURCE_NAMES, "source lock must contain exactly two pinned sources")
    repositories: list[str] = []
    for name in sorted(SOURCE_NAMES):
        source = sources[name]
        require(isinstance(source, dict), f"source {name} must be an object")
        _validate_public_github_url(source.get("repository"), label=f"source {name}")
        commit = source.get("commit")
        require(
            isinstance(commit, str) and COMMIT_RE.fullmatch(commit) is not None,
            f"source {name} commit must be 40 lowercase hex characters",
        )
        expected = EXPECTED_SOURCES[name]
        require(
            _normalized_repository(source["repository"])
            == _normalized_repository(expected["repository"]),
            f"source {name} repository does not match the prepared pin",
        )
        require(commit == expected["commit"], f"source {name} commit does not match the prepared pin")
        repositories.append(source["repository"])
    require(len(set(repositories)) == 2, "source repositories must be distinct")

    ceiling = document.get("claim_ceiling")
    require(isinstance(ceiling, dict), "source lock claim_ceiling must be an object")
    for field in (
        "organizer_sources_executed",
        "competition_data_accessed",
        "benchmark_reproduced",
        "official_submission_made",
        "scientific_or_leaderboard_result_earned",
    ):
        require(ceiling.get(field) is False, f"source lock claim_ceiling.{field} must be false")


def validate_station_status(document: dict[str, object]) -> None:
    require(document.get("schema_version") == "1.0", "status schema_version")
    require(document.get("status") == "PREPARED_NOT_RUN", "station status must be PREPARED_NOT_RUN")
    require(
        document.get("participation_status") == "NOT_ENTERED_UNVERIFIED",
        "participation status must be NOT_ENTERED_UNVERIFIED",
    )
    lineage = document.get("lineage")
    require(isinstance(lineage, dict), "status lineage must be an object")
    require(lineage.get("title_branch") == TITLE_BRANCH, "status title branch")
    require(lineage.get("parent_series_branch") == "kaggle/main", "status parent series branch")
    require(lineage.get("parent_anchor_commit") == SERIES_ANCHOR, "status parent anchor")

    authorization = document.get("authorization")
    require(isinstance(authorization, dict), "status authorization must be an object")
    allowed = _string_list(authorization.get("allowed"), label="authorization.allowed")
    gated = _string_list(
        authorization.get("requires_new_instruction"),
        label="authorization.requires_new_instruction",
    )
    require(set(allowed).isdisjoint(gated), "allowed and gated actions must be disjoint")
    gated_text = " ".join(gated).lower()
    for concept in ("authenticate", "rules", "data", "notebook", "train", "submission"):
        require(concept in gated_text, f"authorization gate must cover {concept}")

    counters = document.get("counters")
    require(isinstance(counters, dict), "status counters must be an object")
    for field in (
        "competition_data_files_opened",
        "competition_data_files_downloaded",
        "competition_data_bytes_read",
        "notebook_runs",
        "submissions",
        "leaderboard_scores",
    ):
        require(type(counters.get(field)) is int, f"counter {field} must be an integer")
        require(counters[field] == 0, f"counter {field} must remain zero")

    storage = document.get("storage")
    require(isinstance(storage, dict), "status storage must be an object")
    require(
        storage.get("current_e_drive_allowed_for_competition_data") is False,
        "current E drive must remain forbidden for competition data",
    )
    require(
        storage.get("repository_may_contain_competition_data") is False,
        "repository must remain forbidden for competition data",
    )


def tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root}",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        text=False,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise VerificationError(f"git ls-files failed: {detail or 'no detail'}")
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def prohibited_path_reason(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    parts = [part.lower() for part in pure.parts]
    if not parts or pure.is_absolute() or ".." in parts:
        return "unsafe tracked path"
    if parts[0] in PROHIBITED_TOP_LEVEL:
        return f"prohibited generated/data directory {parts[0]}"
    if any(part.endswith((".zarr", ".geff")) for part in parts):
        return "tracked competition data container"
    name = parts[-1]
    if name in PROHIBITED_SECRET_NAMES or name.startswith(".env."):
        return "tracked credential/secret filename"
    if name in {"submission.csv", "sample_submission.csv"}:
        return "tracked competition submission"
    if name.endswith(".tar.gz") or PurePosixPath(name).suffix in PROHIBITED_SUFFIXES:
        return "tracked data/model/archive extension"
    return None


def secret_text_reason(text: str) -> str | None:
    patterns = (
        (re.compile("AKI" + r"A[A-Z0-9]{16}"), "AWS access key"),
        (re.compile("gh" + r"[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
        (re.compile("sk" + r"-(?:proj-)?[A-Za-z0-9_-]{24,}"), "API token"),
        (
            re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?" + "PRIVATE KEY-----"),
            "private key material",
        ),
        (
            re.compile(
                r"(?im)^\s*(?:KAGGLE_KEY|API_KEY|ACCESS_TOKEN|PASSWORD|SECRET)\s*[:=]\s*"
                r"[\"']?([A-Za-z0-9_+/=-]{20,})"
            ),
            "credential-like assignment",
        ),
    )
    for pattern, reason in patterns:
        if pattern.search(text):
            return reason
    return None


def validate_inventory(
    root: Path,
    tracked: Iterable[str],
    *,
    read_bytes: Callable[[Path], bytes] | None = None,
) -> int:
    read_bytes = read_bytes or (lambda path: path.read_bytes())
    paths = sorted(set(tracked))
    for path in paths:
        reason = prohibited_path_reason(path)
        require(reason is None, f"{path}: {reason}")
        file_path = root / path
        if file_path.is_symlink():
            raise VerificationError(f"{path}: tracked symlinks are not allowed")
        if not file_path.is_file():
            raise VerificationError(f"{path}: candidate path is not a regular file")
        if file_path.stat().st_size > 5 * 1024 * 1024:
            raise VerificationError(f"{path}: file exceeds 5 MiB repository ceiling")
        suffix = PurePosixPath(path.lower()).suffix
        if suffix not in TEXT_SUFFIXES:
            continue
        try:
            content = read_bytes(file_path)
        except OSError as exc:
            raise VerificationError(f"{path}: cannot scan tracked file: {exc}") from exc
        if len(content) > 1024 * 1024:
            raise VerificationError(f"{path}: text file exceeds 1 MiB scan ceiling")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VerificationError(f"{path}: tracked text file is not UTF-8") from exc
        reason = secret_text_reason(text)
        require(reason is None, f"{path}: detected {reason}")
    return len(paths)


def validate_required_files(root: Path) -> None:
    missing = sorted(path for path in REQUIRED_FILES if not (root / path).is_file())
    require(not missing, f"missing required files: {missing}")


def validate_gitignore(root: Path) -> None:
    lines = {
        line.strip()
        for line in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    for pattern in (
        ".cache/",
        "data/",
        "datasets/",
        "/submission.csv",
        "/sample_submission.csv",
        "*.zarr",
        "*.geff",
    ):
        require(pattern in lines, f".gitignore must include {pattern}")


def validate_local_example(root: Path) -> None:
    try:
        document = tomllib.loads((root / "configs" / "local.example.toml").read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise VerificationError(f"local.example.toml: invalid TOML: {exc}") from exc
    station = document.get("station")
    submission = document.get("submission")
    storage = document.get("storage")
    require(isinstance(station, dict) and station.get("run_enabled") is False, "example run gate")
    require(
        isinstance(submission, dict) and submission.get("enabled") is False,
        "example submission gate",
    )
    require(isinstance(storage, dict), "example storage section")
    forbidden = storage.get("forbidden_roots")
    require(
        isinstance(forbidden, list)
        and any(isinstance(value, str) and value.rstrip("/\\").lower() == "e:" for value in forbidden),
        "example storage must forbid the current E drive",
    )


def verify(root: Path) -> dict[str, object]:
    root = root.resolve(strict=True)
    validate_required_files(root)
    validate_source_lock(load_json(root / "source-lock.v1.json"))
    validate_station_status(load_json(root / "status" / "station-status.v1.json"))
    validate_gitignore(root)
    validate_local_example(root)
    count = validate_inventory(root, tracked_files(root))
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "station_status": "PREPARED_NOT_RUN",
        "participation_status": "NOT_ENTERED_UNVERIFIED",
        "tracked_file_count": count,
        "competition_data_files_opened_by_verifier": 0,
        "external_network_calls_performed_by_verifier": 0,
        "official_scorer_executed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1], help=argparse.SUPPRESS
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = verify(args.root)
    except (OSError, VerificationError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
