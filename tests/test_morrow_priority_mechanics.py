from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "verify_station.py"
SPEC = importlib.util.spec_from_file_location("verify_station_priority", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import setup guard
    raise RuntimeError("unable to load station verifier")
verify_station = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_station)


class MorrowPriorityMechanicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.queue = verify_station.load_strict_json(
            ROOT / "fixtures" / "return-queue.synthetic.json"
        )

    def trusted_context(self) -> dict[str, object]:
        queue = self.queue["queue"]
        return {
            "controller_ref": queue["controller_ref"],
            "priority_assigner_ref": queue["priority_assigner_ref"],
            "queue_id": queue["queue_id"],
            "profile_ref": queue["profile_ref"],
            "profile_epoch": queue["profile_epoch"],
            "policy_ref": queue["policy"]["policy_ref"],
        }

    def genesis(self) -> dict[str, str]:
        queue = self.queue["queue"]
        return {
            "head_ref": queue["priority_genesis_head_ref"],
            "head_sha256": queue["priority_genesis_head_sha256"],
        }

    def genesis_snapshot(self) -> dict[str, object]:
        queue = self.queue["queue"]
        return {
            "snapshot_id": queue["priority_genesis_head_ref"],
            "snapshot_ordinal": 0,
            "snapshot_projection_sha256": queue["priority_genesis_head_sha256"],
        }

    def trusted_ledger_head(
        self, receipts: list[dict[str, object]]
    ) -> dict[str, object]:
        if not receipts:
            genesis = self.genesis()
            return {
                "register_state": "EMPTY_PRIORITY_LEDGER_AT_GENESIS",
                "ledger_length": 0,
                "head_ref": genesis["head_ref"],
                "head_sha256": genesis["head_sha256"],
            }
        current = receipts[-1]
        return {
            "register_state": "DURABLE_PRIORITY_RECEIPT_HEAD",
            "ledger_length": len(receipts),
            "head_ref": current["priority_receipt_ref"],
            "head_sha256": verify_station._canonical_json_sha256(current),
        }

    def snapshot_head(self, ordinal: int) -> dict[str, object]:
        snapshot = self.queue["snapshots"][ordinal - 1]
        return {
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_ordinal": ordinal,
            "snapshot_projection_sha256": snapshot["snapshot_projection_sha256"],
        }

    def lifecycle_for(self, receipt: dict[str, object], state: str) -> dict[str, object]:
        return {
            "task_ref": receipt["task_ref"],
            "tether_ref": receipt["tether_ref"],
            "dispatch_ref": receipt["dispatch_ref"],
            "state": state,
            "terminal_admission_ref": None,
        }

    def candidate(self, receipt_index: int) -> dict[str, object]:
        return {
            key: copy.deepcopy(value)
            for key, value in self.queue["priority_receipts"][receipt_index].items()
            if key != "ledger_ordinal"
        }

    def authorization(self, tether_ref: str) -> dict[str, object]:
        return copy.deepcopy(next(
            item for item in self.queue["priority_authorizations"]
            if item["tether_ref"] == tether_ref
        ))

    def append_root(self, existing: list[dict[str, object]], mark: dict[str, object], **overrides: object) -> list[dict[str, object]]:
        arguments = {
            "existing_receipts": existing,
            "mark": mark,
            "trusted_controller_context": self.trusted_context(),
            "trusted_current_priority_ledger_head": self.trusted_ledger_head(existing),
            "observed_snapshot_head": self.genesis_snapshot(),
            "controller_lifecycle_evidence": self.lifecycle_for(mark, "TASK_COMMISSIONED_DISPATCH_PENDING"),
            "priority_authorization": self.authorization(str(mark["tether_ref"])),
            "priority_genesis_head": self.genesis(),
            "dispatch_assignment_basis_ref": self.queue["queue"]["dispatch_priority_assignment_basis_ref"],
            "revision_assignment_basis_ref": self.queue["queue"]["priority_revision_assignment_basis_ref"],
        }
        arguments.update(overrides)
        return verify_station.append_dispatch_priority_mark(**arguments)

    def append_revision(self, existing: list[dict[str, object]], revision: dict[str, object], **overrides: object) -> list[dict[str, object]]:
        arguments = {
            "existing_receipts": existing,
            "revision": revision,
            "trusted_controller_context": self.trusted_context(),
            "priority_genesis_head": self.genesis(),
            "trusted_current_priority_ledger_head": self.trusted_ledger_head(existing),
            "dispatch_assignment_basis_ref": self.queue["queue"]["dispatch_priority_assignment_basis_ref"],
            "observed_snapshot_head": self.snapshot_head(int(revision["observed_snapshot_ordinal"])),
            "controller_lifecycle_evidence": self.lifecycle_for(revision, "RETURN_PENDING_NOT_SELECTED"),
            "priority_authorization": self.authorization(str(revision["tether_ref"])),
            "revision_assignment_basis_ref": self.queue["queue"]["priority_revision_assignment_basis_ref"],
        }
        arguments.update(overrides)
        return verify_station.append_priority_revision(**arguments)

    def held_unknown_candidate(self) -> dict[str, object]:
        root = self.candidate(3)
        root_receipt = self.queue["priority_receipts"][3]
        root.update({
            "priority_receipt_ref": "SYNTHETIC_PRIORITY_REVISION_HELD_UNKNOWN_0001",
            "idempotency_key": "SYNTHETIC_PRIORITY_REVISION_IDEMPOTENCY_HELD_UNKNOWN_0001",
            "receipt_kind": "PRIORITY_REVISION",
            "revision_ordinal": 1,
            "supersedes_priority_receipt_ref": root_receipt["priority_receipt_ref"],
            "assignment_basis_ref": self.queue["queue"]["priority_revision_assignment_basis_ref"],
            "priority_class": "P1_EXPEDITE",
            "priority_rank": 1,
            "scheduling_mark_binding": "SYNTHETIC_OPAQUE_PRIORITY_MARK_HELD_UNKNOWN_0001",
            "observed_priority_ledger_head_ref": root_receipt["priority_receipt_ref"],
            "observed_priority_ledger_head_sha256": verify_station._canonical_json_sha256(root_receipt),
            "subject_state": "TASK_OUT_OR_RETURN_PENDING_NOT_ADMITTED",
        })
        return root

    def priority_reconciliation(self) -> dict[str, object]:
        hold = self.queue["priority_append_holds"][0]
        return {
            "priority_append_reconciliation_receipt_ref": "SYNTHETIC_PRIORITY_APPEND_RECONCILIATION_HELD_0001",
            "priority_append_hold_ref": hold["priority_append_hold_ref"],
            "controller_ref": hold["controller_ref"],
            "queue_id": hold["queue_id"],
            "profile_ref": hold["profile_ref"],
            "profile_epoch": hold["profile_epoch"],
            "policy_ref": hold["policy_ref"],
            "task_ref": hold["task_ref"],
            "tether_ref": hold["tether_ref"],
            "task_tether_core_sha256": hold["task_tether_core_sha256"],
            "dispatch_ref": hold["dispatch_ref"],
            "reconciliation_handle": hold["reconciliation_handle"],
            "reconciled_persistence_outcome": "CONFIRMED_NOT_APPENDED",
            "confirmed_priority_receipt_ref": None,
            "confirmed_priority_receipt_sha256": None,
            "revalidation_inputs_ref": "SYNTHETIC_PRIORITY_CURRENT_REVALIDATION_HELD_0001",
            "revalidation_result": "PASS",
            "status": "PRIORITY_APPEND_RECONCILED_READY_ELIGIBLE",
            "can_enter_ready": True,
            "external_effect_receipt_ref": None,
        }

    def resolve_priority_hold(self, reconciliation: dict[str, object], **overrides: object) -> dict[str, object]:
        receipts = copy.deepcopy(self.queue["priority_receipts"])
        current = receipts[-1]
        arguments = {
            "hold": copy.deepcopy(self.queue["priority_append_holds"][0]),
            "reconciliation": reconciliation,
            "durable_priority_receipts": receipts,
            "trusted_controller_context": self.trusted_context(),
            "priority_genesis_head": self.genesis(),
            "dispatch_assignment_basis_ref": self.queue["queue"]["dispatch_priority_assignment_basis_ref"],
            "revision_assignment_basis_ref": self.queue["queue"]["priority_revision_assignment_basis_ref"],
            "trusted_current_priority_ledger_head": {
                "register_state": "DURABLE_PRIORITY_RECEIPT_HEAD",
                "ledger_length": len(receipts),
                "head_ref": current["priority_receipt_ref"],
                "head_sha256": verify_station._canonical_json_sha256(current),
            },
            "priority_authorization": self.authorization("SYNTHETIC_TETHER_HELD"),
            "trusted_observed_snapshot_head": self.genesis_snapshot(),
            "trusted_priority_append_hold_head": {
                "hold_ref": self.queue["priority_append_holds"][0]["priority_append_hold_ref"],
                "hold_sha256": verify_station._canonical_json_sha256(
                    self.queue["priority_append_holds"][0]
                ),
            },
        }
        arguments.update(overrides)
        return verify_station.resolve_priority_append_hold(**arguments)

    def refresh_morrow_snapshot(self, document: dict[str, object], index: int) -> None:
        snapshot = document["snapshots"][index]
        return_by_id = {
            item["queue_item_id"]: item
            for item in document["returns"]
        }
        output = snapshot["proposal"]["morrow_output"]
        output["invocation_cut_binding"] = snapshot["morrow_invocation_cut_binding"]
        output["scheduling_view_sha256"] = (
            verify_station.return_queue_scheduling_view_sha256(snapshot, return_by_id)
        )
        output["ready_order"] = verify_station.expected_morrow_binding_order(
            snapshot, return_by_id
        )
        snapshot["snapshot_projection_sha256"] = (
            verify_station.return_queue_snapshot_sha256(snapshot, return_by_id)
        )

    def test_dispatch_root_append_and_exact_retry_are_typed_idempotent(self) -> None:
        mark = self.candidate(0)
        once = self.append_root([], mark)
        self.assertEqual(1, len(once))
        terminal = self.lifecycle_for(mark, "ADMITTED")
        terminal["terminal_admission_ref"] = "TERMINAL"
        twice = self.append_root(
            once,
            mark,
            observed_snapshot_head=None,
            controller_lifecycle_evidence=terminal,
            priority_authorization=None,
        )
        self.assertEqual(once, twice)
        advanced = copy.deepcopy(self.queue["priority_receipts"][:2])
        retried_old_root = self.append_root(
            advanced,
            mark,
            observed_snapshot_head=None,
            controller_lifecycle_evidence=terminal,
            priority_authorization=None,
        )
        self.assertEqual(advanced, retried_old_root)
        with self.assertRaisesRegex(
            verify_station.VerificationError,
            "authenticated current head",
        ):
            self.append_root(
                once,
                mark,
                trusted_current_priority_ledger_head=self.trusted_ledger_head([]),
            )
        with self.assertRaisesRegex(
            verify_station.VerificationError,
            "authenticated current head",
        ):
            self.append_root(
                once,
                mark,
                trusted_current_priority_ledger_head=self.trusted_ledger_head(advanced),
            )
        changed = copy.deepcopy(mark)
        changed["profile_epoch"] = 1.0
        with self.assertRaises(verify_station.VerificationError):
            self.append_root(once, changed)
        with self.assertRaisesRegex(verify_station.VerificationError, "root receipt kind"):
            self.append_root(once, self.candidate(5))

    def test_dispatch_root_rejects_stale_heads_forged_context_and_never_mutates_input(self) -> None:
        mark = self.candidate(0)
        original = copy.deepcopy(mark)
        first = copy.deepcopy(self.queue["priority_receipts"][:1])
        second = self.append_root(first, self.candidate(1))
        self.assertEqual(2, len(second))
        with self.assertRaisesRegex(
            verify_station.VerificationError,
            "authenticated current head",
        ):
            self.append_root(
                first,
                self.candidate(2),
                trusted_current_priority_ledger_head=self.trusted_ledger_head(second),
            )
        stale_global = copy.deepcopy(mark)
        stale_global["observed_priority_ledger_head_sha256"] = "0" * 64
        with self.assertRaisesRegex(verify_station.VerificationError, "global priority-ledger head"):
            self.append_root([], stale_global)
        stale_snapshot = copy.deepcopy(mark)
        stale_snapshot["observed_snapshot_ref"] = "STALE"
        with self.assertRaisesRegex(verify_station.VerificationError, "snapshot head"):
            self.append_root([], stale_snapshot)
        forged = self.trusted_context()
        forged["controller_ref"] = "ATTACKER"
        with self.assertRaises(verify_station.VerificationError):
            self.append_root([], mark, trusted_controller_context=forged)
        forged_empty_head = self.trusted_ledger_head([])
        forged_empty_head["head_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            verify_station.VerificationError,
            "empty register.*genesis head",
        ):
            self.append_root(
                [],
                mark,
                trusted_current_priority_ledger_head=forged_empty_head,
            )
        self.assertEqual(original, mark)

    def test_revision_append_retry_conflict_cas_ceiling_noop_budget_and_terminal(self) -> None:
        existing = copy.deepcopy(self.queue["priority_receipts"][:5])
        revision = self.candidate(5)
        appended = self.append_revision(existing, revision)
        terminal = self.lifecycle_for(revision, "ADMITTED")
        terminal["terminal_admission_ref"] = "TERMINAL"
        retried = self.append_revision(
            appended,
            revision,
            observed_snapshot_head=None,
            controller_lifecycle_evidence=terminal,
            priority_authorization=None,
        )
        self.assertEqual(appended, retried)
        with self.assertRaisesRegex(
            verify_station.VerificationError,
            "authenticated current head",
        ):
            self.append_revision(
                appended,
                revision,
                trusted_current_priority_ledger_head=self.trusted_ledger_head(existing),
            )

        changed = copy.deepcopy(revision)
        changed["observed_snapshot_ordinal"] = 1.0
        with self.assertRaisesRegex(verify_station.VerificationError, "binding conflict"):
            self.append_revision(appended, changed)
        with self.assertRaisesRegex(verify_station.VerificationError, "revision receipt kind"):
            self.append_revision(existing, self.candidate(0))

        mutations = (
            ("observed_priority_ledger_head_sha256", "0" * 64, "global priority-ledger head"),
            ("observed_snapshot_ref", "STALE", "snapshot head"),
            ("supersedes_priority_receipt_ref", "STALE", "predecessor"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                candidate = copy.deepcopy(revision)
                candidate[field] = value
                with self.assertRaisesRegex(verify_station.VerificationError, message):
                    self.append_revision(existing, candidate)

        ceiling = copy.deepcopy(revision)
        ceiling.update(priority_class="P0_URGENT", priority_rank=0)
        with self.assertRaisesRegex(verify_station.VerificationError, "ceiling"):
            self.append_revision(existing, ceiling)
        no_op = copy.deepcopy(revision)
        no_op.update(priority_class="P3_BACKGROUND", priority_rank=3)
        with self.assertRaisesRegex(verify_station.VerificationError, "no-op"):
            self.append_revision(existing, no_op)
        with self.assertRaisesRegex(verify_station.VerificationError, "selected, in-service, admitted"):
            self.append_revision(existing, revision, controller_lifecycle_evidence=terminal)

        short_existing = copy.deepcopy(self.queue["priority_receipts"][:2])
        short_root = short_existing[-1]
        exhausted = {
            key: copy.deepcopy(value)
            for key, value in short_root.items()
            if key != "ledger_ordinal"
        }
        exhausted.update({
            "priority_receipt_ref": "EXHAUSTED_REVISION",
            "idempotency_key": "EXHAUSTED_REVISION_KEY",
            "receipt_kind": "PRIORITY_REVISION",
            "revision_ordinal": 1,
            "supersedes_priority_receipt_ref": short_root["priority_receipt_ref"],
            "assignment_basis_ref": self.queue["queue"]["priority_revision_assignment_basis_ref"],
            "priority_class": "P2_ROUTINE",
            "priority_rank": 2,
            "scheduling_mark_binding": "EXHAUSTED_MARK",
            "observed_priority_ledger_head_ref": short_root["priority_receipt_ref"],
            "observed_priority_ledger_head_sha256": verify_station._canonical_json_sha256(short_root),
            "subject_state": "TASK_OUT_OR_RETURN_PENDING_NOT_ADMITTED",
        })
        with self.assertRaisesRegex(verify_station.VerificationError, "budget"):
            self.append_revision(
                short_existing,
                exhausted,
                observed_snapshot_head=self.genesis_snapshot(),
                priority_authorization=self.authorization("SYNTHETIC_TETHER_SHORT"),
            )

    def test_revision_rejects_forged_trust_root_without_mutating_register(self) -> None:
        existing = copy.deepcopy(self.queue["priority_receipts"][:5])
        before = copy.deepcopy(existing)
        context = self.trusted_context()
        context["controller_ref"] = "SYNTHETIC_ATTACKER_CONTROLLER"
        with self.assertRaises(verify_station.VerificationError):
            self.append_revision(existing, self.candidate(5), trusted_controller_context=context)
        self.assertEqual(before, existing)

    def test_append_helpers_reject_alternate_or_truncated_caller_ledgers(self) -> None:
        genuine = copy.deepcopy(self.queue["priority_receipts"][:5])
        revision = self.candidate(5)

        with self.assertRaisesRegex(
            verify_station.VerificationError,
            "authenticated current head",
        ):
            self.append_revision(
                genuine[:-1],
                revision,
                trusted_current_priority_ledger_head=self.trusted_ledger_head(genuine),
            )

        alternate_root = copy.deepcopy(self.queue["priority_receipts"][0])
        alternate_root.update({
            "priority_receipt_ref": "FABRICATED_ALT_ROOT",
            "idempotency_key": "FABRICATED_ALT_ROOT_KEY",
            "scheduling_mark_binding": "FABRICATED_ALT_MARK",
        })
        alternate_revision = {
            key: copy.deepcopy(value)
            for key, value in alternate_root.items()
            if key != "ledger_ordinal"
        }
        alternate_revision.update({
            "priority_receipt_ref": "FABRICATED_ALT_REVISION",
            "idempotency_key": "FABRICATED_ALT_REVISION_KEY",
            "receipt_kind": "PRIORITY_REVISION",
            "revision_ordinal": 1,
            "supersedes_priority_receipt_ref": "FABRICATED_ALT_ROOT",
            "assignment_basis_ref": self.queue["queue"]["priority_revision_assignment_basis_ref"],
            "priority_class": "P3_BACKGROUND",
            "priority_rank": 3,
            "scheduling_mark_binding": "FABRICATED_ALT_REVISION_MARK",
            "observed_priority_ledger_head_ref": "FABRICATED_ALT_ROOT",
            "observed_priority_ledger_head_sha256": verify_station._canonical_json_sha256(
                alternate_root
            ),
            "subject_state": "TASK_OUT_OR_RETURN_PENDING_NOT_ADMITTED",
        })
        with self.assertRaisesRegex(
            verify_station.VerificationError,
            "authenticated current head",
        ):
            self.append_revision(
                [alternate_root],
                alternate_revision,
                trusted_current_priority_ledger_head=self.trusted_ledger_head(
                    self.queue["priority_receipts"][:1]
                ),
                observed_snapshot_head=self.genesis_snapshot(),
                controller_lifecycle_evidence=self.lifecycle_for(
                    alternate_revision, "TASK_OUT"
                ),
                priority_authorization=self.authorization(
                    str(alternate_revision["tether_ref"])
                ),
            )

    def test_revision_cannot_renew_authority_deadline_scope_or_budget(self) -> None:
        existing = copy.deepcopy(self.queue["priority_receipts"][:5])
        before = copy.deepcopy(existing)
        revision = self.candidate(5)
        for field, value in (
            ("grant_ref", "RENEWED_GRANT"),
            ("scope_ref", "EXPANDED_SCOPE"),
            ("deadline_ref", "EXTENDED_DEADLINE"),
            ("budget_ref", "INCREASED_BUDGET"),
            ("grant_renewed", True),
            ("scope_expanded", True),
            ("deadline_extended", True),
            ("budget_increased", True),
            ("authority_mutated", True),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(revision)
                changed[field] = value
                with self.assertRaises(verify_station.VerificationError):
                    self.append_revision(existing, changed)
                self.assertEqual(before, existing)

    def test_unknown_revision_stages_closed_hold_and_known_durable_retry_cannot_stage(self) -> None:
        existing = copy.deepcopy(self.queue["priority_receipts"][:4])
        revision = self.held_unknown_candidate()
        hold = verify_station.stage_unknown_priority_revision(
            existing,
            revision,
            {
                "priority_append_hold_ref": "SYNTHETIC_PRIORITY_APPEND_HOLD_HELD_0001",
                "reconciliation_handle": "SYNTHETIC_PRIORITY_APPEND_RECONCILIATION_HANDLE_HELD_0001",
            },
            self.trusted_context(),
            self.genesis(),
            self.trusted_ledger_head(existing),
            self.queue["queue"]["dispatch_priority_assignment_basis_ref"],
            self.genesis_snapshot(),
            self.lifecycle_for(revision, "TASK_OUT"),
            self.authorization("SYNTHETIC_TETHER_HELD"),
            self.queue["queue"]["priority_revision_assignment_basis_ref"],
        )
        self.assertEqual(self.queue["priority_append_holds"][0], hold)
        with self.assertRaisesRegex(
            verify_station.VerificationError,
            "authenticated current head",
        ):
            verify_station.stage_unknown_priority_revision(
                existing[:-1],
                revision,
                {
                    "priority_append_hold_ref": "TRUNCATED_HOLD",
                    "reconciliation_handle": "TRUNCATED_HANDLE",
                },
                self.trusted_context(),
                self.genesis(),
                self.trusted_ledger_head(existing),
                self.queue["queue"]["dispatch_priority_assignment_basis_ref"],
                self.genesis_snapshot(),
                self.lifecycle_for(revision, "TASK_OUT"),
                self.authorization("SYNTHETIC_TETHER_HELD"),
                self.queue["queue"]["priority_revision_assignment_basis_ref"],
            )
        durable = self.append_revision(
            existing,
            revision,
            observed_snapshot_head=self.genesis_snapshot(),
            controller_lifecycle_evidence=self.lifecycle_for(revision, "TASK_OUT"),
        )
        with self.assertRaisesRegex(verify_station.VerificationError, "already known durable"):
            verify_station.stage_unknown_priority_revision(
                durable,
                revision,
                {"priority_append_hold_ref": "HOLD", "reconciliation_handle": "HANDLE"},
                self.trusted_context(),
                self.genesis(),
                self.trusted_ledger_head(durable),
                self.queue["queue"]["dispatch_priority_assignment_basis_ref"],
                self.genesis_snapshot(),
                self.lifecycle_for(revision, "TASK_OUT"),
                self.authorization("SYNTHETIC_TETHER_HELD"),
                self.queue["queue"]["priority_revision_assignment_basis_ref"],
            )

    def test_priority_append_hold_needs_authenticated_absence_and_exact_reconciliation(self) -> None:
        reconciliation = self.priority_reconciliation()
        resolved = self.resolve_priority_hold(reconciliation)
        self.assertTrue(resolved["can_enter_ready"])
        with self.assertRaisesRegex(verify_station.VerificationError, "durable register"):
            self.resolve_priority_hold(reconciliation, durable_priority_receipts=[])
        for field, value in (
            ("controller_ref", "ATTACKER"),
            ("task_ref", "OTHER_TASK"),
            ("reconciliation_handle", "OTHER_HANDLE"),
            ("revalidation_result", "FAIL"),
            ("reconciled_persistence_outcome", "UNKNOWN"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(reconciliation)
                changed[field] = value
                with self.assertRaises(verify_station.VerificationError):
                    self.resolve_priority_hold(changed)

    def test_priority_append_hold_rejects_fabricated_chain_and_heads(self) -> None:
        reconciliation = self.priority_reconciliation()
        hold = copy.deepcopy(self.queue["priority_append_holds"][0])
        mutations = (
            ("task_ref", "ATTACK_TASK"),
            ("tether_ref", "ATTACK_TETHER"),
            ("priority_authorization_ref", "ATTACK_AUTHORIZATION"),
            ("attempted_supersedes_priority_receipt_ref", "ATTACK_PREDECESSOR"),
            ("attempted_revision_ordinal", 999999),
            ("observed_priority_ledger_head_ref", "ATTACK_GLOBAL_HEAD"),
            ("observed_snapshot_ref", "ATTACK_SNAPSHOT"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(hold)
                changed[field] = value
                with self.assertRaises(verify_station.VerificationError):
                    self.resolve_priority_hold(reconciliation, hold=changed)

        forged_hold = copy.deepcopy(hold)
        forged_authorization = self.authorization("SYNTHETIC_TETHER_HELD")
        forged_reconciliation = copy.deepcopy(reconciliation)
        forged_values = {
            "priority_authorization_ref": "ATTACK_AUTHORIZATION",
            "task_ref": "ATTACK_TASK",
            "task_tether_core_sha256": "a" * 64,
            "dispatch_ref": "ATTACK_DISPATCH",
        }
        for field, value in forged_values.items():
            forged_hold[field] = value
            if field in forged_reconciliation:
                forged_reconciliation[field] = value
        forged_authorization.update({
            "priority_authorization_ref": forged_values["priority_authorization_ref"],
            "task_ref": forged_values["task_ref"],
            "task_tether_core_sha256": forged_values["task_tether_core_sha256"],
            "dispatch_ref": forged_values["dispatch_ref"],
        })
        with self.assertRaisesRegex(verify_station.VerificationError, "authenticated root|frozen authorization"):
            self.resolve_priority_hold(
                forged_reconciliation,
                hold=forged_hold,
                priority_authorization=forged_authorization,
                trusted_priority_append_hold_head={
                    "hold_ref": forged_hold["priority_append_hold_ref"],
                    "hold_sha256": verify_station._canonical_json_sha256(forged_hold),
                },
            )

        fabricated = copy.deepcopy(hold)
        fabricated.update({
            "priority_append_hold_ref": "FABRICATED_HOLD",
            "idempotency_key": "FABRICATED_IDEMPOTENCY",
            "attempted_priority_receipt_ref": "FABRICATED_ATTEMPT",
            "attempted_priority_receipt_sha256": "b" * 64,
            "reconciliation_handle": "FABRICATED_HANDLE",
        })
        fabricated_reconciliation = copy.deepcopy(reconciliation)
        fabricated_reconciliation.update({
            "priority_append_hold_ref": fabricated["priority_append_hold_ref"],
            "reconciliation_handle": fabricated["reconciliation_handle"],
        })
        with self.assertRaisesRegex(verify_station.VerificationError, "authenticated durable hold membership"):
            self.resolve_priority_hold(fabricated_reconciliation, hold=fabricated)

    def morrow_ingress_context(self) -> tuple[dict[str, object], dict[str, str], list[str]]:
        snapshot = self.queue["snapshots"][0]
        by_id = {item["queue_item_id"]: item for item in self.queue["returns"]}
        mapping = {
            item["opaque_queue_item_binding"]: item["queue_item_id"]
            for item in snapshot["morrow_ready_bindings"]
        }
        return snapshot, mapping, verify_station.expected_morrow_binding_order(snapshot, by_id)

    def ingest(self, raw: bytes, replayed: set[str] | None = None) -> dict[str, object]:
        snapshot, mapping, expected = self.morrow_ingress_context()
        return verify_station.ingest_morrow_output(
            raw,
            snapshot["morrow_invocation_cut_binding"],
            snapshot["proposal"]["morrow_output"]["scheduling_view_sha256"],
            snapshot["policy_ref"],
            mapping,
            expected,
            replayed,
        )

    def test_morrow_ingress_normalizes_policy_wrong_and_malformed_output(self) -> None:
        output = copy.deepcopy(self.queue["snapshots"][0]["proposal"]["morrow_output"])
        raw = json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual("hearthline-plays.morrow-proposal.v1", self.ingest(raw)["schema"])
        output["ready_order"] = list(reversed(output["ready_order"]))
        wrong = json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        capture = self.ingest(wrong)
        self.assertEqual("POLICY_MISMATCH", capture["failure_code"])
        self.assertEqual(hashlib.sha256(wrong).hexdigest(), capture["bounded_raw_output_sha256"])
        self.assertFalse(capture["raw_output_retained"])

        for raw_value in (
            b"{}",
            b'{"x":1,"x":2}',
            b'{"schema":"hearthline-plays.morrow-proposal.v1","status":"PROPOSAL_ONLY_NO_ADMISSION","invocation_cut_binding":[],"scheduling_view_sha256":"' + b"0" * 64 + b'","policy_ref":"x","ready_order":[],"reason_codes":[],"pure_metadata_only":true,"deterministic_stateless":true,"persistent_state_ref":null,"external_effect_count":0}',
            b'{"integer":' + b"9" * 5000 + b"}",
        ):
            with self.subTest(prefix=raw_value[:24]):
                self.assertEqual("MALFORMED", self.ingest(raw_value, {"old"})["failure_code"])

    def test_morrow_ingress_classifies_replay_stale_and_rejects_oversize(self) -> None:
        output = copy.deepcopy(self.queue["snapshots"][0]["proposal"]["morrow_output"])
        output["invocation_cut_binding"] = "mcut:ffffffffffffffffffffffffffffffff"
        raw = json.dumps(output, separators=(",", ":")).encode()
        self.assertEqual(
            "REPLAYED",
            self.ingest(raw, {"mcut:ffffffffffffffffffffffffffffffff"})["failure_code"],
        )
        output = copy.deepcopy(self.queue["snapshots"][0]["proposal"]["morrow_output"])
        output["scheduling_view_sha256"] = "0" * 64
        raw = json.dumps(output, separators=(",", ":")).encode()
        self.assertEqual("STALE", self.ingest(raw)["failure_code"])
        with self.assertRaisesRegex(verify_station.VerificationError, "bounded byte limit"):
            self.ingest(b"x" * (verify_station.MAXIMUM_MORROW_OUTPUT_BYTES + 1))

    def test_two_fairness_due_items_form_stable_prefix_before_urgent_work(self) -> None:
        ready = [
            {"queue_item_id": "old-a", "arrival_ordinal": 1, "controller_approved_processing_cost": 10},
            {"queue_item_id": "old-b", "arrival_ordinal": 2, "controller_approved_processing_cost": 1},
            {"queue_item_id": "urgent", "arrival_ordinal": 3, "controller_approved_processing_cost": 1},
        ]
        reduced = verify_station.reduce_return_queue_snapshot(
            ready,
            {"old-a": 2, "old-b": 2, "urgent": 0},
            {"old-a": 3, "old-b": 3, "urgent": 0},
            ["old-a", "old-b", "urgent"],
            2,
        )
        self.assertEqual(["old-a", "old-b", "urgent"], reduced["schedule_order"])
        self.assertEqual("old-a", reduced["forced_head_queue_item_id"])

    def test_due_unknown_head_rotates_once_then_reopens_without_count_reset(self) -> None:
        document = copy.deepcopy(self.queue)
        verify_station.validate_return_queue(document)
        self.assertEqual(2, document["snapshots"][2]["service_disposition"]["overtake_counts_after"][0]["count"])
        self.assertEqual("synthetic-queue-item-late", document["snapshots"][3]["service_disposition"]["queue_item_id"])
        self.assertEqual(2, document["snapshots"][4]["overtake_counts_before"][0]["count"])
        self.assertEqual("synthetic-queue-item-old", document["snapshots"][4]["admission"]["queue_item_id"])
        projected = verify_station.return_queue_scheduling_view_projection(
            document["snapshots"][4],
            {item["queue_item_id"]: item for item in document["returns"]},
        )
        serialized_projection = json.dumps(projected, sort_keys=True)
        self.assertNotIn("retry_rotation", serialized_projection)
        self.assertNotIn("service_reconciliation", serialized_projection)
        self.assertNotIn("reconciliation_evidence", serialized_projection)

    def test_retry_rotation_release_rejects_wrong_binding_replay_and_mutation(self) -> None:
        mutations = (
            ("source_service_disposition_receipt_ref", "WRONG"),
            ("source_reopen_handle", "WRONG"),
            ("queue_item_id", "synthetic-queue-item-late"),
            ("intervening_queue_item_id", "synthetic-queue-item-old"),
            ("intervening_service_ordinal", True),
            ("priority_mutated", True),
            ("custody_mutated", True),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                document = copy.deepcopy(self.queue)
                document["retry_rotation_release_receipts"][0][field] = value
                with self.assertRaises(verify_station.VerificationError):
                    verify_station.validate_return_queue(document)
        document = copy.deepcopy(self.queue)
        document["retry_rotation_release_receipts"].append(
            copy.deepcopy(document["retry_rotation_release_receipts"][0])
        )
        with self.assertRaises(verify_station.VerificationError):
            verify_station.validate_return_queue(document)

    def test_unknown_reopen_requires_typed_one_shot_service_reconciliation(self) -> None:
        mutations = (
            ("controller_ref", "ATTACKER"),
            ("profile_epoch", True),
            ("service_epoch", 2),
            ("service_disposition_receipt_ref", "WRONG_DISPOSITION"),
            ("queue_item_id", "synthetic-queue-item-late"),
            ("reopen_handle", "WRONG_HANDLE"),
            ("observed_outcome", "FAILED"),
            ("reconciled_outcome", "UNKNOWN"),
            ("retry_permitted", False),
            ("priority_mutated", True),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                document = copy.deepcopy(self.queue)
                document["service_reconciliation_receipts"][0][field] = value
                with self.assertRaises(verify_station.VerificationError):
                    verify_station.validate_return_queue(document)

        document = copy.deepcopy(self.queue)
        document["snapshots"][4]["service_reopen_receipts"][0][
            "reconciliation_receipt_ref"
        ] = "FABRICATED_RECONCILIATION"
        document["snapshots"][4]["snapshot_projection_sha256"] = (
            verify_station.return_queue_snapshot_sha256(
                document["snapshots"][4],
                {item["queue_item_id"]: item for item in document["returns"]},
            )
        )
        with self.assertRaisesRegex(verify_station.VerificationError, "durable reconciliation evidence"):
            verify_station.validate_return_queue(document)

        document = copy.deepcopy(self.queue)
        document["service_reconciliation_receipts"].append(
            copy.deepcopy(document["service_reconciliation_receipts"][0])
        )
        with self.assertRaises(verify_station.VerificationError):
            verify_station.validate_return_queue(document)

    def test_snapshot_rejects_more_than_one_atomic_service_reopen(self) -> None:
        document = copy.deepcopy(self.queue)
        document["snapshots"][4]["service_reopen_receipts"].append(
            copy.deepcopy(document["snapshots"][4]["service_reopen_receipts"][0])
        )
        document["snapshots"][4]["snapshot_projection_sha256"] = (
            verify_station.return_queue_snapshot_sha256(
                document["snapshots"][4],
                {item["queue_item_id"]: item for item in document["returns"]},
            )
        )
        with self.assertRaisesRegex(verify_station.VerificationError, "at most one atomic service reopen"):
            verify_station.validate_return_queue(document)

    def test_retry_rotation_cannot_relabel_an_intervening_attempt_as_zero_peer(self) -> None:
        document = copy.deepcopy(self.queue)
        release = document["retry_rotation_release_receipts"][0]
        prior = document["snapshots"][3]
        release.update({
            "release_mode": "NO_OTHER_ELIGIBLE_READY",
            "intervening_service_record_ref": None,
            "intervening_queue_item_id": None,
            "intervening_service_ordinal": None,
            "pre_reopen_snapshot_id": prior["snapshot_id"],
            "pre_reopen_snapshot_projection_sha256": prior["snapshot_projection_sha256"],
            "derived_other_ready_count": 0,
        })
        with self.assertRaisesRegex(verify_station.VerificationError, "immediately follow"):
            verify_station.validate_return_queue(document)

    def test_no_other_rotation_accepts_only_immediate_zero_peer_cut(self) -> None:
        disposition = {
            "service_disposition_receipt_ref": "DISPOSITION_X",
            "queue_item_id": "x",
            "service_ordinal": 1,
        }
        pre_reopen = {
            "snapshot_id": "SNAPSHOT_1",
            "snapshot_projection_sha256": "a" * 64,
            "cut_arrival_ordinal": 1,
            "ready_ids": ["x"],
            "decision": {"service_head_queue_item_id": "x"},
            "service_disposition": copy.deepcopy(disposition),
        }
        release = {
            "release_mode": "NO_OTHER_ELIGIBLE_READY",
            "source_service_disposition_receipt_ref": "DISPOSITION_X",
            "intervening_service_record_ref": None,
            "intervening_queue_item_id": None,
            "intervening_service_ordinal": None,
            "pre_reopen_snapshot_id": "SNAPSHOT_1",
            "pre_reopen_snapshot_projection_sha256": "a" * 64,
            "derived_other_ready_count": 0,
        }
        verify_station.validate_no_other_retry_rotation_release(
            release, disposition, pre_reopen, 2, 1
        )
        with_peer = copy.deepcopy(pre_reopen)
        with_peer["ready_ids"] = ["x", "peer"]
        with self.assertRaisesRegex(verify_station.VerificationError, "zero other"):
            verify_station.validate_no_other_retry_rotation_release(
                release, disposition, with_peer, 2, 1
            )
        with self.assertRaisesRegex(verify_station.VerificationError, "unexamined arrival"):
            verify_station.validate_no_other_retry_rotation_release(
                release, disposition, pre_reopen, 2, 2
            )

    def test_service_and_admission_numeric_fields_are_type_strict(self) -> None:
        for snapshot_index, record_name, field in (
            (2, "service_disposition", "profile_epoch"),
            (2, "service_disposition", "service_epoch"),
            (2, "service_disposition", "service_ordinal"),
            (0, "admission", "effective_priority_rank"),
        ):
            with self.subTest(record=record_name, field=field):
                document = copy.deepcopy(self.queue)
                document["snapshots"][snapshot_index][record_name][field] = True
                with self.assertRaises(verify_station.VerificationError):
                    verify_station.validate_return_queue(document)

    def test_intake_exact_retry_is_type_strict_for_extra_scheduling_fields(self) -> None:
        arrival = {
            "queue_item_id": "q",
            "return_id": "r",
            "idempotency_key": "k",
            "intake_receipt_ref": "i",
            "enqueue_receipt_ref": "e",
            "return_receipt_ref": "h",
            "controller_approved_processing_cost": 1,
        }
        existing = verify_station.linearize_return_intake([], [arrival])
        changed = copy.deepcopy(arrival)
        changed["controller_approved_processing_cost"] = 1.0
        with self.assertRaisesRegex(verify_station.VerificationError, "identity conflict"):
            verify_station.linearize_return_intake(existing, [changed])

    def test_dynamic_morrow_tokens_reject_cross_invocation_aliases(self) -> None:
        prior_item = self.queue["snapshots"][0]["morrow_ready_bindings"][0]["opaque_queue_item_binding"]
        prior_cut = self.queue["snapshots"][0]["morrow_invocation_cut_binding"]
        cases = (
            ("cut_equals_past_item", "cut", prior_item, "opaque Morrow invocation cut binding"),
            ("item_equals_current_cut", "item", self.queue["snapshots"][4]["morrow_invocation_cut_binding"], "cannot alias any cut or item binding"),
            ("item_equals_past_cut", "item", prior_cut, "cannot alias any cut or item binding"),
            ("item_casefolds_to_past_cut", "item", prior_cut.upper(), "cannot alias any cut or item binding"),
        )
        for name, location, value, message in cases:
            with self.subTest(case=name):
                document = copy.deepcopy(self.queue)
                snapshot = document["snapshots"][4]
                if location == "cut":
                    snapshot["morrow_invocation_cut_binding"] = value
                else:
                    snapshot["morrow_ready_bindings"][0]["opaque_queue_item_binding"] = value
                self.refresh_morrow_snapshot(document, 4)
                with self.assertRaisesRegex(verify_station.VerificationError, message):
                    verify_station.validate_return_queue(document)

    def test_dynamic_morrow_tokens_are_disjoint_from_complete_static_surface(self) -> None:
        queue = self.queue["queue"]
        snapshot_zero = self.queue["snapshots"][0]
        aliases = (
            ("queue_id", queue["queue_id"]),
            ("return_task_ref", self.queue["returns"][0]["task_ref"]),
            ("static_morrow_ref", queue["queue_steward"]["identity_ref"]),
            ("thulia_ref", queue["thulia_non_interference"]["thulia_ref"]),
            ("proposal_ref", self.queue["snapshots"][4]["proposal"]["proposal_ref"]),
            ("prior_view_digest", snapshot_zero["proposal"]["morrow_output"]["scheduling_view_sha256"]),
            ("top_schema", self.queue["schema"]),
            ("top_status", self.queue["status"]),
            ("output_schema", snapshot_zero["proposal"]["morrow_output"]["schema"]),
            ("output_status", snapshot_zero["proposal"]["morrow_output"]["status"]),
            ("retry_release_ref", self.queue["retry_rotation_release_receipts"][0]["retry_rotation_release_receipt_ref"]),
            ("service_reconciliation_ref", self.queue["service_reconciliation_receipts"][0]["service_reconciliation_receipt_ref"]),
            ("service_reconciliation_evidence", self.queue["service_reconciliation_receipts"][0]["reconciliation_evidence_ref"]),
        )
        for index, (name, value) in enumerate(aliases):
            with self.subTest(alias=name):
                document = copy.deepcopy(self.queue)
                snapshot = document["snapshots"][4]
                if index % 2:
                    snapshot["morrow_ready_bindings"][0]["opaque_queue_item_binding"] = value
                else:
                    snapshot["morrow_invocation_cut_binding"] = value
                self.refresh_morrow_snapshot(document, 4)
                with self.assertRaisesRegex(
                    verify_station.VerificationError,
                    "disjoint from all durable controller, data, Thulia, and static Morrow surfaces",
                ):
                    verify_station.validate_return_queue(document)

        for name, leaked in (
            ("uppercase_dynamic_token", self.queue["snapshots"][4]["morrow_invocation_cut_binding"].upper()),
            (
                "nfkc_fullwidth_dynamic_token",
                "".join(
                    chr(ord(character) + 0xFEE0)
                    if 0x21 <= ord(character) <= 0x7E
                    else character
                    for character in self.queue["snapshots"][4]["morrow_invocation_cut_binding"]
                ),
            ),
        ):
            with self.subTest(alias=name):
                document = copy.deepcopy(self.queue)
                document["service_reconciliation_receipts"][0]["reconciliation_evidence_ref"] = leaked
                with self.assertRaisesRegex(
                    verify_station.VerificationError,
                    "disjoint from all durable controller, data, Thulia, and static Morrow surfaces",
                ):
                    verify_station.validate_return_queue(document)

    def test_morrow_and_thulia_non_interference_is_symmetric_and_stateless(self) -> None:
        mutations = (
            ("morrow", "can_invoke_thulia", True),
            ("morrow", "can_impersonate_thulia", True),
            ("morrow", "depends_on_thulia", True),
            ("morrow", "direct_thulia_channel_ref", "CHANNEL"),
            ("morrow", "operates_if_thulia_absent", False),
            ("morrow", "persistent_state_ref", "STATE"),
            ("morrow", "ledger_ref", "LEDGER"),
            ("morrow", "perch_ref", "PERCH"),
            ("morrow", "bridge_gloss_ref", "GLOSS"),
            ("morrow", "liveness_contract_ref", "LIVENESS"),
            ("morrow", "can_read_selected_carry", True),
            ("morrow", "can_read_homecoming_custody", True),
            ("morrow", "can_read_thulia_state", True),
            ("morrow", "can_write_thulia_state", True),
            ("morrow", "can_admit", True),
            ("morrow", "can_execute_effect", True),
            ("thulia", "can_invoke_morrow", True),
            ("thulia", "can_impersonate_morrow", True),
            ("thulia", "depends_on_morrow", True),
            ("thulia", "direct_morrow_channel_ref", "CHANNEL"),
            ("thulia", "operates_if_morrow_absent", False),
            ("thulia", "can_read_or_set_priority", True),
            ("thulia", "can_read_scheduling_view", True),
            ("thulia", "can_write_scheduling_view", True),
            ("thulia", "can_read_proposal", True),
            ("thulia", "can_write_proposal", True),
            ("thulia", "can_read_final_order", True),
            ("thulia", "can_read_admission_state", True),
            ("thulia", "can_set_controller_approved_processing_cost", True),
            ("thulia", "can_set_order", True),
            ("thulia", "can_admit", True),
        )
        for side, field, value in mutations:
            with self.subTest(side=side, field=field):
                document = copy.deepcopy(self.queue)
                target = (
                    document["queue"]["queue_steward"]
                    if side == "morrow"
                    else document["queue"]["thulia_non_interference"]
                )
                target[field] = value
                with self.assertRaises(verify_station.VerificationError):
                    verify_station.validate_return_queue(document)

        document = copy.deepcopy(self.queue)
        document["queue"]["queue_steward"]["identity_ref"] = (
            document["queue"]["thulia_non_interference"]["thulia_ref"]
        )
        with self.assertRaisesRegex(verify_station.VerificationError, "Morrow.*Thulia|Thulia.*scheduling"):
            verify_station.validate_return_queue(document)

        for morrow_ref, thulia_ref in (
            ("synthetic_thulia_0001", "SYNTHETIC_THULIA_0001"),
            ("ROLE_e\u0301", "ROLE_é"),
        ):
            with self.subTest(morrow_ref=morrow_ref, thulia_ref=thulia_ref):
                document = copy.deepcopy(self.queue)
                document["queue"]["queue_steward"]["identity_ref"] = morrow_ref
                document["queue"]["thulia_non_interference"]["thulia_ref"] = thulia_ref
                with self.assertRaisesRegex(verify_station.VerificationError, "canonical identity"):
                    verify_station.validate_return_queue(document)


if __name__ == "__main__":
    unittest.main()
