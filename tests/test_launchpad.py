from __future__ import annotations

import importlib.util
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PAIR = load_module("pair_static", "tools/pair_static.py")
ARCHIVE_GUARD = load_module("orientation_archive_guard", "tools/orientation_archive_guard.py")
VALIDATE = load_module("validate_launchpad", "tools/validate_launchpad.py")


class PairStaticTests(unittest.TestCase):
    def test_disagreement_retained_without_average(self):
        a = json.loads((ROOT / "templates/spark-a.static.json").read_text())
        b = json.loads((ROOT / "templates/spark-b.static.json").read_text())
        a.update(static_id="A", task_id="T", dependencies=["same-model"])
        b.update(static_id="B", task_id="T", dependencies=["same-model"])
        a["claims"] = [{
            "claim_id":"goal","kind":"HYPOTHESIS","value":"red",
            "confidence":0.7,"evidence_refs":["f0"],"assumptions":["color causal"]
        }]
        b["claims"] = [{
            "claim_id":"goal","kind":"HYPOTHESIS","value":"blue",
            "confidence":0.4,"evidence_refs":["f0"],"assumptions":["shape causal"]
        }]
        result = PAIR.build_pair(a, b, "P")
        self.assertEqual(result["pooling_rule"], "NONE")
        self.assertEqual(result["load_bearing_seam"], "goal")
        self.assertEqual(len(result["disagreements"]), 1)
        self.assertIn("same-model", result["shared_dependencies"])

    def test_task_mismatch_fails(self):
        a = json.loads((ROOT / "templates/spark-a.static.json").read_text())
        b = json.loads((ROOT / "templates/spark-b.static.json").read_text())
        a.update(static_id="A", task_id="T1")
        b.update(static_id="B", task_id="T2")
        with self.assertRaises(ValueError):
            PAIR.build_pair(a, b, "P")


class OrientationArchiveClosureTests(unittest.TestCase):
    def test_all_five_archived_requests_reject_before_adapter(self):
        calls = []

        def trap(_: dict) -> None:
            calls.append("CONTACT")
            raise AssertionError("effect adapter must never run")

        for index in range(1, 6):
            path = ROOT / f"practice/requests/ORIENT-{index:04d}.json"
            with self.assertRaisesRegex(
                ARCHIVE_GUARD.ClosedOrientationArchive,
                "CLOSED_EXPIRED_AND_SPENT",
            ):
                ARCHIVE_GUARD.reject_archived_request(path, trap)
        self.assertEqual(calls, [])

    def test_active_replay_broker_is_absent(self):
        self.assertFalse((ROOT / "tools/arc3_replay_probe.py").exists())
        source = (ROOT / "tools/orientation_archive_guard.py").read_text(encoding="utf-8")
        for forbidden in ("import arc_agi", "urllib", "requests", "socket", "subprocess"):
            self.assertNotIn(forbidden, source)

    def test_exponent_overflow_is_rejected_by_active_json_boundaries(self):
        path = ROOT / "tests/.overflow-archive.json"
        path.write_bytes(b'{"request_id":"ORIENT-0001","overflow":1e999}')
        try:
            with self.assertRaisesRegex(
                ARCHIVE_GUARD.ClosedOrientationArchive,
                "non-finite JSON number",
            ):
                ARCHIVE_GUARD.reject_archived_request(path)
            with self.assertRaisesRegex(VALIDATE.ValidationError, "non-finite JSON number"):
                VALIDATE.read_json(path)
        finally:
            path.unlink(missing_ok=True)

    def test_historical_authority_is_bannered_and_body_is_preserved(self):
        grant = (ROOT / "launch/RUN_GRANT_2026-09-03.md").read_bytes()
        self.assertTrue(grant.startswith(
            b"> **Present-day status (4 September 2026): EXPIRED, SPENT, ARCHIVE-ONLY.**"
        ))
        marker = "# Run grant — public ARC-AGI-3 orientation, 3 September 2026\n".encode()
        body = grant[grant.index(marker):]
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "4cbd09a55ecb18c6a3c571ed54ab94f8fee1c2c52ba57c99867e6930822e08d8",
        )
        practice = (ROOT / "practice/README.md").read_text(encoding="utf-8")
        self.assertIn("EXPIRED, SPENT, AND NON-EXECUTABLE", practice)
        self.assertIn("They are not replayable instructions", practice)


if __name__ == "__main__":
    unittest.main()
