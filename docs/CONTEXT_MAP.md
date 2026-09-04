# ARC-AGI-2 context map

**State:** `PREPARED_NOT_RUN`
**Steward and author:** Christopher D. Pang

AI systems may assist as tools for drafting, implementation, and mechanical
verification. They are not authors, stewards, account holders, rule acceptors,
human approvers, or external-action authorities.

This map defines which information may enter each process. It is a boundary
document, not evidence that a public-evaluation audit, Kaggle run, or submission
has happened.

## One-way artifact flow

| Context | May receive | Emits | Must never receive or emit |
| --- | --- | --- | --- |
| Source control | Exact Git commits, trees, SPDX identifiers, claim ceilings, and review status for official web surfaces | `provenance/official-sources.lock.json` | Official task bytes, credentials, rule acceptance, or run authorization |
| Synthetic CI | From-scratch synthetic challenges and synthetic labels | Contract diagnostics and synthetic receipts | Copied, transformed, or encoded official ARC tasks |
| Training | Public training demonstrations and mechanically assigned folds from the pinned source | Frozen solver/config/model identities | Public-evaluation labels or feedback, hidden challenges, or manual task selection after seeing results |
| Prospective public-evaluation runner | The frozen solver/config and label-free public-evaluation challenge, with no solution mount | A closed run manifest and hashed submission frozen before the scoring grant is issued | Labels, scores, or prior correctness signals exposed to the solver; no such external runner or OS sandbox is implemented here |
| Public-evaluation scorer | A preflight-completed, single-use grant; its coupled reservation and completion proof; its exact config, run manifest, input manifest, and submission; the label-free challenge; and separately mounted solutions matching the independent source commitment | Aggregate-only score receipt after an exclusive action claim | Reuse, per-task results, solution grids, predictions, or task IDs in success or failure output |
| Kaggle notebook | The mounted competition challenge and mandatory sample submission, source-locked public assets, strict private metadata, and one bound run grant | `/kaggle/working/submission.json` | Internet, solution labels, credentials in tracked files, task bodies in logs, or submission authority |
| Kaggle evaluator | The closed notebook output selected by a human | Platform result | Hidden challenge or label material returned to the repository |
| Ignition | Exact hashes, current human-reviewed rules, a narrow scope, expiry, and a fresh grant ID and nonce | One coupled reservation record, then a separate completion proof only after artifact binding succeeds | Credentials, redirectable ledgers, broad permission, reusable approval, or authority inferred from CI/publication |

There is no feedback edge from either scorer to the solver. Both attempts for a
test input are generated in one solver call before scoring. A changed branch,
tree, source lock, notebook, solver, configuration, input manifest, hardware
binding, output, rules digest, or notebook version invalidates the relevant
grant.

## Source authority

| Source | Context role | Authority ceiling |
| --- | --- | --- |
| `Grativy6/hearthline-plays` anchor | Normative lineage | Establishes only the inherited parent commit/tree and repository license |
| Pinned `arcprize/ARC-AGI-2` Git source | Normative identity for externally mounted public bytes | Does not identify hidden Kaggle bytes, permit vendoring, or permit evaluation tuning |
| ARC Prize competition track and guide | Official format, scoring, and methodology context | Mutable; unusable for an external grant until freshly captured and reviewed by a human |
| Kaggle competition, evaluation, data, and rules pages | Official platform state and binding competition terms | Mutable; a digest neither accepts terms nor proves account/competition access |
| Pinned `arcprize/arc-agi-benchmarking` Git source | Inspected implementation reference | Not copied and not the scoring authority because its task weighting differs |
| Pinned `Kaggle/kaggle-api` Git source | Inspected notebook-metadata reference | Does not authorize credential use, a notebook version, a run, or a submission |
| Pinned GitHub Actions | Read-only build dependencies | Prove only that the named CI steps ran under declared workflow permissions |
| ARC-AGI-3 sibling titles | Conceptual precedent for provenance and gates | No code, schema, runtime, state, or branch dependency crosses into this title |
| Bounded Hearthline method sources | Off-by-default static-task design vocabulary in `ARC2_METHOD_MAP.md` | No source code, private corpus, weights, runtime behavior, performance, independence, or authority claim crosses |
| Synthetic fixtures | Local contract-test authority | No claim about official tasks or solver capability |

## Contract ownership

