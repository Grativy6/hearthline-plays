# Homecoming return queue

**Design status:** `OFFLINE_REFERENCE_IMPLEMENTED_NOT_WIRED`

**Run status:** `PREPARED_NOT_RUN`

This layer handles only receipt-bound Homecoming return bundles that reach the
same controller synchronization point. It does not queue human grants, consume
an authorization, select carry, change an evaluator-owned result, or perform an
external effect. The existing ARC human gates remain a separate fail-closed
surface.

The current machine-readable successor is
[`return-queue.v2.schema.json`](../schemas/return-queue.v2.schema.json). The v1
schema remains the historical predecessor; it is not silently reinterpreted as
the priority-aware Morrow protocol.

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

Priority is bound earlier. Hearthline assigns a sequencing mark while the task
is commissioned and dispatch-pending, and the controller persists that root
mark before releasing the task. A returning task therefore does not ask Morrow
to infer importance from its result or payload.

The protocol keeps its records separate:

| Record | Owner | Meaning |
| --- | --- | --- |
| Priority authorization | Controller | Who may assign a bounded sequencing mark for one task/Tether and revision budget |
| Dispatch priority mark | Hearthline assignment, controller persistence | Required append-only root mark bound before task release |
| Priority revision | Hearthline assignment, controller persistence | Bounded successor mark for the same pending, unadmitted task |
| Intake and enqueue | Controller | Which distinct return reached this queue, and in what linearized order |
| Frozen full snapshot | Controller | Authoritative ready, held, admitted, fairness, and binding state at one cut |
| Ready-only view | Controller to Morrow | Minimal, fresh-token projection for one invocation |
| Proposal | Morrow | Pure deterministic suggestion for processing that frozen ready set |
| Invalid-output capture | Controller | Closed context plus digest, byte count, and failure code for rejected untrusted bytes |
| Final service order | Controller | Committed permutation and head for one profile and service epoch; no admission by itself |
| Service disposition | Controller | Durable failed or uncertain head transition to held state without count reset |
| Service Reconciliation Receipt | Controller | Typed resolution of an `UNKNOWN` disposition, bound to the exact item, handle, profile, and service epoch |
| Retry Rotation Release Receipt | Controller | Proof that another item received a later service attempt, or that no other eligible ready item exists at the exact pre-reopen cut |
| Queue readiness receipt | Controller | Evidence that a held head's required remedy and current revalidation permit reopening |
| Service Admission Receipt | Controller | One revalidated queue head admitted for processing, with exact pre/post overtake counts |

None of these records grants permission or establishes that a claimed result is
true. The source evaluator retains result authority. Hearthline retains carry
selection, and Thulia receives only selected carry through her separate custody
route.

## Dispatch marks and append-only revisions

The four closed priority classes are `P0_URGENT`, `P1_EXPEDITE`, `P2_ROUTINE`,
and `P3_BACKGROUND`, with numeric ranks `0` through `3`. Lower ranks sort first
only after the fairness-due prefix. The authorization for one task/Tether binds
the assigner, controller, queue, profile and epoch, policy, dispatch, immutable
task/Tether core digest, priority ceiling, revision budget, grant, scope,
deadline, and budget references. Priority remains sequencing-only; it cannot
expand any of those references.

A root mark is accepted only against the current controller lifecycle,
snapshot head, independently trusted global priority-ledger head, and matching
authorization. The append helper also requires the supplied complete register
to match that trusted head; an empty register must carry the typed genesis
state and exact genesis head. This prevents a caller-supplied alternate,
truncated, or forked history from authenticating itself. An authorized revision
must name the latest mark it supersedes, advance the
revision ordinal by one, change the priority rather than append a no-op, remain
within the ceiling and revision budget, and refer to the same task, Tether,
dispatch, authorization, profile, and policy. The task must still be out or
return-pending and unadmitted. Exact idempotent retries return the existing
receipt; the same idempotency key with a changed canonical binding conflicts,
while a fresh key that replays an identity or binding rejects. Stale or forked
heads, no-op or over-budget changes, and post-admission revisions likewise fail
without replacing the last valid mark.

