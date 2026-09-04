# ROSETTA-001 protocol

## Protocol state

`ROSETTA-001` is `PREPARED_NOT_RUN`.

- Authentication: `AUTH_NOT_ATTEMPTED`
- Data: `DATA_NOT_DOWNLOADED`
- Sol task availability: `SOL_MODEL_AVAILABILITY_UNVERIFIED`
- Pilot: `PILOT_UNSELECTED_UNCONSUMED`
- Astra exclusion: `REQUIRED_UNATTESTED_NOT_FROZEN`

Nothing in this document authorizes a Kaggle account action, data acquisition,
model call, generated-code execution, evaluator call, or benchmark dispatch.

## Research question

At a matched GPT-5.6 Sol model, task set, order, sampling policy, budget, and
evaluator, does frozen Hearthline reduce the performance drop between ordinary
Python and Rosetta's novel symbolic interface, and does adding task-local Gloss
reduce that drop further without inventing unsupported correspondences?

The primary descriptive quantity for each system is:

```text
learning_tax(system) = python_pass_rate(system) - core_pass_rate(system)
```

This quantity bundles language induction, tokenization, constrained expression,
syntax handling, and algorithmic performance. It is not, by itself, proof of
durable learning or parameter change.

## Source object

The public benchmark reports 150 AtCoder tasks drawn from LiveCodeBench
`release_v5`, stratified as 40 easy, 50 medium, and 60 hard. Core gives six
synthetic-to-Python demonstrations and requires a solution in a unique
problem-local remapping. Python control uses the same underlying tasks.

The pinned author description says Core extracts `<solution>` content, falls
back to the last fenced block, checks for Python leakage, back-translates,
compiles, and executes with a 30-second timeout. A task passes only when every
test passes. The official reported outcome vocabulary is:

- `PASS`
- `NO_CODE`
- `PYTHON_LEAK`
- `SYNTAX_ERROR`
- `RUNTIME_ERROR`
- `WRONG_ANSWER`

There is no separately documented official `TIMEOUT` category. Preserve raw
timeout and harness evidence as local extensions instead of guessing a mapping.

## Six conditions

| ID | System treatment | Task form | Classification |
|---|---|---|---|
| `C01_BARE_SOL_PYTHON` | no Hearthline and no task-local Gloss | Python control v1 | bare-model candidate |
| `C02_BARE_SOL_CORE` | no Hearthline and no task-local Gloss | Core v1 | bare-model candidate |
| `C03_HEARTHLINE_SOL_PYTHON` | frozen Hearthline(Sol) | Python control v1 | derived system |
| `C04_HEARTHLINE_SOL_CORE` | frozen Hearthline(Sol) | Core v1 | derived system |
| `C05_HEARTHLINE_SOL_TASK_GLOSS_PYTHON` | frozen Hearthline(Sol) plus frozen task-local Gloss | Python control v1 | derived system |
| `C06_HEARTHLINE_SOL_TASK_GLOSS_CORE` | frozen Hearthline(Sol) plus frozen task-local Gloss | Core v1 | derived system |

Task-local Gloss is deliberately present as a null/no-op translation surface in
the Python control. This measures system overhead without granting an extra
problem-solving channel. Its Core behavior is constrained by
`docs/GLOSS_CONTRACT.md`.

## Pilot

The intended first crossing is exactly 15 distinct problems: five easy, five
medium, and five hard.

No problem identities have been selected or consumed. Selection occurs only
after the model, system, sampling, budget, Astra-exclusion, licensing, and
evaluator boundaries are frozen.

A future authorized metadata-only selector must:

1. read only a separately verified index containing exactly `question_id` and
   `difficulty`, tied by digest to the exact pinned dataset distribution;
2. validate 40/50/60 source strata before selection;
3. select 5/5/5 with a frozen, recorded procedure and seed;
4. reject duplicate `question_id` values;
5. emit a sealed ordered task manifest and report the SHA-256 of the exact
   UTF-8 file bytes (the manifest does not contain a self-hash);
6. keep private tests, encoded test payloads, and generator state unavailable
   to every model-facing component;
7. expose a problem statement and the task-authorized demonstrations only when
   that problem's turn begins.

The same ordered 15 tasks must be used in all six conditions. Order effects
must be handled by one preregistered policy; ad hoc reshuffling after seeing an
outcome is forbidden. The pilot does not authorize the remaining 135 tasks.

## Freeze record

Before task selection, record and hash:

