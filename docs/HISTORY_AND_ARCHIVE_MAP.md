# History and archive map

Status: `PRESERVATION_MAP_ONLY`

Compression in this repository means a smaller active reading surface, not
deleted source material. No move, deletion, deduplication, branch disposition,
or redirect is proposed here.

## Branch relationships

- ARC-AGI-2 title `259064e582b3f2ca5107aeddb408e96d49fb1f4c`
  remains trace-bearing even though its tree equals current `arc-agi/main`.
- ARC-AGI-3 launch `97f580504e22bbd59b425274d6b5e0f9a18fe66e`
  and research station `e2b2eec1544caeb8a1a07825d56db1d932c9e3f6`
  are divergent siblings from merge base
  `d4716557587302910b0002757b8e9e65c90b9fd7`, with one unique commit each.
- The launch-only tree delta adds the Astra embargo JSON and Markdown receipts
  and updates the receipt index. It does not replace ARC machinery.
- Merge `bb6327e1f5f96da929c4068d6b95fa94d4f73600`, tree
  `7ff81534a7bc093224b29a5916b69d618e1cd27c`, is the preserved PR #4
  predecessor that joined the launch and hardened-station histories.
- Homecoming merge `a3f99acedd1fa91417510f66eba35c444533f335`, tree
  `c7eac0a173c1b50ac62447785734f96a986bf4fb`, was merged through PR #6. It
  descends from `bb6327e…` and first adds the offline return-queue reference
  without changing the executable candidate, source lock, human-gate state, or
  activity classification.
- The canonical ARC-AGI-3 title now points to Morrow merge
  `25e154d539b1c85e28c5334b9b940ab6880ca600`, tree
  `d249cec7b81d942b84a6f728a421e3cd18ddaf31`, merged through PR #8. Its first
  parent is
  `a3f99acedd1fa91417510f66eba35c444533f335`, tree
  `c7eac0a173c1b50ac62447785734f96a986bf4fb`; its second parent is reviewed
  source head `2f22c90bf2de57e5cb6b2d21b05c4b5c5cdc964b`. The source head and merge
  commit share the exact current tree. This successor adds dispatch priority,
  retry rotation, strict schemas, examples, verification, a stateless Morrow
  sorter, and their story. It strictly separates Morrow's fresh scheduling
  projection from Thulia's durable chronicle and still changes no executable
  candidate, source lock, human-gate state, or activity classification.
- Millennium `3449bd282309aa291a98d1e08819232b1849832e` is an
  append-only successor from `ef18554b2ca828b270dfb78512550b9b401ab6e4`, not
  a current ARC launch.
- Creature `8d859bf124cdda27c1caa0c6dc44cf7b9c4b719e` is one
  commit after Millennium and changes only
  `design/CHARTER_CREATURE_FIELD_GUIDE.md`, `design/CREATURES.md`, and
  `research/INSPIRATION_MAP.md`.

## Inherited text

Millennium and Creature inherit ARC authorization and network-capable wording
from their ancestry. That inherited wording is
`HISTORICAL_INHERITED_NOT_CURRENT_NOT_EXECUTABLE`. The label applies to the
inherited ARC surface; it does not deny each branch's own current bounded
purpose. Rewrite neither genesis nor its receipts to modernize the wording.

## Path-bound material

Source locks, receipts, predecessor/current status files, dialect versions, and
equal-but-semantically-distinct fixtures stay at their exact title-owned paths.
Their validators may bind file names, digests, counts, or relative locations.
An index pointer cannot replace those bytes.

## Current activity classes

| Surface | Classification |
|---|---|
| `main` | Front-door index |
| ARC-AGI-2 title / ARC anchor | `MERGED_REDUNDANT_TOPOLOGY_PRESERVED` |
| ARC-AGI-3 launch | `ACTIVE_CANDIDATE` |
| ARC-AGI-3 research station | `HISTORICAL_PROVENANCE` / divergent sibling |
| Millennium | `PLAY_NOT_PROOF` |
| Creature | `NARRATIVE_DESIGN_GUIDE`; `PROPOSED_NOT_IMPLEMENTED` |
| Biohub and formal Rosetta | `PREPARED_NOT_RUN` |
| Rosetta calibration | `BLOCKED_EXTERNAL_HOSTED_PARQUET_ENGINE_MISSING` |
| Kaggriculture Build 001 | Closed local pinned-interpreter result, not official Kaggle |

Use the [playground index](PLAYGROUND_INDEX.md) and [scientific run
entry](SCIENTIFIC_RUN_ENTRY.md) as current reading aids. The
[machine-readable snapshot](../manifests/branch-status.v1.json) is a dated
pre-merge inventory and remains unchanged as provenance. Reopen historical
questions from the exact branch commit, not from a prose summary.
