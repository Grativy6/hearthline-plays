# RosettaBench preparation guide

Status: `PREPARED_NOT_RUN`

This status applies to the formal `ROSETTA-001` experiment. A separately
authorized, four-call development probe is defined in
[`ROSETTA_CAL_001.md`](ROSETTA_CAL_001.md); it does not select or run the formal
pilot.

This branch makes room for a future RosettaBench experiment. It deliberately
does not install software, authenticate to Kaggle, choose or download tasks,
invoke a model, execute an evaluator, upload a notebook, or publish a
benchmark.

Current boundary labels:

```text
PREPARED_NOT_RUN
AUTH_NOT_ATTEMPTED
SDK_NOT_INSTALLED
ROSETTA_SOURCE_NOT_FETCHED
TASKS_NOT_SELECTED
DATA_NOT_DOWNLOADED
SOL_MODEL_AVAILABILITY_UNVERIFIED
MODEL_SLUG_UNRESOLVED
PUBLICATION_NOT_AUTHORIZED
```

The pinned SDK identities and credential hazards are recorded in
[`KAGGLE_BENCHMARKS_SDK.md`](KAGGLE_BENCHMARKS_SDK.md).

## Intended experiment

The proposed comparison is three systems by two task forms. These are six
matched condition cells, not six completed runs:

| Cell | System | Task form |
| --- | --- | --- |
| `C01_BARE_SOL_PYTHON` | Bare GPT-5.6 Sol | Ordinary Python control |
| `C02_BARE_SOL_CORE` | Bare GPT-5.6 Sol | Rosetta synthetic core |
| `C03_HEARTHLINE_SOL_PYTHON` | Frozen Hearthline(Sol) | Ordinary Python control |
| `C04_HEARTHLINE_SOL_CORE` | Frozen Hearthline(Sol) | Rosetta synthetic core |
| `C05_HEARTHLINE_SOL_TASK_GLOSS_PYTHON` | Frozen Hearthline(Sol) + task-local Gloss | Ordinary Python control |
| `C06_HEARTHLINE_SOL_TASK_GLOSS_CORE` | Frozen Hearthline(Sol) + task-local Gloss | Rosetta synthetic core |

The primary paired quantity is only defined after execution:

```text
learning_tax(system) = python_score(system) - synthetic_score(system)
```

All cells must share the same underlying problem IDs, order, evaluator,
sampling budget, model slug, reasoning configuration, and task material. The
only intended differences are task form and the declared system treatment.
Hearthline and Gloss must be frozen to exact commits or content digests before
the task manifest is opened. Astra exclusion is required for the intended
experiment, but it is currently `REQUIRED_UNATTESTED_NOT_FROZEN`.

The result must retain individual outcomes rather than only the aggregate:

```text
PASS
NO_CODE
PYTHON_LEAK
SYNTAX_ERROR
RUNTIME_ERROR
WRONG_ANSWER
```

Record execution disposition on a separate axis:

```text
COMPLETED
TIMEOUT
INFRASTRUCTURE_FAILURE
```

Only `COMPLETED` rows receive an upstream outcome. An incomplete row must not
be silently counted as a wrong answer or zero.

Token and latency fields retain nonnegative measured values when the platform
exposes them and remain `null` when unavailable; missing telemetry is never
invented as zero.

Where the treatment permits it, retain public-safe records of mappings used,
unresolved mappings, unsupported mappings invented, and reformulations that
avoided an unavailable operation. Hidden evaluator tests and generator secrets
must never enter model-visible context or public receipts.

## Gates before any run

These gates are sequential. Passing one does not imply the next.

### 1. Source-choice gate

Choose either the hashed PyPI release or the exact newer source commit recorded
in `KAGGLE_BENCHMARKS_SDK.md`. Update a future lock file with the choice and do
not call them equivalent.

### 2. Storage gate

Name an explicit absolute cache/data destination on the upgraded PC's internal
hard drive or the intended external drive. Record expected size, available
space, filesystem, and recovery/removal policy. The Corpus USB/removable
workspace and this Git checkout are prohibited data destinations.

No large benchmark or competition data is downloaded during preparation.

### 3. Task-selection gate

Freeze the public RosettaBench repository/dataset revision and selection rule
before inspecting task contents. The 15-problem, 5/5/5 shape is predeclared;
the specific problem IDs remain unselected and require a separate instruction
before the selector may be run. A selection record must state:

- population and exact upstream revision;
- eligibility and exclusion rules;
- difficulty strata and deterministic selection procedure;
- selected problem IDs and order;
- duplicate/overlap checks;
- hashes for prompts, examples, controls, and evaluator material;
- whether any underlying public problem may be familiar to the model.

