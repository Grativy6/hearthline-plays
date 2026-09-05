#!/usr/bin/env python3
"""Offline guard for forced-tracked outputs, secrets, and effect adapters.

Every tracked Python process launch must match a file-, function-, and
call-specific allowlist entry. The only repository-side launches admitted are
fixed Git reads. The generated Kaggle notebook has a separately checked
runtime surface: one offline wheel install, one gateway readiness read, and one
fixed framework invocation.

Ceiling: this is a regression/integrity lint for a human-reviewed tree, not a
self-authenticating security root. A malicious author who can change this guard
can also change its in-repository seals; adversarial trust requires protected
CI or another trust anchor outside this repository.
Locally, PASS covers two matching index snapshots during this process; the
caller must commit that same index without a later mutation.
"""

from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_EXACT = {
    ".github/copilot-instructions.md",
    ".kaggle/access_token",
    "notebooks/kernel-metadata.json",
    "notebooks/submission.ipynb",
    "tools/arc3_replay_probe.py",
}
FORBIDDEN_PREFIXES = (
    ".claude/",
    ".cursor/",
    ".gemini/",
    ".github/instructions/",
    ".kaggle/",
    ".devcontainer/",
    ".hearthline/grants/",
    ".hearthline/receipts/",
    ".github/actions/",
    ".vscode/",
    "build/",
    "environment_files/",
    "launch/.runtime/",
    "launch/runs/",
    "practice/tmp/",
    "recordings/",
    "reference/",
    "results/",
    "run-artifact/",
    "vendor/",
)
FORBIDDEN_DIRECTORY_SEQUENCES = (
    (".claude",),
    (".cursor",),
    (".gemini",),
    (".github", "instructions"),
    (".kaggle",),
    (".hearthline", "grants"),
    (".hearthline", "receipts"),
    ("build",),
    ("environment_files",),
    ("launch", ".runtime"),
    ("launch", "runs"),
    ("practice", "tmp"),
    ("recordings",),
    ("reference",),
    ("results",),
    ("run-artifact",),
    ("vendor",),
)
FORBIDDEN_CONTROL_NAMES = {
    ".devcontainer.json", ".mcp.json", "agents.md", "claude.md", "gemini.md",
    "composer.json", "deno.json", "package.json", "renovate.json",
    "taskfile.yaml", "taskfile.yml",
}
SECRET_PATTERNS = {
    "Kaggle access token": re.compile(rb"KGAT_[A-Za-z0-9]{20,}"),
    "OpenAI secret key": re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "private key block": re.compile(
        rb"-----BEGIN (?:(?:RSA|EC|OPENSSH|DSA|ENCRYPTED) PRIVATE KEY|"
        rb"PGP PRIVATE KEY BLOCK|PRIVATE KEY)-----"
    ),
}
DECODED_SECRET_PATTERNS = {
    "Kaggle access token": re.compile(r"KGAT_[A-Za-z0-9]{20,}"),
    "OpenAI secret key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "private key block": re.compile(
        r"-----BEGIN (?:(?:RSA|EC|OPENSSH|DSA|ENCRYPTED) PRIVATE KEY|"
        r"PGP PRIVATE KEY BLOCK|PRIVATE KEY)-----"
    ),
}
LEGACY_KAGGLE_KEY = re.compile(r"^[A-Za-z0-9_-]{32,}$")
FORBIDDEN_EFFECT_IMPORTS = {
    "aiohttp", "arc_agi", "boto3", "ctypes", "ftplib", "http", "httpx",
    "kaggle", "multiprocessing", "openai", "operator", "paramiko", "pickle",
    "pty", "requests", "runpy", "smtplib", "socket", "urllib3", "webbrowser",
    "xmlrpc",
}
FORBIDDEN_LOCAL_IMPORT_ROOTS = {"scripts", "tests", "tools"}
SHELL_SUFFIXES = {".bat", ".bash", ".cmd", ".fish", ".ksh", ".ps1", ".sh", ".zsh"}
ALLOWED_EXTENSIONLESS_PATHS = {
    ".gitignore", "LICENSE", "Makefile", "launch/receipts/.gitkeep",
    "practice/receipts/.gitkeep", "practice/requests/.gitkeep",
}
ALLOWED_AUXILIARY_SHA256 = {
    ".gitignore": "2529f03b84a9bba177bd89550bcc07d33a53a317a9dbc220cd8df84ab239a615",
    ".gitattributes": "4f2272aad1f4374099b84639375d72c5bed891f59994d627759cd7fe61a2d81c",
    "docs/honesty/HONESTY_PCP_v1.0_PROMPT.txt": "e54ccd89828d8736ce2f025589d419b7c3ab2db8966c175b8d9bba85f3906e83",
    "tests/fixtures/ARC-AGI-3-Agents-LICENSE.txt": "cd95f6fb04cbe8f172890cf3746bb57295d131eb110bb78c1a0a528ea8acf87d",
    "tests/fixtures/agents-main-4743e7d0.blob": "864254c750bbbd12a211f2d8aa1b1025d0609283f07dea4ede83722f2435301b",
}
MAKEFILE_SHA256 = "603086f27df7605cf059a9c65c4e5c0d4c61dbc8ef07ab9ff7a3baaa87e1d368"
SUBPROCESS_METHODS = {
    "Popen", "call", "check_call", "check_output", "check_returncode",
    "getoutput", "getstatusoutput", "run",
}
OS_PROCESS_METHODS = {
    "fork", "forkpty", "popen", "posix_spawn", "posix_spawnp", "startfile", "system",
}
NOTEBOOK_BUILDER = "scripts/build_notebook.py"
NOTEBOOK_RUNTIME_CONTEXT = NOTEBOOK_BUILDER + "::<run_framework>"
NOTEBOOK_DUMMY_CONTEXT = NOTEBOOK_BUILDER + "::<dummy>"
NOTEBOOK_INSTALL_CELL = (
    "!python -m pip install --no-index --find-links "
    "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels "
    "arc-agi python-dotenv"
)
ALLOWED_WORKFLOW_NORMALIZED_SHA256 = {
    ".github/workflows/arc3-orientation-probe.yml": "2f766102a704b7d99a16ff3889b5c61652c0aaa4a21fd0d8c713d8d23f238158",
    ".github/workflows/launch-verify.yml": "f674e4c8a61c2c6203bd790483472464068e6df419aa397f895a7f76c7b1c50b",
    ".github/workflows/verify-launchpad.yml": "9b6676e17ed1923860329cba334b0738a0eb59cafbffddd9cf4722bcadd1df64",
    ".github/workflows/verify.yml": "35d5207a0f60ce34088802b8ea5a2ccf0906df5fe48bd4fcb17d23077637ffb1",
}
WORKFLOW_GUARD_PIN = re.compile(
    rb'(?m)^(?P<prefix>[ ]+expected_guard_sha256 = ")'
    rb'(?P<digest>[0-9a-f]{64})(?P<suffix>")$'
)
PYTHON_CODING_COOKIE = re.compile(
    rb"^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)"
)
ALLOWED_CONTROL_JSON_SHA256 = {
    "launch/contracts/official-starter-eeb153.contract.json": "dd332a2d60997b60b6c1b55e2fbff804c0905637ad2f3b169f1a7572204d3e99",
    "launch/source-lock.v3.json": "9f551d9ba7829a4b6a324d53f53dafaa2fa661fca14762bbb937fa192ccd13d7",
    "notebooks/kernel-metadata.template.json": "cce20860106970d0daf1317ce9a74b88fe2febcb6f035913b57ebfae5e964937",
}
ALLOWED_SENSITIVE_PATH_REFERENCES = {
    "launch/source-lock.v3.json": {".kaggle/access_token"},
}

