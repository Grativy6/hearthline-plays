# Agent Instructions — Biohub Cell Tracking Title

These instructions apply to the entire title branch.

## Authority boundary

The station is `PREPARED_NOT_RUN`, competition entry is
`NOT_ENTERED_UNVERIFIED`, and `run_enabled = false`. Repository work may create
or improve local code, documentation, schemas, synthetic fixtures, and offline
tests. It does not authorize any of the following:

- Kaggle authentication or credential inspection;
- accepting rules, joining the competition, or changing team state;
- authenticated Kaggle API, account-state, or competition-environment
  interaction;
- downloading competition data or hidden evaluation material;
- training, inference, notebook execution, or leaderboard submission;
- claiming a local, official, public, private, or scientific score.

Read-only inspection of public rules, overview text, and public source
repositories is allowed when needed to keep the station accurate; record the
URL and observation time. Obtain explicit user authorization before crossing
any account, data, execution, or submission boundary. Local tooling success is
preparation evidence only.

## Repository and storage rules

- Work only on `kaggle/titles/biohub-cell-tracking-during-development`, whose
  parent series anchor is `8e1bdfa38d4d3169efffdd0cda2c06799981fbfe`.
- Never place the approximately 86–88 GB competition download, archives,
  extracted volumes, caches, model weights, or run outputs on the current E:
  FAT32 USB drive or inside the Git repository.
- A future data root must be an explicit path on a spacious internal drive or a
  suitable separate external drive. Run `tools/check_data_home.py` first. Do
  not weaken its repository-containment, FAT/FAT32, capacity, or removable-media
  gates.
- Keep secrets and Kaggle credentials outside Git. Never print credential
  values, copy them into receipts, or infer permission from their presence.
- Do not commit competition data, third-party source caches, weights,
  predictions, submissions, or environment-specific absolute data paths.
- The recorded CC0 label does not waive Kaggle's live entry, access, or
  data-security obligations.

## Source integrity

Use `source-lock.v1.json` as the authority for public dependencies. The required
pins are:

- organizer baseline/scorer:
  `075fc5f5a52d11077f9dc2b074644618f26939e2`;
- `royerlab/tracksdata`:
  `63a1912f3b6ebd1536a2e8a8adfdf7f5eb84efa4`.

Never replace a pinned revision with a branch name or floating `main`. A source
update is a new, reviewed experiment input: update the lock, rationale, tests,
and receipts together. Preserve third-party licenses and notices.

## Scientific integrity

- Use the play lane for understanding and the pinned official lane for
  benchmark comparison; never present one as the other.
- Group train/validation splits by embryo identity. Never split by frame,
  temporal window, or field of view when that can place one embryo on both
  sides.
- Treat sparse, unlabeled cells as unknown, not as confirmed negatives.
- Do not tune on visible test placeholders or infer hidden-test performance from
  them.
- Track physical voxel scale. Official matching uses physical distance; do not
  substitute raw voxel distance without an explicit conversion.
- Candidate lineage edges must connect `t` to `t+1`. Reject backward, skipped,
  self, duplicate, dangling, or otherwise invalid edges before scoring.
- Keep detection, linking, division, and global-constraint changes separable so
  evidence can identify where a gain or failure came from.
- A lower-cost smoke test, schema check, or synthetic fixture is not a substitute
  for a required official result. Report `PARTIAL`, `BLOCKED_RESOURCE`, or
  `BLOCKED_EXTERNAL` honestly when appropriate.

## Required evidence for later runs

Follow `docs/EXPERIMENT_PROTOCOL.md`. At minimum, record immutable code, source,
dependency, weight, data-manifest, configuration, seed, and split identities;
per-embryo metrics; graph-integrity checks; runtime; peak RAM/VRAM; and the exact
scorer revision. Keep local results separate from Kaggle receipts.

## Safe preparatory commands

```powershell
py -m unittest discover -s tests -v
py tools/verify_station.py
py tools/fetch_pinned_sources.py --check-only
```

`tools/fetch_pinned_sources.py --fetch` performs public GitHub network access.
Do not run it merely to prove that this branch exists. Kaggle actions remain
separately gated even if public sources have been fetched.
When invoking uv on this host, use `py -m uv`; bare `uv` is not assumed to be on
`PATH`.

## Live rules

Before any future competition action, review both the
[overview](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/overview)
and [rules](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/rules).
The recorded entry/team-merger deadline is September 22, 2026 at 23:59 UTC, and
the recorded final-submission deadline is September 29, 2026 at 23:59 UTC.
Treat live Kaggle text as authoritative if it changes.
