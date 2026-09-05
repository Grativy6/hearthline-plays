from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from tools import show_public_micro_episode as viewer

EXPECTED_IDS = [
    "LANTERN-LEDGER-01",
    "LANTERN-REFORMULATE-01",
    "LANTERN-RESET-01",
]


def run_cli(*arguments: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = viewer.main(list(arguments))
    return status, stdout.getvalue(), stderr.getvalue()


class ShowPublicMicroEpisodeTests(unittest.TestCase):
    def test_default_lists_only_episode_ids(self) -> None:
        status, stdout, stderr = run_cli()
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        result = json.loads(stdout)
        self.assertEqual(result["view"], "index")
        self.assertEqual(result["episode_ids"], EXPECTED_IDS)
        self.assertNotIn("learner_view", stdout)
        self.assertNotIn("coach_view", stdout)

    def test_episode_defaults_to_learner_view_without_coach_material(self) -> None:
        status, stdout, stderr = run_cli("LANTERN-LEDGER-01")
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        result = json.loads(stdout)
        self.assertEqual(result["view"], "learner_view")
        self.assertIn("learner_view", result)
        self.assertNotIn("coach_view", result)
        self.assertNotIn("earned_correspondences", stdout)

    def test_coach_view_requires_explicit_answer_sealed(self) -> None:
        status, stdout, stderr = run_cli("LANTERN-LEDGER-01", "--coach-view")
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(
            json.loads(stderr),
            {"error": "--coach-view requires explicit --answer-sealed"},
        )

    def test_sealed_answer_unlocks_only_requested_coach_view(self) -> None:
        status, stdout, stderr = run_cli(
            "LANTERN-LEDGER-01", "--coach-view", "--answer-sealed"
        )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        result = json.loads(stdout)
        self.assertEqual(result["view"], "coach_view")
        self.assertTrue(result["answer_sealed"])
        self.assertIn("coach_view", result)
        self.assertNotIn("learner_view", result)

    def test_unknown_episode_id_is_rejected(self) -> None:
        status, stdout, stderr = run_cli("NOT-AN-EPISODE")
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(
            json.loads(stderr), {"error": "unknown episode ID: NOT-AN-EPISODE"}
        )

    def test_output_is_deterministic(self) -> None:
        first = run_cli("LANTERN-REFORMULATE-01")
        second = run_cli("LANTERN-REFORMULATE-01")
        self.assertEqual(first, second)
        self.assertTrue(first[1].endswith("\n"))
        self.assertEqual(first[1].count("\n"), 1)

    def test_answer_sealed_without_coach_view_is_rejected(self) -> None:
        status, stdout, stderr = run_cli("LANTERN-RESET-01", "--answer-sealed")
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(
            json.loads(stderr),
            {"error": "--answer-sealed is only valid with --coach-view"},
        )


if __name__ == "__main__":
    unittest.main()
