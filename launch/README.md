# Hearthline ARC-AGI-3 launchpad

**Branch:** `arc-agi/titles/arc-agi-3-hearthline-launch-20260903`  
**Parent station:** `74728f8c4ec9409bd0e6c8064a0b6b356da776f6`  
**Current phase:** `PUBLIC_ORIENTATION_AUTHORIZED`  
**Competition/Kaggle phase:** `NOT_AUTHORIZED_NOT_STARTED`

This is a removable launch layer over the earlier research station. It keeps the founding prompt, exact public-source locks, practice requests, compact world models, Spark/Pair-Static records, runner tools, and run receipts in distinct directories so later cleanup can move or delete one layer without rewriting the others.

## Fast map

| Path | Purpose |
|---|---|
| [`launch/FOUNDER_SENDOFF.md`](FOUNDER_SENDOFF.md) | Preserved human founding objective |
| [`launch/RUN_GRANT_2026-09-03.md`](RUN_GRANT_2026-09-03.md) | Exact current public-orientation grant and exclusions |
| [`launch/source-lock.v2.json`](source-lock.v2.json) | Repository, toolkit, harness, and public-analysis identities |
| [`launch/ASTRA_PUBLIC_BLUEPRINT.md`](ASTRA_PUBLIC_BLUEPRINT.md) | Publicly observed design lessons; no hidden-reasoning claim |
| [`design/PAIR_STATIC.md`](../design/PAIR_STATIC.md) | Two Sparks, two source Statics, one comparison Static, then Thulia custody |
| [`schemas/`](../schemas/) | Movable JSON contracts for Statics, world models, plans, requests, and receipts |
| [`templates/`](../templates/) | Empty, human-readable starting objects |
| [`practice/`](../practice/) | Explicit public-game requests and local world-model state |
| [`tools/`](../tools/) | Standard-library validation plus the narrow public replay broker |
| [`tests/`](../tests/) | Offline tests; no ARC contact |
| [`.github/workflows/arc3-orientation-probe.yml`](../.github/workflows/arc3-orientation-probe.yml) | Networked replay and artifact capture, triggered only by a request-file change |

## Portable layers

1. **Source layer:** locators and immutable identities; no corpus bytes.
2. **Policy layer:** founding objective, current grant, stop rules.
3. **Representation layer:** Spark Static, Pair Static, world model, operator map, plan.
4. **Execution layer:** explicit action request and narrow broker.
5. **Evidence layer:** workflow run, artifact, scorecard, and manually admitted receipt.

No layer may silently fill a missing field from another. In particular, the representation layer proposes what may happen; the execution request names what the broker may send; the returned environment observation establishes what happened.

## Run discipline

`present state != operator model != plan != action != outcome`

The compact world model keeps these five surfaces separate. Every action has a hypothesis and expected observable. Every returned frame may update the state and operator model, but does not retroactively justify the action. A failed expectation is retained as information.

## Current natural stop

The launchpad may prepare and perform bounded **public orientation**. It must stop before Kaggle, competition mode, a paid model call, credential use, or any non-public game.
