#!/usr/bin/env python3
"""Check or explicitly fetch the two pinned public code repositories.

This tool never handles Rosetta task data, Hugging Face datasets, Kaggle
datasets, credentials, models, or evaluators.  Its default check mode is both
network-free and write-free, including when the cache does not yet exist.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = REPO_ROOT / "source-lock.v1.json"
DEFAULT_CACHE = REPO_ROOT / ".cache" / "pinned-code"
CODE_PINS = {
    "rosettabench": {
        "repository": "https://github.com/namanbnsl/RosettaBench",
        "commit": "099b4837252becbd2c650ca54b206ac1a6bc3470",
        "directory": "RosettaBench",
    },
    "kaggle_benchmarks": {
        "repository": "https://github.com/Kaggle/kaggle-benchmarks",
        "commit": "ab291417d9a4c731ccfbfb03ac0b8316cb843683",
        "directory": "kaggle-benchmarks",
    },
}


class FetchError(ValueError):
    """Raised when a source lock or checkout violates the code-only boundary."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FetchError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical_repository(value: object) -> str:
    if not isinstance(value, str):
        raise FetchError("repository must be a string")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise FetchError("code repositories must use credential-free https://github.com URLs")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise FetchError("repository URL must not contain credentials, query text, or a fragment")
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if path.count("/") != 2 or not all(path.split("/")[1:]):
        raise FetchError("repository URL must identify one GitHub owner/repository")
    return f"https://github.com{path}"


def load_code_pins(path: Path) -> dict[str, dict[str, str]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FetchError(f"cannot read source lock: {exc}") from exc
    if len(raw) > 256 * 1024:
        raise FetchError("source lock exceeds the 256 KiB safety ceiling")
    try:
        document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FetchError(f"invalid UTF-8 source-lock JSON: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("sources"), dict):
        raise FetchError("source lock must contain a sources object")
    sources = document["sources"]

    unexpected_fetchable = sorted(
        key
        for key, value in sources.items()
        if isinstance(value, dict)
        and value.get("fetch_class") == "public_code"
        and key not in CODE_PINS
    )
    if unexpected_fetchable:
        raise FetchError(
            "refusing unapproved public_code source entries: " + ", ".join(unexpected_fetchable)
        )

    pins: dict[str, dict[str, str]] = {}
    for key, expected in CODE_PINS.items():
        entry = sources.get(key)
        if not isinstance(entry, dict):
            raise FetchError(f"missing source-lock entry: sources.{key}")
        if entry.get("fetch_class") != "public_code":
            raise FetchError(f"sources.{key}.fetch_class must be public_code")
        repository = _canonical_repository(entry.get("repository"))
        if repository != expected["repository"]:
            raise FetchError(f"sources.{key}.repository does not match the approved pin")
        commit = entry.get("commit")
        if commit != expected["commit"]:
            raise FetchError(f"sources.{key}.commit does not match the approved pin")
        pins[key] = {
            "repository": repository,
            "commit": commit,
            "directory": expected["directory"],
        }
    return pins


def validate_cache_path(
    cache: Path,
    *,
    repo_root: Path = REPO_ROOT,
    allow_repo_descendant: bool = False,
) -> Path:
    if not cache.is_absolute():
        raise FetchError("cache path must be absolute")
    resolved = cache.resolve(strict=False)
    root = repo_root.resolve(strict=True)
    if resolved == Path(resolved.anchor):
        raise FetchError("cache path must not be a filesystem root")
    if resolved == root or resolved in root.parents or (
        root in resolved.parents and not allow_repo_descendant
    ):
        raise FetchError("cache path must be outside the repository and its ancestors")
    if resolved == Path.home().resolve(strict=True):
        raise FetchError("cache path must be a dedicated directory, not the home directory")
    git_metadata = (root / ".git").resolve(strict=False)
    if resolved == git_metadata or git_metadata in resolved.parents:
        raise FetchError("cache path must not be inside Git metadata")
    if resolved.exists() and not resolved.is_dir():
        raise FetchError("cache path exists but is not a directory")
    return resolved


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_ASKPASS": "",
            "SSH_ASKPASS": "",
        }
    )
    return environment


Runner = Callable[..., subprocess.CompletedProcess[str]]


