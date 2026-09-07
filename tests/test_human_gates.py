from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_INVENTORY_PATH = (
    ROOT / "launch/runtime/kaggle-stage-v4-runtime-inventory.json"
)
RUNTIME_INVENTORY_BYTES = RUNTIME_INVENTORY_PATH.read_bytes()
RUNTIME_INVENTORY = json.loads(RUNTIME_INVENTORY_BYTES)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GATE = load_module("arc3_human_gate_test", ROOT / "scripts/verify_human_gate.py")
REAL_READ_PRIVATE_RECORD = GATE.read_private_record
REAL_VERIFY_CURRENT_CANDIDATE = GATE.verify_current_candidate


class HumanGateTests(unittest.TestCase):
    NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.consumed_root = Path(self.temporary.name) / "consumption"
        self.root_patch = mock.patch.object(GATE, "CONSUMED_ROOT", self.consumed_root)
        self.root_patch.start()
        self.candidate = {
            "commit": "1" * 40,
            "tree": "2" * 40,
            "account_slug": "grativy6",
            "kernel_id": "grativy6/hearthline-arc3-readiness",
            "accelerator": "cpu",
            "agent_sha256": "3" * 64,
            "builder_sha256": "4" * 64,
            "notebook_sha256": "5" * 64,
            "kernel_metadata_sha256": "6" * 64,
            "source_lock_sha256": "7" * 64,
            "candidate_manifest_sha256": "8" * 64,
            "verified_snapshot_sha256": "9" * 64,
        }
        self.verification = {
            "schema": "hearthline.arc3.offline-candidate-verification.v4",
            "structural_verification": "PASS",
            "kaggle_stage_ready": True,
            "verified_snapshot": {
                "sha256": self.candidate["verified_snapshot_sha256"],
                "candidate_binding": dict(self.candidate),
            },
            "verified_inputs": {
                "source_lock_sha256": self.candidate["source_lock_sha256"],
                "runtime_inventory_sha256": hashlib.sha256(
                    RUNTIME_INVENTORY_BYTES
                ).hexdigest(),
                "runtime_review_receipt_sha256": "ad351aefdc18461bcf297d7095f8a77daa2641c583498cfad1b9f9b25a64206b",
                "runtime_closure_status": "FROZEN_POST_STAGE_SUCCESSOR",
                "public_source_arc_agi_repository": "arcprize/ARC-AGI",
                "public_source_arc_agi_commit": "f12822c4d550121c35a275008d964afbbed47d2f",
                "public_source_arc_agi_version": "0.9.9",
                "public_source_agents_repository": "arcprize/ARC-AGI-3-Agents",
                "public_source_agents_commit": "4743e7d0aaae0ded0d98a89a7e282e63564cd58b",
                "public_source_agents_tree": "6878fdfdd0156059323b541fc229b6329ad4fd28",
                "public_source_agents_files": dict(GATE.PUBLIC_AGENTS_FILES),
                "public_source_agents_license_file": dict(GATE.AGENTS_LICENSE_FILE),
                "kaggle_runtime_kernel_slug": "grativy6/hearthline-arc3-readiness",
                "kaggle_runtime_kernel_version": 4,
                "kaggle_runtime_stage_status": "COMPLETE",
                "kaggle_runtime_visibility": "private",
                "kaggle_runtime_internet_enabled": False,
                "kaggle_runtime_accelerator": "cpu",
                "kaggle_runtime_candidate_snapshot_sha256": "823cd5c7a99b16141959a09f011e361b2c03615ea37e72a65880a9eb5e8db4d0",
                "kaggle_runtime_evidence_manifest_sha256": "b4dd87fe2a0a17e8083bdcfb81a1be2b191fb45776e33e234d369c8918e93b06",
                "kaggle_runtime_logs_sha256": "1471812acc99ca75ca234ea7defd727128a43869bea26e4e91a8577dd062eb53",
                "kaggle_runtime_python_version": RUNTIME_INVENTORY["python_version"],
                "kaggle_runtime_distributions": copy.deepcopy(
                    RUNTIME_INVENTORY["distributions"]
                ),
                "kaggle_runtime_files": dict(RUNTIME_INVENTORY["agents_files"]),
                "kaggle_runtime_license_file": dict(
                    RUNTIME_INVENTORY["agents_license_file"]
                ),
                "kaggle_runtime_provenance_kind": "KAGGLE_PLATFORM_COMPETITION_INPUT",
                "kaggle_runtime_agents_repository": "arcprize/ARC-AGI-3-Agents",
                "kaggle_runtime_agents_commit": "135f20aaf44f13341ebc425666bf03b5cac58d3c",
                "kaggle_runtime_agents_tree": "d7fbafe6e2ed191189db89e5b571fd26da3dc375",
            },
        }
        self.private_records: dict[str, bytes] = {}
        self.clock_patch = mock.patch.object(GATE, "utc_now", return_value=self.NOW)
        self.verify_patch = mock.patch.object(
            GATE,
            "verify_current_candidate",
            side_effect=lambda _build: copy.deepcopy(self.verification),
        )
        self.private_patch = mock.patch.object(
            GATE,
            "read_private_record",
            side_effect=self._private_record,
        )
        self.clock_patch.start()
        self.verify_patch.start()
        self.private_patch.start()

    def tearDown(self) -> None:
        self.private_patch.stop()
        self.verify_patch.stop()
        self.clock_patch.stop()
        self.root_patch.stop()
        self.temporary.cleanup()

    def _private_record(self, path: Path, area: str, label: str) -> tuple[bytes, str]:
        del label
        reference = Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(GATE.ROOT))).as_posix()
        self.assertEqual(area, "receipts")
        return self.private_records[reference], reference

    def common(self, phase: str, grant_id: str, nonce: str) -> dict:
        issued = self.NOW - timedelta(minutes=5)
        return {
            "schema": "hearthline.arc3.human-grant.v3",
            "grant_id": grant_id,
            "phase": phase,
            "decision": "AUTHORIZE_ONCE",
            "human_actor": {"name": "Fixture Human", "attested_by_human": True},
            "issued_at": issued.isoformat(),
            "expires_at": (self.NOW + timedelta(minutes=30)).isoformat(),
            "nonce": nonce,
            "candidate": dict(self.candidate),
            "rules": {
                "locator": GATE.RULES_URL,
                "checked_at": self.NOW.date().isoformat(),
                "submissions_per_day": 1,
                "final_submissions": 2,
            },
            "acknowledgements": {},
            "stage_evidence": None,
        }

    def stage_grant(self, grant_id: str = "stage-grant-001", nonce: str = "a" * 32) -> dict:
        grant = self.common("KAGGLE_STAGE", grant_id, nonce)
        grant["acknowledgements"] = {
            "terms_and_eligibility_reviewed": True,
            "private_kernel_stage_only": True,
            "stage_does_not_authorize_competition_ignition": True,
            "account_slug": self.candidate["account_slug"],
            "kernel_id": self.candidate["kernel_id"],
        }
        return grant

    def competition_grant(
        self,
        receipt_sha: str,
        grant_id: str = "competition-grant-001",
        nonce: str = "b" * 32,
    ) -> dict:
        grant = self.common("COMPETITION_IGNITION", grant_id, nonce)
        grant["issued_at"] = (self.NOW - timedelta(minutes=2)).isoformat()
        grant["acknowledgements"] = {
            "stage_run_complete": True,
            "stage_output_reviewed": True,
            "remaining_daily_submission_confirmed": True,
            "manual_ui_only": True,
            "selected_output": "submission.parquet",
            "account_slug": self.candidate["account_slug"],
            "kernel_id": self.candidate["kernel_id"],
        }
        grant["stage_evidence"] = {
            "receipt_path": ".hearthline/receipts/stage.json",
            "receipt_sha256": receipt_sha,
        }
        return grant

    @staticmethod
    def encoded(document: dict) -> bytes:
        return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()

    def require_secure_consumption(self) -> None:
        if not GATE.secure_dirfd_available():
            self.skipTest("operational gate consumption requires POSIX no-follow directory descriptors")

    def consume_stage(self) -> tuple[dict, Path, bytes]:
        self.require_secure_consumption()
        grant = self.stage_grant()
        grant_bytes = self.encoded(grant)
        validated = GATE.validate_stage(grant, self.verification, self.NOW)
        with mock.patch.object(GATE, "utc_now", return_value=self.NOW - timedelta(minutes=4)):
            path = GATE.consume(validated, grant_bytes)
        return grant, path, grant_bytes

    def stage_receipt(self) -> dict:
        grant, consumption, grant_bytes = self.consume_stage()
        return {
            "schema": "hearthline.arc3.kaggle-stage-result.v4",
            "status": "COMPLETE",
            "candidate": dict(self.candidate),
            "kernel_id": self.candidate["kernel_id"],
            "kernel_run_id": "run-12345",
            "kernel_visibility": "PRIVATE",
            "internet_enabled": False,
            "output_reviewed": True,
            "submission": {"name": "submission.parquet", "sha256": "a" * 64},
            "recorded_by_human": True,
            "credential_material_recorded": False,
            "external_effect_performed_by_gate_tool": False,
            "gate_a": {
                "grant_id": grant["grant_id"],
                "nonce": grant["nonce"],
                "grant_sha256": hashlib.sha256(grant_bytes).hexdigest(),
                "consumption_receipt_path": GATE.canonical_consumption_reference(grant["grant_id"]),
                "consumption_receipt_sha256": hashlib.sha256(consumption.read_bytes()).hexdigest(),
                "account_slug": self.candidate["account_slug"],
                "kernel_id": self.candidate["kernel_id"],
            },
            "public_sources": GATE.expected_public_sources(self.verification),
            "accepted_runtime_binding": GATE.expected_accepted_runtime_binding(
                self.verification
            ),
            "stage_evidence": {
                "evidence_manifest_sha256": "c" * 64,
                "logs_sha256": "d" * 64,
            },
            "kaggle_runtime": GATE.expected_kaggle_runtime(self.verification),
            "recorded_at": (self.NOW - timedelta(minutes=3)).isoformat(),
            "claim_ceiling": "Human-recorded private stage only; local attestation is not a signature.",
        }

    def valid_competition(self) -> tuple[dict, bytes, GATE.ValidatedGate]:
        receipt = self.stage_receipt()
        receipt_bytes = self.encoded(receipt)
        self.private_records[".hearthline/receipts/stage.json"] = receipt_bytes
        grant = self.competition_grant(hashlib.sha256(receipt_bytes).hexdigest())
        validated = GATE.validate_competition(
            grant,
            self.verification,
            receipt,
            hashlib.sha256(receipt_bytes).hexdigest(),
            ".hearthline/receipts/stage.json",
            self.NOW,
        )
        return grant, receipt_bytes, validated

    def assert_competition_receipt_rejected(
        self,
        receipt: dict,
        pattern: str,
    ) -> None:
        receipt_bytes = self.encoded(receipt)
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        grant = self.competition_grant(receipt_sha)
        with self.assertRaisesRegex(GATE.GateError, pattern):
            GATE.validate_competition(
                grant,
                self.verification,
                receipt,
                receipt_sha,
                ".hearthline/receipts/stage.json",
                self.NOW,
            )

    def test_phase_a_exact_snapshot_contract_passes(self) -> None:
        result = GATE.validate_stage(self.stage_grant(), self.verification, self.NOW)
        self.assertEqual(result.phase, "KAGGLE_STAGE")
        self.assertEqual(result.gate_context["verified_snapshot_sha256"], "9" * 64)
        self.assertEqual(result.gate_context["rules_checked_day"], self.NOW.date().isoformat())
        self.assertEqual(
            GATE.parse_time(
                result.gate_context["authorization_expires_at"],
                "authorization expiry",
            ),
            self.NOW + timedelta(minutes=30),
        )

    def test_phase_a_rejects_placeholder_or_nonready_candidate(self) -> None:
        verification = dict(self.verification)
        verification["kaggle_stage_ready"] = False
        with self.assertRaisesRegex(GATE.GateError, "not ready for Kaggle staging"):
            GATE.validate_stage(self.stage_grant(), verification, self.NOW)

    def test_phase_a_rejects_missing_or_extra_v4_verified_inputs(self) -> None:
        missing = copy.deepcopy(self.verification)
        del missing["verified_inputs"]["kaggle_runtime_logs_sha256"]
        with self.assertRaisesRegex(GATE.GateError, "verified successor inputs fields"):
            GATE.validate_stage(self.stage_grant(), missing, self.NOW)

        extra = copy.deepcopy(self.verification)
        extra["verified_inputs"]["unreviewed_extension"] = True
        with self.assertRaisesRegex(GATE.GateError, "verified successor inputs fields"):
            GATE.validate_stage(self.stage_grant(), extra, self.NOW)

    def test_phase_a_rejects_extra_wrong_account_and_boolean_rule(self) -> None:
        grant = self.stage_grant()
        grant["acknowledgements"]["competition_ignition"] = True
        with self.assertRaises(GATE.GateError):
            GATE.validate_stage(grant, self.verification, self.NOW)
        grant = self.stage_grant()
        grant["acknowledgements"]["account_slug"] = "other-user"
        with self.assertRaisesRegex(GATE.GateError, "account differs"):
            GATE.validate_stage(grant, self.verification, self.NOW)
        grant = self.stage_grant()
        grant["rules"]["submissions_per_day"] = True
        with self.assertRaisesRegex(GATE.GateError, "integer one"):
            GATE.validate_stage(grant, self.verification, self.NOW)

    def test_phase_b_binds_exact_gate_a_account_kernel_and_receipt(self) -> None:
        receipt = self.stage_receipt()
        receipt_bytes = self.encoded(receipt)
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        grant = self.competition_grant(receipt_sha)
        result = GATE.validate_competition(
            grant, self.verification, receipt, receipt_sha,
            ".hearthline/receipts/stage.json", self.NOW,
        )
        self.assertEqual(result.submission_sha256, "a" * 64)
        grant["acknowledgements"]["account_slug"] = "different-user"
        with self.assertRaisesRegex(GATE.GateError, "account differs"):
            GATE.validate_competition(
                grant, self.verification, receipt, receipt_sha,
                ".hearthline/receipts/stage.json", self.NOW,
            )

    def test_real_pre_stage_candidate_keeps_gate_b_closed(self) -> None:
        receipt = self.stage_receipt()
        receipt_bytes = self.encoded(receipt)
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        grant = self.competition_grant(receipt_sha)
        self.verification["verified_inputs"]["runtime_closure_status"] = (
            "UNFROZEN_PENDING_GATE_A_SUCCESSOR"
        )
        with self.assertRaisesRegex(GATE.GateError, "RUNTIME_CLOSURE_UNFROZEN"):
            GATE.validate_competition(
                grant,
                self.verification,
                receipt,
                receipt_sha,
                ".hearthline/receipts/stage.json",
                self.NOW,
            )

    def test_phase_b_rejects_different_stage_kernel_and_gate_a_hash(self) -> None:
        receipt = self.stage_receipt()
        receipt_bytes = self.encoded(receipt)
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        grant = self.competition_grant(receipt_sha)
        receipt["kernel_id"] = "other-user/hearthline-arc3-readiness"
        with self.assertRaisesRegex(GATE.GateError, "stage kernel differs"):
            GATE.validate_competition(
                grant, self.verification, receipt, receipt_sha,
                ".hearthline/receipts/stage.json", self.NOW,
            )
        receipt["kernel_id"] = self.candidate["kernel_id"]
        receipt["gate_a"]["grant_sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.GateError, "grant hash mismatch"):
            GATE.validate_competition(
                grant, self.verification, receipt, receipt_sha,
                ".hearthline/receipts/stage.json", self.NOW,
            )

    def test_fabricated_or_missing_gate_a_chain_is_rejected(self) -> None:
        self.consumed_root.mkdir(parents=True)
        fake = self.consumed_root / ("f" * 64 + ".json")
        fake.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(GATE.GateError, "without a ledger"):
            GATE.consumption_records()
        unvalidated = GATE.ValidatedGate(
            phase="KAGGLE_STAGE",
            candidate=dict(self.candidate),
            grant_id="fake-stage-001",
            nonce="f" * 32,
            gate_context={},
            grant_semantic_sha256="0" * 64,
            issued_at=self.NOW,
            expires_at=self.NOW + timedelta(minutes=1),
            rules_checked_day=self.NOW.date().isoformat(),
        )
        with self.assertRaisesRegex(GATE.GateError, "not produced by this validation process"):
            GATE.consume(unvalidated, b"fake")

    def test_one_gate_b_per_utc_day(self) -> None:
        grant, _, validated = self.valid_competition()
        GATE.consume(validated, self.encoded(grant))
        second = self.competition_grant(
            "f" * 64,
            grant_id="competition-grant-002",
            nonce="c" * 32,
        )
        with self.assertRaisesRegex(GATE.GateError, "already consumed on this UTC day"):
            GATE.validate_common(second, "COMPETITION_IGNITION", self.candidate, self.NOW)

    def test_gate_b_cannot_span_a_utc_midnight(self) -> None:
        near_midnight = datetime(2026, 9, 4, 23, 59, tzinfo=UTC)
        stage = self.stage_grant()
        stage["issued_at"] = (near_midnight - timedelta(minutes=1)).isoformat()
        stage["expires_at"] = (near_midnight + timedelta(minutes=2)).isoformat()
        stage["rules"]["checked_at"] = near_midnight.date().isoformat()
        with self.assertRaisesRegex(GATE.GateError, "stay on one UTC day"):
            GATE.validate_common(
                stage,
                "KAGGLE_STAGE",
                self.candidate,
                near_midnight,
            )

        grant = self.competition_grant("f" * 64)
        grant["issued_at"] = (near_midnight - timedelta(minutes=1)).isoformat()
        grant["expires_at"] = (near_midnight + timedelta(minutes=2)).isoformat()
        grant["rules"]["checked_at"] = near_midnight.date().isoformat()
        with self.assertRaisesRegex(GATE.GateError, "stay on one UTC day"):
            GATE.validate_common(
                grant,
                "COMPETITION_IGNITION",
                self.candidate,
                near_midnight,
            )

        grant["expires_at"] = near_midnight.replace(
            hour=23, minute=59, second=59, microsecond=999999
        ).isoformat()
        issued, expires = GATE.validate_common(
            grant,
            "COMPETITION_IGNITION",
            self.candidate,
            near_midnight,
        )
        self.assertEqual(issued.date(), expires.date())

    def test_gate_b_rejects_stage_recorded_after_gate_a_expiry(self) -> None:
        receipt = self.stage_receipt()
        receipt["recorded_at"] = (self.NOW + timedelta(minutes=31)).isoformat()
        receipt_bytes = self.encoded(receipt)
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        grant = self.competition_grant(receipt_sha)
        with self.assertRaisesRegex(GATE.GateError, "at or after Gate A authorization expiry"):
            GATE.validate_competition(
                grant,
                self.verification,
                receipt,
                receipt_sha,
                ".hearthline/receipts/stage.json",
                self.NOW,
            )

        receipt["recorded_at"] = (self.NOW + timedelta(minutes=30)).isoformat()
        receipt_bytes = self.encoded(receipt)
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        grant = self.competition_grant(receipt_sha)
        with self.assertRaisesRegex(GATE.GateError, "at or after Gate A authorization expiry"):
            GATE.validate_competition(
                grant,
                self.verification,
                receipt,
                receipt_sha,
                ".hearthline/receipts/stage.json",
                self.NOW,
            )

    def test_gate_b_rejects_stage_recorded_at_gate_a_consumption(self) -> None:
        receipt = self.stage_receipt()
        ledger = json.loads(
            (self.consumed_root / "ledger.json").read_text(encoding="utf-8")
        )
        gate_a_record = json.loads(
            (self.consumed_root / ledger["records"][0]["path"]).read_text(
                encoding="utf-8"
            )
        )
        receipt["recorded_at"] = gate_a_record["consumed_at"]
        receipt_bytes = self.encoded(receipt)
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        grant = self.competition_grant(receipt_sha)
        with self.assertRaisesRegex(GATE.GateError, "strictly follow"):
            GATE.validate_competition(
                grant,
                self.verification,
                receipt,
                receipt_sha,
                ".hearthline/receipts/stage.json",
                self.NOW,
            )

    def test_grant_id_and_nonce_are_each_single_use(self) -> None:
        self.require_secure_consumption()
        first = GATE.validate_stage(self.stage_grant(), self.verification, self.NOW)
        GATE.consume(first, self.encoded(self.stage_grant()))
        with self.assertRaisesRegex(GATE.GateError, "grant_id is already consumed"):
            GATE.assert_not_consumed(first.grant_id, "c" * 32)
        with self.assertRaisesRegex(GATE.GateError, "grant nonce is already consumed"):
            GATE.assert_not_consumed("different-grant-001", first.nonce)

    def test_consumption_rejects_unrelated_bytes_tampering_and_stale_time(self) -> None:
        self.require_secure_consumption()
        grant = self.stage_grant()
        validated = GATE.validate_stage(grant, self.verification, self.NOW)
        unrelated = self.stage_grant(grant_id="stage-grant-other", nonce="f" * 32)
        with self.assertRaisesRegex(GATE.GateError, "do not match the validated grant"):
            GATE.consume(validated, self.encoded(unrelated))

        tampered = GATE.validate_stage(grant, self.verification, self.NOW)
        object.__setattr__(tampered, "grant_id", "stage-grant-mutated")
        with self.assertRaisesRegex(GATE.GateError, "altered after validation"):
            GATE.consume(tampered, self.encoded(grant))

        expired = GATE.validate_stage(grant, self.verification, self.NOW)
        with mock.patch.object(GATE, "utc_now", return_value=self.NOW + timedelta(hours=1)):
            with self.assertRaisesRegex(GATE.GateError, "not currently active"):
                GATE.consume(expired, self.encoded(grant))

    def test_public_factory_cannot_forge_a_validated_gate(self) -> None:
        self.require_secure_consumption()
        forged_grant = {
            "grant_id": "forged-stage-001",
            "nonce": "e" * 32,
            "rules": {"checked_at": self.NOW.date().isoformat()},
        }
        forged = GATE.make_validated_gate(
            grant=forged_grant,
            phase="KAGGLE_STAGE",
            candidate=dict(self.candidate),
            gate_context={
                "account_slug": self.candidate["account_slug"],
                "kernel_id": self.candidate["kernel_id"],
                "verified_snapshot_sha256": self.candidate["verified_snapshot_sha256"],
            },
            issued_at=self.NOW - timedelta(minutes=1),
            expires_at=self.NOW + timedelta(minutes=1),
        )
        with self.assertRaisesRegex(GATE.GateError, "grant fields"):
            GATE.consume(forged, self.encoded(forged_grant))

    def test_full_raw_phase_validation_runs_under_ledger_lock(self) -> None:
        self.require_secure_consumption()
        grant = self.stage_grant()
        validated = GATE.validate_stage(grant, self.verification, self.NOW)
        original_validate = GATE.validate_stage
        lock_observations: list[bool] = []

        def observe_locked_validation(*args, **kwargs):
            lock_observations.append((self.consumed_root / ".ledger.lock").is_dir())
            return original_validate(*args, **kwargs)

        with mock.patch.object(GATE, "validate_stage", side_effect=observe_locked_validation):
            GATE.consume(validated, self.encoded(grant))
        self.assertEqual(lock_observations, [True])

    def test_gate_b_rechecks_gate_a_under_lock(self) -> None:
        grant, _, validated = self.valid_competition()
        ledger_path = self.consumed_root / "ledger.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        record_path = self.consumed_root / ledger["records"][0]["path"]
        original_open = GATE._open_directory_chain
        mutated = False

        def mutate_before_lock(path: Path, *, create: bool = False):
            nonlocal mutated
            if create and Path(path) == self.consumed_root and not mutated:
                mutated = True
                record = json.loads(record_path.read_text(encoding="utf-8"))
                record["grant_sha256"] = "f" * 64
                record_bytes = self.encoded(record)
                record_path.write_bytes(record_bytes)
                record_hash = hashlib.sha256(record_bytes).hexdigest()
                ledger["records"][0]["sha256"] = record_hash
                ledger["head_sha256"] = record_hash
                ledger_path.write_bytes(self.encoded(ledger))
            return original_open(path, create=create)

        with mock.patch.object(GATE, "_open_directory_chain", side_effect=mutate_before_lock):
            with self.assertRaisesRegex(GATE.GateError, "Gate A consumption receipt hash"):
                GATE.consume(validated, self.encoded(grant))

    def test_gate_b_runtime_distribution_inventory_is_exact_and_ordered(self) -> None:
        baseline = self.stage_receipt()
        version_drift = copy.deepcopy(baseline)
        arc_agi = next(
            row
            for row in version_drift["kaggle_runtime"]["distributions"]
            if row["name"] == "arc-agi"
        )
        arc_agi["version"] = "0.9.9"
        order_drift = copy.deepcopy(baseline)
        distributions = order_drift["kaggle_runtime"]["distributions"]
        distributions[0], distributions[1] = distributions[1], distributions[0]
        count_drift = copy.deepcopy(baseline)
        count_drift["kaggle_runtime"]["distributions"].pop()
        for label, receipt in (
            ("version", version_drift),
            ("order", order_drift),
            ("count", count_drift),
        ):
            with self.subTest(label=label):
                self.assert_competition_receipt_rejected(
                    receipt,
                    "distribution inventory or order differs",
                )

    def test_gate_b_runtime_python_is_exact(self) -> None:
        receipt = self.stage_receipt()
        receipt["kaggle_runtime"]["python_version"] = "3.12.14"
        self.assert_competition_receipt_rejected(
            receipt,
            "Python version differs",
        )

    def test_gate_b_runtime_files_and_license_are_exact(self) -> None:
        baseline = self.stage_receipt()
        file_drift = copy.deepcopy(baseline)
        file_drift["kaggle_runtime"]["agents"]["files"]["agents/agent.py"] = "0" * 64
        license_drift = copy.deepcopy(baseline)
        license_drift["kaggle_runtime"]["agents"]["license_file"]["LICENSE"] = "0" * 64
        for label, receipt, pattern in (
            ("file", file_drift, "Agents files differ"),
            ("license", license_drift, "Agents license differs"),
        ):
            with self.subTest(label=label):
                self.assert_competition_receipt_rejected(receipt, pattern)

    def test_gate_b_public_and_runtime_agents_cannot_be_conflated(self) -> None:
        baseline = self.stage_receipt()
        public_replaced_by_runtime = copy.deepcopy(baseline)
        public_replaced_by_runtime["public_sources"]["agents"]["files"] = dict(
            baseline["kaggle_runtime"]["agents"]["files"]
        )
        self.assert_competition_receipt_rejected(
            public_replaced_by_runtime,
            "public source identities differ",
        )

        runtime_replaced_by_public = copy.deepcopy(baseline)
        runtime_replaced_by_public["kaggle_runtime"]["agents"]["files"] = dict(
            baseline["public_sources"]["agents"]["files"]
        )
        self.assert_competition_receipt_rejected(
            runtime_replaced_by_public,
            "runtime Agents files differ",
        )

    def test_gate_b_requires_runtime_human_review_and_accepted_binding(self) -> None:
        baseline = self.stage_receipt()
        missing_review = copy.deepcopy(baseline)
        missing_review["kaggle_runtime"]["reviewed_by_human"] = False
        self.assert_competition_receipt_rejected(
            missing_review,
            "runtime inventory human review required",
        )

        inventory_hash_drift = copy.deepcopy(baseline)
        inventory_hash_drift["accepted_runtime_binding"]["inventory_sha256"] = "0" * 64
        self.assert_competition_receipt_rejected(
            inventory_hash_drift,
            "accepted runtime binding differs",
        )

        review_hash_drift = copy.deepcopy(baseline)
        review_hash_drift["accepted_runtime_binding"]["human_review_receipt_sha256"] = "0" * 64
        self.assert_competition_receipt_rejected(
            review_hash_drift,
            "accepted runtime binding differs",
        )

        for field in (
            "baseline_evidence_manifest_sha256",
            "baseline_logs_sha256",
        ):
            with self.subTest(stage_receipt_field=field):
                evidence_hash_drift = copy.deepcopy(baseline)
                evidence_hash_drift["accepted_runtime_binding"][field] = "0" * 64
                self.assert_competition_receipt_rejected(
                    evidence_hash_drift,
                    "accepted runtime binding differs",
                )

    def test_gate_b_requires_distinct_well_formed_new_run_stage_evidence(self) -> None:
        baseline = self.stage_receipt()
        missing = copy.deepcopy(baseline)
        del missing["stage_evidence"]["logs_sha256"]
        extra = copy.deepcopy(baseline)
        extra["stage_evidence"]["unreviewed_field"] = "0" * 64
        malformed_manifest = copy.deepcopy(baseline)
        malformed_manifest["stage_evidence"]["evidence_manifest_sha256"] = (
            "not-a-hash"
        )
        malformed_logs = copy.deepcopy(baseline)
        malformed_logs["stage_evidence"]["logs_sha256"] = "not-a-hash"
        reused_baseline_manifest = copy.deepcopy(baseline)
        reused_baseline_manifest["stage_evidence"]["evidence_manifest_sha256"] = (
            baseline["accepted_runtime_binding"][
                "baseline_evidence_manifest_sha256"
            ]
        )
        for label, receipt, pattern in (
            ("missing", missing, "new-run stage evidence fields"),
            ("extra", extra, "new-run stage evidence fields"),
            ("manifest format", malformed_manifest, "evidence manifest SHA-256"),
            ("logs format", malformed_logs, "logs SHA-256"),
            (
                "baseline manifest reuse",
                reused_baseline_manifest,
                "must differ from the accepted baseline manifest",
            ),
        ):
            with self.subTest(label=label):
                self.assert_competition_receipt_rejected(receipt, pattern)

        same_logs_are_allowed = copy.deepcopy(baseline)
        same_logs_are_allowed["stage_evidence"]["logs_sha256"] = baseline[
            "accepted_runtime_binding"
        ]["baseline_logs_sha256"]
        receipt_bytes = self.encoded(same_logs_are_allowed)
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        grant = self.competition_grant(receipt_sha)
        validated = GATE.validate_competition(
            grant,
            self.verification,
            same_logs_are_allowed,
            receipt_sha,
            ".hearthline/receipts/stage.json",
            self.NOW,
        )
        self.assertEqual(validated.phase, "COMPETITION_IGNITION")

    def test_verified_runtime_inventory_is_canonical_unique_complete_and_sorted(self) -> None:
        baseline = copy.deepcopy(self.verification)
        malformed = copy.deepcopy(baseline)
        malformed["verified_inputs"]["kaggle_runtime_distributions"][0]["name"] = "Bad.Name"
        duplicate = copy.deepcopy(baseline)
        duplicate["verified_inputs"]["kaggle_runtime_distributions"][1]["name"] = (
            duplicate["verified_inputs"]["kaggle_runtime_distributions"][0]["name"]
        )
        incomplete = copy.deepcopy(baseline)
        incomplete["verified_inputs"]["kaggle_runtime_distributions"].pop()
        unsorted = copy.deepcopy(baseline)
        rows = unsorted["verified_inputs"]["kaggle_runtime_distributions"]
        rows[0], rows[1] = rows[1], rows[0]
        direct_version_drift = copy.deepcopy(baseline)
        dotenv = next(
            row
            for row in direct_version_drift["verified_inputs"]["kaggle_runtime_distributions"]
            if row["name"] == "python-dotenv"
        )
        dotenv["version"] = "1.2.1"
        for label, verification, pattern in (
            ("canonical", malformed, "canonical distribution name"),
            ("unique", duplicate, "distribution names must be unique"),
            ("complete", incomplete, "exactly 875 distributions"),
            ("sorted", unsorted, "deterministic name order"),
            ("direct version", direct_version_drift, "direct versions"),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(GATE.GateError, pattern):
                    GATE.verified_inputs_v4(verification)

    def test_verified_runtime_machine_evidence_hashes_are_exact(self) -> None:
        for key, pattern in (
            (
                "kaggle_runtime_evidence_manifest_sha256",
                "evidence manifest hash differs",
            ),
            ("kaggle_runtime_logs_sha256", "logs hash differs"),
        ):
            with self.subTest(key=key):
                verification = copy.deepcopy(self.verification)
                verification["verified_inputs"][key] = "0" * 64
                with self.assertRaisesRegex(GATE.GateError, pattern):
                    GATE.verified_inputs_v4(verification)

        malformed = copy.deepcopy(self.verification)
        malformed["verified_inputs"]["kaggle_runtime_logs_sha256"] = "not-a-hash"
        with self.assertRaisesRegex(GATE.GateError, "logs SHA-256"):
            GATE.verified_inputs_v4(malformed)

    def test_verified_runtime_inventory_and_review_receipt_hashes_are_exact(self) -> None:
        for key, pattern in (
            ("runtime_inventory_sha256", "runtime inventory hash differs"),
            (
                "runtime_review_receipt_sha256",
                "runtime review receipt hash differs",
            ),
        ):
            with self.subTest(key=key):
                verification = copy.deepcopy(self.verification)
                verification["verified_inputs"][key] = "0" * 64
                with self.assertRaisesRegex(GATE.GateError, pattern):
                    GATE.verified_inputs_v4(verification)

    def test_verified_runtime_inventory_is_reconstructed_before_acceptance(self) -> None:
        verification = copy.deepcopy(self.verification)
        transitive = next(
            row
            for row in verification["verified_inputs"]["kaggle_runtime_distributions"]
            if row["name"] == "a2a-sdk"
        )
        transitive["version"] = "0.3.27"
        with self.assertRaisesRegex(GATE.GateError, "inventory content hash differs"):
            GATE.verified_inputs_v4(verification)

    def test_candidate_kernel_and_accelerator_match_reviewed_runtime(self) -> None:
        different_kernel = copy.deepcopy(self.verification)
        candidate = different_kernel["verified_snapshot"]["candidate_binding"]
        candidate["account_slug"] = "other-user"
        candidate["kernel_id"] = "other-user/hearthline-arc3-readiness"
        with self.assertRaisesRegex(GATE.GateError, "candidate kernel differs"):
            GATE.verified_inputs_v4(different_kernel)

        different_accelerator = copy.deepcopy(self.verification)
        different_accelerator["verified_snapshot"]["candidate_binding"][
            "accelerator"
        ] = "t4"
        with self.assertRaisesRegex(GATE.GateError, "candidate accelerator differs"):
            GATE.verified_inputs_v4(different_accelerator)

    def test_gate_b_ledger_day_and_parent_are_replayed_fail_closed(self) -> None:
        grant, _, validated = self.valid_competition()
        GATE.consume(validated, self.encoded(grant))
        ledger_path = self.consumed_root / "ledger.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        gate_b_path = self.consumed_root / ledger["records"][1]["path"]
        gate_b = json.loads(gate_b_path.read_text(encoding="utf-8"))
        gate_b["gate_context"]["utc_submission_day"] = "2026-09-03"
        gate_b_bytes = self.encoded(gate_b)
        gate_b_path.write_bytes(gate_b_bytes)
        gate_b_hash = hashlib.sha256(gate_b_bytes).hexdigest()
        ledger["records"][1]["sha256"] = gate_b_hash
        ledger["head_sha256"] = gate_b_hash
        ledger_path.write_bytes(self.encoded(ledger))
        with self.assertRaisesRegex(GATE.GateError, "day/consumption mismatch"):
            GATE.load_consumption_ledger()

        # Make the record internally valid again but orphan its Gate A parent.
        gate_b["gate_context"]["utc_submission_day"] = self.NOW.date().isoformat()
        gate_b["sequence"] = 1
        gate_b["previous_record_sha256"] = None
        gate_b_bytes = self.encoded(gate_b)
        gate_b_path.write_bytes(gate_b_bytes)
        gate_b_hash = hashlib.sha256(gate_b_bytes).hexdigest()
        gate_a_path = self.consumed_root / ledger["records"][0]["path"]
        gate_a_path.unlink()
        orphan_ledger = {
            "schema": "hearthline.arc3.gate-consumption-ledger.v1",
            "record_count": 1,
            "head_sha256": gate_b_hash,
            "records": [{"sequence": 1, "path": gate_b_path.name, "sha256": gate_b_hash}],
        }
        ledger_path.write_bytes(self.encoded(orphan_ledger))
        with self.assertRaisesRegex(GATE.GateError, "no unique earlier Gate A parent"):
            GATE.load_consumption_ledger()

    def test_rehashed_duplicate_gate_b_day_fails_closed_on_replay(self) -> None:
        grant, _, validated = self.valid_competition()
        GATE.consume(validated, self.encoded(grant))
        ledger_path = self.consumed_root / "ledger.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        prior_entry = ledger["records"][-1]
        prior_record = json.loads(
            (self.consumed_root / prior_entry["path"]).read_text(encoding="utf-8")
        )
        duplicate = copy.deepcopy(prior_record)
        duplicate["sequence"] = len(ledger["records"]) + 1
        duplicate["previous_record_sha256"] = prior_entry["sha256"]
        duplicate["grant_id"] = "competition-grant-duplicate-day"
        duplicate["nonce"] = "d" * 32
        duplicate_bytes = self.encoded(duplicate)
        duplicate_hash = hashlib.sha256(duplicate_bytes).hexdigest()
        duplicate_name = Path(
            GATE.canonical_consumption_reference(duplicate["grant_id"])
        ).name
        (self.consumed_root / duplicate_name).write_bytes(duplicate_bytes)
        ledger["record_count"] = duplicate["sequence"]
        ledger["head_sha256"] = duplicate_hash
        ledger["records"].append(
            {
                "sequence": duplicate["sequence"],
                "path": duplicate_name,
                "sha256": duplicate_hash,
            }
        )
        ledger_path.write_bytes(self.encoded(ledger))
        with self.assertRaisesRegex(GATE.GateError, "duplicate Gate B UTC"):
            GATE.load_consumption_ledger()

    def test_overlapping_consumption_allows_exactly_one(self) -> None:
        self.require_secure_consumption()
        first_grant = self.stage_grant(grant_id="stage-grant-001", nonce="d" * 32)
        second_grant = self.stage_grant(grant_id="stage-grant-002", nonce="e" * 32)
        first = GATE.validate_stage(first_grant, self.verification, self.NOW)
        second = GATE.validate_stage(second_grant, self.verification, self.NOW)
        grant_bytes = {
            first.grant_id: self.encoded(first_grant),
            second.grant_id: self.encoded(second_grant),
        }

        def attempt(result: GATE.ValidatedGate) -> str:
            try:
                GATE.consume(result, grant_bytes[result.grant_id])
            except GATE.GateError:
                return "blocked"
            return "written"

        # A pool alone does not prove overlap: a fast first transaction may
        # release the directory lock before the second worker is scheduled. Hold
        # the first transaction immediately after lock acquisition so this test
        # measures mutual exclusion rather than scheduler timing.
        lock_acquired = concurrent.futures.Future()
        release_lock = concurrent.futures.Future()
        real_load = GATE.load_consumption_ledger

        def hold_first_locked_load(*args, **kwargs):
            if kwargs.get("lock_owned") and not lock_acquired.done():
                lock_acquired.set_result(None)
                release_lock.result(timeout=5)
            return real_load(*args, **kwargs)

        with mock.patch.object(
            GATE,
            "load_consumption_ledger",
            side_effect=hold_first_locked_load,
        ):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                first_future = pool.submit(attempt, first)
                try:
                    lock_acquired.result(timeout=5)
                    second_future = pool.submit(attempt, second)
                    second_outcome = second_future.result(timeout=5)
                finally:
                    if not release_lock.done():
                        release_lock.set_result(None)
                first_outcome = first_future.result(timeout=5)

        outcomes = [first_outcome, second_outcome]
        self.assertEqual(sorted(outcomes), ["blocked", "written"])
        records = GATE.consumption_records()
        self.assertEqual(len(records), 1)

    def test_distinct_valid_grants_can_serialize_sequentially(self) -> None:
        self.require_secure_consumption()
        first_grant = self.stage_grant(grant_id="stage-grant-001", nonce="d" * 32)
        second_grant = self.stage_grant(grant_id="stage-grant-002", nonce="e" * 32)
        first = GATE.validate_stage(first_grant, self.verification, self.NOW)
        second = GATE.validate_stage(second_grant, self.verification, self.NOW)

        GATE.consume(first, self.encoded(first_grant))
        GATE.consume(second, self.encoded(second_grant))

        records = GATE.consumption_records()
        self.assertEqual([record["grant_id"] for record in records], [
            "stage-grant-001",
            "stage-grant-002",
        ])
        self.assertEqual([record["sequence"] for record in records], [1, 2])

    def test_unsupported_gate_host_fails_closed_before_consumption(self) -> None:
        grant = self.stage_grant()
        validated = GATE.validate_stage(grant, self.verification, self.NOW)
        with mock.patch.object(GATE, "secure_dirfd_available", return_value=False):
            with self.assertRaisesRegex(GATE.GateError, "require Linux/POSIX"):
                GATE.consume(validated, self.encoded(grant))

    def test_partial_malformed_duplicate_and_broken_chain_fail_closed(self) -> None:
        self.consumed_root.mkdir(parents=True)
        (self.consumed_root / ".pending-fixture.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(GATE.GateError, "partial consumption"):
            GATE.consumption_records()
        (self.consumed_root / ".pending-fixture.json").unlink()
        (self.consumed_root / "ledger.json").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(GATE.GateError, "invalid strict"):
            GATE.consumption_records()
        (self.consumed_root / "ledger.json").write_text(
            '{"schema":"x","schema":"y","record_count":0,"head_sha256":null,"records":[]}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(GATE.GateError, "duplicate JSON key"):
            GATE.consumption_records()
        (self.consumed_root / "ledger.json").write_text(
            '{"schema":"hearthline.arc3.gate-consumption-ledger.v1","record_count":NaN,"head_sha256":null,"records":[]}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(GATE.GateError, "non-finite JSON number"):
            GATE.consumption_records()

    def test_strict_json_rejects_exponent_overflow_nonfinite(self) -> None:
        with self.assertRaisesRegex(GATE.GateError, "non-finite JSON number"):
            GATE.loads_strict(b'{"overflow":1e999}', "overflow fixture")

    def test_gate_never_executes_an_uncommitted_candidate_verifier(self) -> None:
        root = Path(self.temporary.name) / "verifier-root"
        scripts = root / "scripts"
        scripts.mkdir(parents=True)
        marker = root / "UNCOMMITTED_PAYLOAD_EXECUTED"
        malicious = (
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        ).encode("utf-8")
        safe_committed = b"def verify(*args, **kwargs):\n    return {}\n"
        (scripts / "verify_candidate.py").write_bytes(malicious)
        clean = {"commit": "1" * 40, "tree": "2" * 40, "worktree_clean": True}
        with mock.patch.object(GATE, "ROOT", root), mock.patch.object(
            GATE, "_git_identity", return_value=clean
        ), mock.patch.object(
            GATE, "_git_blob", return_value=safe_committed
        ):
            with self.assertRaisesRegex(GATE.GateError, "differs from committed Git object"):
                REAL_VERIFY_CURRENT_CANDIDATE(root / "build")
        self.assertFalse(marker.exists())

    def test_gate_binds_git_identity_across_candidate_verification(self) -> None:
        verifier = b"def verify(*args, **kwargs):\n    return {}\n"
        initial = {"commit": "1" * 40, "tree": "2" * 40, "worktree_clean": True}
        rebound = {"commit": "3" * 40, "tree": "4" * 40, "worktree_clean": True}
        with mock.patch.object(
            GATE,
            "_committed_verifier_bytes",
            side_effect=[(verifier, initial), (verifier, rebound)],
        ):
            with self.assertRaisesRegex(
                GATE.GateError,
                "Git identity changed during candidate verification",
            ):
                REAL_VERIFY_CURRENT_CANDIDATE(Path(self.temporary.name) / "build")

        mismatched = copy.deepcopy(self.verification)
        mismatched["verified_snapshot"]["candidate_binding"]["commit"] = "9" * 40
        verifier = (
            "def verify(*args, **kwargs):\n"
            f"    return {mismatched!r}\n"
        ).encode("utf-8")
        with mock.patch.object(
            GATE,
            "_committed_verifier_bytes",
            side_effect=[(verifier, initial), (verifier, initial)],
        ):
            with self.assertRaisesRegex(
                GATE.GateError,
                "verification result differs from the bound Git identity",
            ):
                REAL_VERIFY_CURRENT_CANDIDATE(Path(self.temporary.name) / "build")

    @unittest.skipUnless(hasattr(os, "symlink") and GATE.secure_dirfd_available(), "requires POSIX no-follow directory descriptors")
    def test_private_record_rejects_parent_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            test_root = Path(temp) / "repo"
            outside = Path(temp) / "outside"
            test_root.mkdir()
            (outside / "receipts").mkdir(parents=True)
            (outside / "receipts" / "stage.json").write_text("{}", encoding="utf-8")
            os.symlink(outside, test_root / ".hearthline", target_is_directory=True)
            with mock.patch.object(GATE, "ROOT", test_root):
                with self.assertRaises((OSError, GATE.GateError)):
                    REAL_READ_PRIVATE_RECORD(
                        test_root / ".hearthline" / "receipts" / "stage.json",
                        "receipts",
                        "stage receipt",
                    )

    def test_schema_contains_closed_phase_conditionals(self) -> None:
        schema = json.loads((ROOT / "launch/schemas/v2/human-grant.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(len(schema["allOf"]), 2)
        for conditional in schema["allOf"]:
            acknowledgement = conditional["then"]["properties"]["acknowledgements"]
            self.assertFalse(acknowledgement["additionalProperties"])

    def test_stage_result_v4_schema_is_closed_and_keeps_old_files_unchanged(self) -> None:
        old_template = ROOT / "launch/gates/stage-result.v2.template.json"
        old_schema = ROOT / "launch/schemas/v2/stage-result.schema.json"
        self.assertEqual(
            hashlib.sha256(old_template.read_bytes()).hexdigest(),
            "262cb026ed8bc12e80b05bcd7d4eef0c4b166ed8919cd65766176d6ad09fa206",
        )
        self.assertEqual(
            hashlib.sha256(old_schema.read_bytes()).hexdigest(),
            "e2e876518f834567a1bf6518d3ce2fd99cc568b178bd02fc753d8243036b639a",
        )

        schema = json.loads(
            (ROOT / "launch/schemas/v4/stage-result.schema.json").read_text(
                encoding="utf-8"
            )
        )
        template = json.loads(
            (ROOT / "launch/gates/stage-result.v4.template.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            schema["$id"],
            "https://github.com/Grativy6/hearthline-plays/launch/schemas/v4/stage-result.schema.json",
        )
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            "hearthline.arc3.kaggle-stage-result.v4",
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(template))
        for key in (
            "candidate", "submission", "gate_a", "public_sources",
            "accepted_runtime_binding", "stage_evidence", "kaggle_runtime",
        ):
            self.assertFalse(schema["properties"][key]["additionalProperties"])
        accepted_runtime_binding = schema["properties"][
            "accepted_runtime_binding"
        ]
        self.assertEqual(
            set(accepted_runtime_binding["required"]),
            {
                "status", "inventory_sha256", "human_review_receipt_sha256",
                "baseline_evidence_manifest_sha256", "baseline_logs_sha256",
            },
        )
        stage_evidence = schema["properties"]["stage_evidence"]
        self.assertEqual(
            set(stage_evidence["required"]),
            {"evidence_manifest_sha256", "logs_sha256"},
        )
        for key in stage_evidence["required"]:
            self.assertEqual(
                stage_evidence["properties"][key],
                {"$ref": "#/$defs/sha256"},
            )
        distributions = schema["properties"]["kaggle_runtime"]["properties"]["distributions"]
        self.assertEqual(distributions["minItems"], 875)
        self.assertEqual(distributions["maxItems"], 875)
        self.assertIn("exact content and order", distributions["$comment"])

        def assert_every_object_schema_is_closed(node, path: str = "$") -> None:
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(
                        node.get("additionalProperties"),
                        False,
                        f"open object schema at {path}",
                    )
                for key, value in node.items():
                    assert_every_object_schema_is_closed(value, f"{path}/{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    assert_every_object_schema_is_closed(value, f"{path}/{index}")

        assert_every_object_schema_is_closed(schema)
        public_agent = schema["$defs"]["agentsPublicFiles"]["properties"]["agents/agent.py"]["const"]
        runtime_agent = schema["$defs"]["agentsRuntimeFiles"]["properties"]["agents/agent.py"]["const"]
        self.assertEqual(public_agent, GATE.PUBLIC_AGENTS_FILES["agents/agent.py"])
        self.assertEqual(runtime_agent, GATE.KAGGLE_RUNTIME_FILES["agents/agent.py"])
        self.assertNotEqual(public_agent, runtime_agent)

    def test_populated_stage_result_v4_validates_against_schema(self) -> None:
        try:
            from jsonschema import Draft202012Validator, FormatChecker
        except ImportError:
            self.skipTest("jsonschema is unavailable on this test host")
        schema = json.loads(
            (ROOT / "launch/schemas/v4/stage-result.schema.json").read_text(
                encoding="utf-8"
            )
        )
        receipt = self.stage_receipt()
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(receipt)
        self.assertEqual(len(receipt["kaggle_runtime"]["distributions"]), 875)


if __name__ == "__main__":
    unittest.main()
