# AGENTS.md — Rosetta title boundary

These instructions apply to this title worktree and every descendant path.

## Read first

Before acting, read `README.md`, `source-lock.v1.json`,
`metadata/public-observation.v1.json`, `docs/ROSETTA_001_PROTOCOL.md`, and
`docs/GLOSS_CONTRACT.md`.

## Lineage and identity

- Repository: `hearthline-plays`
- Series anchor: `c6077763fedb768e599031982a840ad324eb1051`
- Branch: `kaggle/titles/rosetta`
- Experiment ID: `ROSETTA-001`
- Formal experiment state: `ROSETTA-001 / PREPARED_NOT_RUN`
- Development calibration: `ROSETTA-CAL-001 / AUTHORIZED_NOT_DISPATCHED`

On the E: filesystem, invoke Git with the exact worktree supplied to
`safe.directory`. Do not alter another Hearthline checkout or title branch.

## Current authority

The user's 2026-09-04 instruction expands authority for exactly the bounded
`ROSETTA-CAL-001` setup and orientation run described in
`docs/ROSETTA_CAL_001.md`. It permits a clean environment and source cache on
the fixed C: drive, Kaggle OAuth, one duplicate-checked private task push,
attachment of dataset version 1, and one hosted Terra run whose task makes at
most four calls. It does not authorize retries, publication, or formal-pilot
consumption.

Outside that one-shot calibration grant, do not:

- authenticate to Kaggle or test stored credentials;
- invoke `kaggle benchmarks auth` or `kaggle benchmarks init`;
- push, publish, schedule, run, delete, or download a Kaggle benchmark task;
- clone RosettaBench or the Kaggle Benchmarks SDK anywhere except the recorded
  fixed-drive calibration cache;
- download, preview, enumerate, or otherwise consume benchmark task rows;
- select the 15 pilot problems;
- reveal or inspect evaluator-only tests, language seeds, or full maps;
- invoke GPT-5.6 Sol, Astra, or another model as an experimental subject or
  task solver, or invoke the Rosetta evaluator, except for the exact capped
  `gpt-5.6-terra` calibration dispatch;
- compile or execute generated candidate programs;
- claim a score, failure profile, learning tax, cost, latency, or scientific
  conclusion;
- publish a derived Hearthline result as a vanilla Rosetta leaderboard result.

The zero-action labels in `status/station-status.v1.json` and
`metadata/public-observation.v1.json` are scoped to the formal station and its
immutable pre-calibration observation. They are not current host-state claims
for `ROSETTA-CAL-001`; use `status/rosetta-cal-001-status.v1.json` for that
separate calibration. Formal `DATA_NOT_DOWNLOADED` and unselected-pilot states
remain current even after the bounded calibration.

## Experimental invariants

Preserve all six `ROSETTA-001` condition IDs and both paired task forms exactly
as documented. Do not drop its Python controls, substitute a different model
for Sol, or merge its Hearthline and Gloss arms. The separately identified
Terra calibration is not a substitution into `ROSETTA-001`.

The pilot remains `PILOT_UNSELECTED_UNCONSUMED`: five easy, five medium, and
five hard are intended, but their identities are not chosen. Preparation,
synthetic fixtures, schema checks, or public leaderboard inspection do not
count as a pilot or benchmark run.

`abc357_b` is permanently reserved for `ROSETTA-CAL-001` and must be removed by
the digest-bound exclusion manifest before formal pilot ranking. It may never
enter the 15-task pilot.

Checkpoint identity must include at least the experiment ID, condition ID,
exact task version, task-set digest, model identifier, system digest, sampling
digest, budget digest, and attempt number. The upstream notebook's model-only
checkpoint naming is insufficient for a six-condition comparison.

## Astra exclusion

Astra exclusion is required but currently
`REQUIRED_UNATTESTED_NOT_FROZEN`. Do not claim an Astra-excluded experiment
until a human-approved freeze receipt attests the exclusion boundary before
pilot selection. If Astra participates in selection, treatment design, task
solution, execution, repair, or outcome interpretation after the declared
cutoff, `ROSETTA-001` cannot be labeled Astra-excluded without an explicit
protocol amendment and new experiment identity.

## Gloss boundary

The experimental adapter is `task-local Gloss`:

- it is reset for every problem;
- it may use only the six supplied demonstration pairs;
- it may record supported correspondences and unresolved requests;
- it may not access a seed, generator map, tests, evaluator translation, or
  another problem's mappings;
- it may not choose the algorithm or invent unsupported vocabulary.

Task-local Gloss is not canonical Bridge Gloss and does not modify Bridge. It
is not Thulia. Thulia may later flag systemic translation friction without
owning a duplicate mapping ledger, but no Thulia implementation or result is
authorized here.

## Evidence and claims

Keep author-reported static results, live public Kaggle observations, future
bare-model runs, future Hearthline runs, future task-local Gloss runs, and
future fresh-salt derivatives separate.

Public presence of a model name is not proof of model availability. A public
row with a non-numeric result is not a zero benchmark score. A locally
reproduced evaluator is not an official Kaggle result. A derived system result
is not directly comparable unless the declared interface and harness match.

Preserve raw outcomes. Do not collapse harness errors or timeouts into an
official Rosetta category without evidence. The public taxonomy contains
`PASS`, `NO_CODE`, `PYTHON_LEAK`, `SYNTAX_ERROR`, `RUNTIME_ERROR`, and
`WRONG_ANSWER`; local extensions must remain separately labeled.

## External and secret safety

`kaggle benchmarks init` fetches Model Proxy credentials and writes an `.env`.
It is not a read-only setup command. Any later external dispatch requires an
exact target, duplicate check, one authorized dispatch, and an authoritative
receipt. Never commit credentials, tokens, private URLs, task payloads,
generated solutions, hidden tests, or evaluator maps.

## Authorship

Christopher D. Pang directs and authors the project. AI systems may assist with
development and audit but are not authors or scientific authorities.
