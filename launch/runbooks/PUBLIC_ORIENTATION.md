# Public ARC-AGI-3 orientation archive

**Disposition:** `CLOSED_EXPIRED_AND_SPENT`

The 2026-09-03 grant authorized five bounded anonymous public ls20 runs. Those runs are complete and reconciled in `launch/receipts/20260904T070000Z-orientation-reconciliation.v2.json`. This document no longer contains an executable contact recipe.

## Offline inspection only

The following operations do not contact an environment:

```bash
python -I -B tools/repository_guard.py
python -I -B tools/validate_launchpad.py
python -I -B -m unittest discover -s tests -p 'test_reconciliation.py' -v
python -I -B launch/tools/orientation_console.py --explain
python -I -B launch/tools/frame_probe.py local-frame.json
```

`launch/tools/orientation_console.py` retains pure fixture-policy helpers but is retired as a runner. `.github/workflows/arc3-orientation-probe.yml` has no push trigger or replay step. The effect-capable `tools/arc3_replay_probe.py` was removed from the active tree; Git history preserves its source. `tools/orientation_archive_guard.py` rejects each old request before any adapter could be called.

## Reopening requirements

A future public orientation must be designed as a new successor, not a reuse of `ORIENT-0001` through `ORIENT-0005`. Before any contact, a human must bind a fresh grant to:

- the exact candidate commit and tree;
- a content-addressed request and predecessor world model;
- the exact public game/version aperture;
- action, reset, wall-time, and contact ceilings;
- current official source identities and terms;
- an explicit no-retry rule for uncertain dispatch; and
- a reviewed receipt/admission path.

No old `status: AUTHORIZED` field, founder text, green check, local token, or heartbeat renews that authority. Kaggle staging and competition ignition are separate gates and are never implied by public-practice authority.

## Sanitized publication boundary

Commit only field-limited derivatives. Keep raw grids, images, headers, tokens, cookies, scorecard/service identifiers, and GUIDs outside Git. Preserve archive/source-receipt hashes so a reviewer with authorized access can reopen the source without rewriting admitted history.
