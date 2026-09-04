# Hearthline ARC-AGI-3 launch layer

The movable launch kit for this title branch lives in [`launch/`](launch/README.md).

**Current state:** `OFFLINE_CANDIDATE_SOURCE_READY_HUMAN_GATES_CLOSED`

This branch descends from the prepared ARC-AGI-3 research station. Five
completed public-orientation workflow artifacts are reconciled into sanitized
successor receipts. Their legacy status and sealed/founding bytes remain
unchanged. The branch now also contains an offline-default `MyAgent`, a
deterministic ignored notebook package, and two closed human gates.

It does **not** contain credentials, private holdout material, a tracked Kaggle
submission, a competition run, or standing account authority. The historical
orientation grant is expired and spent; no new ARC contact is authorized.
Offline compatibility is bounded by `launch/source-lock.v3.json` and the exact
starter contract. Gate A may authorize one private kernel stage only; Gate B is
a later, separate, manual competition decision.

See `launch/status/current.json` for the mutable current projection and
`launch/gates/README.md` for the fail-closed handoff. Generated artifacts stay
ignored under `build/`; only exact committed regeneration produces the
content-addressed snapshot named by a gate.
