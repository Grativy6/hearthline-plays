from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from tools import validate_result_bundle as validator


IDS = [
    (f"easy-{index}", "easy") for index in range(5)
] + [
    (f"medium-{index}", "medium") for index in range(5)
] + [
    (f"hard-{index}", "hard") for index in range(5)
]


def gloss_telemetry(system: str, task_form: str) -> dict[str, object]:
    if system != "hearthline_gloss":
        return {
            "availability": "NOT_APPLICABLE",
            "mappings_used": None,
            "unresolved_mappings": None,
            "unsupported_mappings_invented": None,
            "reformulations": None,
        }
    count = 0 if task_form == "python" else 1
    return {
        "availability": "AVAILABLE",
        "mappings_used": count,
        "unresolved_mappings": count,
        "unsupported_mappings_invented": 0,
        "reformulations": count,
    }


def bundle(pass_counts: dict[tuple[str, str], int] | None = None) -> dict[str, object]:
    pass_counts = pass_counts or {
        ("bare", "python"): 12,
        ("bare", "core"): 9,
        ("hearthline", "python"): 11,
        ("hearthline", "core"): 8,
        ("hearthline_gloss", "python"): 13,
        ("hearthline_gloss", "core"): 10,
    }
    conditions = []
    for condition_id, system, task_form in validator.CONDITIONS:
        rows = []
        for index, (question_id, difficulty) in enumerate(IDS):
            rows.append(
                {
                    "question_id": question_id,
                    "difficulty": difficulty,
                    "outcome": "PASS" if index < pass_counts[(system, task_form)] else "WRONG_ANSWER",
                    "disposition": "COMPLETED",
                    "input_tokens": 100 + index,
                    "output_tokens": 20 + index,
                    "latency_ms": 10.5 + index,
                    "gloss_telemetry": gloss_telemetry(system, task_form),
                }
            )
        conditions.append(
            {"id": condition_id, "system": system, "task_form": task_form, "results": rows}
        )
    return {
        "schema_version": "1.0",
        "experiment_id": "ROSETTA-001",
        "status": validator.RESULT_STATUS,
        "pilot_manifest_sha256": "1" * 64,
        "source_lock_sha256": "2" * 64,
        "model": {
            "family": "GPT-5.6 Sol",
            "platform_slug": "gpt-5.6-sol",
            "snapshot": "frozen-snapshot",
            "reasoning_setting": "frozen-setting",
            "sampling_configuration_sha256": "3" * 64,
            "provider_seed_effective": "UNAVAILABLE",
            "provider_temperature_effective": "UNAVAILABLE",
        },
        "systems": {
            "hearthline_commit": "4" * 40,
            "hearthline_sha256": "5" * 64,
            "gloss_commit": "6" * 40,
            "gloss_sha256": "7" * 64,
            "astra_exclusion_attestation_sha256": "8" * 64,
        },
        "execution": {
            "n_jobs": 1,
            "max_attempts": 1,
            "on_failure": "continue",
            "internet_enabled": False,
            "retrieval_enabled": False,
            "model_tools_enabled": False,
            "llm_judge_enabled": False,
        },
        "conditions": conditions,
        "summary": {
            "bare_learning_tax": (
                pass_counts[("bare", "python")] - pass_counts[("bare", "core")]
            ) / 15,
            "hearthline_learning_tax": (
                pass_counts[("hearthline", "python")]
                - pass_counts[("hearthline", "core")]
            ) / 15,
            "hearthline_gloss_learning_tax": (
                pass_counts[("hearthline_gloss", "python")]
                - pass_counts[("hearthline_gloss", "core")]
            ) / 15,
        },
        "claim_ceiling": validator.CLAIM_CEILING,
    }


