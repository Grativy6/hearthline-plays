from __future__ import annotations

import ast
import copy
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "morrow_queue.py"
SPEC = importlib.util.spec_from_file_location("morrow_queue", TOOL_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import setup guard
    raise RuntimeError("unable to load Morrow tool")
morrow_queue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(morrow_queue)


def scheduling_view() -> dict[str, object]:
    return {
        "schema": "hearthline-plays.morrow-scheduling-view.v1",
        "status": "CONTROLLER_FROZEN_READY_ONLY_VIEW",
        "invocation_cut_binding": "opaque-cut.test-0001",
        "policy_ref": "STABLE_EFFECTIVE_PRIORITY_THEN_APPROVED_COST_THEN_ARRIVAL_V2",
        "maximum_overtakes": 2,
        "ready_scheduling_view": [
            {
                "opaque_queue_item_binding": "opaque-item.old",
                "ready_arrival_rank": 1,
                "effective_priority_rank": 2,
                "controller_approved_processing_cost": 10,
                "overtake_count": 2,
            },
            {
                "opaque_queue_item_binding": "opaque-item.second-due",
                "ready_arrival_rank": 2,
                "effective_priority_rank": 3,
                "controller_approved_processing_cost": 20,
                "overtake_count": 2,
            },
            {
                "opaque_queue_item_binding": "opaque-item.urgent",
                "ready_arrival_rank": 3,
                "effective_priority_rank": 0,
                "controller_approved_processing_cost": 5,
                "overtake_count": 0,
            },
            {
                "opaque_queue_item_binding": "opaque-item.cheap-routine",
                "ready_arrival_rank": 4,
                "effective_priority_rank": 2,
                "controller_approved_processing_cost": 1,
                "overtake_count": 0,
            },
        ],
    }


class MorrowQueueTests(unittest.TestCase):
    def run_cli(self, raw: str) -> tuple[int, str, str]:
        stdin = io.StringIO(raw)
        stdout = io.StringIO()
        stderr = io.StringIO()
        original_streams = (
            morrow_queue.sys.stdin,
            morrow_queue.sys.stdout,
            morrow_queue.sys.stderr,
        )
        try:
            morrow_queue.sys.stdin = stdin
            morrow_queue.sys.stdout = stdout
            morrow_queue.sys.stderr = stderr
            return_code = morrow_queue.main()
        finally:
            (
                morrow_queue.sys.stdin,
                morrow_queue.sys.stdout,
                morrow_queue.sys.stderr,
            ) = original_streams
        return return_code, stdout.getvalue(), stderr.getvalue()

    def test_pure_proposal_has_stable_due_prefix_then_priority_cost_order(self) -> None:
        proposal = morrow_queue.propose(scheduling_view())
        self.assertEqual(
            [
                "opaque-item.old",
                "opaque-item.second-due",
                "opaque-item.urgent",
                "opaque-item.cheap-routine",
            ],
            proposal["ready_order"],
        )
        self.assertTrue(proposal["deterministic_stateless"])
        self.assertIsNone(proposal["persistent_state_ref"])
        self.assertEqual(0, proposal["external_effect_count"])

    def test_same_input_produces_byte_identical_output(self) -> None:
        raw = json.dumps(scheduling_view(), sort_keys=True)
        first = self.run_cli(raw)
        different = scheduling_view()
        different["ready_scheduling_view"][0]["overtake_count"] = 1
        morrow_queue.propose(different)
        second = self.run_cli(raw)
        self.assertEqual(0, first[0])
        self.assertEqual(first[1], second[1])
        self.assertEqual("", first[2])
        self.assertEqual(
            morrow_queue.propose(scheduling_view()),
            morrow_queue.propose(scheduling_view()),
        )

    def test_published_example_pair_is_exact_executable_output(self) -> None:
        view = json.loads(
            (ROOT / "examples" / "morrow-scheduling-view.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        expected = json.loads(
            (ROOT / "examples" / "morrow-proposal.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(expected, morrow_queue.propose(view))
        result = self.run_cli(json.dumps(view, sort_keys=True, separators=(",", ":")))
        self.assertEqual(0, result[0])
        self.assertEqual(
            (ROOT / "examples" / "morrow-proposal.synthetic.json").read_text(encoding="utf-8"),
            result[1],
        )

    def test_digest_binds_exact_closed_ready_view(self) -> None:
        document = scheduling_view()
        proposal = morrow_queue.propose(document)
        self.assertEqual(
            morrow_queue.canonical_sha256(document),
            proposal["scheduling_view_sha256"],
        )
        changed = copy.deepcopy(document)
        changed["ready_scheduling_view"][0]["overtake_count"] = 1
        self.assertNotEqual(
            proposal["scheduling_view_sha256"],
            morrow_queue.propose(changed)["scheduling_view_sha256"],
        )

    def test_view_rejects_thulia_carry_custody_and_hidden_identity_fields(self) -> None:
        forbidden = (
            ("thulia_ref", "THULIA"),
            ("carry_state", "CARRY:SELECTED"),
            ("homecoming_custody_state", "HOMECOMING:RETURNED"),
            ("queue_item_id", "durable-id"),
            ("priority_class", "P0_URGENT"),
        )
        for field, value in forbidden:
            with self.subTest(field=field):
                document = scheduling_view()
                document["ready_scheduling_view"][0][field] = value
                with self.assertRaisesRegex(morrow_queue.MorrowInputError, "extra"):
                    morrow_queue.propose(document)

    def test_view_requires_canonical_dense_ready_arrival_order(self) -> None:
        for mutation in ("swap", "gap", "bool"):
            with self.subTest(mutation=mutation):
                document = scheduling_view()
                if mutation == "swap":
                    document["ready_scheduling_view"][0]["ready_arrival_rank"] = 2
                    document["ready_scheduling_view"][1]["ready_arrival_rank"] = 1
                elif mutation == "gap":
                    document["ready_scheduling_view"][-1]["ready_arrival_rank"] = 5
                else:
                    document["ready_scheduling_view"][0]["ready_arrival_rank"] = True
                with self.assertRaises(morrow_queue.MorrowInputError):
                    morrow_queue.propose(document)

    def test_cut_and_item_tokens_are_typed_safe_bounded_and_disjoint(self) -> None:
        bad_values = ("", "snowman-☃", "x" * 257, "line\nbreak", "\ud800")
        for value in bad_values:
            with self.subTest(value=repr(value)):
                document = scheduling_view()
                document["invocation_cut_binding"] = value
                with self.assertRaises(morrow_queue.MorrowInputError):
                    morrow_queue.propose(document)
        document = scheduling_view()
        document["invocation_cut_binding"] = document["ready_scheduling_view"][0]["opaque_queue_item_binding"]
        with self.assertRaisesRegex(morrow_queue.MorrowInputError, "must not alias"):
            morrow_queue.propose(document)
        document = scheduling_view()
        document["invocation_cut_binding"] = document["ready_scheduling_view"][0]["opaque_queue_item_binding"].upper()
        with self.assertRaisesRegex(morrow_queue.MorrowInputError, "must not alias"):
            morrow_queue.propose(document)
        document = scheduling_view()
        document["ready_scheduling_view"][1]["opaque_queue_item_binding"] = (
            document["ready_scheduling_view"][0]["opaque_queue_item_binding"].upper()
        )
        with self.assertRaisesRegex(morrow_queue.MorrowInputError, "unique opaque binding"):
            morrow_queue.propose(document)

    def test_numeric_bounds_reject_bool_zero_and_over_maximum(self) -> None:
        mutations = (
            ("maximum_overtakes", True),
            ("maximum_overtakes", 0),
            ("maximum_overtakes", 1_000_001),
            ("controller_approved_processing_cost", True),
            ("controller_approved_processing_cost", 0),
            ("controller_approved_processing_cost", 1_000_001),
            ("effective_priority_rank", 4),
            ("overtake_count", 1_000_001),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                document = scheduling_view()
                if field == "maximum_overtakes":
                    document[field] = value
                else:
                    document["ready_scheduling_view"][0][field] = value
                with self.assertRaises(morrow_queue.MorrowInputError):
                    morrow_queue.propose(document)

    def test_ready_item_limit_accepts_256_and_rejects_257(self) -> None:
        document = scheduling_view()
        document["maximum_overtakes"] = 1_000_000
        document["ready_scheduling_view"] = [
            {
                "opaque_queue_item_binding": f"item-{index:03d}",
                "ready_arrival_rank": index,
                "effective_priority_rank": index % 4,
                "controller_approved_processing_cost": index,
                "overtake_count": 0,
            }
            for index in range(1, 257)
        ]
        self.assertEqual(256, len(morrow_queue.propose(document)["ready_order"]))
        document["ready_scheduling_view"].append({
            "opaque_queue_item_binding": "item-257",
            "ready_arrival_rank": 257,
            "effective_priority_rank": 0,
            "controller_approved_processing_cost": 1,
            "overtake_count": 0,
        })
        with self.assertRaisesRegex(morrow_queue.MorrowInputError, "bounded"):
            morrow_queue.propose(document)

    def test_cli_rejects_malformed_json_without_traceback_or_stdout(self) -> None:
        cases = (
            "null",
            "[]",
            '{"schema":"a","schema":"b"}',
            '{"number":NaN}',
            '{"number":1e9999}',
            "[" * 100_000 + "]" * 100_000,
        )
        for raw in cases:
            with self.subTest(prefix=raw[:20]):
                result = self.run_cli(raw)
                self.assertEqual(2, result[0])
                self.assertEqual("", result[1])
                self.assertIn("MORROW_INPUT_REJECTED", result[2])
                self.assertNotIn("Traceback", result[2])

    def test_cli_source_has_no_state_network_clock_subprocess_or_thulia_dependency(self) -> None:
        source = TOOL_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add((node.module or "").split(".")[0])
        self.assertEqual({"__future__", "hashlib", "json", "sys", "typing"}, imports)
        for forbidden in ("thulia", "socket", "requests", "urllib", "pathlib", "subprocess", "time", "random"):
            self.assertNotIn(forbidden, imports)
        dangerous_builtins = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {
                "open", "exec", "eval", "compile", "__import__", "input",
                "breakpoint", "getattr", "setattr", "delattr", "globals",
                "locals", "vars",
            }
        }
        self.assertEqual(set(), dangerous_builtins)
        sys_attributes = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
        }
        self.assertLessEqual(sys_attributes, {"stdin", "stdout", "stderr"})

    def test_public_schemas_match_cli_examples_and_embedded_contract(self) -> None:
        view_schema = json.loads(
            (ROOT / "schemas" / "morrow-scheduling-view.v1.schema.json").read_text(encoding="utf-8")
        )
        proposal_schema = json.loads(
            (ROOT / "schemas" / "morrow-proposal.v1.schema.json").read_text(encoding="utf-8")
        )
        queue_schema = json.loads(
            (ROOT / "schemas" / "return-queue.v2.schema.json").read_text(encoding="utf-8")
        )
        fixture = json.loads(
            (ROOT / "fixtures" / "return-queue.synthetic.json").read_text(encoding="utf-8")
        )
        view = json.loads(
            (ROOT / "examples" / "morrow-scheduling-view.synthetic.json").read_text(encoding="utf-8")
        )
        proposal = morrow_queue.propose(view)

        self.assertEqual(set(view), set(view_schema["required"]))
        self.assertEqual(set(view), set(view_schema["properties"]))
        self.assertEqual(view["schema"], view_schema["properties"]["schema"]["const"])
        self.assertEqual(view["status"], view_schema["properties"]["status"]["const"])
        self.assertEqual(morrow_queue.POLICY_REF, view_schema["properties"]["policy_ref"]["const"])
        self.assertEqual(morrow_queue.MAX_OVERTAKES, view_schema["properties"]["maximum_overtakes"]["maximum"])
        ready_schema = view_schema["properties"]["ready_scheduling_view"]
        self.assertEqual(morrow_queue.MAX_READY_ITEMS, ready_schema["maxItems"])
        item_schema = view_schema["$defs"]["item"]
        self.assertEqual(set(view["ready_scheduling_view"][0]), set(item_schema["required"]))
        self.assertEqual(set(item_schema["required"]), set(item_schema["properties"]))
        self.assertEqual(
            morrow_queue.MAX_CONTROLLER_APPROVED_PROCESSING_COST,
            item_schema["properties"]["controller_approved_processing_cost"]["maximum"],
        )
        self.assertEqual(
            morrow_queue.MAX_OPAQUE_TOKEN_CHARACTERS,
            view_schema["$defs"]["opaqueToken"]["maxLength"],
        )

        self.assertEqual(set(proposal), set(proposal_schema["required"]))
        self.assertEqual(set(proposal), set(proposal_schema["properties"]))
        embedded = queue_schema["$defs"]["morrowOutput"]
        self.assertEqual(set(proposal_schema["required"]), set(embedded["required"]))
        self.assertEqual(set(proposal_schema["properties"]), set(embedded["properties"]))
        for field in ("schema", "status", "policy_ref", "reason_codes", "pure_metadata_only", "deterministic_stateless", "external_effect_count"):
            self.assertEqual(
                proposal_schema["properties"][field]["const"],
                embedded["properties"][field]["const"],
            )
        self.assertEqual(
            proposal_schema["$defs"]["opaqueToken"],
            queue_schema["$defs"]["opaqueToken"],
        )
        for field in ("invocation_cut_binding", "ready_order", "persistent_state_ref"):
            self.assertEqual(
                proposal_schema["properties"][field],
                embedded["properties"][field],
            )
        self.assertEqual(
            proposal_schema["properties"]["scheduling_view_sha256"],
            queue_schema["$defs"]["sha256"],
        )

        for definition, fixture_value in (
            ("queueSteward", fixture["queue"]["queue_steward"]),
            ("thuliaNonInterference", fixture["queue"]["thulia_non_interference"]),
            ("serviceReconciliation", fixture["service_reconciliation_receipts"][0]),
        ):
            schema = queue_schema["$defs"][definition]
            self.assertEqual(set(fixture_value), set(schema["required"]))
            self.assertEqual(set(schema["required"]), set(schema["properties"]))
            for field, field_schema in schema["properties"].items():
                if "const" in field_schema:
                    self.assertEqual(field_schema["const"], fixture_value[field])


if __name__ == "__main__":
    unittest.main()
