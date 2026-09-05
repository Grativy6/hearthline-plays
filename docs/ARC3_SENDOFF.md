# ARC-AGI-3 sendoff route — index only, no authority

Status: `OFFLINE_CANDIDATE_SOURCE_READY_HUMAN_GATES_CLOSED`

Terminal blocker: `RUNTIME_CLOSURE_UNFROZEN`

This is a custodial route to existing ARC-AGI-3 material. It admits no new ARC
machinery, strategy, evaluation, runtime observation, or result.

## Current Morrow priority-queue successor — repository-adopted, no external authority

- Canonical branch: `arc-agi/titles/arc-agi-3-hearthline-launch-20260903`
- Merge commit: `25e154d539b1c85e28c5334b9b940ab6880ca600`
- Tree: `d249cec7b81d942b84a6f728a421e3cd18ddaf31`
- Reviewed source head: `2f22c90bf2de57e5cb6b2d21b05c4b5c5cdc964b`
- First parent: `a3f99acedd1fa91417510f66eba35c444533f335`
- Second parent: `2f22c90bf2de57e5cb6b2d21b05c4b5c5cdc964b`
- [Merged PR #8](https://github.com/Grativy6/hearthline-plays/pull/8)
- [Morrow and the Marked Tethers](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/design/MORROW_AND_THE_MARKED_TETHERS.md)
- [Offline priority-aware return queue](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/design/RETURN_QUEUE.md)
- [Stateless Morrow CLI](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/tools/morrow_queue.py)
- [Scheduling-view example](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/examples/morrow-scheduling-view.synthetic.json)
- [Exact proposal example](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/examples/morrow-proposal.synthetic.json)
- [Scheduling-view schema](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/schemas/morrow-scheduling-view.v1.schema.json)
- [Proposal schema](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/schemas/morrow-proposal.v1.schema.json)
- [Return-queue v2 schema](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/schemas/return-queue.v2.schema.json)
- [Station verifier](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/tools/verify_station.py)
- [Adopted copy-ready sendoff](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/launch/SENDOFF_2026-09-05.md)

The reviewed source head and merge commit have the same exact tree. This
successor preserves the PR #6 merge as its first parent and adds an offline
priority-aware queue reference, strict schemas, fabricated examples, tests,
and a standard-library stdin/stdout CLI. Hearthline assigns finite priority at
dispatch. The controller owns every durable ledger, hold, count, retry record,
final order, and admission decision. Morrow is a disposable deterministic
sorter over a fresh ready-only projection; his output is untrusted until the
controller validates it.

Morrow and Thulia are strictly non-interfering. Morrow cannot read or write
Thulia's state, invoke or impersonate her, depend on her, or share her channel,
ledger, custody, or carry surfaces. Thulia has the symmetric restrictions over
Morrow's scheduling view, proposal, priority, cost, order, and admission
surfaces. Each must continue to function when the other is absent. Morrow sorts
time; Thulia preserves meaning.

The successor also adds typed retry rotation so a failed or uncertain head
cannot monopolize immediate retry while another eligible item exists. It
preserves separate queue identity for equally valid or same-content returns.
It makes no wall-clock liveness, latency, or eventual-disposition promise. It
is not wired to a runner and is not a hosted-concurrency or performance result.
It queues returns, not grants, and leaves result authority, carry selection,
source-lock bytes, human-gate states, and external effects unchanged.

## Preserved Homecoming predecessor

- Merge commit: `a3f99acedd1fa91417510f66eba35c444533f335`
- Tree: `c7eac0a173c1b50ac62447785734f96a986bf4fb`
- Reviewed source head: `5ba87114119cae8dbf96a5fbd9634c076b23200c`
- [Merged PR #6](https://github.com/Grativy6/hearthline-plays/pull/6)
- [Homecoming return queue at the preserved merge](https://github.com/Grativy6/hearthline-plays/blob/a3f99acedd1fa91417510f66eba35c444533f335/design/RETURN_QUEUE.md)

That merge descends from exact predecessor
`bb6327e1f5f96da929c4068d6b95fa94d4f73600`, produced through PR #4. It first
added the receipt-bound Homecoming queue and controller-only single-head
admission. The current successor extends rather than rewrites that lineage.

The preserved PR #4 predecessor reconciled the launch and hardened-station
histories. It added the exact Honesty PCP scientific-run entrance and the
published [CHARTER v1.0](https://doi.org/10.5281/zenodo.22288471) anchor as
research context rather than an ARC input, permission, or result. Christopher
explicitly adopted that repository preflight and sendoff context on 5 September
2026. The protocol remains `PROPOSED_UNVALIDATED`; that adoption opened neither
human gate and conferred no submission authority.

## Current canonical candidate

- Branch: `arc-agi/titles/arc-agi-3-hearthline-launch-20260903`
- Commit: `25e154d539b1c85e28c5334b9b940ab6880ca600`
- Tree: `d249cec7b81d942b84a6f728a421e3cd18ddaf31`
- [Operational README](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/launch/README.md)
- [Current status](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/launch/status/current.json)
- [Human gates](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/launch/gates/README.md)
- [Source lock v3](https://github.com/Grativy6/hearthline-plays/blob/25e154d539b1c85e28c5334b9b940ab6880ca600/launch/source-lock.v3.json)
- [Scientific Run Entry v1.0](SCIENTIFIC_RUN_ENTRY.md)

## Exact current Morrow-tree remote checks

On 5 September 2026, three pull-request workflows completed successfully at
reviewed source head `2f22c90bf2de57e5cb6b2d21b05c4b5c5cdc964b`, whose
tree is exactly the current merged tree:

- [Verify ARC launchpad — run 33986787817](https://github.com/Grativy6/hearthline-plays/actions/runs/33986787817)
- [Verify Hearthline ARC launch kit — run 33986787821](https://github.com/Grativy6/hearthline-plays/actions/runs/33986787821)
- [Verify research station — run 33986787824](https://github.com/Grativy6/hearthline-plays/actions/runs/33986787824)

Their claim ceiling is offline repository verification on Ubuntu/Python 3.12.
They do not establish a hosted scheduler, private runtime, Gate A, runtime
closure, Gate B, submission, score, or launch readiness.

## Preserved PR #6 queue-tree remote checks

On 5 September 2026, three pull-request workflows completed successfully at
reviewed source head `5ba87114119cae8dbf96a5fbd9634c076b23200c`, whose
tree is exactly the preserved `a3f99ac…` predecessor tree:

- [Verify ARC launchpad — run 33978105033](https://github.com/Grativy6/hearthline-plays/actions/runs/33978105033)
- [Verify Hearthline ARC launch kit — run 33978104990](https://github.com/Grativy6/hearthline-plays/actions/runs/33978104990)
- [Verify research station — run 33978105014](https://github.com/Grativy6/hearthline-plays/actions/runs/33978105014)

These are retained predecessor receipts and are not promoted into verification
of the later Morrow tree.

## Preserved PR #4 successor verification

On 5 September 2026, three pull-request workflows completed successfully at
reviewed source head `27e14f15a3c19723d4e344691fed609c1e1f9975`, whose
tree is exactly the preserved `bb6327e…` predecessor tree:

- [Verify ARC launchpad — run 33974001362](https://github.com/Grativy6/hearthline-plays/actions/runs/33974001362)
- [Verify Hearthline ARC launch kit — run 33974001361](https://github.com/Grativy6/hearthline-plays/actions/runs/33974001361)
- [Verify research station — run 33974001296](https://github.com/Grativy6/hearthline-plays/actions/runs/33974001296)

Their claim ceiling is offline repository verification on Ubuntu/Python 3.12.
They do not establish a private runtime, Gate A, runtime closure, Gate B,
submission, score, or launch readiness.

## Preserved predecessor verification

At `2026-09-04T20:45:47Z`, three push workflows completed successfully at
predecessor commit `97f580504e22bbd59b425274d6b5e0f9a18fe66e`:

- [Verify ARC launchpad — run 33917834935](https://github.com/Grativy6/hearthline-plays/actions/runs/33917834935)
- [Verify Hearthline ARC launch kit — run 33917834892](https://github.com/Grativy6/hearthline-plays/actions/runs/33917834892)
- [Verify research station — run 33917834890](https://github.com/Grativy6/hearthline-plays/actions/runs/33917834890)

These remain historical receipts for the predecessor tree. They are not
silently promoted into verification of a later tree.

## Current stop

- Gate A is closed.
- Gate B is unavailable.
- The private Kaggle runtime/evaluator remains unobserved.
- Exact Linux/POSIX distribution and bundled Agents closure remain unfrozen.
- No current credential, private-stage, holdout, submission, or score authority
  exists in this route.
- No Kaggle or ARC contact is performed by this map.

## Human-only sequence

1. Start from the clean exact candidate commit.
2. Package and verify for the real slug on supported Linux/POSIX Python 3.12.
3. A human rechecks current rules and separately opens Gate A.
4. A human performs the manual private, non-competition stage.
5. Capture the complete runtime/distribution and bundled Agents inventory.
6. Review and freeze a `FROZEN_POST_STAGE_SUCCESSOR` source lock and commit.
7. Regenerate and privately restage from that successor.
8. A human separately opens Gate B.
9. A human performs any separately authorized manual submission.

Gate A does not authorize Gate B. A local test or private stage is not a
competition result.

## Preserved divergence

Launch `97f5805…` and research-station `e2b2eec…` diverge by one commit each
from merge base `d4716557587302910b0002757b8e9e65c90b9fd7`. Their operational
README, current status, gates README, and source locks match; the launch-only
delta adds the Astra access/embargo receipt pair and updates the receipt index.
The merged successor joins both histories without erasing that prior
divergence or collapsing their separate provenance.

The Astra embargo remains `ACTIVE` and its milestone condition remains
`UNRESOLVED_NOT_RECORDED`. This index neither proves an Astra invocation nor
lifts the embargo; only a later append-only steward declaration can record its
condition satisfied. If an Astra contribution is ever admitted, the existing
receipt requires its own explicit grant and successor receipt.

Millennium and Creature are side branches, not ARC-launch descendants. Do not
merge either whole branch into ARC for convenience.

Reopen only with append-only exact receipts and a reviewed successor. Never
rewrite predecessor records or infer authority from this page.
