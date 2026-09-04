# Experiment Protocol

Use this protocol for every future Biohub cell-tracking experiment. It keeps an
exploratory play result, a local benchmark, and an official Kaggle result from
being confused with one another.

## 1. Status and claim ladder

Use the narrowest status earned by the evidence:

| Status | Evidence permitted |
| --- | --- |
| `PREPARED_NOT_RUN` | Branch, locks, guards, schemas, and offline synthetic tests only |
| `LOCAL_PLAY` | An authorized training subset was inspected or processed; no official comparability implied |
| `LOCAL_BENCHMARK` | A pinned pipeline was evaluated on a named, embryo-disjoint local split with complete receipts |
| `OFFICIAL_KAGGLE` | A separately authorized Kaggle run or score has a platform receipt and exact artifact identity |
| `PARTIAL` | Some required evidence is missing; state exactly what remains |
| `BLOCKED_RESOURCE` | Required hardware, storage, data, or runtime is unavailable |
| `BLOCKED_EXTERNAL` | Account, rules, platform, hidden evaluation, or other external state prevents completion |

`PREPARED_NOT_RUN` does not imply competition entry; entry is separately
`NOT_ENTERED_UNVERIFIED` until a user-controlled action and receipt establish
otherwise. Never promote a schema check, synthetic fixture, reduced smoke run,
or local score into a higher claim. Public overview, rules, and source metadata
were inspected during preparation. Authenticated Kaggle account/API/environment
interaction, competition-data consumption, runs, and submissions remain at zero.

## 2. Gates before data access

Do not start a data-bearing run until all applicable gates are recorded:

1. the user has separately authorized the specific access or run;
2. the current Kaggle
   [overview](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/overview)
   and [rules](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/rules)
   have been reviewed;
3. the exact data root passed `tools/check_data_home.py`;
4. the data root is not on the current E: repository volume and does not overlap
   this repository;
5. the source lock and station verifier pass;
6. the planned claim, split, resource budget, and stop conditions are written
   before execution.

The recorded entry/team-merger deadline is September 22, 2026 at 23:59 UTC;
the recorded final deadline is September 29, 2026 at 23:59 UTC. Reconfirm both
on the live pages because organizers may update them.

## 3. Freeze every experiment input

Create a unique run ID using UTC time plus a short slug. Before execution,
record:

- repository commit and dirty-tree status;
- `source-lock.v1.json` hash;
- organizer/scorer revision
  `075fc5f5a52d11077f9dc2b074644618f26939e2`;
- `tracksdata` revision
  `63a1912f3b6ebd1536a2e8a8adfdf7f5eb84efa4`;
- dependency lock and environment inventory;
- model/weight origin and cryptographic hash;
- data manifest with relative paths, sizes, and hashes where practical;
- exact embryo-grouped split manifest and its hash;
- complete configuration and random seeds;
- hardware, OS, CUDA/driver, and resource budget;
- whether the run is `play`, `benchmark`, or `submission-rehearsal`.

Keep host-specific absolute paths in the external receipt, not in deterministic
manifests committed to Git.

## 4. Data and split discipline

- Derive embryo identity from the sample naming or metadata confirmed by the
  data manifest. All fields of view, frames, and temporal windows from one
  embryo must remain on the same side of a split.
- Prefer leave-one-embryo-out reporting when the available training embryos make
  that possible. Report each fold separately as well as any declared aggregate.
- Never random-split frames, windows, or videos when this can leak embryo or
  overlapping spatial context.
- Generate the split manifest once with `tools/make_embryo_splits.py`, review it,
  hash it, and reuse it unchanged for comparisons.
- Ground truth is sparse. Unannotated cells are unknown, not negatives. Do not
  train absence penalties or report recall denominators as though labeling were
  exhaustive unless the method explicitly accounts for sparsity.
- Visible test material is plumbing-only. Do not use it to select a method,
  tune a threshold, estimate generalization, or claim hidden-test performance.
- Pseudo-labels, if later used, must be generated out of fold and recorded as a
  separate input.

## 5. Play lane

The play lane establishes understanding before complexity:

1. load a small contiguous training window without materializing the full volume;
2. confirm axes, dtype, chunking, physical voxel scale, and GEFF coordinates;
3. create a qualitative viewer overlay;
4. detect candidates with a documented classical detector;
5. link only adjacent timepoints using distances converted to physical units;
6. disable divisions initially;
7. run graph validation and, when ground truth permits, the pinned scorer;
8. save the configuration, overlay, metrics, and failure notes.