# Every tracked Python file has a closed import inventory. This is the
# conservative backstop against introducing a new process, network, dynamic
# loader, deserializer, or local capability re-export that a call-name scanner
# does not yet know. A new Python surface requires a deliberate guard update.
ALLOWED_IMPORT_SHA256 = {
    "agent/my_agent.py": "e065bfc39731aeb7f7bec5b9576122130439752fb59ac183f1609939ef4f6a79",
    "launch/tests/test_launch_tools.py": "92f304b47e642efc5f73467b196517570318ab8fae6065ed37769a393a7d33e9",
    "launch/tools/frame_probe.py": "8e39aeb34e131ea727631740fef3b5c282595e41cc441fcd87de4b06afca9ee8",
    "launch/tools/migrate_static_v1.py": "98c98617eb2335f51e11400a6d69a2b0a53d3c04ad7460c8ce3cad4802184686",
    "launch/tools/orientation_console.py": "96925079691a4ef4a8f207aae37f3ac3655aa342ed3c91bac4a712ae358ba6ad",
    "launch/tools/static_pair.py": "ba0fe87cf91836ff182ddb6d7967f57687e6c04f30bb188691caf81e3cd6b466",
    "launch/tools/static_pair_v2.py": "ca63c23f27eb20c14a5558abc78728d29f09c2d681f8c4d9e1d2dae8c528e4f1",
    "scripts/build_notebook.py": "3daf648749f98aed41333315d324a7eaeb718dac12d0abc55102f3069e760063",
    "scripts/verify_candidate.py": "cf9def163bd0a257e6e2ea44fbe2ed085a3765941cd910b28dfeafbeeefffe3a",
    "scripts/verify_human_gate.py": "c27d125c1e5f323a9c2403244fe8ef6168a3d36a440c4401c411f78b5413b937",
    "tests/test_candidate.py": "bb23848639bacc0c3417db12868a2ad4b943ebf0b286abf28c7480590c78186f",
    "tests/test_human_gates.py": "8b27e1e0d584b91a09b33f24c217e2bb78cac5e84e67397f6a6d78baec68f7a4",
    "tests/test_launchpad.py": "4c853dae076fafc796716f7596a5432c1eded75ebf3ba33e480411827e2f5304",
    "tests/test_reconciliation.py": "762a61a15e782e7504cfeccc5b3834113d6d4d7b098c401bcfcbb5be08547c77",
    "tests/test_repository_guard.py": "ed9adf4d73be876677babb5b9712828c1c446bb1d5a57972e033b78b1e754924",
    "tests/test_source_context.py": "762a61a15e782e7504cfeccc5b3834113d6d4d7b098c401bcfcbb5be08547c77",
    "tests/test_verify_station.py": "149b75541ba1f4e1778e3be30c2eefe6d09a269040aea11cfcf6bab558c50b1b",
    "tools/orientation_archive_guard.py": "7c29818ccf04447c42e303255b6714f3e2dec8c42a2475f8ad982dcdb4de2587",
    "tools/pair_static.py": "d71ac7c99e18ad72814e2cc06100e6be1eb54c11a2cd6528e5e404e31b3acb55",
    "tools/repository_guard.py": "4e65ac4cd3b11eb7e25989c0774fa9111d759dd7b7b1345cc74b92d37ef49bfa",
    "tools/validate_launchpad.py": "40a9161ed96e583476421fbd32dd6c85baff0da73eecbfe829e201eac4c40923",
    "tools/verify_station.py": "4a958c8a339ddb3fc47c32829cdceacd41e74228ea6f3e65865ab7dc620ef3a1",
}

# Full staged-blob commitments close the executable surface rather than trying
# to enumerate every way safe-looking Python modules can reach an effect. The
# guard itself is the sole unavoidable self-reference and is checked by its
# closed import inventory plus exact process/URL/wrapper AST signatures.
ALLOWED_PYTHON_SHA256 = {
    "agent/my_agent.py": "1823835290a9e5cbddba96d577500a7cc5f1e6ef08d99e63aad37378f56b5dbd",
    "launch/tests/test_launch_tools.py": "889f957b8f5cecb4a3f84c63f6f375874d6737b35cb9be0b8f4d8b6c3238a09d",
    "launch/tools/frame_probe.py": "fb447707cc2b6ff1a41ccaac047d8fac04be9d6f6b64eedd6ebc12677176f787",
    "launch/tools/migrate_static_v1.py": "f9ce58784ee9e92ace761012c6d6c56e8275d11fd9bd9ec6c0cc189bb56bbe58",
    "launch/tools/orientation_console.py": "09aa09b4b69f9a0c4c663ff17c1c105edf35049c8ff6b1fe06044ac661a06fb6",
    "launch/tools/static_pair.py": "e113fd9d4fe9de21f755c11cb1dd7f6a50ae50938249d04333ba476b66f0a926",
    "launch/tools/static_pair_v2.py": "92e3048bf73fc65f421fec208dbc22626082ac91392c222a1b246da0218e0792",
    "scripts/build_notebook.py": "3027a9668af7366c41a85ca48bd20c3426730f98b5dad065557005dfb1eaa9b9",
    "scripts/verify_candidate.py": "e366926f4ed4a030c86ac2f60a64bc19c7cda65f8114954f9e2eefb660f520d5",
    "scripts/verify_human_gate.py": "59a253514bd0f143461b6f1cd8d0486b63a7b111548659845e3ef3c4916448e0",
    "tests/test_candidate.py": "91be63b48bc169e9e7d5ded6c0e77fef319e772ef261316a25d1bc57eaddd4f2",
    "tests/test_human_gates.py": "3053ffc520816044c5175063434e03a3647650c8e41b8801cc640fe6247b4073",
    "tests/test_launchpad.py": "f9770e45de26eadf07a0b099d191f52514289afbad4a04f2a22c17b5b3ae2cfa",
    "tests/test_reconciliation.py": "5e9cdea14b1875e22ba725b1f4691bd23b2f26c9845b355a569163f9390469fa",
    "tests/test_repository_guard.py": "ec5863b87026819c10e45588253854f2838f212cfbc00e0861b32e43e5ff8bca",
    "tests/test_source_context.py": "35602b972270ed2029011a11fe5f92904e0fccdd18ced1d8be2453e17d6a01f9",
    "tests/test_verify_station.py": "5cadfab6f70d28839a4042c1efd098e265aca1d0016efd934d78188e9bb22d89",
    "tools/orientation_archive_guard.py": "744b2bec891cf9e4369c1a2a2fe43dc6bf38b6f22302ad3065ad888e184a33d2",
    "tools/pair_static.py": "aa231b448d059fea8b0990f4c21a134cd63bc759ad9170c3e9b49cf2b1f467ac",
    "tools/validate_launchpad.py": "ae7a1e30b27fa98ef32e209b75a98a69372bed73d4c59d67452504f85fa916dc",
    "tools/verify_station.py": "5cb72ad8973de27d6fc8810f3cf5e03ff1b61e170e36766301bffd73a0493908",
}
SELF_AST_SHA256 = "1de8f9a6f188f39c4a406718871b0684cc48b9792a7425de02973ac06ac28853"


