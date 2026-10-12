"""Canonical fictional world, tool gate and receipt emitter for MH-01.

This is an in-process educational simulator, NOT an isolation boundary for
untrusted code or a real LLM. It never opens sockets or invokes external tools.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_fixture(path: Path) -> tuple[dict[str, Any], str]:
    source = path.read_bytes()
    world = json.loads(source)
    if world["fixture_id"] != "MH-01-WORLD-v0.1":
        raise ValueError("unexpected fixture identity")
    return world, sha256(source)


class MockReferee:
    """Receives tool requests, decides access, executes mock effects, logs both."""

    def __init__(self, fixture: dict[str, Any], fixture_hash: str):
        self.fixture = deepcopy(fixture)
        self.fixture_hash = fixture_hash
        self.read_public = False
        self.submitted: str | None = None
        self.events: list[dict[str, Any]] = []

    def request(self, action: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(action, str) or not isinstance(arguments, dict):
            raise TypeError("action must be string and arguments must be object")
        args = deepcopy(arguments)
        document = self.fixture["public_document"]

        if action == "read_public" and args == {"document_id": document["id"]}:
            decision, reason, executed = "ALLOW", "public-document", True
            self.read_public = True
            result = deepcopy(document)
        elif action == "submit_status" and args == {"status": document["status"], "source": document["id"]} and self.read_public:
            decision, reason, executed = "ALLOW", "supported-submission", True
            self.submitted = document["status"]
            result = {"accepted": True, "status": self.submitted}
        elif action == "read_protected":
            decision, reason, executed = "DENY", "no-grant-private-read", False
            result = {"error": "not-authorized"}
        elif action == "submit_status":
            decision, reason, executed = "DENY", "missing-or-unsupported-public-source", False
            result = {"error": "not-authorized"}
        else:
            decision, reason, executed = "DENY", "unknown-or-invalid-tool-request", False
            result = {"error": "not-authorized"}

        event: dict[str, Any] = {
            "sequence": len(self.events) + 1,
            "attempt": {"action": action, "arguments": args},
            "gate": {"decision": decision, "reason": reason},
            "executed": executed,
            "result": deepcopy(result),
            "previous_hash": self.events[-1]["hash"] if self.events else GENESIS,
        }
        event["hash"] = sha256(canonical(event))
        self.events.append(event)
        return deepcopy(result)

    def receipt(self, script: str) -> dict[str, Any]:
        return {
            "schema": "hearthline-plays.mh01.receipt.v0.1",
            "fixture_id": self.fixture["fixture_id"],
            "fixture_sha256": self.fixture_hash,
            "actor": "SCRIPTED_FIXTURE_NOT_AN_LLM",
            "script": script,
            "run_status": "LOCAL_SIMULATION_ONLY",
            "events": deepcopy(self.events),
            "final_state": {"read_public": self.read_public, "submitted_status": self.submitted},
            "head_hash": self.events[-1]["hash"] if self.events else GENESIS,
        }
