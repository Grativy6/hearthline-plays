"""Focused tests for frozen external metadata, config, and input bindings."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from hearthline_arc2.validation import (  # noqa: E402
    ARC2_PUBLIC_COMMIT,
    ARC2_PUBLIC_REPOSITORY,
    ARC2_PUBLIC_TREE,
    COMPETITION_SLUG,
    PUBLIC_CHALLENGE_COMMITMENTS,
    ValidationError,
    challenge_semantic_sha256,
    kernel_metadata_hardware_class,
    load_json,
    validate_input_manifest,
    validate_kernel_metadata,
    validate_solver_config,
    validate_source_lock,
)
from tools import preflight  # noqa: E402


FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"
SOURCE_LOCK = ROOT / "provenance" / "official-sources.lock.json"


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def valid_config(
    *, hardware_class: str = "kaggle-cpu", runtime: int = 39600
) -> dict[str, object]:
    return {
        "schema": "hearthline-plays.arc2-solver-config.v1",
        "competition_slug": COMPETITION_SLUG,
        "solver_id": "baseline.identity-zero.v1",
        "seed": 0,
        "seed_policy": "FIXED_INTEGER_PER_TASK",
        "deterministic": True,
        "wall_budget_seconds": runtime,
        "cpu_budget_seconds": runtime,
        "max_work_units": 1,
        "hardware_class": hardware_class,
        "dependency_identities": [],
        "model_identities": [],
        "max_attempts_per_test_input": 2,
        "network_required": False,
    }


def valid_input_manifest(
    *,
    split: str,
    challenge_filename: str,
    challenge_origin: str,
    challenge_raw_sha256: str = "1" * 64,
    challenge_semantic_sha256_value: str | None = None,
    challenge_byte_count: int = 1,
    task_count: int = 1,
    test_input_count: int = 1,
    source_lock_path: Path = SOURCE_LOCK,
) -> dict[str, object]:
    if challenge_semantic_sha256_value is None:
        if split in PUBLIC_CHALLENGE_COMMITMENTS:
            challenge_semantic_sha256_value = str(
                PUBLIC_CHALLENGE_COMMITMENTS[split]["challenge_semantic_sha256"]
            )
        else:
            challenge_semantic_sha256_value = "2" * 64
    manifest: dict[str, object] = {
        "schema": "hearthline-plays.arc2-input-manifest.v1",
        "competition_slug": COMPETITION_SLUG,
        "split": split,
        "challenge_origin": challenge_origin,
        "challenge_filename": challenge_filename,
        "challenge_raw_sha256": challenge_raw_sha256,
        "challenge_semantic_sha256": challenge_semantic_sha256_value,
        "challenge_byte_count": challenge_byte_count,
        "task_count": task_count,
        "test_input_count": test_input_count,
        "source_lock_sha256": sha256_path(source_lock_path),
        "labels_included": False,
        "official_data_vendored": False,
    }
    if split in PUBLIC_CHALLENGE_COMMITMENTS:
        manifest.update(
            {
                "arc2_public_repository": ARC2_PUBLIC_REPOSITORY,
                "arc2_public_commit": ARC2_PUBLIC_COMMIT,
                "arc2_public_tree": ARC2_PUBLIC_TREE,
            }
        )
    return manifest


class KernelMetadataContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = load_json(ROOT / "notebook" / "kernel-metadata.template.json")

    def test_template_is_valid_only_as_an_explicit_placeholder(self) -> None:
        validate_kernel_metadata(self.template, allow_placeholder_id=True)
        with self.assertRaisesRegex(ValidationError, "placeholder"):
            validate_kernel_metadata(self.template)
        self.assertEqual(kernel_metadata_hardware_class(self.template), "kaggle-cpu")

    def test_private_network_and_source_boundaries_are_closed(self) -> None:
        mutations = {
            "unknown key": lambda value: value.update({"extra": True}),
            "public": lambda value: value.update({"is_private": False}),
            "internet": lambda value: value.update({"enable_internet": True}),
            "tpu": lambda value: value.update({"enable_tpu": True}),
            "dataset": lambda value: value.update({"dataset_sources": ["owner/data"]}),
            "kernel": lambda value: value.update({"kernel_sources": ["owner/kernel"]}),
            "model": lambda value: value.update(
                {"model_sources": ["owner/model/framework/variant/1"]}
            ),
            "cpu shape": lambda value: value.update(
                {"enable_gpu": False, "machine_shape": "NvidiaTeslaT4"}
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = copy.deepcopy(self.template)
                mutate(candidate)
                with self.assertRaises(ValidationError):
                    validate_kernel_metadata(candidate, allow_placeholder_id=True)

    def test_accelerator_has_a_finite_shape_and_deterministic_hardware_class(self) -> None:
        metadata = copy.deepcopy(self.template)
        metadata["id"] = "christopher/hearthline-arc-agi-2-2026"
        metadata["enable_gpu"] = True
        metadata["machine_shape"] = "NvidiaTeslaT4"
        validate_kernel_metadata(metadata)
        self.assertEqual(
            kernel_metadata_hardware_class(metadata),
            "kaggle-accelerator:NvidiaTeslaT4",
        )
        metadata["machine_shape"] = "FutureUnreviewedGpu"
        with self.assertRaisesRegex(ValidationError, "pinned Kaggle API"):
            validate_kernel_metadata(metadata)
        metadata["machine_shape"] = "Tpu1VmV38"
        with self.assertRaisesRegex(ValidationError, "pinned Kaggle API"):
            validate_kernel_metadata(metadata)

    def test_embedded_notebook_accelerator_must_match_frozen_metadata(self) -> None:
        metadata = copy.deepcopy(self.template)
        metadata["id"] = "christopher/hearthline-arc-agi-2-2026"
        metadata["enable_gpu"] = True
        metadata["machine_shape"] = "NvidiaTeslaT4"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel-metadata.json"
            write_json(path, metadata)
            with self.assertRaisesRegex(
                preflight.PreflightError, "accelerator settings differ"
            ):
                preflight.check_notebook(
                    "kaggle",
                    path,
                    hardware_class="kaggle-accelerator:NvidiaTeslaT4",
                    max_runtime_seconds=39600,
                )


class FrozenExternalArtifactTests(unittest.TestCase):
    def test_solver_config_is_closed_and_bound_to_hardware_and_runtime(self) -> None:
        config = valid_config()
        validate_solver_config(
            config,
            expected_hardware_class="kaggle-cpu",
            expected_max_runtime_seconds=39600,
            expected_solver_id="baseline.identity-zero.v1",
        )
        mutations = {
            "unknown": lambda value: value.update({"extra": 1}),
            "network": lambda value: value.update({"network_required": True}),
            "attempts": lambda value: value.update(
                {"max_attempts_per_test_input": 3}
            ),
            "hardware": lambda value: value.update({"hardware_class": "other"}),
            "runtime": lambda value: value.update({"wall_budget_seconds": 39599}),
            "solver": lambda value: value.update({"solver_id": "other.solver.v1"}),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = copy.deepcopy(config)
                mutate(candidate)
                with self.assertRaises(ValidationError):
                    validate_solver_config(
                        candidate,
                        expected_hardware_class="kaggle-cpu",
                        expected_max_runtime_seconds=39600,
                        expected_solver_id="baseline.identity-zero.v1",
                    )

    def test_public_manifests_bind_git_and_independent_commitments(self) -> None:
        split_filenames = {
            "TRAINING": "arc-agi_training_challenges.json",
            "PUBLIC_EVALUATION": "arc-agi_evaluation_challenges.json",
        }
        for split, filename in split_filenames.items():
            with self.subTest(split=split):
                commitment = PUBLIC_CHALLENGE_COMMITMENTS[split]
                manifest = valid_input_manifest(
                    split=split,
                    challenge_filename=filename,
                    challenge_origin="PINNED_ARC2_PUBLIC_REPOSITORY",
                    task_count=int(commitment["task_count"]),
                    test_input_count=int(commitment["test_input_count"]),
                )
                validate_input_manifest(
                    manifest,
                    source_lock_path=SOURCE_LOCK,
                    expected_split=split,
                )

                mutations = {
                    "semantic digest": lambda value: value.update(
                        {"challenge_semantic_sha256": "3" * 64}
                    ),
                    "task count": lambda value: value.update(
                        {"task_count": int(commitment["task_count"]) + 1}
                    ),
                    "source repository": lambda value: value.update(
                        {"arc2_public_repository": "other/repository"}
                    ),
                    "source commit": lambda value: value.update(
                        {"arc2_public_commit": "1" * 40}
                    ),
                    "source tree": lambda value: value.update(
                        {"arc2_public_tree": "2" * 40}
                    ),
                    "unknown": lambda value: value.update({"extra": 1}),
                }
                for label, mutate in mutations.items():
                    with self.subTest(split=split, mutation=label):
                        candidate = copy.deepcopy(manifest)
                        mutate(candidate)
                        with self.assertRaises(ValidationError):
                            validate_input_manifest(
                                candidate,
                                source_lock_path=SOURCE_LOCK,
                                expected_split=split,
                            )

    def test_renamed_arbitrary_file_cannot_satisfy_public_commitment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            challenge_path = Path(directory) / "arc-agi_evaluation_challenges.json"
            challenge_path.write_bytes((FIXTURES / "challenges.json").read_bytes())
            commitment = PUBLIC_CHALLENGE_COMMITMENTS["PUBLIC_EVALUATION"]
            manifest = valid_input_manifest(
                split="PUBLIC_EVALUATION",
                challenge_filename=challenge_path.name,
                challenge_origin="PINNED_ARC2_PUBLIC_REPOSITORY",
                challenge_raw_sha256=sha256_path(challenge_path),
                challenge_semantic_sha256_value=str(
                    commitment["challenge_semantic_sha256"]
                ),
                challenge_byte_count=challenge_path.stat().st_size,
                task_count=int(commitment["task_count"]),
                test_input_count=int(commitment["test_input_count"]),
            )
            with self.assertRaises(ValidationError):
                validate_input_manifest(
                    manifest,
                    challenge_path=challenge_path,
                    source_lock_path=SOURCE_LOCK,
                    expected_split="PUBLIC_EVALUATION",
                )

    def test_source_lock_closes_independent_commitment_fields(self) -> None:
        source_lock = load_json(SOURCE_LOCK)
        validate_source_lock(source_lock, required_split="TRAINING")
        validate_source_lock(source_lock, required_split="PUBLIC_EVALUATION")
        with self.assertRaisesRegex(ValidationError, "still unfrozen"):
            validate_source_lock(source_lock, required_split="KAGGLE_HIDDEN")

        mutations = {
            "public semantic digest": lambda value: value[
                "challenge_commitments"
            ]["PUBLIC_EVALUATION"].update(
                {"challenge_semantic_sha256": "4" * 64}
            ),
            "public subtree": lambda value: value["challenge_commitments"][
                "TRAINING"
            ].update({"source_tree": "5" * 40}),
            "extra commitment field": lambda value: value[
                "challenge_commitments"
            ]["TRAINING"].update({"extra": 1}),
            "extra mutable-source field": lambda value: value[
                "mutable_surfaces"
            ][0].update({"extra": 1}),
            "public Git root": lambda value: next(
                item
                for item in value["git_sources"]
                if item["repository"] == ARC2_PUBLIC_REPOSITORY
            ).update({"tree": "6" * 40}),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = copy.deepcopy(source_lock)
                mutate(candidate)
                with self.assertRaises(ValidationError):
                    validate_source_lock(candidate, required_split="TRAINING")

    def test_preflight_rejects_arbitrary_config_and_manifest_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.json"
            manifest_path = root / "manifest.json"
            challenge_path = root / "arc-agi_evaluation_challenges.json"
            write_json(config_path, {})
            write_json(manifest_path, {})
            challenge_path.write_bytes((FIXTURES / "challenges.json").read_bytes())
            bindings = preflight.ExternalBindings(
                config=config_path,
                input_manifest=manifest_path,
                challenge_file=challenge_path,
                output_dir=root / "outside",
                hardware_class="local-cpu",
                max_runtime_seconds=39600,
            )
            with self.assertRaises(preflight.PreflightError):
                preflight.check_external_bindings("public-eval", bindings)

    def test_kaggle_hidden_binds_separate_human_frozen_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            challenge_path = root / "arc-agi_test_challenges.json"
            challenge_path.write_bytes((FIXTURES / "challenges.json").read_bytes())
            semantic_sha256 = challenge_semantic_sha256(load_json(challenge_path))

            frozen_lock = load_json(SOURCE_LOCK)
            frozen_lock["challenge_commitments"]["KAGGLE_HIDDEN"] = {
                "status": "FROZEN_HUMAN_REVIEWED",
                "origin": "KAGGLE_COMPETITION_MOUNT",
                "challenge_filename": "arc-agi_test_challenges.json",
                "challenge_raw_sha256": sha256_path(challenge_path),
                "challenge_semantic_sha256": semantic_sha256,
                "task_count": 2,
                "test_input_count": 3,
                "retrieval_utc": (
                    datetime.now(timezone.utc) - timedelta(minutes=1)
                ).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "human_reviewer": "Christopher D. Pang",
                "revalidate_before": (
                    datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
            source_lock_path = root / "source-lock.json"
            write_json(source_lock_path, frozen_lock)
            validate_source_lock(
                load_json(source_lock_path), required_split="KAGGLE_HIDDEN"
            )

            stale_lock = copy.deepcopy(frozen_lock)
            stale_lock["challenge_commitments"]["KAGGLE_HIDDEN"].update(
                {
                    "retrieval_utc": "2000-01-01T00:00:00Z",
                    "revalidate_before": "2000-01-01T00:00:01Z",
                }
            )
            with self.assertRaisesRegex(ValidationError, "stale"):
                validate_source_lock(stale_lock, required_split="KAGGLE_HIDDEN")

            manifest = valid_input_manifest(
                split="KAGGLE_HIDDEN",
                challenge_filename="arc-agi_test_challenges.json",
                challenge_origin="KAGGLE_COMPETITION_MOUNT",
                challenge_raw_sha256=sha256_path(challenge_path),
                challenge_semantic_sha256_value=semantic_sha256,
                challenge_byte_count=challenge_path.stat().st_size,
                task_count=2,
                test_input_count=3,
                source_lock_path=source_lock_path,
            )
            self.assertFalse(
                {"arc2_public_repository", "arc2_public_commit", "arc2_public_tree"}
                & set(manifest)
            )
            validate_input_manifest(
                manifest,
                challenge_path=challenge_path,
                source_lock_path=source_lock_path,
                expected_split="KAGGLE_HIDDEN",
            )

            mutations = {
                "raw digest": lambda value: value.update(
                    {"challenge_raw_sha256": "7" * 64}
                ),
                "semantic digest": lambda value: value.update(
                    {"challenge_semantic_sha256": "8" * 64}
                ),
                "task count": lambda value: value.update({"task_count": 3}),
                "public Git claim": lambda value: value.update(
                    {"arc2_public_repository": ARC2_PUBLIC_REPOSITORY}
                ),
            }
            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    candidate = copy.deepcopy(manifest)
                    mutate(candidate)
                    with self.assertRaises(ValidationError):
                        validate_input_manifest(
                            candidate,
                            challenge_path=challenge_path,
                            source_lock_path=source_lock_path,
                            expected_split="KAGGLE_HIDDEN",
                        )

            original_challenge = challenge_path.read_bytes()
            challenge_path.write_bytes(original_challenge + b" ")
            self.assertEqual(
                challenge_semantic_sha256(load_json(challenge_path)), semantic_sha256
            )
            with self.assertRaisesRegex(ValidationError, "challenge bytes"):
                validate_input_manifest(
                    manifest,
                    challenge_path=challenge_path,
                    source_lock_path=source_lock_path,
                    expected_split="KAGGLE_HIDDEN",
                )

    def test_kaggle_hidden_rejects_the_unfrozen_readiness_lock(self) -> None:
        manifest = valid_input_manifest(
            split="KAGGLE_HIDDEN",
            challenge_filename="arc-agi_test_challenges.json",
            challenge_origin="KAGGLE_COMPETITION_MOUNT",
        )
        with self.assertRaisesRegex(ValidationError, "still unfrozen"):
            validate_input_manifest(
                manifest,
                source_lock_path=SOURCE_LOCK,
                expected_split="KAGGLE_HIDDEN",
            )


if __name__ == "__main__":
    unittest.main()
