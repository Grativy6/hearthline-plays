# Hearthline/PAL play protocol v1

## Aim

Turn an intimidating conjecture into a sequence of exact games without
weakening its quantifiers or overstating what a win means.

Every game has five named parts:

| Part | Required content |
| --- | --- |
| Board | The finite or formal objects currently in play |
| Legal moves | Transformations allowed by an exact definition |
| Adversary | Counterexample search, incompatible case, lower-bound attack, or dependency audit |
| Verifier | Deterministic test or explicit proof obligation |
| Promotion gate | The strongest claim state the result may enter |

## Turn loop

1. **Bind.** Copy the precise target, definitions, quantifiers, dependencies,
   and source digest into a run receipt.
2. **Compartment.** Choose one bounded board. Record what has been left out.
3. **Play.** Let Builder propose an invariant, construction, algorithm, or
   proof step. Let Hunter seek the smallest counterexample or missing case.
4. **Check.** Use exact arithmetic, exhaustive enumeration, a proof kernel, or
   a human-auditable argument appropriate to the board.
5. **Score.** Record certificates, counterexamples, restricted lemmas, and
   killed hypotheses. Testing finitely many instances supports only the
   declared finite domain unless a proved exhaustive reduction covers the
   general target.
6. **Classify or reopen.** Apply only the claim state whose gate is met.
   Generalizing the scope creates a new claim rather than upgrading the finite
   one. Otherwise preserve the residual and a reproducible reopening handle.

Builder and Hunter are roles within a workflow, not independent witnesses
when they share a model, prompt history, source corpus, or operator.

## Mandatory stop rules

- Testing only finitely many instances, without a proved exhaustive reduction,
  does not settle an unbounded statement.
- Numerical agreement does not become an exact identity.
- Failure to find a counterexample is not proof of absence.
- A restricted-model lower bound is not a lower bound for unrestricted
  computation.
- A simulation is not a regularity or existence proof for a PDE.
- A suggestive geometric picture is not an algebraic-cycle construction.
- A proof checker certifies only the encoded statement under its declared
  axioms, trusted kernel, and dependency set.
- A shared AI lineage is not independent corroboration.
- Ambiguous evidence stops at its lower claim state.

## Receipt rule

Every material run appends a JSON receipt conforming to
[`run-receipt.v1.schema.json`](../schemas/run-receipt.v1.schema.json). A
receipt identifies parents, sources, runtime evidence, exact artifacts,
claim-state deltas, known gaps, and assistance provenance. In v1, a discovered
correction is a new `correction` event whose sole parent is the event being
corrected; it never rewrites the prior receipt. A `merge` names two or more
parents, and a `release` names the head or heads it publishes.

Every JSON event has an ID computed from the canonical event payload, excluding
the ID field itself:

```text
SHA-256(UTF8("HEARTHLINE-MILLENNIUM-EVENT-V1\0") || RFC8785_JCS(payload))
```

Canonical JSON follows RFC 8785 JCS. Receipts additionally prohibit
floating-point numbers and use ASCII object-member names, making the included
standard-library verifier a complete implementation for this restricted
profile. Parent event IDs create a DAG.

No-Astra status is per contribution, not magic inherited from a branch name.
For materially incorporated inputs, `present` dominates `unknown`, which
dominates `session_declared_absent`; the aggregate cannot improve on any input.
A parent receipt edge alone does not incorporate all parent artifacts. The run
must list what it actually used. An opaque commitment whose contents were not
opened is a reference, not an incorporated mathematical input.

Version 1 also admits a `protocol_upgrade` event in the `protocol` arena. It
uses the same content-addressed receipt and artifact checks to bind a new,
versioned verifier, schema, or test at a new path. Canonical genesis files and
previously receipted artifacts are never replaced. The frozen workflow
discovers `millennium/tools/verify_upgrade_*.py`, so later checks can be added
without weakening or rewriting v1. An upgrade is published before artifacts
that depend on it, and its successor verifier must continue checking the v1
genesis and receipts as well as the new version.

Signatures and external timestamps append as sidecars keyed to the immutable
event ID. Until then, Git history is public publication evidence, not a trusted
timestamp or a human cryptographic signature. `SHA256SUMS` and the verifier
check internal consistency; the exact published Git commit supplied out of
band is the trust root for this genesis.
