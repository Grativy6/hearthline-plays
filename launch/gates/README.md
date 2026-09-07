# Two human ignition gates

Both gates are closed. The tools in this repository only validate and consume
one-use grant documents; they cannot authenticate, browse, stage, submit, or
perform an ARC/Kaggle action. A consumed grant is not evidence that the later
human effect happened.

The offline [Homecoming return queue](../../design/RETURN_QUEUE.md) is not part
of this gate-consumption path. It queues synthetic receipt-bound return bundles,
not human grants, and it does not wait around, weaken, replace, or renew the
fail-closed ledger lock below. Concurrent gate consumption therefore continues
to fail closed exactly as documented and tested.

The reviewed private kernel version-4 evidence now closes one exact predecessor
runtime as `FROZEN_POST_STAGE_SUCCESSOR` in `launch/source-lock.v4.json`. That
stage predates the current repair: it does not verify or authorize a successor
snapshot. Both gates are closed. Before Gate B can validate, an exact clean
successor commit must be rebuilt and recorded as a verified snapshot,
receive a fresh Gate-A grant, complete one exact private restage, and record a
human-reviewed v4 stage result. The old grant is expired, immutable, and never
reusable; the runtime review receipt grants local repair authority only.

The live Kaggle competition record inspected on 2026-09-04 reports **one
submission per day** and **two final submissions**. The pinned starter's
five-per-day statement is stale. A human must read the live rules again on the
UTC day of each gate and use the smaller current limit if any source conflicts.

## Common offline preflight

Start from the exact commit intended for staging and a clean worktree:

```sh
make test
make package USERNAME=YOUR_KAGGLE_SLUG ACCELERATOR=cpu
make verify-candidate
```

Run candidate materialization and both gate commands from a Linux/POSIX host.
They deliberately fail closed on hosts without no-follow directory-descriptor
operations. The research-station CI therefore exercises the operational
candidate and gate boundary only on Linux/POSIX with Python 3.12. The gate
suite directly exercises its unsupported-host refusal during grant
consumption. Candidate materialization and verification are tested only on a
supported host; no Windows compatibility claim is made, and no weaker
operational path check is emulated there.

`build/` is ignored and is never a trust root. The verifier reads its three
files once through no-follow descriptors, regenerates their exact bytes from
the current committed Git objects, and places the already-verified bytes under
`build/verified/<snapshot-sha256>/`. The manifest is one regenerated output.
Review the content-addressed snapshot and `build/verification.json` before
granting anything. A placeholder username, dirty worktree, symlink, duplicate
JSON key, unexpected notebook cell/output/source, metadata source, changed
byte, or stale lineage closes Gate A.

The content-addressed name is a local consistency binding, not immutable
storage: a filesystem owner can replace local bytes. Each gate therefore
reruns exact committed regeneration against the selected snapshot, and grant
consumption reruns the complete raw phase validation while holding the closed
ledger lock. This remains procedural evidence rather than a cryptographic
signature or independent witness.

The package follows the structural contract derived from
`arcprize/ARC-AGI-3-Kaggle-Starter` commit
`eeb1535404f321d280a8f9194bbc1d7aca5f05fc`: Python 3.12,
`agents.agent.Agent`/`MyAgent`, the competition rerun signal, offline wheel
source, bundled Agents framework, and `submission.parquet`. The prior reviewed
stage bound Python 3.12.13, all 875 canonical distributions, the admitted
framework files, and `LICENSE`. A successor stage must reproduce that entire
locked runtime closure; local compatibility still cannot establish a private
gateway outcome.

## Gate A — private kernel staging only

1. Copy `kaggle-stage-grant.v2.template.json` (the filename is retained for
   path continuity; its record schema is v3) to the ignored
   `.hearthline/grants/` directory.
2. Copy the complete `verified_snapshot.candidate_binding` only from
   `build/verification.json`. Re-read the live rules and fill the current
   UTC timestamps, a fresh 32-lowercase-hex nonce, account/kernel identity,
   human name, and acknowledgements. The grant may live for at most two hours,
   and its issuance, consumption, and expiry must all remain on one UTC
   calendar day.
3. In an interactive terminal with all Kaggle credential environment variables
   cleared, consume it once:

   ```sh
   make gate-a GRANT=.hearthline/grants/stage.json
   ```

The command writes only an ignored local consumption receipt. After it passes,
the named human may separately configure the modern project-local token
contract (`.kaggle/access_token`, mode `0600`, exported only as
`KAGGLE_API_TOKEN`) and manually invoke the official Kaggle CLI to stage the
exact private kernel from the printed content-addressed snapshot directory.
Do not stage the mutable `build/` parent. There is intentionally no repository target
for that external operation. Never print, commit, copy into CI, or place the
token in a grant/receipt.