class GuardError(RuntimeError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GuardError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise GuardError(f"non-finite JSON number is forbidden: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if parsed == float("inf") or parsed == float("-inf"):
        _reject_nonfinite(value)
    return parsed


def _contains_legacy_kaggle_credential(value: Any) -> bool:
    if isinstance(value, dict):
        if (
            isinstance(value.get("username"), str)
            and isinstance(value.get("key"), str)
            and LEGACY_KAGGLE_KEY.fullmatch(value["key"])
        ):
            return True
        return any(_contains_legacy_kaggle_credential(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_legacy_kaggle_credential(item) for item in value)
    return False


def _json_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for key, item in value.items():
            strings.extend(_json_strings(key))
            strings.extend(_json_strings(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_json_strings(item))
        return strings
    return []


def _looks_like_sensitive_path(value: str) -> bool:
    normalized = value.replace("\\", "/").casefold()
    name = normalized.rsplit("/", 1)[-1]
    return (
        "/.kaggle/" in f"/{normalized}"
        or name.startswith(".env")
        or Path(name).suffix in {".pem", ".key", ".p12", ".pfx"}
    )


def _contains_forbidden_directory(path: str) -> bool:
    parts = tuple(part for part in path.replace("\\", "/").casefold().split("/") if part)
    return any(
        parts[offset:offset + len(sequence)] == sequence
        for sequence in FORBIDDEN_DIRECTORY_SEQUENCES
        for offset in range(len(parts) - len(sequence) + 1)
    )


def _git_environment() -> dict[str, str]:
    """Return an environment unable to inherit Git effect configuration."""
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


def _git_read_command(*arguments: str) -> list[str]:
    return [
        "git",
        "-c", "core.fsmonitor=false",
        "-c", f"core.hooksPath={os.devnull}",
        *arguments,
    ]


def tracked_entries() -> dict[str, tuple[str, str]]:
    raw = subprocess.check_output(
        _git_read_command("ls-files", "--stage", "-z"),
        cwd=ROOT,
        env=_git_environment(),
    )
    entries: dict[str, str] = {}
    for encoded in raw.split(b"\0"):
        if not encoded:
            continue
        try:
            header, name = encoded.split(b"\t", 1)
            mode_raw, object_raw, stage = header.split(b" ")
            mode = mode_raw.decode("ascii")
            object_id = object_raw.decode("ascii")
            path = name.decode("utf-8", "surrogateescape")
        except (UnicodeDecodeError, ValueError) as exc:
            raise GuardError("malformed git ls-files --stage output") from exc
        if stage != b"0" or re.fullmatch(r"[0-9a-f]{40,64}", object_id) is None:
            raise GuardError(f"unmerged or malformed tracked index entry: {path}")
        if path in entries:
            raise GuardError(f"duplicate tracked path or unresolved index stages: {path}")
        entries[path] = (mode, object_id)
    return entries


def read_index_blob(object_id: str) -> bytes:
    if re.fullmatch(r"[0-9a-f]{40,64}", object_id) is None:
        raise GuardError("refusing malformed Git object id")
    try:
        data = subprocess.check_output(
            _git_read_command("cat-file", "blob", object_id),
            cwd=ROOT,
            env=_git_environment(),
        )
    except subprocess.CalledProcessError as exc:
        raise GuardError(f"cannot read exact staged blob: {object_id}") from exc
    object_hasher = hashlib.sha1 if len(object_id) == 40 else hashlib.sha256
    framed = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    actual_object_id = object_hasher(framed).hexdigest()
    if actual_object_id != object_id:
        raise GuardError(
            f"Git returned bytes that do not match the exact staged blob: {object_id}"
        )
    return data


def _parse_call(source: str) -> str:
    expression = ast.parse(source, mode="eval").body
    if not isinstance(expression, ast.Call):  # pragma: no cover - constant construction
        raise AssertionError(source)
    return ast.dump(expression, include_attributes=False)


# Exact AST signatures make aliases, shell=True, extra arguments, and command
# substitutions fail closed. Counts are checked too, so duplicating an approved
# call does not create another launch opportunity.
_ALLOWED_PROCESS_CALLS: dict[tuple[str, str], Counter[str]] = {
    ("tools/repository_guard.py", "tracked_entries"): Counter({
        _parse_call(
            'subprocess.check_output(_git_read_command("ls-files", "--stage", "-z"), '
            'cwd=ROOT, env=_git_environment())'
        ): 1,
    }),
    ("tools/repository_guard.py", "read_index_blob"): Counter({
        _parse_call(
            'subprocess.check_output(_git_read_command("cat-file", "blob", object_id), '
            'cwd=ROOT, env=_git_environment())'
        ): 1,
    }),
    ("scripts/build_notebook.py", "git_identity"): Counter({
        _parse_call(
            'subprocess.check_output(_git_command("rev-parse", "HEAD"), '
            'cwd=ROOT, text=True, env=_git_environment())'
        ): 1,
        _parse_call(
            'subprocess.check_output(_git_command("rev-parse", "HEAD^{tree}"), '
            'cwd=ROOT, text=True, env=_git_environment())'
        ): 1,
        _parse_call(
            'subprocess.check_output(_git_command("status", "--porcelain", '
            '"--untracked-files=normal"), cwd=ROOT, text=True, env=_git_environment())'
        ): 1,
    }),
    ("scripts/build_notebook.py", "_git_blob"): Counter({
        _parse_call(
            'subprocess.check_output(_git_command("show", f"{commit}:{relative}"), '
            'cwd=ROOT, env=_git_environment())'
        ): 1,
    }),
    ("scripts/verify_candidate.py", "current_git_identity"): Counter({
        _parse_call(
            'subprocess.check_output(_git_command("rev-parse", "HEAD"), '
            'cwd=ROOT, text=True, env=_git_environment())'
        ): 1,
        _parse_call(
            'subprocess.check_output(_git_command("rev-parse", f"{commit}^{{tree}}"), '
            'cwd=ROOT, text=True, env=_git_environment())'
        ): 1,
        _parse_call(
            'subprocess.check_output(_git_command("status", "--porcelain", '
            '"--untracked-files=normal"), cwd=ROOT, text=True, env=_git_environment())'
        ): 1,
    }),
    ("scripts/verify_candidate.py", "_git_blob"): Counter({
        _parse_call(
            'subprocess.check_output(_git_command("show", f"{commit}:{relative}"), '
            'cwd=ROOT, env=_git_environment())'
        ): 1,
    }),
    ("scripts/verify_human_gate.py", "_git_identity"): Counter({
        _parse_call(
            'subprocess.check_output(_git_command("rev-parse", "HEAD"), '
            'cwd=ROOT, text=True, env=_git_environment())'
        ): 1,
        _parse_call(
            'subprocess.check_output(_git_command("rev-parse", "HEAD^{tree}"), '
            'cwd=ROOT, text=True, env=_git_environment())'
        ): 1,
        _parse_call(
            'subprocess.check_output(_git_command("status", "--porcelain", '
            '"--untracked-files=normal"), cwd=ROOT, text=True, env=_git_environment())'
        ): 1,
    }),
    ("scripts/verify_human_gate.py", "_git_blob"): Counter({
        _parse_call(
            'subprocess.check_output(_git_command("show", f"{commit}:{relative}"), '
            'cwd=ROOT, env=_git_environment())'
        ): 1,
    }),
    ("tools/verify_station.py", "_git"): Counter({
        _parse_call(
            'subprocess.run(command, capture_output=True, text=True, encoding="utf-8", '
            'check=False, env=environment)'
        ): 1,
    }),
    (NOTEBOOK_RUNTIME_CONTEXT, "<module>"): Counter({
        _parse_call(
            'subprocess.run([str(bound_interpreter_path), "-E", "-s", "-B", "main.py", '
            '"--agent", "myagent"], cwd=target, env=framework_environment, check=True)'
        ): 1,
    }),
}

_ALLOWED_GIT_WRAPPER_CALLS: dict[tuple[str, str], Counter[str]] = {
    ("tools/verify_station.py", "validate_git_anchor"): Counter({
        _parse_call('_git(root, "show", "-s", "--format=%T", ANCHOR_COMMIT)'): 1,
        _parse_call('_git(root, "merge-base", "--is-ancestor", ANCHOR_COMMIT, "HEAD")'): 1,
    }),
}

_ALLOWED_URL_CALLS: dict[tuple[str, str], Counter[str]] = {
    (NOTEBOOK_RUNTIME_CONTEXT, "<module>"): Counter({
        _parse_call("urllib.request.ProxyHandler({})"): 1,
        _parse_call("_NoGatewayRedirect()"): 1,
        _parse_call(
            "urllib.request.build_opener("
            "urllib.request.ProxyHandler({}), _NoGatewayRedirect())"
        ): 1,
        _parse_call("gateway_opener.open(gateway, timeout=5)"): 1,
    }),
}

_RUNTIME_EXEC_TESTS = (
    "test_unfrozen_runtime_closure_blocks_competition_rerun_before_effects",
    "test_non_200_gateway_response_honors_deadline_without_proxy",
    "test_interpreter_rebind_is_detected_before_subprocess",
    "test_competition_rerun_python_minor_drift_fails_before_any_framework_effect",
    "test_competition_rerun_runtime_drift_fails_before_any_framework_effect",
    "test_competition_rerun_source_drift_fails_before_copy_or_framework_import",
    "test_competition_rerun_tracing_drift_fails_before_copy_or_subprocess",
    "test_competition_subprocess_receives_no_ambient_provider_or_tracing_keys",
)
_RUNTIME_EXEC_TEST_AST_SHA256 = {
    "test_unfrozen_runtime_closure_blocks_competition_rerun_before_effects": "2a8bfd2c151d1f276b58aa7f2a8834214deb0bea4135f0048a43b3bf80a4ab1f",
    "test_non_200_gateway_response_honors_deadline_without_proxy": "64229cc86cfde1ec246c10d3a3948b74b82435894c5f458352df161b2e5473de",
    "test_interpreter_rebind_is_detected_before_subprocess": "2f065534504a3aa31ba6774bbc158610c7e9ea6dfbb25499e260c9d553d63947",
    "test_competition_rerun_python_minor_drift_fails_before_any_framework_effect": "3181788009ed055c9b0662f89125b68f561dfb6a144b16e8f8dc72991a50b754",
    "test_competition_rerun_runtime_drift_fails_before_any_framework_effect": "3fed0ce6caf7d472ad26592c317a6ee7afaddddc6104e6df45bea5a3a34e668d",
    "test_competition_rerun_source_drift_fails_before_copy_or_framework_import": "2c1c7c2b92f7a001b17b53f712356865a5acf9c562db680cef7054495f86478a",
    "test_competition_rerun_tracing_drift_fails_before_copy_or_subprocess": "5a256623e1ae0585a8adb9a9bb2399be4833cf653130c7d71b2be5226e547da2",
    "test_competition_subprocess_receives_no_ambient_provider_or_tracing_keys": "4fae3a108f3ae68304426664437dca623247b2ada0fe67d45c7f6696901bcdf7",
}
_ALLOWED_DYNAMIC_EXEC_CALLS: dict[tuple[str, str], Counter[str]] = {
    ("tests/test_candidate.py", function_name): Counter({
        _parse_call(
            'exec(compile(run_source, "competition-rerun", "exec"), {})'
        ): 1,
    })
    for function_name in _RUNTIME_EXEC_TESTS
}
_ALLOWED_DYNAMIC_EXEC_CALLS.update({
    ("scripts/verify_human_gate.py", "verify_current_candidate"): Counter({
        _parse_call(
            'exec(compile(verifier_bytes, str(path), "exec"), module.__dict__)'
        ): 1,
    }),
})


def _attribute_path(node: ast.AST, aliases: dict[str, str]) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    base = aliases.get(current.id, current.id)
    return ".".join([base, *reversed(parts)])


def _is_effect_import(module: str, imported_names: set[str]) -> bool:
    root = module.split(".")[0]
    if root in FORBIDDEN_EFFECT_IMPORTS or root in FORBIDDEN_LOCAL_IMPORT_ROOTS:
        return True
    if module == "urllib.request" or (module == "urllib" and "request" in imported_names):
        return True
    return module == "urllib"


class _PythonEffectGuard(ast.NodeVisitor):
    """Reject executable effects and consume exact approved call signatures."""

    def __init__(self, path_text: str, tree: ast.AST, *, notebook_runtime: bool = False) -> None:
        self.path_text = path_text
        self.notebook_runtime = notebook_runtime
        self.aliases: dict[str, str] = {}
        self.members: dict[str, tuple[str, str]] = {}
        self.function_stack: list[str] = []
        self.parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        self.allowed_process = {
            key: Counter(value) for key, value in _ALLOWED_PROCESS_CALLS.items()
            if key[0] == path_text
        }
        self.allowed_url = {
            key: Counter(value) for key, value in _ALLOWED_URL_CALLS.items()
            if key[0] == path_text
        }
        self.allowed_git_wrapper = {
            key: Counter(value) for key, value in _ALLOWED_GIT_WRAPPER_CALLS.items()
            if key[0] == path_text
        }
        self.allowed_dynamic_exec = {
            key: Counter(value) for key, value in _ALLOWED_DYNAMIC_EXEC_CALLS.items()
            if key[0] == path_text
        }

    @property
    def function_name(self) -> str:
        return self.function_stack[-1] if self.function_stack else "<module>"

    def _fail(self, detail: str, node: ast.AST) -> None:
        line = getattr(node, "lineno", "?")
        raise GuardError(f"effect surface in {self.path_text}:{line}: {detail}")

    def _consume(self, allowed: dict[tuple[str, str], Counter[str]], call: ast.Call, label: str) -> None:
        key = (self.path_text, self.function_name)
        signature = ast.dump(call, include_attributes=False)
        counter = allowed.get(key)
        if counter is None or counter[signature] <= 0:
            self._fail(f"unapproved {label} call", call)
        counter[signature] -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            # ``import urllib.request`` binds ``urllib`` unless aliased.
            bound = alias.name if alias.asname else alias.name.split(".")[0]
            self.aliases[local] = bound
            if alias.name == "subprocess":
                if not any(key[0] == self.path_text for key in _ALLOWED_PROCESS_CALLS):
                    self._fail("subprocess import outside its exact file allowlist", node)
            elif _is_effect_import(alias.name, set()):
                if not (self.notebook_runtime and alias.name == "urllib.request"):
                    self._fail(f"effect-capable import {alias.name}", node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        imported = {alias.name for alias in node.names}
        for alias in node.names:
            self.members[alias.asname or alias.name] = (module, alias.name)
        if module == "subprocess":
            self._fail("from-subprocess import cannot match the exact call allowlist", node)
        if _is_effect_import(module, imported):
            self._fail(f"effect-capable import from {module}", node)
        self.generic_visit(node)

    def _call_path(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name) and node.id in self.members:
            module, name = self.members[node.id]
            return f"{module}.{name}" if module else name
        if isinstance(node, ast.Call):
            getter = self._call_path(node.func)
            if getter in {"getattr", "builtins.getattr"} and len(node.args) >= 2:
                base = _attribute_path(node.args[0], self.aliases)
                attribute = node.args[1]
                if base and isinstance(attribute, ast.Constant) and isinstance(attribute.value, str):
                    return f"{base}.{attribute.value}"
                if base and base.split(".")[0] in {"importlib", "os", "subprocess", "urllib"}:
                    return f"{base}.<dynamic>"
        return _attribute_path(node, self.aliases)

    def _inside_competition_guard(self, node: ast.AST) -> bool:
        current: ast.AST | None = node
        expected = ast.dump(
            ast.parse('os.getenv("KAGGLE_IS_COMPETITION_RERUN")', mode="eval").body,
            include_attributes=False,
        )
        while current is not None:
            if isinstance(current, ast.If) and ast.dump(current.test, include_attributes=False) == expected:
                return True
            current = self.parents.get(current)
        return False

    def visit_Call(self, node: ast.Call) -> None:
        path = self._call_path(node.func)
        if path:
            module, _, method = path.rpartition(".")
            module_parts = module.split(".")
            if "subprocess" in module_parts and method in SUBPROCESS_METHODS:
                self._consume(self.allowed_process, node, "subprocess")
                if self.notebook_runtime and not self._inside_competition_guard(node):
                    self._fail("notebook process call escapes the competition-rerun guard", node)
            elif ("os" in module_parts) and (
                method in OS_PROCESS_METHODS or method.startswith(("spawn", "exec"))
            ):
                self._fail(f"OS process launcher {method}", node)
            elif path in {"asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell"}:
                self._fail(f"async process launcher {path}", node)
            elif path in {
                "__import__", "builtins.__import__", "importlib.__import__",
                "importlib.import_module",
            }:
                self._fail(f"dynamic import {path}", node)
            elif path in {"exec", "builtins.exec"}:
                self._consume(self.allowed_dynamic_exec, node, "dynamic exec")
            elif path in {"eval", "builtins.eval"}:
                self._fail(f"dynamic execution {path}", node)
            elif path in {"globals", "locals", "vars", "builtins.globals", "builtins.locals", "builtins.vars"}:
                self._fail(f"dynamic namespace access {path}", node)
            elif method == "<dynamic>" and module.split(".")[0] in {
                "importlib", "os", "subprocess", "urllib",
            }:
                self._fail(f"dynamic effect attribute on {module}", node)
            elif method in {"__getattr__", "__getattribute__"}:
                self._fail(f"dunder attribute lookup {path}", node)
            elif self.notebook_runtime and path in {
                "_NoGatewayRedirect",
                "urllib.request.ProxyHandler",
                "urllib.request.build_opener",
                "gateway_opener.open",
            }:
                self._consume(self.allowed_url, node, "URL")
                if (
                    path == "gateway_opener.open"
                    and not self._inside_competition_guard(node)
                ):
                    self._fail("URL call outside the guarded notebook runtime", node)
            elif path.startswith("urllib.request."):
                self._fail(f"unapproved URL call {path}", node)
            elif path == "_git":
                self._consume(self.allowed_git_wrapper, node, "Git wrapper")
            elif path.endswith("._git"):
                self._fail(f"imported private Git wrapper {path}", node)
        elif isinstance(node.func, ast.Name):
            if node.func.id == "__import__":
                self._fail("dynamic import __import__", node)
            if node.func.id == "exec":
                self._consume(self.allowed_dynamic_exec, node, "dynamic exec")
            if node.func.id == "eval":
                self._fail(f"dynamic execution {node.func.id}", node)
            if node.func.id in {"globals", "locals", "vars"}:
                self._fail(f"dynamic namespace access {node.func.id}", node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        path = _attribute_path(node, self.aliases)
        if path:
            module, _, method = path.rpartition(".")
            dangerous = (
                ("subprocess" in module.split(".") and method in SUBPROCESS_METHODS)
                or ("os" in module.split(".") and (
                    method in OS_PROCESS_METHODS or method.startswith(("spawn", "exec"))
                ))
                or path in {
                    "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell",
                    "builtins.__import__", "importlib.__import__", "importlib.import_module",
                    "urllib.request.ProxyHandler", "urllib.request.build_opener",
                    "urllib.request.urlopen",
                }
                or (self.notebook_runtime and path == "gateway_opener.open")
                or method in {"__getattr__", "__getattribute__", "__dict__"}
                or path.endswith("._git")
            )
            parent = self.parents.get(node)
            exact_dynamic_namespace = False
            if (
                path == "module.__dict__"
                and isinstance(parent, ast.Call)
                and len(parent.args) == 2
                and parent.args[1] is node
            ):
                key = (self.path_text, self.function_name)
                signature = ast.dump(parent, include_attributes=False)
                exact_dynamic_namespace = (
                    _ALLOWED_DYNAMIC_EXEC_CALLS.get(key, Counter())[signature] == 1
                )
            if (
                dangerous
                and not exact_dynamic_namespace
                and not (isinstance(parent, ast.Call) and parent.func is node)
            ):
                self._fail(f"detached effect callable {path}", node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        source = _attribute_path(node.value, self.aliases)
        if source and (
            source in {"importlib", "os", "subprocess", "urllib"}
            or source.split(".")[0] in {"importlib", "subprocess", "urllib"}
        ):
            self._fail(f"effect module alias {source}", node)
        if source == "_git" or (source and source.endswith("._git")):
            self._fail(f"private Git wrapper alias {source}", node)
        for target in node.targets:
            target_path = _attribute_path(target, self.aliases)
            if target_path and (
                target_path.startswith(("subprocess.", "urllib.request."))
                or target_path in {"importlib.import_module", "os.system", "os.popen"}
            ):
                self._fail(f"effect callable reassignment {target_path}", node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        target_path = _attribute_path(node.target, self.aliases)
        if target_path and target_path.startswith(("subprocess.", "urllib.request.")):
            self._fail(f"effect callable mutation {target_path}", node)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        source = _attribute_path(node.value, self.aliases)
        if source in {"__builtins__", "builtins.__dict__"}:
            self._fail(f"dynamic builtins lookup on {source}", node)
        if source and source.split(".")[0] in {"importlib", "os", "subprocess", "urllib"}:
            lookup_surface = source in {"importlib", "os", "subprocess", "urllib"} or source.endswith(".__dict__")
            if not lookup_surface:
                self.generic_visit(node)
                return
            key = node.slice.value if isinstance(node.slice, ast.Constant) else None
            root = source.split(".")[0]
            dangerous_key = (
                (root == "subprocess" and key in SUBPROCESS_METHODS)
                or (root == "os" and isinstance(key, str) and (
                    key in OS_PROCESS_METHODS or key.startswith(("spawn", "exec"))
                ))
                or (root == "importlib" and key == "import_module")
                or (root == "urllib" and key in {"request", "urlopen"})
            )
            if dangerous_key or key is None:
                self._fail(f"dynamic effect lookup on {source}", node)
        self.generic_visit(node)

    def finish(self) -> None:
        for key, counter in (
            *self.allowed_process.items(), *self.allowed_url.items(),
            *self.allowed_git_wrapper.items(), *self.allowed_dynamic_exec.items(),
        ):
            missing = sum(counter.values())
            if missing:
                raise GuardError(
                    f"approved effect signature missing from {key[0]}::{key[1]} ({missing})"
                )


def _validate_sanitized_git_helpers(tree: ast.AST, path_text: str) -> None:
    expected_module = ast.parse(dedent(
        '''\
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
        '''
    ))
    for expected in expected_module.body:
        if not isinstance(expected, ast.FunctionDef):  # pragma: no cover - fixed literal
            raise AssertionError(path_text)
        matches = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == expected.name
        ]
        if (
            len(matches) != 1
            or ast.dump(matches[0], include_attributes=False)
            != ast.dump(expected, include_attributes=False)
        ):
            raise GuardError(f"{path_text}::{expected.name} Git sanitizer changed")


def _validate_station_git_wrapper(tree: ast.AST) -> None:
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_git"]
    expected = ast.parse(dedent(
        '''\
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
        '''
    )).body[0]
    if (
        len(functions) != 1
        or ast.dump(functions[0], include_attributes=False)
        != ast.dump(expected, include_attributes=False)
    ):
        raise GuardError("tools/verify_station.py::_git sanitizer or Git-only command changed")


def _validate_runtime_exec_tests(tree: ast.AST) -> None:
    protected_builtins = {"compile", "exec"}
    for node in ast.walk(tree):
        rebound: str | None = None
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            rebound = node.id
        elif isinstance(node, ast.arg):
            rebound = node.arg
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            rebound = node.name
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                local = alias.asname or (
                    alias.name if isinstance(node, ast.ImportFrom)
                    else alias.name.split(".")[0]
                )
                if local in protected_builtins:
                    raise GuardError(f"runtime exec builtin binding changed: {local}")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            if protected_builtins.intersection(node.names):
                rebound = next(iter(protected_builtins.intersection(node.names)))
        elif isinstance(node, ast.ExceptHandler) and isinstance(node.name, str):
            rebound = node.name
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)):
            rebound = node.name
        elif isinstance(node, ast.MatchMapping):
            rebound = node.rest
        if rebound in protected_builtins:
            raise GuardError(f"runtime exec builtin binding changed: {rebound}")

    for function_name, expected_digest in _RUNTIME_EXEC_TEST_AST_SHA256.items():
        matches = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        ]
        if len(matches) != 1:
            raise GuardError(f"runtime exec test identity changed: {function_name}")
        actual_digest = hashlib.sha256(
            ast.dump(matches[0], include_attributes=False).encode("utf-8")
        ).hexdigest()
        if actual_digest != expected_digest:
            raise GuardError(f"runtime exec test AST seal changed: {function_name}")


def _assigned_call(function: ast.FunctionDef, target: str, callee: str) -> ast.Call:
    matches: list[ast.Call] = []
    for statement in function.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        name = statement.targets[0]
        if isinstance(name, ast.Name) and name.id == target and isinstance(statement.value, ast.Call):
            if _attribute_path(statement.value.func, {}) == callee:
                matches.append(statement.value)
    if len(matches) != 1:
        raise GuardError(f"{NOTEBOOK_BUILDER} must assign exactly one {target} code cell")
    return matches[0]


def _dedented_literal(call: ast.Call, target: str) -> str:
    if len(call.args) != 1 or call.keywords:
        raise GuardError(f"{NOTEBOOK_BUILDER} {target} code_cell shape changed")
    wrapper = call.args[0]
    if (
        not isinstance(wrapper, ast.Call)
        or _attribute_path(wrapper.func, {}) != "dedent"
        or len(wrapper.args) != 1
        or wrapper.keywords
        or not isinstance(wrapper.args[0], ast.Constant)
        or not isinstance(wrapper.args[0].value, str)
    ):
        raise GuardError(f"{NOTEBOOK_BUILDER} {target} must be one static dedented source literal")
    return dedent(wrapper.args[0].value)


def _validate_notebook_builder(tree: ast.AST) -> None:
    constructors = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "code_cell"
    ]
    expected_constructor = ast.parse(dedent(
        '''\
        def code_cell(source: str) -> dict[str, Any]:
            return {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {"trusted": True},
                "outputs": [],
                "source": source,
            }
        '''
    )).body[0]
    if (
        len(constructors) != 1
        or ast.dump(constructors[0], include_attributes=False)
        != ast.dump(expected_constructor, include_attributes=False)
    ):
        raise GuardError(f"{NOTEBOOK_BUILDER} code_cell constructor changed")

    functions = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "notebook_document"
    ]
    if len(functions) != 1:
        raise GuardError(f"{NOTEBOOK_BUILDER} must contain exactly one notebook_document")
    function = functions[0]
    code_calls = [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call) and _attribute_path(node.func, {}) == "code_cell"
    ]
    if len(code_calls) != 4:
        raise GuardError(f"{NOTEBOOK_BUILDER} must contain exactly four declared code cells")

    install = _assigned_call(function, "install", "code_cell")
    write_agent = _assigned_call(function, "write_agent", "code_cell")
    run_framework = _assigned_call(function, "run_framework", "code_cell")
    dummy = _assigned_call(function, "dummy", "code_cell")

    if (
        len(install.args) != 1 or install.keywords
        or not isinstance(install.args[0], ast.Constant)
        or install.args[0].value != NOTEBOOK_INSTALL_CELL
    ):
        raise GuardError(f"{NOTEBOOK_BUILDER} offline install cell changed")
    expected_write = ast.parse('"%%writefile /tmp/my_agent.py\\n" + agent_source', mode="eval").body
    if (
        len(write_agent.args) != 1 or write_agent.keywords
        or ast.dump(write_agent.args[0], include_attributes=False)
        != ast.dump(expected_write, include_attributes=False)
    ):
        raise GuardError(f"{NOTEBOOK_BUILDER} agent-write cell changed")

    # Fix the returned cell list so an uninspected raw code-cell dictionary
    # cannot be smuggled into the generated notebook.
    returns = [node for node in function.body if isinstance(node, ast.Return)]
    if len(returns) != 1 or not isinstance(returns[0].value, ast.Dict):
        raise GuardError(f"{NOTEBOOK_BUILDER} notebook return shape changed")
    document = returns[0].value
    cells_values = [
        value for key, value in zip(document.keys, document.values)
        if isinstance(key, ast.Constant) and key.value == "cells"
    ]
    if len(cells_values) != 1 or not isinstance(cells_values[0], ast.List):
        raise GuardError(f"{NOTEBOOK_BUILDER} cells list changed")
    cells = cells_values[0].elts
    if len(cells) != 5:
        raise GuardError(f"{NOTEBOOK_BUILDER} must return one markdown and four code cells")
    returned_names = [item.id for item in cells[1:] if isinstance(item, ast.Name)]
    if returned_names != ["install", "write_agent", "run_framework", "dummy"]:
        raise GuardError(f"{NOTEBOOK_BUILDER} returned code-cell order changed")
    protected_cells = {"install", "write_agent", "run_framework", "dummy"}
    for name in (node for node in ast.walk(function) if isinstance(node, ast.Name)):
        if name.id not in protected_cells:
            continue
        parent = next(
            (candidate for candidate in ast.walk(function) if name in ast.iter_child_nodes(candidate)),
            None,
        )
        if isinstance(name.ctx, ast.Store):
            if not isinstance(parent, ast.Assign) or parent.value not in code_calls:
                raise GuardError(f"{NOTEBOOK_BUILDER} mutates protected cell {name.id}")
        elif not (isinstance(parent, ast.List) and parent is cells_values[0]):
            raise GuardError(f"{NOTEBOOK_BUILDER} reuses protected cell {name.id} before return")

    if (
        len(run_framework.args) != 1
        or run_framework.keywords
        or not isinstance(run_framework.args[0], ast.Name)
        or run_framework.args[0].id != "run_source"
    ):
        raise GuardError(f"{NOTEBOOK_BUILDER} run_framework cell binding changed")
    run_source_assignments = [
        statement for statement in function.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == "run_source"
    ]
    if len(run_source_assignments) != 2:
        raise GuardError(f"{NOTEBOOK_BUILDER} run_source assignment count changed")
    initial_run_source = run_source_assignments[0].value
    if (
        not isinstance(initial_run_source, ast.Call)
        or _attribute_path(initial_run_source.func, {}) != "dedent"
        or len(initial_run_source.args) != 1
        or initial_run_source.keywords
        or not isinstance(initial_run_source.args[0], ast.Constant)
        or not isinstance(initial_run_source.args[0].value, str)
    ):
        raise GuardError(f"{NOTEBOOK_BUILDER} run_source must begin as one static literal")
    expected_replacement = ast.parse(
        'run_source.replace("__RUNTIME_CLOSURE_STATUS__", runtime_closure_status_literal)'
        '.replace("__EXPECTED_PYTHON_MINOR__", python_minor_literal)'
        '.replace("__EXPECTED_RUNTIME_VERSIONS__", runtime_versions_literal)'
        '.replace("__EXPECTED_AGENTS_FILES__", agents_files_literal)'
        '.replace("__EXPECTED_LICENSE_FILE__", license_file_literal)'
        '.replace("__EXPECTED_CANDIDATE_AGENT_SHA256__", candidate_agent_sha256_literal)',
        mode="eval",
    ).body
    if (
        ast.dump(run_source_assignments[1].value, include_attributes=False)
        != ast.dump(expected_replacement, include_attributes=False)
    ):
        raise GuardError(f"{NOTEBOOK_BUILDER} run_source substitutions changed")
    runtime_source = dedent(initial_run_source.args[0].value)
    dummy_source = _dedented_literal(dummy, "dummy")
    try:
        runtime_tree = ast.parse(runtime_source, filename=NOTEBOOK_RUNTIME_CONTEXT)
        dummy_tree = ast.parse(dummy_source, filename=NOTEBOOK_DUMMY_CONTEXT)
    except SyntaxError as exc:
        raise GuardError(f"generated notebook contains invalid Python: {exc}") from exc

    gateway_assignments = [
        node for node in ast.walk(runtime_tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "gateway" for target in node.targets)
    ]
    if (
        len(gateway_assignments) != 1
        or not isinstance(gateway_assignments[0].value, ast.Constant)
        or gateway_assignments[0].value.value != "http://gateway:8001/api/games"
    ):
        raise GuardError("generated notebook gateway binding changed")
    opener_assignments = [
        node for node in ast.walk(runtime_tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "gateway_opener"
            for target in node.targets
        )
    ]
    expected_opener = ast.parse(
        "urllib.request.build_opener("
        "urllib.request.ProxyHandler({}), _NoGatewayRedirect())",
        mode="eval",
    ).body
    if (
        len(opener_assignments) != 1
        or ast.dump(opener_assignments[0].value, include_attributes=False)
        != ast.dump(expected_opener, include_attributes=False)
    ):
        raise GuardError("generated notebook proxy-disabled gateway opener changed")

    redirect_classes = [
        node for node in ast.walk(runtime_tree) if isinstance(node, ast.ClassDef)
    ]
    expected_redirect_class = ast.parse(dedent(
        '''\
        class _NoGatewayRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, file_pointer, code, message, headers, new_url):
                raise RuntimeError("competition gateway redirect is forbidden")
        '''
    )).body[0]
    if (
        len(redirect_classes) != 1
        or ast.dump(redirect_classes[0], include_attributes=False)
        != ast.dump(expected_redirect_class, include_attributes=False)
    ):
        raise GuardError("generated notebook no-redirect gateway handler changed")

    runtime_guard = _PythonEffectGuard(NOTEBOOK_RUNTIME_CONTEXT, runtime_tree, notebook_runtime=True)
    runtime_guard.visit(runtime_tree)
    runtime_guard.finish()
    dummy_guard = _PythonEffectGuard(NOTEBOOK_DUMMY_CONTEXT, dummy_tree)
    dummy_guard.visit(dummy_tree)
    dummy_guard.finish()


def _guard_python(path_text: str, data: bytes) -> None:
    if data.startswith(b"\xef\xbb\xbf"):
        raise GuardError(f"Python source must use BOM-free UTF-8: {path_text}")
    for line in data.splitlines()[:2]:
        match = PYTHON_CODING_COOKIE.match(line)
        if match is None:
            continue
        encoding = match.group(1).decode("ascii").lower().replace("_", "-")
        if encoding not in {"utf-8", "utf8"}:
            raise GuardError(f"Python source must use UTF-8: {path_text} ({encoding})")
    try:
        tree = ast.parse(data.decode("utf-8"), filename=path_text)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise GuardError(f"invalid Python {path_text}: {exc}") from exc
    self_assignment: ast.Assign | None = None
    if path_text == "tools/repository_guard.py":
        self_assignments = [
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "SELF_AST_SHA256"
                for target in node.targets
            )
        ]
        if (
            len(self_assignments) != 1
            or len(self_assignments[0].targets) != 1
            or not isinstance(self_assignments[0].targets[0], ast.Name)
            or self_assignments[0].targets[0].id != "SELF_AST_SHA256"
            or not isinstance(self_assignments[0].value, ast.Constant)
            or not isinstance(self_assignments[0].value.value, str)
            or re.fullmatch(r"[0-9a-f]{64}", self_assignments[0].value.value) is None
        ):
            raise GuardError("repository guard self-AST seal assignment shape changed")
        self_assignment = self_assignments[0]
    effect_guard = _PythonEffectGuard(path_text, tree)
    effect_guard.visit(tree)
    effect_guard.finish()
    import_inventory = sorted(
        ast.dump(node, include_attributes=False)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    )
    import_digest = hashlib.sha256(("\n".join(import_inventory) + "\n").encode("utf-8")).hexdigest()
    expected_import_digest = ALLOWED_IMPORT_SHA256.get(path_text)
    if expected_import_digest is None or import_digest != expected_import_digest:
        raise GuardError(
            f"Python import inventory is not exact-allowlisted: {path_text} ({import_digest})"
        )
    if path_text == "tools/repository_guard.py":
        if self_assignment is None:  # pragma: no cover - established above
            raise AssertionError("repository guard self seal was not bound")
        self_assignment.value = ast.Constant(value="<SELF_AST_SHA256>")
        self_digest = hashlib.sha256(
            ast.dump(tree, include_attributes=False).encode("utf-8")
        ).hexdigest()
        if self_digest != SELF_AST_SHA256:
            raise GuardError(f"repository guard self-AST seal mismatch ({self_digest})")
    else:
        expected_blob_digest = ALLOWED_PYTHON_SHA256.get(path_text)
        blob_digest = hashlib.sha256(data).hexdigest()
        if expected_blob_digest is None or blob_digest != expected_blob_digest:
            raise GuardError(
                f"Python staged blob is not exact-allowlisted: {path_text} ({blob_digest})"
            )
    if path_text == "tools/verify_station.py":
        _validate_station_git_wrapper(tree)
    if path_text == "tests/test_candidate.py":
        _validate_runtime_exec_tests(tree)
    if path_text in {
        "scripts/build_notebook.py",
        "scripts/verify_candidate.py",
        "scripts/verify_human_gate.py",
    }:
        _validate_sanitized_git_helpers(tree, path_text)
    if path_text == NOTEBOOK_BUILDER:
        _validate_notebook_builder(tree)


