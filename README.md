# Hearthline ARC-AGI-2 Readiness

**Status:** `PREPARED_NOT_RUN`

**Intended title branch:** `arc-agi/titles/arc-agi-2-readiness-20260904`

**Series anchor:** [`arc-agi/main`](https://github.com/Grativy6/hearthline-plays/tree/arc-agi/main)

**Exact parent anchor commit:** `228d80f0559277c55031f4a80f6179320e10364c`

**Exact parent anchor tree:** `532e178ecd41410e5e9038c647141f2cbe32f01d`

This title is an offline, public-development readiness layer for static
ARC-AGI-2 tasks. It supplies a label-free solver contract, deterministic
format-only baseline, exact two-output submission builder, competition-aligned
local scorer, closed schemas, provenance, a quiet Kaggle notebook template,
and synthetic-only verification.

It contains no official task bytes, model weights, credentials, public
evaluation result, private or semi-private holdout, Kaggle run, submission,
score, or claim of competition standing.

## Current boundary

| Surface | State |
| --- | --- |
| Official public data vendored | `false` |
| Public evaluation opened by this title | `false` |
| Kaggle competition joined by this title | `false` |
| Kaggle API or notebook contacted | `false` |
| Credentials requested or used | `false` |
| Notebook run attempted | `false` |
| Submission attempted | `false` |
| Official score observed | `false` |
| Bound competitive solver/model | `UNBOUND` |

The included baseline only proves the plumbing. It copies each test input for
`attempt_1` and emits a same-sized zero grid for `attempt_2`. It has no claimed
ARC capability and is not authorized for public evaluation or Kaggle.

## Contract

For every test input, a solver returns exactly two complete grids before any
label or correctness feedback. A grid is rectangular, 1–30 cells on each axis,
and contains only integer symbols 0–9. The submission shape is:

```json
{
  "0123abcd": [
    {
      "attempt_1": [[0]],
      "attempt_2": [[0]]
    }
  ]
}
```

Local competition scoring is exact pass@2 per test output:

`sum(any attempt exactly matches each solution grid) / number of test outputs`

There is no pixel credit or task-level reweighting. The public evaluation set
is a sealed, one-shot audit lane; development and tuning use only deterministic
folds of public training data outside this repository.

## Map

- [`provenance/official-sources.lock.json`](provenance/official-sources.lock.json)
  pins the exact ARC-AGI-2, official benchmarking, Kaggle API, CI action, and
  parent identities. Mutable rules remain visibly unfrozen until a human
  reviews and snapshots them for an external grant.
- [`docs/CONTEXT_MAP.md`](docs/CONTEXT_MAP.md) distinguishes normative,
  inspected, and excluded context.
- [`docs/ARC2_METHOD_MAP.md`](docs/ARC2_METHOD_MAP.md) gives a compact,
  source-linked static-task translation of the requested Hearthline methods.
  Every method remains documentation-only and off by default.
- [`schemas/`](schemas/) contains nine closed JSON contracts, including strict
  solver configuration, external input manifest, and Kaggle metadata shapes.
- [`src/hearthline_arc2/`](src/hearthline_arc2/) contains the standard-library
  contract, validator, runner, baseline, and local scorer.
- [`tests/fixtures/synthetic/`](tests/fixtures/synthetic/) contains only small
  tasks authored for these tests.
- [`docs/PREFLIGHT.md`](docs/PREFLIGHT.md) and
  [`tools/preflight.py`](tools/preflight.py) define the fail-closed gates.
- [`ignition/README.md`](ignition/README.md) preserves human authority for a
  one-run grant and a separate one-submission grant.
- [`notebook/`](notebook/) is a cleared, internet-off packaging template, not
  evidence of a Kaggle version or run.

## Offline verification

From the repository root:

```bash
python -B -m unittest discover -s tests -p 'test_*.py' -v
python -B tools/preflight.py --mode dev
```

Build and score the synthetic fixture only:

```bash
python -B tools/build_submission.py \
  --challenges tests/fixtures/synthetic/challenges.json \
  --output-dir /tmp/hearthline-arc2-synthetic \
  --mode SYNTHETIC \
  --run-id synthetic-contract-check

python -B tools/score_local.py \
  --mode synthetic \
  --challenges tests/fixtures/synthetic/challenges.json \
  --solutions tests/fixtures/synthetic/solutions.json \
  --submission /tmp/hearthline-arc2-synthetic/submission.json
```

These commands require only Python 3.12's standard library. The tools contain
no Kaggle push, run, or submission path.

## Source and evaluation rules

- Public ARC-AGI-2 data stays in an external, source-pinned mount.
- Every external input manifest is checked against the actual label-free
  challenge's exact filename/split, raw and canonical-semantic SHA-256, byte
  count, and discovered task/test-input counts. Public splits must match the
  independently recorded repository path/tree commitment; the Kaggle hidden
  split must instead match a fresh human-frozen competition-mount commitment.
  An arbitrary-file hash or unrelated public Git pin is insufficient.
- Committed tests and CI remain synthetic-only.
- The unrestricted synthetic CLIs accept only bytes named in the committed
  authored-fixture lock; relabeling an official file as synthetic cannot enter
  that lane.
- The solver sees demonstrations and test inputs, never test outputs.
- External deployment must place scoring in a separate process over an already
  closed and hashed prediction; this repository does not provide that process
  supervisor.
- Public scoring has no default mode: it requires a preflight-completed
  `PUBLIC_EVAL_ONCE` grant bound to the exact config, run manifest, submission,
  and independently locked solution identity. Preflight first spends its
  coupled grant-ID/nonce pair, then writes a separate completion proof only
  after the challenge snapshot matches the manifest. The scorer requires both
  records and exclusively claims the completed grant before opening the scored
  artifacts. Reuse fails, and public validation failures are redacted.
- The 120-task public evaluation set is not used for iteration, prompt design,
  selection, ablation, or per-task error analysis.
- Hidden Kaggle challenges and predictions are not logged or persisted beyond
  the required platform output.
- Kaggle metadata must be private and internet-off, use the reviewed hardware
  shape, explicitly disable TPU in v1, set `competition_sources` to exactly
  `["arc-prize-2026-arc-agi-2"]`, keep dataset/kernel/model source arrays empty
  in v1, and match the exact hash in its run grant. Nonempty sources require a
  reviewed successor contract.
- `sample_submission.json` is mandatory in the notebook and must exactly match
  discovered task and test-input coverage before output is written.
- Current web rules and Kaggle runtime limits are mutable. Re-read, snapshot,
  hash, and acknowledge them before any external action.
- A passing test, source lock, notebook, publication, or AI suggestion cannot
  authorize a run or submission.

## ARC-AGI-3 boundary

This sibling title reuses ARC-AGI-3's useful provenance ideas—exact lineage,
claim ceilings, fail-closed validation, synthetic fixtures, read-only pinned
CI, and explicit grants. Its method map translates paired-Spark and custody
concepts into off-by-default static-task vocabulary only. It does not copy
interactive frames, actions, scorecards, private records, Creatures, code, or
environment tools. ARC-AGI-2 remains a static batch prediction surface.

## Stewardship and license

Christopher D. Pang is the project steward and author. AI systems are tools
used under human direction; they are not authors, owners, approvers, or sources
of run authority.

Except where a file says otherwise, original material on this branch is
licensed under the [Creative Commons Attribution 4.0 International
License](https://creativecommons.org/licenses/by/4.0/). Referenced datasets,
software, competition pages, names, and trademarks retain their own terms.
