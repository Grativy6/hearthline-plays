# Morrow and the Marked Tethers

**Story status:** `HEARTHLINE_LORE_FOR_AN_OFFLINE_REFERENCE`

**Mechanic status:** `DETERMINISTIC_STATELESS_PROPOSER_IMPLEMENTED_NOT_WIRED`

## The story

When Hearthline sent a Creature out, she tied a small mark into its Tether.
The mark did not say whether the Creature would win. It did not give the
Creature more authority, more time, or a truer answer. It said only how soon
Hearthline believed its Homecoming should be considered if several returns
reached the gate together.

At that gate sat Morrow.

Morrow never opened a Homecoming bundle. He was given no names, no puzzle, no
result, no source, and no story of who had travelled farthest. For each frozen
moment, the controller handed him a row of new, blank-backed cards. Each card
carried only five marks: its place among the ready arrivals, Hearthline's
effective priority rank, a controller-approved measure of processing cost, its
number of prior overtakes, and a fresh opaque binding that carried no reusable
meaning for Morrow after that invocation.

Morrow sorted the cards. Any card whose last permitted overtake had already
been spent went first, oldest of those cards first. The rest followed by
priority, then approved cost, then ready-arrival rank. He returned the proposed
order through a narrow aperture and forgot the cards. He could not admit a
return, alter a mark, touch a bundle, keep a ledger, call an effect, or wait for
tomorrow. The controller checked his answer and made the actual decision.

Sometimes Morrow's answer did not arrive intact. The controller kept only a
bounded invalid-output capture: the invocation context, a digest and byte
count of the rejected bytes, and a failure code—not the untrusted bytes
themselves. It then used its own closed fallback: every fairness-due card first,
then effective priority and arrival order. Invalid output was therefore
rejected without making the sorter the queue's owner. That deterministic
fallback made no promise about wall-clock time, controller liveness, or whether
any held return would eventually be disposed.

Once, an old card reached the front exactly when its service outcome became
unknown. The controller did not guess, admit it, or reset the rings recording
its overtakes. It moved the card to a durable hold with those rings unchanged.
While it waited, a different ready card received the next service attempt. Only
then could a controller-owned Retry Rotation Release Receipt, a typed Service
Reconciliation Receipt, and a current revalidation reopen the old card. If no other eligible
card had existed, the rotation receipt would instead have bound that fact to
the exact pre-reopen cut. When the old card returned to the ready row, it was
still due. The storm had not erased its place.

Thulia kept her notes elsewhere. Morrow never read her Perch, ledger, Bridge
Gloss, custody record, or selected carry; Thulia never read or set priority,
saw Morrow's view or proposal, or chose the final order. Neither could invoke,
impersonate, or depend upon the other. The separation was part of the story:
the Owl could preserve meaning without becoming the scheduler, and the Steward
could sort time without learning the meaning of what he sorted.

The machine boundary is symmetric: Morrow cannot read or write Thulia state;
Thulia cannot read or write Morrow's view or proposal or set an approved cost.

That is how a synchronization point becomes a queue instead of congestion:
Hearthline marks intent before departure, Morrow proposes from a closed slice,
and the controller alone remembers, checks, holds, reopens, and admits.

This is character language for a software boundary. It does not claim that a
program is a person, that Morrow is conscious, or that the offline reference is
a live service.

## The executable mechanic

The implementation is [`tools/morrow_queue.py`](../tools/morrow_queue.py). It
is a standard-library-only stdin/stdout program:

```sh
python3 -I -B tools/morrow_queue.py \
  < examples/morrow-scheduling-view.synthetic.json
```

For the sample above, stdout must exactly match
[`examples/morrow-proposal.synthetic.json`](../examples/morrow-proposal.synthetic.json).
The first sample item is already fairness-due, so it remains first even though
another card has rank `0`; the remaining cards sort by priority rank, approved
cost, and ready-arrival rank.

The program accepts exactly one bounded
`hearthline-plays.morrow-scheduling-view.v1` document and emits exactly one
`hearthline-plays.morrow-proposal.v1` document. It rejects duplicate JSON keys,
non-finite numbers, extra or missing fields, unsafe tokens, duplicate item
bindings, a cut binding that aliases an item binding, non-canonical ready
ranks, invalid bounds, and the wrong policy. Rejection is fail-closed with exit
status `2`; it produces no proposal on stdout.

