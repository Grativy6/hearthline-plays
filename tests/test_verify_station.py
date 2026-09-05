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
        cls.return_queue = verify_station.load_strict_json(
            ROOT / "fixtures" / "return-queue.synthetic.json"
        )

    def test_complete_station_passes_offline_verifier(self) -> None:
        report = verify_station.verify_station(ROOT)
        self.assertEqual("PASS", report["status"])
        self.assertEqual("PREPARED_NOT_RUN", report["station_status"])
        self.assertEqual(0, report["external_network_calls_performed_by_verifier"])
        self.assertEqual(0, report["arc_environment_calls"])
        self.assertEqual(0, report["holdout_consumption"])
        self.assertEqual(3, report["synthetic_fixture_count"])

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

    def test_complete_homecoming_return_queue_passes(self) -> None:
        verify_station.validate_return_queue(copy.deepcopy(self.return_queue))

    def test_batch_and_lone_returns_use_one_linearized_intake_path(self) -> None:
        first = {
            "queue_item_id": "queue-item-a",
            "return_id": "return-a",
            "idempotency_key": "intake-key-a",
            "intake_receipt_ref": "intake-receipt-a",
            "enqueue_receipt_ref": "enqueue-receipt-a",
            "return_receipt_ref": "return-receipt-a",
        }
        second = {
            "queue_item_id": "queue-item-b",
            "return_id": "return-b",
            "idempotency_key": "intake-key-b",
            "intake_receipt_ref": "intake-receipt-b",
            "enqueue_receipt_ref": "enqueue-receipt-b",
            "return_receipt_ref": "return-receipt-b",
        }
        batch = verify_station.linearize_return_intake([], [first, second])
        self.assertEqual(["queue-item-a", "queue-item-b"], [item["queue_item_id"] for item in batch])
        self.assertEqual([1, 2], [item["arrival_ordinal"] for item in batch])
        lone = verify_station.linearize_return_intake([], [first])
        self.assertEqual([{**first, "arrival_ordinal": 1}], lone)

    def test_return_intake_is_idempotent_but_rejects_identity_conflict(self) -> None:
        arrival = {
            "queue_item_id": "queue-item-a",
            "return_id": "return-a",
            "idempotency_key": "intake-key-a",
            "intake_receipt_ref": "intake-receipt-a",
            "enqueue_receipt_ref": "enqueue-receipt-a",
            "return_receipt_ref": "return-receipt-a",
        }
        once = verify_station.linearize_return_intake([], [arrival])
        twice = verify_station.linearize_return_intake(once, [arrival])
        self.assertEqual(once, twice)
        conflict = {**arrival, "return_receipt_ref": "different-receipt"}
        with self.assertRaisesRegex(verify_station.VerificationError, "identity conflict"):
            verify_station.linearize_return_intake(once, [conflict])

    def test_return_intake_rejects_boolean_ordinal_and_reused_receipt(self) -> None:
        first = {
            "queue_item_id": "queue-item-a",
            "return_id": "return-a",
            "idempotency_key": "intake-key-a",
            "intake_receipt_ref": "intake-receipt-a",
            "enqueue_receipt_ref": "enqueue-receipt-a",
            "return_receipt_ref": "return-receipt-a",
        }
        admitted = verify_station.linearize_return_intake([], [first])
        admitted[0]["arrival_ordinal"] = True
        with self.assertRaisesRegex(verify_station.VerificationError, "ordinal chain"):
            verify_station.linearize_return_intake(admitted, [first])

        cross_type_collision = {**first, "enqueue_receipt_ref": first["intake_receipt_ref"]}
        with self.assertRaisesRegex(verify_station.VerificationError, "receipt reference reused"):
            verify_station.linearize_return_intake([], [cross_type_collision])

        second = {
            "queue_item_id": "queue-item-b",
            "return_id": "return-b",
            "idempotency_key": "intake-key-b",
            "intake_receipt_ref": "intake-receipt-b",
            "enqueue_receipt_ref": "enqueue-receipt-b",
            "return_receipt_ref": "return-receipt-a",
        }
        with self.assertRaisesRegex(verify_station.VerificationError, "return_receipt_ref reused"):
            verify_station.linearize_return_intake(
                verify_station.linearize_return_intake([], [first]),
                [second],
            )

        same_batch_collision = {**second, "return_id": first["return_id"]}
        with self.assertRaisesRegex(verify_station.VerificationError, "return_id reused"):
            verify_station.linearize_return_intake([], [first, same_batch_collision])

    def test_queue_rejects_boolean_for_integer_control_fields(self) -> None:
        for path in ("profile_epoch", "external_effect_count"):
            with self.subTest(path=path):
                document = copy.deepcopy(self.return_queue)
                document["queue"][path] = True
                with self.assertRaises(verify_station.VerificationError):
                    verify_station.validate_return_queue(document)
        document = copy.deepcopy(self.return_queue)
        document["queue"]["policy"]["admission_width"] = True
        with self.assertRaisesRegex(verify_station.VerificationError, "one head"):
            verify_station.validate_return_queue(document)

    def test_invalid_or_absent_queue_proposal_falls_back_to_controller_priority_fifo(self) -> None:
        ready = self.return_queue["returns"][:3]
        counts = {item["queue_item_id"]: 0 for item in ready}
        ranks = {
            "synthetic-queue-item-old": 2,
            "synthetic-queue-item-short": 1,
            "synthetic-queue-item-medium": 1,
        }
        invalid_proposals = (
            None,
            ["synthetic-queue-item-short", "synthetic-queue-item-short", "synthetic-queue-item-old"],
            ["synthetic-queue-item-short", "synthetic-queue-item-old"],
            ["synthetic-queue-item-short", "synthetic-queue-item-medium", "unknown"],
            ["synthetic-queue-item-old", "synthetic-queue-item-short", "synthetic-queue-item-medium"],
        )
        for proposal in invalid_proposals:
            with self.subTest(proposal=proposal):
                reduced = verify_station.reduce_return_queue_snapshot(
                    ready, counts, ranks, proposal, 2
                )
                self.assertEqual(
                    "FALLBACK_CONTROLLER_PRIORITY_FIFO_ABSENT_OR_INVALID_PROPOSAL",
                    reduced["proposal_status"],
                )
                self.assertEqual(
                    ["synthetic-queue-item-short", "synthetic-queue-item-medium", "synthetic-queue-item-old"],
                    reduced["schedule_order"],
                )

    def test_unknown_steward_binding_cannot_alias_a_queue_item_id(self) -> None:
        mapping = {"valid-binding": "UNKNOWN_OPAQUE_BINDING:forged"}
        self.assertIsNone(
            verify_station._map_queue_steward_order(["forged"], mapping)
        )

    def test_maximum_overtakes_forces_oldest_due_return(self) -> None:
        by_id = {item["queue_item_id"]: item for item in self.return_queue["returns"]}
        ready = [by_id["synthetic-queue-item-old"], by_id["synthetic-queue-item-late"]]
        reduced = verify_station.reduce_return_queue_snapshot(
            ready,
            {"synthetic-queue-item-old": 2, "synthetic-queue-item-late": 0},
            {"synthetic-queue-item-old": 2, "synthetic-queue-item-late": 1},
            ["synthetic-queue-item-late", "synthetic-queue-item-old"],
            2,
        )
        self.assertEqual("synthetic-queue-item-old", reduced["forced_head_queue_item_id"])
        self.assertEqual("synthetic-queue-item-old", reduced["service_head_queue_item_id"])
        self.assertEqual("MAXIMUM_OVERTAKES_FIFO_FORCED", reduced["schedule_basis"])

    def test_queue_reducer_rejects_boolean_cost_and_duplicate_arrival_ordinal(self) -> None:
        ready = copy.deepcopy(self.return_queue["returns"][:3])
        counts = {item["queue_item_id"]: 0 for item in ready}
        ranks = {item["queue_item_id"]: 2 for item in ready}
        ready[0]["controller_approved_processing_cost"] = True
        with self.assertRaisesRegex(verify_station.VerificationError, "controller-approved costs"):
            verify_station.reduce_return_queue_snapshot(ready, counts, ranks, None, 2)

        ready = copy.deepcopy(self.return_queue["returns"][:3])
        ready[1]["arrival_ordinal"] = ready[0]["arrival_ordinal"]
        with self.assertRaisesRegex(verify_station.VerificationError, "arrival ordinals"):
            verify_station.reduce_return_queue_snapshot(ready, counts, ranks, None, 2)

    def test_queue_steward_cannot_acquire_admission_authority(self) -> None:
        document = copy.deepcopy(self.return_queue)
        document["queue"]["queue_steward"]["can_admit"] = True
        with self.assertRaisesRegex(verify_station.VerificationError, "steward can_admit"):
            verify_station.validate_return_queue(document)

    def test_queue_steward_and_controller_identities_cannot_alias(self) -> None:
        document = copy.deepcopy(self.return_queue)
        document["queue"]["controller_ref"] = document["queue"]["queue_steward"]["identity_ref"]
        with self.assertRaisesRegex(verify_station.VerificationError, "identities must remain distinct"):
            verify_station.validate_return_queue(document)

    def test_controller_cannot_alias_a_data_return_creature(self) -> None:
        document = copy.deepcopy(self.return_queue)
        document["queue"]["controller_ref"] = document["returns"][0]["creature_ref"]
        with self.assertRaises(verify_station.VerificationError):
            verify_station.validate_return_queue(document)

    def test_queue_steward_cannot_enter_the_data_queue_it_proposes_over(self) -> None:
        document = copy.deepcopy(self.return_queue)
        document["returns"][0]["creature_ref"] = document["queue"]["queue_steward"]["identity_ref"]
        with self.assertRaisesRegex(verify_station.VerificationError, "Morrow cannot enter"):
            verify_station.validate_return_queue(document)

    def test_frozen_snapshot_rejects_future_or_missing_visible_return(self) -> None:
        document = copy.deepcopy(self.return_queue)
        document["snapshots"][0]["visible_ids"].append("synthetic-queue-item-late")
        with self.assertRaisesRegex(verify_station.VerificationError, "frozen visibility"):
            verify_station.validate_return_queue(document)

    def test_full_snapshot_binding_covers_partitions_but_steward_view_does_not(self) -> None:
        document = copy.deepcopy(self.return_queue)
        by_id = {item["queue_item_id"]: item for item in document["returns"]}
        snapshot = document["snapshots"][0]
        full_before = verify_station.return_queue_snapshot_sha256(snapshot, by_id)
        view_before = verify_station.return_queue_scheduling_view_sha256(snapshot, by_id)
        snapshot["held_ids"] = []
        self.assertNotEqual(full_before, verify_station.return_queue_snapshot_sha256(snapshot, by_id))
        self.assertEqual(view_before, verify_station.return_queue_scheduling_view_sha256(snapshot, by_id))

    def test_queue_steward_view_is_closed_and_opaque(self) -> None:
        snapshot = self.return_queue["snapshots"][0]
        by_id = {item["queue_item_id"]: item for item in self.return_queue["returns"]}
        view = verify_station.return_queue_scheduling_view_projection(snapshot, by_id)
        allowed = set(self.return_queue["queue"]["queue_steward"]["scheduling_view_field_allowlist"])
        self.assertTrue(view["ready_scheduling_view"])
        for item in view["ready_scheduling_view"]:
            self.assertEqual(allowed, set(item))
            self.assertNotIn("content_sha256", item)
            self.assertNotIn("objective_disposition", item)

    def test_serialized_absent_proposal_uses_fifo_fallback(self) -> None:
        document = copy.deepcopy(self.return_queue)
        document["snapshots"][2]["proposal"] = None
        document["snapshots"][2]["decision"]["proposal_validation"] = (
            "INVALID_OR_ABSENT_USED_CONTROLLER_PRIORITY_FIFO_FALLBACK"
        )
        verify_station.validate_return_queue(document)

    def test_post_cut_return_is_bound_to_immediate_successor_snapshot(self) -> None:
        document = copy.deepcopy(self.return_queue)
        document["returns"][4]["available_snapshot_ordinal"] = 3
        with self.assertRaisesRegex(verify_station.VerificationError, "first eligible snapshot"):
            verify_station.validate_return_queue(document)

    def test_queue_proposal_stale_ready_view_digest_uses_fallback(self) -> None:
        document = copy.deepcopy(self.return_queue)
        snapshot = document["snapshots"][0]
        snapshot["proposal"]["morrow_output"] = {
            "schema": "hearthline-plays.morrow-invalid-output-capture.v1",
            "status": "INVALID_UNTRUSTED_OUTPUT_CAPTURED_FOR_FALLBACK",
            "invocation_cut_binding": snapshot["morrow_invocation_cut_binding"],
            "scheduling_view_sha256": self.return_queue["snapshots"][0]["proposal"]["morrow_output"]["scheduling_view_sha256"],
            "policy_ref": document["queue"]["policy"]["policy_ref"],
            "bounded_raw_output_sha256": "ee268a71b05de985c2d7b596eede7bb289ad999b071882bc65e653b9c52e58a6",
            "bounded_raw_output_byte_count": 12,
            "failure_code": "STALE",
            "raw_output_retained": False,
        }
        snapshot["decision"]["proposal_validation"] = "INVALID_OR_ABSENT_USED_CONTROLLER_PRIORITY_FIFO_FALLBACK"
        snapshot["decision"]["controller_disposition"] = "USE_CONTROLLER_PRIORITY_FIFO_FALLBACK"
        snapshot["decision"]["schedule_basis"] = "CONTROLLER_PRIORITY_THEN_FIFO_FALLBACK"
        snapshot["decision"]["schedule_order"] = [
            "synthetic-queue-item-short",
            "synthetic-queue-item-old",
            "synthetic-queue-item-medium",
        ]
        snapshot["decision"]["service_head_queue_item_id"] = "synthetic-queue-item-short"
        verify_station.validate_return_queue(document)

    def test_valid_proposal_and_controller_override_remain_distinct(self) -> None:
        decision = self.return_queue["snapshots"][2]["decision"]
        self.assertEqual("VALID_EXACT_READY_PERMUTATION_AND_POLICY", decision["proposal_validation"])
        self.assertEqual("ENFORCE_HEAD_MAXIMUM_OVERTAKES", decision["controller_disposition"])
        self.assertEqual("synthetic-queue-item-old", decision["service_head_queue_item_id"])

    def test_queue_admission_cannot_reconcile_or_select_carry(self) -> None:
        for field in ("custody_reconciliation_performed", "carry_mutated"):
            with self.subTest(field=field):
                document = copy.deepcopy(self.return_queue)
                document["snapshots"][0]["admission"][field] = True
                with self.assertRaisesRegex(verify_station.VerificationError, field):
                    verify_station.validate_return_queue(document)

    def test_queue_accepts_non_success_disposition_without_upgrading_it(self) -> None:
        document = copy.deepcopy(self.return_queue)
        medium = document["returns"][2]
        medium["objective_disposition"] = "SYNTHETIC_RULE_MEDIUM:BLOCKED"
        document["snapshots"][1]["admission"]["objective_disposition"] = medium["objective_disposition"]
        verify_station.validate_return_queue(document)

    def test_admission_receipt_binds_profile_snapshot_order_and_controller(self) -> None:
        for field, value, message in (
            ("profile_ref", "WRONG_PROFILE", "admission profile identity"),
            ("snapshot_id", "WRONG_SNAPSHOT", "admission snapshot identity"),
            ("order_receipt_ref", "WRONG_ORDER", "admission order receipt binding"),
            ("controller_ref", "WRONG_CONTROLLER", "controller-only admission"),
        ):
            with self.subTest(field=field):
                document = copy.deepcopy(self.return_queue)
                document["snapshots"][0]["admission"][field] = value
                with self.assertRaisesRegex(verify_station.VerificationError, message):
                    verify_station.validate_return_queue(document)

    def test_order_and_admission_receipts_are_distinct(self) -> None:
        document = copy.deepcopy(self.return_queue)
        document["snapshots"][0]["admission"]["admission_receipt_ref"] = (
            document["snapshots"][0]["decision"]["order_receipt_ref"]
        )
        with self.assertRaisesRegex(verify_station.VerificationError, "admission receipt must be distinct"):
            verify_station.validate_return_queue(document)

    def test_proposal_and_order_records_are_distinct(self) -> None:
        document = copy.deepcopy(self.return_queue)
        document["snapshots"][0]["decision"]["order_receipt_ref"] = (
            document["snapshots"][0]["proposal"]["proposal_ref"]
        )
        document["snapshots"][0]["admission"]["order_receipt_ref"] = (
            document["snapshots"][0]["proposal"]["proposal_ref"]
        )
        with self.assertRaisesRegex(verify_station.VerificationError, "order receipt must be a distinct"):
            verify_station.validate_return_queue(document)

    def test_same_content_wins_keep_distinct_intake_and_admission_identity(self) -> None:
        by_id = {item["queue_item_id"]: item for item in self.return_queue["returns"]}
        old = by_id["synthetic-queue-item-old"]
        short = by_id["synthetic-queue-item-short"]
        self.assertEqual(old["content_sha256"], short["content_sha256"])
        self.assertNotEqual(old["return_id"], short["return_id"])
        self.assertNotEqual(old["objective_id"], short["objective_id"])
        self.assertNotEqual(old["creature_ref"], short["creature_ref"])
        self.assertNotEqual(old["intake_receipt_ref"], short["intake_receipt_ref"])
        self.assertIn(old["queue_item_id"], self.return_queue["accounting"]["admission_order"])
        self.assertIn(short["queue_item_id"], self.return_queue["accounting"]["admission_order"])


if __name__ == "__main__":
    unittest.main()
