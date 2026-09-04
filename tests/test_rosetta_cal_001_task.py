from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from calibration import rosetta_cal_001_task as calibration


TEST_SALT = bytes(range(32))
FIXTURE_CASES = [
    {"input": "aB\n", "output": "ab\n"},
    {"input": "ABc\n", "output": "ABC\n"},
    {"input": "xyz\n", "output": "xyz\n"},
]


def fixture_row() -> dict[str, object]:
    return {
        "question_id": calibration.TASK_ID,
        "question_title": "Synthetic fixture title",
        "question_content": "Synthetic fixture statement.",
        "all_tests": json.dumps(FIXTURE_CASES),
        "private_test_cases": "MUST_NOT_REACH_PROMPT",
    }


def fixture_material() -> tuple[
    calibration.TaskView,
    calibration.TestView,
    calibration.DatasetBinding,
]:
    task, tests = calibration.split_target_material([fixture_row()])
    binding = calibration.DatasetBinding(
        path="UNIT_TEST_ATTACHED_PARQUET",
        attached_file_bytes=1234,
        selected_row_count=1,
        current_version=1,
    )
    return task, tests, binding


class FakeRunner:
    def __init__(self, mode: str = "pass") -> None:
        self.mode = mode
        self.calls = 0

    def __call__(
        self, program: str, case: calibration.TestCase
    ) -> calibration.CaseObservation:
        self.calls += 1
        if self.mode == "pass":
            return calibration.CaseObservation(0, case.expected_stdout, len(case.expected_stdout), 0)
        if self.mode == "wrong":
            return calibration.CaseObservation(0, "not-the-answer\n", 15, 0)
        if self.mode == "runtime":
            return calibration.CaseObservation(1, "", 0, 12)
        if self.mode == "timeout":
            return calibration.CaseObservation(None, "", 0, 0, timed_out=True)
        raise RuntimeError("safe synthetic runner failure")


class DialectAndGlossTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dialect = calibration.create_dialect(TEST_SALT, domain="unit-test-domain")
        self.pairs = calibration.make_program_pairs(self.dialect)
        self.ledger = calibration.GlossLedger.from_pairs(self.pairs)

    def test_mapping_roundtrip_preserves_python_ast(self) -> None:
        program = (
            "text = input()\n"
            "count = 0\n"
            "for char in text:\n"
            "    if char == char.lower():\n"
            "        count = count + 1\n"
            "print(chr(ord(text[0]) - 1))\n"
        )
        synthetic = self.dialect.to_synthetic(program)
        restored = self.dialect.to_python(synthetic)
        self.assertEqual(
            ast.dump(ast.parse(program), include_attributes=False),
            ast.dump(ast.parse(restored), include_attributes=False),
        )
        self.assertNotIn("print", synthetic.split())
        self.assertNotIn("upper", self.dialect.forward)

    def test_frozen_production_domain_and_salt_are_deterministic(self) -> None:
        first = calibration.create_dialect()
        second = calibration.create_dialect()
        self.assertEqual(first.mapping_sha256, second.mapping_sha256)
        self.assertEqual(first.forward, second.forward)
        self.assertEqual(first.domain, calibration.DIALECT_DOMAIN)
        self.assertEqual(len(calibration.DIALECT_SALT_HEX), 64)
        self.assertNotEqual(calibration.DIALECT_SALT, TEST_SALT)

    def test_six_pairs_earn_lower_but_not_upper(self) -> None:
        self.assertEqual(len(self.pairs), 6)
        self.assertTrue(self.ledger.supports("lower"))
        self.assertFalse(self.ledger.supports("upper"))
        rendered = self.ledger.render("word = input()\nprint(word.lower())\n")
        self.assertEqual(
            ast.dump(ast.parse(self.dialect.to_python(rendered)), include_attributes=False),
            ast.dump(ast.parse("word = input()\nprint(word.lower())\n"), include_attributes=False),
        )
        with self.assertRaises(calibration.UnresolvedMapping) as caught:
            self.ledger.render("word = input()\nprint(word.upper())\n")
        self.assertEqual(caught.exception.tokens, ("upper",))

    def test_demonstrations_are_not_the_full_reverse_map(self) -> None:
        shown = set(self.ledger.entries)
        full = set(self.dialect.forward)
        self.assertLess(shown, full)
        self.assertNotIn("upper", shown)
        self.assertNotIn("upper", full)