This lane may inform hypotheses. It is not an official baseline reproduction.

## 6. Benchmark lane

First reproduce the pinned organizer architecture and scorer. Preserve the
organizer behavior as one named baseline, then make one attributable change at
a time:

1. detection or image preprocessing;
2. linking or motion gating;
3. global graph constraints;
4. division modeling.

Do not silently rely on an automatically generated random video split,
unrecorded randomness, or a checkpoint selected by a proxy metric. Supply the
reviewed embryo split, seal seeds and configuration, and choose checkpoints
using a declared criterion. Record whether mixed precision, test-time
augmentation, or an optimizer/ILP is enabled because each changes runtime and
comparability.

At the pinned organizer revision, wrap and receipt these concrete baseline
traps before making a comparative claim:

- the trainer's fallback split random-shuffles video stems instead of grouping
  by embryo;
- per-item augmentation constructs `np.random.default_rng()` independently, so
  a DataLoader seed alone does not seal randomness;
- the detection loss treats every non-ground-truth voxel as negative even
  though annotations are sparse;
- checkpoint selection uses an `accuracy * node_recall` proxy rather than the
  official graph score; and
- `evaluate.py` scores only the intersection of prediction and ground-truth
  names, allowing missing datasets to be skipped unless completeness is checked
  separately.

Accordingly, pass an explicit embryo-grouped split, control every RNG source,
declare how sparse negatives are handled, record the checkpoint criterion, and
fail closed when any expected dataset is missing. Preserve an unmodified
organizer-baseline result separately from wrapped variants.

The official aggregate is based on adjusted edge Jaccard plus `0.1 ×` division
Jaccard. Always use the pinned patched implementation for recorded local
comparisons; do not reimplement the metric as the authority. The official node
assignment uses physical distance with a 7 µm limit, so record scale conversion.

## 7. Graph and artifact validation

Before scoring or packaging, reject or explicitly account for:

- edges not connecting `t` to `t+1`;
- backward, self, duplicate, dangling, or cross-dataset edges;
- non-finite or out-of-bounds coordinates;
- missing datasets or invalid node-ID references;
- indegree greater than one or outdegree greater than two;
- inconsistent voxel/physical coordinate conversion;
- malformed CSV row types, sentinel fields, or non-consecutive output index.

Use `tools/validate_submission.py` for the CSV surface. A valid CSV proves only
local structural conformance; Kaggle acceptance and scoring remain external.

## 8. Required results and diagnostics

For every completed local fold, preserve:

- adjusted edge Jaccard and division Jaccard separately, plus the declared
  aggregate;
- edge and division TP, FP, and FN counts;
- node recall and predicted-to-estimated node ratio when supported by the
  official scorer;
- per-embryo and per-sample results, without hiding failed samples in an average;
- displacement, track-length, and division-count distributions;
- graph-integrity results;
- representative qualitative overlays and named failure cases;
- wall-clock time, peak RAM, peak VRAM, warnings, and exit status.

Negative or null results are valid. Record displaced costs—memory, runtime,
coverage, or graph validity—alongside any apparent metric gain.

## 9. Receipt layout

Keep each run's durable record under `receipts/<RUN_ID>/` and large outputs on
the external data root. A receipt should identify, at minimum:

```text
receipt.json
config.json
environment.txt
data-manifest.sha256
split-manifest.sha256
metrics.json
graph-validation.json
artifact-hashes.sha256
stdout.log
stderr.log
```

Receipts must not contain credentials, competition data, hidden material, or
unredacted absolute paths that disclose secrets. If execution stops early,
retain the immutable failure and mark the missing evidence explicitly.

## 10. Submission gate

Submission is outside the default authority of this branch. After explicit
authorization, a candidate must still pass all of these checks:

- current rules and eligibility reviewed and accepted by the user;
- notebook runs with internet disabled;
- dependencies and weights are available through allowed, pinned inputs;
- a hidden-size rehearsal fits below the current 12-hour CPU/GPU limit with
  margin;
- `submission.csv` passes local validation and contains every expected dataset;
- code, notebook version, output hash, and user-selected submission identity are
  recorded;
- no upload or final selection occurs beyond the exact authorization given.

A public or private leaderboard score is reported only from its platform
receipt. Local estimates remain labeled local.
