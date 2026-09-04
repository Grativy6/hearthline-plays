from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_STARTER = ROOT.parent / "references" / "ARC-AGI-3-Kaggle-Starter"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BUILD = load_module("arc3_build_notebook_test", ROOT / "scripts/build_notebook.py")
VERIFY = load_module("arc3_verify_candidate_test", ROOT / "scripts/verify_candidate.py")


class StubActionData:
    def __init__(self, values: dict[str, object] | None = None, **kwargs: object) -> None:
        self._values = {"game_id": "", **dict(values or {}), **kwargs}

    def model_dump(self) -> dict[str, object]:
        return dict(self._values)


class StubGameAction(Enum):
    RESET = "RESET"
    ACTION1 = "ACTION1"
    ACTION2 = "ACTION2"
    ACTION3 = "ACTION3"
    ACTION4 = "ACTION4"
    ACTION5 = "ACTION5"
    ACTION6 = "ACTION6"
    ACTION7 = "ACTION7"

    def __init__(self, _: str) -> None:
        self.action_data = StubActionData({})
        self.reasoning: object = None

    def is_complex(self) -> bool:
        return self is StubGameAction.ACTION6

    @property
    def action_type(self):
        return StubActionData

    def set_data(self, data: dict[str, int]) -> None:
        # The official complex action model contributes a default game_id.
        self.action_data = StubActionData({"game_id": "", **dict(data)})


class StubGameState(Enum):
    NOT_PLAYED = "NOT_PLAYED"
    NOT_FINISHED = "NOT_FINISHED"
    WIN = "WIN"
    GAME_OVER = "GAME_OVER"


@dataclass
class StubFrameData:
    state: StubGameState
    levels_completed: int = 0
    available_actions: list[StubGameAction] | None = None


class StubAgent:
    MAX_ACTIONS = 80

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args
        self.game_id = str(kwargs.get("game_id", "offline"))
        self.agent_name = str(kwargs.get("agent_name", type(self).__name__.lower()))

    @property
    def name(self) -> str:
        return self.agent_name

    def _convert_raw_frame_data(self, raw: object) -> object:
        return raw


def load_agent_with_official_shape_stubs():
    arcengine = types.ModuleType("arcengine")
    arcengine.FrameData = StubFrameData
    arcengine.GameAction = StubGameAction
    arcengine.GameState = StubGameState
    agents = types.ModuleType("agents")
    agents.__path__ = []
    agent_module = types.ModuleType("agents.agent")
    agent_module.Agent = StubAgent
    with mock.patch.dict(
        sys.modules,
        {"arcengine": arcengine, "agents": agents, "agents.agent": agent_module},
    ):
        return load_module("hearthline_my_agent_test", ROOT / "agent/my_agent.py")


AGENT = load_agent_with_official_shape_stubs()


class OfficialAgentShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        for action in StubGameAction:
            action.action_data = StubActionData({})
            action.reasoning = None

    def frame(
        self,
        state: StubGameState = StubGameState.NOT_FINISHED,
        levels: int = 0,
        available: list[StubGameAction] | None = None,
    ) -> StubFrameData:
        return StubFrameData(
            state=state,
            levels_completed=levels,
            available_actions=list(StubGameAction) if available is None else available,
        )

    def test_subclass_name_and_reset_contract(self) -> None:
        agent = AGENT.MyAgent(game_id="ls20-9607627b", agent_name="fixture")
        self.assertIsInstance(agent, StubAgent)
        self.assertEqual(agent.name, "fixture.hearthline-v2.A0_MINIMAL.80")
        for state in (StubGameState.NOT_PLAYED, StubGameState.GAME_OVER):
            action = agent.choose_action([], self.frame(state=state))
            self.assertEqual(action.name, "RESET")
            self.assertEqual(
                action.reasoning()["authority"],
                "framework-owned effect only",
            )

    def test_grounded_ls20_route_is_exact_then_baseline(self) -> None:
        agent = AGENT.MyAgent(game_id="ls20-9607627b")
        chosen = [agent.choose_action([], self.frame()).name for _ in range(13)]
        self.assertEqual(chosen, list(agent.LS20_LEVEL1_ROUTE))
        advanced = agent.choose_action([], self.frame(levels=1))
        self.assertEqual(advanced.name, "ACTION1")

    def test_action_cap_and_win_stop(self) -> None:
        agent = AGENT.MyAgent(game_id="ft09")
        self.assertFalse(agent.is_done([], self.frame()))
        for _ in range(agent.MAX_ACTIONS):
            agent.choose_action([], self.frame())
        self.assertTrue(agent.is_done([], self.frame()))
        with self.assertRaisesRegex(RuntimeError, "action cap reached"):
            agent.choose_action([], self.frame())
        fresh = AGENT.MyAgent(game_id="ft09")
        self.assertTrue(fresh.is_done([], self.frame(state=StubGameState.WIN)))

    def test_complex_request_does_not_read_or_mutate_singleton_fields(self) -> None:
        action = StubGameAction.ACTION6
        action.action_data = StubActionData({"game_id": "old", "x": 1, "y": 2, "stale": True})
        action.reasoning = {"stale": True}
        first = AGENT.MyAgent._decorate(action, {"call": "first"})
        second = AGENT.MyAgent._decorate(action, {"call": "second"})
        self.assertIsNot(first, second)
        self.assertEqual(first.payload(), {"game_id": "", "x": 31, "y": 31})
        self.assertEqual(first.reasoning(), {"call": "first"})
        self.assertEqual(second.reasoning(), {"call": "second"})
        self.assertEqual(second.payload(), {"game_id": "", "x": 31, "y": 31})
        self.assertEqual(
            action.action_data.model_dump(),
            {"game_id": "old", "x": 1, "y": 2, "stale": True},
        )
        self.assertEqual(action.reasoning, {"stale": True})

    def test_complex_fallback_uses_declared_action_and_fresh_payload(self) -> None:
        agent = AGENT.MyAgent(game_id="unknown")
        frame = self.frame(available=[StubGameAction.ACTION6])
        action = agent.choose_action([], frame)
        self.assertEqual(action.name, "ACTION6")
        self.assertEqual(action.payload(), {"game_id": "", "x": 31, "y": 31})

    def test_explicit_empty_availability_fails_closed(self) -> None:
        agent = AGENT.MyAgent(game_id="unknown")
        with self.assertRaisesRegex(RuntimeError, "no available action"):
            agent.choose_action([], self.frame(available=[]))

    def test_simple_request_ignores_stale_singleton_payload(self) -> None:
        action = StubGameAction.ACTION1
        action.action_data = StubActionData({"game_id": "old", "x": 4, "stale": True})
        decorated = AGENT.MyAgent._decorate(action, {"call": "fresh"})
        self.assertEqual(decorated.payload(), {"game_id": ""})
        self.assertEqual(decorated.reasoning(), {"call": "fresh"})
        self.assertEqual(
            action.action_data.model_dump(),
            {"game_id": "old", "x": 4, "stale": True},
        )

    def test_action_requests_remain_instance_local_under_concurrency(self) -> None:
        barrier = threading.Barrier(2)

        class RecordingEnvironment:
            def __init__(self) -> None:
                self.requests: list[tuple[object, dict, dict]] = []

            def step(self, action, *, data, reasoning):
                barrier.wait(timeout=5)
                self.requests.append((action, dict(data), dict(reasoning)))
                return {"accepted": True}

        first_agent = AGENT.MyAgent(game_id="concurrent-a")
        second_agent = AGENT.MyAgent(game_id="concurrent-b")
        first_agent.arc_env = RecordingEnvironment()
        second_agent.arc_env = RecordingEnvironment()
        singleton_before = StubGameAction.ACTION6.action_data.model_dump()
        first = AGENT._seal_action_request(
            StubGameAction.ACTION6,
            {"x": 2, "y": 3},
            {"worker": "first"},
        )
        second = AGENT._seal_action_request(
            StubGameAction.ACTION6,
            {"x": 61, "y": 62},
            {"worker": "second"},
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(first_agent.do_action_request, first)
            second_future = executor.submit(second_agent.do_action_request, second)
            self.assertEqual(first_future.result(timeout=10), {"accepted": True})
            self.assertEqual(second_future.result(timeout=10), {"accepted": True})
        self.assertEqual(first_agent.arc_env.requests, [(
            StubGameAction.ACTION6,
            {"game_id": "", "x": 2, "y": 3},
            {"worker": "first"},
        )])
        self.assertEqual(second_agent.arc_env.requests, [(
            StubGameAction.ACTION6,
            {"game_id": "", "x": 61, "y": 62},
            {"worker": "second"},
        )])
        self.assertEqual(StubGameAction.ACTION6.action_data.model_dump(), singleton_before)

    def test_request_seal_detaches_nested_data_and_rejects_raw_enum(self) -> None:
        reasoning = {"observations": ["first"]}
        request = AGENT._seal_action_request(
            StubGameAction.ACTION1,
            {},
            reasoning,
        )
        reasoning["observations"].append("late mutation")
        opened = request.reasoning()
        opened_observations = opened["observations"]
        self.assertIsInstance(opened_observations, list)
        opened_observations.append("returned-copy mutation")
        self.assertEqual(request.reasoning(), {"observations": ["first"]})
        with self.assertRaisesRegex(RuntimeError, "unsealed action request"):
            AGENT.MyAgent(game_id="unknown").do_action_request(StubGameAction.ACTION1)

    def test_boolean_counters_fail_closed(self) -> None:
        agent = AGENT.MyAgent(game_id="unknown")
        with self.assertRaisesRegex(RuntimeError, "not a boolean"):
            agent.choose_action([], self.frame(levels=True))

        class BooleanCapAgent(AGENT.MyAgent):
            MAX_ACTIONS = True

        with self.assertRaisesRegex(ValueError, "not a boolean"):
            BooleanCapAgent(game_id="unknown")

    def test_context_profiles_and_atomic_advance_match_machine_context(self) -> None:
        context = json.loads((ROOT / "launch/context/roles.v2.json").read_text(encoding="utf-8"))
        expected = {key: frozenset(value) for key, value in context["frozen_profiles"].items()}
        self.assertEqual(AGENT.ROLE_PROFILES, expected)
        current = {"hypothesis": {"value": "old"}}
        blocked = AGENT.advance(current, "hypothesis", "new", [], False)
        self.assertFalse(blocked.promoted)
        self.assertEqual(blocked.successor, current)
        promoted = AGENT.advance(current, "fact", 7, ["receipt:1"], True)
        self.assertTrue(promoted.promoted)
        self.assertNotIn("fact", current)
        self.assertEqual(promoted.successor["fact"], {"value": 7, "evidence_refs": ["receipt:1"]})


class CandidatePackageTests(unittest.TestCase):
    CLEAN_IDENTITY = {
        "commit": "1" * 40,
        "tree": "2" * 40,
        "worktree_clean": True,
    }

    def trusted_snapshot(self) -> dict:
        return {
            "identity": dict(self.CLEAN_IDENTITY),
            "files": {
                relative: (ROOT / relative).read_bytes()
                for relative in VERIFY.TRUSTED_INPUT_PATHS
            },
        }

    def build_fixture(self, output: Path) -> None:
        if (
            not hasattr(os, "O_DIRECTORY")
            or not hasattr(os, "O_NOFOLLOW")
            or not all(
                function in os.supports_dir_fd
                for function in (os.open, os.mkdir, os.rename, os.stat)
            )
        ):
            self.skipTest("safe directory-descriptor packaging is unavailable")
        committed = {
            relative: (ROOT / relative).read_bytes()
            for relative in VERIFY.TRUSTED_INPUT_PATHS
        }
        with mock.patch.object(
            BUILD, "git_identity", return_value=dict(self.CLEAN_IDENTITY)
        ), mock.patch.object(
            BUILD, "_git_blob", side_effect=lambda _commit, relative: committed[relative]
        ):
            BUILD.build(output, "fixture-user", "cpu")

    def test_builder_rejects_non_ascii_account_slug(self) -> None:
        with self.assertRaisesRegex(BUILD.BuildError, "Kaggle account slug"):
            BUILD._validate_username("éé")
        self.assertEqual(BUILD._validate_username("fixture-user"), "fixture-user")

    def verify_fixture(
        self,
        output: Path,
        *,
        materialize: bool = True,
        receipt: Path | None = None,
    ) -> dict:
        with mock.patch.object(
            VERIFY, "trusted_git_snapshot", return_value=self.trusted_snapshot()
        ), mock.patch.object(
            VERIFY, "current_git_identity", return_value=dict(self.CLEAN_IDENTITY)
        ):
            return VERIFY.verify(
                output,
                require_clean=True,
                materialize=materialize,
                receipt=receipt,
            )

    @staticmethod
    def rewrite(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, indent=1) + "\n", encoding="utf-8")

    @staticmethod
    def rehash_manifest(output: Path) -> None:
        path = output / "candidate-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["artifacts"]["submission.ipynb"] = hashlib.sha256(
            (output / "submission.ipynb").read_bytes()
        ).hexdigest()
        manifest["artifacts"]["kernel-metadata.json"] = hashlib.sha256(
            (output / "kernel-metadata.json").read_bytes()
        ).hexdigest()
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def test_deterministic_exact_regeneration_and_content_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            first = (output / "submission.ipynb").read_bytes()
            self.build_fixture(output)
            self.assertEqual(first, (output / "submission.ipynb").read_bytes())
            result = self.verify_fixture(output)
            self.assertEqual(result["structural_verification"], "PASS")
            self.assertTrue(result["kaggle_stage_ready"])
            self.assertFalse(result["competition_ignition_ready"])
            self.assertEqual(
                result["verified_inputs"]["runtime_closure_status"],
                "UNFROZEN_PENDING_GATE_A_SUCCESSOR",
            )
            snapshot = Path(result["verified_snapshot"]["path"])
            self.assertTrue(snapshot.is_dir())
            for name in VERIFY.BUILD_FILES:
                self.assertEqual((snapshot / name).read_bytes(), (output / name).read_bytes())

    def test_rehashed_notebook_output_and_extra_code_each_fail(self) -> None:
        attacks = []
        def hidden_output(document: dict) -> None:
            document["cells"][1]["outputs"] = [{"output_type": "stream", "text": "hidden"}]
        attacks.append(hidden_output)
        def dump_environment(document: dict) -> None:
            document["cells"][4]["source"] += "\nprint(dict(os.environ))\n"
        attacks.append(dump_environment)
        for attack in attacks:
            with self.subTest(attack=attack.__name__), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "build"
                self.build_fixture(output)
                path = output / "submission.ipynb"
                notebook = json.loads(path.read_text(encoding="utf-8"))
                attack(notebook)
                self.rewrite(path, notebook)
                self.rehash_manifest(output)
                with self.assertRaises(VERIFY.CandidateError):
                    self.verify_fixture(output, materialize=False)

    def test_rehashed_metadata_dataset_and_code_file_each_fail(self) -> None:
        for key, value in (
            ("dataset_sources", ["private-holdout-dataset"]),
            ("code_file", "not-the-verified-notebook.py"),
        ):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "build"
                self.build_fixture(output)
                path = output / "kernel-metadata.json"
                metadata = json.loads(path.read_text(encoding="utf-8"))
                metadata[key] = value
                self.rewrite(path, metadata)
                self.rehash_manifest(output)
                with self.assertRaises(VERIFY.CandidateError):
                    self.verify_fixture(output, materialize=False)

    def test_rehashed_manifest_lineage_fails_exact_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            path = output / "candidate-manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["candidate"]["commit"] = "3" * 40
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.CandidateError, "exact committed regeneration"):
                self.verify_fixture(output, materialize=False)

    def test_duplicate_json_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            path = output / "candidate-manifest.json"
            path.write_bytes(path.read_bytes().replace(b'{\n  "artifacts"', b'{\n  "schema": "duplicate",\n  "artifacts"', 1))
            with self.assertRaisesRegex(VERIFY.CandidateError, "duplicate JSON key"):
                self.verify_fixture(output, materialize=False)

    def test_exponent_overflow_json_fails_closed(self) -> None:
        with self.assertRaisesRegex(BUILD.BuildError, "non-finite JSON number"):
            BUILD.strict_json_bytes(b'{"overflow":1e999}', "overflow fixture")
        with self.assertRaisesRegex(VERIFY.CandidateError, "non-finite JSON number"):
            VERIFY.loads_strict(b'{"overflow":1e999}', "overflow fixture")

    def test_trusted_runtime_versions_are_exactly_pinned(self) -> None:
        committed = self.trusted_snapshot()["files"]
        source_lock = json.loads(
            committed["launch/source-lock.v3.json"].decode("utf-8")
        )
        self.assertEqual(
            source_lock["dependency_resolution"]["required_runtime_versions"],
            {"arc-agi": "0.9.9", "arcengine": "0.9.3"},
        )
        source_lock["dependency_resolution"]["required_runtime_versions"][
            "arcengine"
        ] = "0.0.0"
        altered = dict(committed)
        altered["launch/source-lock.v3.json"] = (
            json.dumps(source_lock).encode("utf-8")
        )
        with self.assertRaisesRegex(VERIFY.CandidateError, "runtime versions"):
            VERIFY.inspect_trusted_contracts(altered)

    def test_stage_inventory_rejects_pep503_canonical_alias_collisions(self) -> None:
        source_lock = json.loads(
            (ROOT / "launch/source-lock.v3.json").read_text(encoding="utf-8")
        )
        python_minor, status, runtime_versions, agents_files, license_file = (
            BUILD._execution_guard_inputs(source_lock)
        )
        dummy_source = BUILD.notebook_document(
            "# test agent\n",
            "cpu",
            python_minor,
            status,
            runtime_versions,
            agents_files,
            license_file,
        )["cells"][4]["source"]
        self.assertIn('re.sub(r"[-_.]+", "-", raw_name).lower()', dummy_source)
        self.assertIn("if name in distributions:", dummy_source)
        self.assertIn("duplicate canonical distribution name", dummy_source)

    def test_git_reads_disable_ambient_config_hooks_and_lazy_fetch(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "GIT_CONFIG_GLOBAL": "/tmp/attacker.gitconfig",
                "GIT_CONFIG_PARAMETERS": "'core.fsmonitor=attacker'",
                "GIT_SSH_COMMAND": "attacker",
            },
            clear=False,
        ):
            for module in (BUILD, VERIFY):
                environment = module._git_environment()
                self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
                self.assertEqual(environment["GIT_CONFIG_GLOBAL"], os.devnull)
                self.assertEqual(environment["GIT_NO_LAZY_FETCH"], "1")
                self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")
                self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
                self.assertNotIn("GIT_CONFIG_PARAMETERS", environment)
                self.assertNotIn("GIT_SSH_COMMAND", environment)
                command = module._git_command("status", "--porcelain")
                self.assertEqual(command[:5], [
                    "git", "-c", "core.fsmonitor=false", "-c",
                    f"core.hooksPath={os.devnull}",
                ])

    def rerun_source(
        self,
        runtime_closure_status: str = "FROZEN_POST_STAGE_SUCCESSOR",
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        source_lock = json.loads(
            (ROOT / "launch/source-lock.v3.json").read_text(encoding="utf-8")
        )
        python_minor, _, runtime_versions, agents_files, license_file = (
            BUILD._execution_guard_inputs(source_lock)
        )
        notebook = BUILD.notebook_document(
            "# test agent\n",
            "cpu",
            python_minor,
            runtime_closure_status,
            runtime_versions,
            agents_files,
            license_file,
        )
        return notebook["cells"][3]["source"], runtime_versions, agents_files

    def frozen_runtime_fixture(
        self,
        root: Path,
    ) -> tuple[str, Path, Path, Path, dict[str, str]]:
        runtime_versions = {"arc-agi": "0.9.9", "arcengine": "0.9.3"}
        framework = root / "source"
        target = root / "target"
        test_agent = root / "my_agent.py"
        test_agent.write_text("# test agent\n", encoding="utf-8")
        agents_files = {}
        for relative in (
            "agents/agent.py",
            "agents/recorder.py",
            "agents/swarm.py",
            "agents/tracing.py",
            "main.py",
        ):
            path = framework / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            content = f"sealed {relative}\n".encode("utf-8")
            path.write_bytes(content)
            agents_files[relative] = hashlib.sha256(content).hexdigest()
        license_bytes = b"MIT test license\n"
        (framework / "LICENSE").write_bytes(license_bytes)
        run_source = BUILD.notebook_document(
            "# test agent\n",
            "cpu",
            "3.12",
            "FROZEN_POST_STAGE_SUCCESSOR",
            runtime_versions,
            agents_files,
            {"LICENSE": hashlib.sha256(license_bytes).hexdigest()},
        )["cells"][3]["source"]
        return run_source, framework, target, test_agent, runtime_versions

    @staticmethod
    def redirect_runtime_paths(
        framework: Path,
        target: Path,
        test_agent: Path,
    ):
        real_path = Path
        source_literal = (
            "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/"
            "ARC-AGI-3-Agents"
        )

        def redirected_path(value: object) -> Path:
            rendered = os.fspath(value)
            if rendered == source_literal:
                return framework
            if rendered == "/kaggle/working/ARC-AGI-3-Agents":
                return target
            if rendered == "/tmp/my_agent.py":
                return test_agent
            return real_path(value)

        return redirected_path

    def test_unfrozen_runtime_closure_blocks_competition_rerun_before_effects(self) -> None:
        run_source, _, _ = self.rerun_source("UNFROZEN_PENDING_GATE_A_SUCCESSOR")
        with mock.patch.object(os, "getenv", return_value="1"), mock.patch(
            "importlib.metadata.version"
        ) as version, mock.patch("urllib.request.build_opener") as build_opener, mock.patch(
            "shutil.copy2"
        ) as copy2, mock.patch("subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "RUNTIME_CLOSURE_UNFROZEN"):
                exec(compile(run_source, "competition-rerun", "exec"), {})

        version.assert_not_called()
        build_opener.assert_not_called()
        copy2.assert_not_called()
        run.assert_not_called()

    def test_non_200_gateway_response_honors_deadline_without_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_source, framework, target, test_agent, runtime_versions = (
                self.frozen_runtime_fixture(root)
            )
            response = mock.MagicMock()
            response.__enter__.return_value.status = 204
            gateway_opener = mock.MagicMock()
            gateway_opener.open.return_value = response
            redirected_path = self.redirect_runtime_paths(framework, target, test_agent)
            with mock.patch.object(os, "getenv", return_value="1"), mock.patch(
                "importlib.metadata.version",
                side_effect=lambda name: runtime_versions[name],
            ), mock.patch("pathlib.Path", side_effect=redirected_path), mock.patch(
                "urllib.request.build_opener", return_value=gateway_opener
            ) as build_opener, mock.patch(
                "time.monotonic", side_effect=(0.0, 601.0)
            ), mock.patch("time.sleep") as sleep, mock.patch(
                "shutil.copy2"
            ) as copy2, mock.patch("subprocess.run") as run:
                with self.assertRaisesRegex(RuntimeError, "gateway did not become ready"):
                    exec(compile(run_source, "competition-rerun", "exec"), {})

            build_opener.assert_called_once()
            self.assertEqual(len(build_opener.call_args.args), 2)
            proxy_handler, redirect_handler = build_opener.call_args.args
            self.assertEqual(proxy_handler.proxies, {})
            self.assertEqual(type(redirect_handler).__name__, "_NoGatewayRedirect")
            with self.assertRaisesRegex(RuntimeError, "gateway redirect is forbidden"):
                redirect_handler.redirect_request(
                    object(), object(), 302, "Found", {"Location": "https://example.invalid"},
                    "https://example.invalid",
                )
            gateway_opener.open.assert_called_once_with(
                "http://gateway:8001/api/games",
                timeout=5,
            )
            sleep.assert_not_called()
            copy2.assert_not_called()
            run.assert_not_called()

    def test_interpreter_rebind_is_detected_before_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_source, framework, target, test_agent, runtime_versions = (
                self.frozen_runtime_fixture(root)
            )
            interpreter = root / "python"
            interpreter_bytes = b"sealed interpreter bytes\n"
            interpreter.write_bytes(interpreter_bytes)
            interpreter.chmod(0o700)
            response = mock.MagicMock()
            response.__enter__.return_value.status = 200
            gateway_opener = mock.MagicMock()

            def rebind_interpreter(*_: object, **__: object):
                original = root / "python-original"
                interpreter.replace(original)
                interpreter.write_bytes(interpreter_bytes)
                interpreter.chmod(0o700)
                return response

            gateway_opener.open.side_effect = rebind_interpreter
            redirected_path = self.redirect_runtime_paths(framework, target, test_agent)
            with mock.patch.object(os, "getenv", return_value="1"), mock.patch.object(
                sys, "executable", str(interpreter)
            ), mock.patch(
                "importlib.metadata.version",
                side_effect=lambda name: runtime_versions[name],
            ), mock.patch("pathlib.Path", side_effect=redirected_path), mock.patch(
                "urllib.request.build_opener", return_value=gateway_opener
            ), mock.patch("subprocess.run") as run:
                with self.assertRaisesRegex(RuntimeError, "interpreter identity changed"):
                    exec(compile(run_source, "competition-rerun", "exec"), {})

            run.assert_not_called()

    def test_competition_rerun_python_minor_drift_fails_before_any_framework_effect(self) -> None:
        run_source, _, _ = self.rerun_source()
        with mock.patch.object(os, "getenv", return_value="1"), mock.patch.object(
            sys, "version_info", (3, 13, 0)
        ), mock.patch("importlib.metadata.version") as version, mock.patch(
            "urllib.request.build_opener"
        ) as build_opener, mock.patch("shutil.copy2") as copy2, mock.patch(
            "subprocess.run"
        ) as run:
            with self.assertRaisesRegex(RuntimeError, "Python minor mismatch"):
                exec(compile(run_source, "competition-rerun", "exec"), {})

        version.assert_not_called()
        build_opener.assert_not_called()
        copy2.assert_not_called()
        run.assert_not_called()

    def test_competition_rerun_runtime_drift_fails_before_any_framework_effect(self) -> None:
        run_source, runtime_versions, _ = self.rerun_source()

        def drifted_version(name: str) -> str:
            if name == "arcengine":
                return "0.0.0"
            return runtime_versions[name]

        with mock.patch.object(os, "getenv", return_value="1"), mock.patch(
            "importlib.metadata.version", side_effect=drifted_version
        ), mock.patch("urllib.request.build_opener") as build_opener, mock.patch(
            "shutil.copytree"
        ) as copytree, mock.patch("shutil.copy2") as copy2, mock.patch(
            "subprocess.run"
        ) as run:
            with self.assertRaisesRegex(RuntimeError, "runtime version mismatch"):
                exec(compile(run_source, "competition-rerun", "exec"), {})

        build_opener.assert_not_called()
        copytree.assert_not_called()
        copy2.assert_not_called()
        run.assert_not_called()

    def test_competition_rerun_source_drift_fails_before_copy_or_framework_import(self) -> None:
        run_source, runtime_versions, agents_files = self.rerun_source()
        real_path = Path
        source_literal = (
            "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/"
            "ARC-AGI-3-Agents"
        )
        with tempfile.TemporaryDirectory() as temporary:
            framework = real_path(temporary) / "ARC-AGI-3-Agents"
            for relative in agents_files:
                path = framework / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"drifted {relative}\n".encode("utf-8"))

            def redirected_path(value: object) -> Path:
                if os.fspath(value) == source_literal:
                    return framework
                return real_path(value)

            with mock.patch.object(os, "getenv", return_value="1"), mock.patch(
                "importlib.metadata.version",
                side_effect=lambda name: runtime_versions[name],
            ), mock.patch("pathlib.Path", side_effect=redirected_path), mock.patch(
                "urllib.request.build_opener"
            ) as build_opener, mock.patch("shutil.copytree") as copytree, mock.patch(
                "shutil.copy2"
            ) as copy2, mock.patch("subprocess.run") as run:
                with self.assertRaisesRegex(RuntimeError, "Agents source mismatch"):
                    exec(compile(run_source, "competition-rerun", "exec"), {})

        build_opener.assert_not_called()
        copytree.assert_not_called()
        copy2.assert_not_called()
        run.assert_not_called()

    def test_competition_registry_excludes_unmeasured_random_agent(self) -> None:
        run_source, runtime_versions, agents_files = self.rerun_source()
        self.assertNotIn("random_agent", run_source)
        self.assertNotIn('"random":', run_source)
        self.assertNotIn("shutil.copytree", run_source)
        self.assertIn('"myagent": MyAgent', run_source)
        for name, version in runtime_versions.items():
            self.assertIn(json.dumps(name), run_source)
            self.assertIn(json.dumps(version), run_source)
        for relative, digest in agents_files.items():
            self.assertIn(json.dumps(relative), run_source)
            self.assertIn(json.dumps(digest), run_source)

    def test_competition_rerun_tracing_drift_fails_before_copy_or_subprocess(self) -> None:
        runtime_versions = {"arc-agi": "0.9.9", "arcengine": "0.9.3"}
        relative_paths = (
            "agents/agent.py",
            "agents/recorder.py",
            "agents/swarm.py",
            "agents/tracing.py",
            "main.py",
        )
        real_path = Path
        source_literal = (
            "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/"
            "ARC-AGI-3-Agents"
        )
        with tempfile.TemporaryDirectory() as temporary:
            framework = real_path(temporary) / "ARC-AGI-3-Agents"
            agents_files = {}
            for relative in relative_paths:
                path = framework / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                content = f"sealed {relative}\n".encode("utf-8")
                path.write_bytes(content)
                agents_files[relative] = hashlib.sha256(content).hexdigest()
            (framework / "agents/tracing.py").write_text(
                "drift after the expected digest was sealed\n",
                encoding="utf-8",
            )
            run_source = BUILD.notebook_document(
                "# test agent\n",
                "cpu",
                "3.12",
                "FROZEN_POST_STAGE_SUCCESSOR",
                runtime_versions,
                agents_files,
                {"LICENSE": "0" * 64},
            )["cells"][3]["source"]

            def redirected_path(value: object) -> Path:
                if os.fspath(value) == source_literal:
                    return framework
                return real_path(value)

            with mock.patch.object(os, "getenv", return_value="1"), mock.patch(
                "importlib.metadata.version",
                side_effect=lambda name: runtime_versions[name],
            ), mock.patch("pathlib.Path", side_effect=redirected_path), mock.patch(
                "urllib.request.build_opener"
            ) as build_opener, mock.patch("shutil.copytree") as copytree, mock.patch(
                "shutil.copy2"
            ) as copy2, mock.patch("subprocess.run") as run:
                with self.assertRaisesRegex(RuntimeError, "Agents source mismatch"):
                    exec(compile(run_source, "competition-rerun", "exec"), {})

        build_opener.assert_not_called()
        copytree.assert_not_called()
        copy2.assert_not_called()
        run.assert_not_called()

    def test_competition_subprocess_receives_no_ambient_provider_or_tracing_keys(self) -> None:
        runtime_versions = {"arc-agi": "0.9.9", "arcengine": "0.9.3"}
        relative_paths = (
            "agents/agent.py",
            "agents/recorder.py",
            "agents/swarm.py",
            "agents/tracing.py",
            "main.py",
        )
        real_path = Path
        source_literal = (
            "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/"
            "ARC-AGI-3-Agents"
        )
        target_literal = "/kaggle/working/ARC-AGI-3-Agents"
        with tempfile.TemporaryDirectory() as temporary:
            root = real_path(temporary)
            framework = root / "source"
            target = root / "target"
            test_agent = root / "my_agent.py"
            test_agent.write_text("# test agent\n", encoding="utf-8")
            agents_files = {}
            for relative in relative_paths:
                path = framework / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                content = f"sealed {relative}\n".encode("utf-8")
                path.write_bytes(content)
                agents_files[relative] = hashlib.sha256(content).hexdigest()
            license_bytes = b"MIT test license\n"
            (framework / "LICENSE").write_bytes(license_bytes)
            hostile_extras = {
                "sitecustomize.py": "raise RuntimeError('startup shadow executed')\n",
                "requests.py": "raise RuntimeError('dependency shadow executed')\n",
                "agents/templates/__init__.py": "raise RuntimeError('template shadow executed')\n",
                ".env.example": "AGENTOPS_API_KEY=platform-secret\nOPENAI_API_KEY=platform-secret\n",
            }
            for relative, content in hostile_extras.items():
                path = framework / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            run_source = BUILD.notebook_document(
                "# test agent\n",
                "cpu",
                "3.12",
                "FROZEN_POST_STAGE_SUCCESSOR",
                runtime_versions,
                agents_files,
                {"LICENSE": hashlib.sha256(license_bytes).hexdigest()},
            )["cells"][3]["source"]

            def redirected_path(value: object) -> Path:
                rendered = os.fspath(value)
                if rendered == source_literal:
                    return framework
                if rendered == target_literal:
                    return target
                if rendered == "/tmp/my_agent.py":
                    return test_agent
                return real_path(value)

            response = mock.MagicMock()
            response.__enter__.return_value.status = 200
            gateway_opener = mock.MagicMock()
            gateway_opener.open.return_value = response
            ambient_secrets = {
                "AGENTOPS_API_KEY": "must-not-cross",
                "OPENAI_API_KEY": "must-not-cross",
                "ANTHROPIC_API_KEY": "must-not-cross",
                "UNRELATED_SECRET": "must-not-cross",
                "PYTHONPATH": "/tmp/module-shadow",
                "PYTHONHOME": "/tmp/interpreter-shadow",
                "PYTHONSTARTUP": "/tmp/startup-injection.py",
                "PYTHONINSPECT": "1",
                "PYTHONBREAKPOINT": "attacker.breakpoint",
            }
            with mock.patch.dict(os.environ, ambient_secrets, clear=False), mock.patch.object(
                os, "getenv", return_value="1"
            ), mock.patch(
                "importlib.metadata.version",
                side_effect=lambda name: runtime_versions[name],
            ), mock.patch("pathlib.Path", side_effect=redirected_path), mock.patch(
                "urllib.request.build_opener", return_value=gateway_opener
            ), mock.patch("subprocess.run") as run:
                exec(compile(run_source, "competition-rerun", "exec"), {})

            run.assert_called_once()
            self.assertEqual(
                run.call_args.args[0],
                [
                    str(real_path(sys.executable).resolve(strict=True)),
                    "-E",
                    "-s",
                    "-B",
                    "main.py",
                    "--agent",
                    "myagent",
                ],
            )
            child_environment = run.call_args.kwargs["env"]
            for key in ("AGENTOPS_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                self.assertEqual(child_environment[key], "")
            for key in (
                "UNRELATED_SECRET",
                "PYTHONPATH",
                "PYTHONHOME",
                "PYTHONSTARTUP",
                "PYTHONINSPECT",
                "PYTHONBREAKPOINT",
            ):
                self.assertNotIn(key, child_environment)
            self.assertFalse(
                [key for key in child_environment if key.startswith("PYTHON")]
            )
            self.assertEqual(child_environment["ARC_API_KEY"], "test-key-123")
            self.assertEqual(child_environment["ARC_BASE_URL"], "http://gateway:8001/")
            self.assertEqual(child_environment["MPLBACKEND"], "agg")
            self.assertEqual(child_environment["HOME"], str(target / ".runtime-home"))
            self.assertEqual(
                child_environment["XDG_CONFIG_HOME"],
                str(target / ".runtime-home/.config"),
            )
            self.assertEqual(
                child_environment["NETRC"],
                str(target / ".runtime-home/.netrc"),
            )
            self.assertEqual((target / ".runtime-home/.netrc").read_bytes(), b"")
            self.assertEqual((target / ".env.example").read_bytes(), b"")
            self.assertEqual((target / "agents/templates/__init__.py").read_bytes(), b"")
            for relative in hostile_extras:
                if relative not in {".env.example", "agents/templates/__init__.py"}:
                    self.assertFalse((target / relative).exists())

    def test_trusted_agents_execution_hashes_are_exactly_pinned(self) -> None:
        committed = self.trusted_snapshot()["files"]
        source_lock = json.loads(
            committed["launch/source-lock.v3.json"].decode("utf-8")
        )
        agents = next(
            row
            for row in source_lock["official_software"]
            if row["repository"] == "arcprize/ARC-AGI-3-Agents"
        )
        agents["inspected_file_bindings"]["main.py"]["sha256"] = "0" * 64
        altered = dict(committed)
        altered["launch/source-lock.v3.json"] = json.dumps(source_lock).encode("utf-8")
        with self.assertRaisesRegex(VERIFY.CandidateError, "file hashes"):
            VERIFY.inspect_trusted_contracts(altered)

    def test_symlinked_candidate_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            original = output / "submission.ipynb"
            target = output / "submission.real"
            original.replace(target)
            try:
                original.symlink_to(target.name)
            except OSError as exc:
                self.skipTest(f"symlinks are unavailable in this test environment: {exc}")
            with self.assertRaises((OSError, VERIFY.CandidateError)):
                self.verify_fixture(output, materialize=False)

    def test_builder_rejects_unaddressed_output_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            output.mkdir()
            (output / "unaddressed.txt").write_text("not a candidate", encoding="utf-8")
            with self.assertRaisesRegex(BUILD.BuildError, "empty or contain exactly"):
                self.build_fixture(output)

    def test_builder_detects_parent_rebind_while_using_held_output_fd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "parent"
            parent.mkdir()
            output = parent / "build"
            committed = {
                relative: (ROOT / relative).read_bytes()
                for relative in VERIFY.TRUSTED_INPUT_PATHS
            }
            original_write = BUILD._atomic_write_at
            moved = Path(temporary) / "moved-parent"
            sabotaged = False

            def rebind_after_first_write(directory_fd: int, name: str, data: bytes) -> None:
                nonlocal sabotaged
                original_write(directory_fd, name, data)
                if not sabotaged:
                    sabotaged = True
                    parent.rename(moved)
                    parent.mkdir()
                    (parent / "build").mkdir()

            with mock.patch.object(
                BUILD, "git_identity", return_value=dict(self.CLEAN_IDENTITY)
            ), mock.patch.object(
                BUILD, "_git_blob", side_effect=lambda _commit, relative: committed[relative]
            ), mock.patch.object(
                BUILD, "_atomic_write_at", side_effect=rebind_after_first_write
            ):
                with self.assertRaisesRegex(BUILD.BuildError, "path changed"):
                    BUILD.build(output, "fixture-user", "cpu")
            self.assertTrue((moved / "build" / "candidate-manifest.json").is_file())
            self.assertFalse((parent / "build" / "candidate-manifest.json").exists())

    def test_builder_detects_same_bytes_file_swap_during_closed_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            detached = Path(temporary) / "detached-manifest.json"
            committed = {
                relative: (ROOT / relative).read_bytes()
                for relative in VERIFY.TRUSTED_INPUT_PATHS
            }
            original_read = BUILD._read_file_with_identity_at
            sabotaged = False

            def swap_after_read(directory_fd: int, name: str):
                nonlocal sabotaged
                data, identity = original_read(directory_fd, name)
                if name == "candidate-manifest.json" and not sabotaged:
                    sabotaged = True
                    (output / name).rename(detached)
                    (output / name).write_bytes(data)
                return data, identity

            with mock.patch.object(
                BUILD, "git_identity", return_value=dict(self.CLEAN_IDENTITY)
            ), mock.patch.object(
                BUILD, "_git_blob", side_effect=lambda _commit, relative: committed[relative]
            ), mock.patch.object(
                BUILD,
                "_read_file_with_identity_at",
                side_effect=swap_after_read,
            ):
                with self.assertRaisesRegex(BUILD.BuildError, "closed snapshot"):
                    BUILD.build(output, "fixture-user", "cpu")

    def test_verifier_detects_build_path_rebind_after_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            moved = Path(temporary) / "detached-build"
            original_materialize = VERIFY._materialize_snapshot_at

            def rebind_build(*args: object, **kwargs: object):
                result = original_materialize(*args, **kwargs)
                output.rename(moved)
                output.mkdir()
                for name in VERIFY.BUILD_FILES:
                    (output / name).write_bytes((moved / name).read_bytes())
                return result

            with mock.patch.object(
                VERIFY, "_materialize_snapshot_at", side_effect=rebind_build
            ):
                with self.assertRaisesRegex(VERIFY.CandidateError, "path changed"):
                    self.verify_fixture(output)

    def test_verifier_detects_same_bytes_sibling_swap_during_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            detached = Path(temporary) / "detached-manifest.json"
            original_read = VERIFY._read_file_with_identity_at
            sabotaged = False

            def swap_after_read(directory_fd: int, name: str, label: str):
                nonlocal sabotaged
                data, identity = original_read(directory_fd, name, label)
                if name == "candidate-manifest.json" and not sabotaged:
                    sabotaged = True
                    (output / name).rename(detached)
                    (output / name).write_bytes(data)
                return data, identity

            with mock.patch.object(
                VERIFY,
                "_read_file_with_identity_at",
                side_effect=swap_after_read,
            ):
                with self.assertRaisesRegex(VERIFY.CandidateError, "closed snapshot"):
                    self.verify_fixture(output, materialize=False)

    def test_verifier_detects_nested_snapshot_rebind_even_with_same_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            detached = Path(temporary) / "detached-snapshot"
            original_materialize = VERIFY._materialize_snapshot_at

            def rebind_snapshot(*args: object, **kwargs: object):
                path, binding = original_materialize(*args, **kwargs)
                target = Path(path)
                target.chmod(0o700)
                target.rename(detached)
                target.mkdir()
                for name in VERIFY.BUILD_FILES:
                    (target / name).write_bytes((detached / name).read_bytes())
                return path, binding

            with mock.patch.object(
                VERIFY, "_materialize_snapshot_at", side_effect=rebind_snapshot
            ):
                with self.assertRaisesRegex(VERIFY.CandidateError, "entry changed"):
                    self.verify_fixture(output)

    def test_snapshot_and_build_inventories_are_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            (output / "extra.txt").write_text("unaddressed", encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.CandidateError, "unaddressed files"):
                self.verify_fixture(output, materialize=False)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            result = self.verify_fixture(output)
            target = Path(result["verified_snapshot"]["path"])
            target.chmod(0o700)
            (target / "extra.txt").write_text("unaddressed", encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.CandidateError, "unaddressed files"):
                self.verify_fixture(output)

    def test_canonical_receipt_is_create_only_idempotent_and_collision_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            receipt = output / "verification.json"
            result = self.verify_fixture(output, receipt=receipt)
            self.assertEqual(
                json.loads(receipt.read_text(encoding="utf-8")),
                result,
            )
            self.assertEqual(self.verify_fixture(output, receipt=receipt), result)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            receipt = output / "verification.json"
            receipt.write_text('{"attacker":true}\n', encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.CandidateError, "receipt differs"):
                self.verify_fixture(output, receipt=receipt)

    def test_receipt_must_be_canonical_and_never_follow_a_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            with self.assertRaisesRegex(VERIFY.CandidateError, "canonical"):
                self.verify_fixture(
                    output,
                    receipt=Path(temporary) / "outside.json",
                )

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            outside = Path(temporary) / "outside.json"
            outside.write_text("do not replace", encoding="utf-8")
            try:
                (output / "verification.json").symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks are unavailable in this test environment: {exc}")
            with self.assertRaises((OSError, VERIFY.CandidateError)):
                self.verify_fixture(
                    output,
                    receipt=output / "verification.json",
                )
            self.assertEqual(outside.read_text(encoding="utf-8"), "do not replace")

    def test_receipt_same_bytes_rebind_is_detected_by_inode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            receipt = output / "verification.json"
            detached = Path(temporary) / "detached-receipt.json"
            original_write = VERIFY._write_verification_receipt_at

            def rebind_receipt(build_fd: int, data: bytes):
                binding = original_write(build_fd, data)
                receipt.rename(detached)
                receipt.write_bytes(detached.read_bytes())
                return binding

            with mock.patch.object(
                VERIFY,
                "_write_verification_receipt_at",
                side_effect=rebind_receipt,
            ):
                with self.assertRaisesRegex(
                    VERIFY.CandidateError, "receipt entry changed"
                ):
                    self.verify_fixture(output, receipt=receipt)

    def test_real_dirty_measurement_fails_before_candidate_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "build"
            self.build_fixture(output)
            with mock.patch.object(
                VERIFY,
                "trusted_git_snapshot",
                side_effect=VERIFY.CandidateError("current worktree is dirty"),
            ):
                with self.assertRaisesRegex(VERIFY.CandidateError, "current worktree is dirty"):
                    VERIFY.verify(output, require_clean=True)

    def test_exact_pinned_official_starter_projects_to_frozen_contract(self) -> None:
        contract = json.loads(
            (ROOT / "launch/contracts/official-starter-eeb153.contract.json").read_text(encoding="utf-8")
        )
        if not OFFICIAL_STARTER.exists():
            self.skipTest("exact upstream checkout is not present in this clone")
        script = OFFICIAL_STARTER / "scripts/build_notebook.py"
        self.assertEqual(hashlib.sha256(script.read_bytes()).hexdigest(), contract["source"]["build_script_sha256"])
        official = load_module("arc3_exact_official_builder_test", script)
        self.assertEqual(VERIFY.project_starter_surface(official.build()), contract["projection"])

    def test_builder_has_no_long_exact_starter_source_block(self) -> None:
        if not OFFICIAL_STARTER.exists():
            self.skipTest("exact upstream checkout is not present in this clone")
        import difflib
        ours = (ROOT / "scripts/build_notebook.py").read_text(encoding="utf-8").splitlines()
        upstream = (OFFICIAL_STARTER / "scripts/build_notebook.py").read_text(encoding="utf-8").splitlines()
        matches = difflib.SequenceMatcher(a=upstream, b=ours, autojunk=False).get_matching_blocks()
        self.assertFalse([match for match in matches if match.size >= 5])


if __name__ == "__main__":
    unittest.main()
