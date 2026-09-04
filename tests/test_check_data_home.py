from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import check_data_home as subject  # noqa: E402


class CheckDataHomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()

    @staticmethod
    def volume(
        *, filesystem: str = "NTFS", drive_type: str = "fixed", free_gib: int = 500
    ) -> subject.VolumeInfo:
        return subject.VolumeInfo(
            mount="X:\\",
            filesystem=filesystem,
            drive_type=drive_type,
            free_bytes=free_gib * subject.GIB,
        )

    def assess(self, proposed: Path, volume: subject.VolumeInfo, **kwargs: object) -> dict[str, object]:
        return subject.assess_data_home(
            proposed,
            repo_root=self.repo,
            forbidden_roots=[],
            forbid_repo_volume=False,
            volume_probe=lambda _path: volume,
            **kwargs,
        )

    def test_accepts_nonexistent_path_on_suitable_fixed_volume_without_creating_it(self) -> None:
        proposed = self.base / "future" / "biohub"
        observed: list[Path] = []

        report = subject.assess_data_home(
            proposed,
            repo_root=self.repo,
            forbidden_roots=[],
            forbid_repo_volume=False,
            volume_probe=lambda path: observed.append(path) or self.volume(),
        )

        self.assertTrue(report["accepted"])
        self.assertFalse(proposed.exists())
        self.assertEqual(observed, [self.base])
        self.assertTrue(report["read_only"])

    def test_rejects_path_inside_repository_and_repository_ancestor(self) -> None:
        inside = self.assess(self.repo / "data", self.volume())
        ancestor = self.assess(self.base, self.volume())
        self.assertFalse(inside["accepted"])
        self.assertFalse(ancestor["accepted"])
        self.assertTrue(any("separate" in error for error in inside["errors"]))
        self.assertTrue(any("separate" in error for error in ancestor["errors"]))

    def test_rejects_fat_and_fat32_unconditionally(self) -> None:
        for filesystem in ("FAT", "fat32"):
            with self.subTest(filesystem=filesystem):
                report = self.assess(
                    self.base / f"target-{filesystem}",
                    self.volume(filesystem=filesystem, drive_type="removable"),
                    acknowledge_removable=True,
                )
                self.assertFalse(report["accepted"])
                self.assertTrue(any("not suitable" in error for error in report["errors"]))

    def test_removable_requires_explicit_acknowledgment_then_passes(self) -> None:
        proposed = self.base / "external" / "biohub"
        volume = self.volume(filesystem="EXFAT", drive_type="removable")
        denied = self.assess(proposed, volume)
        allowed = self.assess(proposed, volume, acknowledge_removable=True)
        self.assertFalse(denied["accepted"])
        self.assertTrue(allowed["accepted"])

    def test_forbidden_root_blocks_sibling_data_home(self) -> None:
        forbidden = self.base / "current-usb"
        forbidden.mkdir()
        proposed = forbidden / "Biohub"
        report = subject.assess_data_home(
            proposed,
            repo_root=self.repo,
            forbidden_roots=[forbidden],
            forbid_repo_volume=False,
            volume_probe=lambda _path: self.volume(filesystem="EXFAT"),
        )
        self.assertFalse(report["accepted"])
        self.assertTrue(any("forbidden root" in error for error in report["errors"]))

    def test_rejects_low_space_and_unapproved_drive_type(self) -> None:
        report = self.assess(
            self.base / "target",
            self.volume(drive_type="remote", free_gib=10),
            min_free_gib=200,
        )
        self.assertFalse(report["accepted"])
        self.assertEqual(len(report["errors"]), 2)

    def test_rejects_existing_regular_file(self) -> None:
        proposed = self.base / "not-a-directory"
        proposed.write_text("fixture", encoding="utf-8")
        report = self.assess(proposed, self.volume())
        self.assertFalse(report["accepted"])
        self.assertTrue(any("not a directory" in error for error in report["errors"]))

    def test_minimum_must_be_positive_and_finite(self) -> None:
        for value in (0, -1, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(subject.DataHomeError):
                self.assess(self.base / "target", self.volume(), min_free_gib=value)

    def test_cli_supports_both_removable_flag_spellings(self) -> None:
        for flag in ("--allow-removable", "--acknowledge-removable"):
            args = subject.build_parser().parse_args([str(self.base / "target"), flag])
            self.assertTrue(args.acknowledge_removable)


if __name__ == "__main__":
    unittest.main()
