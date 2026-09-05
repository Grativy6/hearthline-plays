# Hearthline ARC-AGI-3 launchpad

**Branch:** `codex/arc3-charter-sendoff-20260905`

**Canonical launch ancestor:** `97f580504e22bbd59b425274d6b5e0f9a18fe66e`

**Hardened station ancestor:** `e2b2eec1544caeb8a1a07825d56db1d932c9e3f6`

**Original parent station:** `74728f8c4ec9409bd0e6c8064a0b6b356da776f6`
**Current phase:** `RECONCILED_OFFLINE_CANDIDATE_PREPARATION`

**Competition/Kaggle phase:** `NOT_AUTHORIZED_NOT_STARTED`

This is a removable launch layer over the earlier research station. It keeps the founding prompt, exact public-source locks, practice requests, compact world models, Spark/Pair-Static records, retired-run records, and receipts in distinct directories so later cleanup can move or delete one layer without rewriting the others.

This successor explicitly reconciles the canonical launch and hardened station
siblings, retains the exact Astra embargo commit as an ancestor, and adds only
the documentary run-entry, publication-anchor, and send-off surfaces; the exact
model-facing Honesty PCP input; and the narrow guard/workflow updates needed to
admit and verify that prompt. The executable candidate and source-lock bytes
remain unchanged from the canonical launch ancestor.

## Fast map

| Path | Purpose |
|---|---|
| [`launch/FOUNDER_SENDOFF.md`](FOUNDER_SENDOFF.md) | Preserved human founding objective |
| [`launch/SENDOFF_2026-09-05.md`](SENDOFF_2026-09-05.md) | Draft append-only successor send-off for human review; opens neither gate |
| [`launch/RUN_GRANT_2026-09-03.md`](RUN_GRANT_2026-09-03.md) | Expired, spent historical grant with a present-day non-executable banner; the original record is preserved verbatim below it |
| [`docs/SCIENTIFIC_RUN_ENTRY.md`](../docs/SCIENTIFIC_RUN_ENTRY.md) | Canonical honesty preflight; a required explicit disposition, not authority |
| [`launch/source-lock.v2.json`](source-lock.v2.json) | Historical public-orientation source lock |
| [`launch/source-lock.v3.json`](source-lock.v3.json) | Current official starter/toolkit/Agents/benchmark/Kaggle and bounded-context identities |
| [`launch/status/current.json`](status/current.json) | Mutable v2 current projection over preserved legacy status |
| [`launch/receipts/20260904T070000Z-orientation-reconciliation.v2.json`](receipts/20260904T070000Z-orientation-reconciliation.v2.json) | Five-run reconciled counts and exact source hashes |
| [`launch/contracts/official-starter-eeb153.contract.json`](contracts/official-starter-eeb153.contract.json) | Ordered structural contract derived from the exact pinned starter |
| [`agent/my_agent.py`](../agent/my_agent.py) | Offline-default starter-compatible `MyAgent` source; no environment adapter |
| [`launch/gates/README.md`](gates/README.md) | Closed, one-use human Gate A and Gate B procedure |
| [`launch/ASTRA_PUBLIC_BLUEPRINT.md`](ASTRA_PUBLIC_BLUEPRINT.md) | Publicly observed design lessons; no hidden-reasoning claim |
| [`design/PAIR_STATIC.md`](../design/PAIR_STATIC.md) | Two Sparks, two source Statics, one comparison Static, then Thulia custody |
| [`schemas/`](../schemas/) | Movable JSON contracts for Statics, world models, plans, requests, and receipts |
| [`templates/`](../templates/) | Empty, human-readable starting objects |
| [`practice/`](../practice/) | Explicit public-game requests and local world-model state |
| [`tools/`](../tools/) | Standard-library validation and archive guards only; the public replay broker is deleted from the active tree |
| [`tests/`](../tests/) | Offline tests; no ARC contact |
| [`.github/workflows/arc3-orientation-probe.yml`](../.github/workflows/arc3-orientation-probe.yml) | Manual archive validation only; no replay or automatic trigger |

## Portable layers

1. **Source layer:** locators and immutable identities; no corpus bytes.
2. **Policy layer:** founding objective, current grant, stop rules.
3. **Representation layer:** Spark Static, Pair Static, world model, operator map, plan.
4. **Historical execution layer:** preserved explicit action requests and reconciled receipts; every archived request is rejected by the current guard and no active broker remains.
5. **Evidence layer:** workflow run, artifact, scorecard, and manually admitted receipt.

No layer may silently fill a missing field from another. In particular, the representation layer proposes what may happen; an archived execution request records what the retired broker was once allowed to send; the reconciled returned observation records what happened then. Those historical records grant no present contact authority.

The repository guard is a regression and consistency check over a frozen Git
tree, not a self-authenticating trust anchor: guard code and workflow code live
in the same mutable repository. Protected-branch policy and independent human
review must anchor approval outside this tree before any release decision.

## Frozen local threat model

The readiness checks fail closed against repository-controlled path swaps,
symlinks, hard-link aliases, closed-inventory violations, changed or extra
candidate bytes, duplicate/non-finite JSON, Git replacement refs, ambient Git
configuration/hooks/prompts/lazy fetch, Python import-path injection, stale or
fabricated gate chains, and concurrent ledger consumption. CI materializes the
exact stage-0 regular guard blob from the reviewed index before executing it.
Each workflow pins that guard's raw SHA-256. In the opposite direction the
guard locks each workflow after normalizing only the single
`expected_guard_sha256` assignment, which deliberately breaks an impossible
literal hash cycle while preserving every other workflow byte. A coordinated
guard/workflow change therefore still requires the external protected-branch
review named above; neither in-repository direction is an independent root of
trust.

This is not a hostile-host sandbox. A malicious filesystem owner racing held
descriptors, a compromised Git or Python executable, dynamic loader, operating
system/kernel, runner administrator, or Kaggle platform administrator is
outside the contract. Content-addressed local directories, the guard, and the
gate ledger are consistency/procedural evidence—not signatures, immutable
storage, remote attestation, or proof of an external effect.

## Run discipline

`present state != operator model != plan != action != outcome`

The compact world model keeps these five surfaces separate. Every action has a hypothesis and expected observable. Every returned frame may update the state and operator model, but does not retroactively justify the action. A failed expectation is retained as information.

## Current natural stop

The old public-orientation grant is expired and spent. All environment contact
is closed. The deterministic candidate source and ignored notebook builder pass
offline structural verification against the exact pinned public starter
contract. This does not establish the private runtime, score, or generalization.
Kaggle staging and competition ignition remain closed and each requires a
separate one-use human grant under [`gates/README.md`](gates/README.md).
The dated successor send-off preserves purpose and authorizes repository
preparation only; it does not change this natural stop.
