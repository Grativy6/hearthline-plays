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
            "account_slug": "fixture-user",
            "kernel_id": "fixture-user/hearthline-arc3-readiness",
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
            "structural_verification": "PASS",
            "kaggle_stage_ready": True,
            "verified_snapshot": {
                "sha256": self.candidate["verified_snapshot_sha256"],
                "candidate_binding": dict(self.candidate),
            },
            "verified_inputs": {
                "source_lock_sha256": self.candidate["source_lock_sha256"],
                "agents_repository": "arcprize/ARC-AGI-3-Agents",
                "agents_commit": "4743e7d0aaae0ded0d98a89a7e282e63564cd58b",
                "agents_files": {
                    "agents/agent.py": "1" * 64,
                    "agents/recorder.py": "2" * 64,
                    "agents/swarm.py": "3" * 64,
                    "agents/tracing.py": "4" * 64,
                    "main.py": "5" * 64,
                },
                "agents_license_file": {
                    "LICENSE": "75c4276c506fd93082b38ad39f67ee97aa859574401ef978e701710c7a40af04"
                },
                "runtime_versions": {"arc-agi": "0.9.9", "arcengine": "0.9.3"},
                "runtime_closure_status": "FROZEN_POST_STAGE_SUCCESSOR",
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
            "schema": "hearthline.arc3.kaggle-stage-result.v3",
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
            "runtime_inventory": {
                "captured_from": "HEARTHLINE_STAGE_INVENTORY",
                "complete": True,
                "python_version": "3.12.13",
                "distributions": [
                    {"name": "arc-agi", "version": "0.9.9"},
                    {"name": "arcengine", "version": "0.9.3"},
                    {"name": "python-dotenv", "version": "1.1.1"},
                ],
                "agents_repository": "arcprize/ARC-AGI-3-Agents",
                "agents_expected_commit": "4743e7d0aaae0ded0d98a89a7e282e63564cd58b",
                "agents_files": GATE.expected_agents_files(self.verification),
                "agents_license_file": GATE.expected_agents_license_file(
                    self.verification
                ),
                "reviewed_by_human": True,
            },
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

    def test_gate_b_runtime_versions_are_exact(self) -> None:
        receipt = self.stage_receipt()
        receipt_bytes = self.encoded(receipt)
        grant = self.competition_grant(hashlib.sha256(receipt_bytes).hexdigest())
        receipt["runtime_inventory"]["distributions"][0]["version"] = "99.0"
        with self.assertRaisesRegex(GATE.GateError, "runtime version mismatch: arc-agi"):
            GATE.validate_competition(
                grant,
                self.verification,
                receipt,
                hashlib.sha256(receipt_bytes).hexdigest(),
                ".hearthline/receipts/stage.json",
                self.NOW,
            )

    def test_gate_b_rejects_noncanonical_distribution_aliases(self) -> None:
        receipt = self.stage_receipt()
        receipt["runtime_inventory"]["distributions"].extend(
            [
                {"name": "pkg.name", "version": "1"},
                {"name": "pkg-name", "version": "2"},
            ]
        )
        receipt_bytes = self.encoded(receipt)
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        grant = self.competition_grant(receipt_sha)
        with self.assertRaisesRegex(GATE.GateError, "PEP 503 canonical distribution name"):
            GATE.validate_competition(
                grant,
                self.verification,
                receipt,
                receipt_sha,
                ".hearthline/receipts/stage.json",
                self.NOW,
            )

    def test_gate_b_agents_license_is_exact(self) -> None:
        receipt = self.stage_receipt()
        receipt["runtime_inventory"]["agents_license_file"]["LICENSE"] = "0" * 64
        receipt_bytes = self.encoded(receipt)
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        grant = self.competition_grant(receipt_sha)
        with self.assertRaisesRegex(GATE.GateError, "Agents license differs"):
            GATE.validate_competition(
                grant,
                self.verification,
                receipt,
                receipt_sha,
                ".hearthline/receipts/stage.json",
                self.NOW,
            )

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


if __name__ == "__main__":
    unittest.main()
