# ARC launch contract deprecations

## Canonical successor

New work uses the explicit namespace `hearthline.arc3.*.v2`:

- schemas: `launch/schemas/v2/`;
- blank records: `launch/templates/v2/`;
- Pair compiler: `launch/tools/static_pair_v2.py`; and
- one-way v1 converter: `launch/tools/migrate_static_v1.py`.

The v2 Spark vocabulary is fixed: `role_id`, `observation_refs`, `dependencies`, claims with `epistemic_status` / `proposition` / `value`, a non-authorizing `recommendation`, and a migration receipt. Pair estimates remain separate in `conditional_estimates`; `pooling_rule` is top-level and always `NONE`.

## Legacy collision

Two incompatible dialects were published with the same v1 schema names:

| Dialect | Schema/tool paths | Distinguishing fields | Status |
| --- | --- | --- | --- |
| root-v1 | `schemas/*-static.v1.schema.json`, `tools/pair_static.py` | `kind`, `value`, `dependencies`, `proposed_tests` | Historical read-only input |
| launch-v1 | `launch/schemas/*-static.v1.schema.json`, `launch/tools/static_pair.py` | `status`, `text`, `candidate_world_model`, `proposed_action` | Historical read-only input |

Do not infer a dialect from the string `hearthline.spark-static.v1` alone and do not pass one v1 dialect to the other compiler. The converter detects the structural dialect, binds the source SHA-256, and produces a one-way successor; it never rewrites the source. Migrating representation does not promote a claim or authorize an effect.

`launch/tools/orientation_console.py` is also retired as an executor. Only its pure deterministic fixture-policy helpers remain. The old public replay broker `tools/arc3_replay_probe.py` was deleted from the active tree, not merely disconnected from workflows. Its bytes remain in Git history. The current `tools/orientation_archive_guard.py` has no effect adapter and rejects all five archived request identities before contact.
