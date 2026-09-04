#!/usr/bin/env python3
"""Private, one-task Rosetta-derived orientation for ``abc357_b``.

This module deliberately does not import Kaggle Benchmarks at import time.  The
SDK is loaded only by :func:`build_kaggle_task`, and the resulting task's
``.run()`` call is protected by the ``__main__`` guard at the bottom of the
file.  Importing this module therefore cannot contact a model, load task data,
or execute a candidate program.

This is ``ROSETTA_DERIVED_FRESH_SALT`` calibration evidence.  It is neither a
public RosettaBench score nor a run of the sealed ``ROSETTA-001`` pilot.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import keyword
import math
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
import tokenize
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from importlib import metadata as importlib_metadata
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    # The Kaggle CLI discovers task names with a static AST scan for a literal
    # ``@*.task`` decorator. Runtime registration remains lazy below so an
    # ordinary import cannot load the SDK or contact a configured model proxy.
    import kaggle_benchmarks as kbench

    @kbench.task(name="Hearthline Rosetta CAL 001 abc357b")
    def _kaggle_cli_discovery_marker() -> dict[str, object]: ...

EXPERIMENT_ID = "ROSETTA-CAL-001"
RESULT_LABEL = "ROSETTA_DERIVED_FRESH_SALT"
TASK_ID = "abc357_b"

DATASET_SLUG = "namanbnsl/rosettabench-150-stratified-compressed"
DATASET_EXPECTED_VERSION = 1
DATASET_EXPECTED_TOTAL_BYTES = 736_965_670
DATASET_PATH = Path(
    "/kaggle/input/datasets/namanbnsl/rosettabench-150-stratified-compressed/"
    "rosetta_150_stratified-compressed.parquet"
)

# Generated once for this calibration and then committed as a literal freeze.
# It is new relative to the upstream RosettaBench mappings, but is not treated
# as a secret.  Only its derived six-example surface reaches the model.
DIALECT_DOMAIN = "hearthline/rosetta-cal-001/abc357_b/hash-identifiers-v1"
DIALECT_SALT_HEX = "ee0c8d738f15355a146a5aea42a2e97cef0af4548efeb58f1d597e0c9de61099"
DIALECT_SALT = bytes.fromhex(DIALECT_SALT_HEX)

MAX_LLM_CALLS = 4
ATTEMPTS_PER_CELL = 1
REASONING_EFFORT = "low"
MAX_COMPLETION_TOKENS = 2048
EXPECTED_MODEL_SLUGS = frozenset({"gpt-5.6-terra", "openai/gpt-5.6-terra"})

TEST_TIMEOUT_SECONDS = 2.0
OUTPUT_CAP_BYTES = 16 * 1024
PROGRAM_CAP_BYTES = 32 * 1024
MEMORY_LIMIT_BYTES = 256 * 1024 * 1024

_SYNTHETIC_PREFIX = "rz_"
_SYNTHETIC_IDENTIFIER = re.compile(r"^rz_[0-9a-f]{24}$")
_SOLUTION_BLOCK = re.compile(r"<solution\b[^>]*>(.*?)</solution>", re.IGNORECASE | re.DOTALL)
_FENCED_BLOCK = re.compile(r"```(?:[A-Za-z0-9_+.-]+)?\s*\n(.*?)```", re.DOTALL)


class CalibrationError(RuntimeError):
    """Base class for calibration contract failures."""


class RowFilterError(CalibrationError):
    """Raised when the exact one-row task boundary cannot be established."""


class DialectError(CalibrationError):
    """Raised for malformed or unknown synthetic surface forms."""


class GlossError(CalibrationError):
    """Raised when demonstration-derived Gloss evidence is invalid."""


class UnresolvedMapping(GlossError):
    """Raised when Gloss is asked to render an unsupported surface token."""

    def __init__(self, tokens: Sequence[str]) -> None:
        self.tokens = tuple(tokens)
        super().__init__(f"unresolved task-local Gloss mappings: {', '.join(self.tokens)}")


class CallBudgetExceeded(CalibrationError):
    """Raised before a model invocation would exceed the hard call ceiling."""


class CandidatePolicyError(CalibrationError):
    """Raised when generated code exceeds the deliberately small safe subset."""


class Outcome(StrEnum):
    PASS = "PASS"
    NO_CODE = "NO_CODE"
    PYTHON_LEAK = "PYTHON_LEAK"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    WRONG_ANSWER = "WRONG_ANSWER"


class Disposition(StrEnum):
    COMPLETED = "COMPLETED"
    TIMEOUT = "TIMEOUT"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True)
class TaskView:
    """The only task fields permitted to reach prompt construction."""

    question_id: str
    title: str
    content: str


@dataclass(frozen=True)
class TestCase:
    stdin: str
    expected_stdout: str


@dataclass(frozen=True)
class TestView:
    """Evaluator-only material that is never accepted by prompt builders."""

    question_id: str
    cases: tuple[TestCase, ...]
    tests_sha256: str


@dataclass(frozen=True)
class DatasetBinding:
    path: str
    attached_file_bytes: int
    selected_row_count: int
    current_version: int | None


@dataclass(frozen=True)
class LoadedCalibrationData:
    task: TaskView
    tests: TestView
    binding: DatasetBinding


@dataclass(frozen=True)
class CellSpec:
    cell_id: str
    task_form: str
    treatment: str
    gloss_enabled: bool = False


CELLS = (
    CellSpec("CAL01_BARE_PYTHON", "PYTHON", "BARE"),
    CellSpec("CAL02_BARE_CORE", "CORE", "BARE"),
    CellSpec("CAL03_HEARTHLINE_CORE", "CORE", "HEARTHLINE"),
    CellSpec(
        "CAL04_HEARTHLINE_TASK_GLOSS_CORE",
        "CORE",
        "HEARTHLINE_TASK_LOCAL_GLOSS",
        gloss_enabled=True,
    ),
)


def _select_exact_target(rows: Iterable[Mapping[str, object]]) -> Mapping[str, object]:
    """Filter by exact ID while reading no other field from non-target rows."""

    matches: list[Mapping[str, object]] = []
    for offset, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise RowFilterError(f"row {offset + 1} is not a mapping")
        question_id = row.get("question_id")
        if not isinstance(question_id, str):
            raise RowFilterError(f"row {offset + 1} has a non-string question_id")
        if question_id == TASK_ID:
            matches.append(row)

    if len(matches) != 1:
        raise RowFilterError(f"expected exactly one {TASK_ID!r} row; found {len(matches)}")
    return matches[0]


def _task_view_from_selected(selected: Mapping[str, object]) -> TaskView:
    """Copy only model-visible fields from an already-filtered row."""

    title = selected.get("question_title")
    content = selected.get("question_content")
    if not isinstance(title, str) or not title.strip() or title != title.strip():
        raise RowFilterError("target question_title must be a non-empty trimmed string")
    if not isinstance(content, str) or not content.strip() or content != content.strip():
        raise RowFilterError("target question_content must be a non-empty trimmed string")
    if len(title.encode("utf-8")) > 512 or len(content.encode("utf-8")) > 16 * 1024:
        raise RowFilterError("target prompt fields exceed their size ceilings")
    return TaskView(question_id=TASK_ID, title=title, content=content)


def _test_view_from_selected(selected: Mapping[str, object]) -> TestView:
    """Parse hidden tests from the selected row without crossing into TaskView."""

    payload = selected.get("all_tests")
    if hasattr(payload, "tolist"):
        payload = payload.tolist()
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RowFilterError("all_tests bytes must be UTF-8") from exc
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RowFilterError("all_tests must contain valid JSON") from exc
    if not isinstance(payload, (list, tuple)) or not payload:
        raise RowFilterError("all_tests must be a non-empty list")
    if len(payload) > 10_000:
        raise RowFilterError("all_tests exceeds the 10,000-case safety ceiling")

    cases: list[TestCase] = []
    digest_rows: list[dict[str, str]] = []
    total_bytes = 0
    for offset, raw_case in enumerate(payload):
        if not isinstance(raw_case, Mapping):
            raise RowFilterError(f"all_tests row {offset + 1} is not a mapping")
        stdin = raw_case.get("input")
        expected = raw_case.get("output")
        if not isinstance(stdin, str) or not isinstance(expected, str):
            raise RowFilterError(f"all_tests row {offset + 1} requires string input/output")
        total_bytes += len(stdin.encode("utf-8")) + len(expected.encode("utf-8"))
        if total_bytes > 128 * 1024 * 1024:
            raise RowFilterError("selected tests exceed the 128 MiB safety ceiling")
        cases.append(TestCase(stdin, expected))
        digest_rows.append({"input": stdin, "output": expected})

    canonical = json.dumps(
        digest_rows,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return TestView(TASK_ID, tuple(cases), hashlib.sha256(canonical).hexdigest())


def filter_target_row(rows: Iterable[Mapping[str, object]]) -> TaskView:
    """Select exactly ``abc357_b`` and strip evaluator-only fields."""

    return _task_view_from_selected(_select_exact_target(rows))


def split_target_material(rows: Iterable[Mapping[str, object]]) -> tuple[TaskView, TestView]:
    """Create disjoint prompt and test views only after exact row filtering."""

    selected = _select_exact_target(rows)
    return _task_view_from_selected(selected), _test_view_from_selected(selected)


def load_attached_calibration_data() -> LoadedCalibrationData:
    """Load only the attached ``abc357_b`` row with a parquet predicate."""

    require_kaggle_kernel()
    if not DATASET_PATH.is_file():
        raise RowFilterError(f"attached Kaggle dataset file is missing: {DATASET_PATH}")
    try:
        import pandas as pd
    except ImportError as exc:
        raise RowFilterError("pandas is unavailable in the hosted kernel") from exc

    frame = pd.read_parquet(
        DATASET_PATH,
        columns=["question_id", "question_title", "question_content", "all_tests"],
        filters=[("question_id", "==", TASK_ID)],
    )
    records = frame.to_dict(orient="records")
    task, tests = split_target_material(records)
    binding = DatasetBinding(
        path=str(DATASET_PATH),
        attached_file_bytes=DATASET_PATH.stat().st_size,
        selected_row_count=len(records),
        # Kaggle's attached path exposes the current file, but not its dataset
        # version number.  The caller preflights latest==1 before task push;
        # keep the in-kernel field honestly unavailable rather than guessing.
        current_version=None,
    )
    return LoadedCalibrationData(task, tests, binding)


# All source lexemes in the private evaluator dialect.  Several are never
# demonstrated.  Consequently, the six pairs are not a disguised full reverse
# map.  There intentionally is no ``upper`` constructor.
_DIALECT_SOURCE_TOKENS = (
    "=",
    "(",
    ")",
    ".",
    ":",
    "+",
    "-",
    "*",
    "<",
    "==",
    "input",
    "print",
    "lower",
    "for",
    "in",
    "range",
    "if",
    "else",
    "int",
    "ord",
    "chr",
    "len",
    # Undemonstrated evaluator vocabulary follows.
    "while",
    "break",
    "continue",
    "and",
    "or",
    "not",
    "list",
    "max",
    "min",
    "sorted",
    "append",
    "strip",
    "split",
    "replace",
    "isupper",
    "!=",
    "<=",
    ">=",
    ">",
    "/",
    "//",
    "%",
    "[",
    "]",
    "{",
    "}",
    ",",
)

_REQUIRED_SOLUTION_SURFACE = frozenset(
    {
        "=",
        "(",
        ")",
        ".",
        ":",
        "+",
        "-",
        "*",
        "<",
        "==",
        "input",
        "print",
        "lower",
        "for",
        "in",
        "if",
        "else",
        "ord",
        "chr",
        "len",
    }
)


@dataclass(frozen=True)
class Dialect:
    forward: Mapping[str, str]
    reverse: Mapping[str, str]
    domain: str
    salt_sha256: str
    mapping_sha256: str

    def to_synthetic(self, python_program: str) -> str:
        return _replace_lexemes(python_program, self.forward, reject_unknown_synthetic=False)

    def to_python(self, synthetic_program: str) -> str:
        return _replace_lexemes(synthetic_program, self.reverse, reject_unknown_synthetic=True)


def _hash_identifier(domain: str, salt: bytes, source: str) -> str:
    digest = hashlib.sha256(
        domain.encode("utf-8") + b"\0" + salt + b"\0" + source.encode("utf-8")
    ).hexdigest()
    return f"{_SYNTHETIC_PREFIX}{digest[:24]}"


def create_dialect(salt: bytes = DIALECT_SALT, *, domain: str = DIALECT_DOMAIN) -> Dialect:
    """Create a deterministic dialect from the frozen calibration domain/salt."""

    if not isinstance(salt, bytes) or len(salt) != 32:
        raise DialectError("dialect salt must be exactly 32 bytes")
    if not isinstance(domain, str) or not domain or domain != domain.strip():
        raise DialectError("dialect domain must be a non-empty trimmed string")
    if len(set(_DIALECT_SOURCE_TOKENS)) != len(_DIALECT_SOURCE_TOKENS):
        raise DialectError("dialect source vocabulary contains duplicates")

    forward = {
        source: _hash_identifier(domain, salt, source) for source in _DIALECT_SOURCE_TOKENS
    }
    if len(set(forward.values())) != len(forward):
        raise DialectError("hash-derived synthetic identifiers collided")
    if "upper" in forward:
        raise DialectError("upper must not have a synthetic constructor")
    reverse = {synthetic: source for source, synthetic in forward.items()}
    canonical = json.dumps(forward, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return Dialect(
        forward=MappingProxyType(forward),
        reverse=MappingProxyType(reverse),
        domain=domain,
        salt_sha256=hashlib.sha256(salt).hexdigest(),
        mapping_sha256=hashlib.sha256(canonical.encode("ascii")).hexdigest(),
    )


def _replace_lexemes(
    program: str,
    replacements: Mapping[str, str],
    *,
    reject_unknown_synthetic: bool,
) -> str:
    if not isinstance(program, str):
        raise DialectError("program must be text")
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(program).readline))
    except (IndentationError, tokenize.TokenError) as exc:
        raise DialectError("program cannot be tokenized") from exc

    rendered: list[tuple[int, str]] = []
    for token in tokens:
        value = token.string
        if token.type in {tokenize.NAME, tokenize.OP} and value in replacements:
            replacement = replacements[value]
            replacement_type = tokenize.NAME if _SYNTHETIC_IDENTIFIER.fullmatch(replacement) else token.type
            if replacement in _DIALECT_SOURCE_TOKENS:
                replacement_type = tokenize.OP if replacement in _OPERATOR_TOKENS else tokenize.NAME
            rendered.append((replacement_type, replacement))
            continue
        if (
            reject_unknown_synthetic
            and token.type == tokenize.NAME
            and value.startswith(_SYNTHETIC_PREFIX)
            and value not in replacements
        ):
            raise DialectError("candidate contains an unknown reserved synthetic identifier")
        rendered.append((token.type, value))
    try:
        return tokenize.untokenize(rendered)
    except (IndentationError, tokenize.TokenError) as exc:
        raise DialectError("program cannot be rendered") from exc


_OPERATOR_TOKENS = frozenset(
    token
    for token in _DIALECT_SOURCE_TOKENS
    if token and not (token[0].isalpha() or token[0] == "_")
)


@dataclass(frozen=True)
class ProgramPair:
    pair_id: str
    python: str
    synthetic: str


_DEMONSTRATION_PROGRAMS = (
    "word = input()\nprint(word)\n",
    "word = input()\nsmall = word.lower()\nprint(small)\n",
    "total = 0\nfor item in range(3):\n    total = total + item\nprint(total)\n",
    "value = int(input())\nif value == 0:\n    print(1)\nelse:\n    print(2)\n",
    "letter = input()\ncode = ord(letter) - 1\nprint(chr(code))\n",
    "word = input()\nif len(word) * 2 < 10:\n    print(word.lower())\nelse:\n    print(word)\n",
)


def make_program_pairs(dialect: Dialect) -> tuple[ProgramPair, ...]:
    pairs = tuple(
        ProgramPair(f"PAIR_{offset}", program, dialect.to_synthetic(program))
        for offset, program in enumerate(_DEMONSTRATION_PROGRAMS, start=1)
    )
    if len(pairs) != 6:
        raise CalibrationError("the calibration must expose exactly six program pairs")
    return pairs


def _significant_lexemes(program: str) -> list[str]:
    ignored = {
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
        tokenize.COMMENT,
    }
    try:
        return [
            token.string
            for token in tokenize.generate_tokens(io.StringIO(program).readline)
            if token.type not in ignored
        ]
    except (IndentationError, tokenize.TokenError) as exc:
        raise GlossError("demonstration cannot be tokenized") from exc


@dataclass(frozen=True)
class GlossEntry:
    python_lexeme: str
    synthetic_lexeme: str
    pair_ids: tuple[str, ...]


@dataclass(frozen=True)
class GlossLedger:
    """A deterministic ledger inferred only by aligning the six visible pairs."""

    entries: Mapping[str, GlossEntry]
    reverse: Mapping[str, str]

    @classmethod
    def from_pairs(cls, pairs: Sequence[ProgramPair]) -> GlossLedger:
        if len(pairs) != 6:
            raise GlossError("Gloss requires exactly six program pairs")
        observed: dict[str, tuple[str, list[str]]] = {}
        reverse: dict[str, str] = {}

        for pair in pairs:
            python_tokens = _significant_lexemes(pair.python)
            synthetic_tokens = _significant_lexemes(pair.synthetic)
            if len(python_tokens) != len(synthetic_tokens):
                raise GlossError(f"{pair.pair_id} token alignment changed length")
            for python_lexeme, synthetic_lexeme in zip(
                python_tokens, synthetic_tokens, strict=True
            ):
                if python_lexeme == synthetic_lexeme:
                    continue
                if not _SYNTHETIC_IDENTIFIER.fullmatch(synthetic_lexeme):
                    raise GlossError(f"{pair.pair_id} contains a non-identifier mapping")
                current = observed.get(python_lexeme)
                if current is None:
                    observed[python_lexeme] = (synthetic_lexeme, [pair.pair_id])
                elif current[0] != synthetic_lexeme:
                    raise GlossError(f"conflicting mapping for {python_lexeme!r}")
                elif pair.pair_id not in current[1]:
                    current[1].append(pair.pair_id)
                prior_source = reverse.get(synthetic_lexeme)
                if prior_source is not None and prior_source != python_lexeme:
                    raise GlossError(f"ambiguous synthetic lexeme in {pair.pair_id}")
                reverse[synthetic_lexeme] = python_lexeme

        entries = {
            source: GlossEntry(source, synthetic, tuple(provenance))
            for source, (synthetic, provenance) in observed.items()
        }
        return cls(MappingProxyType(entries), MappingProxyType(reverse))

    def supports(self, python_lexeme: str) -> bool:
        return python_lexeme in self.entries

    def render(self, python_program: str) -> str:
        """Render with demonstrated mappings, refusing unsupported language surface."""

        unresolved: set[str] = set()
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(python_program).readline))
        except (IndentationError, tokenize.TokenError) as exc:
            raise GlossError("requested program cannot be tokenized") from exc
        known_surface = frozenset(_DIALECT_SOURCE_TOKENS) | {"upper"}
        for token in tokens:
            if (
                token.type in {tokenize.NAME, tokenize.OP}
                and token.string in known_surface
                and token.string not in self.entries
            ):
                unresolved.add(token.string)
        if unresolved:
            raise UnresolvedMapping(sorted(unresolved))
        replacements = {
            source: entry.synthetic_lexeme for source, entry in self.entries.items()
        }
        return _replace_lexemes(
            python_program,
            replacements,
            reject_unknown_synthetic=False,
        )

    def public_records(self) -> list[dict[str, object]]:
        """Return only mappings visibly earned from demonstrations."""

        return [
            {
                "python_lexeme": source,
                "synthetic_lexeme": entry.synthetic_lexeme,
                "pair_ids": list(entry.pair_ids),
                "status": "SUPPORTED",
            }
            for source, entry in sorted(self.entries.items())
        ]


def _format_program_pairs(pairs: Sequence[ProgramPair]) -> str:
    sections: list[str] = []
    for pair in pairs:
        sections.append(
            f"{pair.pair_id}\nPYTHON:\n{pair.python.rstrip()}\n"
            f"SYNTHETIC:\n{pair.synthetic.rstrip()}"
        )
    return "\n\n".join(sections)


def _format_gloss_ledger(ledger: GlossLedger) -> str:
    supported = "\n".join(
        f"- {entry.python_lexeme!r} <-> {entry.synthetic_lexeme} "
        f"(SUPPORTED by {', '.join(entry.pair_ids)})"
        for entry in sorted(ledger.entries.values(), key=lambda item: item.python_lexeme)
    )
    return (
        "DETERMINISTIC TASK-LOCAL GLOSS LEDGER\n"
        f"{supported}\n"
        "- 'upper' -> UNRESOLVED (no demonstration supplies a constructor)\n"
        "Gloss may render supported correspondences only; it supplies no algorithm."
    )


def build_messages(
    cell: CellSpec,
    task: TaskView,
    pairs: Sequence[ProgramPair],
    ledger: GlossLedger,
) -> tuple[dict[str, str], ...]:
    """Build one fresh prompt from a filtered :class:`TaskView` only."""

    if not isinstance(task, TaskView):
        raise TypeError("prompt construction requires a filtered TaskView")
    if cell not in CELLS:
        raise CalibrationError("unknown calibration cell")

    common = (
        f"Private {RESULT_LABEL} orientation cell {cell.cell_id}. "
        "Use no tools, retrieval, internet, prior cell, or hidden evaluator state. "
        "This is one attempt. Return exactly one complete program inside "
        "<solution> and </solution>; do not add prose inside the tags."
    )
    if cell.treatment == "BARE":
        treatment = "Solve the stated programming problem directly."
    else:
        treatment = (
            "Hearthline orientation: keep translation evidence separate from algorithm "
            "choice. Inventory only supplied constructions, carry unresolved operations "
            "explicitly, and reformulate from supported operations instead of inventing "
            "a familiar constructor."
        )

    if cell.task_form == "PYTHON":
        system = f"{common}\n{treatment}\nReturn ordinary Python 3 source."
        user = f"Task {task.question_id}: {task.title}\n\n{task.content}"
    else:
        gloss_text = f"\n\n{_format_gloss_ledger(ledger)}" if cell.gloss_enabled else ""
        system = (
            f"{common}\n{treatment}\n"
            "Return only the synthetic dialect. Python keywords, built-ins, methods, "
            "operators, and delimiters shown as remapped in the examples are Python "
            "leaks if emitted literally. Variable names, indentation, numbers, and string "
            "literals remain ordinary. Do not invent synthetic identifiers."
            f"{gloss_text}"
        )
        user = (
            "Infer the local interface only from these six program pairs:\n\n"
            f"{_format_program_pairs(pairs)}\n\n"
            f"Task {task.question_id}: {task.title}\n\n{task.content}"
        )

    return ({"role": "system", "content": system}, {"role": "user", "content": user})


def extract_solution(output: str) -> str | None:
    """Extract the last explicit solution block, then the last fenced block."""

    if not isinstance(output, str):
        return None
    tagged = [match.strip() for match in _SOLUTION_BLOCK.findall(output) if match.strip()]
    if tagged:
        return tagged[-1]
    fenced = [match.strip() for match in _FENCED_BLOCK.findall(output) if match.strip()]
    return fenced[-1] if fenced else None


_PYTHON_BUILTIN_LEAKS = frozenset(
    {
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "filter",
        "float",
        "input",
        "int",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "open",
        "ord",
        "print",
        "range",
        "repr",
        "reversed",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    }
)


def find_python_leaks(synthetic_program: str) -> tuple[str, ...]:
    """Return literal Python surface tokens found outside strings and comments."""

    leaks: set[str] = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(synthetic_program).readline)
        for token in tokens:
            if token.type == tokenize.NAME and (
                keyword.iskeyword(token.string)
                or token.string in _PYTHON_BUILTIN_LEAKS
                or token.string in _DIALECT_SOURCE_TOKENS
                or token.string == "upper"
            ):
                leaks.add(token.string)
            elif token.type == tokenize.OP:
                leaks.add(token.string)
    except (IndentationError, tokenize.TokenError):
        # Tokenization failure is classified as syntax unless a leak was already
        # observed.  Do not manufacture an outcome from an exception string.
        pass
    return tuple(sorted(leaks))


@dataclass(frozen=True)
class CaseObservation:
    returncode: int | None
    stdout: str
    stdout_bytes: int
    stderr_bytes: int
    timed_out: bool = False
    output_limit_exceeded: bool = False


class CaseRunner(Protocol):
    def __call__(self, program: str, case: TestCase) -> CaseObservation: ...


def is_kaggle_kernel() -> bool:
    """Require both a Kaggle marker and the canonical mounted working path."""

    marker = bool(os.environ.get("KAGGLE_KERNEL_RUN_TYPE") or os.environ.get("KAGGLE_URL_BASE"))
    return os.name == "posix" and marker and Path("/kaggle/working").is_dir()


def require_kaggle_kernel() -> None:
    if not is_kaggle_kernel():
        raise CalibrationError("generated candidates may execute only inside a Kaggle kernel")


def _apply_child_resource_limits() -> None:
    """Best-effort POSIX limits, called only in the Kaggle child process."""

    try:
        import resource

        cpu_seconds = max(1, math.ceil(TEST_TIMEOUT_SECONDS) + 1)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
        resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_CAP_BYTES, OUTPUT_CAP_BYTES))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        if hasattr(resource, "RLIMIT_NPROC"):
            resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
    except (ImportError, OSError, ValueError):
        # The receipt labels these limits "where available"; the wall timeout,
        # byte-capped files, stripped environment, and temporary cwd still apply.
        return


class KaggleSubprocessRunner:
    """Execute one generated program/test pair within the Kaggle-only boundary."""

    def __call__(self, program: str, case: TestCase) -> CaseObservation:
        require_kaggle_kernel()
        clean_environment = {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTHONIOENCODING": "utf-8",
        }
        with tempfile.TemporaryDirectory(prefix="rosetta_cal_001_", dir="/kaggle/working") as temp:
            root = Path(temp)
            program_path = root / "candidate.py"
            stdout_path = root / "stdout.bin"
            stderr_path = root / "stderr.bin"
            program_path.write_text(program, encoding="utf-8", newline="\n")
            with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
                process = subprocess.Popen(
                    [sys.executable, "-I", "-S", str(program_path)],
                    cwd=root,
                    env=clean_environment,
                    stdin=subprocess.PIPE,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    start_new_session=True,
                    preexec_fn=_apply_child_resource_limits,
                )
                timed_out = False
                try:
                    process.communicate(case.stdin.encode("utf-8"), timeout=TEST_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=1)

            stdout_raw = stdout_path.read_bytes()[: OUTPUT_CAP_BYTES + 1]
            stderr_raw = stderr_path.read_bytes()[: OUTPUT_CAP_BYTES + 1]
            exceeded = len(stdout_raw) > OUTPUT_CAP_BYTES or len(stderr_raw) > OUTPUT_CAP_BYTES
            return CaseObservation(
                returncode=process.returncode,
                stdout=stdout_raw[:OUTPUT_CAP_BYTES].decode("utf-8", errors="replace"),
                stdout_bytes=min(len(stdout_raw), OUTPUT_CAP_BYTES),
                stderr_bytes=min(len(stderr_raw), OUTPUT_CAP_BYTES),
                timed_out=timed_out,
                output_limit_exceeded=exceeded,
            )


_FORBIDDEN_AST_NODES = (
    ast.AsyncFunctionDef,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.Await,
    ast.ClassDef,
    ast.FunctionDef,
    ast.Global,
    ast.Import,
    ast.ImportFrom,
    ast.Lambda,
    ast.Nonlocal,
    ast.With,
)
_FORBIDDEN_NAMES = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "help",
        "locals",
        "memoryview",
        "open",
        "setattr",
        "vars",
    }
)


def _validate_candidate_policy(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_AST_NODES):
            raise CandidatePolicyError(f"forbidden syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise CandidatePolicyError("forbidden runtime capability")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise CandidatePolicyError("private attribute traversal is forbidden")


def _normalize_stdout(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").splitlines()).rstrip()


@dataclass(frozen=True)
class EvaluationResult:
    outcome: Outcome | None
    disposition: Disposition
    tests_completed: int
    detail: str
    python_leak_count: int = 0


def evaluate_output(
    model_output: str,
    *,
    task_form: str,
    dialect: Dialect,
    tests: TestView,
    case_runner: CaseRunner,
) -> EvaluationResult:
    """Classify an output without retaining code or raw test evidence."""

    candidate = extract_solution(model_output)
    if candidate is None:
        return EvaluationResult(Outcome.NO_CODE, Disposition.COMPLETED, 0, "NO_EXTRACTABLE_BLOCK")
    if len(candidate.encode("utf-8")) > PROGRAM_CAP_BYTES:
        return EvaluationResult(Outcome.RUNTIME_ERROR, Disposition.COMPLETED, 0, "PROGRAM_SIZE_CAP")

    if task_form == "CORE":
        leaks = find_python_leaks(candidate)
        if leaks:
            return EvaluationResult(
                Outcome.PYTHON_LEAK,
                Disposition.COMPLETED,
                0,
                "LITERAL_PYTHON_SURFACE",
                len(leaks),
            )
        try:
            python_program = dialect.to_python(candidate)
        except DialectError:
            return EvaluationResult(
                Outcome.SYNTAX_ERROR,
                Disposition.COMPLETED,
                0,
                "SYNTHETIC_TRANSLATION_ERROR",
            )
    elif task_form == "PYTHON":
        python_program = candidate
    else:
        raise CalibrationError(f"unknown task form: {task_form}")

    try:
        tree = ast.parse(python_program, mode="exec")
        compile(tree, "<rosetta-cal-001-candidate>", "exec")
    except (SyntaxError, ValueError, OverflowError):
        return EvaluationResult(Outcome.SYNTAX_ERROR, Disposition.COMPLETED, 0, "COMPILE_ERROR")
    try:
        _validate_candidate_policy(tree)
    except CandidatePolicyError:
        return EvaluationResult(Outcome.RUNTIME_ERROR, Disposition.COMPLETED, 0, "POLICY_REJECTED")

    if tests.question_id != TASK_ID or not tests.cases:
        raise CalibrationError("evaluator requires the selected task's non-empty TestView")

    completed = 0
    for case in tests.cases:
        try:
            observation = case_runner(python_program, case)
        except Exception:
            return EvaluationResult(
                None,
                Disposition.INFRASTRUCTURE_FAILURE,
                completed,
                "CASE_RUNNER_FAILURE",
            )
        if observation.timed_out:
            return EvaluationResult(Outcome.RUNTIME_ERROR, Disposition.TIMEOUT, completed, "TEST_TIMEOUT")
        if observation.output_limit_exceeded:
            return EvaluationResult(
                Outcome.RUNTIME_ERROR,
                Disposition.COMPLETED,
                completed,
                "OUTPUT_CAP",
            )
        if observation.returncode != 0:
            return EvaluationResult(
                Outcome.RUNTIME_ERROR,
                Disposition.COMPLETED,
                completed,
                "NONZERO_EXIT",
            )
        completed += 1
        if _normalize_stdout(observation.stdout) != _normalize_stdout(case.expected_stdout):
            return EvaluationResult(
                Outcome.WRONG_ANSWER,
                Disposition.COMPLETED,
                completed,
                "OUTPUT_MISMATCH",
            )
    return EvaluationResult(Outcome.PASS, Disposition.COMPLETED, completed, "ALL_TESTS_PASSED")


@dataclass(frozen=True)
class ModelReply:
    text: str
    telemetry: Mapping[str, int | float | None]


class ModelCaller(Protocol):
    def __call__(
        self,
        *,
        cell_id: str,
        messages: tuple[dict[str, str], ...],
        reasoning: str,
        extra_api_params: Mapping[str, int],
    ) -> object: ...


_TELEMETRY_KEYS = (
    "input_tokens",
    "output_tokens",
    "input_tokens_cost_nanodollars",
    "output_tokens_cost_nanodollars",
    "total_cost_nanodollars",
    "total_backend_latency_ms",
)


def _finite_number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)) or value < 0:
        return None
    return value


def _coerce_model_reply(value: object) -> ModelReply:
    if isinstance(value, ModelReply):
        return value
    if isinstance(value, str):
        return ModelReply(value, MappingProxyType({}))

    text: object = None
    usage: object = None
    if isinstance(value, Mapping):
        for key in ("output_text", "text", "content"):
            if isinstance(value.get(key), str):
                text = value[key]
                break
        usage = value.get("usage")
    else:
        for attribute in ("output_text", "text", "content"):
            candidate = getattr(value, attribute, None)
            if isinstance(candidate, str):
                text = candidate
                break
        usage = getattr(value, "usage", None)
    if not isinstance(text, str):
        raise CalibrationError("model response did not expose text")

    telemetry: dict[str, int | float | None] = {}
    if isinstance(usage, Mapping):
        for key in _TELEMETRY_KEYS:
            telemetry[key] = _finite_number(usage.get(key))
    else:
        for key in _TELEMETRY_KEYS:
            telemetry[key] = _finite_number(getattr(usage, key, None))
    return ModelReply(text, MappingProxyType(telemetry))


class CallBudget:
    """A fail-closed counter around the sole model invocation surface."""

    def __init__(self, caller: ModelCaller, maximum: int = MAX_LLM_CALLS) -> None:
        if maximum != MAX_LLM_CALLS:
            raise CalibrationError(f"call budget is frozen at {MAX_LLM_CALLS}")
        self._caller = caller
        self.maximum = maximum
        self.calls = 0

    def invoke(self, cell_id: str, messages: tuple[dict[str, str], ...]) -> ModelReply:
        if self.calls >= self.maximum:
            raise CallBudgetExceeded("hard four-call calibration ceiling reached")
        self.calls += 1
        raw = self._caller(
            cell_id=cell_id,
            messages=messages,
            reasoning=REASONING_EFFORT,
            extra_api_params={"max_completion_tokens": MAX_COMPLETION_TOKENS},
        )
        return _coerce_model_reply(raw)


def _message_digest(messages: Sequence[Mapping[str, str]]) -> str:
    encoded = json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _task_digest(task: TaskView) -> str:
    encoded = json.dumps(
        {
            "question_id": task.question_id,
            "question_title": task.title,
            "question_content": task.content,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _receipt_gloss_records(ledger: GlossLedger) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for entry in sorted(ledger.entries.values(), key=lambda item: item.python_lexeme):
        records.append(
            {
                "python_lexeme": entry.python_lexeme,
                "synthetic_lexeme_sha256": hashlib.sha256(
                    entry.synthetic_lexeme.encode("ascii")
                ).hexdigest(),
                "pair_ids": list(entry.pair_ids),
                "status": "SUPPORTED",
            }
        )
    return records


def _safe_runtime_metadata(
    *, actor_model: str | None, sdk_version: str | None
) -> dict[str, object]:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "kaggle_benchmarks_version": sdk_version,
        "actor_model": actor_model,
    }


def _not_run_cell(cell: CellSpec, reason: str) -> dict[str, object]:
    return {
        "cell_id": cell.cell_id,
        "task_form": cell.task_form,
        "treatment": cell.treatment,
        "attempts": 0,
        "fresh_chat": False,
        "messages_sha256": None,
        "output_sha256": None,
        "output_bytes": 0,
        "outcome": None,
        "disposition": Disposition.NOT_RUN,
        "detail": reason,
        "wall_latency_ms": None,
        "telemetry": dict.fromkeys(_TELEMETRY_KEYS),
        "gloss_enabled": cell.gloss_enabled,
    }


def run_calibration(
    model_caller: ModelCaller,
    *,
    task: TaskView,
    tests: TestView,
    dataset_binding: DatasetBinding,
    actor_model: str | None,
    sdk_version: str | None,
    dialect: Dialect | None = None,
    case_runner: CaseRunner | None = None,
) -> dict[str, object]:
    """Run up to four one-attempt cells and return a non-sensitive receipt.

    Supplying ``case_runner`` is an injection seam for deterministic unit tests.
    Production callers omit it, which enforces the Kaggle-kernel check before
    the first model call and uses :class:`KaggleSubprocessRunner`.
    """

    if not isinstance(task, TaskView) or task.question_id != TASK_ID:
        raise RowFilterError("run requires the exact filtered TaskView")
    if not isinstance(tests, TestView) or tests.question_id != TASK_ID or not tests.cases:
        raise RowFilterError("run requires the exact hidden TestView")
    if not isinstance(dataset_binding, DatasetBinding):
        raise RowFilterError("run requires an explicit dataset binding")
    if case_runner is None:
        require_kaggle_kernel()
        selected_runner: CaseRunner = KaggleSubprocessRunner()
    else:
        selected_runner = case_runner

    selected_dialect = create_dialect() if dialect is None else dialect
    pairs = make_program_pairs(selected_dialect)
    ledger = GlossLedger.from_pairs(pairs)
    if not _REQUIRED_SOLUTION_SURFACE.issubset(ledger.entries):
        missing = sorted(_REQUIRED_SOLUTION_SURFACE - set(ledger.entries))
        raise GlossError(f"demonstrations do not support the solution surface: {missing}")
    if ledger.supports("upper"):
        raise GlossError("upper must remain unresolved")

    budget = CallBudget(model_caller)
    cells: list[dict[str, object]] = []
    abort_reason: str | None = None
    for cell in CELLS:
        if abort_reason is not None:
            cells.append(_not_run_cell(cell, abort_reason))
            continue
        messages = build_messages(cell, task, pairs, ledger)
        started = time.perf_counter()
        try:
            reply = budget.invoke(cell.cell_id, messages)
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            cells.append(
                {
                    "cell_id": cell.cell_id,
                    "task_form": cell.task_form,
                    "treatment": cell.treatment,
                    "attempts": ATTEMPTS_PER_CELL,
                    "fresh_chat": True,
                    "messages_sha256": _message_digest(messages),
                    "output_sha256": None,
                    "output_bytes": 0,
                    "outcome": None,
                    "disposition": Disposition.INFRASTRUCTURE_FAILURE,
                    "detail": "MODEL_CALL_FAILURE",
                    "model_error_class": type(exc).__name__,
                    "wall_latency_ms": elapsed_ms,
                    "telemetry": dict.fromkeys(_TELEMETRY_KEYS),
                    "gloss_enabled": cell.gloss_enabled,
                }
            )
            abort_reason = "NOT_RUN_AFTER_MODEL_INFRASTRUCTURE_FAILURE"
            continue

        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        try:
            evaluation = evaluate_output(
                reply.text,
                task_form=cell.task_form,
                dialect=selected_dialect,
                tests=tests,
                case_runner=selected_runner,
            )
        except Exception as exc:
            output_bytes = reply.text.encode("utf-8")
            cells.append(
                {
                    "cell_id": cell.cell_id,
                    "task_form": cell.task_form,
                    "treatment": cell.treatment,
                    "attempts": ATTEMPTS_PER_CELL,
                    "fresh_chat": True,
                    "messages_sha256": _message_digest(messages),
                    "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
                    "output_bytes": len(output_bytes),
                    "outcome": None,
                    "disposition": Disposition.INFRASTRUCTURE_FAILURE,
                    "detail": "EVALUATOR_FAILURE",
                    "evaluator_error_class": type(exc).__name__,
                    "wall_latency_ms": elapsed_ms,
                    "telemetry": {
                        key: _finite_number(reply.telemetry.get(key))
                        for key in _TELEMETRY_KEYS
                    },
                    "gloss_enabled": cell.gloss_enabled,
                }
            )
            abort_reason = "NOT_RUN_AFTER_EVALUATOR_INFRASTRUCTURE_FAILURE"
            continue
        output_bytes = reply.text.encode("utf-8")
        cells.append(
            {
                "cell_id": cell.cell_id,
                "task_form": cell.task_form,
                "treatment": cell.treatment,
                "attempts": ATTEMPTS_PER_CELL,
                "fresh_chat": True,
                "messages_sha256": _message_digest(messages),
                "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
                "output_bytes": len(output_bytes),
                "outcome": evaluation.outcome,
                "disposition": evaluation.disposition,
                "detail": evaluation.detail,
                "tests_completed": evaluation.tests_completed,
                "python_leak_count": evaluation.python_leak_count,
                "wall_latency_ms": elapsed_ms,
                "telemetry": {
                    key: _finite_number(reply.telemetry.get(key)) for key in _TELEMETRY_KEYS
                },
                "gloss_enabled": cell.gloss_enabled,
            }
        )
        if evaluation.disposition == Disposition.INFRASTRUCTURE_FAILURE:
            abort_reason = "NOT_RUN_AFTER_EVALUATOR_INFRASTRUCTURE_FAILURE"

    if budget.calls > MAX_LLM_CALLS or len(cells) != len(CELLS):
        raise CalibrationError("calibration violated its bounded four-cell call plan")

    receipt: dict[str, object] = {
        "schema_version": "rosetta-cal-001-receipt.v1",
        "experiment_id": EXPERIMENT_ID,
        "result_label": RESULT_LABEL,
        "public_score": False,
        "orientation_only": True,
        "task_id": TASK_ID,
        "task_statement_sha256": _task_digest(task),
        "dialect": {
            "derivation": "sha256_identifier_tokens_v1",
            "domain": selected_dialect.domain,
            "salt_literal_sha256": selected_dialect.salt_sha256,
            "mapping_sha256": selected_dialect.mapping_sha256,
            "seed_disclosed_to_model": False,
            "full_reverse_map_disclosed_to_model": False,
        },
        "call_policy": {
            "model": actor_model,
            "maximum_calls": MAX_LLM_CALLS,
            "actual_calls": budget.calls,
            "attempts_per_cell": ATTEMPTS_PER_CELL,
            "reasoning": REASONING_EFFORT,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "fresh_chat_per_cell": True,
            "tools": False,
            "retrieval": False,
        },
        "runtime": _safe_runtime_metadata(
            actor_model=actor_model,
            sdk_version=sdk_version,
        ),
        "dataset": {
            "expected": {
                "slug": DATASET_SLUG,
                "version": DATASET_EXPECTED_VERSION,
                "total_bytes": DATASET_EXPECTED_TOTAL_BYTES,
            },
            "current": {
                "attached_path": dataset_binding.path,
                "attached_file_bytes": dataset_binding.attached_file_bytes,
                "version": dataset_binding.current_version,
                "version_exposed_in_kernel": dataset_binding.current_version is not None,
                "selected_row_count": dataset_binding.selected_row_count,
                "selected_question_id": TASK_ID,
                "selected_tests_sha256": tests.tests_sha256,
            },
            "exact_filter_applied_before_views": True,
        },
        "evaluator": {
            "test_count": len(tests.cases),
            "tests_disclosed_to_model": False,
            "raw_tests_in_receipt": False,
            "per_test_timeout_seconds": TEST_TIMEOUT_SECONDS,
            "per_stream_output_cap_bytes": OUTPUT_CAP_BYTES,
            "subprocess_scope": "KAGGLE_KERNEL_ONLY",
        },
        "gloss": {
            "source": "six_program_pairs_only",
            "supported": _receipt_gloss_records(ledger),
            "unresolved": [{"python_lexeme": "upper", "status": "UNRESOLVED"}],
            "ambiguous_count": 0,
            "conflicting_count": 0,
            "cross_task_state": False,
        },
        "cells": cells,
        "claim_boundary": (
            "Private one-task orientation; not a public RosettaBench score, leaderboard "
            "entry, ROSETTA-001 pilot result, or estimate of learning tax."
        ),
    }
    return receipt


def _flatten_messages(messages: Sequence[Mapping[str, str]]) -> str:
    return "\n\n".join(
        f"<{message['role'].upper()}>\n{message['content']}" for message in messages
    )


def _non_calibration_actor_receipt(actor_model: str | None) -> dict[str, object]:
    """Return a zero-call receipt for Kaggle's build actor or a wrong run actor."""

    actor_label = actor_model if actor_model is not None else "MODEL_IDENTIFIER_UNAVAILABLE"
    return {
        "schema_version": "rosetta-cal-build-probe.v1",
        "experiment_id": EXPERIMENT_ID,
        "result_label": "NO_MODEL_BUILD_OR_WRONG_ACTOR",
        "disposition": "NOT_A_CALIBRATION_RUN",
        "actor_model_present": actor_model is not None,
        "actor_model_sha256": hashlib.sha256(actor_label.encode("utf-8")).hexdigest(),
        "model_calls": 0,
        "dataset_loaded": False,
        "evaluator_runs": 0,
        "publication": False,
    }