The human must finish that manual stage on the rules-check UTC day and strictly
before the printed `authorized_effect_deadline_utc`. The Gate A receipt carries
the exact authorization issuance, expiry, and rules date into Gate B. A stage
recorded after that deadline or on another day is rejected. The stage timestamp
is human-attested rather than independently observed by this repository, so a
receipt cannot make a late platform action valid.

Gate A does not authorize competition ignition. Record the resulting private
kernel outcome by filling `stage-result.v4.template.json` (schema
`hearthline.arc3.kaggle-stage-result.v4`) under ignored
`.hearthline/receipts/`. Include the exact candidate, kernel/run identity,
private/offline settings, the canonical Gate A grant hash and chained
consumption receipt path/hash, the identical account and kernel identity,
reviewed `submission.parquet` hash, and no credential material. The Phase A
notebook prints one canonical `HEARTHLINE_STAGE_INVENTORY` line: copy its
complete Python/distribution list and Agents file plus `LICENSE` hashes into the
receipt, then reconcile them with `launch/source-lock.v4.json`. The result must
match the locked ordered inventory of exactly 875 unique canonical names,
including `arc-agi==0.9.8`, `arcengine==0.9.3`, and
`python-dotenv==1.2.2`, plus every sealed file and license hash. The separately
pinned public ARC-AGI source remains version 0.9.9. Public and platform runtime
identities must never be conflated. A failed, incomplete, unreviewed,
differently hashed, missing-inventory, reordered, or source-mismatched run keeps
Gate B closed.

The successor preserves the effective-distribution semantics that produced the
reviewed version-4 inventory. Equal canonical metadata aliases collapse. When
raw metadata exposes more than one version, `importlib.metadata.version` must
select exactly one of the observed versions; if it is absent or selects
anything else, validation fails deterministically and reports every observed
version. The locked 875-row list is therefore the reviewed active runtime, not
a claim that Kaggle contains no lower-precedence metadata shadows.

In the v4 stage receipt, `accepted_runtime_binding` carries the hashes of the
reviewed predecessor version-4 baseline. The separate `stage_evidence` object
must carry the new run's own evidence-manifest and log hashes; its manifest hash
must differ from the baseline. Baseline hashes must never be copied into the
new-run evidence fields.

The competition-rerun notebook does not rely only on that later result receipt.
It contains the verifier-owned complete ordered distribution inventory, exact
version/file/license bindings, and distinct public-source identities from the
committed v4 source lock. It checks them before gateway contact or copying and
again before importing/running the framework. Any drift aborts the rerun path.

## Gate B — one manual competition ignition (currently blocked)

Do not create or consume this grant from the present commit. The steps below
describe the successor-only path after an exact clean commit has produced a
verified snapshot, a fresh Gate-A grant has authorized one exact private
restage, and the resulting v4 evidence has been reviewed and recorded.

1. Copy `competition-ignition-grant.v2.template.json` (v3 record schema) into the ignored grant
   directory only after Gate A's run is complete and its exact output reviewed.
2. Bind the exact stage receipt path/hash, candidate snapshot, Gate A account,
   and Gate A kernel. Re-read the
   live rules again, confirm an allowance remains that UTC day, select only
   `submission.parquet`, and issue a fresh grant lasting at most one hour.
   Its issuance, consumption, and expiry must all fall on that same UTC
   calendar day; set the expiry before midnight.
3. Consume it in an interactive credential-free terminal:

   ```sh
   make gate-b GRANT=.hearthline/grants/competition.json \
     STAGE_RECEIPT=.hearthline/receipts/stage.json
   ```

After that validation, the named human may separately open Kaggle and make one
manual UI decision to submit the exact reviewed output **on the recorded UTC
day and strictly before the printed `authorized_effect_deadline_utc`**. No script here clicks
the UI, polls a run, or infers success. Append a new sanitized successor receipt
and update only `launch/status/current.json`; do not edit legacy status,
founding text, or sealed/reconciled history.

Only one Gate B may be consumed per UTC day. The chained local ledger rejects
missing, extra, malformed, duplicate-key, hash-mismatched, partially written,
or reordered records. It is still a local procedural attestation controlled by
the filesystem owner—not a digital signature, independent witness, or proof
that Kaggle accepted a stage or submission. The human must compare the actual
private UI/run evidence and keep external effects outside this repository. The
ledger limits grant consumption; it cannot observe when a human acts in the
platform UI, so an expired grant must never be used even if its consumption
receipt exists.