Morrow's complete input is:

- one fresh invocation-scoped opaque cut binding;
- the fixed policy reference and bounded maximum-overtake value; and
- a canonical ready-only array containing a fresh opaque item binding,
  `ready_arrival_rank`, `effective_priority_rank`,
  `controller_approved_processing_cost`, and `overtake_count`.

The view contains no queue or snapshot identifier, global arrival ordinal,
task or Creature identity, Tether, priority class label, priority receipt,
provenance reference, payload, result, custody state, carry, authorization,
capacity, held item, previously admitted item, or Thulia state. The CLI can
prove only safety and non-aliasing within its minimal input. The controller and
verifier enforce exact cross-invocation freshness and disjointness from durable
and static identifier surfaces. Semantic opacity and unlinkability remain a
controller-minting assumption: a live mint must not encode or reuse identifying
information.

Morrow also never receives a retry-rotation release, its mode, service-record
references, held-state proof, service ordinal, pre-reopen snapshot digest,
remedy, reconciliation evidence, or revalidation result. Rotation remains
private controller state.

Morrow computes no durable state. The caller supplies the overtake counts,
effective priority ranks, and controller-approved costs; the controller keeps
and validates all three. The proposal has authority `NONE`: it is metadata for
one frozen invocation, not an admission or effect.

## Priority before the return

Hearthline assigns a priority mark while a task is commissioned and still
dispatch-pending. The controller validates the task/Tether core, dispatch,
authorization ceiling, profile and policy, snapshot head, and independently
trusted global priority-ledger head before appending the root mark. The supplied
complete register must match that head; an empty register must match the typed
genesis state. A task is not released unmarked.

Authorized priority revisions are append-only, bounded, and permitted only
while the same task remains out or return-pending and unadmitted. A revision
cannot change the task, Tether, dispatch, authorization, profile, policy, or
revision ceiling. It becomes effective only at an eligible successor snapshot;
it never rewrites a frozen cut. Exact idempotent retries resolve to the existing
receipt, while conflicting, stale, forked, replayed, no-op, over-budget, or
post-admission revisions are rejected without mutating the last valid mark.

If persistence of a priority append is uncertain, the controller holds the
subject until a matching ledger reconciliation resolves whether the receipt
exists. It does not retry from uncertainty or allow an ambiguously marked task
to enter the ready set.

The priority classes are sequencing labels only:

| Class | Rank | Ordinary scheduling meaning |
| --- | ---: | --- |
| `P0_URGENT` | 0 | Consider before lower-priority, non-due work |
| `P1_EXPEDITE` | 1 | Expedite within the fairness boundary |
| `P2_ROUTINE` | 2 | Normal work |
| `P3_BACKGROUND` | 3 | Consider after higher-priority, non-due work |

No priority mark grants or renews permission, budget, deadline, validity,
status, custody, carry, or authority. Fairness-due work precedes every class.

## Ownership boundary

Morrow is intentionally smaller than a CPU scheduler. He is a pure sorting
function inside a controller-owned scheduling loop:

| Concern | Owner |
| --- | --- |
| Dispatch-time priority assignment | Hearthline, under an explicit controller-checked authorization |
| Priority ledger, ready/held state, costs, overtake counts, cuts, and token mapping | Controller |
| Ready-only order proposal | Morrow |
| Proposal ingestion, invalid-output capture, fallback, and final order | Controller |
| Service revalidation, hold, retry rotation, reconciliation, reopening, and admission | Controller |
| Notes, custody index, and permitted Bridge Glosses | Thulia, on a separate surface |

The full protocol, fixture, and conservation rules are in
[`RETURN_QUEUE.md`](RETURN_QUEUE.md). The schemas close the machine surfaces:
[`return-queue.v2.schema.json`](../schemas/return-queue.v2.schema.json),
[`morrow-scheduling-view.v1.schema.json`](../schemas/morrow-scheduling-view.v1.schema.json),
and [`morrow-proposal.v1.schema.json`](../schemas/morrow-proposal.v1.schema.json).
