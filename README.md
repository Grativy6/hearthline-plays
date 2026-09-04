# Hearthline Playground — Biohub Cell Tracking During Development

This title branch reserves a careful Hearthline play and benchmark station for
the Kaggle competition **Biohub — Cell Tracking During Development**. The
scientific task is to detect cells in 3D microscopy volumes, link them through
time, identify divisions, and reconstruct lineages.

## Current state

- Branch: `kaggle/titles/biohub-cell-tracking-during-development`
- Parent series anchor: `8e1bdfa38d4d3169efffdd0cda2c06799981fbfe`
- Status: `PREPARED_NOT_RUN`; entry state: `NOT_ENTERED_UNVERIFIED`;
  `run_enabled = false`
- Kaggle authentication, rule acceptance, competition entry, data download,
  notebook execution, and submission: **not performed**
- Competition-data and holdout consumption: **zero**

The branch contains offline guardrails, validators, source pins, and operating
instructions. Passing those checks proves only that the station is prepared;
it is not evidence of a cell-tracking result or Kaggle score.

## Storage boundary

The competition download is approximately 86–88 GB before allowing for working
copies, caches, checkpoints, and predictions. **Do not put it on the current E:
FAT32 USB drive or anywhere inside this repository.**

After the PC upgrade, choose either:

- a spacious internal PC drive; or
- the new external drive, formatted with a suitable large-file filesystem.

A planning allowance of at least 200 GiB free is recommended for a complete
workspace. Before any future download, validate the exact destination with
`tools/check_data_home.py`. The guard rejects FAT/FAT32, repository-contained
paths, and paths that contain the repository. A separate removable drive also
requires the deliberate `--allow-removable` flag.

## Intended route

1. **Play lane:** inspect one explicitly authorized training sample, visualize
   it, detect candidate cells with an understandable classical baseline, and
   link detections only across adjacent frames.
2. **Benchmark lane:** reproduce the pinned organizer baseline and patched
   official scorer, then evaluate embryo-disjoint splits before changing the
   model.
3. **Kaggle lane:** only after separate authorization, current rule review,
   account entry, an internet-off notebook rehearsal, and a submission-file
   audit.

Start with [Getting Started](docs/GETTING_STARTED.md), then use the
[Experiment Protocol](docs/EXPERIMENT_PROTOCOL.md) for any later run.

## Pinned public sources

- Organizer baseline and patched scorer:
  [`royerlab/kaggle-cell-tracking-competition@075fc5f5a52d11077f9dc2b074644618f26939e2`](https://github.com/royerlab/kaggle-cell-tracking-competition/tree/075fc5f5a52d11077f9dc2b074644618f26939e2)
- `tracksdata`:
  [`royerlab/tracksdata@63a1912f3b6ebd1536a2e8a8adfdf7f5eb84efa4`](https://github.com/royerlab/tracksdata/tree/63a1912f3b6ebd1536a2e8a8adfdf7f5eb84efa4)

The machine-readable lock is `source-lock.v1.json`. Do not silently float
either dependency to a newer revision.

## Competition clock and rules

The official timeline currently states:

- Entry and team-merger deadline: **September 22, 2026, 23:59 UTC**
- Final submission deadline: **September 29, 2026, 23:59 UTC**

Review the live [competition overview](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/overview)
and [official rules](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/rules)
before any account, data, or submission action. The organizers may change the
timeline or rules; this branch does not substitute for the live pages or record
acceptance of them.

## Offline station checks

These commands do not authenticate to Kaggle, acquire competition data, train a
model, or submit anything:

```powershell
py -m unittest discover -s tests -v
py tools/verify_station.py
py tools/fetch_pinned_sources.py --check-only
```

The inert template `configs/local.example.toml` keeps `run_enabled = false`.
Do not turn it into a run configuration before the hardware/storage upgrade and
a new instruction authorizing the intended activity.

## License and attribution

Except where a file says otherwise, original material in this branch is
licensed under the repository's CC BY 4.0 license. Third-party code, data,
competition materials, names, and trademarks retain their own terms. Christopher
D. Pang directs and authors the project. AI systems are development tools, not
co-authors or independent scientific authorities.