The synthetic remapping layer is contamination-resistant, not proof that the
underlying AtCoder algorithm is unseen.

### 4. Data-access gate

Review current upstream terms, license, access requirements, and download size.
Then authorize either check-only inspection or an explicit fetch. Check-only
must not silently become download. Fetch must require the approved absolute
destination and expected hashes.

### 5. Environment gate

On the upgraded machine, create a fresh Python `>=3.11` environment from the
chosen lock. Verify package identity and browser/runtime requirements without
copying Kaggle's internal staging configuration. Confirm that no parent `.env`
will be loaded and that credentials cannot enter Git or command output.

Installation is a future action and is not authorized by this guide.

### 6. Model-access gate

Only after explicit permission to authenticate, list the models actually
available to this Kaggle account and benchmark type. Do not infer access from a
public leaderboard. Resolve and record the exact Sol model slug or stop with
`SOL_MODEL_AVAILABILITY_UNVERIFIED`.

Authentication, `kaggle benchmarks init`, and model invocation are separate
actions and require separate approval.

### 7. Freeze gate

Freeze the six-cell manifest, treatment artifacts, prompt templates, evaluator,
budget, row order, SDK identity, model slug, and receipt schema. Verify that no
condition has internet, retrieval, language-generator maps, evaluator-side
tests, or undeclared tools.

The future SDK evaluation starts conservatively with:

```text
n_jobs=1
max_attempts=1
on_failure=continue
```

These are failure-accounting defaults, not a claim of deterministic sampling.

### 8. Execution gate

Obtain explicit permission for the bounded pilot and its expected quota/cost.
Run the six matched cells from the frozen manifest. Do not retry semantic
failures. Preserve errors and incomplete cells as errors or incomplete cells.

A local fake, import check, schema validation, or dry-run is never a Rosetta
result or a Kaggle run.

### 9. Publication gate

Analysis and publication remain separate. A completed local or hosted run does
not authorize `tasks push`, `tasks publish`, leaderboard submission, or public
claims. Publication requires a public-safety review and explicit approval of
the exact target and artifacts.

## Prepared tooling

The checked-in source tool has two deliberately distinct modes. Check-only is
offline and write-free, even when the cache does not exist:

```text
py tools/fetch_pinned_code.py --check-only --cache <ABSOLUTE_CODE_CACHE>
```

The explicit fetch mode is for the two pinned public GitHub code repositories
only. It never fetches the Rosetta dataset or Kaggle task material, and it must
not be used until a destination and fetch are separately authorized:

```text
py tools/fetch_pinned_code.py --fetch-code --cache <ABSOLUTE_APPROVED_CODE_CACHE>
```

Pilot selection is also inert until explicitly invoked. It accepts only a
small JSON list whose 150 entries contain exactly `question_id` and
`difficulty`; it rejects prompt, test, mapping, and other task fields, removes
the digest-bound development exclusion `abc357_b`, and creates rather than
overwrites its output:

```text
py tools/select_pilot.py <METADATA_ONLY_INDEX.json> --output <NEW_SEALED_MANIFEST.json>
```

That command selects identifiers, so do not run it under the current
`PILOT_UNSELECTED_UNCONSUMED` authority. It fails if the frozen exclusion is
missing or altered. On success it prints
`pilot_manifest_sha256`, defined as SHA-256 over the exact emitted UTF-8 file
bytes. The manifest deliberately has no ambiguous embedded self-hash.

The result-bundle validator is structural only and never executes candidate
code:

```text
py tools/validate_result_bundle.py <COMPLETED_RESULT_BUNDLE.json>
```

For provenance verification, supply both bound files. The tool then compares
their exact byte digests, verifies the pilot manifest's 5/5/5 identifiers and
order against every result condition, and binds its dataset revision to the
source lock instead of checking only digest syntax:

```text
py tools/validate_result_bundle.py <COMPLETED_RESULT_BUNDLE.json> --pilot-manifest <SEALED_MANIFEST.json> --source-lock source-lock.v1.json
```

A completed bundle copied from the template must use status
`RESULTS_RECORDED_NOT_PUBLIC`, replace every null model/system/source binding
with its frozen identifier or digest, retain the conservative execution policy,
and keep the template's structural-only claim ceiling. The validator rejects
unbound metadata and summaries that differ from the per-row outcomes.

The safe station check is:

```text
py tools/verify_station.py
```

Run tooling should be separate again from source fetching, and publication
tooling should be separate from both. A general readiness verifier must remain
safe to run without credentials, data, model access, or external effects.

## What can be done safely now

Read and review these documents. Refine the proposed scientific questions and
receipt schema without selecting tasks or opening data. When the upgraded
storage and compute are ready, resume at the source-choice and storage gates;
do not treat the existence of this branch as permission to skip them.
