# Arena PNP — the circuit garden

**Official target:** determine whether `P = NP`.

**Genesis state:** `PLAY / NO_COMPLEXITY_CLASS_CLAIM`

P versus NP is the cleanest first public game because every small-board move
can be exact. Its danger is equally clean: no collection of fixed finite
boards establishes an asymptotic statement over all input lengths.

## Level 0: exact small Boolean circuit garden

Choose, before a run:

- a Boolean function family;
- a fixed input width `n`;
- an exact gate basis and fan-in rule;
- an exact size bound `s`;
- whether constants and negated inputs are free;
- a canonical circuit encoding.

| Part | Arena binding |
| --- | --- |
| Board | All canonical circuits allowed by the fixed `(n, basis, s)` rules |
| Builder | Supplies a circuit claimed to compute the target truth table |
| Hunter | Supplies a mismatching input or a smaller equivalent circuit |
| Verifier | Exhaustively evaluates every one of the `2^n` inputs and, when minimality is claimed, enumerates every smaller canonical circuit |
| Win | Exact equivalence, an explicit counterexample input, or certified minimality on this finite board |

A winning receipt must contain the truth-table digest, circuit encoding and
digest, enumeration rules, checker digest, counts, and deterministic replay
command. The strongest possible Level 0 state is `certified_finite`.

## Why this game matters

The garden gives us a trustworthy adversarial harness: hypotheses die on the
smallest exact counterexample, symmetries can be quotiented explicitly, and
candidate lower-bound invariants can be tested before anyone spends months on
them. Its output can motivate a restricted theorem, but extrapolation from
finitely many small values of `n` is not a complexity lower bound.

## Later gates

1. Prove one invariant in a named restricted circuit or proof model.
2. Have Hunter identify the precise feature that blocks transfer to a stronger
   model.
3. Record any transfer lemma as a separate claim with all assumptions.
4. Do not state either `P = NP` or `P != NP` as a result unless an argument
   reaches the exact official quantifiers; even then its internal ceiling is
   `proof_candidate`.

**Locked official source:** `clay:p-vs-np:official-description:2022-bytes`
