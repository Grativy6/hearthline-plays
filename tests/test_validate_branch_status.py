from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_branch_status", ROOT / "tools" / "validate_branch_status.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
MANIFEST = ROOT / "manifests" / "branch-status.v1.json"


class BranchStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = MODULE.load(MANIFEST)

    def assert_invalid(self, data: dict[str, object]) -> None:
        with self.assertRaises(MODULE.ValidationError):
            MODULE.validate(data)

    def test_canonical_manifest_passes(self) -> None:
        MODULE.validate(self.data)

    def test_duplicate_json_key_fails(self) -> None:
        with self.assertRaises(MODULE.ValidationError):
            json.loads('{"a":1,"a":2}', object_pairs_hook=MODULE.unique_object)

    def test_duplicate_or_unsorted_branch_fails(self) -> None:
        changed = copy.deepcopy(self.data)
        changed["branches"][1]["name"] = changed["branches"][0]["name"]
        self.assert_invalid(changed)

    def test_changed_tip_or_tree_fails(self) -> None:
        for key in ("commit", "tree"):
            changed = copy.deepcopy(self.data)
            branch = next(item for item in changed["branches"] if item["name"] == MODULE.ARC3_BRANCH)
            branch[key] = "0" * 40
            self.assert_invalid(changed)

    def test_missing_runtime_blocker_fails(self) -> None:
        changed = copy.deepcopy(self.data)
        branch = next(item for item in changed["branches"] if item["name"] == MODULE.ARC3_BRANCH)
        branch["declared_status"].remove(MODULE.ARC3_BLOCKER)
        self.assert_invalid(changed)

    def test_open_authority_flag_fails(self) -> None:
        changed = copy.deepcopy(self.data)
        changed["authority"]["grants_external_action"] = True
        self.assert_invalid(changed)

    def test_ci_head_run_or_conclusion_mismatch_fails(self) -> None:
        for key, value in (("head_sha", "0" * 40), ("id", 1), ("conclusion", "failure")):
            changed = copy.deepcopy(self.data)
            changed["canonical_arc3_candidate_ci"]["runs"][0][key] = value
            self.assert_invalid(changed)

    def test_missing_inherited_classification_fails(self) -> None:
        changed = copy.deepcopy(self.data)
        branch = next(item for item in changed["branches"] if item["name"].startswith("millennium/"))
        branch["claim_ceiling"] = "play only"
        self.assert_invalid(changed)

    def test_unsafe_path_or_url_fails(self) -> None:
        changed = copy.deepcopy(self.data)
        changed["branches"][0]["status_source_paths"] = ["../secret"]
        self.assert_invalid(changed)
        changed = copy.deepcopy(self.data)
        changed["branches"][0]["branch_url"] = "https://user:pass@github.com/Grativy6/hearthline-plays/tree/x"
        self.assert_invalid(changed)


if __name__ == "__main__":
    unittest.main()
