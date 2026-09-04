#!/usr/bin/env python3
"""Fail-closed, standard-library checks for the Hearthline ARC launchpad."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class ValidationError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{path}: {exc}") from exc


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValidationError(f"non-finite JSON number is forbidden: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if parsed == float("inf") or parsed == float("-inf"):
        _reject_nonfinite(value)
    return parsed


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def unique(values: list[Any], label: str) -> None:
    require(len(values) == len(set(values)), f"{label} must be unique")


def check_source_lock() -> None:
    data = read_json(ROOT / "launch/source-lock.v3.json")
    require(data["schema"] == "hearthline-plays.arc3-launch-source-lock.v3", "source lock schema")
    require(data["status"] == "OFFLINE_CANDIDATE_PREPARATION_NO_EFFECT_AUTHORITY", "source lock status")
    repos = data["official_software"]
    unique([row["repository"] for row in repos], "official_software.repository")
    starter = next(row for row in repos if row["repository"] == "arcprize/ARC-AGI-3-Kaggle-Starter")
    require(starter["upstream_file_vendored"] is False, "official starter file must not be vendored")
    require(starter["interoperability_literals_reexpressed"] is True, "starter interface provenance")
    require(starter["license_or_notice_file_observed_at_pin"] is False, "starter license observation")
    require(
        all(
            row.get("bytes_copied") is False
            for row in repos
            if row is not starter
            and row.get("repository") != "arcprize/ARC-AGI-3-Agents"
        ),
        "non-Agents official source bytes must not be copied",
    )
    identities = {row["repository"]: row["commit"] for row in repos}
    require(identities["arcprize/ARC-AGI-3-Kaggle-Starter"] == "eeb1535404f321d280a8f9194bbc1d7aca5f05fc", "starter commit")
    require(identities["arcprize/ARC-AGI-3-Agents"] == "4743e7d0aaae0ded0d98a89a7e282e63564cd58b", "Agents commit")
    require(identities["arcprize/arc-agi-3-benchmarking"] == "1aa78da7e3058e0ead572ede7cd97065d1e5befc", "benchmark commit")
    require(identities["Kaggle/kaggle-api"] == "659469c4185cfca0fb3be01edad6f50277528d9d", "Kaggle CLI commit")
    agents = next(row for row in repos if row["repository"] == "arcprize/ARC-AGI-3-Agents")
    require(
        {path: binding["sha256"] for path, binding in agents["inspected_file_bindings"].items()}
        == {
            "agents/agent.py": "49f1a349cd5e2123fceb266aec4a3a758d18ef5520e0212e808f695905d9e073",
            "agents/recorder.py": "0a08d89f4067a760012767c05d4406bd2bf409f426e29a1193106abfcbb696c8",
            "agents/swarm.py": "d9dc48f710f1b90a6552db0921293c7e89c8a925ed00a3faefa07ae19998ad39",
            "agents/tracing.py": "951ca56508c524504e116303f7c64f4eb5cf723c72cab892d4d1a3292b1cc51f",
            "main.py": "864254c750bbbd12a211f2d8aa1b1025d0609283f07dea4ede83722f2435301b",
        },
        "Agents controlling-file bindings",
    )
    require(
        agents["license_file_binding"] == {
            "path": "LICENSE",
            "git_blob": "d8e1cd42ac40338c6c76a8a6ac18eea0eaf95fbe",
            "sha256": "75c4276c506fd93082b38ad39f67ee97aa859574401ef978e701710c7a40af04",
            "spdx": "MIT",
            "copyright_notice": "Copyright (c) 2025 ARC Prize",
        },
        "Agents MIT license binding",
    )
    require("LICENSE" in agents["runtime_license_preservation"], "Agents runtime license preservation")
    require(agents.get("bytes_copied") is True, "Agents test fixture copy must be disclosed")
    require(
        (ROOT / ".gitattributes").read_text(encoding="utf-8")
        == "tests/fixtures/*.blob -text\n",
        "Agents binary fixture line-ending policy",
    )
    fixture = agents.get("repository_fixture")
    require(
        fixture == {
            "path": "tests/fixtures/agents-main-4743e7d0.blob",
            "sha256": "864254c750bbbd12a211f2d8aa1b1025d0609283f07dea4ede83722f2435301b",
            "upstream_git_blob": "4a071bc3a4ce1dab94f754a617e5c1e70d9f907b",
            "purpose": "non-executable exact-byte fixture for offline Git-blob/SHA-256 pairing regression only",
            "license_copy": "tests/fixtures/ARC-AGI-3-Agents-LICENSE.txt",
            "license_copy_sha256": "cd95f6fb04cbe8f172890cf3746bb57295d131eb110bb78c1a0a528ea8acf87d",
            "license_copy_note": "MIT license text with one terminal POSIX newline",
        },
        "Agents exact-byte fixture disclosure",
    )
    fixture_bytes = (ROOT / fixture["path"]).read_bytes()
    require(sha256(ROOT / fixture["path"]) == fixture["sha256"], "Agents fixture SHA-256")
    framed = b"blob " + str(len(fixture_bytes)).encode("ascii") + b"\0" + fixture_bytes
    require(hashlib.sha1(framed).hexdigest() == fixture["upstream_git_blob"], "Agents fixture Git blob")
    require(
        sha256(ROOT / fixture["license_copy"]) == fixture["license_copy_sha256"],
        "Agents fixture license copy",
    )
    context = {row["source_id"]: row for row in data["bounded_context_sources"]}
    for source_id in ("fbt-synthesis-v0.1", "gold-v0.1"):
        require(
            context[source_id]["registry_commit"] == "f78e95a02fea16a7bd23ac01acbff4040a01bcd6",
            f"{source_id}: public registry commit",
        )
        require(
            context[source_id]["registry_blob"] == "bd6fa84302d53ea5ae54e5e7ac4bdc3ed8162ed9",
            f"{source_id}: public registry blob",
        )
    competition = data["competition_contract"]
    require(competition["authoritative_safe_assumption"]["submissions_per_day"] == 1, "one submission per day")
    require(competition["authoritative_safe_assumption"]["final_submissions"] == 2, "two final submissions")
    dependency = data["dependency_resolution"]
    require(
        dependency["runtime_closure_status"]
        == "UNFROZEN_PENDING_GATE_A_SUCCESSOR",
        "Gate B runtime closure must remain explicitly unfrozen",
    )
    require(
        dependency["current_blocker"].startswith("RUNTIME_CLOSURE_UNFROZEN:"),
        "Gate B runtime closure blocker",
    )
    require(
        "FROZEN_POST_STAGE_SUCCESSOR" in dependency["successor_requirement"],
        "Gate B successor requirement",
    )
    rules = data["run_rules"]
    require(rules["offline_by_default"] is True, "offline default")
    require(rules["credential_use_authorized"] is False, "credentials must be forbidden")
    require(rules["paid_provider_calls_authorized"] is False, "paid providers must be forbidden")
    require(rules["competition_mode_authorized"] is False, "competition mode forbidden")
    require(rules["kaggle_contact_authorized"] is False, "Kaggle contact forbidden")
    require(rules["automatic_push_or_submit_permitted"] is False, "automatic push/submit forbidden")


def check_status() -> None:
    legacy = ROOT / "launch/status.json"
    require(
        sha256(legacy) == "21e907e181d24fda6e392a2d6ed5209f033d2b2383396d3c5edb8944e6963adb",
        "legacy status bytes changed",
    )
    data = read_json(ROOT / "launch/status/current.json")
    require(data["schema"] == "hearthline-plays.arc3-launch-status.v2", "current status schema")
    require(data["competition"]["kaggle_contact_count"] == 0, "Kaggle count must remain zero")
    require(data["competition"]["kaggle_stage_authorized"] is False, "Kaggle stage must default closed")
    require(data["competition"]["competition_ignition_authorized"] is False, "competition ignition must default closed")
    require(data["competition"]["private_holdout_access"] is False, "private holdout must remain false")
    require(data["competition"]["paid_provider_calls"] == 0, "paid provider calls must remain zero")
    require(data["public_orientation"]["new_contact_authorized"] is False, "public replay must remain closed")
    require(data["public_orientation"]["automatic_trigger_enabled"] is False, "automatic replay trigger forbidden")
    candidate = data["candidate"]
    require(candidate["repo_prepared"] is True, "candidate source preparation")
    require(candidate["context_profile"] == "A0_MINIMAL", "candidate context must default minimal")
    require(candidate["generated_artifacts_tracked"] is False, "generated candidate must remain ignored")
    require(candidate["human_gate_a"] == candidate["human_gate_b"] == "CLOSED", "human gates must default closed")


def check_schemas_and_templates() -> None:
    schema_paths = sorted((ROOT / "schemas").glob("*.json"))
    schema_paths += sorted((ROOT / "launch/schemas").glob("**/*.json"))
    for path in schema_paths:
        data = read_json(path)
        require(data.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"{path}: draft")
        require(isinstance(data.get("$id"), str), f"{path}: id")
    expected = {
        "templates/spark-a.static.json": "hearthline.spark-static.v1",
        "templates/spark-b.static.json": "hearthline.spark-static.v1",
        "templates/pair.static.json": "hearthline.pair-static.v1",
        "templates/world-model.json": "hearthline.arc3-world-model.v1",
        "templates/action-plan.json": "hearthline.arc3-action-plan.v1",
        "practice/ls20/world-model.json": "hearthline.arc3-world-model.v1",
        "practice/ls20/action-plan.json": "hearthline.arc3-action-plan.v1",
        "launch/templates/v2/spark-static.blank.json": "hearthline.arc3.spark-static.v2",
        "practice/ls20/world-model.v2.json": "hearthline.arc3.world-model.v2",
    }
    for rel, schema in expected.items():
        data = read_json(ROOT / rel)
        require(data.get("schema") == schema, f"{rel}: wrong schema")


def check_requests() -> None:
    req_dir = ROOT / "practice/requests"
    if not req_dir.exists():
        return
    ids = []
    for path in sorted(req_dir.glob("*.json")):
        data = read_json(path)
        require(data.get("schema") == "hearthline.arc3-orientation-request.v1", f"{path}: schema")
        rid = data.get("request_id")
        require(isinstance(rid, str) and rid.startswith("ORIENT-"), f"{path}: request_id")
        ids.append(rid)
        require(data.get("mode") == "PUBLIC_ORIENTATION", f"{path}: mode")
        require(data.get("status") == "AUTHORIZED", f"{path}: preserved historical status")
        require(data.get("grant_ref") == "launch/RUN_GRANT_2026-09-03.md", f"{path}: historical grant reference")
        require(rid in {f"ORIENT-{index:04d}" for index in range(1, 6)}, f"{path}: request is outside the closed archive")
        require(data.get("game_id") in {"ls20", "ft09", "vc33"}, f"{path}: public game")
        require(data.get("close_scorecard") is True, f"{path}: scorecard must close")
        actions = data.get("actions")
        require(isinstance(actions, list), f"{path}: actions")
        max_actions = data.get("max_actions")
        require(type(max_actions) is int and len(actions) <= max_actions <= 64, f"{path}: action bound")
        for action in actions:
            require(action.get("action") in {f"ACTION{i}" for i in range(1, 8)}, f"{path}: action")
            require(len(action.get("hypothesis", "")) <= 400, f"{path}: hypothesis too long")
            require(len(action.get("expected_observable", "")) <= 400, f"{path}: expected too long")
    unique(ids, "request IDs")
    require(set(ids) == {f"ORIENT-{index:04d}" for index in range(1, 6)}, "closed orientation archive inventory")
    readme = (ROOT / "practice/README.md").read_text(encoding="utf-8")
    require("EXPIRED, SPENT, AND NON-EXECUTABLE" in readme, "practice archive retirement banner")
    require("They are not replayable instructions" in readme, "practice requests must not be presented as live")


def check_workflow_boundary() -> None:
    path = ROOT / ".github/workflows/arc3-orientation-probe.yml"
    text = path.read_text(encoding="utf-8")
    for required in (
        "workflow_dispatch:",
        "permissions:",
        "contents: read",
        "test_reconciliation.py",
        "hearthline-repository-guard.py",
        '--root "$GITHUB_WORKSPACE"',
    ):
        require(required in text, f"workflow missing {required!r}")
    for forbidden in ("push:", "arc3_replay_probe.py", "pip install", "three.arcprize.org"):
        require(forbidden not in text, f"workflow contains forbidden token {forbidden!r}")


def check_reconciliation() -> None:
    index = read_json(ROOT / "launch/receipts/20260904T070000Z-orientation-reconciliation.v2.json")
    receipts = []
    for binding in index["admitted_receipts"]:
        path = ROOT / binding["path"]
        require(sha256(path) == binding["sha256"], f"admitted receipt hash: {path}")
        receipts.append(read_json(path))
    totals = index["verified_totals"]
    require(len(receipts) == totals["public_arc_contacts"] == 5, "reconciled public contacts")
    require(sum(row["admitted_execution"]["observed_environment_actions"] for row in receipts) == totals["observed_environment_actions"] == 27, "reconciled action total")
    require(sum(row["admitted_execution"]["captured_frame_records"] for row in receipts) == totals["captured_frame_records"] == 36, "reconciled frame total")
    require(all(row["admitted_execution"]["competition_mode"] is False for row in receipts), "orientation must be non-competition")


def check_candidate_surface() -> None:
    agent_path = ROOT / "agent/my_agent.py"
    source = agent_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(agent_path))
    imports = set()
    classes = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = node
    require(not imports & {"os", "subprocess", "socket", "requests", "urllib", "kaggle"}, "agent effect-capable import")
    require("MyAgent" in classes, "MyAgent missing")
    methods = {node.name for node in classes["MyAgent"].body if isinstance(node, ast.FunctionDef)}
    require({"is_done", "choose_action"} <= methods, "official Agent methods missing")

    metadata = read_json(ROOT / "notebooks/kernel-metadata.template.json")
    require(set(metadata) == {
        "id", "title", "code_file", "language", "kernel_type", "is_private",
        "enable_gpu", "enable_tpu", "enable_internet", "keywords",
        "dataset_sources", "kernel_sources", "competition_sources", "model_sources",
    }, "kernel template fields")
    require(metadata["code_file"] == "submission.ipynb", "kernel template code file")
    require(metadata["is_private"] is True, "kernel template private")
    require(metadata["enable_internet"] is False, "kernel template offline")
    require(metadata["dataset_sources"] == metadata["kernel_sources"] == metadata["model_sources"] == [], "kernel template extra sources")
    require(metadata["competition_sources"] == ["arc-prize-2026-arc-agi-3"], "kernel competition source")

    contract = read_json(ROOT / "launch/contracts/official-starter-eeb153.contract.json")
    lock = read_json(ROOT / "launch/source-lock.v3.json")
    starter = next(row for row in lock["official_software"] if row["repository"] == "arcprize/ARC-AGI-3-Kaggle-Starter")
    require(contract["source"]["commit"] == starter["commit"], "starter contract commit")
    require(
        contract["source"]["build_script_sha256"]
        == starter["inspected_file_bindings"]["scripts/build_notebook.py"]["sha256"],
        "starter contract script hash",
    )
    require(contract["projection"]["install"]["packages"] == ["arc-agi", "python-dotenv"], "starter package projection")
    require(contract["source"]["license_observation"].startswith("No LICENSE or NOTICE"), "starter license observation")

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    for forbidden in ("kaggle kernels", "kaggle competitions", "curl ", "KAGGLE_API_TOKEN", ".kaggle/access_token"):
        require(forbidden not in makefile, f"Makefile external-effect surface: {forbidden}")
    gate_source = (ROOT / "scripts/verify_human_gate.py").read_text(encoding="utf-8")
    for forbidden in ("import requests", "import webbrowser", "kaggle kernels"):
        require(forbidden not in gate_source, f"gate effect surface: {forbidden}")
    for required in (
        "grant_id is already consumed",
        "grant nonce is already consumed",
        "os.rename",
        "_assert_gate_seal(result)",
        "sealed Gate A parent missing or duplicated under ledger lock",
        "verify_current_candidate(args.build_dir)",
        "runtime inventory must be complete",
        "a Gate B grant was already consumed on this UTC day",
        "GIT_NO_REPLACE_OBJECTS",
        "worktree candidate verifier differs from committed Git object",
        "Git identity changed during candidate verification",
        "candidate verification result differs from the bound Git identity",
        "Local procedural gate consumed",
    ):
        require(required in gate_source, f"gate single-use surface missing: {required}")
    require(not (ROOT / "tools/arc3_replay_probe.py").exists(), "legacy replay broker must be absent")
    archive_guard = (ROOT / "tools/orientation_archive_guard.py").read_text(encoding="utf-8")
    require("CLOSED_EXPIRED_AND_SPENT" in archive_guard, "orientation archive closure guard")
    require("import arc_agi" not in archive_guard, "archive guard must have no ARC adapter")

    stage = read_json(ROOT / "launch/gates/kaggle-stage-grant.v2.template.json")
    competition = read_json(ROOT / "launch/gates/competition-ignition-grant.v2.template.json")
    require(stage["rules"]["submissions_per_day"] == 1, "Gate A daily limit")
    require(competition["rules"]["submissions_per_day"] == 1, "Gate B daily limit")
    require(stage["schema"] == competition["schema"] == "hearthline.arc3.human-grant.v3", "gate template schema")
    require(competition["acknowledgements"]["account_slug"] == "REPLACE_FROM_CONSUMED_GATE_A", "Gate B account binding")
    require(stage["human_actor"]["attested_by_human"] is False, "Gate A template must not self-attest")
    require(competition["human_actor"]["attested_by_human"] is False, "Gate B template must not self-attest")


def check_protected_history() -> None:
    expected = {
        "launch/FOUNDER_SENDOFF.md": "c5edc23c8f8d9affb84924088b92d22d5914a1e2be98d036e3c79390edd036cc",
        "launch/status.json": "21e907e181d24fda6e392a2d6ed5209f033d2b2383396d3c5edb8944e6963adb",
        "launch/receipts/20260904T001827Z-pre-astra-lineage-seal.json": "375aa8b834a5b17fb1dc5e74883160b1266a441df86aa6c385a076a8434cec8f",
        "launch/receipts/20260904T001827Z-pre-astra-lineage-seal.md": "6951e2b75460927ea3fec5f53eddcd32847e75bd7b3728ec8f7db4dc99ce45d1",
    }
    for relative, digest in expected.items():
        require(sha256(ROOT / relative) == digest, f"protected history changed: {relative}")
    grant = (ROOT / "launch/RUN_GRANT_2026-09-03.md").read_bytes()
    marker = "# Run grant — public ARC-AGI-3 orientation, 3 September 2026\n".encode("utf-8")
    require(grant.startswith(b"> **Present-day status (4 September 2026): EXPIRED, SPENT, ARCHIVE-ONLY.**"), "historical grant retirement banner")
    require(marker in grant, "historical grant body marker")
    historical_body = grant[grant.index(marker):]
    require(
        hashlib.sha256(historical_body).hexdigest()
        == "4cbd09a55ecb18c6a3c571ed54ab94f8fee1c2c52ba57c99867e6930822e08d8",
        "historical run grant body changed",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    checks = [
        check_source_lock,
        check_status,
        check_schemas_and_templates,
        check_requests,
        check_workflow_boundary,
        check_reconciliation,
        check_candidate_surface,
        check_protected_history,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    print("LAUNCHPAD_CONFORMANT")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"FAIL {exc}")
        raise SystemExit(1)
