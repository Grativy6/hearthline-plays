from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_station as subject  # noqa: E402


class VerifyStationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_lock = json.loads((ROOT / "source-lock.v1.json").read_text(encoding="utf-8"))
        cls.status = json.loads(
            (ROOT / "status" / "station-status.v1.json").read_text(encoding="utf-8")
        )

    def test_current_source_lock_and_status_structures_are_valid(self) -> None:
        subject.validate_source_lock(copy.deepcopy(self.source_lock))
        subject.validate_station_status(copy.deepcopy(self.status))

    def test_source_lock_requires_exact_repositories_commits_and_anchor(self) -> None:
        mutations = (
            ("lineage", "series_anchor_commit", "0" * 40),
            ("sources.organizer_baseline", "commit", "0" * 40),
            (
                "sources.tracksdata",
                "repository",
                "https://github.com/royerlab/not-tracksdata.git",
            ),
        )
        for section, field, value in mutations:
            with self.subTest(section=section, field=field):
                document = copy.deepcopy(self.source_lock)
                target = document
                for part in section.split("."):
                    target = target[part]
                target[field] = value
                with self.assertRaises(subject.VerificationError):
                    subject.validate_source_lock(document)

    def test_source_lock_rejects_embedded_url_credentials_and_positive_claims(self) -> None:
        document = copy.deepcopy(self.source_lock)
        document["sources"]["tracksdata"]["repository"] = (
            "https://user:password@github.com/royerlab/tracksdata.git"
        )
        with self.assertRaises(subject.VerificationError):
            subject.validate_source_lock(document)

        document = copy.deepcopy(self.source_lock)
        document["claim_ceiling"]["competition_data_accessed"] = True
        with self.assertRaisesRegex(subject.VerificationError, "must be false"):
            subject.validate_source_lock(document)

    def test_status_requires_prepared_not_run_and_unverified_participation(self) -> None:
        for field, value in (
            ("status", "COMPLETE"),
            ("participation_status", "ENTERED"),
        ):
            document = copy.deepcopy(self.status)
            document[field] = value
            with self.assertRaises(subject.VerificationError):
                subject.validate_station_status(document)

    def test_status_requires_every_activity_counter_to_remain_zero_integer(self) -> None:
        fields = (
            "competition_data_files_opened",
            "competition_data_files_downloaded",
            "competition_data_bytes_read",
            "notebook_runs",
            "submissions",
            "leaderboard_scores",
        )
        for field in fields:
            with self.subTest(field=field):
                document = copy.deepcopy(self.status)
                document["counters"][field] = 1
                with self.assertRaises(subject.VerificationError):
                    subject.validate_station_status(document)
        document = copy.deepcopy(self.status)
        document["counters"]["submissions"] = False
        with self.assertRaisesRegex(subject.VerificationError, "must be an integer"):
            subject.validate_station_status(document)

    def test_status_requires_storage_and_authorization_boundaries(self) -> None:
        document = copy.deepcopy(self.status)
        document["storage"]["current_e_drive_allowed_for_competition_data"] = True
        with self.assertRaises(subject.VerificationError):
            subject.validate_station_status(document)

        document = copy.deepcopy(self.status)
        document["authorization"]["requires_new_instruction"] = ["make a submission"]
        with self.assertRaisesRegex(subject.VerificationError, "gate must cover"):
            subject.validate_station_status(document)

    def test_prohibited_path_patterns_cover_data_secrets_models_and_submission(self) -> None:
        prohibited = (
            "data/volume/chunk.bin",
            "fixtures/real.zarr/chunk",
            "private/kaggle.json",
            "weights/model.ckpt",
            "submission.csv",
            "nested/sample_submission.csv",
            ".cache/pinned-sources/repo/file.py",
        )
        for path in prohibited:
            with self.subTest(path=path):
                self.assertIsNotNone(subject.prohibited_path_reason(path))
        self.assertIsNone(subject.prohibited_path_reason("fixtures/submission.valid.synthetic.csv"))

    def test_secret_scanner_detects_common_material_without_embedding_it_in_repo(self) -> None:
        samples = (
            "AKI" + "A" + "B" * 16,
            "gh" + "p_" + "a" * 35,
            "sk" + "-proj-" + "a" * 30,
            "-----BEGIN " + "PRIVATE KEY-----",
            "KAGGLE_KEY=" + "A" * 32,
        )
        for sample in samples:
            with self.subTest(sample=sample[:8]):
                self.assertIsNotNone(subject.secret_text_reason(sample))
        self.assertIsNone(subject.secret_text_reason("KAGGLE_KEY=CHANGE_ME"))

    def test_inventory_scans_unignored_candidate_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            safe = root / "safe.md"
            secret = root / "secret.md"
            safe.write_text("synthetic fixture", encoding="utf-8")
            secret.write_text("API_KEY=" + "Z" * 30, encoding="utf-8")
            self.assertEqual(subject.validate_inventory(root, ["safe.md"]), 1)
            with self.assertRaisesRegex(subject.VerificationError, "credential-like"):
                subject.validate_inventory(root, ["secret.md"])

    def test_local_example_keeps_run_submission_and_e_drive_gates_closed(self) -> None:
        subject.validate_local_example(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            (root / "configs" / "local.example.toml").write_text(
                "[station]\nrun_enabled=true\n"
                "[submission]\nenabled=false\n"
                "[storage]\nforbidden_roots=['E:/']\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(subject.VerificationError, "run gate"):
                subject.validate_local_example(root)

    def test_json_loader_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema_version":"1.0","schema_version":"2.0"}', encoding="utf-8")
            with self.assertRaisesRegex(subject.VerificationError, "duplicate JSON key"):
                subject.load_json(path)


if __name__ == "__main__":
    unittest.main()