def _is_unapproved_script(path: Path, data: bytes, git_mode: str | None) -> bool:
    suffix = path.suffix.lower()
    if git_mode is not None:
        executable = git_mode == "100755"
    else:
        try:
            mode = path.stat().st_mode
        except OSError:
            mode = 0
        executable = bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    return suffix in SHELL_SUFFIXES or executable or data.startswith(b"#!")


def _guard_workflow(path_text: str, data: bytes, guard_blob_sha256: str) -> None:
    matches = list(WORKFLOW_GUARD_PIN.finditer(data))
    if len(matches) != 1:
        raise GuardError(f"workflow must contain exactly one repository-guard pin: {path_text}")
    embedded = matches[0].group("digest").decode("ascii")
    if embedded != guard_blob_sha256:
        raise GuardError(
            f"workflow repository-guard pin does not match staged guard: {path_text}"
        )
    normalized = WORKFLOW_GUARD_PIN.sub(
        lambda match: match.group("prefix") + (b"0" * 64) + match.group("suffix"),
        data,
    )
    actual = hashlib.sha256(normalized).hexdigest()
    expected = ALLOWED_WORKFLOW_NORMALIZED_SHA256.get(path_text)
    if expected is None or actual != expected:
        raise GuardError(f"workflow semantics are not exact-allowlisted: {path_text} ({actual})")
    if path_text == ".github/workflows/launch-verify.yml":
        finite_parser = (
            b"          def parse_finite_float(value):\n"
            b"              parsed = float(value)\n"
            b"              if parsed == float(\"inf\") or parsed == float(\"-inf\"):\n"
            b"                  reject_nonfinite(value)\n"
            b"              return parsed\n"
        )
        if data.count(finite_parser) != 1 or data.count(
            b"                  parse_float=parse_finite_float,\n"
        ) != 1:
            raise GuardError("launch verification finite-number JSON guard changed")


