from __future__ import annotations

import copy
import json
import tomllib
import unittest
from pathlib import Path

from tools import verify_calibration as verifier
from tools import verify_station

REPO_ROOT = Path(__file__).resolve().parents[1]


class VerifyCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (REPO_ROOT / verifier.CONFIG_PATH).open("rb") as handle:
            cls.config = tomllib.load(handle)
        cls.status = json.loads((REPO_ROOT / verifier.STATUS_PATH).read_text(encoding="utf-8"))
        cls.task_sha256 = verifier._sha256_bytes(REPO_ROOT / verifier.TASK_PATH)

    def test_current_package_passes_static_pre_dispatch_verification(self) -> None:
        report = verifier.verify_calibration(REPO_ROOT)
        self.assertEqual(report["verdict"], "PASS_STATIC_BLOCKED_REPAIR_READY")
        self.assertEqual(report["task_source_sha256"], self.task_sha256)
        self.assertEqual(report["maximum_model_calls"], 4)
        self.assertFalse(report["publication_enabled"])
        self.assertEqual(
            report["verification_side_effects"],
            {"network_calls": 0, "model_calls": 0, "evaluator_runs": 0, "external_writes": 0},
        )

    def test_config_binds_exact_task_source_digest(self) -> None:
        mutated = copy.deepcopy(self.config)
        mutated["hosted_task"]["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            verifier.CalibrationVerificationError,
            "task source SHA-256 mismatch",
        ):
            verifier.validate_config(mutated, task_sha256=self.task_sha256)

    def test_config_rejects_cell_budget_model_or_publication_drift(self) -> None:
        mutations = (
            lambda doc: doc["cells"][0].__setitem__("id", "WRONG"),
            lambda doc: doc["execution"].__setitem__("max_model_calls", 5),
            lambda doc: doc["model"].__setitem__("calibration_model", "gpt-5.6-luna"),
            lambda doc: doc["hosted_task"].__setitem__("publication_enabled", True),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                document = copy.deepcopy(self.config)
                mutate(document)
                with self.assertRaises(verifier.CalibrationVerificationError):
                    verifier.validate_config(document, task_sha256=self.task_sha256)

    def test_status_rejects_dispatch_or_formal_pilot_activity(self) -> None:
        for section, key, value in (
            ("dispatch", "model_calls", 1),
            ("dispatch", "publications", 1),
            ("formal_experiment", "pilot_identifiers_selected", 1),
        ):
            with self.subTest(section=section, key=key):
                document = copy.deepcopy(self.status)
                document[section][key] = value
                with self.assertRaises(verifier.CalibrationVerificationError):
                    verifier.validate_status(document, task_sha256=self.task_sha256)

    def test_source_has_frozen_cells_and_single_model_surface(self) -> None:
        report = verifier.validate_task_source(REPO_ROOT / verifier.TASK_PATH)
        self.assertEqual(report["cells"], 4)
        self.assertEqual(report["model_prompt_callsites"], 1)
        self.assertEqual(report["fresh_chat_callsites"], 1)
        self.assertEqual(report["task_run_callsites"], 1)

    def test_formal_station_requires_but_does_not_execute_calibration_artifacts(self) -> None:
        required = {
            verifier.CONFIG_PATH.as_posix(),
            verifier.TASK_PATH.as_posix(),
            verifier.STATUS_PATH.as_posix(),
            "docs/ROSETTA_CAL_001.md",
            "tools/verify_calibration.py",
            "tests/test_rosetta_cal_001_task.py",
            "tests/test_verify_calibration.py",
        }
        self.assertTrue(required.issubset(verify_station.REQUIRED_FILES))
        report = verify_station.verify_station(REPO_ROOT)
        self.assertEqual(report["verdict"], "PASS_PREPARATION_ONLY")
        self.assertEqual(report["verification_side_effects"]["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
