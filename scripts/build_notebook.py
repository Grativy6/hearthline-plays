#!/usr/bin/env python3
"""Build one deterministic, offline ARC-AGI-3 candidate package.

The generated manifest is an output, never a trust anchor. Verification
regenerates every byte from committed Git objects and compares the result with
a single safely-read snapshot of this directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from textwrap import dedent
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "agent/my_agent.py"
METADATA_TEMPLATE = ROOT / "notebooks/kernel-metadata.template.json"
SOURCE_LOCK = ROOT / "launch/source-lock.v3.json"
STARTER_CONTRACT = ROOT / "launch/contracts/official-starter-eeb153.contract.json"
BUILDER_PATH = ROOT / "scripts/build_notebook.py"
DEFAULT_OUTPUT = ROOT / "build"

ACCELERATORS = {
    "cpu": {"name": "none", "gpu": False},
    "t4": {"name": "nvidiaTeslaT4", "gpu": True},
    "p100": {"name": "nvidiaTeslaP100", "gpu": True},
    "rtx6000": {"name": "nvidiaRtx6000", "gpu": True},
}
OUTPUT_FILES = (
    "candidate-manifest.json",
    "kernel-metadata.json",
    "submission.ipynb",
)


class BuildError(RuntimeError):
    """Raised when a deterministic package cannot be built safely."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BuildError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise BuildError(f"non-finite JSON number is forbidden: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if parsed == float("inf") or parsed == float("-inf"):
        _reject_nonfinite(value)
    return parsed


def strict_json_bytes(data: bytes, label: str) -> Any:
    try:
        text = data.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"{label}: invalid strict UTF-8 JSON: {exc}") from exc


def code_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"trusted": True},
        "outputs": [],
        "source": source,
    }


