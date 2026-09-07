# Hearthline ARC-AGI-3 launch layer

The movable launch kit for this title branch lives in [`launch/`](launch/README.md).

**Current state:** `FROZEN_POST_STAGE_SUCCESSOR_LOCAL_REPAIR_ONLY`

This branch descends from the prepared ARC-AGI-3 research station. Five
completed public-orientation workflow artifacts are reconciled into sanitized
successor receipts. Their legacy status and sealed/founding bytes remain
unchanged. Private kernel version 4 subsequently completed, and Christopher D.
Pang reviewed its output and full 875-distribution runtime inventory. The
resulting `FROZEN_POST_STAGE_SUCCESSOR` closure is evidence for this local
repair, not proof that the repaired successor has run.

It does **not** contain credentials, private holdout material, a tracked Kaggle
submission, a competition run, or standing account authority. Expired grants
remain immutable and unusable. Offline compatibility is bounded by
`launch/source-lock.v4.json` and the exact starter contract; the public ARC-AGI
0.9.9 pin and reviewed Kaggle runtime are deliberately separate. Both human
gates are closed. The exact successor snapshot is generated from the final
local commit and recorded in an ignored local verification receipt rather than
embedded self-referentially in this tracked file. Before Gate B can even be
considered, that snapshot must receive a fresh Gate-A grant and complete one
exact private restage with a reviewed v4 result.

See `launch/status/current.json` for the mutable current projection and
`launch/gates/README.md` for the fail-closed handoff. Generated artifacts stay
ignored under `build/`; only exact committed regeneration produces the
content-addressed snapshot named by a gate.