Snapshot cuts make revisions non-retroactive. The effective mark for a frozen
snapshot is the newest valid receipt at or before that snapshot's priority
ledger cut. A later revision can first affect an eligible successor snapshot;
it cannot rewrite the order that Morrow already saw.

An uncertain append outcome is not treated as success or absence. The
controller holds the subject outside the ready set until a matching priority-
ledger reconciliation establishes the outcome. It does not retry an append
from uncertainty.

The reference exposes a pure reconciliation checker for that boundary. It
requires an authenticated complete priority-ledger head, an independently
trusted durable hold reference and digest, the original trusted snapshot head,
the exact task/Tether chain and authorization, and a closed reconciliation
receipt. Its returned eligibility decision is not itself a
durable queue transition: a live controller must atomically append and consume
that reconciliation before constructing a successor ready snapshot. The
synthetic five-snapshot trace deliberately witnesses the unresolved hold only;
it does not claim that host persistence lane is wired here.

## Frozen snapshots and Morrow's closed view

The controller freezes a finite full snapshot before asking for a proposal. A
controller-owned digest binds the queue, destination, synchronization point,
profile and service epochs, policy and priority-ledger cut, arrival cut,
ready/held/admitted partitions, effective priority marks, overtake counts,
fresh token mappings, and any service-reopen receipts. A return arriving after
the cut waits for the immediate successor snapshot. Held returns remain
controller-visible but never enter Morrow's ready permutation, and prior
admission does not imply terminal service.

Morrow receives a different, ready-only projection described by
[`morrow-scheduling-view.v1.schema.json`](../schemas/morrow-scheduling-view.v1.schema.json).
It contains only:

- the schema and frozen-ready status;
- a fresh invocation-scoped opaque cut binding;
- the fixed policy and bounded `maximum_overtakes`; and
- a canonical dense ready array with a fresh opaque item binding,
  `ready_arrival_rank`, `effective_priority_rank`,
  `controller_approved_processing_cost`, and `overtake_count`.

The projection excludes queue, snapshot, task, Tether, Creature, source,
payload, result, custody, carry, grant, authorization, provenance, global
arrival, capacity, held/admitted partitions, and Thulia state. The controller
creates new cut and item bindings for every invocation, keeps their private
mapping, and prevents aliases against current, prior, or protected identifier
surfaces. The verifier proves exact freshness and non-aliasing for the supplied
records. Semantic opacity and unlinkability depend on a live controller minting
tokens that do not encode or reuse identifying information; the offline
verifier cannot prove that property from token spelling alone.

Processing cost is controller-approved scheduling metadata bound by a
controller attestation to the queue, profile, epoch, policy, task/Tether core,
and opaque scheduling binding. It is not a return's self-reported importance or
authority.

Morrow is the named Queue Steward and the executable function in
[`tools/morrow_queue.py`](../tools/morrow_queue.py). It reads one bounded JSON
view from stdin and writes one proposal to stdout. It has no filesystem,
network, clock, randomness, subprocess, persistence, heartbeat, local-module,
ledger, Thulia, custody, carry, admission, or effect surface. Its authority is
`NONE` and its only allowed output is `QUEUE_ORDER_PROPOSAL_ONLY`.
Retry-rotation identities, release modes, held-state proofs, service ordinals,
pre-reopen snapshot digests, remedies, reconciliation evidence, and
revalidation results also remain outside Morrow's view.

## Ordering, fallback, and bounded overtakes

The reference policy is
`STABLE_EFFECTIVE_PRIORITY_THEN_APPROVED_COST_THEN_ARRIVAL_V2`:

1. Place every item with `overtake_count >= maximum_overtakes` in a stable
   oldest-ready-first prefix.
2. Sort the remaining items by effective priority rank, ascending.
3. Within a priority rank, sort by controller-approved processing cost,
   ascending.
4. Break remaining ties by ready-arrival rank, ascending.

