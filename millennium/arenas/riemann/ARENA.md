# Arena RH — signed turns, not zero hunting

**Official target:** every nontrivial zero of the Riemann zeta function has
real part `1/2`.

**Genesis state:** `PRIVATE_CHECKPOINT_COMMITTED / NO_PUBLIC_PROOF_CLAIM`

## Inheritance rule

This arena does not restart the steward's Riemann work and does not publish
it. The genesis receipt contains an opaque salted commitment to the exact
private checkpoint supplied at founding. The reveal receipt and source bytes
remain outside Git.

The public repository may inherit only explicitly promoted outputs from that
checkpoint: a self-contained definition, lemma, counterfixture, verifier, or
proof candidate that the steward chooses to disclose in a later append-only
event. An opaque commitment is evidence of byte identity, not validation of
the mathematics inside it.

## First live game: one residual, two players

| Part | Arena binding |
| --- | --- |
| Board | One explicitly named residual from the private checkpoint, with all prerequisites copied into the private run receipt |
| Builder | Proposes a finite, prime-computable signed-turn construction or a narrower bridge lemma |
| Hunter | Searches for a violating character, scale, sign pattern, hidden dependence, or failed quantifier |
| Verifier | Exact symbolic checks and interval/error bounds where computation enters; human audit for every bridge |
| Win | A counterexample to the proposal, or a complete restricted lemma with its domain explicit |

The open official target is not scored by checking more zeros. Finite zero
verification can test implementation and eliminate candidates, but it cannot
prove a statement about all nontrivial zeros.

## Promotion gate

- A computation that only checks finitely many zeros, without a proved
  exhaustive reduction, stops at `certified_finite`.
- A complete lemma over a named restricted class may reach
  `proved_restricted`.
- A claim to RH itself may reach `proof_candidate` only when a self-contained
  argument addresses the official statement, every dependency is disclosed,
  and no known gap or unresolved proof obligation remains.
- This project cannot promote its own work to `externally_established`.

**Locked official source:** `clay:riemann:official-description:2022-bytes`
