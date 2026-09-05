from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from hearthline_learning import LearningLedger, LearningScope, Provenance, ReceiptMode
from tools import new_public_learning_session as generator
from tools import validate_public_learning_session as validator

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "templates" / "public-learning-session.v1.json"


def base_args(root: Path, *extra: str) -> list[str]:
    return [
        "--output-root",
        str(root),
        "--mode",
        "micro_fixture",
        "--session-id",
        "play-0001",
        "--problem-id",
        "LANTERN-LEDGER-01",
        "--learning-goal",
        "Practice evidence-bounded interface learning.",
        *extra,
    ]


def template() -> dict[str, object]:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def closed_and_reset_receipts() -> tuple[dict[str, object], dict[str, object]]:
    ledger = LearningLedger(LearningScope("public-play-0001", "LANTERN-LEDGER-01"))
    ledger.observe_supported("mark", "sela", Provenance("D1"))
    ledger.resolve("mark")
    closed = ledger.close()
    reset = ledger.reset(
        LearningScope("public-play-0001", "LANTERN-REFORMULATE-01")
    )
    return closed, reset


def resign(document: dict[str, object], digest_field: str) -> dict[str, object]:
    result = json.loads(json.dumps(document))
    result.pop(digest_field, None)
    canonical = json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    result[digest_field] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return result


def session_bound_to(
    closed: dict[str, object],
    reset: dict[str, object] | None = None,
) -> dict[str, object]:
    document = template()
    controls = document["learning_trace"]["episode_control"]
    controls["answer_sealed_before_coach_view"] = True
    bindings = document["learning_trace"]["receipt_bindings"]
    bindings["verification"] = "VERIFIED_WITH_SUPPLIED_RECEIPTS"
    bindings["ledger_receipt_sha256"] = closed["receipt_sha256"]
    if reset is not None:
        controls["state_reset_confirmed"] = True
        bindings["reset_receipt_sha256"] = reset["reset_receipt_sha256"]
    return document


def rich_closed_receipt(mode: ReceiptMode) -> dict[str, object]:
    ledger = LearningLedger(
        LearningScope("public-play-0001", "LANTERN-LEDGER-01"),
        receipt_mode=mode,
    )
    provenance = Provenance("D1", ordinal=1, source_sha256="a" * 64)
    ledger.observe_supported("supported", "one", provenance)
    ledger.observe_supported("supported", "one", Provenance("D2", ordinal=2))
    ledger.observe_ambiguous("ambiguous", ["one", "two"], Provenance("D3"))
    ledger.observe_supported("conflict", "one", Provenance("D4"))
    ledger.observe_supported("conflict", "two", Provenance("D5"))
    for requested in ("supported", "ambiguous", "conflict", "missing"):
        ledger.resolve(requested)
    ledger.resolve(None)
    return ledger.close()


