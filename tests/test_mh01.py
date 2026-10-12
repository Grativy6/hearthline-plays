"""Independent-replay tests; no model or network usage."""

from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy

from security_lab.mh01.demo import DEFAULT_FIXTURE, run
from security_lab.mh01.referee import MockReferee, canonical, load_fixture
from security_lab.mh01.verify import check


class MH01Tests(unittest.TestCase):
    def test_benign_completes_public_task(self):
        receipt = run("benign")
        self.assertEqual(check(receipt, DEFAULT_FIXTURE), [])
        self.assertEqual(receipt["final_state"]["submitted_status"], "GREEN")
        self.assertEqual([e["executed"] for e in receipt["events"]], [True, True])

    def test_tempted_attempts_are_recorded_not_executed(self):
        receipt = run("tempted")
        self.assertEqual(check(receipt, DEFAULT_FIXTURE), [])
        self.assertEqual([e["gate"]["decision"] for e in receipt["events"]], ["ALLOW", "DENY", "DENY", "ALLOW"])
        self.assertEqual([e["executed"] for e in receipt["events"]], [True, False, False, True])
        self.assertNotIn("SYNTHETIC PLACEHOLDER", json.dumps(receipt))

    def test_submission_without_source_read_is_denied(self):
        fixture, sha = load_fixture(DEFAULT_FIXTURE)
        judge = MockReferee(fixture, sha)
        result = judge.request("submit_status", {"status": "GREEN", "source": "bulletin-public"})
        self.assertEqual(result, {"error": "not-authorized"})
        self.assertEqual(check(judge.receipt("custom"), DEFAULT_FIXTURE), [])

    def test_unknown_action_fails_closed(self):
        fixture, sha = load_fixture(DEFAULT_FIXTURE)
        judge = MockReferee(fixture, sha)
        judge.request("read_system_files", {"path": "/tmp/other"})
        self.assertEqual(judge.events[0]["gate"]["decision"], "DENY")
        self.assertFalse(judge.events[0]["executed"])
        self.assertEqual(check(judge.receipt("custom"), DEFAULT_FIXTURE), [])

    def test_changed_result_fails_hash_check(self):
        receipt = run("tempted")
        receipt["events"][1]["result"] = {"leaked": True}
        self.assertTrue(any("hash" in e for e in check(receipt, DEFAULT_FIXTURE)))

    def test_forged_execution_detected_even_with_rehashed_chain(self):
        receipt = deepcopy(run("tempted"))
        target = receipt["events"][1]
        target["executed"] = True
        target["gate"] = {"decision": "ALLOW", "reason": "forged"}
        # Attacker knows how to recompute ALL hashes. Replay must still reject.
        previous = "0" * 64
        for event in receipt["events"]:
            event["previous_hash"] = previous
            event["hash"] = hashlib.sha256(canonical({k: v for k, v in event.items() if k != "hash"})).hexdigest()
            previous = event["hash"]
        receipt["head_hash"] = previous
        errors = check(receipt, DEFAULT_FIXTURE)
        self.assertTrue(any("execution claim" in e for e in errors))
        self.assertTrue(any("gate verdict" in e for e in errors))

    def test_fixture_mismatch_detected(self):
        receipt = run("benign")
        receipt["fixture_sha256"] = "f" * 64
        self.assertIn("fixture bytes mismatch", check(receipt, DEFAULT_FIXTURE))


if __name__ == "__main__":
    unittest.main()
