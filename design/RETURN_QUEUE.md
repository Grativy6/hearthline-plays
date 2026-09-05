# Homecoming return queue

**Design status:** `OFFLINE_REFERENCE_IMPLEMENTED_NOT_WIRED`

**Run status:** `PREPARED_NOT_RUN`

This layer handles only receipt-bound Homecoming return bundles that reach the
same controller synchronization point. It does not queue human grants, consume
an authorization, select carry, change an evaluator-owned result, or perform an
external effect. The existing ARC human gates remain a separate fail-closed
surface.

## Why a queue begins at synchronization

Concurrent Homecomings should not become a race in which one return acquires
reality and the others become lock congestion. The controller first records a
short, linearized intake receipt for every return. That receipt fixes a unique
queue-item ID, return ID, idempotency key, controller-assigned arrival ordinal,
source receipt, objective, Creature, content hash, evaluation disposition,
custody state, and carry state. A lone return follows this same intake path; a
batch does not give either return ownership of the synchronization point. The
longer inspection and scheduling work happens only after those identities are
fixed. Every attempt has an intake receipt; every accepted placement also has
a distinct enqueue receipt. Exact retries resolve to the same item, while
distinct returns cannot reuse an item, return, intake, enqueue, or Homecoming
receipt identity.

Arrival order, a Queue Steward's proposal, the controller's final service
order, and actual controller admission are different records:

| Record | Owner | Meaning |
| --- | --- | --- |
| Intake | Controller | Which distinct return reached this queue, and in what linearized order |
| Proposal | Task-scoped Queue Steward | A pure metadata-only suggestion for processing a frozen ready set |
| Final service order | Controller | A committed permutation and head for one profile and service epoch; no admission by itself |
| Service Admission Receipt | Controller | One revalidated queue head admitted for processing, with exact pre/post overtake counts |

None of these records grants permission or establishes that a claimed result is
true. The source evaluator retains result authority. Hearthline retains carry
selection, and Thulia receives only selected carry through her separate custody
route.

## Frozen snapshots and bounded overtakes

The controller freezes a finite snapshot before asking for a proposal. A
controller-owned full projection digest binds the queue, destination,
synchronization point, profile and service epochs, cut, and opaque visible,
ready, held, and previously-admitted partitions. The Queue Steward receives a
separate ready-only scheduling-view projection and digest. A return that
arrives after the cut waits for the immediate successor snapshot; it cannot
jump into the already frozen set. Held returns remain named and visible but are
not placed in the ready permutation, and prior admission does not imply
terminal service.

Processing cost is controller-approved scheduling metadata with a named
controller attestation, not a return's self-reported importance or authority.
The Steward's closed view contains only an opaque item binding, arrival
ordinal, approved cost, provenance reference, and overtake count. It excludes
payload or content identity, source identity, result or validity status,
Homecoming custody, carry, grants, authority, and effect state. The reference policy is
`STABLE_ASCENDING_CONTROLLER_APPROVED_COST_THEN_ARRIVAL_V1`. A task-scoped Queue Steward
may propose the exact ready-set permutation produced by that policy. The
proposal binds the steward manifest, policy, snapshot ID, controller-owned full
snapshot digest, and the distinct ready scheduling-view digest. The controller
checks that the proposed opaque bindings form a bijection over the ready
scheduling view, then maps them back to internal ready IDs. An absent,
duplicated, omitted, unknown, or otherwise invalid proposal falls back to
controller-computed FIFO order.

The Steward's proposal returns through a manifest-bound control aperture under
a profile distinct from the data queue. It cannot enter, recursively reorder,
or block the data queue under review.

Proposal validity and controller disposition remain separate: a proposal may be
structurally valid while the controller replaces its head to enforce fairness.
Each ready return carries a persisted overtake count. When any return reaches
`maximum_overtakes`, the oldest such return is forced to the head, regardless of the
cost proposal. The final service order does not consume an overtake or admit
anything. Only one head is admitted per controller step. The controller
revalidates that head against its immutable intake projection before appending
a distinct Service Admission Receipt bound to the exact queue, profile and
service epochs, snapshot, order receipt, controller, item, and pre/post
overtake counts. Queueing, waiting, steering, or resumption never renews a
grant, deadline, validity claim, scope, authority, or budget.

This gives a structural no-starvation rule for each finite frozen set, assuming
the controller continues taking terminating steps. It is not a liveness proof
against controller failure, process loss, or an indefinitely held return.

## Conservation rules

For every snapshot and admission:

- ready IDs remain an exact, unique set;
- the proposal and final schedule are recorded separately;
- the final schedule is a permutation of the ready set;
- an admitted item is exactly the final schedule head;
- all non-head ready returns remain queued with updated overtake counts;
- held returns remain visible and post-cut returns first appear in the next
  snapshot;
- content-equal returns with different intake identities remain separate;
- no return is silently dropped, merged, renamed, claimed, or upgraded;
- evaluator-owned objective disposition, `HOMECOMING:RETURNED` custody, and
  carry state remain distinct and unchanged; queue admission performs no
  reconciliation; and
- the Queue Steward has no admission, mutation, carry, grant, or effect port.

The synthetic fixture demonstrates controller-approved costs `[10, 1, 2]`, the
proposed order `short, medium, old`, and `maximum_overtakes = 2`. The short and
medium returns are separately admitted, persisting two overtakes for the old
return. The old return is then forced to the third snapshot's head. A held
return stays visible, and a later intake waits for the next snapshot. Two
separately identified returns share the same synthetic content hash and are
still admitted separately.

## Claim ceiling and reopening

[`return-queue.synthetic.json`](../fixtures/return-queue.synthetic.json) and the
standard-library verifier exercise deterministic data invariants only. They are
not a hosted scheduler, concurrency benchmark, Creature run, ARC interaction,
task result, authority receipt, or evidence of reduced latency.

A live implementation would need a separately authorized controller binding,
durable crash recovery, bounded processing behavior, authentic source receipts,
and a matched evaluation. Reopen through a successor design and manifest; do
not infer those missing properties from this offline reference.
