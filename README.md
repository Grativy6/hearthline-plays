# ARC-AGI-3 Research Station

**Status:** `PREPARED_NOT_RUN`

**Series anchor:** [`arc-agi/main`](https://github.com/Grativy6/hearthline-plays/tree/arc-agi/main)

**Exact parent anchor commit:** `228d80f0559277c55031f4a80f6179320e10364c`

**Exact parent anchor tree:** `532e178ecd41410e5e9038c647141f2cbe32f01d`

This title branch is a public research station for organizing source context,
tool inspiration, provenance, and an auditable Creature design before any
separately authorized ARC-AGI-3 or Kaggle attempt. It contains no game
implementation, gameplay state, private holdout, credentials, submission
payload, score, or claim that a run has begun.

## Current boundary

| Surface | State |
| --- | --- |
| Kaggle contacted | `false` |
| ARC environment contacted | `false` |
| Private or sealed holdout accessed | `false` |
| Submission attempted | `false` |
| Environment calls | `0` |
| Holdout consumption | `0` |
| Current official ARC framework | `UNBOUND` |
| Current official package and game | `UNBOUND` |
| Current official evaluator | `UNBOUND` |
| Operator and scribe models | `UNBOUND` |
| Run budgets | `UNBOUND` |

`UNBOUND` is deliberate. Historical package versions or earlier public-game
calibrations do not silently become the environment for a future attempt. A
later run needs a new authorization, a fresh official-surface review, an exact
freeze, and a preregistration bound to that freeze.

## Station map

- [`research/sources.lock.json`](research/sources.lock.json) — strict,
  machine-readable source and artifact identities.
- [`research/INSPIRATION_MAP.md`](research/INSPIRATION_MAP.md) — bounded
  relationships between published research and proposed tools.
- [`research/STRONGWIZ_V3_INSPECTION.md`](research/STRONGWIZ_V3_INSPECTION.md) —
  pinned Strongwiz v3 findings, verified surfaces, and residuals.
- [`design/CREATURES.md`](design/CREATURES.md) — the proposed composite of
  separately bounded Sparks, ledgers, Homes, and controller-admitted,
  broker/domain-written effects.
- [`prep/ARC_AGI_3_NO_RUN_PREFLIGHT.md`](prep/ARC_AGI_3_NO_RUN_PREFLIGHT.md) —
  the stop boundary for this preparation pass and the gates a later run would
  have to satisfy.
- [`schemas/research-source.v1.schema.json`](schemas/research-source.v1.schema.json),
  [`schemas/creature-manifest.v1.schema.json`](schemas/creature-manifest.v1.schema.json),
  and [`schemas/objective-window.v1.schema.json`](schemas/objective-window.v1.schema.json)
  — closed schema surfaces.
- [`fixtures/creature-manifest.synthetic.json`](fixtures/creature-manifest.synthetic.json)
  and [`fixtures/objective-window.synthetic.json`](fixtures/objective-window.synthetic.json)
  — fabricated structure and receipt order only, with no operational or
  challenge data.
- [`tools/verify_station.py`](tools/verify_station.py) and
  [`tests/test_verify_station.py`](tests/test_verify_station.py) —
  standard-library-only offline validation.

## Research and provenance rule

The station records PAL v2.3, BRRRT v2.0, the Single Cut Transport Lemma
v0.2, Compactification Costs v0.2, and the pinned Strongwiz v3 prototype.
Source bytes are not copied into this repository. Public locators and exact
artifact identities are recorded instead.

Five additional public corpus works are listed as optional, unlocked design
context in the inspiration map. They are not run inputs and would require a
source-lock successor before later use.

These works share one author-led lineage. Their agreement is not independent
corroboration. A citation is not code import, execution, adoption, proof,
authorization, or evidence that a mechanism improved ARC performance.

## Creature rule

A Creature is a manifest-bound composition of separate Hearthline Sparks. It
is not a fourth Spark role, a person, a source of authority, or a merged mind.
Each Spark retains its own identity, grant, budget, ledger, Static, and Home.
Thulia may keep a partitioned Perch index and prepare source-bound Bridge
Glosses, but she does not govern the Creature, merge ledgers, approve carry,
select actions, or receive an authority or action port.

Authenticated external operator control alone grants or revokes permission.
The canonical controller admits and serializes proposals but does not execute
external effects. A separately authorized broker/domain writer executes and
records an admitted effect. Parallel proposals never create parallel writers,
and an ambiguous effect stops for reconciliation instead of being retried from
uncertainty.

A frozen terminal-authority source establishes the terminal observation. The
adapter may validate and project that observation; it cannot manufacture or
upgrade terminal status.

## Heartbeat rule

A heartbeat is a bounded status and receipt surface. It can report fresh
liveness evidence or a material boundary, and an unchanged work projection can
still have audit motion. A heartbeat is not task progress, permission,
authority, or evidence of completion. It cannot keep a Codex workspace alive,
renew a task, or guarantee a handoff.

## Open objective window

A controller/product-owned objective window may accept a new objective while
another Spark or Creature is honestly suspended. Every objective keeps a
separate ID, Spark-or-Creature binding, scope, grant, budget, ledger, heartbeat
contract, and Homecoming custody state. Objective disposition and Homecoming
custody remain separate coordinates; reconciliation cannot manufacture a task
or result status. Completion order may differ from intake order, but one
aggregate response closes only after the explicitly named objective set has an
explicit qualified disposition. Rule-established results remain in their
evaluator's namespace; handoffs such as `OBJECTIVE:BLOCKED` or
`OBJECTIVE:LEFT_OPEN` do not become completion. A heartbeat is an
interrupt/checkpoint receipt within that protocol; it is neither the scheduler
nor a keepalive.

## Millennium Playground successor

The [`millennium/`](millennium/) subtree is an append-only successor to this
branch's pre-Astra lineage anchor. It opens three bounded research games:
Riemann Hypothesis, P versus NP, and a geometry track that keeps the solved
Poincare conjecture control separate from the open Hodge conjecture frontier.

Its genesis receipt seals provenance, source identities, and claim ceilings.
It does not claim a Millennium problem solution.

## License

Except where a file says otherwise, original material on this branch is
licensed under the [Creative Commons Attribution 4.0 International
License](https://creativecommons.org/licenses/by/4.0/). Referenced works and
software retain their own exact licenses and identities.
