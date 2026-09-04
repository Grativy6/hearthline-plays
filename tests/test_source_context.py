from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class SourceLockV3Tests(unittest.TestCase):
    def test_official_identities_and_live_safe_limit_are_frozen(self) -> None:
        lock = load("launch/source-lock.v3.json")
        commits = {row["repository"]: row["commit"] for row in lock["official_software"]}
        self.assertEqual(commits["arcprize/ARC-AGI-3-Kaggle-Starter"], "eeb1535404f321d280a8f9194bbc1d7aca5f05fc")
        self.assertEqual(commits["arcprize/ARC-AGI-3-Agents"], "4743e7d0aaae0ded0d98a89a7e282e63564cd58b")
        self.assertEqual(commits["arcprize/arc-agi-3-benchmarking"], "1aa78da7e3058e0ead572ede7cd97065d1e5befc")
        self.assertEqual(lock["competition_contract"]["authoritative_safe_assumption"]["submissions_per_day"], 1)
        self.assertTrue(lock["competition_contract"]["known_contradiction"]["starter_and_mirrored_docs_statement"].startswith("5 "))
        self.assertFalse(lock["credential_contract"]["credential_use_authorized"])
        self.assertEqual(
            lock["dependency_resolution"]["runtime_closure_status"],
            "UNFROZEN_PENDING_GATE_A_SUCCESSOR",
        )
        self.assertTrue(
            lock["dependency_resolution"]["current_blocker"].startswith(
                "RUNTIME_CLOSURE_UNFROZEN:"
            )
        )
        starter = next(
            row for row in lock["official_software"]
            if row["repository"] == "arcprize/ARC-AGI-3-Kaggle-Starter"
        )
        self.assertFalse(starter["upstream_file_vendored"])
        self.assertTrue(starter["interoperability_literals_reexpressed"])
        self.assertFalse(starter["license_or_notice_file_observed_at_pin"])
        agents = next(
            row for row in lock["official_software"]
            if row["repository"] == "arcprize/ARC-AGI-3-Agents"
        )
        self.assertEqual(
            agents["inspected_file_bindings"],
            {
                "agents/agent.py": {
                    "git_blob": "50e3a03652226d2775779bfba90bc745256a44c5",
                    "sha256": "49f1a349cd5e2123fceb266aec4a3a758d18ef5520e0212e808f695905d9e073",
                },
                "agents/recorder.py": {
                    "git_blob": "0d06dc6c346f24311d4be995397555c8e3ab94d0",
                    "sha256": "0a08d89f4067a760012767c05d4406bd2bf409f426e29a1193106abfcbb696c8",
                },
                "agents/swarm.py": {
                    "git_blob": "bb3a376220f636099dd910653db3e1918935f30f",
                    "sha256": "d9dc48f710f1b90a6552db0921293c7e89c8a925ed00a3faefa07ae19998ad39",
                },
                "agents/tracing.py": {
                    "git_blob": "60d13f489ad1a3fa04dc9ff7c8ee6f0f35a175f7",
                    "sha256": "951ca56508c524504e116303f7c64f4eb5cf723c72cab892d4d1a3292b1cc51f",
                },
                "main.py": {
                    "git_blob": "4a071bc3a4ce1dab94f754a617e5c1e70d9f907b",
                    "sha256": "864254c750bbbd12a211f2d8aa1b1025d0609283f07dea4ede83722f2435301b",
                },
            },
        )
        self.assertEqual(
            agents["license_file_binding"],
            {
                "path": "LICENSE",
                "git_blob": "d8e1cd42ac40338c6c76a8a6ac18eea0eaf95fbe",
                "sha256": "75c4276c506fd93082b38ad39f67ee97aa859574401ef978e701710c7a40af04",
                "spdx": "MIT",
                "copyright_notice": "Copyright (c) 2025 ARC Prize",
            },
        )
        self.assertIn("LICENSE", agents["runtime_license_preservation"])
        fixture_binding = agents["repository_fixture"]
        self.assertEqual(
            (ROOT / ".gitattributes").read_text(encoding="utf-8"),
            "tests/fixtures/*.blob -text\n",
        )
        fixture = (ROOT / fixture_binding["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(fixture).hexdigest(), fixture_binding["sha256"])
        framed = b"blob " + str(len(fixture)).encode("ascii") + b"\0" + fixture
        self.assertEqual(hashlib.sha1(framed).hexdigest(), fixture_binding["upstream_git_blob"])
        self.assertEqual(
            agents["inspected_file_bindings"]["main.py"],
            {
                "git_blob": fixture_binding["upstream_git_blob"],
                "sha256": fixture_binding["sha256"],
            },
        )
        self.assertNotEqual(
            hashlib.sha256(fixture.replace(b"\n", b"\r\n")).hexdigest(),
            fixture_binding["sha256"],
        )
        self.assertEqual(
            hashlib.sha256((ROOT / fixture_binding["license_copy"]).read_bytes()).hexdigest(),
            fixture_binding["license_copy_sha256"],
        )

    def test_context_roles_default_off_and_profiles_are_exact_ablations(self) -> None:
        context = load("launch/context/roles.v2.json")
        roles = {row["role_id"] for row in context["roles"]}
        self.assertEqual(len(roles), 8)
        self.assertTrue(all(not row["default_enabled"] for row in context["roles"]))
        full = set(context["frozen_profiles"]["A0_FULL"])
        self.assertEqual(full, roles)
        self.assertEqual(full - set(context["frozen_profiles"]["A0_NO_A0BK"]), {"A0BK_ADVISORY_GATE"})
        self.assertEqual(full - set(context["frozen_profiles"]["A0_NO_FBT_CONTINUATION"]), {"FBT_CONTINUATION_SPLIT"})
        self.assertEqual(full - set(context["frozen_profiles"]["A0_NO_GOLD"]), {"GOLD_1_PLUS_5_LENS"})
        self.assertFalse(context["common_safety_shell"]["ablatable"])


if __name__ == "__main__":
    unittest.main()