def markdown_cell(source: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def _execution_guard_inputs(
    source_lock: Any,
) -> tuple[str, str, dict[str, str], dict[str, str], dict[str, str]]:
    """Extract the closed competition-rerun preflight from the source lock."""
    if not isinstance(source_lock, dict):
        raise BuildError("source lock must be an object")
    dependency_resolution = source_lock.get("dependency_resolution")
    if not isinstance(dependency_resolution, dict):
        raise BuildError("source lock dependency resolution must be an object")
    runtime_closure_status = dependency_resolution.get("runtime_closure_status")
    if runtime_closure_status not in {
        "UNFROZEN_PENDING_GATE_A_SUCCESSOR",
        "FROZEN_POST_STAGE_SUCCESSOR",
    }:
        raise BuildError("source lock runtime closure status is invalid")
    runtime_versions = dependency_resolution.get("required_runtime_versions")
    if (
        not isinstance(runtime_versions, dict)
        or set(runtime_versions) != {"arc-agi", "arcengine"}
        or any(
            not isinstance(name, str)
            or not isinstance(version, str)
            or not version
            for name, version in runtime_versions.items()
        )
    ):
        raise BuildError("source lock runtime versions are not a closed exact map")

    official_software = source_lock.get("official_software")
    if not isinstance(official_software, list):
        raise BuildError("source lock official software must be a list")
    starter_rows = [
        row
        for row in official_software
        if isinstance(row, dict)
        and row.get("repository") == "arcprize/ARC-AGI-3-Kaggle-Starter"
    ]
    if len(starter_rows) != 1:
        raise BuildError("source lock must contain exactly one starter identity")
    starter_contract = starter_rows[0].get("contract")
    python_minor = (
        starter_contract.get("python_minor")
        if isinstance(starter_contract, dict)
        else None
    )
    if (
        not isinstance(python_minor, str)
        or len(python_minor.split(".")) != 2
        or not all(part.isdigit() for part in python_minor.split("."))
    ):
        raise BuildError("source lock Python minor is invalid")
    agents_rows = [
        row
        for row in official_software
        if isinstance(row, dict)
        and row.get("repository") == "arcprize/ARC-AGI-3-Agents"
    ]
    if len(agents_rows) != 1:
        raise BuildError("source lock must contain exactly one Agents identity")
    bindings = agents_rows[0].get("inspected_file_bindings")
    expected_paths = {
        "agents/agent.py",
        "agents/recorder.py",
        "agents/swarm.py",
        "agents/tracing.py",
        "main.py",
    }
    if not isinstance(bindings, dict) or set(bindings) != expected_paths:
        raise BuildError("source lock executed Agents files are not a closed exact map")
    agents_files: dict[str, str] = {}
    for relative, binding in bindings.items():
        if not isinstance(binding, dict):
            raise BuildError(f"source lock Agents binding is not an object: {relative}")
        digest = binding.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise BuildError(f"source lock Agents sha256 is invalid: {relative}")
        agents_files[relative] = digest
    license_binding = agents_rows[0].get("license_file_binding")
    if not isinstance(license_binding, dict) or license_binding.get("path") != "LICENSE":
        raise BuildError("source lock Agents license binding is invalid")
    license_digest = license_binding.get("sha256")
    if (
        not isinstance(license_digest, str)
        or len(license_digest) != 64
        or any(character not in "0123456789abcdef" for character in license_digest)
    ):
        raise BuildError("source lock Agents license sha256 is invalid")
    return (
        python_minor,
        runtime_closure_status,
        {name: runtime_versions[name] for name in sorted(runtime_versions)},
        {name: agents_files[name] for name in sorted(agents_files)},
        {"LICENSE": license_digest},
    )


def notebook_document(
    agent_source: str,
    accelerator: str,
    python_minor: str,
    runtime_closure_status: str,
    runtime_versions: dict[str, str],
    agents_files: dict[str, str],
    license_file: dict[str, str],
) -> dict[str, Any]:
    """Return the exact notebook document for a declared accelerator."""
    if accelerator not in ACCELERATORS:
        raise BuildError(f"unknown accelerator: {accelerator}")
    accel = ACCELERATORS[accelerator]

    install = code_cell(
        "!python -m pip install --no-index --find-links "
        "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels "
        "arc-agi python-dotenv"
    )
    write_agent = code_cell("%%writefile /tmp/my_agent.py\n" + agent_source)

    # This independently expresses the public interoperability contract. The
    # registry and environment are rendered from typed rows instead of copying
    # the starter's multi-line literals.
    runtime_versions_literal = json.dumps(runtime_versions, sort_keys=True)
    agents_files_literal = json.dumps(agents_files, sort_keys=True)
    license_file_literal = json.dumps(license_file, sort_keys=True)
    candidate_agent_sha256_literal = json.dumps(
        sha256_bytes(agent_source.encode("utf-8"))
    )
    python_minor_literal = json.dumps(python_minor)
    runtime_closure_status_literal = json.dumps(runtime_closure_status)
    run_source = dedent(
        """\
        import hashlib
        import importlib.metadata
        import os
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
            expected_python_minor = __EXPECTED_PYTHON_MINOR__
            observed_python_minor = ".".join(str(part) for part in sys.version_info[:2])
            if observed_python_minor != expected_python_minor:
                raise RuntimeError(
                    "Python minor mismatch before competition rerun: "
                    f"expected={expected_python_minor!r}, observed={observed_python_minor!r}"
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
            observed_runtime_versions = {}
            for distribution_name in sorted(expected_runtime_versions):
                try:
                    observed_runtime_versions[distribution_name] = importlib.metadata.version(
                        distribution_name
                    )
                except importlib.metadata.PackageNotFoundError:
                    observed_runtime_versions[distribution_name] = None
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
        "__EXPECTED_PYTHON_MINOR__", python_minor_literal
    ).replace(
        "__EXPECTED_RUNTIME_VERSIONS__", runtime_versions_literal
    ).replace(
        "__EXPECTED_AGENTS_FILES__", agents_files_literal
    ).replace(
        "__EXPECTED_LICENSE_FILE__", license_file_literal
    ).replace(
        "__EXPECTED_CANDIDATE_AGENT_SHA256__", candidate_agent_sha256_literal
    )
    run_framework = code_cell(run_source)
    dummy = code_cell(dedent(
        """\
        import hashlib
        import importlib.metadata
        import json
        import os
        import re
        import sys
        from pathlib import Path

        if not os.getenv("KAGGLE_IS_COMPETITION_RERUN"):
            distributions = {}
            for distribution in importlib.metadata.distributions():
                raw_name = str(distribution.metadata.get("Name", distribution.name)).strip()
                name = re.sub(r"[-_.]+", "-", raw_name).lower()
                if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is None:
                    raise RuntimeError(f"invalid canonical distribution name: {raw_name!r}")
                if name in distributions:
                    raise RuntimeError(f"duplicate canonical distribution name: {name}")
                distributions[name] = str(distribution.version)
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
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "pygments_lexer": "ipython3",
            },
            "kaggle": {
                "accelerator": accel["name"],
                "isGpuEnabled": accel["gpu"],
                "isInternetEnabled": False,
                "language": "python",
                "sourceType": "notebook",
            },
            "hearthline": {
                "agent_sha256": sha256_bytes(agent_source.encode("utf-8")),
                "builder": "scripts/build_notebook.py",
                "official_agents_commit": "4743e7d0aaae0ded0d98a89a7e282e63564cd58b",
                "official_starter_commit": "eeb1535404f321d280a8f9194bbc1d7aca5f05fc",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 4,
        "cells": [
            markdown_cell(
                "# Hearthline ARC-AGI-3 candidate\n\n"
                "Generated offline from `agent/my_agent.py`. Phase A only stages a private kernel; "
                "Phase B is a separate manual competition-UI decision."
            ),
            install,
            write_agent,
            run_framework,
            dummy,
        ],
    }


def _validate_username(username: str) -> str:
    if not isinstance(username, str):
        raise BuildError("username must be text")
    if not username:
        return "REPLACE_WITH_YOUR_USERNAME"
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,62}", username) is None:
        raise BuildError("username must be one 2..63 character Kaggle account slug")
    return username


