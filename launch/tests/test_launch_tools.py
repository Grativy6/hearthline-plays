from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "launch" / "tools"
SCHEMAS = ROOT / "launch" / "schemas"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


frame_probe = load_module("frame_probe", TOOLS / "frame_probe.py")
static_pair = load_module("static_pair", TOOLS / "static_pair.py")
static_pair_v2 = load_module("static_pair_v2", TOOLS / "static_pair_v2.py")
orientation_console = load_module(
    "orientation_console", TOOLS / "orientation_console.py"
)


class FakeAction:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeEnvironment:
    def __init__(self, names: list[str]) -> None:
        self.action_space = [FakeAction(name) for name in names]


class FrameProbeTests(unittest.TestCase):
    def test_summary_components_and_auto_background(self) -> None:
        grid = [
            [0, 0, 0, 0],
            [0, 2, 2, 0],
            [0, 0, 3, 0],
            [0, 0, 0, 0],
        ]
        summary = frame_probe.summarize_grid(grid)
        self.assertEqual(summary["shape"], {"height": 4, "width": 4})
        self.assertEqual(summary["background_candidate"]["value"], 0)
        self.assertEqual(
            summary["background_candidate"]["basis"],
            "most_frequent_then_lowest",
        )
        self.assertEqual(summary["components_4_neighbor"]["2"][0]["size"], 2)
        self.assertEqual(summary["components_4_neighbor"]["3"][0]["size"], 1)

    def test_exact_diff(self) -> None:
        before = [[0, 1], [0, 0]]
        after = [[0, 0], [2, 0]]
        diff = frame_probe.diff_grids(before, after)
        self.assertTrue(diff["comparable"])
        self.assertEqual(diff["changed_cells"], 2)
        self.assertEqual(
            diff["transitions"],
            [
                {"from": 0, "to": 2, "count": 1},
                {"from": 1, "to": 0, "count": 1},
            ],
        )

    def test_explicit_background_is_labeled_explicit(self) -> None:
        summary = frame_probe.summarize_grid([[0, 0], [0, 1]], background=1)
        self.assertEqual(summary["background_candidate"], {"value": 1, "basis": "explicit"})

    def test_rejects_ragged_grid(self) -> None:
        with self.assertRaises(frame_probe.GridError):
            frame_probe.extract_last_grid([[0, 0], [0]])


class PairStaticTests(unittest.TestCase):
    def make_static(self, static_id: str, spark_id: str, lens: str) -> dict:
        return {
            "schema": "hearthline.spark-static.v1",
            "static_id": static_id,
            "predecessor_static_id": None,
            "task_id": "task-1",
            "spark_id": spark_id,
            "lens": lens,
            "observation_refs": ["event-1"],
            "claims": [
                {
                    "claim_id": f"claim-{static_id}",
                    "status": "INFERRED",
                    "text": "ACTION1 changes the visible state",
                    "evidence_refs": ["event-1"],
                    "confidence": 0.7,
                }
            ],
            "candidate_world_model": {"actor": {"movable": True}},
            "proposed_action": {
                "action": "ACTION1",
                "data": {},
                "reason": "test the inferred control",
            },
            "predicted_consequence": {"changed_cells": ">0"},
            "residuals": ["actor identity remains unresolved"],
            "claim_ceiling": "test fixture",
        }

    def test_pair_preserves_sources_and_does_not_pool(self) -> None:
        a = self.make_static("static-a", "spark-a", "geometry")
        b = self.make_static("static-b", "spark-b", "causal")
        pair = static_pair.compile_pair(a, b, "pair-1", "pair-static-1")
        self.assertEqual(pair["source_statics"], ["static-a", "static-b"])
        self.assertEqual(pair["estimates"]["pooling_rule"], "NONE")
        self.assertEqual(
            pair["recommended_discriminating_action"]["action"], "ACTION1"
        )
        self.assertIn(
            pair["comparison_class"],
            {
                "AGREEMENT_WITH_DEPENDENT_SUPPORT",
                "SAME_ACTION_DIFFERENT_REASONS",
            },
        )

    def test_rejects_task_mismatch(self) -> None:
        a = self.make_static("static-a", "spark-a", "geometry")
        b = self.make_static("static-b", "spark-b", "causal")
        b["task_id"] = "task-2"
        with self.assertRaises(static_pair.StaticError):
            static_pair.compile_pair(a, b, "pair-1", "pair-static-1")


