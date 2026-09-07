from __future__ import annotations

import copy
import importlib.util
import hashlib
import json
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
ARCHIVE_GUARD = load_module("orientation_archive_guard", "tools/orientation_archive_guard.py")
VALIDATE = load_module("validate_launchpad", "tools/validate_launchpad.py")


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


class OrientationArchiveClosureTests(unittest.TestCase):
    def test_all_five_archived_requests_reject_before_adapter(self):
        calls = []

        def trap(_: dict) -> None:
            calls.append("CONTACT")
            raise AssertionError("effect adapter must never run")

        for index in range(1, 6):
            path = ROOT / f"practice/requests/ORIENT-{index:04d}.json"
            with self.assertRaisesRegex(
                ARCHIVE_GUARD.ClosedOrientationArchive,
                "CLOSED_EXPIRED_AND_SPENT",
            ):
                ARCHIVE_GUARD.reject_archived_request(path, trap)
        self.assertEqual(calls, [])

    def test_active_replay_broker_is_absent(self):
        self.assertFalse((ROOT / "tools/arc3_replay_probe.py").exists())
        source = (ROOT / "tools/orientation_archive_guard.py").read_text(encoding="utf-8")
        for forbidden in ("import arc_agi", "urllib", "requests", "socket", "subprocess"):
            self.assertNotIn(forbidden, source)

    def test_exponent_overflow_is_rejected_by_active_json_boundaries(self):
        path = ROOT / "tests/.overflow-archive.json"
        path.write_bytes(b'{"request_id":"ORIENT-0001","overflow":1e999}')
        try:
            with self.assertRaisesRegex(
                ARCHIVE_GUARD.ClosedOrientationArchive,
                "non-finite JSON number",
            ):
                ARCHIVE_GUARD.reject_archived_request(path)
            with self.assertRaisesRegex(VALIDATE.ValidationError, "non-finite JSON number"):
                VALIDATE.read_json(path)
        finally:
            path.unlink(missing_ok=True)

    def test_historical_authority_is_bannered_and_body_is_preserved(self):
        grant = (ROOT / "launch/RUN_GRANT_2026-09-03.md").read_bytes()
        self.assertTrue(grant.startswith(
            b"> **Present-day status (4 September 2026): EXPIRED, SPENT, ARCHIVE-ONLY.**"
        ))
        marker = "# Run grant — public ARC-AGI-3 orientation, 3 September 2026\n".encode()
        body = grant[grant.index(marker):]
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "4cbd09a55ecb18c6a3c571ed54ab94f8fee1c2c52ba57c99867e6930822e08d8",
        )
        practice = (ROOT / "practice/README.md").read_text(encoding="utf-8")
        self.assertIn("EXPIRED, SPENT, AND NON-EXECUTABLE", practice)
        self.assertIn("They are not replayable instructions", practice)