class RowBoundaryTests(unittest.TestCase):
    def test_exact_filter_precedes_disjoint_prompt_and_test_views(self) -> None:
        rows = [
            {
                "question_id": "different_task",
                "question_title": "do not read",
                "question_content": "OTHER_ROW_SECRET",
                "all_tests": "OTHER_TEST_SECRET",
            },
            fixture_row(),
        ]
        task, tests = calibration.split_target_material(rows)
        dialect = calibration.create_dialect(TEST_SALT)
        pairs = calibration.make_program_pairs(dialect)
        ledger = calibration.GlossLedger.from_pairs(pairs)
        messages = calibration.build_messages(calibration.CELLS[1], task, pairs, ledger)
        rendered = json.dumps(messages)
        self.assertEqual(task.question_id, calibration.TASK_ID)
        self.assertEqual(tests.question_id, calibration.TASK_ID)
        self.assertEqual(len(tests.cases), len(FIXTURE_CASES))
        self.assertRegex(tests.tests_sha256, r"^[0-9a-f]{64}$")
        self.assertNotIn("OTHER_ROW_SECRET", rendered)
        self.assertNotIn("OTHER_TEST_SECRET", rendered)
        self.assertNotIn("MUST_NOT_REACH_PROMPT", rendered)
        for case in FIXTURE_CASES:
            self.assertNotIn(case["input"], rendered)

    def test_test_parser_accepts_list_and_json_but_rejects_malformed_rows(self) -> None:
        as_list = fixture_row()
        as_list["all_tests"] = FIXTURE_CASES
        _, list_view = calibration.split_target_material([as_list])
        _, json_view = calibration.split_target_material([fixture_row()])
        self.assertEqual(list_view.tests_sha256, json_view.tests_sha256)

        malformed = fixture_row()
        malformed["all_tests"] = [{"input": "missing output"}]
        with self.assertRaises(calibration.RowFilterError):
            calibration.split_target_material([malformed])

    def test_filter_rejects_missing_duplicate_and_inexact_ids(self) -> None:
        valid = fixture_row()
        with self.assertRaises(calibration.RowFilterError):
            calibration.filter_target_row([])
        with self.assertRaises(calibration.RowFilterError):
            calibration.filter_target_row([valid, dict(valid)])
        with self.assertRaises(calibration.RowFilterError):
            calibration.filter_target_row(
                [{**valid, "question_id": f" {calibration.TASK_ID}"}]
            )

    def test_prompt_builder_requires_filtered_task_view(self) -> None:
        dialect = calibration.create_dialect(TEST_SALT)
        pairs = calibration.make_program_pairs(dialect)
        ledger = calibration.GlossLedger.from_pairs(pairs)
        with self.assertRaises(TypeError):
            calibration.build_messages(  # type: ignore[arg-type]
                calibration.CELLS[0],
                fixture_row(),
                pairs,
                ledger,
            )


class OutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dialect = calibration.create_dialect(TEST_SALT)
        _, self.tests, _ = fixture_material()

    def evaluate(
        self,
        output: str,
        *,
        task_form: str = "PYTHON",
        runner: FakeRunner | None = None,
    ) -> calibration.EvaluationResult:
        return calibration.evaluate_output(
            output,
            task_form=task_form,
            dialect=self.dialect,
            tests=self.tests,
            case_runner=runner or FakeRunner(),
        )

    def test_no_code_and_python_leak(self) -> None:
        self.assertEqual(self.evaluate("plain prose").outcome, calibration.Outcome.NO_CODE)
        leaked = self.evaluate(
            "<solution>print('leak')</solution>", task_form="CORE"
        )
        self.assertEqual(leaked.outcome, calibration.Outcome.PYTHON_LEAK)
        self.assertGreater(leaked.python_leak_count, 0)

    def test_syntax_pass_wrong_runtime_and_timeout(self) -> None:
        syntax = self.evaluate("<solution>if :</solution>")
        self.assertEqual(syntax.outcome, calibration.Outcome.SYNTAX_ERROR)

        safe_program = "<solution>value = input()\nprint(value)</solution>"
        self.assertEqual(
            self.evaluate(safe_program, runner=FakeRunner("pass")).outcome,
            calibration.Outcome.PASS,
        )
        self.assertEqual(
            self.evaluate(safe_program, runner=FakeRunner("wrong")).outcome,
            calibration.Outcome.WRONG_ANSWER,
        )
        self.assertEqual(
            self.evaluate(safe_program, runner=FakeRunner("runtime")).outcome,
            calibration.Outcome.RUNTIME_ERROR,
        )
        timeout = self.evaluate(safe_program, runner=FakeRunner("timeout"))
        self.assertEqual(timeout.outcome, calibration.Outcome.RUNTIME_ERROR)
        self.assertEqual(timeout.disposition, calibration.Disposition.TIMEOUT)

    def test_valid_synthetic_fixture_reaches_safe_runner(self) -> None:
        python_program = "value = input()\nprint(value.lower())\n"
        synthetic = self.dialect.to_synthetic(python_program)
        runner = FakeRunner("pass")
        result = self.evaluate(
            f"<solution>{synthetic}</solution>", task_form="CORE", runner=runner
        )
        self.assertEqual(result.outcome, calibration.Outcome.PASS)
        self.assertEqual(runner.calls, len(FIXTURE_CASES))


