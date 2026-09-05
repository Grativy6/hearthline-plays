from __future__ import annotations

import hashlib
import json
import unittest

from hearthline_learning import (
    EvidenceSourceKind,
    LearningLedger,
    LearningScope,
    LedgerClosedError,
    LedgerState,
    LedgerStateError,
    Provenance,
    ReceiptMode,
    ResolutionOutcome,
)


def source(number: int) -> Provenance:
    return Provenance(
        source_id=f"demonstration-{number:02d}",
        source_kind=EvidenceSourceKind.SUPPLIED_DEMONSTRATION,
        ordinal=number,
        source_sha256=hashlib.sha256(f"pair-{number}".encode()).hexdigest(),
    )


class LearningLedgerResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scope = LearningScope("session-001", "public-problem-001")
        self.ledger = LearningLedger(self.scope)

    def test_supported_render_requires_and_reports_provenance(self) -> None:
        observation_id = self.ledger.observe_supported("lower", "rune_a", source(1))
        result = self.ledger.resolve("lower")

        self.assertEqual(observation_id, "observation-0001")
        self.assertIs(result.outcome, ResolutionOutcome.SUPPORTED_RENDER)
        self.assertEqual(result.rendering, "rune_a")
        self.assertEqual(result.candidates, ("rune_a",))
        self.assertEqual(result.evidence_ids, (observation_id,))
        self.assertTrue(result.accepted)
        self.assertFalse(result.refused)

        receipt = self.ledger.export_receipt()
        provenance = receipt["observations"][0]["provenance"]
        self.assertEqual(
            provenance["source_id_sha256"],
            hashlib.sha256(b"demonstration-01").hexdigest(),
        )
        self.assertEqual(provenance["ordinal"], 1)
        self.assertTrue(provenance["caller_declared_not_verified"])

    def test_missing_evidence_is_unresolved_not_negative_evidence(self) -> None:
        result = self.ledger.resolve("upper")
        self.assertIs(result.outcome, ResolutionOutcome.UNRESOLVED)
        self.assertIsNone(result.rendering)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.refusal_reason, "NO_SUPPORTING_OBSERVATION")

    def test_one_multi_candidate_observation_is_ambiguous(self) -> None:
        self.ledger.observe_ambiguous("comparison", ["rune_b", "rune_a"], source(1))
        result = self.ledger.resolve("comparison")
        self.assertIs(result.outcome, ResolutionOutcome.AMBIGUOUS)
        self.assertEqual(result.candidates, ("rune_a", "rune_b"))
        self.assertIsNone(result.rendering)

    def test_incompatible_observations_are_conflicting(self) -> None:
        self.ledger.observe_supported("loop", "rune_a", source(1))
        self.ledger.observe_supported("loop", "rune_b", source(2))
        result = self.ledger.resolve("loop")
        self.assertIs(result.outcome, ResolutionOutcome.CONFLICTING)
        self.assertEqual(result.candidates, ("rune_a", "rune_b"))
        self.assertEqual(
            result.evidence_ids,
            ("observation-0001", "observation-0002"),
        )

    def test_independent_ambiguities_can_earn_one_intersection(self) -> None:
        self.ledger.observe_ambiguous("delimiter", ["alpha", "beta"], source(1))
        self.ledger.observe_ambiguous("delimiter", ["beta", "gamma"], source(2))
        result = self.ledger.resolve("delimiter")
        self.assertIs(result.outcome, ResolutionOutcome.SUPPORTED_RENDER)
        self.assertEqual(result.rendering, "beta")
        self.assertEqual(len(result.evidence_ids), 2)

    def test_direction_is_part_of_the_exact_request_key(self) -> None:
        self.ledger.observe_supported(
            "token", "forward", source(1), direction="python_to_synthetic"
        )
        self.ledger.observe_supported(
            "token", "reverse", source(2), direction="synthetic_to_python"
        )
        self.assertEqual(
            self.ledger.resolve("token", direction="python_to_synthetic").rendering,
            "forward",
        )
        self.assertEqual(
            self.ledger.resolve("token", direction="synthetic_to_python").rendering,
            "reverse",
        )

    def test_cross_scope_and_invalid_requests_are_audited_contract_errors(self) -> None:
        wrong_scope = LearningScope("session-001", "different-problem")
        cross_scope = self.ledger.resolve("lower", scope=wrong_scope)
        invalid = self.ledger.resolve(None)
        malformed_scope = self.ledger.resolve("lower", scope="not-a-scope")

        self.assertIs(cross_scope.outcome, ResolutionOutcome.CONTRACT_ERROR)
        self.assertEqual(cross_scope.refusal_reason, "CROSS_SCOPE_REQUEST_REFUSED")
        self.assertIs(invalid.outcome, ResolutionOutcome.CONTRACT_ERROR)
        self.assertEqual(
            malformed_scope.refusal_reason,
            "SCOPE_MUST_BE_LEARNING_SCOPE",
        )
        receipt = self.ledger.export_receipt()
        self.assertEqual(receipt["counts"]["refused"], 3)
        self.assertEqual(receipt["counts"]["outcomes"]["CONTRACT_ERROR"], 3)
        self.assertEqual(
            [request["request_id"] for request in receipt["requests"]],
            ["request-0001", "request-0002", "request-0003"],
        )

    def test_repeated_claims_are_retained_and_counted(self) -> None:
        self.ledger.observe_supported("input", "rune", source(1))
        self.ledger.observe_supported("input", "rune", source(2))
        result = self.ledger.resolve("input")
        self.assertIs(result.outcome, ResolutionOutcome.SUPPORTED_RENDER)
        receipt = self.ledger.export_receipt()
        self.assertEqual(receipt["counts"]["repeated_claim_groups"], 1)
        self.assertEqual(receipt["counts"]["repeated_claim_observations"], 1)