class ValidateResultBundleTests(unittest.TestCase):
    def test_valid_bundle_computes_pass_rates_and_learning_taxes(self) -> None:
        report = validator.validate_bundle(bundle())
        self.assertEqual(report["verdict"], "STRUCTURAL_ONLY_PASS")
        self.assertAlmostEqual(report["systems"]["bare"]["python"]["pass_rate"], 12 / 15)
        self.assertAlmostEqual(report["systems"]["bare"]["core"]["pass_rate"], 9 / 15)
        self.assertAlmostEqual(report["systems"]["bare"]["learning_tax"], 3 / 15)
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(report["evaluator_runs"], 0)

    def test_supplied_summary_must_match_computed_taxes(self) -> None:
        document = bundle()
        document["summary"] = {
            "bare_learning_tax": 3 / 15,
            "hearthline_learning_tax": 3 / 15,
            "hearthline_gloss_learning_tax": 3 / 15,
        }
        validator.validate_bundle(document)
        document["summary"]["bare_learning_tax"] = 0.0
        with self.assertRaisesRegex(validator.BundleError, "does not match"):
            validator.validate_bundle(document)

    def test_requires_exact_six_conditions_in_order(self) -> None:
        for mutation in ("missing", "reordered", "renamed"):
            with self.subTest(mutation=mutation):
                document = bundle()
                if mutation == "missing":
                    document["conditions"].pop()
                elif mutation == "reordered":
                    document["conditions"][0], document["conditions"][1] = (
                        document["conditions"][1],
                        document["conditions"][0],
                    )
                else:
                    document["conditions"][0]["id"] = "wrong"
                with self.assertRaises(validator.BundleError):
                    validator.validate_bundle(document)

    def test_requires_same_ordered_5_5_5_ids(self) -> None:
        changed = bundle()
        changed["conditions"][1]["results"][0]["question_id"] = "different"
        with self.assertRaisesRegex(validator.BundleError, "same ordered"):
            validator.validate_bundle(changed)
        reordered = bundle()
        rows = reordered["conditions"][0]["results"]
        rows[0], rows[5] = rows[5], rows[0]
        with self.assertRaisesRegex(validator.BundleError, "5 easy"):
            validator.validate_bundle(reordered)

    def test_rejects_python_leak_in_python_control(self) -> None:
        document = bundle()
        document["conditions"][0]["results"][0]["outcome"] = "PYTHON_LEAK"
        with self.assertRaisesRegex(validator.BundleError, "Python control"):
            validator.validate_bundle(document)

    def test_infrastructure_and_timeout_are_separate_and_keep_scores_undefined(self) -> None:
        for disposition in ("INFRASTRUCTURE_FAILURE", "TIMEOUT"):
            with self.subTest(disposition=disposition):
                document = bundle()
                row = document["conditions"][0]["results"][0]
                row["disposition"] = disposition
                row["outcome"] = None
                document["summary"]["bare_learning_tax"] = None
                report = validator.validate_bundle(document)
                bare = report["systems"]["bare"]
                self.assertIsNone(bare["python"]["pass_rate"])
                self.assertIsNone(bare["learning_tax"])
                self.assertEqual(bare["python"]["dispositions"][disposition], 1)

    def test_noncompleted_row_cannot_claim_upstream_outcome(self) -> None:
        document = bundle()
        document["conditions"][0]["results"][0]["disposition"] = "TIMEOUT"
        with self.assertRaisesRegex(validator.BundleError, "must be null"):
            validator.validate_bundle(document)

    def test_telemetry_must_be_nonnegative_and_finite(self) -> None:
        for field, value in (
            ("input_tokens", -1),
            ("output_tokens", 1.5),
            ("latency_ms", math.inf),
            ("latency_ms", True),
        ):
            with self.subTest(field=field, value=value):
                document = bundle()
                document["conditions"][0]["results"][0][field] = value
                with self.assertRaises(validator.BundleError):
                    validator.validate_bundle(document)

    def test_unavailable_token_and_latency_telemetry_may_remain_null(self) -> None:
        document = bundle()
        for field in ("input_tokens", "output_tokens", "latency_ms"):
            document["conditions"][0]["results"][0][field] = None
        validator.validate_bundle(document)

        incomplete = bundle()
        row = incomplete["conditions"][0]["results"][0]
        row.update(
            {
                "outcome": None,
                "disposition": "INFRASTRUCTURE_FAILURE",
                "input_tokens": None,
                "output_tokens": None,
                "latency_ms": None,
            }
        )
        incomplete["summary"]["bare_learning_tax"] = None
        validator.validate_bundle(incomplete)

    def test_gloss_availability_semantics(self) -> None:
        unavailable = bundle()
        telemetry = unavailable["conditions"][4]["results"][0]["gloss_telemetry"]
        telemetry["availability"] = "UNAVAILABLE"
        for key in validator.GLOSS_COUNTERS:
            telemetry[key] = None
        validator.validate_bundle(unavailable)

        bad_counter = copy.deepcopy(unavailable)
        bad_counter["conditions"][4]["results"][0]["gloss_telemetry"]["mappings_used"] = 1
        with self.assertRaisesRegex(validator.BundleError, "must be null"):
            validator.validate_bundle(bad_counter)

        non_gloss_available = bundle()
        non_gloss_available["conditions"][0]["results"][0]["gloss_telemetry"]["availability"] = "AVAILABLE"
        with self.assertRaisesRegex(validator.BundleError, "NOT_APPLICABLE"):
            validator.validate_bundle(non_gloss_available)

    def test_gloss_python_available_telemetry_is_no_op(self) -> None:
        document = bundle()
        document["conditions"][4]["results"][0]["gloss_telemetry"]["mappings_used"] = 1
        with self.assertRaisesRegex(validator.BundleError, "no-op"):
            validator.validate_bundle(document)

    def test_result_fields_are_exact(self) -> None:
        document = bundle()
        document["conditions"][0]["results"][0]["generated_code"] = "not allowed"
        with self.assertRaisesRegex(validator.BundleError, "invalid fields"):
            validator.validate_bundle(document)

    def test_completed_bundle_requires_frozen_metadata_and_claim_ceiling(self) -> None:
        for path, value in (
            (("status",), "TEMPLATE_NOT_A_RUN"),
            (("pilot_manifest_sha256",), None),
            (("model", "platform_slug"), None),
            (("systems", "astra_exclusion_attestation_sha256"), None),
            (("execution", "n_jobs"), 2),
            (("claim_ceiling",), "official leaderboard result"),
        ):
            with self.subTest(path=path):
                document = bundle()
                if len(path) == 1:
                    document[path[0]] = value
                else:
                    document[path[0]][path[1]] = value
                with self.assertRaises(validator.BundleError):
                    validator.validate_bundle(document)

    def test_external_binding_verification_uses_exact_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "pilot.json"
            path.write_bytes(b'{"pilot":true}\n')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            receipt = validator.verify_bound_file(path, digest, "pilot manifest")
            self.assertEqual(receipt["sha256"], digest)
            with self.assertRaisesRegex(validator.BundleError, "does not match"):
                validator.verify_bound_file(path, "0" * 64, "pilot manifest")

    def test_external_bindings_match_pilot_semantics_to_result_rows(self) -> None:
        pilot = {
            "schema_version": "1.0",
            "experiment_id": "ROSETTA-001",
            "status": "SELECTED_IDS_ONLY_NOT_RUN",
            "source_dataset_commit": validator.DATASET_COMMIT,
            "source_index_sha256": "9" * 64,
            "development_exclusion_manifest_sha256": validator.EXCLUSION_MANIFEST_SHA256,
            "development_excluded_question_ids": validator.DEVELOPMENT_EXCLUDED_IDS,
            "selection": {
                "method": validator.SELECTION_METHOD,
                "seed_sha256": validator.SELECTION_SEED,
                "rank_input": "seed_sha256 + NUL + difficulty + NUL + question_id",
                "population_by_difficulty": {"easy": 40, "medium": 50, "hard": 60},
                "eligible_by_difficulty": {"easy": 39, "medium": 50, "hard": 60},
                "requested_by_difficulty": {"easy": 5, "medium": 5, "hard": 5},
                "selected": [
                    {
                        "order": index,
                        "question_id": question_id,
                        "difficulty": difficulty,
                        "rank_sha256": "a" * 64,
                    }
                    for index, (question_id, difficulty) in enumerate(IDS)
                ],
            },
            "task_material_opened_during_selection": False,
            "frozen_at_utc": "2026-09-04T00:00:00Z",
        }
        source_lock = {
            "schema_version": "source-lock.v1",
            "generated_at_utc": "2026-09-04T00:00:00Z",
            "experiment_id": "ROSETTA-001",
            "station_status": "PREPARED_NOT_RUN",
            "lineage": {},
            "materialization": {},
            "sources": {"rosetta_dataset_hf": {"commit": validator.DATASET_COMMIT}},
            "kaggle_benchmark": {},
            "kaggle_writeup": {},
            "license_resolution": {},
            "selection": {
                "method": validator.SELECTION_METHOD,
                "development_exclusion_manifest": {
                    "path": "exclusions/development-tasks.v1.json",
                    "sha256": validator.EXCLUSION_MANIFEST_SHA256,
                    "excluded_task_ids": validator.DEVELOPMENT_EXCLUDED_IDS,
                },
            },
            "claims_not_earned": {},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pilot_path = root / "pilot.json"
            source_path = root / "source-lock.json"
            pilot_path.write_text(json.dumps(pilot) + "\n", encoding="utf-8", newline="\n")
            source_path.write_text(
                json.dumps(source_lock) + "\n", encoding="utf-8", newline="\n"
            )
            document = bundle()
            document["pilot_manifest_sha256"] = hashlib.sha256(
                pilot_path.read_bytes()
            ).hexdigest()
            document["source_lock_sha256"] = hashlib.sha256(
                source_path.read_bytes()
            ).hexdigest()
            receipt = validator.verify_external_bindings(
                document, pilot_path, source_path
            )
            self.assertTrue(
                receipt["semantic_checks"]["pilot_identifiers_and_order_match_results"]
            )
            document["conditions"][0]["results"][0]["question_id"] = "different"
            with self.assertRaisesRegex(validator.BundleError, "do not match"):
                validator.verify_external_bindings(document, pilot_path, source_path)

    def test_external_binding_rejects_frozen_development_task(self) -> None:
        document = bundle()
        pilot = {
            "schema_version": "1.0",
            "experiment_id": "ROSETTA-001",
            "status": "SELECTED_IDS_ONLY_NOT_RUN",
            "source_dataset_commit": validator.DATASET_COMMIT,
            "source_index_sha256": "9" * 64,
            "development_exclusion_manifest_sha256": validator.EXCLUSION_MANIFEST_SHA256,
            "development_excluded_question_ids": validator.DEVELOPMENT_EXCLUDED_IDS,
            "selection": {
                "method": validator.SELECTION_METHOD,
                "seed_sha256": validator.SELECTION_SEED,
                "rank_input": "seed_sha256 + NUL + difficulty + NUL + question_id",
                "population_by_difficulty": {"easy": 40, "medium": 50, "hard": 60},
                "eligible_by_difficulty": {"easy": 39, "medium": 50, "hard": 60},
                "requested_by_difficulty": {"easy": 5, "medium": 5, "hard": 5},
                "selected": [
                    {
                        "order": index,
                        "question_id": "abc357_b" if index == 0 else question_id,
                        "difficulty": difficulty,
                        "rank_sha256": "a" * 64,
                    }
                    for index, (question_id, difficulty) in enumerate(IDS)
                ],
            },
            "task_material_opened_during_selection": False,
            "frozen_at_utc": "2026-09-04T00:00:00Z",
        }
        source_lock = {
            "schema_version": "source-lock.v1",
            "generated_at_utc": "2026-09-04T00:00:00Z",
            "experiment_id": "ROSETTA-001",
            "station_status": "PREPARED_NOT_RUN",
            "lineage": {},
            "materialization": {},
            "sources": {"rosetta_dataset_hf": {"commit": validator.DATASET_COMMIT}},
            "kaggle_benchmark": {},
            "kaggle_writeup": {},
            "license_resolution": {},
            "selection": {
                "method": validator.SELECTION_METHOD,
                "development_exclusion_manifest": {
                    "path": "exclusions/development-tasks.v1.json",
                    "sha256": validator.EXCLUSION_MANIFEST_SHA256,
                    "excluded_task_ids": validator.DEVELOPMENT_EXCLUDED_IDS,
                },
            },
            "claims_not_earned": {},
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pilot.json"
            source_path = Path(temporary) / "source-lock.json"
            path.write_text(json.dumps(pilot) + "\n", encoding="utf-8", newline="\n")
            source_path.write_text(
                json.dumps(source_lock) + "\n", encoding="utf-8", newline="\n"
            )
            document["pilot_manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            document["source_lock_sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(validator.BundleError, "frozen development exclusion"):
                validator.verify_external_bindings(document, path, source_path)


if __name__ == "__main__":
    unittest.main()
