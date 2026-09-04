# Hearthline Farm — Kaggriculture

A public Hearthline/Sol experiment in which the game supplies the world, the rules, and the current state—and Hearthline has to make the farm work.

## Founding direction

> "spin it up like it's in FS and hearthline has to make a farm work. they already tell you the rules and what you have available. should be easy, right? idk, lol"
>
> — Christopher D. Pang, 3 September 2026

No manual strategy journal is required from Chris. No copied leaderboard strategy is the starting point. Hearthline/Sol must enter through the public rules, inspect the state actually supplied, act, preserve what happened, and improve from its own local runs.

## Campaign model

- **World and referee:** the pinned public Kaggriculture environment.
- **Player:** the Hearthline farm policy.
- **Operator, architect, and accountable human:** Christopher D. Pang.
- **Season:** one 720-turn campaign by default.
- **Day:** one 24-turn planning and execution interval.
- **Canonical state:** the environment observation and replay, not optional narration.
- **Goal:** finish with more money in the bank than the opponent. Unsold inventory is not score.

The optional human-readable view may feel like Finis Solutus—a current state, available actions, a chosen move, and a persistent consequence—but it must never overwrite the environment's actual state.

## Lineage and source lock

- Parent series anchor: `kaggle/main` at `b88571603698205c2be94b7b0d652fa3c096d67d`.
- Shared playground parent: `main` at `986288008f5fa21aec8ebb0b73b0d98ccecaaf6a`.
- Public environment source: `Kaggle/kaggle-environments`.
- Kaggriculture environment revision: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
- Declared environment version at that revision: `0.1.0`.
- Controlling public files: `kaggle_environments/envs/kaggriculture/{README.md,AGENTS.md,kaggriculture.json,kaggriculture.py}`.

A later source revision is a new dependency and must be recorded before comparison.

## Astra-excluded development boundary

This branch is reserved for the Christopher D. Pang + PAL-informed Hearthline + GPT-5.6 Sol lineage through its first sealed result. GPT-6 Astra output, code, strategy, analysis, recommendation, or runtime inference is not authorized to enter this branch before that result. Any later Astra-assisted work belongs in a clearly named successor branch with its own receipt.

This is a provenance boundary, not a claim that awareness of Astra's public existence is a technical contribution.

## Build 001

The first build should get Hearthline into the actual world quickly:

1. Load the pinned public environment locally.
2. Convert each observation into a compact farm state and obligation list.
3. Generate only schema-valid actions for the farmer, any hired hands, and the market.
4. Complete full seasons without crashes, timeouts, silent shed overflow, or forgotten endgame liquidation.
5. Run matched seeded games against the built-in `starter` agent in both seats.
6. Preserve replay, metrics, source revision, code hash, and result receipt.

The initial target is not an optimal farm. It is a farm that **lives through the season, learns where it loses money, and beats the single-tile carrot loop on unseen seeds**.

See [`AGENTS.md`](AGENTS.md) and [`launch/BUILD_001.md`](launch/BUILD_001.md).

## Authorization boundary

Local public-environment development and testing are authorized. This branch contains no Kaggle credentials, private holdout material, official submission, or standing authority to join the competition, spend money, use an account, or submit an entrant. Those remain separate human actions.

## License

Original project material follows the repository's CC BY 4.0 license unless a file says otherwise. Kaggle's code, rules, assets, names, and trademarks retain their own terms.