class LearningLedgerReceiptTests(unittest.TestCase):
    def make_ledger(self, mode: ReceiptMode = ReceiptMode.DIGESTS) -> LearningLedger:
        ledger = LearningLedger(
            LearningScope("session-receipt", "public-problem-receipt"),
            receipt_mode=mode,
        )
        ledger.observe_supported("sensitive-source", "sensitive-render", source(1))
        ledger.resolve("sensitive-source")
        ledger.resolve("unsupported-source")
        return ledger

    def test_receipt_is_deterministic_detached_and_json_safe(self) -> None:
        first_ledger = self.make_ledger()
        second_ledger = self.make_ledger()
        first = first_ledger.export_receipt()
        second = second_ledger.export_receipt()
        self.assertEqual(first, second)
        json.dumps(first, allow_nan=False)

        digest = first.pop("receipt_sha256")
        canonical = json.dumps(
            first,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        self.assertEqual(digest, hashlib.sha256(canonical.encode("utf-8")).hexdigest())
        self.assertIn("receipt_sha256", first_ledger.export_receipt())

    def test_digest_receipt_hides_forms_while_raw_mode_is_explicit(self) -> None:
        digest_receipt = self.make_ledger().export_receipt()
        digest_json = json.dumps(digest_receipt, sort_keys=True)
        self.assertNotIn("sensitive-source", digest_json)
        self.assertNotIn("sensitive-render", digest_json)
        self.assertNotIn("session-receipt", digest_json)
        self.assertNotIn("public-problem-receipt", digest_json)
        self.assertNotIn("demonstration-01", digest_json)
        self.assertNotIn("source_to_render", digest_json)
        self.assertIn("requested_form_sha256", digest_receipt["observations"][0])

        raw_receipt = self.make_ledger(ReceiptMode.RAW).export_receipt()
        self.assertEqual(raw_receipt["scope"]["session_id"], "session-receipt")
        self.assertEqual(
            raw_receipt["observations"][0]["provenance"]["source_id"],
            "demonstration-01",
        )
        self.assertEqual(
            raw_receipt["observations"][0]["requested_form"],
            "sensitive-source",
        )
        self.assertEqual(raw_receipt["requests"][0]["rendering"], "sensitive-render")
        self.assertTrue(raw_receipt["implementation_boundary"]["raw_content_included"])

    def test_receipt_exposes_non_capabilities_and_all_outcome_buckets(self) -> None:
        receipt = self.make_ledger().export_receipt()
        self.assertEqual(
            receipt["identity"],
            "experimental_evidence_bounded_learning_ledger_not_canonical_gloss",
        )
        boundary = receipt["implementation_boundary"]
        self.assertEqual(
            boundary["scope"],
            "LEDGER_MODULE_OPERATIONS_ONLY_NOT_CALLER_ACTIVITY",
        )
        self.assertFalse(boundary["caller_evidence_origin_verified"])
        self.assertTrue(boundary["public_release_review_required"])
        self.assertFalse(boundary["raw_content_included"])
        self.assertFalse(boundary["module_performs"]["cross_scope_learning_state"])
        self.assertTrue(boundary["module_performs"]["cross_scope_receipt_lineage"])
        other_capabilities = {
            key: value
            for key, value in boundary["module_performs"].items()
            if key != "cross_scope_receipt_lineage"
        }
        self.assertTrue(all(value is False for value in other_capabilities.values()))
        self.assertEqual(
            set(receipt["counts"]["outcomes"]),
            {outcome.value for outcome in ResolutionOutcome},
        )

    def test_close_is_idempotent_and_guards_all_active_operations(self) -> None:
        ledger = self.make_ledger()
        first = ledger.close()
        second = ledger.close()
        self.assertEqual(first, second)
        self.assertIs(ledger.state, LedgerState.CLOSED)
        self.assertEqual(first["lifecycle"]["state"], "CLOSED")

        with self.assertRaises(LedgerClosedError):
            ledger.observe_supported("new", "mapping", source(2))
        with self.assertRaises(LedgerClosedError):
            ledger.resolve("sensitive-source")
        self.assertEqual(first, ledger.export_receipt())

    def test_reset_requires_close_clears_state_and_records_transition(self) -> None:
        ledger = self.make_ledger()
        with self.assertRaises(LedgerStateError):
            ledger.reset(LearningScope("session-next", "problem-next"))

        closed = ledger.close()
        reset = ledger.reset(LearningScope("session-next", "problem-next"))
        self.assertTrue(reset["prior_observations_cleared"])
        self.assertTrue(reset["prior_requests_cleared"])
        self.assertEqual(reset["from_receipt_sha256"], closed["receipt_sha256"])
        self.assertIs(ledger.state, LedgerState.OPEN)
        self.assertEqual(ledger.generation, 1)

        result = ledger.resolve("sensitive-source")
        self.assertIs(result.outcome, ResolutionOutcome.UNRESOLVED)
        receipt = ledger.export_receipt()
        self.assertEqual(receipt["counts"]["observations"], 0)
        self.assertEqual(receipt["counts"]["requests"], 1)
        self.assertEqual(
            receipt["lifecycle"]["reset_from_receipt_sha256"],
            closed["receipt_sha256"],
        )

    def test_reset_refuses_same_scope(self) -> None:
        ledger = self.make_ledger()
        ledger.close()
        with self.assertRaises(LedgerStateError):
            ledger.reset(ledger.scope)


class LearningLedgerValidationTests(unittest.TestCase):
    def test_scope_and_provenance_are_strict_and_json_shaped(self) -> None:
        with self.assertRaises(ValueError):
            LearningScope(" session", "problem")
        with self.assertRaises(ValueError):
            LearningScope("session", "problem with spaces")
        with self.assertRaises(ValueError):
            Provenance("source", ordinal=True)
        with self.assertRaises(TypeError):
            Provenance("source", source_kind="unverified")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            Provenance("source", source_sha256="ABC")

        value = source(4).to_dict()
        self.assertEqual(value["ordinal"], 4)
        json.dumps(value, allow_nan=False)

    def test_direction_is_opaque_and_hashed_in_digest_receipts(self) -> None:
        ledger = LearningLedger(LearningScope("session", "problem"))
        with self.assertRaises(ValueError):
            ledger.observe_supported(
                "source",
                "render",
                source(1),
                direction="private task label",
            )
        result = ledger.resolve("source", direction="private task label")
        self.assertIs(result.outcome, ResolutionOutcome.CONTRACT_ERROR)
        receipt = ledger.export_receipt()
        self.assertNotIn("private task label", json.dumps(receipt))

    def test_observation_contract_rejects_unusable_or_fake_evidence(self) -> None:
        ledger = LearningLedger(LearningScope("session", "problem"))
        with self.assertRaises(ValueError):
            ledger.observe_supported("", "render", source(1))
        with self.assertRaises(ValueError):
            ledger.observe_supported("source", "", source(1))
        with self.assertRaises(TypeError):
            ledger.observe_supported("source", "render", object())  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ledger.observe_ambiguous("source", ["same", "same"], source(1))
        self.assertEqual(ledger.export_receipt()["counts"]["observations"], 0)


if __name__ == "__main__":
    unittest.main()
