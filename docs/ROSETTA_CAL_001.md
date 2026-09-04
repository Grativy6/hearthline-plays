# ROSETTA-CAL-001 orientation calibration

## Scope and status

`ROSETTA-CAL-001` is a one-problem development calibration, separate from the
sealed `ROSETTA-001` experiment. It uses only `abc357_b`, an example already
named and analyzed in the pinned RosettaBench README. That identifier is now a
permanent development exclusion from the later 15-problem pilot.

The calibration is intentionally small:

- one Kaggle dataset row;
- one available hosted model;
- four fresh chats and at most four model calls total;
- one attempt per cell;
- `max_completion_tokens=2048` and `reasoning="low"` per call;
- no model tools, retrieval, internet, cross-cell memory, repair, or retry;
- deterministic evaluation in the disposable Kaggle task kernel;
- no task publication or leaderboard claim.

The public 150-row Core and Python-control tasks are not dispatched. The
installed CLI has no row filter, so doing so would violate the usage cap.

## Why this task

The public author analysis says `abc357_b` requires uppercase conversion while
the six demonstrations expose `.lower()` but not `.upper()`. It is therefore a
high-information development probe for one narrow seam: whether a treatment
invents a familiar-but-unsupported token or reformulates with demonstrated
operations. Because the mechanism is already public, this task cannot support
a novelty, contamination-resistance, or general-capability claim.

## Four cells

| ID | Treatment | Form | Purpose |
| --- | --- | --- | --- |
| `CAL01_BARE_PYTHON` | no Hearthline and no task-local Gloss | ordinary Python | confirm underlying task tractability |
| `CAL02_BARE_CORE` | no Hearthline and no task-local Gloss | fresh synthetic dialect | expose the interface failure mode |
| `CAL03_HEARTHLINE_CORE` | frozen compact Hearthline treatment | fresh synthetic dialect | inspect strategic reformulation |
| `CAL04_HEARTHLINE_TASK_GLOSS_CORE` | same Hearthline treatment plus deterministic demonstrated-only ledger | fresh synthetic dialect | inspect supported/refused mapping behavior |

The three Core cells use the same prompt material and deterministic dialect.
Each cell starts in a new chat. Outputs and evaluator outcomes are never fed
into a later cell.

Task-local Gloss is a deterministic prompt-side ledger derived only from the
six displayed pairs. It is not canonical Bridge Gloss, not Thulia, and not a
second model call. Its source and tests live in the calibration task file.

## Model boundary

The authenticated Kaggle model listing observed on 2026-09-04 contains
`gpt-5.6-terra` and `gpt-5.6-luna`, but not `gpt-5.6-sol`. The public Core task
also records an earlier Sol run that errored on quota reservation. Therefore:

- `ROSETTA-001` remains bound to the intended Sol family and unrun;
- this calibration may use exact slug `gpt-5.6-terra` as an explicitly named
  orientation model;
- a Terra result is never relabeled as Sol or compared as a Sol reproduction.

Direct OpenAI API use is outside this calibration path. No existing
`OPENAI_API_KEY` is reused without the credential choice required by the local
OpenAI API workflow.

## Storage and environment

The execution root is
`C:\Users\cdpan\HearthlineData\RosettaBench` on the fixed NTFS C: drive. The
removable FAT32 E: drive is prohibited for caches, task data, and outputs.

Prepared external state:

- Python 3.12.14 virtual environment at `env\py312`;
- `kaggle_benchmarks` 0.6.1 installed from exact source commit
  `ab291417d9a4c731ccfbfb03ac0b8316cb843683`;
- RosettaBench inspection checkout at exact commit
  `099b4837252becbd2c650ca54b206ac1a6bc3470`;
- no 737 MB Rosetta parquet downloaded to the PC;
- Kaggle OAuth stored only in Kaggle's normal user credential location, never
  in this repository.

The private hosted task attaches Kaggle dataset
`namanbnsl/rosettabench-150-stratified-compressed`. Because the CLI attaches
the latest published version rather than a numbered version, version 1 and its
metadata must be rechecked immediately before task creation. The task filters
to exactly `abc357_b` before constructing any prompt or test object.

## Dispatch boundary

Before task creation, run the side-effect-free static gate:

```text
py tools/verify_calibration.py --mode pre-dispatch
```

It must report `PASS_STATIC_PRE_DISPATCH`. The gate binds the exact task-source
digest, model allowlist, dataset metadata, cell order, call budget, development
exclusion, private-task policy, and zeroed pre-dispatch status in
`status/rosetta-cal-001-status.v1.json`. It does not authenticate, open data,
call a model, execute the evaluator, or create an external task.

The authorized external target is one private task with slug
`hearthline-rosetta-cal-001-abc357b`. Task creation is persistent because the
current server does not support deletion. A duplicate-name check must return
no task before the one-time push.

Task version 1 failed during Kaggle's model-less build probe: its strict actor
guard rejected the placeholder before the dataset was loaded or any model was
called. The first run request was then rejected locally because only a
completed task can run. These failures are preserved in the calibration status.
One corrective push to the same private task is permitted; concrete hosted
actors remain fail-closed to Terra, while the model-less creation placeholder
may complete the build. No second repair is permitted.

Exactly one hosted run may be dispatched against `gpt-5.6-terra`. The task
itself makes at most four calls. A failed or uncertain model dispatch is
recorded and is not retried automatically. `kaggle benchmarks tasks publish`
is forbidden.

## Evaluator and security boundary

The task is a clean-room Rosetta-derived calibration rather than a copy of the
unlicensed upstream notebook. It generates a deterministic fresh dialect,
presents six paired examples, checks Python leakage, back-translates, compiles,
and runs the candidate against the selected dataset row's tests.

Generated code executes only inside Kaggle's disposable task kernel, in a
temporary directory with a stripped environment and operating-system resource
limits where available. That is materially safer than running it on the user's
PC, but it is not a proof of complete process or network isolation. Preserve
that residual in every receipt.

## Claim ceiling

The calibration may report exact per-cell outcomes, observed leakage,
unsupported method use, demonstrated mappings, reformulation markers, token
telemetry when exposed, task/runtime errors, and artifact hashes.

It does not estimate a Rosetta score or learning tax, establish a causal Gloss
benefit, generalize beyond one pre-exposed task, measure durable learning,
prove contamination freedom, demonstrate ARC-AGI-3 improvement, or earn a
public leaderboard comparison.
