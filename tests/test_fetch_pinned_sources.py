from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import fetch_pinned_sources as subject  # noqa: E402


def completed(args: object, code: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, code, stdout, stderr)


class FakeGit:
    def __init__(self, *, commit: str, repository: str, dirty: bool = False) -> None:
        self.commit = commit
        self.repository = repository
        self.dirty = dirty
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, arguments: object, *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        args = list(arguments)  # type: ignore[arg-type]
        self.calls.append((args, cwd))
        command = args[0]
        if command == "check-ignore":
            return completed(args)
        if command == "clone":
            destination = Path(args[-1])
            (destination / ".git").mkdir(parents=True)
            return completed(args)
        if command in {"fetch", "checkout", "cat-file"}:
            return completed(args)
        if command == "status":
            return completed(args, stdout="?? stray.txt\n" if self.dirty else "")
        if command == "remote":
            return completed(args, stdout=self.repository + "\n")
        if command == "rev-parse":
            return completed(args, stdout=self.commit + "\n")
        raise AssertionError(f"unexpected fake git command: {args}")


class FetchPinnedSourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock_path = ROOT / "source-lock.v1.json"
        cls.sources = subject.load_source_lock(cls.lock_path)

    def test_loads_exact_two_public_pins(self) -> None:
        self.assertEqual(set(self.sources), set(subject.SOURCE_NAMES))
        for source in self.sources.values():
            self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
            self.assertTrue(source["repository"].startswith("https://github.com/"))

    def test_rejects_credentials_non_https_and_bad_commit(self) -> None:
        base = json.loads(self.lock_path.read_text(encoding="utf-8"))
        bad_values = (
            "https://user:secret@github.com/royerlab/tracksdata.git",
            "ssh://git@github.com/royerlab/tracksdata.git",
            "https://example.com/royerlab/tracksdata.git",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            for value in bad_values:
                with self.subTest(value=value):
                    document = json.loads(json.dumps(base))
                    document["sources"]["tracksdata"]["repository"] = value
                    path.write_text(json.dumps(document), encoding="utf-8")
                    with self.assertRaises(subject.SourceError):
                        subject.load_source_lock(path)
            base["sources"]["tracksdata"]["commit"] = "ABC"
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaises(subject.SourceError):
                subject.load_source_lock(path)

    def test_check_only_missing_cache_performs_no_network_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            cache = repo / ".cache" / "pinned-sources"
            fake = FakeGit(commit="0" * 40, repository="https://github.com/example/example.git")
            report = subject.process_sources(
                lock_path=self.lock_path,
                cache=cache,
                repo_root=repo,
                fetch=False,
                runner=fake,
            )
            self.assertEqual(report["mode"], "CHECK_ONLY_OFFLINE")
            self.assertFalse(cache.exists())
            self.assertEqual([call[0][0] for call in fake.calls], ["check-ignore"])
            for value in report["checkouts"].values():
                self.assertEqual(value["status"], "MISSING")

    def test_cache_must_be_dedicated_ignored_repo_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            fake = FakeGit(commit="0" * 40, repository="https://github.com/example/example.git")
            with self.assertRaisesRegex(subject.SourceError, "inside the repository"):
                subject.process_sources(
                    lock_path=self.lock_path,
                    cache=Path(directory) / "outside",
                    repo_root=repo,
                    fetch=False,
                    runner=fake,
                )

            unignored = lambda arguments, cwd=None: completed(arguments, code=1)
            with self.assertRaisesRegex(subject.SourceError, "not ignored"):
                subject.process_sources(
                    lock_path=self.lock_path,
                    cache=repo / "cache",
                    repo_root=repo,
                    fetch=False,
                    runner=unignored,
                )

            cache = repo / ".cache" / "pinned-sources"
            cache.mkdir(parents=True)
            (cache / "surprise.txt").write_text("fixture", encoding="utf-8")
            with self.assertRaisesRegex(subject.SourceError, "unexpected entries"):
                subject.process_sources(
                    lock_path=self.lock_path,
                    cache=cache,
                    repo_root=repo,
                    fetch=False,
                    runner=fake,
                )

    def test_existing_checkout_must_be_clean_at_exact_head_and_origin(self) -> None:
        source = self.sources["tracksdata"]
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "tracksdata"
            (destination / ".git").mkdir(parents=True)
            good = FakeGit(commit=source["commit"], repository=source["repository"])
            report = subject.inspect_checkout(destination, source, runner=good)
            self.assertEqual(report["status"], "PINNED_CLEAN")

            dirty = FakeGit(commit=source["commit"], repository=source["repository"], dirty=True)
            with self.assertRaisesRegex(subject.SourceError, "dirty"):
                subject.inspect_checkout(destination, source, runner=dirty)

            wrong_head = FakeGit(commit="0" * 40, repository=source["repository"])
            with self.assertRaisesRegex(subject.SourceError, "does not match locked"):
                subject.inspect_checkout(destination, source, runner=wrong_head)

            wrong_origin = FakeGit(
                commit=source["commit"], repository="https://github.com/other/repository.git"
            )
            with self.assertRaisesRegex(subject.SourceError, "origin does not match"):
                subject.inspect_checkout(destination, source, runner=wrong_origin)

    def test_explicit_fetch_uses_clone_fetch_checkout_then_verifies(self) -> None:
        source = self.sources["organizer_baseline"]
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            destination = cache / "organizer_baseline"
            fake = FakeGit(commit=source["commit"], repository=source["repository"])
            report = subject.fetch_missing_checkout(destination, source, runner=fake)
            commands = [call[0][0] for call in fake.calls]
            self.assertEqual(commands[:3], ["clone", "fetch", "checkout"])
            self.assertEqual(report["status"], "PINNED_CLEAN")

    def test_cli_requires_explicit_mode_and_disallows_both(self) -> None:
        parser = subject.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])
        with self.assertRaises(SystemExit):
            parser.parse_args(["--check-only", "--fetch"])

    def test_git_environment_disables_interactive_credentials(self) -> None:
        env = subject._git_environment()
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["GCM_INTERACTIVE"], "Never")
        self.assertEqual(env["GIT_ASKPASS"], "")


if __name__ == "__main__":
    unittest.main()
