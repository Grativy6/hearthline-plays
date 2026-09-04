# ROSETTA-001 task-local Gloss contract

## Identity

`ROSETTA-001 task-local Gloss` is a narrow experimental translation surface for
one Rosetta problem at a time.

It is not canonical Bridge Gloss, does not modify or instantiate the canonical
Bridge subsystem, and must not be cited as evidence about canonical Gloss. It
is also not Thulia and does not own a strategic or authority model.

## Purpose

Task-local Gloss makes the translation boundary inspectable:

```text
six supplied demonstration pairs
              |
              v
supported, provenance-bearing correspondences
              |
              v
Hearthline chooses an algorithm or reformulation
              |
              v
Gloss renders only supported constructions
```

Its value is not an extra answer generator. Its value is refusing to erase the
difference between a demonstrated correspondence and a familiar operation that
has no demonstrated synthetic constructor.

## Allowed inputs

For a Core problem, Gloss may receive only the six synthetic-to-Python
demonstration pairs, the candidate representation Hearthline asks it to check
or render, and the frozen parser and normalization rules declared before task
selection.

For a Python-control problem, Gloss receives no synthetic mapping material and
acts as a recorded no-op. It may not add hints, algorithms, examples, or extra
tokens to the Python arm.

Gloss must never receive a language seed, complete generator map, private test,
expected output outside the authorized prompt, another problem's mapping, a
previous arm's solution or outcome, or external retrieval.

## State model

Gloss state is created after the six demonstrations arrive and destroyed after
the problem receipt is sealed. It never crosses a problem boundary.

Every recorded correspondence has a source form, target form, direction, exact
demonstration provenance, normalization, status, final-candidate use count, and
conflict evidence. Status is one of `SUPPORTED`, `AMBIGUOUS`, `CONFLICTING`, or
`UNRESOLVED`.

Absence of evidence is `UNRESOLVED`, not negative evidence and not permission to
infer a token from ordinary Python knowledge.

## Permitted operations

Task-local Gloss may:

1. parse the supplied pairs using the frozen parser;
2. record exact or frozen-normalized correspondences with provenance;
3. detect repeated, ambiguous, or conflicting evidence;
4. check whether requested surface constructions are supported;
5. deterministically render a candidate using supported mappings;
6. return unresolved or conflicting requests to Hearthline;
7. emit an audit record of mappings used and requests refused.

Deterministic means the same frozen inputs and configuration produce the same
surface record and rendering. Any heuristic normalization must be declared and
hashed before pilot selection.

## Forbidden operations

Task-local Gloss may not choose the algorithm, solve the problem, invent a
synthetic word or operator, infer that a familiar Python operation must have a
token, consult the evaluator, execute code, use model pretraining as mapping
provenance, carry state between problems, allocate extra model calls, or coerce
an unresolved status to supported.

If Hearthline needs an unavailable operation, strategy remains with Hearthline:
it may construct a solution from operations already supported by the examples
or leave the request unresolved. Gloss records that boundary; it does not cross
it.

## Interface outcomes

For each requested translation, Gloss returns one of:

- `SUPPORTED_RENDER`: rendering plus supporting evidence;
- `AMBIGUOUS`: multiple supported renderings with no frozen resolution;
- `CONFLICTING`: supplied evidence conflicts under the frozen parser;
- `UNRESOLVED`: no demonstration supports the requested construction;
- `CONTRACT_ERROR`: invalid input or an attempted boundary violation.

Only `SUPPORTED_RENDER` may enter a candidate solution. A future protocol may
allow Hearthline to reformulate after another outcome, but its retry and
reformulation budget must be frozen and matched.

## Audit record

Each problem-level receipt must bind the experiment and condition IDs, opaque
task position, task-set digest, Gloss implementation and configuration digests,
demonstration digest, ordered correspondences, every request and status, final
used mapping set, friction counts, state-reset confirmation, and confirmation
that no seed, full map, test, retrieval, or cross-task state was available.

Do not store private task material in a public receipt. Use digests and opaque
identifiers where disclosure would expose or consume the sealed pilot.

## Relationship to Thulia

Thulia may later observe aggregate friction such as recurrent `UNRESOLVED`,
`AMBIGUOUS`, or `CONFLICTING` events. It need not and must not maintain a
duplicate mapping ledger. No Thulia intervention or result is part of the six
conditions unless a future preregistered experiment explicitly adds one.

## Claim boundary

A task-local Gloss benefit would be evidence about this frozen adapter within
this derived system experiment. It would not establish a property of canonical
Bridge Gloss, Thulia, bare GPT-5.6 Sol, or the public Rosetta leaderboard.

This contract is prepared but not implemented, frozen, or run.