| Contract | Governs | Important semantic check outside JSON Schema |
| --- | --- | --- |
| `challenge-set.v1.schema.json` | Label-free tasks with demonstrations and test inputs | Grids are rectangular; language-specific booleans are rejected; no test output reaches `TaskView` |
| `submission.v1.schema.json` | Exactly `attempt_1` and `attempt_2` for each test input | Task IDs and ordered test counts exactly match the challenge; duplicate attempts are diagnostic only |
| `kernel-metadata.v1.schema.json` | Closed Kaggle notebook metadata | Private/internet settings, explicit TPU disablement, and reviewed GPU/machine shape agree; competition source is the exact slug, all noncompetition source arrays are empty in v1, and the exact metadata digest agrees with the grant |
| `solver-config.v1.schema.json` | Frozen solver and budget configuration | Solver identity, attempts, network boundary, models, seed, and positive non-boolean budgets agree with the run |
| `input-manifest.v1.schema.json` | Immutable external challenge identity | Raw and canonical-semantic identities/counts agree with the source lock; public splits bind the exact ARC-AGI-2 path/tree, while hidden input binds a separately frozen Kaggle artifact and makes no public-Git identity claim |
| `source-lock.v1.schema.json` | Immutable Git identities and mutable official surfaces | Expected pins are exact, repositories and URLs are unique, licenses are allowed, and mutable reviews are fresh for external modes |
| `run-manifest.v1.schema.json` | Reproducibility and safety assertions for one run | Hashes bind the actual artifacts; times are ordered and elapsed time does not exceed the wall budget; mode/fold fields agree; discovered counts are measured rather than assumed |
| `score-receipt.v1.schema.json` | Output-pair-weighted exact-match evidence | Numerator and denominator agree with the exact rational and decimal display; public evaluation stays aggregate-only |
| `ignition-grant.v1.schema.json` | Expiring, single-use human authority | Hashes match, issue precedes expiry, the grant-ID/nonce pair is unused and reserved before access/action, successful artifact binding creates a separate completion proof, and wording exactly matches scope |

The schemas use JSON Schema draft 2020-12 and close every repository-owned
object with `additionalProperties: false`. The standard-library semantic
validator is runtime-normative for relationships a schema cannot safely
express, including rectangular grids, parity, duplicate identities, time
ordering, freshness, and single-use state.

## Identity and scoring boundaries

- The title descends directly from `arc-agi/main` commit
  `228d80f0559277c55031f4a80f6179320e10364c`, tree
  `532e178ecd41410e5e9038c647141f2cbe32f01d`.
- The pinned public dataset identifies an external mount. It does not authorize
  vendoring, make public evaluation development data, or identify Kaggle's
  hidden rerun set.
- `arcprize/arc-agi-benchmarking` is an inspected reference, not the 2026
  Kaggle scoring oracle. This title weights individual test outputs:
  `sum(any exact attempt match) / number of test outputs`.
- The notebook requires `sample_submission.json`, validates its closed
  two-attempt shape, and requires exact task/test-input parity with the mounted
  challenge. No fixed hidden-task count is a contract.
- Git pins are immutable. All seven official web surfaces in the initial lock
  are `UNFROZEN_REVALIDATE_BEFORE_EXTERNAL_GRANT`; their null digests are valid
  only for development preparation.
- The non-consuming development/CI inspection also accepts a coherent, fresh,
  fully human-reviewed source state so a later externally ready clean commit
  can remain CI-verifiable. It neither writes ledger state nor authorizes use.

## Repository exclusion boundary

No official task data, public-evaluation answers, hidden holdout material,
model weights, provider prompts containing tasks, raw predictions, Kaggle
outputs, account contacts, credentials, tokens, private grants, or per-task
correctness belongs in this branch. Runtime artifacts live outside the tracked
tree. Only deliberately sanitized aggregate receipts may later be considered
for publication.

CI proves offline conformance against synthetic inputs. It does not accept
rules, spend a grant-ID/nonce pair, start a notebook, submit an output, prove
eligibility, or establish competition standing.

`StaticSolver` is an information-minimizing interface, not an operating-system
sandbox. This title exposes no external-evaluation runner: before a competitive
solver can be bound, the runner and scorer must execute in separate processes
with solution paths absent from the solver mount. The monotonic deadline is
checked before and after each solver call, but Python cannot preempt arbitrary
in-process code; `max_work_units` remains solver-enforced and CPU budget remains
provenance until such a process supervisor exists. Those limitations keep the
external state closed rather than becoming implicit capability claims.
