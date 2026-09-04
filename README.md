# Hearthline Farm — Kaggriculture

A public Hearthline/Sol experiment in which the game supplies the world, the rules,
and the current state—and Hearthline has to make the farm work.

## Build 001 result

**The farm works.** The frozen deterministic candidate completed and won all **24
unseen matched games** against Kaggriculture's built-in `starter`, covering twelve
seeds in both seats under the byte-verified pinned interpreter. Median bank
advantage was **+$31,485**; all named completion, parity, timing, care, overflow,
and liquidation checks passed.

This is a local pinned-interpreter result, not an official Kaggle score. See
[`launch/BUILD_001_RESULT.md`](launch/BUILD_001_RESULT.md), the
[`evaluation manifest`](launch/evaluation-manifest-v1.json), and the
[`unseen evaluation receipt`](receipts/build001-pinned-unseen-summary.json).

## Founding direction

> "spin it up like it's in FS and hearthline has to make a farm work. they already tell you the rules and what you have available. should be easy, right? idk, lol"
>
> — Christopher D. Pang, 3 September 2026

No manual strategy journal is required from Chris. No copied leaderboard strategy
is the starting point. Hearthline/Sol must enter through the public rules, inspect
the state actually supplied, act, preserve what happened, and improve from its own
local runs.

## Campaign model

- **World and referee:** the pinned public Kaggriculture environment.
- **Player:** the Hearthline farm policy.
- **Operator, architect, and accountable human:** Christopher D. Pang.
- **Season:** one 720-step campaign by default, containing 719 agent-action transitions after initialization.
- **Day:** one 24-turn planning and execution interval.
- **Canonical state:** the environment observation and replay, not optional narration.
- **Goal:** finish with more money in the bank than the opponent. Unsold inventory is not score.

The optional human-readable view may feel like Finis Solutus—a current state,
available actions, a chosen move, and a persistent consequence—but it must never
overwrite the environment's actual state.

## Run locally

Python's standard library is sufficient. First fetch the two exact public referee
files and verify their Git blob identities; then run one season or the frozen set.
`pytest` is needed only for the small agent tests.

```bash
python scripts/fetch_pinned_source.py
python scripts/run_pinned.py --seed 101 --seat 0 --out runs/first-furrow-actions.json
python scripts/evaluate_exact.py --set unseen
pytest -q tests/test_agent.py
```

The full instrumented Build 001 harness and replay are preserved in the sealed
reproducibility package named in the result receipt. Generated replays stay under
ignored `runs/`.

## Lineage and source lock

- Parent series anchor: `kaggle/main` at `b88571603698205c2be94b7b0d652fa3c096d67d`.
- Shared playground parent: `main` at `986288008f5fa21aec8ebb0b73b0d98ccecaaf6a`.
- Public environment source: `Kaggle/kaggle-environments`.
- Kaggriculture environment revision: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
- Declared environment version at that revision: `0.1.0`.
- Controlling public files: `kaggle_environments/envs/kaggriculture/{README.md,AGENTS.md,kaggriculture.json,kaggriculture.py}`.

A later source revision is a new dependency and must be recorded before comparison.

## Astra-excluded development boundary

This branch is reserved for the Christopher D. Pang + PAL-informed Hearthline +
GPT-5.6 Sol lineage through its first sealed result. GPT-6 Astra output, code,
strategy, analysis, recommendation, or runtime inference did not enter Build 001.
Any later Astra-assisted work belongs in a clearly named successor branch with its
own receipt.

This is a provenance boundary, not a claim that awareness of Astra's public
existence is a technical contribution.

## Build 001

The first build got Hearthline into the actual world quickly:

1. load the pinned public environment locally;
2. convert each observation into a compact farm state and obligation list;
3. generate only schema-valid actions for the farmer, hired hands, and market;
4. complete full seasons without crashes, timeouts, shed overflow, or forgotten liquidation;
5. run matched seeded games against built-in `starter` in both seats;
6. preserve source identities, candidate hash, raw results, actions, and receipts.

The initial target was not an optimal farm. It was a farm that **lived through the
season, learned where it lost money, and beat the single-tile carrot loop on unseen
seeds**. Build 001 closed that named local target.

See [`AGENTS.md`](AGENTS.md), [`launch/BUILD_001.md`](launch/BUILD_001.md), and
[`launch/BUILD_001_RESULT.md`](launch/BUILD_001_RESULT.md).

## Authorization boundary

Local public-environment development and testing were authorized. This branch
contains no Kaggle credentials, private holdout material, official submission, or
standing authority to join the competition, spend money, use an account, or submit
an entrant. Those remain separate human actions.

## License

Except where a file says otherwise, original project material follows the
repository's CC BY 4.0 license. Referee files fetched from Kaggle's public source
retain the upstream Apache 2.0 license. The sealed local reproduction package
includes a copy of that license. Kaggle's names, assets, and trademarks retain
their own terms.
