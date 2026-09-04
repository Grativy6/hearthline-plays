# ARC-AGI-3 replay probe — removed

The executable `tools/arc3_replay_probe.py` was deleted from the active tree.
It could still interpret the five legacy `status: AUTHORIZED` request records
after their controlling grant had expired and been spent. Removing workflow
triggers was insufficient because a human could invoke the script directly.

The old source remains available in Git history for provenance. Current code
contains only [`orientation_archive_guard.py`](orientation_archive_guard.py),
which has no effect adapter and unconditionally rejects `ORIENT-0001` through
`ORIENT-0005` before contact. A future orientation requires a new request,
fresh grant, new runner review, and an independently bounded effect path.
