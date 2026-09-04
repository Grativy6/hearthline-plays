"""Synthetic-only regression tests for the canonical one-shot ledger."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hearthline_arc2.authorization import (  # noqa: E402
    AuthorizationError,
    claim_public_evaluation,
    complete_preflight_consumption,
    record_preflight_consumption,
)


def synthetic_grant(
    grant_id: str = "synthetic-grant-1",
    nonce: str = "1" * 64,
    scope: str = "PUBLIC_EVAL_ONCE",
) -> dict[str, str]:
    return {"grant_id": grant_id, "nonce": nonce, "scope": scope}


class AuthorizationTests(unittest.TestCase):
    def test_consumed_grant_can_be_claimed_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            grant = synthetic_grant()
            record_preflight_consumption(grant, ledger)
            complete_preflight_consumption(grant, ledger)
            claim = claim_public_evaluation(grant, ledger)
            self.assertTrue(claim.is_file())
            with self.assertRaises(AuthorizationError):
                claim_public_evaluation(grant, ledger)

    def test_duplicate_nonce_is_rejected_even_with_new_grant_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            record_preflight_consumption(synthetic_grant(), ledger)
            with self.assertRaises(AuthorizationError):
                record_preflight_consumption(
                    synthetic_grant(grant_id="synthetic-grant-2"), ledger
                )

    def test_duplicate_grant_id_is_rejected_even_with_new_nonce(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            record_preflight_consumption(synthetic_grant(), ledger)
            with self.assertRaises(AuthorizationError):
                record_preflight_consumption(synthetic_grant(nonce="2" * 64), ledger)

    def test_claim_requires_preflight_consumption_and_public_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            with self.assertRaises(AuthorizationError):
                claim_public_evaluation(synthetic_grant(), ledger)
            run_grant = synthetic_grant(scope="KAGGLE_NOTEBOOK_RUN_ONCE")
            record_preflight_consumption(run_grant, ledger)
            with self.assertRaises(AuthorizationError):
                claim_public_evaluation(run_grant, ledger)

    def test_reservation_without_successful_binding_cannot_authorize_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            grant = synthetic_grant()
            record_preflight_consumption(grant, ledger)
            with self.assertRaisesRegex(AuthorizationError, "completion proof"):
                claim_public_evaluation(grant, ledger)
            with self.assertRaisesRegex(AuthorizationError, "already spent"):
                record_preflight_consumption(grant, ledger)

    def test_completion_proof_is_closed_bound_and_single_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            grant = synthetic_grant()
            record_preflight_consumption(grant, ledger)
            completion_path = complete_preflight_consumption(grant, ledger)
            with self.assertRaisesRegex(AuthorizationError, "already exists"):
                complete_preflight_consumption(grant, ledger)
            completion = json.loads(completion_path.read_text(encoding="utf-8"))
            completion["unexpected"] = True
            completion_path.write_text(json.dumps(completion) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(AuthorizationError, "not closed"):
                claim_public_evaluation(grant, ledger)

    def test_corrupted_consumption_evidence_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "bad-lock"
            grant = synthetic_grant()
            ledger_path = record_preflight_consumption(grant, ledger)
            ledger_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(AuthorizationError, "record"):
                claim_public_evaluation(grant, ledger)

            ledger = Path(directory) / "bad-record"
            record_path = record_preflight_consumption(grant, ledger)
            record = json.loads(record_path.read_text(encoding="utf-8").strip())
            record["consumed_at"] = "not-a-time"
            record_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(AuthorizationError, "record"):
                claim_public_evaluation(grant, ledger)

    def test_duplicate_key_ledger_record_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            grant = synthetic_grant()
            ledger_path = record_preflight_consumption(grant, ledger)
            record = json.loads(ledger_path.read_text(encoding="utf-8"))
            canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
            duplicate = canonical.replace(
                '"grant_id":"synthetic-grant-1"',
                '"grant_id":"synthetic-grant-1","grant_id":"synthetic-grant-1"',
            )
            ledger_path.write_text(duplicate + "\n", encoding="utf-8")
            with self.assertRaisesRegex(AuthorizationError, "duplicate JSON key"):
                claim_public_evaluation(grant, ledger)
            self.assertFalse((ledger / "claims" / f"{grant['nonce']}.used").exists())

    def test_duplicate_key_completion_record_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            grant = synthetic_grant()
            record_preflight_consumption(grant, ledger)
            completion_path = complete_preflight_consumption(grant, ledger)
            completion = json.loads(completion_path.read_text(encoding="utf-8"))
            canonical = json.dumps(completion, sort_keys=True, separators=(",", ":"))
            duplicate = canonical.replace(
                '"grant_id":"synthetic-grant-1"',
                '"grant_id":"synthetic-grant-1","grant_id":"synthetic-grant-1"',
            )
            completion_path.write_text(duplicate + "\n", encoding="utf-8")
            with self.assertRaisesRegex(AuthorizationError, "duplicate JSON key"):
                claim_public_evaluation(grant, ledger)
            self.assertFalse((ledger / "claims" / f"{grant['nonce']}.used").exists())

    def test_noncanonical_completion_record_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            grant = synthetic_grant()
            record_preflight_consumption(grant, ledger)
            completion_path = complete_preflight_consumption(grant, ledger)
            completion = json.loads(completion_path.read_text(encoding="utf-8"))
            completion_path.write_text(
                json.dumps(completion, indent=2, sort_keys=False) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuthorizationError, "not canonical JSON"):
                claim_public_evaluation(grant, ledger)
            self.assertFalse((ledger / "claims" / f"{grant['nonce']}.used").exists())

    def test_truncated_completion_record_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            grant = synthetic_grant()
            record_preflight_consumption(grant, ledger)
            completion_path = complete_preflight_consumption(grant, ledger)
            payload = completion_path.read_bytes()
            self.assertTrue(payload.endswith(b"\n"))
            completion_path.write_bytes(payload[:-1])
            with self.assertRaisesRegex(AuthorizationError, "partial record"):
                claim_public_evaluation(grant, ledger)
            self.assertFalse((ledger / "claims" / f"{grant['nonce']}.used").exists())

    def test_ledger_wide_duplicate_identity_corruption_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for duplicate_field in ("grant_id", "nonce"):
                with self.subTest(field=duplicate_field):
                    ledger = Path(directory) / duplicate_field
                    grant = synthetic_grant()
                    path = record_preflight_consumption(grant, ledger)
                    record = json.loads(path.read_text(encoding="utf-8").strip())
                    duplicate = dict(record)
                    duplicate["grant_id"] = "synthetic-grant-2"
                    duplicate["nonce"] = "2" * 64
                    duplicate[duplicate_field] = record[duplicate_field]
                    with path.open("a", encoding="utf-8") as stream:
                        stream.write(
                            json.dumps(
                                duplicate,
                                sort_keys=True,
                                separators=(",", ":"),
                            )
                            + "\n"
                        )
                    with self.assertRaisesRegex(AuthorizationError, "duplicate"):
                        claim_public_evaluation(grant, ledger)


if __name__ == "__main__":
    unittest.main()