class BudgetAndReceiptTests(unittest.TestCase):
    def test_four_semantic_cells_use_frozen_call_settings(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_model(**kwargs: object) -> str:
            calls.append(kwargs)
            return "no program in this orientation fixture"

        task, tests, binding = fixture_material()
        receipt = calibration.run_calibration(
            fake_model,
            task=task,
            tests=tests,
            dataset_binding=binding,
            actor_model="gpt-5.6-terra",
            sdk_version="0.6.1",
            dialect=calibration.create_dialect(TEST_SALT),
            case_runner=FakeRunner(),
        )
        expected_ids = [
            "CAL01_BARE_PYTHON",
            "CAL02_BARE_CORE",
            "CAL03_HEARTHLINE_CORE",
            "CAL04_HEARTHLINE_TASK_GLOSS_CORE",
        ]
        self.assertEqual([cell.cell_id for cell in calibration.CELLS], expected_ids)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(receipt["cells"]), 4)
        self.assertEqual(receipt["call_policy"]["maximum_calls"], 4)  # type: ignore[index]
        self.assertEqual(receipt["call_policy"]["actual_calls"], 4)  # type: ignore[index]
        for index, call in enumerate(calls):
            self.assertEqual(call["cell_id"], expected_ids[index])
            self.assertEqual(call["reasoning"], "low")
            self.assertEqual(call["extra_api_params"], {"max_completion_tokens": 2048})
            messages = call["messages"]
            self.assertEqual(len(messages), 2)  # type: ignore[arg-type]
        self.assertEqual(len({id(call["messages"]) for call in calls}), 4)

    def test_infrastructure_failure_aborts_later_cells_without_calls(self) -> None:
        calls = 0

        def failed_model(**_kwargs: object) -> str:
            nonlocal calls
            calls += 1
            raise RuntimeError("synthetic provider failure")

        task, tests, binding = fixture_material()
        receipt = calibration.run_calibration(
            failed_model,
            task=task,
            tests=tests,
            dataset_binding=binding,
            actor_model="gpt-5.6-terra",
            sdk_version="0.6.1",
            dialect=calibration.create_dialect(TEST_SALT),
            case_runner=FakeRunner(),
        )
        self.assertEqual(calls, 1)
        self.assertEqual(receipt["call_policy"]["actual_calls"], 1)  # type: ignore[index]
        cells = receipt["cells"]
        self.assertEqual(cells[0]["disposition"], calibration.Disposition.INFRASTRUCTURE_FAILURE)
        self.assertTrue(
            all(cell["disposition"] == calibration.Disposition.NOT_RUN for cell in cells[1:])
        )
        self.assertTrue(all(cell["attempts"] == 0 for cell in cells[1:]))

    def test_evaluator_infrastructure_failure_also_aborts(self) -> None:
        calls = 0

        def valid_model(**_kwargs: object) -> str:
            nonlocal calls
            calls += 1
            return "<solution>value = input()\nprint(value)</solution>"

        task, tests, binding = fixture_material()
        receipt = calibration.run_calibration(
            valid_model,
            task=task,
            tests=tests,
            dataset_binding=binding,
            actor_model="gpt-5.6-terra",
            sdk_version="0.6.1",
            dialect=calibration.create_dialect(TEST_SALT),
            case_runner=FakeRunner("infrastructure"),
        )
        self.assertEqual(calls, 1)
        self.assertEqual(
            receipt["cells"][0]["disposition"],  # type: ignore[index]
            calibration.Disposition.INFRASTRUCTURE_FAILURE,
        )
        self.assertTrue(
            all(
                cell["disposition"] == calibration.Disposition.NOT_RUN
                for cell in receipt["cells"][1:]  # type: ignore[index]
            )
        )

    def test_call_budget_fails_before_a_fifth_invocation(self) -> None:
        calls = 0

        def fake_model(**_kwargs: object) -> str:
            nonlocal calls
            calls += 1
            return "none"

        budget = calibration.CallBudget(fake_model)
        messages = ({"role": "user", "content": "fixture"},)
        for index in range(4):
            budget.invoke(f"cell-{index}", messages)
        with self.assertRaises(calibration.CallBudgetExceeded):
            budget.invoke("cell-5", messages)
        self.assertEqual(calls, 4)

    def test_receipt_has_hashes_runtime_dataset_gloss_and_no_raw_tests(self) -> None:
        def fake_model(**_kwargs: object) -> calibration.ModelReply:
            return calibration.ModelReply(
                "<solution>value = input()\nprint(value)</solution>",
                {
                    "input_tokens": 10,
                    "output_tokens": 7,
                    "total_backend_latency_ms": 12,
                },
            )

        task, tests, binding = fixture_material()
        receipt = calibration.run_calibration(
            fake_model,
            task=task,
            tests=tests,
            dataset_binding=binding,
            actor_model="gpt-5.6-terra",
            sdk_version="0.6.1+source",
            dialect=calibration.create_dialect(TEST_SALT),
            case_runner=FakeRunner("pass"),
        )
        self.assertEqual(receipt["result_label"], "ROSETTA_DERIVED_FRESH_SALT")
        self.assertFalse(receipt["public_score"])
        for cell in receipt["cells"]:  # type: ignore[assignment]
            self.assertRegex(cell["output_sha256"], r"^[0-9a-f]{64}$")
            self.assertIn("telemetry", cell)
        self.assertEqual(receipt["runtime"]["actor_model"], "gpt-5.6-terra")  # type: ignore[index]
        self.assertEqual(
            receipt["runtime"]["kaggle_benchmarks_version"],  # type: ignore[index]
            "0.6.1+source",
        )
        self.assertEqual(receipt["dataset"]["expected"]["version"], 1)  # type: ignore[index]
        self.assertEqual(receipt["dataset"]["current"]["version"], 1)  # type: ignore[index]
        self.assertEqual(receipt["dataset"]["current"]["selected_row_count"], 1)  # type: ignore[index]
        gloss = receipt["gloss"]
        supported = {entry["python_lexeme"] for entry in gloss["supported"]}  # type: ignore[index]
        self.assertIn("lower", supported)
        self.assertNotIn("upper", supported)
        self.assertEqual(
            gloss["unresolved"],  # type: ignore[index]
            [{"python_lexeme": "upper", "status": "UNRESOLVED"}],
        )
        encoded = json.dumps(receipt, sort_keys=True)
        for case in FIXTURE_CASES:
            self.assertNotIn(case["input"], encoded)
            self.assertNotIn(case["output"], encoded)
        self.assertNotIn("expected_stdout", encoded)
        self.assertTrue(receipt["evaluator"]["raw_tests_in_receipt"] is False)  # type: ignore[index]


