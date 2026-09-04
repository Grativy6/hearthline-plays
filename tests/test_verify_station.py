from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from tools import verify_station as verifier


REPO_ROOT = Path(__file__).resolve().parents[1]


class VerifyStationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_lock = json.loads((REPO_ROOT / "source-lock.v1.json").read_text(encoding="utf-8"))
        cls.status = json.loads(
            (REPO_ROOT / "status" / "station-status.v1.json").read_text(encoding="utf-8")
        )
        cls.public_observation = json.loads(
            (REPO_ROOT / "metadata" / "public-observation.v1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.pilot_template = json.loads(
            (REPO_ROOT / "templates" / "pilot-selection.v1.json").read_text(encoding="utf-8")
        )
        cls.result_template = json.loads(
            (REPO_ROOT / "templates" / "result-bundle.v1.json").read_text(encoding="utf-8")
        )
        with (REPO_ROOT / "configs" / "rosetta-001.example.toml").open("rb") as handle:
            cls.config = tomllib.load(handle)

    def test_current_exact_structures_validate(self) -> None:
        verifier.validate_source_lock(copy.deepcopy(self.source_lock))
        verifier.validate_public_observation(copy.deepcopy(self.public_observation))
        verifier.validate_status(copy.deepcopy(self.status))
        verifier.validate_config(copy.deepcopy(self.config))
        verifier.validate_templates(
            copy.deepcopy(self.pilot_template), copy.deepcopy(self.result_template)
        )

    def test_source_lock_rejects_anchor_pin_license_or_materialization_drift(self) -> None:
        mutations = (
            lambda doc: doc["lineage"].__setitem__("series_anchor_commit", "0" * 40),
            lambda doc: doc["sources"]["rosettabench"].__setitem__("commit", "0" * 40),
            lambda doc: doc["sources"]["kaggle_benchmarks"].__setitem__("license", "MIT"),
            lambda doc: doc["sources"]["rosetta_dataset_hf"]["license"].__setitem__("status", "CC0"),
            lambda doc: doc["materialization"].__setitem__("benchmark_data_downloaded", True),
            lambda doc: doc["selection"]["development_exclusion_manifest"].__setitem__(
                "sha256", "0" * 64
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                document = copy.deepcopy(self.source_lock)
                mutate(document)
                with self.assertRaises(verifier.VerificationError):
                    verifier.validate_source_lock(document)

    def test_status_requires_exact_zero_counter_inventory(self) -> None:
        nonzero = copy.deepcopy(self.status)
        nonzero["counters"]["benchmark_model_calls"] = 1
        with self.assertRaisesRegex(verifier.VerificationError, "integer zero"):
            verifier.validate_status(nonzero)
        wrong_name = copy.deepcopy(self.status)
        wrong_name["counters"]["model_calls"] = wrong_name["counters"].pop(
            "benchmark_model_calls"
        )
        with self.assertRaisesRegex(verifier.VerificationError, "inventory"):
            verifier.validate_status(wrong_name)

    def test_public_observation_preserves_unrun_and_unpaired_sol_boundaries(self) -> None:
        for mutate in (
            lambda doc: doc["collection_boundary"].__setitem__("model_invoked", True),
            lambda doc: doc["station_state"].__setitem__("pilot", "SELECTED"),
            lambda doc: doc["live_kaggle_leaderboard"]["selected_rows"][0].__setitem__(
                "core_numeric", 0
            ),
        ):
            with self.subTest(mutate=mutate):
                document = copy.deepcopy(self.public_observation)
                mutate(document)
                with self.assertRaises(verifier.VerificationError):
                    verifier.validate_public_observation(document)

    def test_status_rejects_bound_or_claimed_state(self) -> None:
        for path, value in (
            (("experiment_bindings", "model_snapshot"), "some-model"),
            (("astra_exclusion", "claim_currently_earned"), True),
            (("platform", "authentication"), "DONE"),
        ):
            with self.subTest(path=path):
                document = copy.deepcopy(self.status)
                document[path[0]][path[1]] = value
                with self.assertRaises(verifier.VerificationError):
                    verifier.validate_status(document)

    def test_config_rejects_enabled_actions_and_condition_drift(self) -> None:
        enabled = copy.deepcopy(self.config)
        enabled["station"]["run_enabled"] = True
        with self.assertRaises(verifier.VerificationError):
            verifier.validate_config(enabled)
        network = copy.deepcopy(self.config)
        network["execution"]["internet_enabled"] = True
        with self.assertRaises(verifier.VerificationError):
            verifier.validate_config(network)
        condition = copy.deepcopy(self.config)
        condition["conditions"][0]["id"] = "wrong"
        with self.assertRaises(verifier.VerificationError):
            verifier.validate_config(condition)

    def test_templates_reject_selection_results_and_bound_artifacts(self) -> None:
        selected = copy.deepcopy(self.pilot_template)
        selected["selection"]["selected"] = ["problem"]
        with self.assertRaises(verifier.VerificationError):
            verifier.validate_templates(selected, copy.deepcopy(self.result_template))
        results = copy.deepcopy(self.result_template)
        results["conditions"][0]["results"] = [{}]
        with self.assertRaises(verifier.VerificationError):
            verifier.validate_templates(copy.deepcopy(self.pilot_template), results)
        bound = copy.deepcopy(self.result_template)
        bound["model"]["platform_slug"] = "bound-model"
        with self.assertRaises(verifier.VerificationError):
            verifier.validate_templates(copy.deepcopy(self.pilot_template), bound)

    def test_inventory_accepts_safe_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "safe.txt").write_text("synthetic fixture", encoding="utf-8")
            report = verifier.scan_inventory(root, ["safe.txt"])
            self.assertEqual(report["candidate_files"], 1)

    def test_bootstrap_requires_offline_no_download_create_gate(self) -> None:
        text = (REPO_ROOT / "tools" / "bootstrap_environment.ps1").read_text(
            encoding="utf-8-sig"
        )
        verifier.validate_bootstrap(text)
        with self.assertRaises(verifier.VerificationError):
            verifier.validate_bootstrap(text.replace("--no-python-downloads", ""))

    def test_inventory_rejects_data_run_notebook_and_secret_paths(self) -> None:
        prohibited = (
            "data/task.json",
            "runs/output.json",
            "notebook.ipynb",
            "table.parquet",
            "response.run.json",
            "private.pem",
            "kaggle.json",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in prohibited:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic", encoding="utf-8")
            for relative in prohibited:
                with self.subTest(relative=relative):
                    with self.assertRaises(verifier.VerificationError):
                        verifier.scan_inventory(root, [relative])

    def test_inventory_rejects_secret_like_content_and_large_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret_path = root / "note.txt"
            secret_path.write_text("sk-" + "a" * 24, encoding="utf-8")
            with self.assertRaisesRegex(verifier.VerificationError, "secret-like"):
                verifier.scan_inventory(root, ["note.txt"])
            binary_path = root / "binary.bin"
            binary_path.write_bytes(b"\xff\x00sk-" + b"b" * 24)
            with self.assertRaisesRegex(verifier.VerificationError, "secret-like"):
                verifier.scan_inventory(root, ["binary.bin"])
            large_path = root / "large.txt"
            large_path.write_text("four", encoding="utf-8")
            with mock.patch.object(verifier, "MAX_FILE_BYTES", 3):
                with self.assertRaisesRegex(verifier.VerificationError, "exceeds"):
                    verifier.scan_inventory(root, ["large.txt"])

    def test_full_station_verification_reports_zero_actions(self) -> None:
        report = verifier.verify_station(REPO_ROOT)
        self.assertEqual(report["verdict"], "PASS_PREPARATION_ONLY")
        self.assertEqual(
            report["verification_side_effects"],
            {"data_downloads": 0, "network_calls": 0, "model_calls": 0, "evaluator_runs": 0},
        )
        self.assertFalse(any(report["claims_earned"].values()))


if __name__ == "__main__":
    unittest.main()
