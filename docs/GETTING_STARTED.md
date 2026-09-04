# Getting Started

This guide prepares the station without contacting Kaggle or consuming
competition data. The current stopping point is intentionally
`PREPARED_NOT_RUN` while the PC, RAM, GPU, and storage are being upgraded.
Competition entry remains `NOT_ENTERED_UNVERIFIED`.

## 1. Confirm the title branch

From this repository:

```powershell
git status --short --branch
git rev-parse HEAD
```

The branch must be `kaggle/titles/biohub-cell-tracking-during-development`. Its
prepared parent series anchor is
`8e1bdfa38d4d3169efffdd0cda2c06799981fbfe`; later local commits will naturally
move `HEAD`, so verify the anchor from history or station metadata rather than
expecting `HEAD` to remain equal to it.

## 2. Run only the offline control-plane checks

Use a current Python 3 interpreter. The initial station checks use the standard
library and do not require a GPU:

```powershell
py -m unittest discover -s tests -v
py tools/verify_station.py
py tools/fetch_pinned_sources.py --check-only
```

Expected meaning:

- the unit tests exercise guards with synthetic or temporary inputs;
- `verify_station.py` checks the prepared-state files and invariants;
- `fetch_pinned_sources.py --check-only` validates the source lock without
  fetching it.

These checks do **not** validate Kaggle credentials, accept rules, join the
competition, download data, train a model, run inference, or earn a score. The
inert template `configs/local.example.toml` retains `run_enabled = false`. For
the present setup request, stop here.

## 3. Plan the future data home

The approximately 86–88 GB competition dataset must not live on the current E:
FAT32 USB drive or in this repository. Plan for at least 200 GiB free so the
download can coexist with caches, checkpoints, and predictions.

After the new hardware and storage arrive, validate an exact internal-drive
destination such as:

```powershell
py tools/check_data_home.py "D:\HearthlineData\biohub-cell-tracking" --min-free-gib 200
```

For the separately chosen external drive, acknowledge that removable target
explicitly:

```powershell
py tools/check_data_home.py "X:\HearthlineData\biohub-cell-tracking" --min-free-gib 200 --allow-removable
```

Replace `D:` or `X:` with the actual upgraded-machine drive. Do not use E: as a
placeholder. The current E: drive is categorically forbidden for competition
data. Other external storage is allowed after it is explicitly bound, is not
FAT/FAT32, does not overlap the repository, and passes the capacity check. The
removable flag does not override filesystem, containment, or capacity failures.

Recommended separation on the chosen data drive:

```text
biohub-cell-tracking/
├── archives/       # original downloads, if later authorized
├── competition/    # immutable competition files
├── cache/          # regenerable arrays and package caches
├── checkpoints/    # model weights
├── runs/           # predictions and local run outputs
└── manifests/      # hashes and inventories
```

Only small manifests and receipts that contain no protected data should be
copied back into Git.

## 4. Review live terms before any Kaggle action

The recorded dates are:

- entry and team merger: September 22, 2026 at 23:59 UTC;
- final submission: September 29, 2026 at 23:59 UTC.

Before authentication, entry, or acquisition, re-read the live
[overview](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/overview)
and [rules](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/rules).
The live pages are authoritative. Rule acceptance and account entry are manual,
user-controlled actions; the presence of a Kaggle CLI or credential file is not
authorization.

## 5. Prepare the future Python environment

On this host, invoke uv as `py -m uv`; do not assume bare `uv` is on `PATH`.
The bootstrap script performs a read-only preflight unless `-Create` is supplied:

```powershell
powershell -File tools\bootstrap_environment.ps1
```

After the upgrade, `-Create` may be used to create the local Python 3.12 virtual
environment. It still does not install ML packages or touch Kaggle:

```powershell
powershell -File tools\bootstrap_environment.ps1 -Create
```

Do not choose an accelerator-specific PyTorch build until the upgraded GPU and
driver are known. Record that choice in the eventual dependency lock.

## 6. Materialize pinned public sources only when wanted

The source lock fixes the patched organizer scorer and `tracksdata` revisions:

```text
royerlab/kaggle-cell-tracking-competition  075fc5f5a52d11077f9dc2b074644618f26939e2
royerlab/tracksdata                        63a1912f3b6ebd1536a2e8a8adfdf7f5eb84efa4
```

After deciding to allow public GitHub network access:

```powershell
py tools/fetch_pinned_sources.py --fetch
```

This populates the ignored source cache and verifies the exact revisions; it
does not contact Kaggle. Never use a floating branch in a recorded experiment.

The organizer baseline currently references a floating `tracksdata@main`.
Never let a normal dependency install resolve that reference. For the future
environment, install the source-locked `tracksdata` checkout first, install the
source-locked organizer baseline with dependency resolution disabled
(`--no-deps`), and install every remaining dependency only from a reviewed lock.
The exact install command belongs in that hardware-specific lock once the GPU is
known.

## 7. Begin with the play lane after data is authorized

Choose one training sample only after data access is separately authorized.
The first useful loop is intentionally understandable:

1. stream a small contiguous time window from Zarr;
2. inspect intensity and physical voxel-scale metadata;
3. visualize image planes and sparse GEFF annotations;
4. detect candidate cells with a local-maximum or Difference-of-Gaussians
   baseline;
5. link candidates between adjacent frames with a physically gated assignment;
6. keep cell divisions disabled for the first smoke result;
7. validate the graph and preserve qualitative overlays plus a receipt.

This is a learning result, not the official baseline.

## 8. Advance to the benchmark lane

Reproduce the organizer's pinned Temporal 3D U-Net and cross-attention linker
before altering it. Build embryo-disjoint splits from a name-only data manifest.
The tool deliberately writes only the named file, so create its external parent
directory explicitly:

```powershell
$manifestRoot = "D:\HearthlineData\biohub-cell-tracking\manifests"
New-Item -ItemType Directory -Force -LiteralPath $manifestRoot | Out-Null
py tools/make_embryo_splits.py --samples-file "$manifestRoot\train-samples.txt" --output "$manifestRoot\embryo-folds.json"
```

The output is a deterministic list of leave-one-embryo-out folds using canonical
sample basenames without `.zarr`. Review and hash it before use. Run the official
patched scorer locally and preserve edge/division components, not just the
aggregate. Follow `docs/EXPERIMENT_PROTOCOL.md` for the required controls and
receipts.

## 9. Treat submission as a later, separate gate

The competition currently requires notebook submissions with internet disabled,
a CPU or GPU runtime no longer than 12 hours, and a file named
`submission.csv`. Before any authorized upload, validate its structure locally:

```powershell
py tools/validate_submission.py "D:\HearthlineData\biohub-cell-tracking\runs\RUN_ID\submission.csv" --expected-datasets "D:\HearthlineData\biohub-cell-tracking\manifests\test-datasets.txt"
```

Validation does not authorize submission or prove acceptance by Kaggle. This
guide intentionally contains no data-download or submission command.
