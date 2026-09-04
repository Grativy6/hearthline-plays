from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


class ProtectedHistoryTests(unittest.TestCase):
    EXPECTED = {
        "launch/FOUNDER_SENDOFF.md": "c5edc23c8f8d9affb84924088b92d22d5914a1e2be98d036e3c79390edd036cc",
        "launch/status.json": "21e907e181d24fda6e392a2d6ed5209f033d2b2383396d3c5edb8944e6963adb",
        "launch/receipts/20260904T001827Z-pre-astra-lineage-seal.json": "375aa8b834a5b17fb1dc5e74883160b1266a441df86aa6c385a076a8434cec8f",
        "launch/receipts/20260904T001827Z-pre-astra-lineage-seal.md": "6951e2b75460927ea3fec5f53eddcd32847e75bd7b3728ec8f7db4dc99ce45d1",
    }

    def test_protected_bytes_are_unchanged(self) -> None:
        for path, expected in self.EXPECTED.items():
            with self.subTest(path=path):
                self.assertEqual(sha256(path), expected)


class ReconciliationTests(unittest.TestCase):
    def test_index_binds_exact_admitted_receipts(self) -> None:
        index = load_json(
            "launch/receipts/20260904T070000Z-orientation-reconciliation.v2.json"
        )
        receipts = []
        for binding in index["admitted_receipts"]:
            self.assertEqual(sha256(binding["path"]), binding["sha256"])
            receipts.append(load_json(binding["path"]))

        self.assertEqual(sum(r["admitted_execution"]["observed_environment_actions"] for r in receipts), 27)
        self.assertEqual(sum(r["admitted_execution"]["captured_frame_records"] for r in receipts), 36)
        self.assertEqual(sum(bool(r["admitted_execution"]["scorecard_close_returned_record"]) for r in receipts), 5)
        self.assertEqual(max(r["admitted_execution"]["scorecard_total_levels_completed"] for r in receipts), 1)
        self.assertEqual(index["verified_totals"]["public_arc_contacts"], len(receipts))

    def test_status_is_fail_closed(self) -> None:
        status = load_json("launch/status/current.json")
        self.assertFalse(status["competition"]["kaggle_stage_authorized"])
        self.assertFalse(status["competition"]["competition_ignition_authorized"])
        self.assertFalse(status["public_orientation"]["new_contact_authorized"])
        self.assertEqual(status["public_orientation"]["observed_environment_action_count"], 27)
        self.assertEqual(status["competition"]["daily_submission_limit_safe_assumption"], 1)

    def test_world_model_keeps_hypotheses_unpromoted(self) -> None:
        model = load_json("practice/ls20/world-model.v2.json")
        self.assertEqual(model["world_model_id"], "LS20-WM-0001")
        self.assertEqual(model["observation_aperture"]["actions"], 27)
        self.assertTrue(all("HYPOTHESIS" in row["status"] or "NOT_IDENTIFIED" in row["status"] for row in model["hypotheses"]))
        self.assertEqual(model["action_model"]["ACTION2"]["status"], "NOT_OBSERVED")


if __name__ == "__main__":
    unittest.main()
