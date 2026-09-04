"""Synthetic and metadata-only tests for fail-closed readiness gates."""

from __future__ import annotations

import copy
import hashlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import preflight  # noqa: E402
from hearthline_arc2.authorization import (  # noqa: E402
    AuthorizationError,
    record_preflight_consumption,
)


class PreflightTests(unittest.TestCase):
    def test_owned_json_schemas_and_deterministic_pipeline_pass(self) -> None:
        preflight.check_json_and_schema_surfaces()
        preflight.check_synthetic_fixtures()
        preflight.check_synthetic_pipeline()

    def test_exact_source_lock_passes_in_development(self) -> None:
        preflight.check_source_lock("dev")

    def test_external_mode_rejects_unfrozen_mutable_sources(self) -> None:
        with self.assertRaisesRegex(preflight.PreflightError, "human-reviewed"):
            preflight.check_source_lock("public-eval")

    def test_development_ci_can_inspect_a_complete_fresh_review_state(self) -> None:
        real_load = preflight.load_json
        lock_path = ROOT / "provenance" / "official-sources.lock.json"
        reviewed = copy.deepcopy(real_load(lock_path))
        now = datetime.now(timezone.utc)
        for surface in reviewed["mutable_surfaces"]:
            surface.update(
                {
                    "content_sha256": hashlib.sha256(
                        surface["url"].encode("utf-8")
                    ).hexdigest(),
                    "status": preflight.FROZEN,
                    "retrieval_utc": (now - timedelta(minutes=1))
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z"),
                    "human_reviewer": "Christopher D. Pang",
                    "revalidate_before": (now + timedelta(days=1))
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z"),
                }
            )

        def load_reviewed(path):
            return reviewed if Path(path) == lock_path else real_load(path)

        with mock.patch.object(preflight, "load_json", side_effect=load_reviewed):
            preflight.check_source_lock("dev")

        hidden = reviewed["challenge_commitments"]["KAGGLE_HIDDEN"]
        hidden.update(
            {
                "status": preflight.FROZEN,
                "challenge_raw_sha256": "8" * 64,
                "challenge_semantic_sha256": "9" * 64,
                "task_count": 1,
                "test_input_count": 1,
                "retrieval_utc": (now - timedelta(minutes=1))
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                "human_reviewer": "Christopher D. Pang",
                "revalidate_before": (now + timedelta(days=1))
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
            }
        )
        with mock.patch.object(preflight, "load_json", side_effect=load_reviewed):
            preflight.check_source_lock("dev")

    def test_one_character_git_pin_mutation_fails_closed(self) -> None:
        real_load = preflight.load_json
        lock_path = ROOT / "provenance" / "official-sources.lock.json"
        mutated = copy.deepcopy(real_load(lock_path))
        mutated["git_sources"][0]["commit"] = "0" + mutated["git_sources"][0][
            "commit"
        ][1:]

        def load_with_mutation(path):
            return mutated if Path(path) == lock_path else real_load(path)

        with mock.patch.object(preflight, "load_json", side_effect=load_with_mutation):
            with self.assertRaises(preflight.PreflightError):
                preflight.check_source_lock("dev")

    def test_duplicate_mutable_url_fails_closed(self) -> None:
        real_load = preflight.load_json
        lock_path = ROOT / "provenance" / "official-sources.lock.json"
        mutated = copy.deepcopy(real_load(lock_path))
        mutated["mutable_surfaces"][1]["url"] = mutated["mutable_surfaces"][0][
            "url"
        ]

        def load_with_mutation(path):
            return mutated if Path(path) == lock_path else real_load(path)

        with mock.patch.object(preflight, "load_json", side_effect=load_with_mutation):
            with self.assertRaises(preflight.PreflightError):
                preflight.check_source_lock("dev")

    def test_external_notebook_metadata_rejects_placeholder(self) -> None:
        template = ROOT / "notebook" / "kernel-metadata.template.json"
        with self.assertRaisesRegex(preflight.PreflightError, "placeholder"):
            preflight.check_notebook("kaggle", template)

    def test_solver_boundary_and_notebook_lint_pass(self) -> None:
        preflight.check_no_external_capability()
        preflight.check_notebook("dev")

    def test_grant_identity_pair_consumption_is_coupled_and_single_use(self) -> None:
        grant = {
            "grant_id": "synthetic-consumption-test",
            "nonce": "7" * 64,
            "scope": "PUBLIC_EVAL_ONCE",
        }
        with tempfile.TemporaryDirectory() as directory:
            consumption = Path(directory)
            marker = record_preflight_consumption(grant, consumption)
            self.assertTrue(marker.is_file())
            with self.assertRaisesRegex(AuthorizationError, "already spent"):
                record_preflight_consumption(grant, consumption)


if __name__ == "__main__":
    unittest.main()
