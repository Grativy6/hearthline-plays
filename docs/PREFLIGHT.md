# ARC-AGI-2 offline preflight

**Disposition:** `PREPARED_NOT_RUN`

This preflight verifies repository structure and synthetic behavior. It is not
a rules acceptance, public-evaluation grant, Kaggle join, notebook version,
submission, score, or endorsement.

## Development gate

Run:

```bash
python -B -m unittest discover -s tests -p 'test_*.py' -v
python -B tools/preflight.py --mode dev
```

The development gate fails closed unless:

1. the title descends from anchor
   `228d80f0559277c55031f4a80f6179320e10364c` and records its exact tree;
2. every owned JSON and all nine closed schemas parse;
3. the immutable source identities and licenses match the lock;
4. mutable official pages remain explicitly unfrozen rather than represented
   as timeless rules;
5. Python compiles without writing bytecode;
6. synthetic challenges, solutions, and submissions pass closed semantic
   validation;
7. the two-attempt scorer gives output-pair-weighted exact pass@2;
8. two baseline builds serialize identically;
9. no official data, credentials, run material, notebook output, network call,
   or Kaggle action command appears in a tracked/committable surface; and
10. notebook metadata is closed, private, internet-off, and explicitly
    TPU-disabled in v1;
    `competition_sources` is exactly
    `["arc-prize-2026-arc-agi-2"]`, dataset/kernel/model source arrays are
    empty in v1, and the mandatory sample-submission path and exact parity
    check remain present.

Success prints `ARC2_READINESS_CONFORMANT_PREPARED_NOT_RUN`. That wording is a
repository result only.

## Public evaluation gate

Public evaluation is deliberately outside development CI. Before a single
local audit, the external-mode gate requires all of the following:

- a committed, clean solver/configuration hash frozen before access;
- an external data manifest whose exact filename/split, raw and
  canonical-semantic challenge SHA-256, byte count, and discovered
  task/test-input counts match an independent source-lock commitment;
- fresh, human-reviewed mutable-source snapshots;
- an already-closed run manifest and submission produced without labels;
- an unexpired `PUBLIC_EVAL_ONCE` grant bound to every relevant hash, including
  that run manifest, submission, and the independently locked solution-set
  semantic identity;
- an operator-enforced process/mount boundary that exposes solution files only
  to the scorer (the repository supplies no OS sandbox or supervisor); and
- aggregate-only output with no task IDs, grids, or per-task feedback.

In the committed `PREPARED_NOT_RUN` state, the implementation rejects
`--mode public-eval` while those mutable sources are unfrozen, before loading
the evaluation challenge.

Once a later human has frozen those sources and committed the exact artifacts,
the gate shape is:

```bash
python -B tools/preflight.py --mode public-eval \
  --grant /operator/private/public-eval-grant.json \
  --config /operator/frozen/solver-config.json \
  --input-manifest /operator/frozen/public-eval-manifest.json \
  --challenge-file /sealed/arc-agi_evaluation_challenges.json \
  --output-dir /operator/runtime/arc2-public-eval \
  --hardware-class local-cpu \
  --max-runtime-seconds 39600
```

All paths are operator-selected examples, not repository fixtures. After its
metadata-only checks, preflight reserves the grant ID and nonce as one coupled,
fail-closed record in the fixed ignored `ignition/consumption-ledger/`, before
opening the challenge for its final binding check. The isolated label-free run
necessarily predates its exact scoring grant. Preflight then reads one
challenge byte snapshot and proves that same snapshot's raw and
canonical-semantic digests, byte count, exact filename, and discovered
coverage; it never opens solutions. Only a successful binding check creates a
separate exclusive completion proof. The scorer requires both the reservation
and that completion proof. A partial, failed, or uncertain state remains spent
but is not scoreable; the CLI cannot redirect the ledger.

The separate scorer invocation is explicit and uses the same artifacts:

```bash
python -B tools/score_local.py --mode public-eval \
  --grant /operator/private/public-eval-grant.json \
  --config /operator/frozen/solver-config.json \
  --input-manifest /operator/frozen/public-eval-manifest.json \
  --run-manifest /operator/runtime/arc2-public-eval/run-manifest.json \
  --challenges /sealed/arc-agi_evaluation_challenges.json \
  --solutions /scorer-only/arc-agi_evaluation_solutions.json \
  --submission /operator/runtime/arc2-public-eval/submission.json \
  --receipt /operator/runtime/arc2-public-eval/aggregate-receipt.json
```

It claims the preflight-completed grant after verifying its coupled
grant-ID/nonce reservation, completion proof, and exact frozen
config/run/submission identities, before opening any scored artifact. It then
requires the scorer-only solution
set to equal the independent semantic commitment in the source lock. It emits
aggregate-only output, redacts all public-evaluation failure detail, and cannot
be repeated. No public evaluation was performed while preparing this title.

## Kaggle packaging gate

The current official material observed on 2026-09-04 describes a notebook-only
competition, no internet during evaluation, exactly two predicted grids per
test input, `submission.json`, and a runtime ceiling of 12 hours for CPU or
GPU notebooks. Every fact is revalidation-sensitive.

The Kaggle package gate binds the exact notebook, solver, configuration,
label-free challenge manifest, accelerator, source snapshots, and a budget
below the then-current ceiling. `tools/preflight.py --mode kaggle` remains
offline and rejects placeholder/unfrozen state. It contains no platform call.

Its argument shape mirrors public evaluation, omitting `--output-dir` and using
an ignored, filled metadata file plus a `KAGGLE_NOTEBOOK_RUN_ONCE` grant:

```bash
python -B tools/preflight.py --mode kaggle \
  --grant /operator/private/kaggle-run-grant.json \
  --config /operator/frozen/solver-config.json \
  --input-manifest /operator/frozen/kaggle-hidden-manifest.json \
  --challenge-file /external/arc-agi_test_challenges.json \
  --notebook-metadata /operator/frozen/kernel-metadata.json \
  --hardware-class kaggle-cpu \
  --max-runtime-seconds 39600
```

The grant-ID/nonce pair is reserved before the manifest is checked against that
actual label-free challenge, so a mismatch remains spent and produces no
completion proof. Only a successful binding creates the proof required before
the human may start the run. The hidden manifest binds a
fresh, human-frozen raw and canonical-semantic digest/count commitment for the
competition mount; the public repository pin does not identify hidden bytes.
Metadata must be private,
internet-off, and explicitly TPU-disabled in v1; its owner ID and
accelerator/machine shape are closed to the pinned Kaggle API's documented GPU
names (`NvidiaTeslaT4` or `NvidiaTeslaP100`), `competition_sources` is exactly
`["arc-prize-2026-arc-agi-2"]`, and dataset/kernel/model source arrays are
exactly empty in v1. Nonempty sources require a reviewed successor schema and
validator. The metadata's exact raw-byte hash is grant-bound. The gate spends
that one-run grant ID and nonce; only Christopher D. Pang can then perform the
separate platform action. Submission requires the scope-specific
`KAGGLE_SUBMIT_ONCE` template and is intentionally not a repository command.

The human run grant and human submission grant are separate. See
[`../ignition/README.md`](../ignition/README.md).

## Deliberately absent

- Kaggle credentials or credential discovery;
- Kaggle API calls;
- official task files;
- public evaluation execution;
- model downloads or network installers;
- notebook pushing, running, polling, or submission;
- score claims; and
- ARC-AGI-3 interactive runtime machinery.

## Stewardship

Christopher D. Pang retains authorship, stewardship, and approval authority.
AI is a tool and cannot satisfy any human gate.
