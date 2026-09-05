# Rosetta public playground

## What is public

RosettaBench has public surfaces, but it is not divided into an ARC-style
public game set and a separately documented hidden evaluation set.

The public benchmark collection contains two version-1 task forms:

- [RosettaBench Core](https://www.kaggle.com/benchmarks/tasks/namanbnsl/rosettabench-core),
  which asks models to work through a fresh problem-local symbolic interface;
- [RosettaBench Python Baseline (Control)](https://www.kaggle.com/benchmarks/tasks/namanbnsl/rosettabench-python-baseline-control),
  which presents the same 150 underlying problems in ordinary Python.

The [public benchmark and leaderboard](https://www.kaggle.com/benchmarks/namanbnsl/rosetta),
[public repository](https://github.com/namanbnsl/RosettaBench), public
notebooks, and public dataset mirrors make the benchmark inspectable and
reproducible. The repository exposes the mapping generator and fixed seed
procedure. The dataset includes fields called `public_test_cases` and
`private_test_cases`, but both fields are distributed on a public dataset
surface. Here, `private` is an upstream field name, not evidence of a sealed
Rosetta holdout.

That makes Rosetta especially useful as a **public practice environment** for
rule acquisition. It does not make its public tasks a fresh or secret test for
Hearthline.

All exact URLs and source pins are recorded in
[`playground/public-resources.v1.json`](../playground/public-resources.v1.json).
The example route policy is
[`playground/routes.example.toml`](../playground/routes.example.toml).

## What this playground is for

The playground treats the score as a byproduct. Its immediate learning targets
are:

1. **Acquire the local rule system.** Record only correspondences earned from
   the supplied examples.
2. **Separate evidence from assumption.** Mark an unavailable construction
   `UNRESOLVED`; familiarity is not evidence.
3. **Reformulate.** Build the goal from supported operations when the obvious
   operation has not been supplied.
4. **Reset.** Destroy the mapping ledger when an episode ends. A token may mean
   something different in the next local system.
5. **Reflect.** Preserve what was supported, refused, reformulated, and reset
   before looking at a score.

The default route uses the wholly original
[`orientation-deck.v1.json`](../playground/micro/orientation-deck.v1.json).
It contains no Rosetta task row, test, generated map, author solution, or
upstream code. It can be played by hand with zero model calls.

## Reusable learning kit

Run the complete offline check first:

```text
py tools/verify_public_playground.py
```

List the original episodes, then reveal only the learner-facing side of one:

```text
py tools/show_public_micro_episode.py
py tools/show_public_micro_episode.py LANTERN-LEDGER-01
```

After the answer is written and sealed, the coach side requires an explicit
gate:

```text
py tools/show_public_micro_episode.py LANTERN-LEDGER-01 --coach-view --answer-sealed
```

The `hearthline_learning` package is deliberately smaller than a solver. Its
`LearningLedger` accepts caller-supplied observations with provenance, resolves
only exact supported forms, retains ambiguity and conflict, refuses unresolved
requests, seals a deterministic receipt, and requires a close/reset transition
before a new problem. It has no strategy, network, model, evaluator, data
loader, or code-execution surface.

```python
from hearthline_learning import (
    EvidenceSourceKind,
    LearningLedger,
    LearningScope,
    Provenance,
)

ledger = LearningLedger(LearningScope("lantern-0001", "LANTERN-LEDGER-01"))
ledger.observe_supported(
    "mark",
    "sela",
    Provenance("D1", EvidenceSourceKind.ORIGINAL_MICRO_FIXTURE, ordinal=1),
)
supported = ledger.resolve("mark")
withheld = ledger.resolve("reverse")
receipt = ledger.close()
reset_receipt = ledger.reset(
    LearningScope("lantern-0001", "LANTERN-REFORMULATE-01")
)
```

The default `DIGESTS` receipt hashes task-local forms and opaque source/scope
identifiers. Provenance classes remain caller-declared rather than verified,
and every receipt says that a public-release review is still required. `RAW`
mode is explicit and includes the forms and identifiers; it should remain local
unless separately reviewed.

Create a zero-activity session scaffold on a non-`E:` destination:

```text
py tools/new_public_learning_session.py --output-root C:\HearthlineData\RosettaBench\playground\sessions --mode micro_fixture --session-id lantern-0001 --problem-id LANTERN-LEDGER-01 --learning-goal "Practice evidence-bounded rule acquisition and reset."
```

The session trace has places for evidence IDs, withheld assumptions,
reformulations, reflection, answer-before-coach state, score/match as a
byproduct, and SHA-256 bindings to source, ledger, and reset receipts. An empty
scaffold is marked `RECEIPTS_UNBOUND`. Validate it without performing the
session:

```text
py tools/validate_public_learning_session.py templates/public-learning-session.v1.json
```

For a completed manual micro episode, set the recorded digests and
`VERIFIED_WITH_SUPPLIED_RECEIPTS`, then supply the actual receipt documents:

```text
py tools/validate_public_learning_session.py <SESSION.json> --ledger-receipt <LEDGER.json> --reset-receipt <RESET.json>
```

The validator recomputes both self-digests and verifies the reset-to-ledger
link. This establishes internal receipt consistency, not the truth of
caller-declared provenance or permission to publish the trace.

`public_core` and `public_python` select exact pinned version-1 URLs. A
nonzero model budget is only a future plan and is capped at one; evaluator and
candidate-code budgets remain zero. For example, this writes a plan but does
not open the task or call the model:

```text
py tools/new_public_learning_session.py --output-root C:\HearthlineData\RosettaBench\playground\sessions --mode public_core --session-id core-orientation-0001 --problem-id public-core-unselected --learning-goal "Study evidence and reformulation on one public exercise." --model-calls 1 --future-plan "One fresh-chat call after separate task-access and model-use authorization."
```

## Low-usage loop

Use one short episode at a time:

```text
read demonstrations
       |
       v
write a provenance-bearing rule ledger
       |
       v
label each requested operation SUPPORTED or UNRESOLVED
       |
       v
reformulate from supported operations if needed
       |
       v
answer once, record assumptions, then reset state
```

A good orientation session is:

1. Play one micro episode manually. Model calls: `0`.
2. If a model comparison is explicitly wanted later, replay that one episode
   in one fresh chat. Model-call ceiling: `1`.
3. Record the ledger, unresolved requests, reformulation, and reset receipt.
4. Stop. Do not promote a pleasant result into a benchmark claim.

No retry is part of this loop. A second attempt changes the exercise and needs
its own declared purpose.

## Routes

### `micro_original`

This is the default. It is local, tiny, and data-free. The coach should expose
only an episode's `learner_view`, then compare the response with `coach_view`
after the answer is sealed. These fixtures teach the target habits; they are
not held-out measurements.

### `public_source_read`

This opens pinned public descriptions, repository views, and notebooks for
study. It does not copy their contents into this repository, authenticate,
download data, or invoke a model. The Core and Python task pages remain the
separate disabled reference routes below. Use this route to understand the
benchmark's construction and limitations.

### `public_leaderboard_observe`

This reads only the public leaderboard. Every copied row is labeled
`PUBLIC_OBSERVATION`: it is somebody else's public run, not Hearthline evidence.
Leaderboard state can drift, so any later use needs a fresh timestamp.

### `public_core_reference` and `public_python_reference`

These routes point to the public Kaggle task pages but are disabled. Each full
task contains 150 model-facing problems; running either would be a substantive
evaluation, not a low-usage orientation. The upstream Core notebook also has a
small debug path, but using it would still require external data and model
authority. The original micro route gives the immediate lesson without
consuming an upstream row.

### `bulk_dataset`

This route is unset and disabled. No data root is selected. A future authorized
materialization must use a user-selected fixed internal drive or explicit
external storage. `E:\` is prohibited because this Corpus checkout is on the
removable workspace and must not become a bulk-data cache.

Setting a path in the example file does not authorize a download.

## Current Terra row

At `2026-09-04T23:15:42Z`, the public Kaggle leaderboard reported GPT-5.6
Terra at:

| Task form | Public score |
| --- | ---: |
| RosettaBench Core v1 | `0.49333333333333335` |
| Python Baseline v1 | `0.8933333333333333` |
| Display-independent difference | `0.4` |

Classification: `PUBLIC_OBSERVATION`.

This row is not our run, not a Hearthline result, and not evidence from
`ROSETTA-CAL-001`. The difference is a direct arithmetic summary of two public
scores; it does not establish why they differ.

## Separation from the formal records

### `ROSETTA-001`

The formal six-condition experiment remains `PREPARED_NOT_RUN`. Its pilot is
`PILOT_UNSELECTED_UNCONSUMED`, its task identities remain sealed and
unselected, and its Astra-exclusion gate remains unattested. Playing an
original micro fixture or reading a public page does not select, consume, or
partially run that pilot.

### `ROSETTA-CAL-001`

The private calibration attempt is terminally blocked after Kaggle run 1233792
failed at parquet loading. It made zero prompt, model, and evaluator calls. The
public Terra leaderboard row above must never be substituted for those missing
calibration outcomes. This playground grants no repair, retry, task update,
download, or publication authority.

## Link-only and licensing boundary

Public visibility is not one uniform reuse license. At the pinned snapshot:

- the RosettaBench GitHub repository has no license file;
- the Core task license is unresolved here;
- the Hugging Face mirror uses the underspecified label `cc`;
- other surfaces declare different licenses that do not transfer across
  repositories or artifacts.

For that reason, this layer links to and pins public sources without copying
upstream code, notebooks, task rows, tests, generated maps, or model outputs.
The micro deck is original Hearthline material and is explicitly marked as
practice rather than Rosetta evidence.

## Claim ceiling

Public play can support observations about a learning process: whether a
participant tracked provenance, withheld an unsupported mapping, found a
supported reformulation, reset local state, and reflected accurately.

It cannot by itself establish a Rosetta score, learning tax, causal Gloss
benefit, durable learning, contamination freedom, ARC-AGI-3 transfer, or formal
`ROSETTA-001` result.
