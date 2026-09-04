"""Synthetic-only regressions for the cleared Kaggle notebook contract."""

from __future__ import annotations

import copy
import json
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"
NOTEBOOK = ROOT / "notebook" / "arc2_submission.ipynb"
SAMPLE_MISSING = object()


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def execute_notebook(
    runtime: Path,
    sample: object = SAMPLE_MISSING,
) -> Path:
    """Execute the tracked notebook against only the synthetic fixtures."""

    challenges_path = runtime / "arc-agi_test_challenges.json"
    sample_path = runtime / "sample_submission.json"
    output_path = runtime / "submission.json"
    challenges_path.write_bytes((FIXTURES / "challenges.json").read_bytes())
    if sample is not SAMPLE_MISSING:
        sample_path.write_text(
            json.dumps(sample, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    notebook = load_json(NOTEBOOK)
    assert isinstance(notebook, dict)
    code_cells = [
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ]
    namespace: dict[str, object] = {}
    exec(compile(code_cells[0], str(NOTEBOOK), "exec"), namespace)
    namespace.update(
        {
            "CHALLENGES_PATH": challenges_path,
            "SAMPLE_PATH": sample_path,
            "OUTPUT_PATH": output_path,
            "DEADLINE": time.monotonic() + 60,
        }
    )
    for source in code_cells[1:]:
        exec(compile(source, str(NOTEBOOK), "exec"), namespace)
    return output_path


class NotebookContractTests(unittest.TestCase):
    def test_sample_submission_is_mandatory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            with self.assertRaisesRegex(
                FileNotFoundError,
                "required sample_submission.json is missing",
            ):
                execute_notebook(runtime)
            self.assertFalse((runtime / "submission.json").exists())

    def test_sample_submission_rejects_missing_and_extra_tasks(self) -> None:
        baseline = load_json(FIXTURES / "submission.json")
        assert isinstance(baseline, dict)
        missing = copy.deepcopy(baseline)
        missing.pop(next(iter(missing)))
        extra = copy.deepcopy(baseline)
        extra["deadbeef"] = copy.deepcopy(next(iter(extra.values())))

        for case, sample in (("missing", missing), ("extra", extra)):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(
                    ValueError,
                    "submission task coverage mismatch",
                ):
                    execute_notebook(Path(directory), sample)

    def test_sample_submission_rejects_mismatched_test_input_count(self) -> None:
        sample = load_json(FIXTURES / "submission.json")
        assert isinstance(sample, dict)
        task_id = next(iter(sample))
        assert isinstance(sample[task_id], list)
        sample[task_id] = sample[task_id][:-1]

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ValueError,
                "submission test-input coverage mismatch",
            ):
                execute_notebook(Path(directory), sample)


if __name__ == "__main__":
    unittest.main()