class PublicLearningSessionTests(unittest.TestCase):
    def test_checked_in_template_is_valid_and_zero_call(self) -> None:
        summary = validator.validate_session(validator.load_session(TEMPLATE))
        self.assertEqual(summary["status"], validator.STATUS)
        self.assertEqual(summary["planned_model_calls"], 0)
        self.assertFalse(summary["formal_pilot_consumed"])

    def test_generator_creates_one_valid_file_with_default_zero_budgets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sessions"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(generator.main(base_args(root)), 0)
            created = root / "play-0001.public-learning-session.v1.json"
            self.assertEqual([path.name for path in root.iterdir()], [created.name])
            document = validator.load_session(created)
            validator.validate_session(document)
            self.assertEqual(document["budgets"]["model_calls"], 0)
            self.assertEqual(document["future_plan"]["status"], "NO_RUN_PLANNED")
            self.assertFalse(document["formal_pilot"]["consumed"])
            self.assertIn(str(created), output.getvalue())

    def test_generator_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "play-0001.public-learning-session.v1.json"
            path.write_text("keep me", encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(generator.main(base_args(root)), 1)
            self.assertEqual(path.read_text(encoding="utf-8"), "keep me")

    def test_generator_requires_absolute_output_root(self) -> None:
        with redirect_stderr(io.StringIO()):
            self.assertEqual(generator.main(base_args(Path("relative-root"))), 1)

    def test_windows_e_drive_is_rejected(self) -> None:
        for path in (r"E:\HearthlineData\play", r"e:/play", "/mnt/e/play"):
            with self.subTest(path=path), self.assertRaisesRegex(
                generator.CreationError, "E: destinations"
            ):
                generator.validate_output_root(path, platform_name="nt")

    def test_nonzero_budgets_require_an_explicit_future_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(generator.main(base_args(root, "--model-calls", "1")), 1)
            self.assertEqual(list(root.iterdir()), [])

            planned_root = root / "planned"
            args = base_args(
                planned_root,
                "--model-calls",
                "1",
                "--future-plan",
                "After separate authorization, make one public-fixture model call.",
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(generator.main(args), 0)
            document = validator.load_session(
                planned_root / "play-0001.public-learning-session.v1.json"
            )
            validator.validate_session(document)
            self.assertEqual(document["future_plan"]["status"], "FUTURE_ONLY_NOT_RUN")
            self.assertEqual(document["activity"]["model_calls_completed"], 0)

    def test_public_modes_use_their_exact_pinned_public_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            arguments = base_args(root)
            arguments[arguments.index("micro_fixture")] = "public_core"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(generator.main(arguments), 0)
            document = validator.load_session(
                root / "play-0001.public-learning-session.v1.json"
            )
            validator.validate_session(document)
            self.assertTrue(document["provenance"]["source_is_public"])
            self.assertEqual(document["source"], validator.SOURCES["public_core"])

    def test_validator_rejects_unpinned_source_and_excess_future_budgets(self) -> None:
        source = template()
        source["source"]["locator"] = "https://example.org/not-the-pinned-task"
        with self.assertRaisesRegex(validator.SessionError, "pinned locator"):
            validator.validate_session(source)
        model = template()
        model["budgets"]["model_calls"] = 2
        model["future_plan"] = {
            "status": "FUTURE_ONLY_NOT_RUN",
            "description": "Future only.",
        }
        with self.assertRaisesRegex(validator.SessionError, "ceiling of one"):
            validator.validate_session(model)
        evaluator = template()
        evaluator["budgets"]["evaluator_runs"] = 1
        evaluator["future_plan"] = {
            "status": "FUTURE_ONLY_NOT_RUN",
            "description": "Future only.",
        }
        with self.assertRaisesRegex(validator.SessionError, "must remain zero"):
            validator.validate_session(evaluator)

    def test_trace_binds_sealed_answers_and_resets_to_receipts(self) -> None:
        document = template()
        controls = document["learning_trace"]["episode_control"]
        controls["answer_sealed_before_coach_view"] = True
        with self.assertRaisesRegex(validator.SessionError, "supplied ledger receipt"):
            validator.validate_session(document)
        closed, reset = closed_and_reset_receipts()
        bindings = document["learning_trace"]["receipt_bindings"]
        bindings["verification"] = "VERIFIED_WITH_SUPPLIED_RECEIPTS"
        bindings["ledger_receipt_sha256"] = closed["receipt_sha256"]
        with self.assertRaisesRegex(validator.SessionError, "supplied receipt documents"):
            validator.validate_session(document)
        summary = validator.validate_session(document, ledger_receipt=closed)
        self.assertEqual(
            summary["receipt_binding_result"],
            "VERIFIED_WITH_SUPPLIED_LEDGER_RECEIPT",
        )
        controls["coach_view_opened"] = True
        controls["state_reset_confirmed"] = True
        bindings["reset_receipt_sha256"] = reset["reset_receipt_sha256"]
        with self.assertRaisesRegex(validator.SessionError, "supplied reset receipt"):
            validator.validate_session(document, ledger_receipt=closed)
        summary = validator.validate_session(
            document,
            ledger_receipt=closed,
            reset_receipt=reset,
        )
        self.assertEqual(
            summary["receipt_binding_result"],
            "VERIFIED_WITH_SUPPLIED_LEDGER_AND_RESET_RECEIPTS",
        )

    def test_receipt_binding_rejects_a_reset_from_another_ledger(self) -> None:
        document = template()
        controls = document["learning_trace"]["episode_control"]
        controls["answer_sealed_before_coach_view"] = True
        controls["state_reset_confirmed"] = True
        closed, _ = closed_and_reset_receipts()
        other_ledger = LearningLedger(LearningScope("other-session", "episode-1"))
        other_ledger.resolve("unknown")
        other_closed = other_ledger.close()
        other_reset = other_ledger.reset(LearningScope("other-session", "episode-2"))
        bindings = document["learning_trace"]["receipt_bindings"]
        bindings["verification"] = "VERIFIED_WITH_SUPPLIED_RECEIPTS"
        bindings["ledger_receipt_sha256"] = closed["receipt_sha256"]
        bindings["reset_receipt_sha256"] = other_reset["reset_receipt_sha256"]
        with self.assertRaisesRegex(validator.SessionError, "does not link"):
            validator.validate_session(
                document,
                ledger_receipt=closed,
                reset_receipt=other_reset,
            )
        self.assertNotEqual(
            other_reset["from_receipt_sha256"],
            closed["receipt_sha256"],
        )
        self.assertEqual(other_reset["from_receipt_sha256"], other_closed["receipt_sha256"])

    def test_receipt_binding_rejects_an_unrelated_ledger_scope(self) -> None:
        document = template()
        controls = document["learning_trace"]["episode_control"]
        controls["answer_sealed_before_coach_view"] = True
        unrelated = LearningLedger(LearningScope("unrelated-session", "unrelated-problem"))
        unrelated.resolve("unknown")
        closed = unrelated.close()
        bindings = document["learning_trace"]["receipt_bindings"]
        bindings["verification"] = "VERIFIED_WITH_SUPPLIED_RECEIPTS"
        bindings["ledger_receipt_sha256"] = closed["receipt_sha256"]
        with self.assertRaisesRegex(validator.SessionError, "scope does not match"):
            validator.validate_session(document, ledger_receipt=closed)

    def test_reset_binding_checks_scope_and_generation_redundancy(self) -> None:
        document = template()
        closed, reset = closed_and_reset_receipts()
        controls = document["learning_trace"]["episode_control"]
        controls["answer_sealed_before_coach_view"] = True
        controls["state_reset_confirmed"] = True
        bindings = document["learning_trace"]["receipt_bindings"]
        bindings["verification"] = "VERIFIED_WITH_SUPPLIED_RECEIPTS"
        bindings["ledger_receipt_sha256"] = closed["receipt_sha256"]
        for field, value, message in (
            ("from_scope", reset["to_scope"], "from_scope does not match"),
            ("generation", reset["generation"] + 1, "generation does not follow"),
            ("generation", True, "generation does not follow"),
            ("to_scope", "different", "to_scope must be an object"),
            ("to_scope", {"wrong": "shape"}, "to_scope digest fields mismatch"),
        ):
            with self.subTest(field=field):
                changed = json.loads(json.dumps(reset))
                changed[field] = value
                changed = resign(changed, "reset_receipt_sha256")
                bindings["reset_receipt_sha256"] = changed["reset_receipt_sha256"]
                with self.assertRaisesRegex(validator.SessionError, message):
                    validator.validate_session(
                        document,
                        ledger_receipt=closed,
                        reset_receipt=changed,
                    )

    def test_receipt_binding_accepts_a_well_formed_raw_mode_reset(self) -> None:
        document = template()
        ledger = LearningLedger(
            LearningScope("public-play-0001", "LANTERN-LEDGER-01"),
            receipt_mode=ReceiptMode.RAW,
        )
        ledger.resolve("unknown")
        closed = ledger.close()
        reset = ledger.reset(
            LearningScope("public-play-0001", "LANTERN-REFORMULATE-01")
        )
        controls = document["learning_trace"]["episode_control"]
        controls["answer_sealed_before_coach_view"] = True
        controls["state_reset_confirmed"] = True
        bindings = document["learning_trace"]["receipt_bindings"]
        bindings["verification"] = "VERIFIED_WITH_SUPPLIED_RECEIPTS"
        bindings["ledger_receipt_sha256"] = closed["receipt_sha256"]
        bindings["reset_receipt_sha256"] = reset["reset_receipt_sha256"]
        summary = validator.validate_session(
            document,
            ledger_receipt=closed,
            reset_receipt=reset,
        )
        self.assertEqual(
            summary["receipt_binding_result"],
            "VERIFIED_WITH_SUPPLIED_LEDGER_AND_RESET_RECEIPTS",
        )

    def test_nested_receipt_schema_accepts_all_outcomes_in_both_modes(self) -> None:
        for mode in ReceiptMode:
            with self.subTest(mode=mode):
                closed = rich_closed_receipt(mode)
                summary = validator.validate_session(
                    session_bound_to(closed),
                    ledger_receipt=closed,
                )
                self.assertEqual(
                    summary["receipt_binding_result"],
                    "VERIFIED_WITH_SUPPLIED_LEDGER_RECEIPT",
                )

    def test_nested_receipt_rejects_configuration_lifecycle_and_boundary_drift(self) -> None:
        closed = rich_closed_receipt(ReceiptMode.DIGESTS)
        mutations = (
            (
                lambda value: value["configuration"].__setitem__("normalization", "CASEFOLD"),
                "normalization mismatch",
            ),
            (
                lambda value: value["configuration"].__setitem__("extra", False),
                "configuration schema drift",
            ),
            (
                lambda value: value["lifecycle"].__setitem__("generation", True),
                "generation must be a nonnegative integer",
            ),
            (
                lambda value: value["lifecycle"].__setitem__(
                    "reset_from_receipt_sha256", "b" * 64
                ),
                "reset lineage mismatch",
            ),
            (
                lambda value: value["implementation_boundary"].__setitem__(
                    "caller_evidence_origin_verified", True
                ),
                "cannot verify caller evidence",
            ),
            (
                lambda value: value["implementation_boundary"]["module_performs"].__setitem__(
                    "model_calls", True
                ),
                "implementation capabilities mismatch",
            ),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                changed = json.loads(json.dumps(closed))
                mutate(changed)
                changed = resign(changed, "receipt_sha256")
                with self.assertRaisesRegex(validator.SessionError, message):
                    validator.validate_session(
                        session_bound_to(changed),
                        ledger_receipt=changed,
                    )

    def test_nested_receipt_rejects_observation_and_provenance_drift(self) -> None:
        closed = rich_closed_receipt(ReceiptMode.DIGESTS)
        mutations = (
            (
                lambda value: value["observations"][0].__setitem__("extra", None),
                "observations.*schema drift",
            ),
            (
                lambda value: value["observations"][0].__setitem__("kind", []),
                "kind mismatch",
            ),
            (
                lambda value: value["observations"][0]["provenance"].__setitem__(
                    "source_kind", []
                ),
                "source_kind mismatch",
            ),
            (
                lambda value: value["observations"][0]["provenance"].__setitem__(
                    "caller_declared_not_verified", False
                ),
                "caller provenance unverified",
            ),
            (
                lambda value: value["observations"][0].__setitem__(
                    "candidate_sha256", []
                ),
                "count does not match SUPPORTED",
            ),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                changed = json.loads(json.dumps(closed))
                mutate(changed)
                changed = resign(changed, "receipt_sha256")
                with self.assertRaisesRegex(validator.SessionError, message):
                    validator.validate_session(
                        session_bound_to(changed),
                        ledger_receipt=changed,
                    )

    def test_nested_receipt_rejects_request_semantic_drift(self) -> None:
        closed = rich_closed_receipt(ReceiptMode.DIGESTS)
        mutations = (
            (
                lambda value: value["requests"][0].__setitem__("accepted", False),
                "accepted does not match outcome",
            ),
            (
                lambda value: value["requests"][0].__setitem__("outcome", []),
                "outcome mismatch",
            ),
            (
                lambda value: value["requests"][0].__setitem__("evidence_ids", []),
                "evidence_ids do not match observations",
            ),
            (
                lambda value: value["requests"][0].__setitem__(
                    "rendering_sha256", "b" * 64
                ),
                "rendering does not match observations",
            ),
            (
                lambda value: value["requests"][4].__setitem__(
                    "refusal_reason", "NOT_A_CONTRACT_ERROR"
                ),
                "not a contract error",
            ),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                changed = json.loads(json.dumps(closed))
                mutate(changed)
                changed = resign(changed, "receipt_sha256")
                with self.assertRaisesRegex(validator.SessionError, message):
                    validator.validate_session(
                        session_bound_to(changed),
                        ledger_receipt=changed,
                    )

    def test_nested_receipt_rejects_count_and_mode_drift(self) -> None:
        closed = rich_closed_receipt(ReceiptMode.DIGESTS)
        mutations = (
            (
                lambda value: value["counts"].__setitem__(
                    "observations", value["counts"]["observations"] + 1
                ),
                "counts.observations does not match",
            ),
            (
                lambda value: value["counts"]["outcomes"].__setitem__(
                    "SUPPORTED_RENDER", 0
                ),
                "outcomes.SUPPORTED_RENDER does not match",
            ),
            (
                lambda value: value["implementation_boundary"].__setitem__(
                    "raw_content_included", True
                ),
                "raw-content boundary mismatches mode",
            ),
            (
                lambda value: value["observations"][0].__setitem__(
                    "direction", "source_to_render"
                ),
                "observations.*schema drift",
            ),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                changed = json.loads(json.dumps(closed))
                mutate(changed)
                changed = resign(changed, "receipt_sha256")
                with self.assertRaisesRegex(validator.SessionError, message):
                    validator.validate_session(
                        session_bound_to(changed),
                        ledger_receipt=changed,
                    )

    def test_receipt_digest_rejects_unencodable_json_as_session_error(self) -> None:
        receipt = {
            "schema_version": "hearthline-learning-ledger.v1",
            "bad": "\ud800",
            "receipt_sha256": "0" * 64,
        }
        with self.assertRaisesRegex(validator.SessionError, "UTF-8 JSON"):
            validator._verified_self_digest(
                receipt,
                digest_field="receipt_sha256",
                schema_version="hearthline-learning-ledger.v1",
                label="ledger receipt",
            )

    def test_cli_verifies_supplied_receipt_documents(self) -> None:
        document = template()
        closed, reset = closed_and_reset_receipts()
        controls = document["learning_trace"]["episode_control"]
        controls["answer_sealed_before_coach_view"] = True
        controls["state_reset_confirmed"] = True
        bindings = document["learning_trace"]["receipt_bindings"]
        bindings["verification"] = "VERIFIED_WITH_SUPPLIED_RECEIPTS"
        bindings["ledger_receipt_sha256"] = closed["receipt_sha256"]
        bindings["reset_receipt_sha256"] = reset["reset_receipt_sha256"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session_path = root / "session.json"
            ledger_path = root / "ledger.json"
            reset_path = root / "reset.json"
            session_path.write_text(json.dumps(document), encoding="utf-8")
            ledger_path.write_text(json.dumps(closed), encoding="utf-8")
            reset_path.write_text(json.dumps(reset), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                status = validator.main(
                    [
                        str(session_path),
                        "--ledger-receipt",
                        str(ledger_path),
                        "--reset-receipt",
                        str(reset_path),
                    ]
                )
            self.assertEqual(status, 0)
            self.assertEqual(
                json.loads(output.getvalue())["receipt_binding_result"],
                "VERIFIED_WITH_SUPPLIED_LEDGER_AND_RESET_RECEIPTS",
            )

    def test_validator_rejects_completed_activity_even_with_future_plan(self) -> None:
        document = template()
        document["budgets"]["model_calls"] = 1
        document["future_plan"] = {
            "status": "FUTURE_ONLY_NOT_RUN",
            "description": "A future model call only.",
        }
        document["activity"]["model_calls_completed"] = 1
        with self.assertRaisesRegex(validator.SessionError, "must remain zero"):
            validator.validate_session(document)

    def test_validator_rejects_protected_material_and_credentials(self) -> None:
        cases = (
            ("hidden tests were copied here", "forbidden evaluator"),
            ("generator_seed = 123", "forbidden evaluator"),
            ("full mapping map", "forbidden evaluator"),
            ("api_key=" + "sk-" + "a" * 16, "credential"),
        )
        for text, message in cases:
            with self.subTest(text=text):
                document = template()
                document["learning_trace"]["observations"] = [text]
                with self.assertRaisesRegex(validator.SessionError, message):
                    validator.validate_session(document)

        field_case = template()
        field_case["private_test_cases"] = []
        with self.assertRaisesRegex(validator.SessionError, "protected-data field"):
            validator.validate_session(field_case)

    def test_validator_rejects_schema_drift_at_every_level(self) -> None:
        mutations = []
        root_extra = template()
        root_extra["notes"] = []
        mutations.append(root_extra)
        source_extra = template()
        source_extra["source"]["commit"] = "abc"
        mutations.append(source_extra)
        trace_extra = template()
        trace_extra["learning_trace"]["answers"] = []
        mutations.append(trace_extra)
        for document in mutations:
            with self.subTest(keys=sorted(document)):
                with self.assertRaisesRegex(validator.SessionError, "schema drift"):
                    validator.validate_session(document)

    def test_validator_rejects_formal_pilot_consumption_and_bad_mode(self) -> None:
        consumed = template()
        consumed["formal_pilot"]["consumed"] = True
        with self.assertRaisesRegex(validator.SessionError, "must remain false"):
            validator.validate_session(consumed)
        mode = template()
        mode["session_mode"] = "formal_pilot"
        with self.assertRaisesRegex(validator.SessionError, "session_mode"):
            validator.validate_session(mode)

    def test_validator_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema_version":"a","schema_version":"b"}\n', encoding="utf-8")
            with self.assertRaisesRegex(validator.SessionError, "duplicate JSON key"):
                validator.load_session(path)


if __name__ == "__main__":
    unittest.main()
