# Pair Static — tied Sparks with a non-recursive comparison return

**Design status:** `IMPLEMENTABLE_DRAFT`  
**Task role:** representation and comparison  
**Authority:** none beyond the current external grant

## Shape

```text
                         same task and snapshot
                                  |
                    +-------------+-------------+
                    |                           |
                 Spark A                     Spark B
             declared lens A             declared lens B
                    |                           |
                Static A                    Static B
                    +-------------+-------------+
                                  |
                         Pair Scribe Spark
                                  |
                    Pair Static P (new ledger)
                                  |
                              Thulia
                                  |
                    Hearthline-facing custody index
```

The useful result is one outward comparison object whose internal cut remains readable.

## Three-ledger rule

- Spark A writes only Static A.
- Spark B writes only Static B.
- The Pair Scribe reads the admitted projections of A and B and writes **Static P**.
- Static P cites A and B; it never replaces or edits them.
- Thulia stores identities, status, source handles, and reopening routes. She does not solve the task or choose an action.

This prevents “two loose answers” without flattening the pair into one unsupported conclusion.

## Pair Scribe job

The Pair Scribe may:

- normalize claim IDs and compare their typed values;
- mark agreements, disagreements, unique claims, and shared dependencies;
- preserve each estimate under its own account;
- identify a likely load-bearing seam;
- propose at most one discriminating test or observation;
- compress only what the receiving boundary does not need immediately; and
- retain source handles to every omitted detail.

It may not:

- solve the original task a third time;
- average probabilities without a declared pooling rule;
- treat two passes through one model/context as independent evidence;
- edit either source Static;
- launch the proposed test;
- grant itself another Scribe;
- recursively compare its own comparison; or
- promote agreement into truth, permission, or action authority.

## Probability discipline

Two outputs are usually conditional estimates:

```text
estimate A = P(outcome | model A, evidence A)
estimate B = P(outcome | model B, evidence B)
```

Until calibration and dependency structure justify a pool, Pair Static retains the pair rather than averaging it. Its default is:

```yaml
pooling_rule: NONE
```

The disagreement may be the most useful result.

## Natural stops

The Pair Scribe returns when:

- agreement is sufficient for Hearthline's current decision;
- one discriminating test is identified;
- disagreement cannot be resolved under present evidence;
- the two Statics contain no material difference; or
- source integrity, scope, or budget is insufficient.

A proposed test reopens through Hearthline or the controller. It does not loop automatically.

## Compression law

Each handoff makes a new trace:

```text
substantive work
  -> Spark Static
  -> Pair reconstruction and comparison
  -> Pair Static
  -> Thulia custody projection
  -> Hearthline decision
```

A summary is never treated as the whole source. Every material omission keeps an address back to the richer ledger.
