# ARC-AGI-2 bounded method map

**Status:** documentation-only candidate context; every method is off by
default.

This map makes the Hearthline method vocabulary available for static
ARC-AGI-2 design without importing the ARC-AGI-3 runtime, private corpus,
weights, task data, or evaluation feedback. The shipped solver is still only
`IdentityZeroBaseline`; there is no executable method switch in this title.
Activating any row requires a successor solver/config identity, synthetic or
training-only tests, a fresh commit and tree, and any later external grant.

## Static-task translation

| Candidate method | Narrow static ARC-AGI-2 translation | Off behavior and ceiling |
| --- | --- | --- |
| A0BK advisory gate | Before a human boundary, compare the proposed run's identity, witness, scope, authority, consequence, budget, and re-entry state with its exact artifacts. | Omit the advisory vocabulary while retaining the non-ablatable preflight and human grant. It cannot create a grant, credential, prediction, or A0BK-conformance claim. |
| FBT continuation split | Keep mutable search/cache state separate from an immutable, version-bound derivation record for one task. Re-entry may cite the record but must reopen any divergence. | Reconstruct from the frozen task/config only. Cached state is neither evidence nor renewed authority; no FBT implementation, weights, or performance credit is inherited. |
| GOLD `1+5` / new-geometry lens | Compare one common grid/object projection with five separately declared views—for example spatial/topological, object correspondence, palette role, count/repetition, and candidate transformation—and keep route residuals separate. | Use the common projection and baseline grid geometry only. There is no pooling, privileged geometry, optimizer, physics, consciousness, or ARC-capability claim. |
| PAL role ledger | Keep observations, derived features, hypotheses, candidate transformations, predictions, score receipts, grants, custody, and residuals in their declared roles. | Retain only ordinary typed fields. No truth certificate, independent corroboration, full PAL conformance, or authority backflow follows. |
| Single Cut checkpoint | At an exact completed-task or batch boundary, bind the task/config identity, deterministic cursor, declared work projection, and completed outputs before re-entry. | Restart from immutable inputs and ordinary run records. A checkpoint is not progress, extra budget, correctness, or permission. |
| Distinction grouping | Group statements as direct task observation, derived relation, hypothesis, unresolved item, or plan-only candidate before choosing outputs. | Keep the fields ungrouped. Group membership cannot fabricate evidence, average confidence, or promote a hypothesis. |
| `advance` atomic promotion | Under a rule frozen before evaluation, either install one complete candidate transformation/output field with all evidence handles or leave it unpromoted with a residual. | Promote nothing. Partial mutation, plan-to-fact conversion, and retroactive edits are forbidden. |
| Paired Sparks | Produce two source-linked, immutable candidate records from the same label-free task view using declared distinct lenses; comparison preserves agreements, dependencies, and disagreements without automatic averaging. | Use one baseline solver record. Same-model outputs are dependent evidence, not independent votes, and neither Spark may see labels or score feedback. |
| Thulia custody | Maintain a partitioned index of the two Spark records and their comparison, exposing only the smallest source-bound summary needed for output selection. | No custody layer. Thulia cannot merge source ledgers, solve as an undeclared third Spark, select a score-informed revision, approve a grant, or emit an external action. |

These are prospective translations, not implemented solver features or an
ablation result. Any comparison must be frozen before measurement, use
synthetic fixtures or mechanically assigned public-training folds, and remain
outside the one-shot public-evaluation and hidden Kaggle holdouts.

## Public source identities and claim ceilings

| Source identity | Used here only for | Claim ceiling |
| --- | --- | --- |
| [A0 Software Boundary-Layer Kernel v0.10.0](https://doi.org/10.5281/zenodo.22168887), artifact SHA-256 `f3b57da98db3b105e6a67b2c76471123365041ce86e53977be5aa7002b84c46a`, CC-BY-4.0 | A0BK advisory vocabulary | Conceptual context only; no source code, authority, or conformance crosses. Zenodo metadata says `0.10` while the source identity/filename says `0.10.0`; the discrepancy remains visible. |
| [Full Bandwidth Is Not Full Trace v0.1](https://doi.org/10.5281/zenodo.22228162), [registry](https://github.com/Grativy6/hearthline/blob/f78e95a02fea16a7bd23ac01acbff4040a01bcd6/docs/research-station/source-identities.json) commit `f78e95a02fea16a7bd23ac01acbff4040a01bcd6`, tree `68042cf2a978e55472579058d4aaf57da72a7ed0`, blob `bd6fa84302d53ea5ae54e5e7ac4bdc3ed8162ed9` | FBT separation of working state from typed trace | Publication bytes are not admitted here; no code, weights, causal trace-fidelity, ARC, or safety result crosses. |
| [GOLD v0.1](https://doi.org/10.5281/zenodo.22236848), same exact registry commit/tree/blob | `1+5` comparison and residual vocabulary | Publication bytes are not admitted here; no privileged geometry, universal optimizer, physics, consciousness, PAL-canon change, or authority crosses. |
| [PAL v2.3](https://doi.org/10.5281/zenodo.22240134), package SHA-256 `5b133741d43ece584caffab1285af8804bfac6699894e92e2e08436b3b337bf1`, CC-BY-4.0 | Typed roles, authority ceilings, residuals, local closure, and reopening | No full-package conformance, truth, independence, or external authority crosses. |
| [Single Cut Transport Lemma v0.2](https://doi.org/10.5281/zenodo.22239108), PDF SHA-256 `e4b038d4a5e0f638d400af8610fb91373be2a22ec7bebbdb41a4061f85574b57`, verification bundle SHA-256 `dbd4c1f9b916842522b842e3bc57084b02a95a923d68db562a996cd61adda4c8`, CC-BY-4.0 | Exact checkpoint and typed re-entry vocabulary | Finite fixtures are not unbounded proof; heartbeat/checkpoint existence is not progress; recoverability is not authority. |
| [Boundary-Readable Trace and Absorber-Informed Closure v2.0](https://doi.org/10.5281/zenodo.22261831), canonical PDF SHA-256 `f9e699ad4a8541506ecc6678c3296bdf4fbe4dd249a0dd6759c7fd0d22837e0a`, CC-BY-4.0 | Distinction preservation and atomic promotion vocabulary | Readability is not decoding; verification without an external grant is preparation only; no universal or physical claim crosses. |
| [Hearthline ARC protocol](https://github.com/Grativy6/hearthline-plays/blob/fb5759134a5230e434f496088460a9dc8493f099/launch/strategy/HEARTHLINE_ARC_PROTOCOL.md), commit `fb5759134a5230e434f496088460a9dc8493f099`, tree `cb7789ffe985b8802e07d1b1befbcadffdcf93f2`, file blob `216f5d96e4a8c5bd44379a7c8577f4886c0efbbb`, repository CC-BY-4.0 | Paired-Spark and Thulia custody vocabulary | No ARC-AGI-3 frames, actions, state, results, code, or runtime dependency crosses; no capability or independence claim is inherited. |

These context citations are intentionally separate from
`provenance/official-sources.lock.json`, whose scope is official ARC/Kaggle/CI
readiness identity. A citation is not an executable dependency, evidence that
a method ran, or run authorization.
