from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PAIR = load_module("pair_static", "tools/pair_static.py")
PROBE = load_module("arc3_replay_probe", "tools/arc3_replay_probe.py")


class PairStaticTests(unittest.TestCase):
    def test_disagreement_retained_without_average(self):
        a = json.loads((ROOT / "templates/spark-a.static.json").read_text())
        b = json.loads((ROOT / "templates/spark-b.static.json").read_text())
        a.update(static_id="A", task_id="T", dependencies=["same-model"])
        b.update(static_id="B", task_id="T", dependencies=["same-model"])
        a["claims"] = [{
            "claim_id":"goal","kind":"HYPOTHESIS","value":"red",
            "confidence":0.7,"evidence_refs":["f0"],"assumptions":["color causal"]
        }]
        b["claims"] = [{
            "claim_id":"goal","kind":"HYPOTHESIS","value":"blue",
            "confidence":0.4,"evidence_refs":["f0"],"assumptions":["shape causal"]
        }]
        result = PAIR.build_pair(a, b, "P")
        self.assertEqual(result["pooling_rule"], "NONE")
        self.assertEqual(result["load_bearing_seam"], "goal")
        self.assertEqual(len(result["disagreements"]), 1)
        self.assertIn("same-model", result["shared_dependencies"])

    def test_task_mismatch_fails(self):
        a = json.loads((ROOT / "templates/spark-a.static.json").read_text())
        b = json.loads((ROOT / "templates/spark-b.static.json").read_text())
        a.update(static_id="A", task_id="T1")
        b.update(static_id="B", task_id="T2")
        with self.assertRaises(ValueError):
            PAIR.build_pair(a, b, "P")


class ProbePureFunctionTests(unittest.TestCase):
    def test_components(self):
        grid = [
            [0,0,0,0],
            [0,1,1,0],
            [0,0,2,0],
            [0,0,2,0],
        ]
        result = PROBE.connected_components(grid)
        self.assertEqual(result["background"], 0)
        sizes = sorted(c["size"] for c in result["components"])
        self.assertEqual(sizes, [2,2])

    def test_empty_orientation_request(self):
        req = {
            "schema":"hearthline.arc3-orientation-request.v1",
            "request_id":"ORIENT-0001","game_id":"ls20","seed":0,
            "mode":"PUBLIC_ORIENTATION","source_world_model":"practice/ls20/world-model.json",
            "actions":[],"max_actions":0,"close_scorecard":True,
            "grant_ref":"launch/RUN_GRANT_2026-09-03.md","status":"AUTHORIZED"
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "req.json"
            p.write_text(json.dumps(req))
            loaded = PROBE.load_request(p)
        self.assertEqual(loaded["request_id"], "ORIENT-0001")

    def test_private_game_rejected(self):
        req = {
            "schema":"hearthline.arc3-orientation-request.v1",
            "request_id":"ORIENT-0001","game_id":"secret","seed":0,
            "mode":"PUBLIC_ORIENTATION","source_world_model":"x",
            "actions":[],"max_actions":0,"close_scorecard":True,
            "grant_ref":"launch/RUN_GRANT_2026-09-03.md","status":"AUTHORIZED"
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "req.json"
            p.write_text(json.dumps(req))
            with self.assertRaises(ValueError):
                PROBE.load_request(p)


if __name__ == "__main__":
    unittest.main()