def render_candidate(
    *,
    agent_bytes: bytes,
    metadata_template_bytes: bytes,
    source_lock_bytes: bytes,
    starter_contract_bytes: bytes,
    builder_bytes: bytes,
    commit: str,
    tree: str,
    username: str,
    accelerator: str,
) -> dict[str, bytes]:
    """Render every candidate byte from explicit, content-addressed inputs."""
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise BuildError("commit must be 40 lowercase hexadecimal characters")
    if len(tree) != 40 or any(char not in "0123456789abcdef" for char in tree):
        raise BuildError("tree must be 40 lowercase hexadecimal characters")
    account_slug = _validate_username(username)
    if accelerator not in ACCELERATORS:
        raise BuildError(f"unknown accelerator: {accelerator}")
    try:
        agent_source = agent_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError("agent/my_agent.py must be UTF-8") from exc
    metadata = strict_json_bytes(metadata_template_bytes, "kernel metadata template")
    if not isinstance(metadata, dict):
        raise BuildError("kernel metadata template must be an object")
    source_lock = strict_json_bytes(source_lock_bytes, "source lock")
    strict_json_bytes(starter_contract_bytes, "starter contract")

    kernel_id = f"{account_slug}/hearthline-arc3-readiness"
    metadata["id"] = kernel_id
    metadata["enable_gpu"] = ACCELERATORS[accelerator]["gpu"]
    (
        python_minor,
        runtime_closure_status,
        runtime_versions,
        agents_files,
        license_file,
    ) = _execution_guard_inputs(source_lock)
    notebook = notebook_document(
        agent_source,
        accelerator,
        python_minor,
        runtime_closure_status,
        runtime_versions,
        agents_files,
        license_file,
    )
    notebook_bytes = (json.dumps(notebook, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
    metadata_bytes = (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    trusted_inputs = {
        "agent/my_agent.py": sha256_bytes(agent_bytes),
        "launch/contracts/official-starter-eeb153.contract.json": sha256_bytes(starter_contract_bytes),
        "launch/source-lock.v3.json": sha256_bytes(source_lock_bytes),
        "notebooks/kernel-metadata.template.json": sha256_bytes(metadata_template_bytes),
        "scripts/build_notebook.py": sha256_bytes(builder_bytes),
    }
    artifacts = {
        "kernel-metadata.json": sha256_bytes(metadata_bytes),
        "submission.ipynb": sha256_bytes(notebook_bytes),
    }
    manifest = {
        "schema": "hearthline.arc3.offline-candidate-manifest.v3",
        "candidate": {"commit": commit, "tree": tree, "worktree_clean": True},
        "parameters": {
            "accelerator": accelerator,
            "account_slug": account_slug,
            "kernel_id": kernel_id,
        },
        "trusted_inputs": trusted_inputs,
        "artifacts": artifacts,
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


def git_identity() -> dict[str, Any]:
    commit = subprocess.check_output(
        _git_command("rev-parse", "HEAD"), cwd=ROOT, text=True, env=_git_environment()
    ).strip()
    tree = subprocess.check_output(
        _git_command("rev-parse", "HEAD^{tree}"), cwd=ROOT, text=True, env=_git_environment()
    ).strip()
    dirty = bool(
        subprocess.check_output(
            _git_command("status", "--porcelain", "--untracked-files=normal"),
            cwd=ROOT,
            text=True,
            env=_git_environment(),
        ).strip()
    )
    return {"commit": commit, "tree": tree, "worktree_clean": not dirty}


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


def _read_regular_input(path: Path) -> bytes:
    label = path.relative_to(ROOT)
    path_before = path.lstat()
    if not stat.S_ISREG(path_before.st_mode) or path_before.st_nlink != 1:
        raise BuildError(f"tracked input must be one regular file: {label}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise BuildError(f"tracked input must remain one regular file: {label}")
        if (
            path_before.st_dev, path_before.st_ino, path_before.st_size, path_before.st_mtime_ns
        ) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise BuildError(f"tracked input changed before open: {label}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise BuildError(f"tracked input changed during read: {label}")
        path_after = path.lstat()
        if (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) != (path_after.st_dev, path_after.st_ino, path_after.st_size, path_after.st_mtime_ns):
            raise BuildError(f"tracked input path changed during read: {label}")
        data = b"".join(chunks)
        if len(data) != after.st_size:
            raise BuildError(f"tracked input short read: {label}")
        return data
    finally:
        os.close(descriptor)


def _git_blob(commit: str, relative: str) -> bytes:
    try:
        return subprocess.check_output(
            _git_command("show", f"{commit}:{relative}"),
            cwd=ROOT,
            env=_git_environment(),
        )
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"committed build input unavailable: {relative}") from exc


def _require_safe_dirfd_support() -> None:
    required = (os.open, os.mkdir, os.rename, os.stat)
    if (
        not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or not all(function in os.supports_dir_fd for function in required)
    ):
        raise BuildError(
            "candidate packaging requires no-follow directory-descriptor support"
        )


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _absolute_lexical(path: Path) -> Path:
    """Normalize dots without resolving or silently accepting any symlink."""
    return Path(os.path.abspath(os.fspath(path)))


def _open_real_directory(path: Path, label: str) -> tuple[int, os.stat_result]:
    """Open every component no-follow and return the held final directory."""
    absolute = _absolute_lexical(path)
    anchor = Path(absolute.anchor)
    descriptor = os.open(anchor, _directory_flags())
    try:
        for component in absolute.parts[1:]:
            before = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise BuildError(f"{label} contains a non-directory or symlink component")
            child = os.open(component, _directory_flags(), dir_fd=descriptor)
            try:
                opened = os.fstat(child)
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
                ):
                    raise BuildError(f"{label} changed while its path was opened")
            except Exception:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode):
            raise BuildError(f"{label} must be a real directory")
        return descriptor, opened
    except Exception:
        os.close(descriptor)
        raise


def _open_output_directory(
    output_dir: Path,
) -> tuple[Path, int, int, os.stat_result]:
    """Create/open the output leaf beneath a held, no-follow parent FD."""
    absolute = _absolute_lexical(output_dir)
    if absolute == Path(absolute.anchor):
        raise BuildError("output directory cannot be a filesystem root")
    parent_fd, _ = _open_real_directory(absolute.parent, "output directory parent")
    try:
        try:
            os.mkdir(absolute.name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        entry = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(entry.st_mode):
            raise BuildError("output directory must be a real directory")
        output_fd = os.open(absolute.name, _directory_flags(), dir_fd=parent_fd)
        try:
            opened = os.fstat(output_fd)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or (entry.st_dev, entry.st_ino) != (opened.st_dev, opened.st_ino)
            ):
                raise BuildError("output directory changed before it was held")
        except Exception:
            os.close(output_fd)
            raise
        return absolute, parent_fd, output_fd, opened
    except Exception:
        os.close(parent_fd)
        raise


def _require_directory_binding(
    absolute: Path,
    parent_fd: int,
    opened: os.stat_result,
) -> None:
    """Require both the held parent entry and lexical path to remain bound."""
    entry = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not stat.S_ISDIR(entry.st_mode)
        or (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino)
    ):
        raise BuildError("output directory entry changed during packaging")
    rebound_fd, rebound = _open_real_directory(absolute, "output directory path")
    try:
        if (opened.st_dev, opened.st_ino) != (rebound.st_dev, rebound.st_ino):
            raise BuildError("output directory path changed during packaging")
    finally:
        os.close(rebound_fd)


def _read_file_with_identity_at(
    directory_fd: int,
    name: str,
) -> tuple[bytes, tuple[int, int, int, int]]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise BuildError(f"output must be one regular file: {name}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise BuildError(f"output changed while being read: {name}")
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(entry.st_mode)
            or entry.st_nlink != 1
            or (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            )
            != (entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns)
        ):
            raise BuildError(f"output path changed while being read: {name}")
        data = b"".join(chunks)
        if len(data) != after.st_size:
            raise BuildError(f"output short read: {name}")
        return data, (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
    finally:
        os.close(descriptor)


def _read_file_at(directory_fd: int, name: str) -> bytes:
    return _read_file_with_identity_at(directory_fd, name)[0]


def _read_output_snapshot_at(directory_fd: int) -> dict[str, bytes]:
    names = set(os.listdir(directory_fd))
    if names != set(OUTPUT_FILES):
        raise BuildError(
            "output directory inventory mismatch: "
            f"missing={sorted(set(OUTPUT_FILES) - names)}, "
            f"extra={sorted(names - set(OUTPUT_FILES))}"
        )
    result: dict[str, bytes] = {}
    identities: dict[str, tuple[int, int, int, int]] = {}
    for name in OUTPUT_FILES:
        result[name], identities[name] = _read_file_with_identity_at(
            directory_fd, name
        )
    if set(os.listdir(directory_fd)) != names:
        raise BuildError("output directory inventory changed while being read")
    for name, identity in identities.items():
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        current = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or current != identity:
            raise BuildError(f"output path changed during closed snapshot: {name}")
    return result


def _require_initial_output_inventory(directory_fd: int) -> None:
    names = set(os.listdir(directory_fd))
    expected = set(OUTPUT_FILES)
    if names and names != expected:
        raise BuildError(
            "output directory must be empty or contain exactly one prior candidate: "
            f"missing={sorted(expected - names)}, extra={sorted(names - expected)}"
        )
    for name in names:
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise BuildError(f"prior output must be one regular file: {name}")


def _atomic_write_at(directory_fd: int, name: str, data: bytes) -> None:
    """Publish one file relative to a held directory and verify its identity."""
    temporary = f".{name}.pending-{os.getpid()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
    try:
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise BuildError(f"short write while publishing {name}")
            offset += written
        os.fsync(descriptor)
        written_info = os.fstat(descriptor)
        pending = os.stat(temporary, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(pending.st_mode)
            or pending.st_nlink != 1
            or (written_info.st_dev, written_info.st_ino)
            != (pending.st_dev, pending.st_ino)
        ):
            raise BuildError(f"pending output path changed before publish: {name}")
        os.rename(
            temporary,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        published = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(published.st_mode)
            or published.st_nlink != 1
            or (written_info.st_dev, written_info.st_ino)
            != (published.st_dev, published.st_ino)
        ):
            raise BuildError(f"published output path changed: {name}")
    finally:
        os.close(descriptor)


def build(output_dir: Path, username: str, accelerator: str) -> dict[str, Any]:
    _require_safe_dirfd_support()
    identity = git_identity()
    if identity["worktree_clean"] is not True:
        raise BuildError("refusing to package a dirty worktree")
    absolute, parent_fd, output_fd, output_identity = _open_output_directory(output_dir)
    try:
        _require_initial_output_inventory(output_fd)
        _require_directory_binding(absolute, parent_fd, output_identity)
        inputs = {
            "agent/my_agent.py": _git_blob(identity["commit"], "agent/my_agent.py"),
            "notebooks/kernel-metadata.template.json": _git_blob(identity["commit"], "notebooks/kernel-metadata.template.json"),
            "launch/source-lock.v3.json": _git_blob(identity["commit"], "launch/source-lock.v3.json"),
            "launch/contracts/official-starter-eeb153.contract.json": _git_blob(identity["commit"], "launch/contracts/official-starter-eeb153.contract.json"),
            "scripts/build_notebook.py": _git_blob(identity["commit"], "scripts/build_notebook.py"),
        }
        for relative, committed in inputs.items():
            if _read_regular_input(ROOT / relative) != committed:
                raise BuildError(f"worktree input differs from committed Git object: {relative}")
        before_render = git_identity()
        if before_render != identity or before_render["worktree_clean"] is not True:
            raise BuildError("Git identity changed while freezing build inputs")
        rendered = render_candidate(
            agent_bytes=inputs["agent/my_agent.py"],
            metadata_template_bytes=inputs["notebooks/kernel-metadata.template.json"],
            source_lock_bytes=inputs["launch/source-lock.v3.json"],
            starter_contract_bytes=inputs["launch/contracts/official-starter-eeb153.contract.json"],
            builder_bytes=inputs["scripts/build_notebook.py"],
            commit=identity["commit"],
            tree=identity["tree"],
            username=username,
            accelerator=accelerator,
        )
        if set(rendered) != set(OUTPUT_FILES):
            raise BuildError("renderer returned an unexpected output inventory")
        for name in OUTPUT_FILES:
            _require_directory_binding(absolute, parent_fd, output_identity)
            _atomic_write_at(output_fd, name, rendered[name])
        os.fsync(output_fd)
        if _read_output_snapshot_at(output_fd) != rendered:
            raise BuildError("published candidate differs from rendered bytes")
        final_identity = git_identity()
        if final_identity != identity or final_identity["worktree_clean"] is not True:
            raise BuildError("Git identity changed while writing the candidate")
        _require_directory_binding(absolute, parent_fd, output_identity)
        if _read_output_snapshot_at(output_fd) != rendered:
            raise BuildError("published candidate changed during final checks")
        return strict_json_bytes(
            rendered["candidate-manifest.json"], "rendered candidate manifest"
        )
    finally:
        os.close(output_fd)
        os.close(parent_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--username", default="")
    parser.add_argument("--accelerator", choices=sorted(ACCELERATORS), default="cpu")
    args = parser.parse_args()
    try:
        manifest = build(args.output_dir, args.username, args.accelerator)
    except (BuildError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"build_notebook: {exc}") from exc
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