def run_git(checkout: Path, arguments: Sequence[str], *, runner: Runner = subprocess.run) -> str:
    command = [
        "git",
        "-c",
        f"safe.directory={checkout.resolve(strict=False)}",
        "-c",
        "credential.helper=",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        *arguments,
    ]
    try:
        completed = runner(
            command,
            cwd=str(checkout.parent),
            env=_git_environment(),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise FetchError(f"cannot execute Git: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "Git command failed").strip()
        raise FetchError(detail)
    return completed.stdout.strip()


def inspect_checkout(
    checkout: Path,
    pin: Mapping[str, str],
    *,
    runner: Runner = subprocess.run,
) -> dict[str, object]:
    if not checkout.exists():
        return {
            "status": "MISSING",
            "path": str(checkout),
            "network_git_commands_attempted": 0,
        }
    if checkout.is_symlink() or not checkout.is_dir() or not (checkout / ".git").exists():
        raise FetchError(f"existing checkout is not a Git repository: {checkout}")
    status = run_git(checkout, ["-C", str(checkout), "status", "--porcelain"], runner=runner)
    if status:
        raise FetchError(f"existing checkout is dirty: {checkout}")
    origin = run_git(
        checkout, ["-C", str(checkout), "remote", "get-url", "origin"], runner=runner
    )
    if _canonical_repository(origin) != pin["repository"]:
        raise FetchError(f"existing checkout origin mismatch: {checkout}")
    head = run_git(checkout, ["-C", str(checkout), "rev-parse", "HEAD"], runner=runner)
    if head != pin["commit"]:
        raise FetchError(f"existing checkout commit mismatch: {checkout}")
    return {
        "status": "PINNED_CLEAN",
        "path": str(checkout),
        "commit": head,
        "network_git_commands_attempted": 0,
    }


def fetch_checkout(
    checkout: Path,
    pin: Mapping[str, str],
    *,
    runner: Runner = subprocess.run,
) -> dict[str, object]:
    if checkout.exists():
        return inspect_checkout(checkout, pin, runner=runner)
    run_git(
        checkout,
        ["clone", "--no-checkout", "--filter=blob:none", pin["repository"] + ".git", str(checkout)],
        runner=runner,
    )
    run_git(
        checkout,
        ["-C", str(checkout), "fetch", "--depth=1", "origin", pin["commit"]],
        runner=runner,
    )
    run_git(
        checkout,
        ["-C", str(checkout), "checkout", "--detach", pin["commit"]],
        runner=runner,
    )
    result = inspect_checkout(checkout, pin, runner=runner)
    # Clone, fetch, and checkout are each network-capable for a partial clone;
    # Git may perform an opaque number of socket operations within them.
    result["network_git_commands_attempted"] = 3
    return result


def process_sources(
    lock_path: Path,
    cache: Path,
    *,
    fetch: bool,
    runner: Runner = subprocess.run,
    repo_root: Path = REPO_ROOT,
) -> dict[str, object]:
    pins = load_code_pins(lock_path)
    cache = validate_cache_path(cache, repo_root=repo_root, allow_repo_descendant=not fetch)
    if fetch:
        cache.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, object]] = {}
    for key, pin in pins.items():
        checkout = cache / pin["directory"]
        results[key] = (
            fetch_checkout(checkout, pin, runner=runner)
            if fetch
            else inspect_checkout(checkout, pin, runner=runner)
        )
    return {
        "mode": "FETCH_CODE" if fetch else "CHECK_ONLY_OFFLINE",
        "network_authorized": fetch,
        "network_git_commands_attempted": sum(
            int(result["network_git_commands_attempted"]) for result in results.values()
        ),
        "network_socket_operations": 0 if not fetch else "NOT_OBSERVABLE_WITHIN_GIT",
        "data_actions": 0,
        "sources": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument(
        "--cache",
        type=Path,
        help="absolute dedicated code cache; required for --fetch-code",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only", action="store_true", help="offline, write-free inspection")
    mode.add_argument("--fetch-code", action="store_true", help="explicitly fetch only the two code pins")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.fetch_code and args.cache is None:
            raise FetchError("--fetch-code requires an explicit --cache destination")
        cache = args.cache if args.cache is not None else DEFAULT_CACHE
        report = process_sources(args.lock, cache, fetch=args.fetch_code)
    except (FetchError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