Morrow emits the cut binding, canonical scheduling-view digest, policy,
proposed opaque order, fixed reason codes, and explicit pure/stateless/no-effect
flags. The controller accepts only the exact context-bound policy order and
maps the fresh bindings back to its private queue identities.

Morrow's stdout is untrusted ingress. Malformed JSON, duplicate keys, unsafe
values, stale context, replayed cuts, a wrong digest or policy,
missing/duplicate/unknown bindings, a non-bijective order, or a valid
permutation in the wrong policy order is invalid. For bytes already admitted by
the one-megabyte bounded reader, the controller stores a closed invalid-output
capture containing the expected cut, view digest and policy, exact raw SHA-256
and byte count, and failure code. It does not persist the raw untrusted output
in that record. Output beyond the reader limit is rejected before this helper
and treated as absent for the same controller fallback; it is not represented
as an in-limit capture.

Invalid or absent output invokes a controller-computed fallback: the same
stable fairness-due prefix, then effective priority rank, then FIFO by arrival.
Controller-approved cost is deliberately not used in fallback. The controller
owns both the fallback and the final order. This establishes deterministic
handling for the frozen snapshot; it makes no wall-clock, controller-liveness,
or eventual-disposition guarantee.

Each ready return carries a controller-persisted overtake count. Final order
alone consumes no overtake and admits nothing. Only a successful single-head
admission increments each still-ready item that the admitted head overtook. A
due item remains in the stable due prefix even if another item is `P0_URGENT`.
This gives a structural no-starvation rule for each finite frozen set if the
controller continues taking successful terminating steps. It is not a
liveness proof against controller failure, process loss, repeated service
holds, or an indefinitely held return.

## Service outcome, hold, reconciliation, and reopening

The controller revalidates the scheduled head against its immutable intake
projection immediately before admission. A known pass may append one Service
Admission Receipt. A failed or uncertain service attempt does not become an
admission. Instead, an atomic Service Disposition moves that head from ready to
held and records the blocker, required remedy, reopen handle, and exact
overtake counts before and after. No count is incremented or reset.

`UNKNOWN` is distinct from `FAILED`. An unknown outcome requires a matching
typed Service Reconciliation Receipt because the controller must determine what
happened before trying again. It binds the source disposition, item, reopen
handle, queue, profile and service epoch, and an explicit
`CONFIRMED_NOT_ADMITTED_SAFE_TO_RETRY` result. Reopening either outcome also
requires one unique,
controller-owned Retry Rotation Release Receipt. It proves that a distinct
queue item received a later service attempt after the held item's disposition,
or—when none exists—that the exact pre-reopen snapshot had zero other eligible
ready items. It carries the held item's saved overtake count and cannot mutate
priority, authority, custody, result, deadline, or budget.

A Queue Readiness receipt then binds the prior disposition, item, handle,
remedy, rotation release, current snapshot, current revalidation inputs, and a
`PASS` result. Each disposition and each rotation release can be consumed only
once. The item re-enters the next ready view with its saved overtake count; if
it was due before the hold, it is still due after reopening. Rotation blocks
an immediate repeat while another eligible ready item exists; it does not
promise wall-clock fairness, successful admission, controller liveness, or
eventual disposition.

## Morrow and Thulia do not meet

Morrow and Thulia have symmetric non-interference boundaries. Morrow has no
Perch, ledger, Bridge Gloss, direct Thulia channel, dependency, invocation, or
impersonation route. He cannot read selected carry or Homecoming custody.
Thulia cannot read or set priority, read a Morrow scheduling view or proposal,
read the final order or admission state, set an order, admit, invoke Morrow, or
impersonate him. Their identifiers and state surfaces are disjoint, and each
must remain operable if the other is absent.

In explicit read/write terms, Morrow cannot read or write Thulia state. Thulia
cannot read or write Morrow's scheduling view or proposal and cannot set
controller-approved scheduling cost or any other scheduling input.

Thulia may preserve permitted notes through her own custody path. Those notes
do not become scheduling inputs. Morrow may sort closed metadata without
becoming a scribe, a Creature, or a controller. The story-facing version of
this boundary is [`MORROW_AND_THE_MARKED_TETHERS.md`](MORROW_AND_THE_MARKED_TETHERS.md).

