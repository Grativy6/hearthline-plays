from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "verify_station.py"
SPEC = importlib.util.spec_from_file_location("verify_station", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import setup guard
    raise RuntimeError("unable to load station verifier")
verify_station = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_station)


class StationVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = verify_station.load_strict_json(ROOT / "research" / "sources.lock.json")
        cls.source_ids = [source["source_id"] for source in cls.sources["sources"]]
        cls.creature = verify_station.load_strict_json(
            ROOT / "fixtures" / "creature-manifest.synthetic.json"
        )
        cls.objective_window = verify_station.load_strict_json(
            ROOT / "fixtures" / "objective-window.synthetic.json"
        )

    def test_complete_station_passes_offline_verifier(self) -> None:
        report = verify_station.verify_station(ROOT)
        self.assertEqual("PASS", report["status"])
        self.assertEqual("PREPARED_NOT_RUN", report["station_status"])
        self.assertEqual(0, report["external_network_calls_performed_by_verifier"])
        self.assertEqual(0, report["arc_environment_calls"])
        self.assertEqual(0, report["holdout_consumption"])
        self.assertEqual(2, report["synthetic_fixture_count"])

    def test_duplicate_json_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(verify_station.VerificationError, "duplicate JSON key"):
            verify_station.loads_strict_json(
                '{"status":"PREPARED_NOT_RUN","status":"RUN"}'
            )

    def test_exponent_overflow_json_is_rejected(self) -> None:
        with self.assertRaisesRegex(verify_station.VerificationError, "non-finite JSON number"):
            verify_station.loads_strict_json('{"overflow":1e999}')

    def test_source_contact_boundary_is_immutable(self) -> None:
        document = copy.deepcopy(self.sources)
        document["rules"]["arc_or_kaggle_contacted"] = True
        with self.assertRaisesRegex(verify_station.VerificationError, "boundary rules"):
            verify_station.validate_sources(document)

    def test_source_digest_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.sources)
        document["sources"][0]["artifacts"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(verify_station.VerificationError, "artifact digest set"):
            verify_station.validate_sources(document)

    def test_creature_ledgers_and_homes_cannot_merge(self) -> None:
        document = copy.deepcopy(self.creature)
        document["members"][1]["ledger_ref"] = document["members"][0]["ledger_ref"]
        document["members"][1]["home_ref"] = document["members"][0]["home_ref"]
        with self.assertRaisesRegex(verify_station.VerificationError, "separate ledger_ref"):
            verify_station.validate_creature(document, self.source_ids)

    def test_ledger_scribe_has_no_action_or_authority_port(self) -> None:
        for field in ("action_port", "authority_port"):
            with self.subTest(field=field):
                document = copy.deepcopy(self.creature)
                document["members"][1][field] = True
                with self.assertRaisesRegex(verify_station.VerificationError, field):
                    verify_station.validate_creature(document, self.source_ids)

    def test_thulia_cannot_govern(self) -> None:
        document = copy.deepcopy(self.creature)
        document["thulia"]["governing"] = True
        with self.assertRaisesRegex(verify_station.VerificationError, "Thulia: governing"):
            verify_station.validate_creature(document, self.source_ids)

    def test_comparison_arms_require_separate_roots_and_ledgers(self) -> None:
        for field, message in (("lab_root_ref", "separate roots"), ("ledger_ref", "separate ledgers")):
            with self.subTest(field=field):
                document = copy.deepcopy(self.creature)
                document["comparison"]["arms"][1][field] = document["comparison"]["arms"][0][field]
                with self.assertRaisesRegex(verify_station.VerificationError, message):
                    verify_station.validate_creature(document, self.source_ids)

    def test_objective_events_cannot_borrow_another_grant(self) -> None:
        document = copy.deepcopy(self.objective_window)
        document["events"][4]["grant_ref"] = document["objectives"][1]["grant_ref"]
        with self.assertRaisesRegex(verify_station.VerificationError, "grant_ref scope bleed"):
            verify_station.validate_objective_window(document)

    def test_objective_lifecycle_receipts_cannot_duplicate(self) -> None:
        document = copy.deepcopy(self.objective_window)
        document["events"][5]["lifecycle_receipt_ref"] = document["events"][4]["lifecycle_receipt_ref"]
        with self.assertRaisesRegex(verify_station.VerificationError, "lifecycle receipts must be unique"):
            verify_station.validate_objective_window(document)

    def test_static_window_cannot_claim_an_external_effect(self) -> None:
        document = copy.deepcopy(self.objective_window)
        document["events"][4]["external_effect_receipt_ref"] = "SYNTHETIC_EFFECT_0001"
        with self.assertRaisesRegex(verify_station.VerificationError, "external effects must remain absent"):
            verify_station.validate_objective_window(document)

    def test_homecoming_custody_cannot_manufacture_task_status(self) -> None:
        document = copy.deepcopy(self.objective_window)
        document["objective_set"]["final_states"][0]["objective_disposition"] = "HOMECOMING:RECONCILED"
        with self.assertRaisesRegex(verify_station.VerificationError, "custody and rule-owned disposition"):
            verify_station.validate_objective_window(document)

    def test_aggregate_response_needs_explicit_objective_set_disposition(self) -> None:
        document = copy.deepcopy(self.objective_window)
        document["objective_set"]["all_objectives_explicitly_disposed"] = False
        with self.assertRaisesRegex(verify_station.VerificationError, "explicit disposition"):
            verify_station.validate_objective_window(document)


if __name__ == "__main__":
    unittest.main()