class HostedSdkBoundaryTests(unittest.TestCase):
    def test_injected_actor_exact_prompt_api_and_fresh_chat_per_cell(self) -> None:
        task_view, test_view, binding = fixture_material()
        loaded = calibration.LoadedCalibrationData(task_view, test_view, binding)
        chat_names: list[str] = []
        prompt_calls: list[tuple[str, dict[str, object]]] = []

        class FakeChat:
            usage = types.SimpleNamespace(
                input_tokens=11,
                output_tokens=3,
                input_tokens_cost_nanodollars=5,
                output_tokens_cost_nanodollars=7,
                total_cost_nanodollars=12,
                total_backend_latency_ms=9,
            )

            def __enter__(self) -> FakeChat:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        class FakeChats:
            def new(self, name: str) -> FakeChat:
                chat_names.append(name)
                return FakeChat()

        class FakeLlm:
            model = "gpt-5.6-terra"

            def prompt(self, message: str, **kwargs: object) -> str:
                prompt_calls.append((message, kwargs))
                return "fixture prose without code"

        def task_decorator(*, name: str):
            self.assertEqual(name, "Hearthline Rosetta CAL 001 abc357b")

            def decorate(function):
                self.assertIs(function.__annotations__["return"], dict)
                return function

            return decorate

        fake_sdk = types.SimpleNamespace(task=task_decorator, chats=FakeChats())
        with (
            patch.dict(sys.modules, {"kaggle_benchmarks": fake_sdk}),
            patch.object(calibration, "require_kaggle_kernel"),
            patch.object(calibration, "load_attached_calibration_data", return_value=loaded),
        ):
            task_function = calibration.build_kaggle_task()
            receipt = task_function(FakeLlm())

        expected_ids = [cell.cell_id for cell in calibration.CELLS]
        self.assertEqual(chat_names, expected_ids)
        self.assertEqual(len(prompt_calls), 4)
        for message, kwargs in prompt_calls:
            self.assertIn("<SYSTEM>", message)
            self.assertEqual(
                kwargs,
                {
                    "reasoning": "low",
                    "extra_api_params": {"max_completion_tokens": 2048},
                },
            )
        self.assertEqual(receipt["call_policy"]["model"], "gpt-5.6-terra")  # type: ignore[index]
        self.assertEqual(receipt["runtime"]["actor_model"], "gpt-5.6-terra")  # type: ignore[index]

    def test_hosted_task_rejects_wrong_actor_before_loading_data(self) -> None:
        loaded = False

        class WrongLlm:
            model = "gpt-5.6-luna"

        def load_data() -> None:
            nonlocal loaded
            loaded = True

        def task_decorator(*, name: str):
            del name
            return lambda function: function

        fake_sdk = types.SimpleNamespace(task=task_decorator)
        with (
            patch.dict(sys.modules, {"kaggle_benchmarks": fake_sdk}),
            patch.object(calibration, "require_kaggle_kernel"),
            patch.object(calibration, "load_attached_calibration_data", side_effect=load_data),
        ):
            task_function = calibration.build_kaggle_task()
            with self.assertRaisesRegex(calibration.CalibrationError, "frozen gpt-5.6-terra"):
                task_function(WrongLlm())

        self.assertFalse(loaded)

    def test_task_creation_placeholder_is_allowed_without_a_model_call(self) -> None:
        task_view, test_view, binding = fixture_material()
        loaded = calibration.LoadedCalibrationData(task_view, test_view, binding)

        class FakeChat:
            usage = types.SimpleNamespace()

            def __enter__(self) -> FakeChat:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        class FakeChats:
            def new(self, _name: str) -> FakeChat:
                return FakeChat()

        class BuildPlaceholder:
            name = "llm"

            def prompt(self, _message: str, **_kwargs: object) -> str:
                raise RuntimeError("model proxy is intentionally absent during task creation")

        def task_decorator(*, name: str):
            del name
            return lambda function: function

        fake_sdk = types.SimpleNamespace(task=task_decorator, chats=FakeChats())
        with (
            patch.dict(sys.modules, {"kaggle_benchmarks": fake_sdk}),
            patch.object(calibration, "require_kaggle_kernel"),
            patch.object(calibration, "load_attached_calibration_data", return_value=loaded),
        ):
            receipt = calibration.build_kaggle_task()(BuildPlaceholder())

        self.assertIsNone(receipt["call_policy"]["model"])  # type: ignore[index]
        self.assertEqual(receipt["call_policy"]["actual_calls"], 1)  # type: ignore[index]
        self.assertEqual(
            receipt["cells"][0]["disposition"],  # type: ignore[index]
            calibration.Disposition.INFRASTRUCTURE_FAILURE,
        )


class ImportBoundaryTests(unittest.TestCase):
    def test_import_does_not_import_sdk_load_data_or_run_task(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "sdk-imported.txt"
            fake_sdk = root / "kaggle_benchmarks.py"
            fake_sdk.write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join((str(root), str(project_root)))
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import calibration.rosetta_cal_001_task; print('import-only')",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), "import-only")
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
