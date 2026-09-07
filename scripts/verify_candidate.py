#!/usr/bin/env python3
"""Regenerate and verify an ARC-AGI-3 candidate entirely offline.

The verifier treats Git's current committed objects as the trust root. It
reads candidate files once through no-follow file descriptors, regenerates all
three expected files from committed inputs, compares exact bytes, and then
materializes those already-verified bytes under a content-addressed directory.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUILD = ROOT / "build"
TRUSTED_INPUT_PATHS = (
    "agent/my_agent.py",
    "launch/contracts/official-starter-eeb153.contract.json",
    "launch/receipts/20260907T002817Z-stage-v4-runtime-review.json",
    "launch/runtime/kaggle-stage-v4-runtime-inventory.json",
    "launch/source-lock.v4.json",
    "notebooks/kernel-metadata.template.json",
    "scripts/build_notebook.py",
)
BUILD_FILES = (
    "candidate-manifest.json",
    "kernel-metadata.json",
    "submission.ipynb",
)
BUILD_EXTRAS = {"verified": "directory", "verification.json": "regular"}
FORBIDDEN_AGENT_IMPORTS = {
    "aiohttp", "boto3", "http", "kaggle", "openai", "os", "requests",
    "socket", "subprocess", "urllib",
}
EXPECTED_METADATA_KEYS = {
    "id", "title", "code_file", "language", "kernel_type", "is_private",
    "enable_gpu", "enable_tpu", "enable_internet", "keywords",
    "dataset_sources", "kernel_sources", "competition_sources", "model_sources",
}
ACCELERATOR_BY_METADATA = {
    ("none", False): "cpu",
    ("nvidiaTeslaT4", True): "t4",
    ("nvidiaTeslaP100", True): "p100",
    ("nvidiaRtx6000", True): "rtx6000",
}
ACCELERATOR_SETTINGS = {
    "cpu": {"name": "none", "gpu": False},
    "t4": {"name": "nvidiaTeslaT4", "gpu": True},
    "p100": {"name": "nvidiaTeslaP100", "gpu": True},
    "rtx6000": {"name": "nvidiaRtx6000", "gpu": True},
}
REVIEWED_RUNTIME_INVENTORY_SHA256 = (
    "17bfcc2ab86fd8cd3ba4a664ce0220f93c5cab008dd7336e0b7db7b88941b2ce"
)
RUNTIME_REVIEW_RECEIPT_SHA256 = (
    "ad351aefdc18461bcf297d7095f8a77daa2641c583498cfad1b9f9b25a64206b"
)
RUNTIME_REVIEW_ATTESTATION_SHA256 = (
    "d721087df9ad28f26da262cddb066a7273b42f61d7fd96f7bb641c0840393dc2"
)


class CandidateError(RuntimeError):
    """Raised when any candidate invariant fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise CandidateError(f"non-finite JSON number is forbidden: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if parsed == float("inf") or parsed == float("-inf"):
        _reject_nonfinite(value)
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
        raise CandidateError(f"{label}: invalid strict UTF-8 JSON: {exc}") from exc


def require_exact_keys(value: Any, keys: Iterable[str], label: str) -> None:
    require(isinstance(value, dict), f"{label} must be an object")
    expected = set(keys)
    actual = set(value)
    require(actual == expected, f"{label} fields: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")


def current_git_identity() -> dict[str, Any]:
    commit = subprocess.check_output(
        _git_command("rev-parse", "HEAD"), cwd=ROOT, text=True, env=_git_environment()
    ).strip()
    tree = subprocess.check_output(
        _git_command("rev-parse", f"{commit}^{{tree}}"), cwd=ROOT, text=True, env=_git_environment()
    ).strip()
    porcelain = subprocess.check_output(
        _git_command("status", "--porcelain", "--untracked-files=normal"),
        cwd=ROOT,
        text=True,
        env=_git_environment(),
    )
    return {"commit": commit, "tree": tree, "worktree_clean": not porcelain.strip()}


def _git_environment() -> dict[str, str]:
    """Return a Git environment that cannot consult ambient hooks or remotes."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
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


def _git_blob(commit: str, relative: str) -> bytes:
    try:
        return subprocess.check_output(
            _git_command("show", f"{commit}:{relative}"),
            cwd=ROOT,
            env=_git_environment(),
        )
    except subprocess.CalledProcessError as exc:
        raise CandidateError(f"trusted Git input unavailable: {relative}") from exc


def _read_regular(path: Path, label: str) -> bytes:
    path_before = path.lstat()
    require(stat.S_ISREG(path_before.st_mode), f"{label} must be a regular file")
    require(path_before.st_nlink == 1, f"{label} must not be a hard-linked alias")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), f"{label} must be a regular file")
        require(before.st_nlink == 1, f"{label} must not be a hard-linked alias")
        require(
            (path_before.st_dev, path_before.st_ino, path_before.st_size, path_before.st_mtime_ns)
            == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
            f"{label} changed before it was opened",
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
        path_after = path.lstat()
        require(stat.S_ISREG(path_after.st_mode), f"{label} changed into a non-regular path")
        require(path_after.st_nlink == 1, f"{label} became a hard-linked alias")
        require(
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            == (path_after.st_dev, path_after.st_ino, path_after.st_size, path_after.st_mtime_ns),
            f"{label} path changed while being read",
        )
        return data
    finally:
        os.close(descriptor)


def trusted_git_snapshot(require_clean: bool) -> dict[str, Any]:
    """Freeze one HEAD plus its exact committed build inputs."""
    before = current_git_identity()
    if require_clean:
        require(before["worktree_clean"] is True, "current worktree is dirty")
    files = {relative: _git_blob(before["commit"], relative) for relative in TRUSTED_INPUT_PATHS}
    if require_clean:
        for relative, committed in files.items():
            current = _read_regular(ROOT / relative, f"worktree {relative}")
            require(current == committed, f"worktree input differs from committed Git object: {relative}")
    after = current_git_identity()
    require(after["commit"] == before["commit"] and after["tree"] == before["tree"], "Git HEAD changed during verification")
    if require_clean:
        require(after["worktree_clean"] is True, "worktree changed during verification")
    return {"identity": before, "files": files}


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _directory_identity(info: os.stat_result) -> tuple[int, int]:
    return (info.st_dev, info.st_ino)


def _open_directory(path: Path, label: str) -> tuple[int, os.stat_result]:
    """Open every lexical path component no-follow and hold the final FD."""
    absolute = _absolute_lexical(path)
    descriptor = os.open(Path(absolute.anchor), _directory_flags())
    try:
        for component in absolute.parts[1:]:
            before = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            require(stat.S_ISDIR(before.st_mode), f"{label} contains a non-directory or symlink component")
            child = os.open(component, _directory_flags(), dir_fd=descriptor)
            try:
                opened = os.fstat(child)
                require(
                    stat.S_ISDIR(opened.st_mode)
                    and _directory_identity(before) == _directory_identity(opened),
                    f"{label} changed while its path was opened",
                )
            except Exception:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        opened = os.fstat(descriptor)
        require(stat.S_ISDIR(opened.st_mode), f"{label} must be a real directory")
        return descriptor, opened
    except Exception:
        os.close(descriptor)
        raise


def _require_directory_path_binding(
    path: Path,
    expected: os.stat_result,
    label: str,
) -> None:
    descriptor, current = _open_directory(path, label)
    try:
        require(
            _directory_identity(current) == _directory_identity(expected),
            f"{label} path changed",
        )
    finally:
        os.close(descriptor)


def _read_file_with_identity_at(
    directory_fd: int,
    name: str,
    label: str,
) -> tuple[bytes, tuple[int, int, int, int]]:
    file_flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        file_flags |= os.O_NOFOLLOW
    descriptor = os.open(name, file_flags, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), f"{label} must be a regular file")
        require(before.st_nlink == 1, f"{label} must not be a hard-linked alias")
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
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        require(
            stat.S_ISREG(entry.st_mode)
            and entry.st_nlink == 1
            and _file_identity(after) == _file_identity(entry),
            f"{label} path changed while being read",
        )
        return data, _file_identity(after)
    finally:
        os.close(descriptor)


def _read_file_at(directory_fd: int, name: str, label: str) -> bytes:
    return _read_file_with_identity_at(directory_fd, name, label)[0]


def _read_build_snapshot_at(
    directory_fd: int,
    *,
    label: str,
    allowed_extras: dict[str, str] | None = None,
) -> dict[str, bytes]:
    allowed = allowed_extras or {}
    names = set(os.listdir(directory_fd))
    expected = set(BUILD_FILES)
    require(expected <= names, f"{label} is missing candidate files: {sorted(expected-names)}")
    require(names <= expected | set(allowed), f"{label} has unaddressed files: {sorted(names-expected-set(allowed))}")
    extra_identities: dict[str, tuple[str, tuple[int, ...]]] = {}
    for name, kind in allowed.items():
        if name not in names:
            continue
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        require(
            (kind == "directory" and stat.S_ISDIR(info.st_mode))
            or (kind == "regular" and stat.S_ISREG(info.st_mode) and info.st_nlink == 1),
            f"{label}/{name} has the wrong path type",
        )
        identity = (
            _directory_identity(info)
            if kind == "directory"
            else _file_identity(info)
        )
        extra_identities[name] = (kind, identity)
    result: dict[str, bytes] = {}
    file_identities: dict[str, tuple[int, int, int, int]] = {}
    for name in BUILD_FILES:
        result[name], file_identities[name] = _read_file_with_identity_at(
            directory_fd, name, f"{label}/{name}"
        )
    require(set(os.listdir(directory_fd)) == names, f"{label} inventory changed while being read")
    for name, identity in file_identities.items():
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1
            and _file_identity(info) == identity,
            f"{label}/{name} changed during closed snapshot",
        )
    for name, (kind, identity) in extra_identities.items():
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        current = (
            _directory_identity(info)
            if kind == "directory" and stat.S_ISDIR(info.st_mode)
            else _file_identity(info)
            if kind == "regular" and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            else ()
        )
        require(current == identity, f"{label}/{name} changed while candidate files were read")
    return result


def read_build_snapshot(
    build_dir: Path,
    *,
    allowed_extras: dict[str, str] | None = None,
) -> dict[str, bytes]:
    """Read one closed candidate inventory and reject path replacement."""
    if os.open not in os.supports_dir_fd:
        path_before = build_dir.lstat()
        require(stat.S_ISDIR(path_before.st_mode), "build path must be a real directory")
        names = {path.name for path in build_dir.iterdir()}
        allowed = allowed_extras or {}
        expected = set(BUILD_FILES)
        require(expected <= names, f"build is missing candidate files: {sorted(expected-names)}")
        require(names <= expected | set(allowed), f"build has unaddressed files: {sorted(names-expected-set(allowed))}")
        result = {name: _read_regular(build_dir / name, f"build/{name}") for name in BUILD_FILES}
        path_after = build_dir.lstat()
        require(
            stat.S_ISDIR(path_after.st_mode)
            and (path_before.st_dev, path_before.st_ino) == (path_after.st_dev, path_after.st_ino),
            "build directory path changed while being read",
        )
        require({path.name for path in build_dir.iterdir()} == names, "build inventory changed while being read")
        return result
    directory_fd, opened = _open_directory(build_dir, "build path")
    try:
        result = _read_build_snapshot_at(
            directory_fd,
            label="build",
            allowed_extras=allowed_extras,
        )
        _require_directory_path_binding(build_dir, opened, "build directory")
        return result
    finally:
        os.close(directory_fd)


def inspect_agent(source: str) -> dict[str, Any]:
    tree = ast.parse(source, filename="agent/my_agent.py")
    imports: set[str] = set()
    my_agent: ast.ClassDef | None = None
    context_profile = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.ClassDef) and node.name == "MyAgent":
            my_agent = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "CONTEXT_PROFILE" for target in targets):
                if isinstance(node.value, ast.Constant):
                    context_profile = node.value.value
    forbidden = sorted(imports & FORBIDDEN_AGENT_IMPORTS)
    require(not forbidden, f"agent imports effect-capable modules: {forbidden}")
    require(my_agent is not None, "agent must define MyAgent")
    bases = {base.id for base in my_agent.bases if isinstance(base, ast.Name)}
    require("Agent" in bases, "MyAgent must directly subclass Agent")
    methods = {node.name for node in my_agent.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    require({"is_done", "choose_action"} <= methods, "MyAgent contract methods missing")
    require(context_profile == "A0_MINIMAL", "committed candidate must default to A0_MINIMAL")
    require("KAGGLE_API_TOKEN" not in source and ".kaggle" not in source, "agent may not read Kaggle credentials")
    compile(source, "agent/my_agent.py", "exec")
    return {"imports": sorted(imports), "context_profile": context_profile, "methods": sorted(methods)}


def inspect_metadata(metadata: Any) -> dict[str, Any]:
    require_exact_keys(metadata, EXPECTED_METADATA_KEYS, "kernel metadata")
    require(isinstance(metadata["id"], str), "kernel id must be text")
    match = re.fullmatch(
        r"(REPLACE_WITH_YOUR_USERNAME|[A-Za-z0-9][A-Za-z0-9_-]{1,62})/hearthline-arc3-readiness",
        metadata["id"],
    )
    require(match is not None, "kernel identity format")
    expected_scalars = {
        "title": "Hearthline ARC3 Readiness",
        "code_file": "submission.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_tpu": False,
        "enable_internet": False,
        "keywords": [],
        "dataset_sources": [],
        "kernel_sources": [],
        "competition_sources": ["arc-prize-2026-arc-agi-3"],
        "model_sources": [],
    }
    for key, expected in expected_scalars.items():
        require(metadata[key] == expected and type(metadata[key]) is type(expected), f"kernel metadata {key} mismatch")
    require(
        metadata["title"].lower().replace(" ", "-") == metadata["id"].rsplit("/", 1)[1],
        "kernel title must resolve to the declared id slug",
    )
    require(type(metadata["enable_gpu"]) is bool, "kernel metadata enable_gpu must be boolean")
    return {
        "account_slug": match.group(1),
        "kernel_id": metadata["id"],
        "enable_gpu": metadata["enable_gpu"],
    }


def _install_projection(source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise CandidateError("starter install cell is not Python") from exc
    require(len(tree.body) == 3, "starter install cell shape")
    require(
        isinstance(tree.body[0], ast.Import)
        and [alias.name for alias in tree.body[0].names] == ["subprocess"],
        "starter install subprocess import",
    )
    require(
        isinstance(tree.body[1], ast.Import)
        and [alias.name for alias in tree.body[1].names] == ["sys"],
        "starter install sys import",
    )
    expression = tree.body[2]
    require(
        isinstance(expression, ast.Expr)
        and isinstance(expression.value, ast.Call)
        and isinstance(expression.value.func, ast.Attribute)
        and isinstance(expression.value.func.value, ast.Name)
        and expression.value.func.value.id == "subprocess"
        and expression.value.func.attr == "run",
        "starter install subprocess shape",
    )
    call = expression.value
    require(
        len(call.args) == 1
        and isinstance(call.args[0], ast.List)
        and len(call.keywords) == 1
        and call.keywords[0].arg == "check"
        and isinstance(call.keywords[0].value, ast.Constant)
        and call.keywords[0].value.value is True,
        "starter install must fail fast",
    )
    argv = call.args[0].elts
    require(
        argv
        and isinstance(argv[0], ast.Attribute)
        and isinstance(argv[0].value, ast.Name)
        and argv[0].value.id == "sys"
        and argv[0].attr == "executable",
        "starter install interpreter binding",
    )
    try:
        tokens = ["python", *[ast.literal_eval(item) for item in argv[1:]]]
    except (ValueError, TypeError) as exc:
        raise CandidateError("starter install argv must be literal") from exc
    if tokens[:3] == ["python", "-m", "pip"]:
        tokens = ["pip", *tokens[3:]]
    require(tokens[:2] == ["pip", "install"], "starter install command shape")
    require("--find-links" in tokens, "starter wheel source missing")
    index = tokens.index("--find-links")
    requirements = [token for token in tokens[index + 2:] if not token.startswith("-")]
    return {
        "installer": "pip",
        "no_index": "--no-index" in tokens,
        "wheelhouse": tokens[index + 1],
        "packages": [
            requirement.split("==", 1)[0]
            if requirement.count("==") == 1
            else requirement
            for requirement in requirements
        ],
    }


def _dummy_projection(source: str) -> dict[str, Any]:
    tree = ast.parse(source)
    data = columns = output = None
    rerun_signal = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "getenv" and node.args:
            try:
                rerun_signal |= ast.literal_eval(node.args[0]) == "KAGGLE_IS_COMPETITION_RERUN"
            except (ValueError, TypeError):
                pass
        elif node.func.attr == "DataFrame":
            keywords = {item.arg: item.value for item in node.keywords if item.arg}
            if "data" in keywords and "columns" in keywords:
                data = ast.literal_eval(keywords["data"])
                columns = ast.literal_eval(keywords["columns"])
        elif node.func.attr == "to_parquet" and node.args:
            output = ast.literal_eval(node.args[0])
    return {
        "rerun_signal": "KAGGLE_IS_COMPETITION_RERUN" if rerun_signal else None,
        "data": data,
        "columns": columns,
        "output": output,
    }


def _runtime_env_projection(run: str) -> dict[str, str]:
    keys = (
        "SCHEME", "HOST", "PORT", "ARC_API_KEY", "ARC_BASE_URL",
        "OPERATION_MODE", "ENVIRONMENTS_DIR", "RECORDINGS_DIR",
    )
    env: dict[str, str] = {}
    for key in keys:
        match = re.search(rf"{key}=([^\r\n]*)", run)
        if match is not None:
            env[key] = match.group(1)
    if len(env) == len(keys):
        return env
    try:
        tree = ast.parse(run)
        for node in tree.body:
            if not isinstance(node, ast.If):
                continue
            for child in node.body:
                if isinstance(child, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "runtime_settings"
                    for target in child.targets
                ):
                    rows = ast.literal_eval(child.value)
                    candidate = dict(rows)
                    if all(key in candidate for key in keys):
                        return {key: candidate[key] for key in keys}
    except (SyntaxError, ValueError, TypeError):
        pass
    raise CandidateError("starter runtime environment is incomplete")


def project_starter_surface(notebook: dict[str, Any]) -> dict[str, Any]:
    cells = notebook.get("cells", [])
    require(len(cells) == 5, "official starter shape requires five cells")
    require(
        [cell.get("cell_type") for cell in cells] == ["markdown", "code", "code", "code", "code"],
        "official starter cell order mismatch",
    )
    code = [str(cell.get("source", "")) for cell in cells[1:]]
    write_match = re.match(r"%%writefile\s+([^\s]+)\n", code[1])
    require(write_match is not None, "starter agent write cell shape")
    run = code[2]
    try:
        parsed = ast.parse(run)
    except SyntaxError:
        argv = (
            ["python", "main.py", "--agent", "myagent"]
            if "!cd /kaggle/working/ARC-AGI-3-Agents" in run
            and re.search(r"(?m)^\s*python\s+main\.py\s+--agent\s+myagent\s*$", run)
            else None
        )
    else:
        argv = None
        for node in ast.walk(parsed):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run" and node.args:
                try:
                    candidate = ast.literal_eval(node.args[0])
                except (ValueError, TypeError):
                    argument = node.args[0]
                    first = argument.elts[0] if isinstance(argument, ast.List) and argument.elts else None
                    if (
                        isinstance(argument, ast.List)
                        and len(argument.elts) == 7
                        and isinstance(first, ast.Call)
                        and isinstance(first.func, ast.Name)
                        and first.func.id == "str"
                        and len(first.args) == 1
                        and isinstance(first.args[0], ast.Name)
                        and first.args[0].id == "bound_interpreter_path"
                        and not first.keywords
                    ):
                        try:
                            tail = [ast.literal_eval(item) for item in argument.elts[1:]]
                        except (ValueError, TypeError):
                            continue
                        if tail == [
                            "-E", "-s", "-B", "main.py", "--agent", "myagent",
                        ]:
                            argv = ["python", "main.py", "--agent", "myagent"]
                            break
                    continue
                if candidate == ["python", "main.py", "--agent", "myagent"]:
                    argv = candidate
                    break
    urls = sorted(set(re.findall(r"https?://[^\"'\s]+", run)))
    registry = bool(re.search(r"[\"']myagent[\"']\s*:\s*MyAgent", run))
    kaggle = notebook.get("metadata", {}).get("kaggle", {})
    return {
        "nbformat": [notebook.get("nbformat"), notebook.get("nbformat_minor")],
        "cell_roles": ["markdown", "install", "write_agent", "competition_rerun", "dummy_output"],
        "kaggle": {
            "internet_enabled": kaggle.get("isInternetEnabled"),
            "language": kaggle.get("language"),
            "source_type": kaggle.get("sourceType"),
            "accelerator_gpu_coherent": (
                (kaggle.get("accelerator") == "none" and kaggle.get("isGpuEnabled") is False)
                or (kaggle.get("accelerator") != "none" and kaggle.get("isGpuEnabled") is True)
            ),
        },
        "install": _install_projection(code[0]),
        "agent_temp_path": write_match.group(1),
        "rerun_signal": "KAGGLE_IS_COMPETITION_RERUN" if "KAGGLE_IS_COMPETITION_RERUN" in run else None,
        "gateway": "http://gateway:8001/api/games" if "http://gateway:8001/api/games" in run else None,
        "framework_source": (
            "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/ARC-AGI-3-Agents"
            if "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/ARC-AGI-3-Agents" in run else None
        ),
        "framework_target": "/kaggle/working/ARC-AGI-3-Agents" if "/kaggle/working/ARC-AGI-3-Agents" in run else None,
        "registered_agent": {"key": "myagent", "class": "MyAgent"} if registry else None,
        "runtime_env": _runtime_env_projection(run),
        "launch_argv": argv,
        "run_urls": urls,
        "dummy": _dummy_projection(code[3]),
    }


def inspect_notebook(
    notebook: Any,
    agent_source: str,
    source_lock_sha256: str,
    runtime_inventory_sha256: str,
) -> dict[str, Any]:
    require_exact_keys(notebook, {"metadata", "nbformat", "nbformat_minor", "cells"}, "notebook")
    require(notebook["nbformat"] == 4 and type(notebook["nbformat"]) is int, "notebook nbformat")
    require(notebook["nbformat_minor"] == 4 and type(notebook["nbformat_minor"]) is int, "notebook nbformat_minor")
    metadata = notebook["metadata"]
    require_exact_keys(metadata, {"kernelspec", "language_info", "kaggle", "hearthline"}, "notebook metadata")
    require_exact_keys(metadata["kernelspec"], {"display_name", "language", "name"}, "notebook kernelspec")
    require_exact_keys(metadata["language_info"], {"file_extension", "mimetype", "name", "pygments_lexer"}, "notebook language_info")
    require_exact_keys(metadata["kaggle"], {"accelerator", "isGpuEnabled", "isInternetEnabled", "language", "sourceType"}, "notebook kaggle metadata")
    require_exact_keys(metadata["hearthline"], {
        "agent_sha256", "builder", "public_agents_commit",
        "kaggle_runtime_agents_commit", "official_starter_commit",
        "source_lock_sha256", "runtime_inventory_sha256",
    }, "notebook Hearthline metadata")
    hearthline_metadata = metadata["hearthline"]
    require(
        hearthline_metadata["agent_sha256"]
        == sha256(agent_source.encode("utf-8")),
        "notebook Hearthline agent binding",
    )
    require(
        hearthline_metadata["builder"] == "scripts/build_notebook.py",
        "notebook Hearthline builder binding",
    )
    require(
        hearthline_metadata["public_agents_commit"]
        == "4743e7d0aaae0ded0d98a89a7e282e63564cd58b",
        "notebook public Agents binding",
    )
    require(
        hearthline_metadata["kaggle_runtime_agents_commit"]
        == "135f20aaf44f13341ebc425666bf03b5cac58d3c",
        "notebook Kaggle runtime Agents binding",
    )
    require(
        hearthline_metadata["official_starter_commit"]
        == "eeb1535404f321d280a8f9194bbc1d7aca5f05fc",
        "notebook official starter binding",
    )
    for field, expected in (
        ("source_lock_sha256", source_lock_sha256),
        ("runtime_inventory_sha256", runtime_inventory_sha256),
    ):
        require(
            isinstance(hearthline_metadata[field], str)
            and re.fullmatch(r"[0-9a-f]{64}", hearthline_metadata[field]) is not None,
            f"notebook Hearthline {field} binding",
        )
        require(
            hearthline_metadata[field] == expected,
            f"notebook Hearthline {field} mismatch",
        )
    require(metadata["kaggle"]["isInternetEnabled"] is False, "notebook internet must be disabled")
    accelerator_key = (metadata["kaggle"]["accelerator"], metadata["kaggle"]["isGpuEnabled"])
    require(accelerator_key in ACCELERATOR_BY_METADATA, "notebook accelerator metadata mismatch")
    cells = notebook["cells"]
    require(isinstance(cells, list) and len(cells) == 5, "starter notebook cells missing")
    expected_types = ["markdown", "code", "code", "code", "code"]
    require([cell.get("cell_type") for cell in cells] == expected_types, "notebook cell order")
    require_exact_keys(cells[0], {"cell_type", "metadata", "source"}, "notebook markdown cell")
    require(cells[0]["metadata"] == {}, "markdown cell metadata must be empty")
    for index, cell in enumerate(cells[1:], start=1):
        require_exact_keys(cell, {"cell_type", "execution_count", "metadata", "outputs", "source"}, f"notebook code cell {index}")
        require(cell["execution_count"] is None, f"notebook code cell {index} execution_count")
        require(cell["metadata"] == {"trusted": True}, f"notebook code cell {index} metadata")
        require(cell["outputs"] == [], f"notebook code cell {index} must have no outputs")
        require(isinstance(cell["source"], str), f"notebook code cell {index} source")
    code = [cell["source"] for cell in cells[1:]]
    install_projection = _install_projection(code[0])
    require(
        install_projection["packages"]
        == ["arc-agi", "arcengine", "python-dotenv"],
        "candidate install package set",
    )
    embedded = [text for text in code if text.startswith("%%writefile /tmp/my_agent.py\n")]
    require(len(embedded) == 1 and embedded[0].split("\n", 1)[1] == agent_source, "embedded agent differs from committed source")
    joined = "\n".join(code)
    for forbidden in ("KAGGLE_API_TOKEN", ".kaggle/access_token", "kaggle kernels", "enable_internet=True"):
        require(forbidden not in joined, f"notebook contains forbidden staging surface: {forbidden}")
    urls = re.findall(r"https?://[^\"'\s]+", joined)
    require(all(url.startswith("http://gateway:8001/") for url in urls), f"unexpected notebook URL: {urls}")
    for required in (
        "HEARTHLINE_STAGE_INVENTORY=", "importlib.metadata.distributions",
        '"agents/agent.py"', '"agents/recorder.py"', '"agents/swarm.py"',
        '"agents/tracing.py"', '"main.py"', '"agents_license_file"', '"LICENSE"',
    ):
        require(required in code[-1], f"private-stage inventory surface missing: {required}")
    for required in (
        "importlib.metadata.version",
        "runtime_closure_status",
        "RUNTIME_CLOSURE_UNFROZEN",
        "FROZEN_POST_STAGE_SUCCESSOR",
        "expected_python_version",
        "Python version mismatch before competition rerun",
        "importlib.metadata.distributions",
        "conflicting canonical distribution versions",
        "expected_runtime_versions",
        "expected_agents_files",
        "expected_license_file",
        "expected_target_files",
        "runtime version mismatch before competition rerun",
        "Agents source mismatch before competition rerun",
        "copied Agents files changed before framework import",
        "passthrough_environment",
        "urllib.request.ProxyHandler({})",
        "_NoGatewayRedirect",
        "competition gateway redirect is forbidden",
        "gateway_ready",
        "bound_interpreter_identity",
        "competition Python interpreter identity changed before launch",
        "str(bound_interpreter_path)",
        '"-E", "-s", "-B", "main.py"',
        'example_environment = target / ".env.example"',
        "neutralized .env.example changed before framework import",
        'framework_environment["HOME"] = str(runtime_home)',
        'framework_environment["NETRC"] = str(runtime_netrc)',
        '("AGENTOPS_API_KEY", "")',
        '("OPENAI_API_KEY", "")',
    ):
        require(required in code[2], f"competition-rerun preflight missing: {required}")
    require(
        "random_agent" not in code[2] and '"random":' not in code[2],
        "competition-rerun registry may only import the measured candidate agent",
    )
    require(
        "shutil.copytree" not in code[2],
        "competition-rerun runtime may not copy the unclosed platform tree",
    )
    return {
        "accelerator": ACCELERATOR_BY_METADATA[accelerator_key],
        "code_cells": 4,
        "internet_enabled": False,
        "urls": urls,
    }


def _validated_distribution_inventory(inventory: Any) -> tuple[list[dict[str, str]], dict[str, str]]:
    require_exact_keys(
        inventory,
        {"agents_files", "agents_license_file", "distributions", "python_version"},
        "runtime inventory",
    )
    rows = inventory["distributions"]
    require(isinstance(rows, list), "runtime inventory distributions")
    require(len(rows) == 875, "runtime inventory distribution count")
    names: list[str] = []
    versions: dict[str, str] = {}
    for index, row in enumerate(rows):
        require_exact_keys(row, {"name", "version"}, f"runtime distribution {index}")
        name = row["name"]
        version = row["version"]
        require(
            isinstance(name, str)
            and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is not None,
            f"runtime distribution {index} canonical name",
        )
        require(
            isinstance(version, str) and bool(version),
            f"runtime distribution {index} version",
        )
        require(name not in versions, f"runtime inventory duplicate distribution: {name}")
        names.append(name)
        versions[name] = version
    require(names == sorted(names), "runtime inventory ordering")
    require(inventory["python_version"] == "3.12.13", "runtime inventory Python version")
    return rows, versions


def _validate_reviewed_runtime_assets(
    source_lock: dict[str, Any],
    inventory_bytes: bytes,
    review_receipt_bytes: bytes,
    *,
    public_agents: dict[str, Any],
    public_toolkit: dict[str, Any],
) -> dict[str, Any]:
    """Independently validate the reviewed platform runtime and its receipt."""
    inventory = loads_strict(inventory_bytes, "runtime inventory")
    review_receipt = loads_strict(review_receipt_bytes, "runtime review receipt")
    distribution_rows, version_map = _validated_distribution_inventory(inventory)
    dependency = source_lock["dependency_resolution"]
    required_versions = dependency["required_runtime_versions"]
    require(
        all(version_map.get(name) == version for name, version in required_versions.items()),
        "runtime inventory required versions",
    )

    reviewed = dependency["reviewed_stage_runtime"]
    require_exact_keys(reviewed, {
        "schema", "stage_identity", "output", "python_version", "inventory",
        "runtime_file_bindings", "runtime_license_binding",
        "official_historical_provenance", "machine_evidence", "human_review",
    }, "reviewed stage runtime")
    require(
        reviewed["schema"] == "hearthline-plays.arc3-reviewed-stage-runtime.v1",
        "reviewed stage runtime schema",
    )
    require_exact_keys(reviewed["stage_identity"], {
        "kernel_slug", "kernel_version", "status", "visibility",
        "internet_enabled", "accelerator", "candidate_snapshot_sha256",
        "machine_evidence_recorded_at_utc",
    }, "reviewed stage identity")
    expected_stage = {
        "kernel_slug": "grativy6/hearthline-arc3-readiness",
        "kernel_version": 4,
        "status": "COMPLETE",
        "visibility": "private",
        "internet_enabled": False,
        "accelerator": "cpu",
        "candidate_snapshot_sha256": "823cd5c7a99b16141959a09f011e361b2c03615ea37e72a65880a9eb5e8db4d0",
        "machine_evidence_recorded_at_utc": "2026-09-06T23:53:42Z",
    }
    require(reviewed["stage_identity"] == expected_stage, "reviewed stage identity")
    require_exact_keys(reviewed["output"], {
        "path", "bytes", "sha256", "parquet_magic_valid",
        "output_inventory_count",
    }, "reviewed stage output")
    require(reviewed["output"] == {
        "path": "submission.parquet",
        "bytes": 2648,
        "sha256": "71bfd543030e339d87bd9ff744d466218398a1259650b2c255626d27049c88bb",
        "parquet_magic_valid": True,
        "output_inventory_count": 1,
    }, "reviewed stage output")
    require(reviewed["python_version"] == inventory["python_version"], "reviewed runtime Python binding")
    require_exact_keys(reviewed["inventory"], {
        "path", "sha256", "distribution_count", "canonical_names_unique",
        "canonical_names_sorted",
    }, "reviewed runtime inventory binding")
    require(reviewed["inventory"] == {
        "path": "launch/runtime/kaggle-stage-v4-runtime-inventory.json",
        "sha256": sha256(inventory_bytes),
        "distribution_count": len(distribution_rows),
        "canonical_names_unique": True,
        "canonical_names_sorted": True,
    }, "reviewed runtime inventory binding")

    runtime_files = reviewed["runtime_file_bindings"]
    expected_runtime_files = {
        "agents/agent.py": "85655f7a11a105e50bba76efd00bebf8056d02ddbae827a8f8a5b46e849fc087",
        "agents/recorder.py": "0a08d89f4067a760012767c05d4406bd2bf409f426e29a1193106abfcbb696c8",
        "agents/swarm.py": "d9dc48f710f1b90a6552db0921293c7e89c8a925ed00a3faefa07ae19998ad39",
        "agents/tracing.py": "951ca56508c524504e116303f7c64f4eb5cf723c72cab892d4d1a3292b1cc51f",
        "main.py": "864254c750bbbd12a211f2d8aa1b1025d0609283f07dea4ede83722f2435301b",
    }
    require(runtime_files == expected_runtime_files, "reviewed Kaggle runtime file hashes")
    require(inventory["agents_files"] == runtime_files, "runtime inventory/file binding mismatch")
    require(
        sha256(inventory_bytes) == REVIEWED_RUNTIME_INVENTORY_SHA256,
        "reviewed runtime inventory evidence hash",
    )
    runtime_license = reviewed["runtime_license_binding"]
    require_exact_keys(runtime_license, {
        "path", "sha256", "spdx", "copyright_notice",
    }, "reviewed runtime license binding")
    require(runtime_license == {
        "path": "LICENSE",
        "sha256": "75c4276c506fd93082b38ad39f67ee97aa859574401ef978e701710c7a40af04",
        "spdx": "MIT",
        "copyright_notice": "Copyright (c) 2025 ARC Prize",
    }, "reviewed runtime license binding")
    runtime_license_file = {runtime_license["path"]: runtime_license["sha256"]}
    require(
        inventory["agents_license_file"] == runtime_license_file,
        "runtime inventory/license binding mismatch",
    )

    public_files = {
        path: binding.get("sha256") if isinstance(binding, dict) else None
        for path, binding in public_agents["inspected_file_bindings"].items()
    }
    require(
        public_files["agents/agent.py"]
        == "49f1a349cd5e2123fceb266aec4a3a758d18ef5520e0212e808f695905d9e073",
        "public Agents source hash",
    )
    require(
        public_files["agents/agent.py"] != runtime_files["agents/agent.py"],
        "public source and Kaggle runtime bindings were conflated",
    )
    require(public_toolkit["version"] == "0.9.9", "public ARC-AGI source version")

    provenance = reviewed["official_historical_provenance"]
    require_exact_keys(provenance, {
        "kind", "repository", "commit", "tree", "inspected_file_bindings",
        "license_file_binding", "same_agents_agent_blob_also_at_parallel_commit",
        "claim_ceiling",
    }, "reviewed runtime provenance")
    require(
        provenance["kind"] == "KAGGLE_PLATFORM_COMPETITION_INPUT"
        and provenance["repository"] == "arcprize/ARC-AGI-3-Agents"
        and provenance["commit"] == "135f20aaf44f13341ebc425666bf03b5cac58d3c"
        and provenance["tree"] == "d7fbafe6e2ed191189db89e5b571fd26da3dc375"
        and provenance["same_agents_agent_blob_also_at_parallel_commit"]
        == "ca950a814c1a16b90e08ac9bc6e2f7720871980d",
        "reviewed runtime provenance identity",
    )
    provenance_files = provenance["inspected_file_bindings"]
    require(
        isinstance(provenance_files, dict) and set(provenance_files) == set(runtime_files),
        "reviewed runtime provenance file inventory",
    )
    for path, binding in provenance_files.items():
        require_exact_keys(binding, {"git_blob", "sha256"}, f"runtime provenance {path}")
        require(
            isinstance(binding["git_blob"], str)
            and re.fullmatch(r"[0-9a-f]{40}", binding["git_blob"]) is not None,
            f"runtime provenance {path} Git blob",
        )
    require(
        {path: binding["sha256"] for path, binding in provenance_files.items()}
        == runtime_files,
        "reviewed runtime provenance file hashes",
    )
    require_exact_keys(
        provenance["license_file_binding"],
        {"path", "git_blob", "sha256"},
        "reviewed runtime provenance license",
    )
    require(
        provenance["license_file_binding"]["path"] == runtime_license["path"]
        and provenance["license_file_binding"]["sha256"] == runtime_license["sha256"],
        "reviewed runtime provenance license binding",
    )

    machine = reviewed["machine_evidence"]
    require_exact_keys(machine, {
        "evidence_manifest_sha256", "logs_sha256", "recorded_at_utc",
        "private_artifact_paths_committed",
    }, "reviewed runtime machine evidence")
    require(
        isinstance(machine["evidence_manifest_sha256"], str)
        and re.fullmatch(r"[0-9a-f]{64}", machine["evidence_manifest_sha256"])
        is not None
        and isinstance(machine["logs_sha256"], str)
        and re.fullmatch(r"[0-9a-f]{64}", machine["logs_sha256"]) is not None,
        "reviewed runtime machine evidence hashes",
    )
    require(
        machine["evidence_manifest_sha256"]
        == "b4dd87fe2a0a17e8083bdcfb81a1be2b191fb45776e33e234d369c8918e93b06"
        and machine["logs_sha256"]
        == "1471812acc99ca75ca234ea7defd727128a43869bea26e4e91a8577dd062eb53"
        and machine["recorded_at_utc"] == expected_stage["machine_evidence_recorded_at_utc"]
        and machine["private_artifact_paths_committed"] is False,
        "reviewed runtime machine evidence binding",
    )

    human = reviewed["human_review"]
    require_exact_keys(human, {
        "receipt_path", "receipt_sha256", "reviewed_by", "reviewed_at_utc",
        "attestation_sha256", "public_source_pin_retained",
        "runtime_binding_accepted",
    }, "reviewed runtime human review")
    require(
        human["receipt_path"]
        == "launch/receipts/20260907T002817Z-stage-v4-runtime-review.json"
        and human["receipt_sha256"] == sha256(review_receipt_bytes)
        and human["receipt_sha256"] == RUNTIME_REVIEW_RECEIPT_SHA256
        and human["reviewed_by"] == "Christopher D. Pang"
        and human["reviewed_at_utc"] == "2026-09-07T00:28:17Z"
        and human["attestation_sha256"] == RUNTIME_REVIEW_ATTESTATION_SHA256
        and human["public_source_pin_retained"] is True
        and human["runtime_binding_accepted"] is True,
        "reviewed runtime human review binding",
    )

    require_exact_keys(review_receipt, {
        "schema", "recorded_at", "status", "review", "binding",
        "authority_boundary",
    }, "runtime review receipt")
    require(
        review_receipt["schema"]
        == "hearthline-plays.arc3-stage-runtime-review-receipt.v1"
        and review_receipt["status"]
        == "HUMAN_REVIEW_ACCEPTED_FOR_LOCAL_SUCCESSOR_REPAIR"
        and review_receipt["recorded_at"] == "2026-09-07T00:28:17Z",
        "runtime review receipt identity",
    )
    require_exact_keys(review_receipt["review"], {
        "reviewed_by", "reviewed_at", "attestation", "attestation_sha256",
    }, "runtime review receipt review")
    receipt_review = review_receipt["review"]
    require(
        receipt_review["reviewed_by"] == human["reviewed_by"]
        and receipt_review["reviewed_at"] == human["reviewed_at_utc"]
        and receipt_review["attestation_sha256"] == human["attestation_sha256"]
        and sha256(receipt_review["attestation"].encode("utf-8"))
        == receipt_review["attestation_sha256"],
        "runtime review receipt attestation",
    )
    require_exact_keys(review_receipt["binding"], {
        "candidate_evidence", "stage", "output", "runtime_inventory",
        "runtime_file_bindings", "runtime_license_binding", "machine_evidence",
        "public_source_pin", "observed_runtime_provenance",
    }, "runtime review receipt binding")
    binding = review_receipt["binding"]
    require_exact_keys(binding["candidate_evidence"], {
        "commit", "tree", "snapshot_sha256",
    }, "runtime review candidate evidence")
    require(binding["candidate_evidence"] == {
        "commit": "543ffbd2f90e3593dad577b3e088f9baacbef002",
        "tree": "c7c2f2660524cc38143dfa3f16edf03d2d8bc011",
        "snapshot_sha256": expected_stage["candidate_snapshot_sha256"],
    }, "runtime review candidate evidence")
    require_exact_keys(binding["stage"], {
        "kernel_slug", "kernel_version", "status", "visibility",
        "internet_enabled", "accelerator", "machine_evidence_recorded_at",
    }, "runtime review stage")
    expected_receipt_stage = dict(expected_stage)
    expected_receipt_stage.pop("candidate_snapshot_sha256")
    expected_receipt_stage["machine_evidence_recorded_at"] = expected_receipt_stage.pop(
        "machine_evidence_recorded_at_utc"
    )
    require(binding["stage"] == expected_receipt_stage, "runtime review stage binding")
    require(binding["output"] == reviewed["output"], "runtime review output binding")
    require(binding["runtime_file_bindings"] == runtime_files, "runtime review file binding")
    require(binding["runtime_inventory"] == {
        **reviewed["inventory"],
        "python_version": reviewed["python_version"],
        "required_versions": required_versions,
    }, "runtime review inventory binding")
    require_exact_keys(binding["runtime_license_binding"], {
        "path", "git_blob", "sha256", "spdx", "copyright_notice",
    }, "runtime review license binding")
    require(
        {
            key: binding["runtime_license_binding"][key]
            for key in ("path", "sha256", "spdx", "copyright_notice")
        }
        == runtime_license,
        "runtime review license binding",
    )
    require_exact_keys(binding["machine_evidence"], {
        "evidence_manifest_sha256", "logs_sha256", "private_artifact_paths_committed",
    }, "runtime review machine evidence")
    require(binding["machine_evidence"] == {
        key: machine[key]
        for key in (
            "evidence_manifest_sha256", "logs_sha256", "private_artifact_paths_committed",
        )
    }, "runtime review machine evidence binding")
    require(binding["public_source_pin"] == {
        "repository": "arcprize/ARC-AGI-3-Agents",
        "commit": public_agents["commit"],
        "tree": public_agents["tree"],
        "agents_agent_git_blob": public_agents["inspected_file_bindings"][
            "agents/agent.py"
        ]["git_blob"],
        "agents_agent_sha256": public_files["agents/agent.py"],
        "arc_agi_source_version": public_toolkit["version"],
        "retained_unchanged": True,
    }, "runtime review public source binding")
    require(binding["observed_runtime_provenance"] == {
        "kind": provenance["kind"],
        "repository": provenance["repository"],
        "official_historical_commit": provenance["commit"],
        "official_historical_tree": provenance["tree"],
        "inspected_file_bindings": provenance["inspected_file_bindings"],
        "license_file_binding": provenance["license_file_binding"],
        "same_agents_agent_blob_also_occurs_at_parallel_commit": provenance[
            "same_agents_agent_blob_also_at_parallel_commit"
        ],
        "claim_ceiling": provenance["claim_ceiling"],
    }, "runtime review provenance binding")
    require_exact_keys(review_receipt["authority_boundary"], {
        "local_repair_authorized", "grant_creation_or_consumption_authorized",
        "local_git_commit_as_repair_step_authorized", "remote_git_push_authorized",
        "kaggle_contact_or_stage_authorized", "gate_b_authorized",
        "competition_submission_authorized", "expired_grant_may_be_edited_or_reused",
    }, "runtime review authority boundary")
    require(review_receipt["authority_boundary"] == {
        "local_repair_authorized": True,
        "grant_creation_or_consumption_authorized": False,
        "local_git_commit_as_repair_step_authorized": True,
        "remote_git_push_authorized": False,
        "kaggle_contact_or_stage_authorized": False,
        "gate_b_authorized": False,
        "competition_submission_authorized": False,
        "expired_grant_may_be_edited_or_reused": False,
    }, "runtime review authority boundary")
    return {
        "reviewed": reviewed,
        "inventory": inventory,
        "distribution_rows": distribution_rows,
        "version_map": version_map,
        "runtime_files": runtime_files,
        "runtime_license_file": runtime_license_file,
        "provenance": provenance,
    }


def inspect_trusted_contracts(
    committed: dict[str, bytes],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Validate committed declarative inputs independently of the builder."""
    source_lock = loads_strict(committed["launch/source-lock.v4.json"], "source lock")
    contract = loads_strict(
        committed["launch/contracts/official-starter-eeb153.contract.json"],
        "official starter contract",
    )
    template = loads_strict(
        committed["notebooks/kernel-metadata.template.json"],
        "kernel metadata template",
    )
    require_exact_keys(source_lock, {
        "schema", "status", "recorded_at", "steward", "predecessor",
        "official_software", "competition_contract", "credential_contract",
        "dependency_resolution", "bounded_context_sources", "candidate_base",
        "run_rules", "residuals",
    }, "source lock")
    require(source_lock["schema"] == "hearthline-plays.arc3-launch-source-lock.v4", "source lock schema")
    require(
        source_lock["status"] == "FROZEN_POST_STAGE_SUCCESSOR_LOCAL_REPAIR_ONLY",
        "source lock status",
    )
    require(isinstance(source_lock["official_software"], list), "source lock official software")
    official_software = source_lock["official_software"]
    toolkit_rows = [
        row
        for row in official_software
        if isinstance(row, dict)
        and row.get("repository") == "arcprize/ARC-AGI"
    ]
    require(
        len(toolkit_rows) == 1,
        "source lock must contain exactly one public ARC-AGI identity",
    )
    toolkit = toolkit_rows[0]
    require(
        toolkit.get("commit") == "f12822c4d550121c35a275008d964afbbed47d2f"
        and toolkit.get("tree") == "9ee140e4183df0df109cec50b7cd0d2531c47168"
        and toolkit.get("version") == "0.9.9",
        "source lock public ARC-AGI identity",
    )
    by_repository = {
        row.get("repository"): row
        for row in official_software
        if isinstance(row, dict)
    }
    require(len(by_repository) == len(official_software), "source lock repository identities must be unique objects")
    starter = by_repository.get("arcprize/ARC-AGI-3-Kaggle-Starter")
    agents = by_repository.get("arcprize/ARC-AGI-3-Agents")
    require(
        isinstance(starter, dict)
        and isinstance(agents, dict),
        "pinned starter, toolkit, and Agents identities are required",
    )
    require(starter.get("commit") == "eeb1535404f321d280a8f9194bbc1d7aca5f05fc", "source lock starter commit")
    require(starter.get("tree") == "332ff438d9b092c95e58a07eace6194379de06b4", "source lock starter tree")
    require(starter.get("upstream_file_vendored") is False, "source lock starter vendoring disposition")
    require(starter.get("interoperability_literals_reexpressed") is True, "source lock starter interoperability disposition")
    require(starter.get("license_or_notice_file_observed_at_pin") is False, "source lock starter license observation")
    require(
        isinstance(starter.get("contract"), dict)
        and starter["contract"].get("python_minor") == "3.12",
        "source lock Python minor",
    )
    require(agents.get("commit") == "4743e7d0aaae0ded0d98a89a7e282e63564cd58b", "source lock Agents commit")
    require(agents.get("tree") == "6878fdfdd0156059323b541fc229b6329ad4fd28", "source lock Agents tree")
    require(
        agents.get("license_file_binding") == {
            "path": "LICENSE",
            "git_blob": "d8e1cd42ac40338c6c76a8a6ac18eea0eaf95fbe",
            "sha256": "75c4276c506fd93082b38ad39f67ee97aa859574401ef978e701710c7a40af04",
            "spdx": "MIT",
            "copyright_notice": "Copyright (c) 2025 ARC Prize",
        },
        "source lock Agents MIT license binding",
    )
    require(
        isinstance(agents.get("runtime_license_preservation"), str)
        and "exact LICENSE" in agents["runtime_license_preservation"]
        and "five sealed executable files" in agents["runtime_license_preservation"],
        "source lock Agents runtime license preservation",
    )
    agents_bindings = agents.get("inspected_file_bindings")
    require(isinstance(agents_bindings, dict), "source lock Agents file bindings")
    expected_agents_hashes = {
        "agents/agent.py": "49f1a349cd5e2123fceb266aec4a3a758d18ef5520e0212e808f695905d9e073",
        "agents/recorder.py": "0a08d89f4067a760012767c05d4406bd2bf409f426e29a1193106abfcbb696c8",
        "agents/swarm.py": "d9dc48f710f1b90a6552db0921293c7e89c8a925ed00a3faefa07ae19998ad39",
        "agents/tracing.py": "951ca56508c524504e116303f7c64f4eb5cf723c72cab892d4d1a3292b1cc51f",
        "main.py": "864254c750bbbd12a211f2d8aa1b1025d0609283f07dea4ede83722f2435301b",
    }
    require(
        set(agents_bindings) == set(expected_agents_hashes),
        "source lock executed Agents files",
    )
    require(
        {
            relative: binding.get("sha256") if isinstance(binding, dict) else None
            for relative, binding in agents_bindings.items()
        }
        == expected_agents_hashes,
        "source lock executed Agents file hashes",
    )
    dependency_resolution = source_lock["dependency_resolution"]
    require_exact_keys(dependency_resolution, {
        "starter_ranges_observed", "required_runtime_versions",
        "runtime_closure_status", "candidate_policy", "reviewed_stage_runtime",
        "successor_requirement", "current_blocker",
    }, "source lock dependency resolution")
    require(
        dependency_resolution["required_runtime_versions"]
        == {
            "arc-agi": "0.9.8",
            "arcengine": "0.9.3",
            "python-dotenv": "1.2.2",
        },
        "source lock required runtime versions",
    )
    require(
        dependency_resolution["runtime_closure_status"]
        == "FROZEN_POST_STAGE_SUCCESSOR",
        "source lock runtime closure status",
    )
    require(
        "fresh prospective Gate-A grant"
        in dependency_resolution["successor_requirement"]
        and "Gate B remains a separate human-authorized action"
        in dependency_resolution["successor_requirement"],
        "source lock runtime closure successor requirement",
    )

    require_exact_keys(contract, {"schema", "source", "projection", "claim_ceiling"}, "official starter contract")
    require(contract["schema"] == "hearthline.arc3.official-starter-contract.v1", "official starter contract schema")
    require_exact_keys(contract["source"], {
        "repository", "commit", "tree", "build_script_path", "build_script_sha256",
        "relationship", "license_observation",
    }, "official starter contract source")
    require(contract["source"]["repository"] == "arcprize/ARC-AGI-3-Kaggle-Starter", "starter contract repository")
    require(contract["source"]["commit"] == starter["commit"], "starter contract/source-lock commit mismatch")
    require(contract["source"]["tree"] == starter["tree"], "starter contract/source-lock tree mismatch")
    require(contract["source"]["build_script_path"] == "scripts/build_notebook.py", "starter contract build path")
    require(contract["source"]["build_script_sha256"] == "8c9961bc3a9006c0f187392426fc9a659176362b54592c4aad5b6b1a3f3da318", "starter contract script hash")
    require(isinstance(contract["projection"], dict) and contract["projection"], "starter contract projection is required")
    require(isinstance(contract["claim_ceiling"], str) and contract["claim_ceiling"].strip(), "starter contract claim ceiling")
    inspect_metadata(template)
    require(template["id"] == "REPLACE_WITH_YOUR_USERNAME/hearthline-arc3-readiness", "metadata template identity")
    require(template["enable_gpu"] is False, "metadata template must default to CPU")
    runtime_state = _validate_reviewed_runtime_assets(
        source_lock,
        committed["launch/runtime/kaggle-stage-v4-runtime-inventory.json"],
        committed["launch/receipts/20260907T002817Z-stage-v4-runtime-review.json"],
        public_agents=agents,
        public_toolkit=toolkit,
    )
    return source_lock, contract, template, runtime_state


def _expected_code_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"trusted": True},
        "outputs": [],
        "source": source,
    }