class LaunchV4ClosureValidationTests(unittest.TestCase):
    def _inputs(self):
        lock = json.loads((ROOT / "launch/source-lock.v4.json").read_text(encoding="utf-8"))
        inventory = json.loads((ROOT / VALIDATE.RUNTIME_INVENTORY).read_text(encoding="utf-8"))
        receipt = json.loads((ROOT / VALIDATE.RUNTIME_REVIEW_RECEIPT).read_text(encoding="utf-8"))
        return lock, inventory, receipt

    def _validate(self, lock, inventory, receipt):
        VALIDATE._validate_source_lock(
            lock,
            inventory,
            receipt,
            inventory_digest=VALIDATE.RUNTIME_INVENTORY_SHA256,
            review_receipt_digest=VALIDATE.RUNTIME_REVIEW_RECEIPT_SHA256,
        )

    def test_current_v4_runtime_closure_validates(self):
        self._validate(*self._inputs())
        VALIDATE._validate_status(
            json.loads((ROOT / "launch/status/current.json").read_text(encoding="utf-8"))
        )

    def test_current_status_rejects_falsified_machine_evidence(self):
        mutations = {
            "machine_logs_sha256": "0" * 64,
            "machine_evidence_manifest_sha256": "1" * 64,
            "candidate_snapshot_sha256": "2" * 64,
            "output_sha256": "3" * 64,
            "runtime_inventory_path": "launch/runtime/other.json",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                status = json.loads(
                    (ROOT / "launch/status/current.json").read_text(encoding="utf-8")
                )
                status["reviewed_stage_evidence"][field] = value
                with self.assertRaisesRegex(
                    VALIDATE.ValidationError,
                    "reviewed stage evidence binding",
                ):
                    VALIDATE._validate_status(status)

    def test_current_status_rejects_extra_evidence_field(self):
        status = json.loads(
            (ROOT / "launch/status/current.json").read_text(encoding="utf-8")
        )
        status["reviewed_stage_evidence"]["unbound"] = True
        with self.assertRaisesRegex(VALIDATE.ValidationError, "reviewed stage evidence fields"):
            VALIDATE._validate_status(status)

    def test_current_status_rejects_predecessor_and_reconciliation_mutations(self):
        mutations = (
            ("predecessor sha", lambda status: status["predecessor"].update(sha256="0" * 64),
             "current status predecessor binding"),
            ("predecessor extra field", lambda status: status["predecessor"].update(unbound=True),
             "current status predecessor fields"),
            ("reconciliation path", lambda status: status.update(last_reconciliation="launch/receipts/other.json"),
             "current status reconciliation pointer"),
        )
        for label, mutate, expected_error in mutations:
            with self.subTest(case=label):
                status = json.loads(
                    (ROOT / "launch/status/current.json").read_text(encoding="utf-8")
                )
                mutate(status)
                with self.assertRaisesRegex(VALIDATE.ValidationError, expected_error):
                    VALIDATE._validate_status(status)

    def test_current_status_rejects_candidate_and_authority_mutations(self):
        mutations = (
            ("candidate source", lambda status: status["candidate"].update(agent_source="other.py"),
             "current candidate binding"),
            ("candidate extra field", lambda status: status["candidate"].update(unbound=True),
             "current candidate fields"),
            ("authority field", lambda status: status["authority"].update(current_gate_a_grant="PRESENT"),
             "current authority binding"),
            ("authority extra field", lambda status: status["authority"].update(unbound=False),
             "current authority fields"),
        )
        for label, mutate, expected_error in mutations:
            with self.subTest(case=label):
                status = json.loads(
                    (ROOT / "launch/status/current.json").read_text(encoding="utf-8")
                )
                mutate(status)
                with self.assertRaisesRegex(VALIDATE.ValidationError, expected_error):
                    VALIDATE._validate_status(status)

    def test_current_status_rejects_public_orientation_mutations(self):
        mutations = (
            lambda status: status["public_orientation"].update(workflow_runs=6),
            lambda status: status["public_orientation"].update(unbound=True),
        )
        expected_errors = (
            "current public orientation binding",
            "current public orientation fields",
        )
        for mutate, expected_error in zip(mutations, expected_errors, strict=True):
            with self.subTest(expected_error=expected_error):
                status = json.loads(
                    (ROOT / "launch/status/current.json").read_text(encoding="utf-8")
                )
                mutate(status)
                with self.assertRaisesRegex(VALIDATE.ValidationError, expected_error):
                    VALIDATE._validate_status(status)

    def test_current_status_rejects_competition_mutations(self):
        mutations = (
            lambda status: status["competition"].update(
                competition_submission_observed=True
            ),
            lambda status: status["competition"].update(unbound=False),
        )
        expected_errors = (
            "current competition status binding",
            "current competition status fields",
        )
        for mutate, expected_error in zip(mutations, expected_errors, strict=True):
            with self.subTest(expected_error=expected_error):
                status = json.loads(
                    (ROOT / "launch/status/current.json").read_text(encoding="utf-8")
                )
                mutate(status)
                with self.assertRaisesRegex(VALIDATE.ValidationError, expected_error):
                    VALIDATE._validate_status(status)

    def test_current_status_rejects_unbound_projection_text(self):
        mutations = (
            (
                lambda status: status.update(updated_at="2026-09-07T00:43:47Z"),
                "current status update timestamp",
            ),
            (
                lambda status: status["open_residuals"].append("unbound residual"),
                "current status residuals",
            ),
            (
                lambda status: status.update(reopening="rewrite sealed history"),
                "current status reopening boundary",
            ),
        )
        for mutate, expected_error in mutations:
            with self.subTest(expected_error=expected_error):
                status = json.loads(
                    (ROOT / "launch/status/current.json").read_text(encoding="utf-8")
                )
                mutate(status)
                with self.assertRaisesRegex(VALIDATE.ValidationError, expected_error):
                    VALIDATE._validate_status(status)

    def test_duplicate_canonical_inventory_name_fails(self):
        lock, inventory, receipt = self._inputs()
        mutated = copy.deepcopy(inventory)
        mutated["distributions"][1]["name"] = mutated["distributions"][0]["name"]
        with self.assertRaisesRegex(VALIDATE.ValidationError, "canonical names must be unique"):
            self._validate(lock, mutated, receipt)

    def test_reordered_inventory_fails(self):
        lock, inventory, receipt = self._inputs()
        mutated = copy.deepcopy(inventory)
        mutated["distributions"][0], mutated["distributions"][1] = (
            mutated["distributions"][1],
            mutated["distributions"][0],
        )
        with self.assertRaisesRegex(VALIDATE.ValidationError, "canonical names must be sorted"):
            self._validate(lock, mutated, receipt)

    def test_inventory_hash_mutation_fails(self):
        lock, inventory, receipt = self._inputs()
        mutated = copy.deepcopy(lock)
        mutated["dependency_resolution"]["reviewed_stage_runtime"]["inventory"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(VALIDATE.ValidationError, "reviewed runtime inventory binding"):
            self._validate(mutated, inventory, receipt)

    def test_inventory_file_digest_mismatch_fails(self):
        lock, inventory, receipt = self._inputs()
        with self.assertRaisesRegex(VALIDATE.ValidationError, "runtime inventory byte hash"):
            VALIDATE._validate_source_lock(
                lock,
                inventory,
                receipt,
                inventory_digest="0" * 64,
                review_receipt_digest=VALIDATE.RUNTIME_REVIEW_RECEIPT_SHA256,
            )

    def test_public_runtime_agents_conflation_fails(self):
        lock, inventory, receipt = self._inputs()
        mutated = copy.deepcopy(lock)
        public_agents = next(
            row for row in mutated["official_software"]
            if row["repository"] == "arcprize/ARC-AGI-3-Agents"
        )
        public_agents["inspected_file_bindings"]["agents/agent.py"]["sha256"] = (
            VALIDATE.RUNTIME_AGENTS_FILES["agents/agent.py"]
        )
        with self.assertRaisesRegex(VALIDATE.ValidationError, "Agents controlling-file bindings"):
            self._validate(mutated, inventory, receipt)

    def test_public_arc_source_tree_drift_fails(self):
        lock, inventory, receipt = self._inputs()
        mutated = copy.deepcopy(lock)
        public_toolkit = next(
            row
            for row in mutated["official_software"]
            if row["repository"] == "arcprize/ARC-AGI"
        )
        public_toolkit["tree"] = "0" * 40
        with self.assertRaisesRegex(VALIDATE.ValidationError, "ARC-AGI public source tree"):
            self._validate(mutated, inventory, receipt)

    def test_stale_current_source_lock_pointers_fail(self):
        status = json.loads((ROOT / "launch/status/current.json").read_text(encoding="utf-8"))
        status["source_lock"]["path"] = "launch/source-lock.v3.json"
        with self.assertRaisesRegex(VALIDATE.ValidationError, "current status source-lock pointer"):
            VALIDATE._validate_status(status)

        context = json.loads((ROOT / "launch/context/roles.v2.json").read_text(encoding="utf-8"))
        context["source_lock"] = "launch/source-lock.v3.json"
        with self.assertRaisesRegex(VALIDATE.ValidationError, "current source-lock pointer"):
            VALIDATE._validate_context_roles(context)


if __name__ == "__main__":
    unittest.main()