class PairStaticV2Tests(unittest.TestCase):
    def make_static(self, static_id: str, role_id: str, value: str) -> dict:
        return {
            "schema": "hearthline.arc3.spark-static.v2",
            "static_id": static_id,
            "predecessor_static_id": None,
            "task_id": "task-v2",
            "role_id": role_id,
            "lens": "bounded-test",
            "observation_refs": ["sha256:frame-1"],
            "dependencies": ["shared-segmentation"],
            "claims": [{
                "claim_id": "claim-1",
                "epistemic_status": "HYPOTHESIS",
                "proposition": "candidate object identity",
                "value": value,
                "evidence_refs": ["sha256:frame-1"],
                "assumptions": ["palette stable"],
                "confidence": 0.5,
            }],
            "candidate_world_model": {"object": value},
            "recommendation": None,
            "residuals": ["identity unresolved"],
            "status": "UNRESOLVED",
            "claim_ceiling": "fixture only",
            "migration": None,
        }

    def test_v2_pair_retains_conditional_estimates(self) -> None:
        a = self.make_static("v2-a", "role-a", "red")
        b = self.make_static("v2-b", "role-b", "blue")
        pair = static_pair_v2.compile_pair(a, b, "pair-v2", "pair-static-v2")
        self.assertEqual(pair["schema"], "hearthline.arc3.pair-static.v2")
        self.assertEqual(pair["pooling_rule"], "NONE")
        self.assertEqual(len(pair["conditional_estimates"]), 2)
        self.assertEqual(pair["comparison_class"], "CONFLICTING_CONDITIONAL_ACCOUNTS")

    def test_both_v1_dialects_migrate_to_explicit_v2(self) -> None:
        paths = [
            ROOT / "templates" / "spark-a.static.json",
            ROOT / "launch" / "templates" / "spark-static.blank.json",
        ]
        dialects = []
        for path in paths:
            raw = path.read_bytes()
            value = json.loads(raw)
            migrated = static_pair_v2.migrate_v1_static(value, "0" * 64)
            static_pair_v2.validate_spark(migrated)
            dialects.append(migrated["migration"]["source_dialect"])
        self.assertEqual(dialects, ["root-v1", "launch-v1"])


class OrientationPolicyTests(unittest.TestCase):
    def test_calibration_uses_declared_order(self) -> None:
        policy = orientation_console.StateNoveltyPolicy(seed=3)
        env = FakeEnvironment(["ACTION1", "ACTION2", "ACTION3", "ACTION4"])
        response = object()
        summary = {"components_4_neighbor": {}}
        names = []
        for state_id in ("s0", "s1", "s2", "s3"):
            choice = policy.choose(env, response, summary, state_id)
            self.assertIsNotNone(choice)
            action, data, prediction = choice
            names.append(action.name)
            self.assertEqual(data, {})
            self.assertEqual(prediction["phase"], "CALIBRATION")
        self.assertEqual(names, ["ACTION1", "ACTION4", "ACTION2", "ACTION3"])

    def test_click_targets_are_bounded_and_unique(self) -> None:
        summary = {
            "components_4_neighbor": {
                "2": [
                    {"size": 4, "centroid": {"x": 63.4, "y": -0.4}},
                    {"size": 1, "centroid": {"x": 10, "y": 20}},
                ]
            }
        }
        targets = orientation_console.component_click_targets(summary)
        self.assertEqual(len(targets), len({(item["x"], item["y"]) for item in targets}))
        self.assertTrue(all(0 <= item["x"] <= 63 for item in targets))
        self.assertTrue(all(0 <= item["y"] <= 63 for item in targets))


class RepositorySurfaceTests(unittest.TestCase):
    def test_json_documents_parse(self) -> None:
        paths = list(SCHEMAS.glob("*.json")) + list(
            (ROOT / "launch" / "templates").glob("*.json")
        )
        self.assertGreaterEqual(len(paths), 5)
        for path in paths:
            with self.subTest(path=path):
                json.loads(path.read_text(encoding="utf-8"))

    def test_tools_compile_as_loaded_modules(self) -> None:
        self.assertEqual(
            orientation_console.OFFICIAL_COMMIT,
            "f12822c4d550121c35a275008d964afbbed47d2f",
        )
        self.assertEqual(orientation_console.POLICY_ID, "hearthline-state-novelty-v0.1")

    def test_orientation_console_has_no_effect_adapter(self) -> None:
        source = (TOOLS / "orientation_console.py").read_text(encoding="utf-8")
        self.assertEqual(orientation_console.EXECUTION_STATUS, "RETIRED_OFFLINE_ONLY")
        for forbidden in ("import arc_agi", "OperationMode", "allow-public-contact"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
