# Finis Solutus

**Series anchor:** `finis-solutus/main`  
[Return to the Hearthline Plays front door](https://github.com/Grativy6/hearthline-plays)

Finis Solutus is an open-ended fantasy world-system built from persistent rules rather than a predetermined plot. This branch is its stable public series parent: shared kernels, scaffolds, and series-wide material can live here before any one world begins.

## Branchline

| Branch | Role |
| --- | --- |
| `finis-solutus/main` | Current series anchor |
| `finis-solutus/worlds/<slug>` | One persistent world created from an exact anchor commit |

Create every world branch from `finis-solutus/main`. Do not create active world state on the anchor.

A world branch README should record:

- its parent anchor commit;
- the inherited Finis Solutus kernel or ruleset version;
- the world name and stable branch identity;
- where its persistent state is kept;
- any migration ancestry, conflicts, or transformations.

Chats are sessions. The persistent state carried by the world branch is the continuing record.

## Upgrades and migrations

A kernel upgrade must not silently rewrite an ongoing world. Preserve the original branch and create an explicit child branch for the migration. Record what was inherited, what changed, and what could not be carried forward cleanly.

That makes each world recoverable without forcing every world to move at once.

## Current state

This is the series scaffold only. No persistent world has been installed yet.

## License

Except where a file says otherwise, original material on this branch is licensed under the [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/). Third-party material retains its own terms.
