from __future__ import annotations

import ast
import importlib.util
import stat
import sys
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("arc3_repository_guard_test", ROOT / "tools/repository_guard.py")
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GUARD
SPEC.loader.exec_module(GUARD)


class RepositoryGuardTests(unittest.TestCase):
    def assert_python_rejected(self, source: str, pattern: str = "effect") -> None:
        fixture = ROOT / "tests/.effect-adapter-fixture.py"
        fixture.write_text(source, encoding="utf-8")
        try:
            with self.assertRaisesRegex(GUARD.GuardError, pattern):
                GUARD.guard([str(fixture.relative_to(ROOT))])
        finally:
            fixture.unlink(missing_ok=True)

    def test_forced_tracked_ignored_outputs_are_rejected(self) -> None:
        for path in (
            "build/submission.ipynb",
            ".hearthline/receipts/grant.json",
            "recordings/private.json",
            "notebooks/kernel-metadata.json",
            "tools/arc3_replay_probe.py",
        ):
            with self.subTest(path=path), self.assertRaisesRegex(GUARD.GuardError, "forbidden tracked paths"):
                GUARD.guard([path])

    def test_sensitive_output_directories_are_rejected_at_any_depth(self) -> None:
        for path in (
            "archive/recordings/private.json",
            "backup/.hearthline/grants/stage.json",
            "nested/results/candidate.json",
        ):
            with self.subTest(path=path), self.assertRaisesRegex(
                GUARD.GuardError, "forbidden tracked paths"
            ):
                GUARD.guard([path])

    def test_forbidden_paths_are_casefolded_and_legacy_kaggle_key_is_secret(self) -> None:
        fixture_root = ROOT / "tests/.guard-root-fixture"
        fixture_root.mkdir(exist_ok=False)
        try:
            with (
                patch.object(GUARD, "ROOT", fixture_root),
                self.assertRaisesRegex(GUARD.GuardError, "forbidden tracked paths"),
            ):
                GUARD.guard([".KAGGLE/kaggle.json"])

            credential = fixture_root / "backup.json"
            credential.write_text(
                '{"archive":{"username":"example",'
                '"key":"0123456789abcdef0123456789abcdef"}}',
                encoding="utf-8",
            )
            with (
                patch.object(GUARD, "ROOT", fixture_root),
                self.assertRaisesRegex(GUARD.GuardError, "legacy Kaggle API key"),
            ):
                GUARD.guard(["backup.json"])
        finally:
            credential = fixture_root / "backup.json"
            credential.unlink(missing_ok=True)
            fixture_root.rmdir()

    def test_effect_capable_configuration_locations_are_rejected(self) -> None:
        for path in (
            ".github/actions/local/action.yml",
            ".github/copilot-instructions.md",
            ".github/instructions/security.instructions.md",
            ".vscode/tasks.json",
            ".devcontainer/devcontainer.json",
            ".devcontainer.json",
            ".mcp.json",
            ".claude/settings.json",
            "nested/.claude/settings.json",
            ".cursor/mcp.json",
            "nested/.cursor/rules/safety.mdc",
            ".gemini/settings.json",
            "nested/.gemini/settings.json",
            "AGENTS.md",
            "docs/AGENTS.md",
            "CLAUDE.md",
            "GEMINI.md",
            "package.json",
            "renovate.json",
        ):
            with self.subTest(path=path), self.assertRaisesRegex(
                GUARD.GuardError, "forbidden tracked paths"
            ):
                GUARD.guard([path])

    def test_casefold_ambiguous_paths_are_rejected_before_read(self) -> None:
        with self.assertRaisesRegex(GUARD.GuardError, "casefold-ambiguous"):
            GUARD.guard(["fixtures/Config.json", "fixtures/config.json"])

    def test_json_unicode_escaping_cannot_hide_modern_token(self) -> None:
        fixture = ROOT / "tests/.escaped-secret.json"
        fixture.write_text(
            '{"token":"K\\u0047AT_abcdefghijklmnopqrstuvwxyz"}',
            encoding="utf-8",
        )
        try:
            with self.assertRaisesRegex(GUARD.GuardError, "decoded Kaggle access token"):
                GUARD.guard([str(fixture.relative_to(ROOT))])
        finally:
            fixture.unlink(missing_ok=True)

    def test_json_unicode_escaping_cannot_hide_sensitive_path(self) -> None:
        fixture = ROOT / "tests/.escaped-path.json"
        fixture.write_text(
            '{"credential_path":".\\u006bAGGLE/kaggle.json"}',
            encoding="utf-8",
        )
        try:
            with self.assertRaisesRegex(GUARD.GuardError, "decoded sensitive path"):
                GUARD.guard([str(fixture.relative_to(ROOT))])
        finally:
            fixture.unlink(missing_ok=True)

    def test_encrypted_and_pgp_private_key_headers_are_rejected(self) -> None:
        fixture = ROOT / "tests/.private-key-fixture.md"
        try:
            for marker in (
                "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----",
                "-----BEGIN " + "DSA PRIVATE KEY-----",
                "-----BEGIN " + "PGP PRIVATE KEY BLOCK-----",
            ):
                fixture.write_text(marker, encoding="utf-8")
                with self.subTest(marker=marker), self.assertRaisesRegex(
                    GUARD.GuardError, "private key block"
                ):
                    GUARD.guard([str(fixture.relative_to(ROOT))])
        finally:
            fixture.unlink(missing_ok=True)

    def test_token_shaped_tracked_filename_is_rejected_without_echo(self) -> None:
        secret_name = "K" + "GAT_" + ("a" * 24) + ".md"
        fixture = ROOT / "tests" / secret_name
        fixture.write_bytes(b"")
        try:
            with self.assertRaisesRegex(
                GUARD.GuardError, "secret in tracked path name: Kaggle access token"
            ) as raised:
                GUARD.guard([str(fixture.relative_to(ROOT))])
            self.assertNotIn(secret_name, str(raised.exception))
        finally:
            fixture.unlink(missing_ok=True)

    def test_executed_control_json_is_exactly_allowlisted(self) -> None:
        path_text = "notebooks/kernel-metadata.template.json"
        original = (ROOT / path_text).read_bytes()
        fixture_root = ROOT / "tests/.guard-root-fixture"
        fixture = fixture_root / path_text
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(original + b" ")
        try:
            with (
                patch.object(GUARD, "ROOT", fixture_root),
                self.assertRaisesRegex(GUARD.GuardError, "control JSON staged blob"),
            ):
                GUARD.guard([path_text])
        finally:
            fixture.unlink(missing_ok=True)
            fixture.parent.rmdir()
            fixture_root.rmdir()

    def test_non_source_auxiliary_blobs_are_exactly_allowlisted(self) -> None:
        path_text = "tests/fixtures/ARC-AGI-3-Agents-LICENSE.txt"
        fixture_root = ROOT / "tests/.guard-root-fixture"
        fixture = fixture_root / path_text
        fixture.parent.mkdir(parents=True)
        fixture.write_text("changed fixture\n", encoding="utf-8")
        try:
            with (
                patch.object(GUARD, "ROOT", fixture_root),
                self.assertRaisesRegex(GUARD.GuardError, "auxiliary staged blob"),
            ):
                GUARD.guard([path_text])
        finally:
            fixture.unlink(missing_ok=True)
            fixture.parent.rmdir()
            (fixture_root / "tests").rmdir()
            fixture_root.rmdir()

    def test_gitignore_cleanliness_control_is_exactly_allowlisted(self) -> None:
        path_text = ".gitignore"
        fixture_root = ROOT / "tests/.guard-root-fixture"
        fixture_root.mkdir()
        (fixture_root / path_text).write_text("*\n", encoding="utf-8")
        try:
            with (
                patch.object(GUARD, "ROOT", fixture_root),
                self.assertRaisesRegex(GUARD.GuardError, "auxiliary staged blob"),
            ):
                GUARD.guard([path_text])
        finally:
            (fixture_root / path_text).unlink(missing_ok=True)
            fixture_root.rmdir()

    def test_guard_git_reads_clear_ambient_effect_configuration(self) -> None:
        ambient = {
            "PATH": "/usr/bin",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.fsmonitor",
            "GIT_CONFIG_VALUE_0": "/tmp/evil",
            "GIT_SSH_COMMAND": "curl https://example.invalid",
        }
        with (
            patch.object(GUARD.os, "environ", ambient),
            patch.object(GUARD.subprocess, "check_output", return_value=b"") as check,
        ):
            self.assertEqual(GUARD.tracked_entries(), {})
        command = check.call_args.args[0]
        environment = check.call_args.kwargs["env"]
        self.assertEqual(
            command,
            [
                "git", "-c", "core.fsmonitor=false",
                "-c", f"core.hooksPath={GUARD.os.devnull}",
                "ls-files", "--stage", "-z",
            ],
        )
        self.assertFalse(any(key.startswith("GIT_") for key in ambient if key in environment))
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(environment["GIT_CONFIG_GLOBAL"], GUARD.os.devnull)
        self.assertEqual(environment["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertEqual(environment["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")

    def test_index_blob_reader_rejects_replacement_bytes(self) -> None:
        with (
            patch.object(GUARD.subprocess, "check_output", return_value=b"replacement"),
            self.assertRaisesRegex(GUARD.GuardError, "do not match the exact staged blob"),
        ):
            GUARD.read_index_blob("0" * 40)

    def test_materialized_guard_accepts_explicit_repository_root(self) -> None:
        temporary_code_location = ROOT / "tests/.materialized-guard"
        isolated_flags = type("Flags", (), {"isolated": 1})()
        with (
            patch.object(GUARD, "ROOT", temporary_code_location),
            patch.object(GUARD.sys, "flags", isolated_flags),
            patch.object(
                GUARD,
                "guard",
                return_value={"tracked": 1, "json": 0, "python": 1, "workflows": 0},
            ) as guarded,
        ):
            self.assertEqual(GUARD.main(["--root", str(ROOT)]), 0)
            self.assertEqual(GUARD.ROOT, ROOT.resolve())
            guarded.assert_called_once_with()

    def test_materialized_guard_rejects_relative_repository_root(self) -> None:
        with self.assertRaisesRegex(GUARD.GuardError, "absolute path"):
            GUARD._root_from_arguments(["--root", "."])

    def test_effect_capable_python_adapter_is_rejected(self) -> None:
        self.assert_python_rejected("import arc_agi\n", "effect-capable import")

    def test_non_utf8_python_cookie_polyglot_is_rejected(self) -> None:
        source = (
            b"# coding: utf-7\n"
            b'# +AAo-os.system("kaggle kernels push -p .")\n'
            b'print("apparently safe")\n'
        )
        with self.assertRaisesRegex(GUARD.GuardError, "must use UTF-8"):
            GUARD._guard_python("tests/.effect-adapter-fixture.py", source)

    def test_subprocess_launch_bypasses_are_rejected(self) -> None:
        cases = {
            "run Kaggle": 'import subprocess\nsubprocess.run(["kaggle", "kernels", "push"])\n',
            "Popen curl": 'import subprocess\nsubprocess.Popen(["curl", "https://example.invalid"])\n',
            "check_call wget": 'import subprocess\nsubprocess.check_call(["wget", "https://example.invalid"])\n',
            "check_output Kaggle": 'import subprocess\nsubprocess.check_output(["kaggle", "competitions", "submit"])\n',
            "aliased subprocess": 'import subprocess as sp\nsp.run(["kaggle", "kernels", "push"])\n',
            "from subprocess": 'from subprocess import run\nrun(["curl", "https://example.invalid"])\n',
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                self.assert_python_rejected(source)

    def test_os_process_launch_bypasses_are_rejected(self) -> None:
        cases = {
            "system": 'import os\nos.system("kaggle kernels push -p .")\n',
            "popen": 'import os\nos.popen("curl https://example.invalid")\n',
            "spawn": 'import os\nos.spawnlp(os.P_WAIT, "kaggle", "kaggle", "kernels", "push")\n',
            "alias": 'import os as operating_system\noperating_system.system("curl example.invalid")\n',
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                self.assert_python_rejected(source, "OS process launcher")

    def test_dynamic_import_bypasses_are_rejected(self) -> None:
        cases = {
            "dunder import": '__import__("requests").post("https://example.invalid")\n',
            "importlib": 'import importlib\nimportlib.import_module("kaggle")\n',
            "aliased importlib": 'import importlib as loader\nloader.import_module("requests")\n',
            "from importlib": 'from importlib import import_module\nimport_module("arc_agi")\n',
            "importlib dunder": 'import importlib\nimportlib.__import__("requests")\n',
            "getattr importlib": (
                'import importlib\ngetattr(importlib, "import_module")("kaggle")\n'
            ),
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                self.assert_python_rejected(source, "dynamic import")

    def test_nearby_dynamic_exec_shape_is_not_allowlisted(self) -> None:
        source = (
            "def test_unfrozen_runtime_closure_blocks_competition_rerun_before_effects():\n"
            "    exec(compile(run_source, 'different-origin', 'exec'), {})\n"
        )
        tree = ast.parse(source)
        visitor = GUARD._PythonEffectGuard("tests/test_candidate.py", tree)
        with self.assertRaisesRegex(GUARD.GuardError, "unapproved dynamic exec"):
            visitor.visit(tree)

        gate_source = (
            "def verify_current_candidate():\n"
            "    exec(compile(verifier_bytes, str(path), 'exec'), {})\n"
        )
        gate_tree = ast.parse(gate_source)
        gate_visitor = GUARD._PythonEffectGuard(
            "scripts/verify_human_gate.py", gate_tree
        )
        with self.assertRaisesRegex(GUARD.GuardError, "unapproved dynamic exec"):
            gate_visitor.visit(gate_tree)

    def test_runtime_exec_test_functions_are_exact_ast_sealed(self) -> None:
        source = (ROOT / "tests/test_candidate.py").read_text(encoding="utf-8")
        GUARD._validate_runtime_exec_tests(ast.parse(source))
        target_name = "test_unfrozen_runtime_closure_blocks_competition_rerun_before_effects"
        exact_call = 'exec(compile(run_source, "competition-rerun", "exec"), {})'
        for mutation in ("decorator", "default", "lambda", "compile shadow"):
            tree = ast.parse(source)
            target = next(
                node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == target_name
            )
            if mutation == "decorator":
                target.decorator_list.append(ast.parse(exact_call, mode="eval").body)
            elif mutation == "default":
                target.args.defaults.append(ast.parse(exact_call, mode="eval").body)
            elif mutation == "lambda":
                target.body.insert(0, ast.parse(f"deferred = lambda: {exact_call}").body[0])
            else:
                target.body.insert(0, ast.parse("compile = attacker").body[0])
            expected_error = (
                "runtime exec builtin binding"
                if mutation == "compile shadow"
                else "runtime exec test AST seal"
            )
            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                GUARD.GuardError, expected_error
            ):
                GUARD._validate_runtime_exec_tests(tree)

        tree = ast.parse(source)
        tree.body.insert(0, ast.parse("compile = attacker").body[0])
        with self.assertRaisesRegex(GUARD.GuardError, "runtime exec builtin binding"):
            GUARD._validate_runtime_exec_tests(tree)

    def test_gateway_opener_name_is_special_only_inside_notebook_runtime(self) -> None:
        source = (
            "def configure_mock():\n"
            "    gateway_opener = mock.MagicMock()\n"
            "    gateway_opener.open.return_value = response\n"
        )
        tree = ast.parse(source)
        visitor = GUARD._PythonEffectGuard("tests/test_repository_guard.py", tree)
        visitor.visit(tree)
        visitor.finish()

        runtime_tree = ast.parse("callback = gateway_opener.open\n")
        runtime_visitor = GUARD._PythonEffectGuard(
            GUARD.NOTEBOOK_RUNTIME_CONTEXT,
            runtime_tree,
            notebook_runtime=True,
        )
        with self.assertRaisesRegex(GUARD.GuardError, "detached effect callable"):
            runtime_visitor.visit(runtime_tree)

    def test_independent_audit_effect_bypasses_are_rejected(self) -> None:
        cases = {
            "pty spawn": 'import pty\npty.spawn(["kaggle", "kernels", "push"])\n',
            "ctypes system": 'import ctypes\nctypes.CDLL(None).system(b"curl example.invalid")\n',
            "urllib3 request": (
                'import urllib3\nurllib3.PoolManager().request("GET", "https://example.invalid")\n'
            ),
            "builtins dictionary import": (
                '__builtins__["__import__"]("requests").get("https://example.invalid")\n'
            ),
            "os dunder system": (
                'import os\nos.__getattribute__("system")("kaggle kernels push -p .")\n'
            ),
            "local capability re-export": (
                'import scripts.build_notebook as b\n'
                'b.subprocess.run(["kaggle", "kernels", "push"])\n'
            ),
            "imported Git wrapper": (
                'from pathlib import Path\nfrom tools.verify_station import _git\n'
                '_git(Path("."), "push", "origin", "HEAD")\n'
            ),
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                fixture = ROOT / "tests/.effect-adapter-fixture.py"
                fixture.write_text(source, encoding="utf-8")
                try:
                    with self.assertRaises(GUARD.GuardError):
                        GUARD.guard([str(fixture.relative_to(ROOT))])
                finally:
                    fixture.unlink(missing_ok=True)

    def test_second_audit_indirect_effect_bypasses_are_rejected(self) -> None:
        cases = {
            "fork": 'import os\nos.fork()\n',
            "multiprocessing": (
                'import multiprocessing\n'
                'multiprocessing.Process(target=print).start()\n'
            ),
            "operator attrgetter": (
                'import os, operator\n'
                'operator.attrgetter("system")(os)("git push origin HEAD")\n'
            ),
            "xmlrpc": (
                'import xmlrpc.client\n'
                'xmlrpc.client.ServerProxy("https://example.invalid").ping()\n'
            ),
            "httpx": 'import httpx\nhttpx.get("https://example.invalid")\n',
            "runpy": 'import runpy\nrunpy.run_path("/tmp/evil.py")\n',
            "pickle": 'import pickle\npickle.loads(payload)\n',
            "pathlib os re-export": (
                'import pathlib\nosp = getattr(pathlib, "os")\n'
                'run = getattr(osp, "system")\nrun("git push origin HEAD")\n'
            ),
            "importlib arbitrary loader": (
                'import importlib.util\n'
                'spec = importlib.util.spec_from_file_location("evil", "/tmp/evil.py")\n'
                'module = importlib.util.module_from_spec(spec)\n'
                'spec.loader.exec_module(module)\n'
            ),
            "async network": (
                'import asyncio\n'
                'asyncio.run(asyncio.open_connection("example.invalid", 443))\n'
            ),
            "filesystem unlink": (
                'from pathlib import Path\nPath("/tmp/target").unlink()\n'
            ),
            "filesystem recursive delete": (
                'import shutil\nshutil.rmtree("/tmp/target")\n'
            ),
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                fixture = ROOT / "tests/.effect-adapter-fixture.py"
                fixture.write_text(source, encoding="utf-8")
                try:
                    with self.assertRaises(GUARD.GuardError):
                        GUARD.guard([str(fixture.relative_to(ROOT))])
                finally:
                    fixture.unlink(missing_ok=True)

    def test_changed_existing_python_blob_fails_even_with_same_imports(self) -> None:
        path_text = "tools/pair_static.py"
        original = (ROOT / path_text).read_bytes()
        mutated = original + b'\nPath("/tmp/audit-target").unlink()\n'
        with self.assertRaisesRegex(GUARD.GuardError, "staged blob is not exact-allowlisted"):
            GUARD._guard_python(path_text, mutated)

    def test_guard_self_ast_rejects_safe_import_effect_insertion(self) -> None:
        path_text = "tools/repository_guard.py"
        original = (ROOT / path_text).read_bytes()
        mutated = original + b'\nPath("/tmp/audit-target").unlink()\n'
        with self.assertRaisesRegex(GUARD.GuardError, "self-AST seal mismatch"):
            GUARD._guard_python(path_text, mutated)

    def test_guard_self_ast_rejects_executable_seal_rhs(self) -> None:
        path_text = "tools/repository_guard.py"
        original = (ROOT / path_text).read_bytes()
        old = f'SELF_AST_SHA256 = "{GUARD.SELF_AST_SHA256}"'.encode("ascii")
        replacement = (
            b'SELF_AST_SHA256 = (os.system("true"), "'
            + GUARD.SELF_AST_SHA256.encode("ascii")
            + b'")[1]'
        )
        mutated = original.replace(old, replacement, 1)
        self.assertNotEqual(mutated, original)
        with self.assertRaisesRegex(GUARD.GuardError, "assignment shape changed"):
            GUARD._guard_python(path_text, mutated)

    def test_detached_and_dynamic_process_callables_are_rejected(self) -> None:
        # Use an allowlisted path so rejection proves the exact call signature,
        # not merely the file-level subprocess-import rule, is load-bearing.
        cases = {
            "detached": 'import subprocess\nrunner = subprocess.run\n',
            "getattr": 'import subprocess\ngetattr(subprocess, "run")(["kaggle"])\n',
            "module alias": 'import subprocess\nprocess = subprocess\nprocess.run(["kaggle"])\n',
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                tree = ast.parse(source)
                visitor = GUARD._PythonEffectGuard("scripts/build_notebook.py", tree)
                with self.assertRaisesRegex(GUARD.GuardError, "effect"):
                    visitor.visit(tree)

    def test_only_exact_git_subprocess_callers_are_allowed(self) -> None:
        result = GUARD.guard([
            "tools/repository_guard.py",
            "scripts/build_notebook.py",
            "scripts/verify_candidate.py",
            "scripts/verify_human_gate.py",
            "tools/verify_station.py",
        ])
        self.assertEqual(result["python"], 5)

    def test_shell_and_extensionless_executables_are_rejected(self) -> None:
        shell = ROOT / "tests/.effect-launcher.sh"
        extensionless = ROOT / "tests/effect-launcher"
        shell.write_text("#!/bin/sh\nkaggle kernels push -p .\n", encoding="utf-8")
        extensionless.write_text("#!/bin/sh\ncurl https://example.invalid\n", encoding="utf-8")
        extensionless.chmod(extensionless.stat().st_mode | stat.S_IXUSR)
        try:
            for fixture in (shell, extensionless):
                with self.subTest(path=fixture.name), self.assertRaisesRegex(
                    GUARD.GuardError, "unapproved tracked"
                ):
                    GUARD.guard([str(fixture.relative_to(ROOT))])
        finally:
            shell.unlink(missing_ok=True)
            extensionless.unlink(missing_ok=True)

    def test_git_index_executable_bit_is_independently_rejected(self) -> None:
        fixture = ROOT / "tests/index-executable"
        fixture.write_text("kaggle kernels push -p .\n", encoding="utf-8")
        fixture.chmod(stat.S_IRUSR | stat.S_IWUSR)
        try:
            self.assertTrue(GUARD._is_unapproved_script(fixture, fixture.read_bytes(), "100755"))
        finally:
            fixture.unlink(missing_ok=True)

    def test_foreign_executables_and_unknown_source_types_are_rejected(self) -> None:
        fixtures = {
            "tests/.effect.PY": "import requests\n",
            "tests/.effect.pyc": "sourceless import shadow\n",
            "tests/.effect.so": "native import shadow\n",
            "tests/.effect.txt": "import requests\n",
            "tests/.effect.ipynb": '{"cells": []}\n',
            "tests/effect-no-suffix": "import requests\n",
            "tests/.effect.js": "#!/usr/bin/env node\nfetch('https://example.invalid')\n",
            "tests/.effect.rb": "#!/usr/bin/env ruby\nsystem('git push origin HEAD')\n",
            "tests/.effect.exe": "MZ-not-an-approved-binary\n",
            "tests/.effect.json": '{"apparently": "data"}\n',
        }
        paths = []
        try:
            for relative, content in fixtures.items():
                path = ROOT / relative
                path.write_text(content, encoding="utf-8")
                if path.suffix.lower() in {".js", ".rb", ".exe", ".json"}:
                    path.chmod(path.stat().st_mode | stat.S_IXUSR)
                paths.append(path)
                with self.subTest(path=relative), self.assertRaises(GUARD.GuardError):
                    GUARD.guard([relative])
        finally:
            for path in paths:
                path.unlink(missing_ok=True)

    def test_makefile_bytes_are_exactly_allowlisted(self) -> None:
        fixture_root = ROOT / "tests/.guard-root-fixture"
        fixture_root.mkdir(exist_ok=False)
        (fixture_root / "Makefile").write_text(
            "all:\n\tcurl https://example.invalid\n",
            encoding="utf-8",
        )
        try:
            with (
                patch.object(GUARD, "ROOT", fixture_root),
                self.assertRaisesRegex(GUARD.GuardError, "Makefile staged blob"),
            ):
                GUARD.guard(["Makefile"])
        finally:
            (fixture_root / "Makefile").unlink(missing_ok=True)
            fixture_root.rmdir()

    def test_exact_staged_blob_wins_over_clean_worktree_shadow(self) -> None:
        target = "tools/pair_static.py"
        self.assertNotIn(b"import requests", (ROOT / target).read_bytes())
        entries = GUARD.tracked_entries()
        mode, _ = entries[target]
        bad_object = "a" * 40
        ordered = {target: (mode, bad_object)}
        ordered.update((path, entry) for path, entry in entries.items() if path != target)
        real_reader = GUARD.read_index_blob

        def staged_reader(object_id: str) -> bytes:
            if object_id == bad_object:
                return b"import requests\n"
            return real_reader(object_id)

        with (
            patch.object(GUARD, "tracked_entries", return_value=ordered),
            patch.object(GUARD, "read_index_blob", side_effect=staged_reader),
            self.assertRaisesRegex(GUARD.GuardError, "effect-capable import"),
        ):
            GUARD.guard()

    def test_index_change_during_scan_is_rejected(self) -> None:
        original = GUARD.tracked_entries()
        changed = dict(original)
        target = "tools/pair_static.py"
        mode, _ = changed[target]
        changed[target] = (mode, "f" * 40)
        with (
            patch.object(GUARD, "tracked_entries", side_effect=[original, changed]),
            patch.object(GUARD, "_guard_workflow"),
            self.assertRaisesRegex(GUARD.GuardError, "index changed while"),
        ):
            GUARD.guard()

    def test_unapproved_workflow_is_rejected_as_a_whole(self) -> None:
        fixture = ROOT / ".github/workflows/.exfil-fixture.yml"
        fixture.write_text(
            "on: push\njobs:\n  exfil:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: python -c 'import urllib3; urllib3.PoolManager()'\n",
            encoding="utf-8",
        )
        try:
            with self.assertRaisesRegex(GUARD.GuardError, "workflow"):
                GUARD.guard([str(fixture.relative_to(ROOT))])
        finally:
            fixture.unlink(missing_ok=True)

    def test_workflows_bootstrap_exact_index_guard_before_repository_code(self) -> None:
        for path_text in GUARD.ALLOWED_WORKFLOW_NORMALIZED_SHA256:
            source = (ROOT / path_text).read_text(encoding="utf-8")
            with self.subTest(path=path_text):
                self.assertIn('"ls-files", "--stage", "-z", "--", "tools/repository_guard.py"', source)
                self.assertIn('rb"100644 ([0-9a-f]{40,64}) 0\\ttools/repository_guard\\.py\\x00"', source)
                self.assertIn('"cat-file", "blob", match.group(1).decode("ascii")', source)
                self.assertIn('"GIT_NO_REPLACE_OBJECTS": "1"', source)
                self.assertIn(
                    'framed = b"blob " + str(len(blob)).encode("ascii") + b"\\0" + blob',
                    source,
                )
                self.assertIn("hashlib.new(object_hash, framed).hexdigest()", source)
                self.assertIn("if hashlib.sha256(blob).hexdigest() != expected_guard_sha256:", source)
                self.assertIn("os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW", source)
                self.assertIn(
                    'python -I -B "$RUNNER_TEMP/hearthline-repository-guard.py" '
                    '--root "$GITHUB_WORKSPACE"',
                    source,
                )
                self.assertNotIn("python -I -B tools/repository_guard.py", source)
                self.assertLess(
                    source.index("Materialize and run the exact staged repository guard"),
                    source.rindex("python -I -B"),
                )

        launch = (ROOT / ".github/workflows/launch-verify.yml").read_text(encoding="utf-8")
        verify = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        self.assertNotIn("\n    paths:", launch)
        self.assertIn("  push:\n", launch)
        self.assertIn("  pull_request:\n", launch)
        self.assertIn("  verify-launch:\n    needs: guard-repository\n", launch)
        self.assertIn("  verify:\n    needs: guard-repository\n", verify)

    def test_guard_only_regular_blob_change_is_stopped_by_workflow_pin(self) -> None:
        path_text = ".github/workflows/launch-verify.yml"
        workflow = (ROOT / path_text).read_bytes()
        changed_guard = (ROOT / "tools/repository_guard.py").read_bytes() + b"\nprint('effect')\n"
        with self.assertRaisesRegex(GUARD.GuardError, "pin does not match"):
            GUARD._guard_workflow(
                path_text,
                workflow,
                GUARD.hashlib.sha256(changed_guard).hexdigest(),
            )

    def test_index_symlink_mode_is_rejected_before_blob_read(self) -> None:
        with (
            patch.object(
                GUARD,
                "tracked_entries",
                return_value={"tools/repository_guard.py": ("120000", "0" * 40)},
            ),
            patch.object(GUARD, "read_index_blob") as reader,
            self.assertRaisesRegex(GUARD.GuardError, "non-regular or executable tracked paths"),
        ):
            GUARD.guard()
        reader.assert_not_called()

    def test_generated_notebook_intended_runtime_is_structurally_allowed(self) -> None:
        source = (ROOT / "scripts/build_notebook.py").read_text(encoding="utf-8")
        GUARD._validate_notebook_builder(ast.parse(source))

    def test_generated_notebook_rejects_changed_effect_surfaces(self) -> None:
        source = (ROOT / "scripts/build_notebook.py").read_text(encoding="utf-8")
        mutations = {
            "online install": source.replace(
                "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels",
                "https://example.invalid/wheels",
                1,
            ),
            "Kaggle subprocess": source.replace(
                '[str(bound_interpreter_path), "-E", "-s", "-B", "main.py", "--agent", "myagent"]',
                '["kaggle", "kernels", "push"]',
                1,
            ),
            "external gateway": source.replace(
                'gateway = "http://gateway:8001/api/games"',
                'gateway = "https://example.invalid/api/games"',
                1,
            ),
            "ambient proxy enabled": source.replace(
                "urllib.request.ProxyHandler({}),\n                _NoGatewayRedirect(),",
                "_NoGatewayRedirect(),",
                1,
            ),
            "redirect handler weakened": source.replace(
                'raise RuntimeError("competition gateway redirect is forbidden")',
                "return None",
                1,
            ),
            "cell constructor transformation": source.replace(
                '"source": source,',
                '"source": source + "\\n!kaggle kernels push -p .",',
                1,
            ),
        }
        for label, mutated in mutations.items():
            self.assertNotEqual(mutated, source, f"mutation fixture did not alter source: {label}")
            with self.subTest(label=label), self.assertRaises(GUARD.GuardError):
                GUARD._validate_notebook_builder(ast.parse(mutated))

    def test_duplicate_json_is_rejected(self) -> None:
        fixture = ROOT / "tests/.duplicate-fixture.json"
        fixture.write_text('{"same":1,"same":2}', encoding="utf-8")
        try:
            with self.assertRaisesRegex(GUARD.GuardError, "duplicate JSON key"):
                GUARD.guard([str(fixture.relative_to(ROOT))])
        finally:
            fixture.unlink()

    def test_overflowing_json_number_is_rejected(self) -> None:
        fixture = ROOT / "tests/.overflow-fixture.json"
        fixture.write_text('{"overflow":1e999}', encoding="utf-8")
        try:
            with self.assertRaisesRegex(GUARD.GuardError, "non-finite JSON number"):
                GUARD.guard([str(fixture.relative_to(ROOT))])
        finally:
            fixture.unlink()


if __name__ == "__main__":
    unittest.main()
