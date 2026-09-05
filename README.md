# Hearthline Plays

A public playground for building, running, and playing games with AI models.

This repository is organized by branch so one growing playground does not become one crowded root. `main` is the front door and shared map. Each game series has a stable anchor branch; individual titles, worlds, and bounded experiments branch from that anchor.

## Start here

`main` is an index, not a runnable title and not a grant of external authority.

- [Playground index](docs/PLAYGROUND_INDEX.md) — every current public branch,
  exact tip, role, and honest status.
- [Scientific Run Entry v1.0](docs/SCIENTIFIC_RUN_ENTRY.md) — the required,
  versioned honesty preflight for scientific, evaluation, benchmark, and ARC
  routes.
- [ARC-AGI-3 sendoff route](docs/ARC3_SENDOFF.md) — the exact current
  candidate, evidence, blocker, closed gates, and human-only reopening sequence.
- [History and archive map](docs/HISTORY_AND_ARCHIVE_MAP.md) — retained,
  merged, divergent, sealed, and inherited surfaces without flattening them.
- [Machine-readable branch snapshot](manifests/branch-status.v1.json) — the
  dated source for exact branch tips and index classifications.

The current ARC-AGI-3 review candidate is
`arc-agi/titles/arc-agi-3-hearthline-launch-20260903` at
`97f580504e22bbd59b425274d6b5e0f9a18fe66e`. Its exact remote verification is
green, but its operational status remains
`OFFLINE_CANDIDATE_SOURCE_READY_HUMAN_GATES_CLOSED` and its terminal blocker
remains `RUNTIME_CLOSURE_UNFROZEN`. Verification is not permission or a score.

A [2026-09-05 review successor](https://github.com/Grativy6/hearthline-plays/pull/4)
reconciles that launch tip with the hardened research-station sibling, adds the
published [CHARTER v1.0](https://doi.org/10.5281/zenodo.22288471) anchor and a
copy-ready sendoff, and leaves the executable candidate bytes unchanged. It is
review-only until adopted; it does not open either human gate or resolve the
private-runtime blocker.

## Shared game embodiment blueprint

[`Hearthline Game Embodiment Blueprint v0.1`](docs/HEARTHLINE_GAME_EMBODIMENT_BLUEPRINT_v0.1.md) defines the title-neutral controller–heartbeat architecture for persistent AI play: the environment is the world and referee, the controller is the body, the heartbeat is the sensory return, and Hearthline is the player.

Title branches may adopt an exact blueprint version and supply their own game adapter, controller profile, observer, heartbeat schema, persistent trace, intervention ledger, run manifest, and provenance record. The shared blueprint does not place executable game code on `main` or silently alter an existing title branch.

## Front of the playground: Finis Solutus

**Finis Solutus** is the current front-of-house project: an open-ended fantasy world built from persistent rules rather than a predetermined plot.

- Series anchor: [`finis-solutus/main`](https://github.com/Grativy6/hearthline-plays/tree/finis-solutus/main)
- Persistent world branches: `finis-solutus/worlds/<slug>`

## Deeper branch: ARC-AGI

ARC work has its own series branch so public ARC-AGI development can grow without taking over the repository entrance.

- Series anchor: [`arc-agi/main`](https://github.com/Grativy6/hearthline-plays/tree/arc-agi/main)
- Title or environment branches: `arc-agi/titles/<slug>`

## Branch map

| Branch pattern | Role |
| --- | --- |
| `main` | Shared front door, branch map, cross-title blueprints, and license |
| `finis-solutus/main` | Finis Solutus series anchor and common scaffold |
| `finis-solutus/worlds/<slug>` | One persistent Finis Solutus world |
| `arc-agi/main` | ARC-AGI series anchor and public-development boundary |
| `arc-agi/titles/<slug>` | One ARC title, environment, or bounded experiment |
| `<series>/main` | Future series anchor |
| `<series>/titles/<slug>` | Future title branch created from its series anchor |

The `<series>/main` form is deliberate: Git cannot keep both a branch named `<series>` and descendants named `<series>/...`. Giving every series an explicit `/main` anchor leaves room for its children.

## Branchline rules

1. Create each title or world from the exact commit of its series anchor.
2. Record that parent commit and any inherited kernel, ruleset, or environment version in the child branch README.
3. Keep ongoing state and its ancestry explicit. A migration or major upgrade creates a child branch; it does not silently rewrite an existing world or run.
4. Keep credentials, secrets, private holdouts, and material that cannot be redistributed out of the repository.
5. Treat third-party rules, names, datasets, assets, APIs, and trademarks according to their own terms.

There is intentionally no game implementation on `main`. Playable material belongs in the branch that owns its lineage.

## License

Except where a file says otherwise, original material in this repository is licensed under the [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).

Third-party material is not relicensed by its presence here.

Suggested attribution: **Hearthline Plays — Christopher D. Pang — CC BY 4.0 — https://github.com/Grativy6/hearthline-plays**
