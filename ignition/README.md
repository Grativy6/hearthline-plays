# Human ignition

**State:** `PREPARED_NOT_RUN`

**Steward and author:** Christopher D. Pang

This directory documents authorization; it is not an execution interface.
Repository preparation, a source digest, green CI, publication, or AI-assisted
work never authorizes access to sealed evaluation data or contact with Kaggle.
AI is tooling only and cannot approve a grant, accept rules, use an account,
start a notebook, or submit an output.

## Narrow grant scopes

| Scope | Permits exactly once | Does not permit |
| --- | --- | --- |
| `PUBLIC_EVAL_ONCE` | One sealed, aggregate-only audit of the frozen solver | Inspection, per-task feedback, tuning, Kaggle activity, or a repeat |
| `KAGGLE_NOTEBOOK_RUN_ONCE` | One run of the bound notebook version and artifacts | Submission, a changed version, a retry, or broader account activity |
| `KAGGLE_SUBMIT_ONCE` | One submission of the bound immutable notebook version and output hash | A notebook run, a changed output, a later version, or a retry |

No wildcard, recurring, multi-run, or combined scope exists. A grant contains
artifact identities only; it must never contain a password, API key, token,
cookie, credential path, or contact list.

## Before creating a grant

1. Freeze a clean title commit and tree descended from the recorded anchor.
2. Personally review the live official pages relevant to the intended scope.
   Rule acceptance, eligibility, external-data terms, and account authority are
   human responsibilities; a page hash is not acceptance.
3. Save reviewable human-readable snapshots outside official task-data paths.
   Record canonical URLs, retrieval UTC, SHA-256 digests, human reviewer, and a
   future `revalidate_before` time. External modes fail while any required
   source remains unfrozen or stale.
4. Validate the closed solver configuration and input manifest. The latter
   must bind raw and canonical-semantic challenge identities plus byte/count
   parity to the independent source-lock commitment. Public splits bind the
   exact pinned ARC-AGI-2 path/tree; Kaggle hidden input instead requires a
   fresh human-frozen competition-artifact commitment.
5. For Kaggle, fill and validate a closed metadata file with `is_private: true`,
   `enable_internet: false`, `enable_tpu: false` in v1, the reviewed
   accelerator/machine shape, `competition_sources` exactly
   `["arc-prize-2026-arc-agi-2"]`, and empty
   dataset/kernel/model source arrays in v1. A nonempty source requires a
   reviewed successor contract. Bind the metadata's raw-byte SHA-256 in the
   Kaggle grant.
6. Compute the exact source-lock, notebook, solver code, configuration, input
   manifest, metadata (when applicable), and rules hashes. For public
   evaluation, first close the label-free run, then bind the exact run manifest
   and submission plus the source lock's independently committed solution-set
   semantic hash. Bind the actual hardware and a runtime limit below the
   reviewed platform ceiling, with shutdown and serialization margin.
7. Generate a cryptographically random nonce and a unique grant ID. Neither may
   have appeared in the canonical local consumption ledger.

## Create and consume one grant

Copy exactly one matching template to an ignored operator-selected grant path:

- `public-eval-grant.template.json`
- `kaggle-run-grant.template.json`
- `kaggle-submit-grant.template.json`

Do not add or remove fields to change its scope. Replace every `TEMPLATE_`
value and all-zero hash with the exact frozen value, then set a short UTC
validity window and name the human approver.

For `PUBLIC_EVAL_ONCE`:

```text
I authorize exactly one sealed public-evaluation audit; its aggregate result will not be used for tuning.
```

For `KAGGLE_NOTEBOOK_RUN_ONCE`:

```text
I reviewed the current rules and authorize exactly one bound Kaggle notebook run; this is not submission authorization.
```

For `KAGGLE_SUBMIT_ONCE`:

```text
I authorize exactly one submission of this notebook version and output; no later version or retry is covered.
```

After metadata-only validation, offline preflight reserves the grant ID and
nonce as one coupled, fail-closed record in the single ignored
`ignition/consumption-ledger/`. It then checks one byte snapshot of the selected
label-free challenge against the bound manifest. Only success creates a
separate exclusive completion proof. That location cannot be redirected from
the CLI and is outside the private grant-input directory. A partial or corrupt
record/marker invalidates authorization; a crash, timeout, rejection, mismatch,
or uncertain outcome remains spent and is not scoreable or runnable. Never edit
the ledger back to unused.

For public evaluation, `score_local.py --mode public-eval` requires the same
grant, solver config, input manifest, run manifest, and submission. It verifies
their exact identities and relationships, requires the coupled reservation and
post-binding completion proof, then exclusively claims the grant before opening
the challenge, solution, or submission. The solution set must match the independently locked semantic
identity. A repeat cannot score, all successful output is aggregate-only, and
failure text contains no task identifier, grid, prediction, label, or artifact
path. The operator must provide separate solver and scorer process/mount
capabilities; this repository does not provide an OS sandbox or supervisor.

For a notebook run, the authorized human—not CI or a repository verifier—starts
the exact reviewed version. The notebook may write only the structurally
validated `/kaggle/working/submission.json`; it does not submit.

After a run, the human checks platform completion, notebook version, output
name and SHA-256, validation receipt, and logs for leakage. Submission then
requires a new nonce and a distinct `KAGGLE_SUBMIT_ONCE` grant that also binds
the immutable platform notebook/version ID, metadata SHA-256, output SHA-256,
and freshly reviewed rules SHA-256. No repository command submits; the human
performs the submission through the platform flow.

Any changed binding, expired review, expired grant, reused grant ID or nonce, ambiguous
platform state, failure, or retry returns the project to
`PREPARED_NOT_RUN`. Authorization never expands by inference.
