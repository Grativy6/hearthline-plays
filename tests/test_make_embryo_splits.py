from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import make_embryo_splits as subject  # noqa: E402


class MakeEmbryoSplitsTests(unittest.TestCase):
    def test_derives_prefix_from_canonical_basename(self) -> None:
        self.assertEqual(subject.embryo_id(r"C:\data\fish17_fov03.zarr"), "fish17")
        self.assertEqual(subject.canonical_sample("/data/fish17_fov03.zarr"), "fish17_fov03")

    def test_output_is_deterministic_and_organizer_compatible(self) -> None:
        names = ["embryoB_fov01.zarr", "embryoA_fov02.zarr", "embryoA_fov01.zarr"]
        forward = subject.build_splits(names)
        reverse = subject.build_splits(reversed(names))

        self.assertEqual(forward, reverse)
        self.assertEqual(len(forward), 2)
        self.assertEqual(
            forward[0],
            {
                "split": 0,
                "held_out_embryo": "embryoA",
                "train": ["embryoB_fov01"],
                "test": ["embryoA_fov01", "embryoA_fov02"],
            },
        )
        self.assertTrue(set(forward[0]["train"]).isdisjoint(forward[0]["test"]))

    def test_refuses_fewer_than_two_embryos(self) -> None:
        with self.assertRaisesRegex(subject.SplitError, "at least 2 embryos"):
            subject.build_splits(["embryoA_fov01", "embryoA_fov02"])

    def test_refuses_malformed_sample_names(self) -> None:
        for name in ("noseparator", "_fov01", "embryoA_", "plainname.zarr", ""):
            with self.subTest(name=name), self.assertRaises(subject.SplitError):
                subject.build_splits([name, "embryoB_fov01"])

    def test_refuses_duplicates_after_path_and_suffix_canonicalization(self) -> None:
        with self.assertRaisesRegex(subject.SplitError, "duplicate canonical"):
            subject.build_splits(
                [r"C:\one\embryoA_fov01.zarr", "/two/embryoA_fov01", "embryoB_fov01"]
            )

    def test_loads_text_fixture_without_touching_named_samples(self) -> None:
        path = ROOT / "fixtures" / "sample-names.txt"
        samples = subject.load_samples_file(path)
        self.assertEqual(len(samples), 3)
        self.assertEqual(len(subject.build_splits(samples)), 2)

    def test_loads_json_manifest_and_rejects_wrong_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            good = Path(directory) / "good.json"
            bad = Path(directory) / "bad.json"
            good.write_text(json.dumps({"samples": ["a_1", "b_1"]}), encoding="utf-8")
            bad.write_text(json.dumps({"samples": [1]}), encoding="utf-8")
            self.assertEqual(subject.load_samples_file(good), ["a_1", "b_1"])
            with self.assertRaises(subject.SplitError):
                subject.load_samples_file(bad)

    def test_cli_writes_only_requested_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "folds.json"
            code = subject.main(["a_one.zarr", "b_one.zarr", "--output", str(output)])
            self.assertEqual(code, 0)
            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document[0]["train"], ["b_one"])
            self.assertFalse((Path(directory) / "a_one.zarr").exists())


if __name__ == "__main__":
    unittest.main()
