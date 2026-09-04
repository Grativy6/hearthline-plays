# Build 001 Result — First Furrow

**Classification:** `CLOSED_IN_SCOPE_LOCAL_PINNED_INTERPRETER`

**Recorded:** 2026-09-04 UTC

**Candidate:** `main.py`

**Candidate SHA-256:** `c8408e411a433a5e9cebf90648302c20f7528e2119fc22c22bebe7cb0d49f193`

## Result

Hearthline entered the pinned public Kaggriculture world, completed full seasons,
and beat the built-in deterministic `starter` agent on every declared development
and unseen match.

| Evaluation | Games | Wins | Losses | Ties | Median advantage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Development seeds, both seats | 8 | 8 | 0 | 0 | +31,566.5 |
| Frozen unseen seeds, both seats | 24 | 24 | 0 | 0 | +31,485 |

Across the 24 unseen matches:

- Hearthline median final bank: **$34,989**
- Starter median final bank: **$3,504**
- Mean advantage: **+$31,606.75**
- Advantage range: **+$30,109 to +$34,483**
- Seat 0 median advantage: **+$31,485**
- Seat 1 median advantage: **+$31,485**
- Maximum observed Hearthline action time: **0.113504 seconds** under the one-second limit

The first complete season, seed 101 with Hearthline in seat 0, ended **$34,351 to
$3,427**. The farm planted sixteen melons twice, followed with late carrots, hired
five inexpensive hands each day, sold promptly, lost no crops to missed water or
decay, overflowed nothing, and ended with no sellable inventory.

## What was checked

The evaluator verified all of the following across the frozen unseen set:

- the pinned `kaggriculture.py` and `kaggriculture.json` Git blob identities;
- the frozen candidate hash and evaluation manifest;
- completion and reward/bank agreement for every season;
- zero candidate exceptions and zero malformed action shapes;
- every observed action returned under one second;
- exact action parity between the byte-verified interpreter run and a separately instrumented harness;
- exact canonical state parity after every one of 719 action transitions per game;
- final-state parity;
- zero preventable watering/feeding loss, crop-decay loss, shed overflow, suspected unit no-op, or sellable end-state inventory;
- positive median bank advantage overall and independently in both seats.

The detailed receipt is `receipts/build001-pinned-unseen-summary.json`; its row-level table
is `receipts/build001-pinned-unseen-raw.csv`. The evaluation seeds were frozen in
`launch/evaluation-manifest-v1.json` before the unseen run. A complete portable
reproduction bundle, including the full replay and instrumented parity harness, is
identified by `receipts/build001-reproducibility-package.json`.

## Policy earned in this build

Build 001 is intentionally small rather than generally optimal:

1. use sixteen nearby plots in the initially unlocked quadrant;
2. hire five cheap daily hands;
3. schedule care before profit;
4. route units greedily to unique work;
5. run two melon cycles and finish with carrots;
6. sell all shed inventory promptly;
7. preserve a valid `PASS` fallback.

It does not yet model animals, buy land, optimize against strong opponents, or
adapt production deeply to shop composition. Those are later branches, not hidden
claims inside this result.

## Exact boundary

This is a **local result under byte-verified public Kaggriculture interpreter and
specification blobs**. The exact interpreter was run directly through a minimal
local compatibility wrapper because the full `kaggle-environments` package could
not be installed in this network-restricted execution container. The interpreter
bytes and JSON bytes match the pinned upstream Git objects exactly; every action
and every resulting canonical state also matched the separately instrumented
harness.

Full execution through the packaged Kaggle SDK/competition loader, Kaggle account
use, rule acceptance, official submission, and leaderboard scoring remain
unperformed. Nothing in this result is an official Kaggle score.

## Lineage

Christopher D. Pang supplied the objective, PAL-informed architecture, direction,
and accountable decisions. GPT-5.6 Sol was the authorized AI development tool.
Hearthline is the resulting player policy. GPT-6 Astra supplied no output, code,
strategy, analysis, recommendation, or runtime inference to this lineage before
the Build 001 seal.

PAL supplied bounded trace, residual, comparison, local-closure, and reopening
discipline. The game result comes from the executed code and referee trace, not
from PAL terminology.