def build_kaggle_task() -> Any:
    """Build the private SDK task lazily; importing this module has no SDK effect."""

    try:
        import kaggle_benchmarks as kbench
    except ImportError as exc:
        raise CalibrationError("kaggle_benchmarks is not installed in this kernel") from exc

    def rosetta_cal_001_task(llm: object) -> dict[str, object]:
        require_kaggle_kernel()
        actor_model_raw = getattr(llm, "model", None)
        actor_model = str(actor_model_raw)[:256] if actor_model_raw is not None else None
        # Task creation supplies a non-Terra build actor. It must be able to
        # serialize this task without loading data or touching a model. Any
        # accidentally dispatched non-Terra run follows the same zero-call
        # path. Only the frozen Terra identifiers may cross into calibration.
        if actor_model not in EXPECTED_MODEL_SLUGS:
            return _non_calibration_actor_receipt(actor_model)
        loaded = load_attached_calibration_data()
        try:
            sdk_version = importlib_metadata.version("kaggle_benchmarks")
        except importlib_metadata.PackageNotFoundError:
            sdk_version = None

        def call_model(
            *,
            cell_id: str,
            messages: tuple[dict[str, str], ...],
            reasoning: str,
            extra_api_params: Mapping[str, int],
        ) -> object:
            with kbench.chats.new(cell_id) as chat:
                response = llm.prompt(
                    _flatten_messages(messages),
                    reasoning=reasoning,
                    extra_api_params=dict(extra_api_params),
                )
                usage = getattr(chat, "usage", None)
            telemetry = {
                key: _finite_number(getattr(usage, key, None)) for key in _TELEMETRY_KEYS
            }
            return ModelReply(str(response), MappingProxyType(telemetry))

        return run_calibration(
            call_model,
            task=loaded.task,
            tests=loaded.tests,
            dataset_binding=loaded.binding,
            actor_model=actor_model,
            sdk_version=sdk_version,
        )

    # ``from __future__ import annotations`` stores annotations as strings,
    # while this SDK revision performs identity-based result inference.  Bind
    # the concrete built-in here so the returned receipt is a Dictionary
    # result rather than a mismatched PassFail result.
    rosetta_cal_001_task.__annotations__["return"] = dict
    return kbench.task(name="Hearthline Rosetta CAL 001 abc357b")(
        rosetta_cal_001_task
    )


def main() -> None:
    """Run one private task attempt through the SDK's explicit run surface."""

    task = build_kaggle_task()
    import kaggle_benchmarks as kbench

    task.run(llm=kbench.llm)


if __name__ == "__main__":
    main()