def _expected_notebook(
    agent_source: str,
    accelerator: str,
    python_version: str,
    runtime_closure_status: str,
    runtime_versions: dict[str, str],
    agents_files: dict[str, str],
    license_file: dict[str, str],
    source_lock_sha256: str,
    runtime_inventory_sha256: str,
) -> dict[str, Any]:
    """Verifier-owned renderer; it never imports or executes builder code."""
    require(accelerator in ACCELERATOR_SETTINGS, "candidate accelerator")
    accel = ACCELERATOR_SETTINGS[accelerator]
    require(
        isinstance(source_lock_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", source_lock_sha256) is not None,
        "candidate source lock SHA-256",
    )
    require(
        isinstance(runtime_inventory_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", runtime_inventory_sha256) is not None,
        "candidate runtime inventory SHA-256",
    )
    install = _expected_code_cell(
        dedent(
            """\
            import subprocess
            import sys

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--find-links",
                    "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels",
                    "arc-agi==0.9.8",
                    "arcengine==0.9.3",
                    "python-dotenv==1.2.2",
                ],
                check=True,
            )
            """
        )
    )
    write_agent = _expected_code_cell("%%writefile /tmp/my_agent.py\n" + agent_source)
    python_version_literal = json.dumps(python_version)
    runtime_closure_status_literal = json.dumps(runtime_closure_status)
    runtime_versions_literal = json.dumps(runtime_versions, sort_keys=True)
    agents_files_literal = json.dumps(agents_files, sort_keys=True)
    license_file_literal = json.dumps(license_file, sort_keys=True)
    candidate_agent_sha256_literal = json.dumps(sha256(agent_source.encode("utf-8")))
    run_source = dedent(
        """\
        import hashlib
        import importlib.metadata
        import os
        import re
        import shutil
        import stat
        import subprocess
        import sys
        import time
        import urllib.request
        from pathlib import Path

        if os.getenv("KAGGLE_IS_COMPETITION_RERUN"):
            runtime_closure_status = __RUNTIME_CLOSURE_STATUS__
            if runtime_closure_status != "FROZEN_POST_STAGE_SUCCESSOR":
                raise RuntimeError(
                    "RUNTIME_CLOSURE_UNFROZEN: Gate B requires a reviewed post-Stage-A successor"
                )
            expected_python_version = __EXPECTED_PYTHON_VERSION__
            observed_python_version = sys.version.split()[0]
            if observed_python_version != expected_python_version:
                raise RuntimeError(
                    "Python version mismatch before competition rerun: "
                    f"expected={expected_python_version!r}, observed={observed_python_version!r}"
                )
            try:
                bound_interpreter_path = Path(sys.executable).resolve(strict=True)
                bound_interpreter_stat = bound_interpreter_path.stat()
            except OSError as exc:
                raise RuntimeError("cannot bind the competition Python interpreter") from exc
            if not stat.S_ISREG(bound_interpreter_stat.st_mode):
                raise RuntimeError("competition Python interpreter is not a regular file")
            bound_interpreter_identity = (
                bound_interpreter_stat.st_dev,
                bound_interpreter_stat.st_ino,
                bound_interpreter_stat.st_size,
                bound_interpreter_stat.st_mtime_ns,
            )

            expected_runtime_versions = __EXPECTED_RUNTIME_VERSIONS__
            distribution_versions = {}
            for distribution in importlib.metadata.distributions():
                raw_name = str(distribution.metadata.get("Name", distribution.name)).strip()
                name = re.sub(r"[-_.]+", "-", raw_name).lower()
                if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is None:
                    raise RuntimeError(f"invalid canonical distribution name: {raw_name!r}")
                version = str(distribution.version)
                distribution_versions.setdefault(name, set()).add(version)
            observed_runtime_versions = {}
            for name in sorted(distribution_versions):
                versions = sorted(distribution_versions[name])
                if len(versions) == 1:
                    observed_runtime_versions[name] = versions[0]
                    continue
                effective_version = None
                try:
                    effective_version = str(importlib.metadata.version(name))
                except importlib.metadata.PackageNotFoundError:
                    pass
                if effective_version not in versions:
                    raise RuntimeError(
                        "conflicting canonical distribution versions: "
                        + f"{name}: {' != '.join(repr(version) for version in versions)}"
                    )
                observed_runtime_versions[name] = effective_version
            if observed_runtime_versions != expected_runtime_versions:
                raise RuntimeError(
                    "runtime version mismatch before competition rerun: "
                    f"expected={expected_runtime_versions!r}, "
                    f"observed={observed_runtime_versions!r}"
                )

            expected_agents_files = __EXPECTED_AGENTS_FILES__
            source = Path("/kaggle/input/competitions/arc-prize-2026-arc-agi-3/ARC-AGI-3-Agents")
            observed_source_files = {}
            for relative in sorted(expected_agents_files):
                path = source / relative
                try:
                    observed_source_files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    observed_source_files[relative] = None
            if observed_source_files != expected_agents_files:
                raise RuntimeError(
                    "Agents source mismatch before competition rerun: "
                    f"expected={expected_agents_files!r}, observed={observed_source_files!r}"
                )
            expected_license_file = __EXPECTED_LICENSE_FILE__
            observed_license_file = {}
            for relative in sorted(expected_license_file):
                path = source / relative
                try:
                    observed_license_file[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    observed_license_file[relative] = None
            if observed_license_file != expected_license_file:
                raise RuntimeError(
                    "Agents license mismatch before competition rerun: "
                    f"expected={expected_license_file!r}, observed={observed_license_file!r}"
                )
            candidate_agent = Path("/tmp/my_agent.py")
            try:
                observed_candidate_agent = hashlib.sha256(candidate_agent.read_bytes()).hexdigest()
            except OSError:
                observed_candidate_agent = None
            expected_candidate_agent = __EXPECTED_CANDIDATE_AGENT_SHA256__
            if observed_candidate_agent != expected_candidate_agent:
                raise RuntimeError("candidate agent changed before competition rerun")

            class _NoGatewayRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, request, file_pointer, code, message, headers, new_url):
                    raise RuntimeError("competition gateway redirect is forbidden")

            gateway = "http://gateway:8001/api/games"
            gateway_opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                _NoGatewayRedirect(),
            )
            deadline = time.monotonic() + 600
            while True:
                gateway_ready = False
                try:
                    with gateway_opener.open(gateway, timeout=5) as response:
                        if response.status == 200:
                            gateway_ready = True
                except Exception:
                    gateway_ready = False
                if gateway_ready:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("competition gateway did not become ready")
                time.sleep(5)

            target = Path("/kaggle/working/ARC-AGI-3-Agents")
            if target.exists():
                raise RuntimeError("competition working target already exists")
            target.mkdir(mode=0o700)
            (target / "agents").mkdir(mode=0o700)
            (target / "agents/templates").mkdir(mode=0o700)
            for relative in sorted(expected_agents_files):
                shutil.copy2(source / relative, target / relative)
            for relative in sorted(expected_license_file):
                shutil.copy2(source / relative, target / relative)
            example_environment = target / ".env.example"
            example_environment.write_bytes(b"")
            templates_init = target / "agents/templates/__init__.py"
            templates_init.write_bytes(b"")
            shutil.copy2(candidate_agent, target / "agents/templates/my_agent.py")

            registry_rows = (
                "from typing import Type",
                "from dotenv import load_dotenv",
                "from .agent import Agent, Playback",
                "from .swarm import Swarm",
                "from .templates.my_agent import MyAgent",
                "",
                "load_dotenv()",
                "AVAILABLE_AGENTS: dict[str, Type[Agent]] = {",
                '    "myagent": MyAgent,',
                "}",
            )
            registry_text = "\\n".join(registry_rows) + "\\n"
            registry_path = target / "agents/__init__.py"
            registry_path.write_text(registry_text, encoding="utf-8")

            runtime_settings = (
                ("SCHEME", "http"),
                ("HOST", "gateway"),
                ("PORT", "8001"),
                ("ARC_API_KEY", "test-key-123"),
                ("ARC_BASE_URL", "http://gateway:8001/"),
                ("OPERATION_MODE", "online"),
                ("ENVIRONMENTS_DIR", ""),
                ("RECORDINGS_DIR", "/kaggle/working/server_recording"),
                ("DEBUG", "False"),
                ("AGENTOPS_API_KEY", ""),
                ("OPENAI_API_KEY", ""),
                ("ANTHROPIC_API_KEY", ""),
                ("GOOGLE_API_KEY", ""),
                ("GEMINI_API_KEY", ""),
                ("GROQ_API_KEY", ""),
                ("MISTRAL_API_KEY", ""),
                ("COHERE_API_KEY", ""),
                ("TOGETHER_API_KEY", ""),
                ("OPENROUTER_API_KEY", ""),
                ("LANGSMITH_API_KEY", ""),
                ("WANDB_API_KEY", ""),
                ("HF_TOKEN", ""),
                ("HUGGING_FACE_HUB_TOKEN", ""),
                ("HUGGINGFACEHUB_API_TOKEN", ""),
            )
            runtime_text = "\\n".join(f"{key}={value}" for key, value in runtime_settings) + "\\n"
            runtime_path = target / ".env"
            runtime_path.write_text(runtime_text, encoding="utf-8")
            runtime_home = target / ".runtime-home"
            runtime_home.mkdir(mode=0o700)
            runtime_config_home = runtime_home / ".config"
            runtime_config_home.mkdir(mode=0o700)
            runtime_netrc = runtime_home / ".netrc"
            runtime_netrc.write_bytes(b"")

            observed_copied_files = {
                relative: hashlib.sha256((target / relative).read_bytes()).hexdigest()
                for relative in sorted(expected_agents_files)
            }
            observed_runtime_versions = {
                distribution_name: importlib.metadata.version(distribution_name)
                for distribution_name in sorted(expected_runtime_versions)
            }
            if observed_copied_files != expected_agents_files:
                raise RuntimeError("copied Agents files changed before framework import")
            observed_copied_license = {
                relative: hashlib.sha256((target / relative).read_bytes()).hexdigest()
                for relative in sorted(expected_license_file)
            }
            if observed_copied_license != expected_license_file:
                raise RuntimeError("copied Agents license changed before framework import")
            if (
                hashlib.sha256((target / "agents/templates/my_agent.py").read_bytes()).hexdigest()
                != expected_candidate_agent
            ):
                raise RuntimeError("copied candidate agent changed before framework import")
            if observed_runtime_versions != expected_runtime_versions:
                raise RuntimeError("runtime versions changed before framework import")
            if example_environment.read_bytes() != b"":
                raise RuntimeError("neutralized .env.example changed before framework import")
            if templates_init.read_bytes() != b"":
                raise RuntimeError("generated templates package changed before framework import")
            if registry_path.read_text(encoding="utf-8") != registry_text:
                raise RuntimeError("generated agent registry changed before framework import")
            if runtime_path.read_text(encoding="utf-8") != runtime_text:
                raise RuntimeError("generated runtime environment changed before framework import")
            if runtime_netrc.read_bytes() != b"":
                raise RuntimeError("generated empty netrc changed before framework import")
            expected_target_files = {
                ".env",
                ".env.example",
                ".runtime-home/.netrc",
                "LICENSE",
                "agents/__init__.py",
                "agents/agent.py",
                "agents/recorder.py",
                "agents/swarm.py",
                "agents/templates/__init__.py",
                "agents/templates/my_agent.py",
                "agents/tracing.py",
                "main.py",
            }
            expected_target_directories = {
                ".runtime-home",
                ".runtime-home/.config",
                "agents",
                "agents/templates",
            }
            observed_target_files = set()
            observed_target_directories = set()
            for entry in target.rglob("*"):
                relative = entry.relative_to(target).as_posix()
                if entry.is_symlink():
                    raise RuntimeError(f"runtime target contains a symlink: {relative}")
                if entry.is_file():
                    observed_target_files.add(relative)
                elif entry.is_dir():
                    observed_target_directories.add(relative)
                else:
                    raise RuntimeError(f"runtime target contains a special file: {relative}")
            if observed_target_files != expected_target_files:
                raise RuntimeError("runtime target file inventory is not closed")
            if observed_target_directories != expected_target_directories:
                raise RuntimeError("runtime target directory inventory is not closed")

            passthrough_environment = (
                "CUDA_VISIBLE_DEVICES",
                "LANG",
                "LC_ALL",
                "NVIDIA_VISIBLE_DEVICES",
                "TMPDIR",
                "TZ",
            )
            framework_environment = {
                key: os.environ[key]
                for key in passthrough_environment
                if key in os.environ
            }
            framework_environment.update(dict(runtime_settings))
            framework_environment["HOME"] = str(runtime_home)
            framework_environment["XDG_CONFIG_HOME"] = str(runtime_config_home)
            framework_environment["NETRC"] = str(runtime_netrc)
            framework_environment["MPLBACKEND"] = "agg"
            try:
                current_interpreter_path = Path(sys.executable).resolve(strict=True)
                current_interpreter_stat = current_interpreter_path.stat()
            except OSError as exc:
                raise RuntimeError("cannot recheck the competition Python interpreter") from exc
            current_interpreter_identity = (
                current_interpreter_stat.st_dev,
                current_interpreter_stat.st_ino,
                current_interpreter_stat.st_size,
                current_interpreter_stat.st_mtime_ns,
            )
            if (
                current_interpreter_path != bound_interpreter_path
                or current_interpreter_identity != bound_interpreter_identity
                or not stat.S_ISREG(current_interpreter_stat.st_mode)
            ):
                raise RuntimeError("competition Python interpreter identity changed before launch")
            subprocess.run(
                [str(bound_interpreter_path), "-E", "-s", "-B", "main.py", "--agent", "myagent"],
                cwd=target,
                env=framework_environment,
                check=True,
            )
        """
    )
    run_source = run_source.replace(
        "__RUNTIME_CLOSURE_STATUS__", runtime_closure_status_literal
    ).replace(
        "__EXPECTED_PYTHON_VERSION__", python_version_literal
    ).replace(
        "__EXPECTED_RUNTIME_VERSIONS__", runtime_versions_literal
    ).replace(
        "__EXPECTED_AGENTS_FILES__", agents_files_literal
    ).replace(
        "__EXPECTED_LICENSE_FILE__", license_file_literal
    ).replace(
        "__EXPECTED_CANDIDATE_AGENT_SHA256__", candidate_agent_sha256_literal
    )
    run_framework = _expected_code_cell(run_source)
    dummy = _expected_code_cell(dedent(
        """\
        import hashlib
        import importlib.metadata
        import json
        import os
        import re
        import sys
        from pathlib import Path

        if not os.getenv("KAGGLE_IS_COMPETITION_RERUN"):
            distribution_versions = {}
            for distribution in importlib.metadata.distributions():
                raw_name = str(distribution.metadata.get("Name", distribution.name)).strip()
                name = re.sub(r"[-_.]+", "-", raw_name).lower()
                if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is None:
                    raise RuntimeError(f"invalid canonical distribution name: {raw_name!r}")
                version = str(distribution.version)
                distribution_versions.setdefault(name, set()).add(version)
            distributions = {}
            for name in sorted(distribution_versions):
                versions = sorted(distribution_versions[name])
                if len(versions) == 1:
                    distributions[name] = versions[0]
                    continue
                effective_version = None
                try:
                    effective_version = str(importlib.metadata.version(name))
                except importlib.metadata.PackageNotFoundError:
                    pass
                if effective_version not in versions:
                    raise RuntimeError(
                        "conflicting canonical distribution versions: "
                        + f"{name}: {' != '.join(repr(version) for version in versions)}"
                    )
                distributions[name] = effective_version
            framework_root = Path(
                "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/ARC-AGI-3-Agents"
            )
            agents_files = {}
            for relative in (
                "agents/agent.py",
                "agents/recorder.py",
                "agents/swarm.py",
                "agents/tracing.py",
                "main.py",
            ):
                path = framework_root / relative
                agents_files[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            license_path = framework_root / "LICENSE"
            agents_license_file = {
                "LICENSE": hashlib.sha256(license_path.read_bytes()).hexdigest()
                if license_path.is_file()
                else None
            }
            stage_inventory = {
                "python_version": sys.version.split()[0],
                "distributions": [
                    {"name": name, "version": distributions[name]}
                    for name in sorted(distributions)
                ],
                "agents_files": agents_files,
                "agents_license_file": agents_license_file,
            }
            print(
                "HEARTHLINE_STAGE_INVENTORY="
                + json.dumps(stage_inventory, sort_keys=True, separators=(",", ":"))
            )

            import pandas as pd
            submission = pd.DataFrame(
                data=[["1_0", "1", True, 1]],
                columns=["row_id", "game_id", "end_of_game", "score"],
            )
            submission.to_parquet("/kaggle/working/submission.parquet", index=False)
        """
    ))
    return {
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {
                "file_extension": ".py", "mimetype": "text/x-python", "name": "python",
                "pygments_lexer": "ipython3",
            },
            "kaggle": {
                "accelerator": accel["name"], "isGpuEnabled": accel["gpu"],
                "isInternetEnabled": False, "language": "python", "sourceType": "notebook",
            },
            "hearthline": {
                "agent_sha256": sha256(agent_source.encode("utf-8")),
                "builder": "scripts/build_notebook.py",
                "public_agents_commit": "4743e7d0aaae0ded0d98a89a7e282e63564cd58b",
                "kaggle_runtime_agents_commit": "135f20aaf44f13341ebc425666bf03b5cac58d3c",
                "official_starter_commit": "eeb1535404f321d280a8f9194bbc1d7aca5f05fc",
                "source_lock_sha256": source_lock_sha256,
                "runtime_inventory_sha256": runtime_inventory_sha256,
            },
        },
        "nbformat": 4,
        "nbformat_minor": 4,
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": (
                "# Hearthline ARC-AGI-3 candidate\n\n"
                "Generated offline from `agent/my_agent.py`. Phase A only stages a private kernel; "
                "Phase B is a separate manual competition-UI decision."
            )},
            install, write_agent, run_framework, dummy,
        ],
    }