- exact Kaggle task slugs and version numbers;
- exact dataset distribution and content digest;
- exact GPT-5.6 Sol model slug, provider revision, and availability evidence;
- full bare, Hearthline, and task-local Gloss system definitions;
- prompt template and message-role ordering;
- temperature, top-p, seed support, stop rules, and maximum output;
- token, time, turn, tool, and monetary budgets;
- retry and repair policy;
- network and retrieval policy;
- generated-code sandbox policy;
- checkpoint and cache namespace policy;
- pilot selection method and sealed-manifest destination;
- receipt schema and artifact destinations;
- Astra-exclusion attestation and cutoff.

If a field cannot be frozen or the platform does not expose it, mark it
`UNAVAILABLE` and assess comparability before running. Do not silently fill it
with a guessed default.

## Matched execution rules

Across paired conditions, hold constant every factor except the declared system
treatment and task form. In particular:

- use the same exact Sol model configuration;
- use the same ordered tasks and one fresh chat per problem;
- give each system the same problem material and evaluator-visible budget;
- prohibit internet, retrieval, cross-problem memory, and hidden-map access;
- reset task-local state, including Gloss, after every problem;
- do not expose private tests, expected outputs, language seeds, or the
  evaluator's full reverse map;
- apply one frozen retry policy;
- execute candidate code only inside the frozen sandbox;
- never repair an arm after observing another arm's result.

The upstream baseline notebook's visible checkpoint convention is keyed by
model tag. That is insufficient here. A checkpoint key must include experiment,
condition, task-set digest, model, system, sampling, budget, and attempt.

## Measurements

Preserve per task and condition:

- official outcome code and raw evaluator evidence;
- a separate disposition of `COMPLETED`, `TIMEOUT`, or
  `INFRASTRUCTURE_FAILURE`, without coercing the latter two into an official
  outcome;
- wall-clock latency and platform-reported model latency, kept distinct;
- input, output, cached, reasoning, and total tokens when exposed;
- platform-reported cost and the pricing source/time, when exposed;
- exact model and harness identifiers;
- task-local Gloss mappings used, with demonstration provenance;
- unresolved mappings requested;
- unsupported mappings proposed or emitted;
- reformulations that avoided an unavailable operation;
- retries, truncations, and checkpoint resumes.

Primary summaries are pass rate and learning tax for each system. Also report
the full failure distribution, per-difficulty results, paired per-problem
changes, and missing/errored observations. Do not convert missing results to
zero.

## Comparability labels

Use one of these labels on every result:

- `PUBLIC_OBSERVATION`: copied from a public surface; not our run.
- `VANILLA_REPRODUCTION_CANDIDATE`: bare-model result whose exact comparability
  audit is not yet complete.
- `VANILLA_REPRODUCTION`: exact public-task reproduction with evidence.
- `DERIVED_SYSTEM_RESULT`: Hearthline or task-local Gloss changes the system.
- `ROSETTA_DERIVED_FRESH_SALT`: a separately specified mapping regeneration.

Hearthline and task-local Gloss results remain `DERIVED_SYSTEM_RESULT` even if
they use the public tasks and scorer. They must not inherit a public leaderboard
rank.

## Astra-exclusion gate

`ROSETTA-001` is intended to be Astra-excluded, but that property is not yet
attested or frozen. Before selection, a human-approved record must define what
counts as Astra participation, the exclusion interval, permitted non-Astra
tooling, who may view the sealed pilot, and the consequence of a breach.

Until that record exists, report `REQUIRED_UNATTESTED_NOT_FROZEN`. A later
assertion cannot retroactively make already exposed task material sealed.

## Security boundary

Rosetta executes model-generated code after translation. A 30-second timeout is
not a complete sandbox. Before any local evaluator run, freeze operating-system
isolation, filesystem mounts, process and memory limits, network denial, secret
removal, output caps, and cleanup behavior. Kaggle execution remains an external
dispatch with its own terms and quota.

## Interpretation limits

The underlying AtCoder tasks are public and date from 2023–2024. The public
generator and deterministic mappings are reproducible. Consequently,
“contamination-free” is retained only as the author's description, not as a
verified property of a future model.

A fresh sealed salt can reduce exposure of exact mappings, but it does not make
the underlying algorithms private and it produces a Rosetta-derived result, not
the public benchmark. The Python control helps separate ordinary coding ability
from interface cost; it cannot prove that an algorithm was newly derived.

## Promotion rule

Advance beyond the 15-task pilot only after all six conditions complete under
the frozen protocol, no holdout or cross-arm contamination occurs, missing and
external failures are retained, the result package passes an independent audit,
and a human explicitly authorizes further task consumption.

Preparation never earns a scientific conclusion or full-benchmark run.
