# Hearthline Playground — RosettaBench

This title branch carries a sealed no-run research station for `ROSETTA-001`
and a separate one-problem development calibration, `ROSETTA-CAL-001`.

RosettaBench tests whether a model can solve programming problems through a
new, problem-local symbolic interface. Its public Core task presents each of
150 AtCoder problems in a unique synthetic remapping of Python and supplies six
synthetic-to-Python demonstration pairs. Its Python task presents the same
problem set as a control. The author defines:

```text
learning tax = Python pass rate - Rosetta Core pass rate
```

The Git branch contains lightweight instructions, public metadata, calibration
source, and offline verification tools. It does not contain Rosetta notebooks,
benchmark data, test cases, model outputs, credentials, or private run
artifacts. External setup and private receipts live on the fixed C: drive.

## Station state

| Boundary | State |
|---|---|
| Preparation | `PREPARED_NOT_RUN` |
| Kaggle authentication | `AUTH_NOT_ATTEMPTED` |
| Benchmark data | `DATA_NOT_DOWNLOADED` |
| GPT-5.6 Sol usability for these tasks | `SOL_MODEL_AVAILABILITY_UNVERIFIED` |
| Pilot | `PILOT_UNSELECTED_UNCONSUMED` |
| Astra exclusion | `REQUIRED_UNATTESTED_NOT_FROZEN` |

These rows describe the formal `ROSETTA-001` experiment. It remains unrun and
its 15 task IDs remain unselected. The separate calibration state and exact
four-call ceiling are recorded in
[the calibration protocol](docs/ROSETTA_CAL_001.md).

The public leaderboard currently contains a row named GPT-5.6 Sol, but that row
has no numeric Core score and no Python-control result. Presence in the table is
not evidence that a paired Sol run is available or operational.

## Development calibration

`ROSETTA-CAL-001` uses only the already-publicly-discussed `abc357_b` task. It
is permanently excluded from the later pilot through
[`exclusions/development-tasks.v1.json`](exclusions/development-tasks.v1.json).
The current Kaggle account exposes Terra and Luna but not Sol, so any completed
calibration is explicitly a Terra orientation result, never a Sol substitute
or public Rosetta score.

The calibration has four fresh-chat cells: bare Python, bare synthetic Core,
Hearthline synthetic Core, and Hearthline plus deterministic task-local Gloss
synthetic Core. It permits at most four model calls, no retries, and no
publication. See [the calibration protocol](docs/ROSETTA_CAL_001.md).

## Frozen formal design target

`ROSETTA-001` is a three-system by two-task-form design:

| Condition | System | Task form | Result class |
|---|---|---|---|
| `C01_BARE_SOL_PYTHON` | bare GPT-5.6 Sol | Python control | public-comparability candidate only after an exact-harness audit |
| `C02_BARE_SOL_CORE` | bare GPT-5.6 Sol | Rosetta Core | public-comparability candidate only after an exact-harness audit |
| `C03_HEARTHLINE_SOL_PYTHON` | frozen Hearthline(Sol) | Python control | derived system result |
| `C04_HEARTHLINE_SOL_CORE` | frozen Hearthline(Sol) | Rosetta Core | derived system result |
| `C05_HEARTHLINE_SOL_TASK_GLOSS_PYTHON` | frozen Hearthline(Sol) plus task-local Gloss | Python control | derived system result |
| `C06_HEARTHLINE_SOL_TASK_GLOSS_CORE` | frozen Hearthline(Sol) plus task-local Gloss | Rosetta Core | derived system result |

The first crossing is intended to be a 15-problem pilot with five easy, five
medium, and five hard problems. No problem has been selected, opened, assigned,
or consumed. Full-task execution is not earned by preparing this branch.

The Hearthline and Gloss conditions are not vanilla model results and must not
be placed on the public Rosetta leaderboard as if they were. Even the bare Sol
conditions are comparable only if the exact public task version, model version,
prompt, sampling, budget, evaluator, and execution semantics are matched and
recorded.

## Task-local Gloss

The Gloss named in this experiment is a narrow, task-local translation surface.
It records only correspondences supported by the six demonstrations, resets for
every problem, and exposes unresolved translation rather than inventing a
synthetic token. It is not canonical Bridge Gloss, does not modify Bridge, and
is not a second Thulia ledger. See [the Gloss contract](docs/GLOSS_CONTRACT.md).

## Prepared tools

Start with [the preparation guide](docs/GETTING_STARTED.md). The branch includes
an offline station verifier, an offline check-only/explicit code-fetch split, a
strict exclusion-aware metadata-only pilot selector, a structural result-bundle
validator, and one bounded private calibration task. It contains no publication
command.

## Before any run

The ordered gates are specified in
[the ROSETTA-001 protocol](docs/ROSETTA_001_PROTOCOL.md). At minimum, a future
authorized run needs:

1. human confirmation of the applicable Kaggle terms and data licenses;
2. a verified, exact Sol model identifier that can run both task forms;
3. frozen system prompts, budgets, sampling, tools, order, retry policy, and
   checkpoint namespace for all six conditions;
4. an Astra-exclusion attestation made before task selection;
5. authorized metadata-only selection of a sealed 5/5/5 pilot;
6. isolation of tests, language seeds, evaluator maps, and generated code;
7. explicit run authority and receipt locations.

Those gates remain closed for `ROSETTA-001`. The exact, separately authorized
calibration exception is recorded in `docs/ROSETTA_CAL_001.md`; it does not
open the formal pilot or authorize a public task or leaderboard entry.

## Public source snapshot

The exact public pins are recorded in [source-lock.v1.json](source-lock.v1.json).
The public observations, including leaderboard drift and schema discrepancies,
are recorded in
[metadata/public-observation.v1.json](metadata/public-observation.v1.json).

Important boundaries:

- `namanbnsl/RosettaBench` was observed at commit
  `099b4837252becbd2c650ca54b206ac1a6bc3470`.
- `Kaggle/kaggle-benchmarks` uses default branch `ci`, not `main`, and was
  observed at commit `ab291417d9a4c731ccfbfb03ac0b8316cb843683`.
- the Hugging Face dataset mirror was observed at commit
  `87567193229336fae36f0da95c4af6a2a46bf90f`.
- the Kaggle benchmark contains task version 1 of `rosettabench-core` and
  `rosettabench-python-baseline-control`.

## Licensing boundary

Licensing is not uniform across the public surfaces:

- the Kaggle dataset metadata declares MIT for dataset version 1;
- the Hugging Face mirror declares only the underspecified label `cc`;
- the Kaggle Python-control task page declares Apache-2.0;
- the Kaggle writeup declares CC0 for the writeup;
- the Kaggle Benchmarks SDK is Apache-2.0;
- the RosettaBench GitHub repository has no license file at the pinned commit.

No license is inherited across those surfaces. The GitHub source and HF mirror
remain unresolved for redistribution until a human review says otherwise.

## Lineage

- Series anchor: `c6077763fedb768e599031982a840ad324eb1051`
- Title branch: `kaggle/titles/rosetta`
- Experiment: `ROSETTA-001`

Christopher D. Pang directs and authors the project. AI systems are development
tools, not co-authors or independent scientific authorities.