def render_expected_candidate(
    committed: dict[str, bytes], identity: dict[str, Any], account_slug: str, accelerator: str
) -> dict[str, bytes]:
    """Independently regenerate the complete candidate from committed bytes."""
    source_lock, _, template, runtime_state = inspect_trusted_contracts(committed)
    agent_source = committed["agent/my_agent.py"].decode("utf-8")
    metadata = dict(template)
    metadata["id"] = f"{account_slug}/hearthline-arc3-readiness"
    metadata["enable_gpu"] = ACCELERATOR_SETTINGS[accelerator]["gpu"]
    notebook = _expected_notebook(
        agent_source,
        accelerator,
        runtime_state["reviewed"]["python_version"],
        source_lock["dependency_resolution"]["runtime_closure_status"],
        dict(runtime_state["version_map"]),
        dict(runtime_state["runtime_files"]),
        dict(runtime_state["runtime_license_file"]),
        sha256(committed["launch/source-lock.v4.json"]),
        sha256(committed["launch/runtime/kaggle-stage-v4-runtime-inventory.json"]),
    )
    notebook_bytes = (json.dumps(notebook, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
    metadata_bytes = (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    manifest = {
        "schema": "hearthline.arc3.offline-candidate-manifest.v4",
        "candidate": {"commit": identity["commit"], "tree": identity["tree"], "worktree_clean": True},
        "parameters": {
            "accelerator": accelerator,
            "account_slug": account_slug,
            "kernel_id": f"{account_slug}/hearthline-arc3-readiness",
        },
        "trusted_inputs": {
            relative: sha256(committed[relative])
            for relative in TRUSTED_INPUT_PATHS
        },
        "artifacts": {
            "kernel-metadata.json": sha256(metadata_bytes),
            "submission.ipynb": sha256(notebook_bytes),
        },
        "effect_claims": {
            "competition_ignition_authorized": False,
            "credential_used": False,
            "external_contact": False,
            "kaggle_stage_authorized": False,
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return {
        "candidate-manifest.json": manifest_bytes,
        "kernel-metadata.json": metadata_bytes,
        "submission.ipynb": notebook_bytes,
    }


def _snapshot_envelope(identity: dict[str, Any], files: dict[str, bytes], trusted: dict[str, bytes]) -> tuple[dict[str, Any], str]:
    envelope = {
        "schema": "hearthline.arc3.verified-snapshot.v1",
        "commit": identity["commit"],
        "tree": identity["tree"],
        "candidate_files": {name: sha256(files[name]) for name in sorted(files)},
        "trusted_inputs": {name: sha256(trusted[name]) for name in sorted(trusted)},
    }
    encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return envelope, sha256(encoded)


def _open_directory_at(parent_fd: int, name: str, label: str) -> int:
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    require(stat.S_ISDIR(before.st_mode), f"{label} must be a real directory")
    descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
    info = os.fstat(descriptor)
    require(
        stat.S_ISDIR(info.st_mode)
        and _directory_identity(before) == _directory_identity(info),
        f"{label} changed before it was held",
    )
    return descriptor


def _require_child_directory_binding(
    parent_fd: int,
    name: str,
    expected: tuple[int, int],
    label: str,
) -> None:
    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    require(
        stat.S_ISDIR(current.st_mode)
        and _directory_identity(current) == expected,
        f"{label} entry changed",
    )


def _validated_verified_inventory(verified_fd: int) -> set[str]:
    inventory = set(os.listdir(verified_fd))
    for name in inventory:
        require(
            re.fullmatch(r"[0-9a-f]{64}", name) is not None,
            f"unrecognized verified snapshot entry: {name}",
        )
        info = os.stat(name, dir_fd=verified_fd, follow_symlinks=False)
        require(
            stat.S_ISDIR(info.st_mode),
            f"verified snapshot entry is not a real directory: {name}",
        )
    return inventory


def _write_new_regular_at(directory_fd: int, name: str, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, 0o400, dir_fd=directory_fd)
    try:
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            require(written > 0, f"short write while materializing {name}")
            offset += written
        os.fsync(descriptor)
        written_info = os.fstat(descriptor)
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        require(
            stat.S_ISREG(entry.st_mode)
            and entry.st_nlink == 1
            and _file_identity(written_info) == _file_identity(entry),
            f"materialized snapshot path changed: {name}",
        )
    finally:
        os.close(descriptor)


def _materialize_snapshot_at(
    build_dir: Path,
    build_fd: int,
    snapshot_sha256: str,
    files: dict[str, bytes],
) -> tuple[Path, dict[str, tuple[int, int]]]:
    """Write and verify a closed snapshot entirely below a held build FD."""
    try:
        os.mkdir("verified", mode=0o700, dir_fd=build_fd)
    except FileExistsError:
        pass
    verified_fd = _open_directory_at(build_fd, "verified", "verified snapshot root")
    verified_identity = _directory_identity(os.fstat(verified_fd))
    try:
        inventory = _validated_verified_inventory(verified_fd)
        if snapshot_sha256 in inventory:
            target_fd = _open_directory_at(verified_fd, snapshot_sha256, "verified snapshot")
            target_identity = _directory_identity(os.fstat(target_fd))
            try:
                existing = _read_build_snapshot_at(target_fd, label="verified snapshot")
                _require_child_directory_binding(
                    verified_fd,
                    snapshot_sha256,
                    target_identity,
                    "verified snapshot",
                )
            finally:
                os.close(target_fd)
            require(existing == files, "existing content-addressed snapshot is corrupt")
        else:
            # Reserve the final content-addressed name atomically. A collision
            # fails instead of allowing rename-overwrite semantics. A crash may
            # leave an incomplete final directory, which the next run rejects.
            os.mkdir(snapshot_sha256, mode=0o700, dir_fd=verified_fd)
            target_fd = _open_directory_at(verified_fd, snapshot_sha256, "verified snapshot")
            target_identity = _directory_identity(os.fstat(target_fd))
            require(not os.listdir(target_fd), "new verified snapshot was not empty")
            try:
                for name in BUILD_FILES:
                    _require_child_directory_binding(
                        verified_fd,
                        snapshot_sha256,
                        target_identity,
                        "verified snapshot",
                    )
                    _write_new_regular_at(target_fd, name, files[name])
                require(
                    _read_build_snapshot_at(target_fd, label="verified snapshot") == files,
                    "materialized content-addressed snapshot mismatch",
                )
                os.fchmod(target_fd, 0o500)
                os.fsync(target_fd)
            finally:
                os.close(target_fd)

        _require_child_directory_binding(
            build_fd,
            "verified",
            verified_identity,
            "verified snapshot root",
        )
        _require_child_directory_binding(
            verified_fd,
            snapshot_sha256,
            target_identity,
            "verified snapshot",
        )
        require(
            _validated_verified_inventory(verified_fd)
            == inventory | {snapshot_sha256},
            "verified snapshot root inventory changed during materialization",
        )
        target_fd = _open_directory_at(verified_fd, snapshot_sha256, "verified snapshot")
        try:
            require(
                _directory_identity(os.fstat(target_fd)) == target_identity,
                "verified snapshot changed before final read",
            )
            require(
                _read_build_snapshot_at(target_fd, label="verified snapshot") == files,
                "verified snapshot changed before materialization completed",
            )
        finally:
            os.close(target_fd)
        os.fsync(verified_fd)
        return (
            _absolute_lexical(build_dir) / "verified" / snapshot_sha256,
            {"verified": verified_identity, "snapshot": target_identity},
        )
    finally:
        os.close(verified_fd)


def _recheck_materialized_snapshot(
    build_fd: int,
    snapshot_sha256: str,
    files: dict[str, bytes],
    binding: dict[str, tuple[int, int]],
) -> None:
    _require_child_directory_binding(
        build_fd, "verified", binding["verified"], "verified snapshot root"
    )
    verified_fd = _open_directory_at(build_fd, "verified", "verified snapshot root")
    try:
        require(
            _directory_identity(os.fstat(verified_fd)) == binding["verified"],
            "verified snapshot root changed before final verification",
        )
        _require_child_directory_binding(
            verified_fd,
            snapshot_sha256,
            binding["snapshot"],
            "verified snapshot",
        )
        target_fd = _open_directory_at(verified_fd, snapshot_sha256, "verified snapshot")
        try:
            require(
                _directory_identity(os.fstat(target_fd)) == binding["snapshot"],
                "verified snapshot changed before final verification",
            )
            require(
                _read_build_snapshot_at(target_fd, label="verified snapshot") == files,
                "verified snapshot changed after materialization",
            )
        finally:
            os.close(target_fd)
        _validated_verified_inventory(verified_fd)
    finally:
        os.close(verified_fd)


def _verification_receipt_bytes(result: dict[str, Any]) -> bytes:
    return (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_verification_receipt_at(
    build_fd: int,
    data: bytes,
) -> tuple[int, int, int, int]:
    """Create the one canonical receipt without following or replacing a path."""
    name = "verification.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, 0o400, dir_fd=build_fd)
    except FileExistsError:
        require(
            _read_file_at(build_fd, name, "build/verification.json") == data,
            "existing canonical verification receipt differs; refusing collision",
        )
        entry = os.stat(name, dir_fd=build_fd, follow_symlinks=False)
        identity = _file_identity(entry)
        require(
            _read_file_at(build_fd, name, "build/verification.json") == data
            and _file_identity(
                os.stat(name, dir_fd=build_fd, follow_symlinks=False)
            )
            == identity,
            "existing canonical verification receipt changed during validation",
        )
        return identity
    try:
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            require(written > 0, "short write while publishing verification receipt")
            offset += written
        os.fsync(descriptor)
        written_info = os.fstat(descriptor)
        entry = os.stat(name, dir_fd=build_fd, follow_symlinks=False)
        require(
            stat.S_ISREG(entry.st_mode)
            and entry.st_nlink == 1
            and _file_identity(written_info) == _file_identity(entry),
            "canonical verification receipt path changed while being written",
        )
    finally:
        os.close(descriptor)
    os.fsync(build_fd)
    require(
        _read_file_at(build_fd, name, "build/verification.json") == data,
        "canonical verification receipt changed after publication",
    )
    identity = _file_identity(written_info)
    require(
        _file_identity(os.stat(name, dir_fd=build_fd, follow_symlinks=False))
        == identity,
        "canonical verification receipt entry changed after publication",
    )
    return identity


def _require_verification_receipt_binding(
    build_fd: int,
    expected_identity: tuple[int, int, int, int],
    expected_data: bytes,
) -> None:
    info = os.stat("verification.json", dir_fd=build_fd, follow_symlinks=False)
    require(
        stat.S_ISREG(info.st_mode)
        and info.st_nlink == 1
        and _file_identity(info) == expected_identity,
        "canonical verification receipt entry changed",
    )
    require(
        _read_file_at(
            build_fd, "verification.json", "build/verification.json"
        )
        == expected_data,
        "canonical verification receipt bytes changed",
    )


def _verify_candidate_files(
    build_dir: Path,
    *,
    trusted: dict[str, Any],
    actual: dict[str, bytes],
    require_clean: bool,
    materialize: bool,
    build_fd: int | None,
    build_identity: os.stat_result | None,
    write_receipt: bool,
) -> dict[str, Any]:
    identity = trusted["identity"]
    committed = trusted["files"]
    manifest = loads_strict(actual["candidate-manifest.json"], "candidate manifest")
    metadata = loads_strict(actual["kernel-metadata.json"], "kernel metadata")
    notebook = loads_strict(actual["submission.ipynb"], "submission notebook")

    metadata_result = inspect_metadata(metadata)
    agent_source = committed["agent/my_agent.py"].decode("utf-8")
    agent_result = inspect_agent(agent_source)
    notebook_result = inspect_notebook(
        notebook,
        agent_source,
        sha256(committed["launch/source-lock.v4.json"]),
        sha256(committed["launch/runtime/kaggle-stage-v4-runtime-inventory.json"]),
    )
    require(metadata["enable_gpu"] is notebook["metadata"]["kaggle"]["isGpuEnabled"], "notebook/metadata GPU mismatch")
    require(notebook_result["accelerator"] in ACCELERATOR_BY_METADATA.values(), "accelerator not allowed")

    source_lock, starter_contract, _, runtime_state = inspect_trusted_contracts(committed)
    reviewed_starter_projection = json.loads(
        json.dumps(starter_contract["projection"])
    )
    require(
        reviewed_starter_projection["install"]["packages"]
        == ["arc-agi", "python-dotenv"],
        "pinned public starter package projection changed",
    )
    reviewed_starter_projection["install"]["packages"] = [
        "arc-agi",
        "arcengine",
        "python-dotenv",
    ]
    require(
        project_starter_surface(notebook) == reviewed_starter_projection,
        "generated notebook differs from the pinned starter plus reviewed runtime pin",
    )
    expected = render_expected_candidate(
        committed,
        identity,
        metadata_result["account_slug"],
        notebook_result["accelerator"],
    )
    for name in BUILD_FILES:
        require(actual[name] == expected[name], f"build/{name} differs from exact committed regeneration")

    require_exact_keys(manifest, {"schema", "candidate", "parameters", "trusted_inputs", "artifacts", "effect_claims"}, "candidate manifest")
    require(manifest["schema"] == "hearthline.arc3.offline-candidate-manifest.v4", "candidate manifest schema")
    require(manifest["candidate"] == {**identity, "worktree_clean": True}, "candidate manifest lineage mismatch")
    require(manifest["parameters"] == {
        "accelerator": notebook_result["accelerator"],
        "account_slug": metadata_result["account_slug"],
        "kernel_id": metadata_result["kernel_id"],
    }, "candidate manifest parameters mismatch")
    require(manifest["effect_claims"] == {
        "competition_ignition_authorized": False,
        "credential_used": False,
        "external_contact": False,
        "kaggle_stage_authorized": False,
    }, "candidate effect claims must remain false")

    envelope, snapshot_sha = _snapshot_envelope(identity, actual, committed)
    if materialize:
        require(build_fd is not None and build_identity is not None, "verified materialization requires a held build directory")
        snapshot_path, snapshot_binding = _materialize_snapshot_at(
            build_dir,
            build_fd,
            snapshot_sha,
            actual,
        )
        _require_directory_path_binding(build_dir, build_identity, "build directory")
        require(
            _read_build_snapshot_at(
                build_fd,
                label="build",
                allowed_extras=BUILD_EXTRAS,
            )
            == actual,
            "candidate changed during snapshot materialization",
        )
        _recheck_materialized_snapshot(
            build_fd, snapshot_sha, actual, snapshot_binding
        )
    else:
        snapshot_path = None
        snapshot_binding = None

    candidate_binding = {
        "commit": identity["commit"],
        "tree": identity["tree"],
        "account_slug": metadata_result["account_slug"],
        "kernel_id": metadata_result["kernel_id"],
        "accelerator": notebook_result["accelerator"],
        "agent_sha256": sha256(committed["agent/my_agent.py"]),
        "builder_sha256": sha256(committed["scripts/build_notebook.py"]),
        "notebook_sha256": sha256(actual["submission.ipynb"]),
        "kernel_metadata_sha256": sha256(actual["kernel-metadata.json"]),
        "source_lock_sha256": sha256(committed["launch/source-lock.v4.json"]),
        "candidate_manifest_sha256": sha256(actual["candidate-manifest.json"]),
        "verified_snapshot_sha256": snapshot_sha,
    }
    placeholder = metadata_result["account_slug"] == "REPLACE_WITH_YOUR_USERNAME"
    agents_row = next(
        row for row in source_lock["official_software"]
        if row["repository"] == "arcprize/ARC-AGI-3-Agents"
    )
    agents_files = {
        path: binding["sha256"]
        for path, binding in agents_row["inspected_file_bindings"].items()
    }
    toolkit_row = next(
        row for row in source_lock["official_software"]
        if row["repository"] == "arcprize/ARC-AGI"
    )
    stage_identity = runtime_state["reviewed"]["stage_identity"]
    provenance = runtime_state["provenance"]
    result = {
        "schema": "hearthline.arc3.offline-candidate-verification.v4",
        "structural_verification": "PASS",
        "python": sys.version.split()[0],
        "agent": agent_result,
        "notebook": notebook_result,
        "verified_inputs": {
            "source_lock_sha256": sha256(committed["launch/source-lock.v4.json"]),
            "runtime_inventory_sha256": sha256(
                committed["launch/runtime/kaggle-stage-v4-runtime-inventory.json"]
            ),
            "runtime_review_receipt_sha256": sha256(
                committed["launch/receipts/20260907T002817Z-stage-v4-runtime-review.json"]
            ),
            "runtime_closure_status": source_lock["dependency_resolution"][
                "runtime_closure_status"
            ],
            "public_source_arc_agi_repository": toolkit_row["repository"],
            "public_source_arc_agi_commit": toolkit_row["commit"],
            "public_source_arc_agi_version": toolkit_row["version"],
            "public_source_agents_repository": agents_row["repository"],
            "public_source_agents_commit": agents_row["commit"],
            "public_source_agents_tree": agents_row["tree"],
            "public_source_agents_files": agents_files,
            "public_source_agents_license_file": {
                "LICENSE": agents_row["license_file_binding"]["sha256"]
            },
            "kaggle_runtime_kernel_slug": stage_identity["kernel_slug"],
            "kaggle_runtime_kernel_version": stage_identity["kernel_version"],
            "kaggle_runtime_stage_status": stage_identity["status"],
            "kaggle_runtime_visibility": stage_identity["visibility"],
            "kaggle_runtime_internet_enabled": stage_identity["internet_enabled"],
            "kaggle_runtime_accelerator": stage_identity["accelerator"],
            "kaggle_runtime_candidate_snapshot_sha256": stage_identity[
                "candidate_snapshot_sha256"
            ],
            "kaggle_runtime_python_version": runtime_state["reviewed"][
                "python_version"
            ],
            "kaggle_runtime_distributions": runtime_state["distribution_rows"],
            "kaggle_runtime_files": runtime_state["runtime_files"],
            "kaggle_runtime_license_file": runtime_state["runtime_license_file"],
            "kaggle_runtime_provenance_kind": provenance["kind"],
            "kaggle_runtime_agents_repository": provenance["repository"],
            "kaggle_runtime_agents_commit": provenance["commit"],
            "kaggle_runtime_agents_tree": provenance["tree"],
            "kaggle_runtime_evidence_manifest_sha256": runtime_state["reviewed"]
            ["machine_evidence"]["evidence_manifest_sha256"],
            "kaggle_runtime_logs_sha256": runtime_state["reviewed"][
                "machine_evidence"
            ]["logs_sha256"],
        },
        "verified_snapshot": {
            "sha256": snapshot_sha,
            "path": (
                snapshot_path.relative_to(ROOT).as_posix()
                if snapshot_path is not None and snapshot_path.is_relative_to(ROOT)
                else str(snapshot_path) if snapshot_path is not None else None
            ),
            "envelope": envelope,
            "candidate_binding": candidate_binding,
        },
        "kernel_identity_placeholder": placeholder,
        "offline_package_ready": True,
        "kaggle_stage_ready": bool(require_clean and materialize and not placeholder),
        "competition_ignition_ready": False,
        "kaggle_stage_authorized": False,
        "competition_ignition_authorized": False,
        "claim_ceiling": (
            "Exact regeneration and local content-addressed snapshot only. Local files and ledger entries are procedural "
            "attestations, not signatures or proof of a Kaggle action, environment result, or competition score."
        ),
    }

    receipt_data: bytes | None = None
    receipt_binding: tuple[int, int, int, int] | None = None
    if write_receipt:
        require(
            materialize and build_fd is not None and build_identity is not None,
            "a canonical receipt requires held stage-ready materialization",
        )
        receipt_data = _verification_receipt_bytes(result)
        receipt_binding = _write_verification_receipt_at(build_fd, receipt_data)

    if materialize:
        require(
            build_fd is not None
            and build_identity is not None
            and snapshot_binding is not None,
            "final verification requires held filesystem bindings",
        )
        require(
            _read_build_snapshot_at(
                build_fd,
                label="build",
                allowed_extras=BUILD_EXTRAS,
            )
            == actual,
            "candidate changed before verification completed",
        )
        _recheck_materialized_snapshot(
            build_fd, snapshot_sha, actual, snapshot_binding
        )
        if receipt_binding is not None and receipt_data is not None:
            _require_verification_receipt_binding(
                build_fd, receipt_binding, receipt_data
            )
        _require_directory_path_binding(build_dir, build_identity, "build directory")
    else:
        require(
            read_build_snapshot(build_dir, allowed_extras=BUILD_EXTRAS) == actual,
            "candidate changed before verification completed",
        )

    # A clean measurement before reading is insufficient: recheck the exact
    # commit/tree/worktree only after every materialized byte was re-read.
    final_identity = current_git_identity()
    require(
        final_identity["commit"] == identity["commit"]
        and final_identity["tree"] == identity["tree"],
        "Git HEAD changed during candidate verification",
    )
    if require_clean:
        require(
            final_identity["worktree_clean"] is True,
            "worktree changed during candidate verification",
        )
    if materialize:
        _require_directory_path_binding(build_dir, build_identity, "build directory")
        _recheck_materialized_snapshot(
            build_fd, snapshot_sha, actual, snapshot_binding
        )
        if receipt_binding is not None and receipt_data is not None:
            _require_verification_receipt_binding(
                build_fd, receipt_binding, receipt_data
            )
    return result


def verify(
    build_dir: Path,
    require_clean: bool = False,
    materialize: bool = True,
    receipt: Path | None = None,
) -> dict[str, Any]:
    require(sys.version_info[:2] == (3, 12), f"verification requires Python 3.12, got {sys.version.split()[0]}")
    if receipt is not None:
        require(
            _absolute_lexical(receipt)
            == _absolute_lexical(build_dir) / "verification.json",
            "receipt path must be the canonical build/verification.json",
        )
        require(materialize, "receipt writing requires snapshot materialization")
    trusted = trusted_git_snapshot(require_clean)
    if not materialize:
        actual = read_build_snapshot(build_dir, allowed_extras=BUILD_EXTRAS)
        return _verify_candidate_files(
            build_dir,
            trusted=trusted,
            actual=actual,
            require_clean=require_clean,
            materialize=False,
            build_fd=None,
            build_identity=None,
            write_receipt=False,
        )

    require(
        hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.rename in os.supports_dir_fd
        and os.stat in os.supports_dir_fd,
        "stage-ready snapshot materialization requires no-follow directory-descriptor support",
    )
    build_fd, build_identity = _open_directory(build_dir, "build path")
    try:
        actual = _read_build_snapshot_at(
            build_fd,
            label="build",
            allowed_extras=BUILD_EXTRAS,
        )
        return _verify_candidate_files(
            build_dir,
            trusted=trusted,
            actual=actual,
            require_clean=require_clean,
            materialize=True,
            build_fd=build_fd,
            build_identity=build_identity,
            write_receipt=receipt is not None,
        )
    finally:
        os.close(build_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    try:
        result = verify(
            args.build_dir,
            require_clean=args.require_clean,
            receipt=args.receipt,
        )
    except (OSError, UnicodeDecodeError, SyntaxError, subprocess.CalledProcessError, CandidateError) as exc:
        raise SystemExit(f"verify_candidate: {exc}") from exc
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
