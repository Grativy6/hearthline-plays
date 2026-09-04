#!/usr/bin/env python3
"""Materialize source-locked public repositories only with an explicit --fetch."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit


SOURCE_NAMES = ("organizer_baseline", "tracksdata")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")


class SourceError(ValueError):
    """Raised when the source lock or a cached checkout is unsafe."""


def public_repository_url(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise SourceError(f"{label}: repository must be a string")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SourceError(
            f"{label}: repository must be a credential-free public https://github.com URL"
        )
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 2:
        raise SourceError(f"{label}: repository URL must identify owner/repository")
    return value


def normalized_repository_url(value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path.rstrip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def load_source_lock(path: Path) -> dict[str, dict[str, str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceError(f"invalid source lock JSON: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != "1.0":
        raise SourceError("source lock must be an object with schema_version 1.0")
    sources = document.get("sources")
    if not isinstance(sources, dict) or set(sources) != set(SOURCE_NAMES):
        raise SourceError(f"source lock must define exactly {', '.join(SOURCE_NAMES)}")

    result: dict[str, dict[str, str]] = {}
    for name in SOURCE_NAMES:
        source = sources.get(name)
        if not isinstance(source, dict):
            raise SourceError(f"{name}: source entry must be an object")
        repository = public_repository_url(source.get("repository"), label=name)
        commit = source.get("commit")
        if not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
            raise SourceError(f"{name}: commit must be exactly 40 lowercase hex characters")
        result[name] = {"repository": repository, "commit": commit}
    if len({normalized_repository_url(item["repository"]) for item in result.values()}) != 2:
        raise SourceError("source repositories must be distinct")
    return result


def _git_environment() -> dict[str, str]:
    env = os.environ.copy()
    # Refuse interactive auth and bypass configured credential helpers. These
    # checkouts are deliberately restricted to public, credential-free URLs.
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "GIT_ASKPASS": "",
            "SSH_ASKPASS": "",
        }
    )
    return env


def run_git(
    arguments: Sequence[str], *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    configuration = ["-c", "credential.helper=", "-c", "core.askPass="]
    if cwd is not None:
        configuration[0:0] = ["-c", f"safe.directory={cwd.resolve(strict=False)}"]
    return subprocess.run(
        ["git", *configuration, *arguments],
        cwd=cwd,
        env=_git_environment(),
        text=True,
        capture_output=True,
        check=False,
    )


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _checked_git(
    runner: Runner,
    arguments: Sequence[str],
    *,
    cwd: Path | None = None,
    label: str,
) -> str:
    result = runner(arguments, cwd=cwd)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SourceError(f"{label}: git command failed: {detail or 'no detail'}")
    return result.stdout.strip()


def inspect_checkout(
    destination: Path,
    source: Mapping[str, str],
    *,
    runner: Runner = run_git,
) -> dict[str, object]:
    if not destination.exists():
        return {"status": "MISSING", "path": str(destination)}
    if not destination.is_dir() or not (destination / ".git").exists():
        raise SourceError(f"{destination}: existing cache entry is not a Git checkout")

    status = _checked_git(
        runner,
        ["status", "--porcelain", "--untracked-files=all"],
        cwd=destination,
        label=str(destination),
    )
    if status:
        raise SourceError(f"{destination}: existing checkout is dirty")

    origin = _checked_git(
        runner,
        ["remote", "get-url", "origin"],
        cwd=destination,
        label=str(destination),
    )
    public_repository_url(origin, label=f"{destination} origin")
    if normalized_repository_url(origin) != normalized_repository_url(source["repository"]):
        raise SourceError(f"{destination}: origin does not match source lock")

    head = _checked_git(
        runner,
        ["rev-parse", "HEAD"],
        cwd=destination,
        label=str(destination),
    )
    if head != source["commit"]:
        raise SourceError(
            f"{destination}: HEAD {head or '<empty>'} does not match locked {source['commit']}"
        )
    _checked_git(
        runner,
        ["cat-file", "-e", f"{source['commit']}^{{commit}}"],
        cwd=destination,
        label=str(destination),
    )
    return {
        "status": "PINNED_CLEAN",
        "path": str(destination),
        "repository": source["repository"],
        "commit": source["commit"],
    }


def cache_is_ignored(
    cache: Path, *, repo_root: Path, runner: Runner = run_git
) -> bool:
    try:
        relative = cache.resolve(strict=False).relative_to(repo_root.resolve(strict=True))
    except ValueError:
        return False
    result = runner(["check-ignore", "--quiet", "--", relative.as_posix()], cwd=repo_root)
    return result.returncode == 0


def fetch_missing_checkout(
    destination: Path,
    source: Mapping[str, str],
    *,
    runner: Runner = run_git,
) -> dict[str, object]:
    if destination.exists():
        # Never repair, overwrite, fetch, or move an existing cache entry.
        return inspect_checkout(destination, source, runner=runner)

    result = runner(
        ["clone", "--no-checkout", "--filter=blob:none", source["repository"], str(destination)],
        cwd=destination.parent,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SourceError(f"clone failed for {source['repository']}: {detail or 'no detail'}")
    _checked_git(
        runner,
        ["fetch", "--force", "--depth=1", "origin", source["commit"]],
        cwd=destination,
        label=str(destination),
    )
    _checked_git(
        runner,
        ["checkout", "--detach", source["commit"]],
        cwd=destination,
        label=str(destination),
    )
    return inspect_checkout(destination, source, runner=runner)


def process_sources(
    *,
    lock_path: Path,
    cache: Path,
    repo_root: Path,
    fetch: bool,
    runner: Runner = run_git,
) -> dict[str, object]:
    sources = load_source_lock(lock_path)
    cache = cache.resolve(strict=False)
    repo_root = repo_root.resolve(strict=True)
    try:
        relative_cache = cache.relative_to(repo_root)
    except ValueError as exc:
        raise SourceError("cache must be a dedicated ignored directory inside the repository") from exc
    if not relative_cache.parts or relative_cache.parts[0].lower() == ".git":
        raise SourceError("cache path must not be the repository root or inside .git")
    if not cache_is_ignored(cache, repo_root=repo_root, runner=runner):
        raise SourceError(f"repository-local cache path is not ignored: {cache}")

    if cache.exists():
        if not cache.is_dir():
            raise SourceError(f"cache path is not a directory: {cache}")
        unexpected = sorted(entry.name for entry in cache.iterdir() if entry.name not in SOURCE_NAMES)
        if unexpected:
            raise SourceError(f"cache contains unexpected entries: {unexpected}")

    if fetch:
        cache.mkdir(parents=True, exist_ok=True)

    checkouts: dict[str, object] = {}
    for name in SOURCE_NAMES:
        destination = cache / name
        if fetch:
            checkouts[name] = fetch_missing_checkout(
                destination, sources[name], runner=runner
            )
        else:
            checkouts[name] = inspect_checkout(destination, sources[name], runner=runner)

    return {
        "schema_version": "1.0",
        "mode": "FETCH" if fetch else "CHECK_ONLY_OFFLINE",
        "network_allowed": fetch,
        "credentials_allowed": False,
        "cache": str(cache),
        "checkouts": checkouts,
    }


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check-only",
        action="store_true",
        help="offline lock/cache inspection; missing checkouts are acceptable",
    )
    mode.add_argument(
        "--fetch",
        action="store_true",
        help="explicitly allow public Git clone/fetch operations",
    )
    parser.add_argument("--lock", type=Path, default=repo_root / "source-lock.v1.json")
    parser.add_argument(
        "--cache", type=Path, default=repo_root / ".cache" / "pinned-sources"
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = process_sources(
            lock_path=args.lock,
            cache=args.cache,
            repo_root=args.repo_root,
            fetch=args.fetch,
        )
    except (OSError, SourceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
