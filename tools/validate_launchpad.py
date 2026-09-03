#!/usr/bin/env python3
"""Fail-closed, standard-library checks for the Hearthline ARC launchpad."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class ValidationError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{path}: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def unique(values: list[Any], label: str) -> None:
    require(len(values) == len(set(values)), f"{label} must be unique")


def check_source_lock() -> None:
    data = read_json(ROOT / "launch/source-lock.v2.json")
    require(data["schema"] == "hearthline-plays.arc3-launch-source-lock.v2", "source lock schema")
    require(data["status"] == "PUBLIC_ORIENTATION_AUTHORIZED", "source lock status")
    repos = data["repo_views"]
    unique([row["repository"] for row in repos], "repo_views.repository")
    require(all(row["bytes_copied"] is False for row in repos), "repo source bytes must not be copied")
    rules = data["run_rules"]
    require(rules["public_games_only"] is True, "public games only")
    require(rules["credentials_permitted"] is False, "credentials must be forbidden")
    require(rules["paid_provider_calls_permitted"] is False, "paid providers must be forbidden")
    require(rules["competition_mode_permitted"] is False, "competition mode forbidden")
    require(rules["kaggle_contact_permitted"] is False, "Kaggle contact forbidden")
    require(rules["automatic_action_selection_by_workflow"] is False, "workflow may not choose actions")


def check_status() -> None:
    data = read_json(ROOT / "launch/status.json")
    require(data["schema"] == "hearthline-plays.arc3-launch-status.v1", "status schema")
    require(data["kaggle_contact_count"] == 0, "Kaggle count must remain zero")
    require(data["competition_mode"] is False, "competition mode must remain false")
    require(data["private_holdout_access"] is False, "private holdout must remain false")
    require(data["paid_provider_calls"] == 0, "paid provider calls must remain zero")


def check_schemas_and_templates() -> None:
    for path in sorted((ROOT / "schemas").glob("*.json")):
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
        require(data.get("game_id") in {"ls20", "ft09", "vc33"}, f"{path}: public game")
        require(data.get("close_scorecard") is True, f"{path}: scorecard must close")
        actions = data.get("actions")
        require(isinstance(actions, list), f"{path}: actions")
        require(len(actions) <= data.get("max_actions", -1) <= 64, f"{path}: action bound")
        for action in actions:
            require(action.get("action") in {f"ACTION{i}" for i in range(1, 8)}, f"{path}: action")
            require(len(action.get("hypothesis", "")) <= 400, f"{path}: hypothesis too long")
            require(len(action.get("expected_observable", "")) <= 400, f"{path}: expected too long")
    unique(ids, "request IDs")


def check_workflow_boundary() -> None:
    path = ROOT / ".github/workflows/arc3-orientation-probe.yml"
    text = path.read_text(encoding="utf-8")
    for required in (
        "f12822c4d550121c35a275008d964afbbed47d2f",
        "permissions:",
        "contents: read",
        "practice/requests/",
        "tools/arc3_replay_probe.py",
    ):
        require(required in text, f"workflow missing {required!r}")
    for forbidden in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "KAGGLE", "competition"):
        require(forbidden not in text, f"workflow contains forbidden token {forbidden!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    checks = [check_source_lock, check_status, check_schemas_and_templates, check_requests, check_workflow_boundary]
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
