# ARC-AGI Playground

**Series anchor:** `arc-agi/main`  
[Return to the Hearthline Plays front door](https://github.com/Grativy6/hearthline-plays)

This is the public development and play branch for ARC-AGI games and environments. ARC-AGI-3 can be built here as its own title branch before any separately authorized move to a competition or Kaggle environment.

## Branchline

| Branch | Role |
| --- | --- |
| `arc-agi/main` | Public series anchor, shared rules, and common scaffold |
| `arc-agi/titles/<slug>` | One title, environment, or bounded experiment created from an exact anchor commit |

Create each title branch from `arc-agi/main`. Keep implementation, run data, and title-specific notes on the title branch rather than at the repository front door.

A title branch README should record:

- its parent anchor commit;
- the official public source, rules, and environment version it inherits;
- its permitted inputs and excluded inputs;
- how to run it locally;
- its declared evaluator or scoring rule, if any;
- what state or evidence is carried forward.

## Public-play boundary

- Use public, authorized, source-pinned material.
- Keep credentials, secrets, private or sealed holdouts, and non-redistributable challenge data out of the repository.
- Keep runs reproducible enough to identify the code, configuration, and public inputs used.
- A trace, observation, score payload, or return bundle is data brought forward. It becomes a result only when a declared evaluation rule assigns that status.
- This series anchor does not upload submissions or claim external validation, endorsement, or competition standing.

## Current state

This is the series scaffold only. No ARC title or game implementation has been installed yet.

ARC-AGI and related names, rules, datasets, and trademarks remain with their respective owners. This repository is an independent playground and is not affiliated with or endorsed by ARC Prize.

## License

Except where a file says otherwise, original material on this branch is licensed under the [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/). Third-party material retains its own terms.
