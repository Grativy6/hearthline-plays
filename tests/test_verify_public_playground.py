from __future__ import annotations

import copy
import json
import tomllib
import unittest
from pathlib import Path

from tools import verify_public_playground as verifier

REPO_ROOT = Path(__file__).resolve().parents[1]


class VerifyPublicPlaygroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(
            (REPO_ROOT / verifier.CATALOG_PATH).read_text(encoding="utf-8")
        )
        cls.deck = json.loads((REPO_ROOT / verifier.DECK_PATH).read_text(encoding="utf-8"))
        with (REPO_ROOT / verifier.ROUTES_PATH).open("rb") as handle:
            cls.routes = tomllib.load(handle)

    def test_current_public_playground_passes_offline(self) -> None:
        report = verifier.verify_public_playground(REPO_ROOT)
        self.assertEqual(report["verdict"], "PASS_PUBLIC_PLAYGROUND_READY")
        self.assertEqual(report["routes"]["default_route"], "micro_original")
        self.assertEqual(report["deck"]["episode_count"], 3)
        self.assertFalse(any(report["claims_earned"].values()))
        self.assertTrue(all(value == 0 for value in report["verification_side_effects"].values()))

    def test_catalog_rejects_materialization_and_status_drift(self) -> None:
        for mutate in (
            lambda doc: doc["boundaries"].__setitem__("dataset_downloaded", True),
            lambda doc: doc["boundaries"].__setitem__("rosetta_001_status", "RUN"),
            lambda doc: doc["public_surfaces"][2].__setitem__("default_route_enabled", True),
            lambda doc: doc["public_surfaces"][2].__setitem__("url", "https://example.invalid"),
            lambda doc: doc["public_surfaces"][2].__setitem__("version", 2),
            lambda doc: doc["public_surfaces"][2].__setitem__("candidate_code_executions", 1),
            lambda doc: doc["storage_policy"].__setitem__("bulk_data_root", "C:\\data"),
            lambda doc: doc["public_observations"][0].__setitem__("not_our_run", False),
            lambda doc: doc["public_observations"][0]["scores"].__setitem__("core", 1.0),
            lambda doc: doc["public_observations"][0]["task_versions"].__setitem__("core", 2),
        ):
            with self.subTest(mutate=mutate):
                document = copy.deepcopy(self.catalog)
                mutate(document)
                with self.assertRaises(verifier.PlaygroundVerificationError):
                    verifier.validate_catalog(document)

    def test_routes_reject_run_authority_and_e_drive_data(self) -> None:
        mutations = (
            lambda doc: doc.__setitem__("formal_experiment_enabled", True),
            lambda doc: doc["session"].__setitem__("default_model_calls", 1),
            lambda doc: doc["routes"]["public_core_reference"].__setitem__("enabled", True),
            lambda doc: doc["routes"]["bulk_dataset"].__setitem__("destination", "E:\\data"),
            lambda doc: doc["routes"]["public_source_read"].__setitem__("authentication", True),
            lambda doc: doc["routes"]["public_leaderboard_observe"].__setitem__("evaluator_calls", 1),
            lambda doc: doc["routes"]["public_leaderboard_observe"].__setitem__(
                "candidate_code_executions", 1
            ),
            lambda doc: doc["separation"]["rosetta_cal_001"].__setitem__("repair_or_retry_authorized", True),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                document = copy.deepcopy(self.routes)
                mutate(document)
                with self.assertRaises(verifier.PlaygroundVerificationError):
                    verifier.validate_routes(document)

    def test_deck_requires_original_zero_upstream_learner_first_content(self) -> None:
        for mutate in (
            lambda doc: doc["upstream_material"].__setitem__("task_rows", 1),
            lambda doc: doc["use"].__setitem__("default_model_calls", 1),
            lambda doc: doc["use"].__setitem__("show_learner_view_first", False),
            lambda doc: doc["episodes"][0]["learner_view"].__setitem__("source", "https://example.org"),
        ):
            with self.subTest(mutate=mutate):
                document = copy.deepcopy(self.deck)
                mutate(document)
                with self.assertRaises(verifier.PlaygroundVerificationError):
                    verifier.validate_deck(document)

    def test_learning_ledger_smoke_proves_refusal_and_reset(self) -> None:
        report = verifier.validate_learning_ledger()
        self.assertEqual(report["supported_outcome"], "SUPPORTED_RENDER")
        self.assertEqual(report["unsupported_outcome"], "UNRESOLVED")
        self.assertTrue(report["reset_verified"])


if __name__ == "__main__":
    unittest.main()