## Conservation rules

For every snapshot and controller step:

- ready, held, and previously admitted IDs are disjoint and conserved;
- effective priority comes only from the append-only ledger at the frozen cut;
- Morrow sees only the canonical ready-only projection and fresh bindings;
- a valid proposal is the exact deterministic policy order over that view;
- the final schedule is a permutation of the ready set;
- an admitted item is exactly the revalidated final-schedule head;
- a service disposition and an admission are mutually exclusive for one step;
- failed or uncertain heads move to held without losing their counts;
- every reopened `UNKNOWN` consumes one matching controller-owned Service
  Reconciliation Receipt;
- reopening a service-held item consumes exactly one matching controller-owned
  retry-rotation release;
- all non-head ready returns remain queued with exact updated counts;
- held returns stay out of Morrow's view and post-cut arrivals first appear in
  the successor snapshot;
- content-equal returns with different intake identities remain separate;
- no return is silently dropped, merged, renamed, claimed, or upgraded;
- evaluator-owned disposition, `HOMECOMING:RETURNED` custody, and carry remain
  distinct and unchanged; queue admission performs no reconciliation of
  custody, carry, evaluator status, or Thulia state (controller service-outcome
  reconciliation is separate queue-state evidence); and
- priority, proposal, fallback, hold, reopening, and admission perform no
  external effect and grant no authority.

## Synthetic walk-through

[`return-queue.synthetic.json`](../fixtures/return-queue.synthetic.json) is a
five-snapshot fabricated trace. It demonstrates dispatch roots, a bounded
priority revision that becomes effective only at a successor cut, fresh Morrow
bindings, valid proposals, normalized invalid-output capture, controller
priority/FIFO fallback, bounded overtakes, an unresolved priority-append hold,
durable unknown service outcomes, retry rotation, reconciliation, and reopening
with a saved due count.

The first snapshot admits the short `P1` return while the older `P2` return is
overtaken. A `P1` revision for the medium return becomes visible in snapshot
two; invalid Morrow output then triggers controller fallback, which admits the
medium return and brings the old return to its maximum of two overtakes. The
old return is forced to the front in snapshot three, but its service outcome is
`UNKNOWN`, so it moves to held with count `2`. Snapshot four gives the distinct
late return the intervening service attempt; that attempt also ends in an
unresolved `UNKNOWN` hold. The controller's rotation release cites this typed
intervening disposition. Snapshot five carries the old return's matching
rotation, reconciliation, and readiness evidence, reopens it still due at count
`2`, and admits it. A separate return with an unresolved `UNKNOWN` priority-
revision append remains controller-held and never enters Morrow's view. Two
returns with the same synthetic content hash retain different intake identities
and are accounted separately.

The standalone synthetic CLI pair is:

- [`morrow-scheduling-view.synthetic.json`](../examples/morrow-scheduling-view.synthetic.json)
- [`morrow-proposal.synthetic.json`](../examples/morrow-proposal.synthetic.json)

Run it from the repository root:

```sh
python3 -I -B tools/morrow_queue.py \
  < examples/morrow-scheduling-view.synthetic.json
```

The first sample binding is already due and therefore precedes a rank-`0`
binding. The non-due remainder demonstrates priority and approved-cost order.

## Claim ceiling and reopening the design

The fixture, schemas, CLI, and standard-library verifier exercise deterministic
data invariants only. They are not a hosted scheduler, concurrency benchmark,
performance result, Creature run, ARC interaction, task result, authority
receipt, or evidence of reduced latency.

A live implementation would need a separately authorized controller binding,
durable crash recovery, bounded processing behavior, authentic source receipts,
and a matched evaluation. Reopen through a successor design and manifest; do
not infer those missing properties from this offline reference.

Closed classes and per-task ceilings prevent out-of-contract escalation; they
do not prevent semantic priority inflation if a controller policy broadly
authorizes or assigns urgent marks.
