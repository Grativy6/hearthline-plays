# Hearthline Millennium Playground

**State:** `GENESIS_SEALED / PLAY_NOT_PROOF`

**Human author and steward:** Christopher D. Pang

**Hearthline and PAL:** disclosed AI-assisted research tools, without
authorship or mathematical authority

This is a place to treat hard mathematics as adversarial, exact games while
keeping every promotion honest. A game may produce a counterexample, a finite
certificate, a restricted theorem, a useful failed route, or eventually a
proof candidate. None of those is silently relabeled as a solution to an
official Millennium Prize Problem.

## The first three arenas

| Arena | First game | Honest ceiling of that game |
| --- | --- | --- |
| [Riemann](arenas/riemann/ARENA.md) | Continue the steward's privately committed checkpoint; attack one explicit residual at a time | Private research checkpoint or restricted lemma |
| [P versus NP](arenas/p-vs-np/ARENA.md) | Exact small Boolean circuit garden | Exhaustively certified finite result |
| [Geometry](arenas/geometry/ARENA.md) | Poincare control lane plus separately gated Hodge frontier | Reproduced control result or restricted geometry lemma |

The shared rules live in [`PLAY_PROTOCOL.md`](protocol/PLAY_PROTOCOL.md).
The claim-state map lives in [`CLAIM_STATES.md`](protocol/CLAIM_STATES.md).

## What the seal means

The public genesis records the exact parent lineage anchor, official-source
digests, arena boundaries, and an opaque commitment to a private Riemann
checkpoint. Git contains neither that private artifact nor its reveal data.

The seal establishes integrity and disclosed ancestry of these bytes. It does
not establish correctness, originality, exclusive authorship, complete
disclosure, absence of undisclosed assistance, prize eligibility, or Clay
Mathematics Institute recognition.

Run the offline verifier:

```bash
python3 millennium/tools/verify_genesis.py
```

The authoritative problem statements and the revised prize rules are linked
and byte-locked in
[`clay-official-sources.lock.json`](research/clay-official-sources.lock.json).
The official Clay overview is
<https://www.claymath.org/millennium-problems/>.
