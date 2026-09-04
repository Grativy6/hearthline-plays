from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools import fetch_pinned_code as fetcher


def source_lock() -> dict[str, object]:
    return {
        "sources": {
            "rosettabench": {
                "repository": "https://github.com/namanbnsl/RosettaBench.git",
                "commit": fetcher.CODE_PINS["rosettabench"]["commit"],
                "fetch_class": "public_code",
            },
            "kaggle_benchmarks": {
                "repository": "https://github.com/Kaggle/kaggle-benchmarks.git",
                "commit": fetcher.CODE_PINS["kaggle_benchmarks"]["commit"],
                "fetch_class": "public_code",
            },
            "rosetta_dataset_hf": {
                "repository": "https://huggingface.co/datasets/example/data",
                "fetch_class": "metadata_only_non_fetchable",
            },
            "rosetta_dataset_kaggle": {
                "repository": "https://www.kaggle.com/datasets/example/data",
                "fetch_class": "metadata_only_non_fetchable",
            },
        }
    }


class FetchPinnedCodeTests(unittest.TestCase):
    def write_lock(self, directory: Path, document: object | None = None) -> Path:
        path = directory / "source-lock.v1.json"
        path.write_text(json.dumps(document if document is not None else source_lock()), encoding="utf-8")
        return path

    def test_loads_only_two_code_pins_and_ignores_data_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pins = fetcher.load_code_pins(self.write_lock(Path(temporary)))
        self.assertEqual(set(pins), {"rosettabench", "kaggle_benchmarks"})

    def test_refuses_unapproved_public_code_entry(self) -> None:
        document = source_lock()
        document["sources"]["surprise"] = {
            "repository": "https://github.com/example/surprise",
            "commit": "0" * 40,
            "fetch_class": "public_code",
        }
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(fetcher.FetchError, "unapproved"):
                fetcher.load_code_pins(self.write_lock(Path(temporary), document))

    def test_refuses_changed_commit_and_credential_url(self) -> None:
        for replacement, expected in (
            ({"commit": "0" * 40}, "commit"),
            (
                {
                    "repository": "https://person:"
                    + "password@github.com/namanbnsl/RosettaBench"
                },
                "credential",
            ),
        ):
            with self.subTest(replacement=replacement):
                document = source_lock()
                document["sources"]["rosettabench"].update(replacement)
                with tempfile.TemporaryDirectory() as temporary:
                    with self.assertRaisesRegex(fetcher.FetchError, expected):
                        fetcher.load_code_pins(self.write_lock(Path(temporary), document))

    def test_check_only_missing_cache_is_network_and_write_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "repo"
            repo.mkdir()
            lock = self.write_lock(repo)
            cache = base / "external-cache"

            def forbidden_runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError("Git must not run for missing-cache check-only")

            report = fetcher.process_sources(
                lock, cache, fetch=False, runner=forbidden_runner, repo_root=repo
            )
            self.assertFalse(cache.exists())
            self.assertEqual(report["mode"], "CHECK_ONLY_OFFLINE")
            self.assertFalse(report["network_authorized"])
            self.assertEqual(report["network_git_commands_attempted"], 0)
            self.assertEqual(report["network_socket_operations"], 0)
            self.assertEqual(
                {item["status"] for item in report["sources"].values()}, {"MISSING"}
            )

    def test_inspection_uses_exact_safe_directory_and_no_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "RosettaBench"
            (checkout / ".git").mkdir(parents=True)
            outputs = iter(
                [
                    "",
                    "https://github.com/namanbnsl/RosettaBench.git\n",
                    fetcher.CODE_PINS["rosettabench"]["commit"] + "\n",
                ]
            )
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                return subprocess.CompletedProcess(command, 0, next(outputs), "")

            report = fetcher.inspect_checkout(
                checkout, fetcher.CODE_PINS["rosettabench"], runner=runner
            )
            self.assertEqual(report["status"], "PINNED_CLEAN")
            self.assertEqual(len(commands), 3)
            for command in commands:
                self.assertIn(f"safe.directory={checkout.resolve()}", command)
                self.assertIn("credential.helper=", command)
                self.assertIn("core.fsmonitor=false", command)
                self.assertIn("core.untrackedCache=false", command)

    def test_explicit_fetch_mode_with_pinned_cache_reports_no_network_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "repo"
            cache = base / "external-cache"
            repo.mkdir()
            lock = self.write_lock(repo)
            for pin in fetcher.CODE_PINS.values():
                (cache / pin["directory"] / ".git").mkdir(parents=True)

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                checkout = Path(command[command.index("-C") + 1])
                pin = next(
                    value
                    for value in fetcher.CODE_PINS.values()
                    if value["directory"] == checkout.name
                )
                if "status" in command:
                    output = ""
                elif "get-url" in command:
                    output = pin["repository"] + ".git\n"
                else:
                    output = pin["commit"] + "\n"
                return subprocess.CompletedProcess(command, 0, output, "")

            report = fetcher.process_sources(
                lock, cache, fetch=True, runner=runner, repo_root=repo
            )
            self.assertTrue(report["network_authorized"])
            self.assertEqual(report["network_git_commands_attempted"], 0)

    def test_check_only_git_environment_disables_optional_locks(self) -> None:
        environment = fetcher._git_environment()
        self.assertEqual(environment["GIT_OPTIONAL_LOCKS"], "0")

    def test_dirty_or_mismatched_checkout_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "RosettaBench"
            (checkout / ".git").mkdir(parents=True)

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(command, 0, " M modified.py\n", "")

            with self.assertRaisesRegex(fetcher.FetchError, "dirty"):
                fetcher.inspect_checkout(
                    checkout, fetcher.CODE_PINS["rosettabench"], runner=runner
                )

    def test_fetch_cache_must_be_explicit_and_outside_repo(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            fetcher.build_parser().parse_args([])
        parsed = fetcher.build_parser().parse_args(["--fetch-code"])
        self.assertIsNone(parsed.cache)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(fetcher.main(["--fetch-code"]), 1)
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            with self.assertRaisesRegex(fetcher.FetchError, "outside"):
                fetcher.validate_cache_path(repo / ".cache" / "code", repo_root=repo)

    def test_modes_are_mutually_exclusive(self) -> None:
        parser = fetcher.build_parser()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["--check-only", "--fetch-code"])


if __name__ == "__main__":
    unittest.main()