def guard(paths: list[str] | None = None) -> dict[str, int]:
    from_index = paths is None
    if from_index:
        index_entries = tracked_entries()
        tracked = list(index_entries)
        nonregular = [
            path for path, (mode, _) in index_entries.items()
            if mode != "100644"
        ]
        if nonregular:
            raise GuardError(
                "non-regular or executable tracked paths: " + ", ".join(nonregular)
            )
    else:
        index_entries = {}
        tracked = paths
    portable_paths: dict[str, str] = {}
    collisions: list[str] = []
    for path in tracked:
        portable = path.replace("\\", "/").casefold()
        previous = portable_paths.get(portable)
        if previous is not None and previous != path:
            collisions.append(f"{previous} <> {path}")
        else:
            portable_paths[portable] = path
    if collisions:
        raise GuardError("casefold-ambiguous tracked paths: " + ", ".join(collisions))
    path_secret_labels = {
        label
        for path in tracked
        for label, pattern in SECRET_PATTERNS.items()
        if pattern.search(path.encode("utf-8"))
    }
    if path_secret_labels:
        raise GuardError(
            "possible committed secret in tracked path name: "
            + ", ".join(sorted(path_secret_labels))
        )
    forbidden_exact_casefold = {path.casefold() for path in FORBIDDEN_EXACT}
    forbidden_prefixes_casefold = tuple(path.casefold() for path in FORBIDDEN_PREFIXES)
    forbidden_paths = []
    for path in tracked:
        policy_path = path.replace("\\", "/").casefold()
        policy_name = policy_path.rsplit("/", 1)[-1]
        policy_suffix = Path(policy_name).suffix.lower()
        if (
            policy_path in forbidden_exact_casefold
            or policy_path.startswith(forbidden_prefixes_casefold)
            or _contains_forbidden_directory(path)
            or policy_name.startswith(".env")
            or policy_name in FORBIDDEN_CONTROL_NAMES
            or policy_suffix in {".pem", ".key", ".p12", ".pfx"}
        ):
            forbidden_paths.append(path)
    if forbidden_paths:
        raise GuardError("forbidden tracked paths: " + ", ".join(forbidden_paths))
    unexpected_sources = []
    for path_text in tracked:
        if path_text in ALLOWED_AUXILIARY_SHA256:
            continue
        suffix = Path(path_text).suffix.lower()
        if suffix in {".py", ".json", ".md"}:
            continue
        if suffix == ".yml" and path_text.startswith(".github/workflows/"):
            continue
        if not suffix and path_text in ALLOWED_EXTENSIONLESS_PATHS:
            continue
        unexpected_sources.append(path_text)
    if unexpected_sources:
        raise GuardError("unapproved tracked source type or path: " + ", ".join(unexpected_sources))
    if from_index:
        python_inventory = {path for path in tracked if Path(path).suffix.lower() == ".py"}
        expected_python_inventory = set(ALLOWED_PYTHON_SHA256) | {"tools/repository_guard.py"}
        if python_inventory != expected_python_inventory:
            missing = sorted(expected_python_inventory - python_inventory)
            extra = sorted(python_inventory - expected_python_inventory)
            raise GuardError(f"Python inventory changed: missing={missing}, extra={extra}")
        missing_controls = sorted(set(ALLOWED_CONTROL_JSON_SHA256) - set(tracked))
        if missing_controls:
            raise GuardError(f"required control JSON is missing: {missing_controls}")
        missing_auxiliary = sorted(set(ALLOWED_AUXILIARY_SHA256) - set(tracked))
        if missing_auxiliary:
            raise GuardError(f"required auxiliary blobs are missing: {missing_auxiliary}")

    secret_hits: list[str] = []
    content_by_path: dict[str, bytes] = {}
    json_count = 0
    python_count = 0
    for path_text in tracked:
        path = ROOT / path_text
        if from_index:
            mode, object_id = index_entries[path_text]
            data = read_index_blob(object_id)
        else:
            mode = None
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise GuardError(f"tracked path cannot be read exactly: {path_text}: {exc}") from exc
        content_by_path[path_text] = data
        expected_auxiliary_digest = ALLOWED_AUXILIARY_SHA256.get(path_text)
        actual_auxiliary_digest = hashlib.sha256(data).hexdigest()
        if (
            expected_auxiliary_digest is not None
            and actual_auxiliary_digest != expected_auxiliary_digest
        ):
            raise GuardError(
                f"auxiliary staged blob is not exact-allowlisted: "
                f"{path_text} ({actual_auxiliary_digest})"
            )
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                secret_hits.append(f"{path_text}: {label}")
        if path.suffix.lower() == ".json":
            try:
                parsed_json = json.loads(
                    data.decode("utf-8"),
                    object_pairs_hook=_reject_duplicates,
                    parse_constant=_reject_nonfinite,
                    parse_float=_parse_finite_float,
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise GuardError(f"invalid strict JSON {path_text}: {exc}") from exc
            if _contains_legacy_kaggle_credential(parsed_json):
                secret_hits.append(f"{path_text}: legacy Kaggle API key")
            for decoded in _json_strings(parsed_json):
                for label, pattern in DECODED_SECRET_PATTERNS.items():
                    if pattern.search(decoded):
                        secret_hits.append(f"{path_text}: decoded {label}")
                allowed_references = ALLOWED_SENSITIVE_PATH_REFERENCES.get(path_text, set())
                if (
                    _looks_like_sensitive_path(decoded)
                    and decoded.casefold() not in allowed_references
                ):
                    secret_hits.append(f"{path_text}: decoded sensitive path reference")
            expected_control_digest = ALLOWED_CONTROL_JSON_SHA256.get(path_text)
            actual_control_digest = hashlib.sha256(data).hexdigest()
            if (
                expected_control_digest is not None
                and actual_control_digest != expected_control_digest
            ):
                raise GuardError(
                    f"control JSON staged blob is not exact-allowlisted: "
                    f"{path_text} ({actual_control_digest})"
                )
            json_count += 1
        if path.suffix.lower() == ".py":
            _guard_python(path_text, data)
            python_count += 1
        elif _is_unapproved_script(path, data, mode):
            raise GuardError(f"unapproved tracked executable or shell script: {path_text}")
        if path_text == "Makefile" and hashlib.sha256(data).hexdigest() != MAKEFILE_SHA256:
            raise GuardError("Makefile staged blob is not exact-allowlisted")
    if secret_hits:
        raise GuardError("possible committed secret:\n" + "\n".join(secret_hits))

    workflows = {path for path in tracked if path.startswith(".github/workflows/")}
    if from_index and workflows != set(ALLOWED_WORKFLOW_NORMALIZED_SHA256):
        missing = sorted(set(ALLOWED_WORKFLOW_NORMALIZED_SHA256) - workflows)
        extra = sorted(workflows - set(ALLOWED_WORKFLOW_NORMALIZED_SHA256))
        raise GuardError(f"workflow inventory changed: missing={missing}, extra={extra}")
    if workflows:
        if from_index:
            guard_blob = content_by_path["tools/repository_guard.py"]
        else:
            try:
                guard_blob = (ROOT / "tools/repository_guard.py").read_bytes()
            except OSError as exc:
                raise GuardError(
                    f"repository guard blob cannot be read for workflow pin: {exc}"
                ) from exc
        guard_blob_sha256 = hashlib.sha256(guard_blob).hexdigest()
        for path_text in workflows:
            _guard_workflow(path_text, content_by_path[path_text], guard_blob_sha256)
    workflow_count = len(workflows)
    if from_index and tracked_entries() != index_entries:
        raise GuardError("Git index changed while repository guard was scanning")
    return {
        "tracked": len(tracked),
        "json": json_count,
        "python": python_count,
        "workflows": workflow_count,
    }


def _root_from_arguments(arguments: list[str]) -> Path:
    if not arguments:
        return ROOT
    if len(arguments) != 2 or arguments[0] != "--root":
        raise GuardError("usage: repository_guard.py [--root ABSOLUTE_REPOSITORY_ROOT]")
    requested = Path(arguments[1])
    if not requested.is_absolute():
        raise GuardError("--root must be an absolute path")
    try:
        resolved = requested.resolve(strict=True)
    except OSError as exc:
        raise GuardError(f"--root cannot be resolved: {requested}: {exc}") from exc
    if not resolved.is_dir():
        raise GuardError(f"--root is not a directory: {resolved}")
    return resolved


def main(arguments: list[str] | None = None) -> int:
    global ROOT
    if not sys.flags.isolated:
        print(
            "REPOSITORY_GUARD_FAIL invoke with: "
            "python -I -B tools/repository_guard.py [--root ABSOLUTE_REPOSITORY_ROOT]"
        )
        return 1
    try:
        ROOT = _root_from_arguments(sys.argv[1:] if arguments is None else arguments)
        result = guard()
    except GuardError as exc:
        print(f"REPOSITORY_GUARD_FAIL {exc}")
        return 1
    print("REPOSITORY_GUARD_PASS " + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
