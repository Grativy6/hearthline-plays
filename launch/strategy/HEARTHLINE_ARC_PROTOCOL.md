# Hearthline ARC protocol

**Version:** `0.1-prepractice`  
**Status:** `PROPOSED_AND_LOCALLY_CHECKABLE`  
**Author and steward:** Christopher D. Pang  
**AI role:** implementation and drafting tool under the steward's direction

This protocol translates the existing Hearthline cast into a bounded ARC practice loop. It is deliberately smaller than the full corpus: keep what changes the next action, preserve handles back to evidence, and stop rather than filling an unknown with a confident story.

## 1. Core loop

```text
observe
  -> extract direct frame facts
  -> update compact world model
  -> run two declared Spark lenses on the same task
  -> create one Pair Static preserving agreement and disagreement
  -> choose one discriminating or goal-directed action
  -> act once
  -> compare predicted and observed consequence
  -> append receipt
  -> revise, stop, or continue
```

Only one action crosses to the environment at a time. Internal plurality may generate alternatives; it does not generate parallel effect authority.

## 2. Five records that must not collapse

### 2.1 Observation

Directly returned data only:

- game and session identity as supplied by the official surface;
- current terminal state, levels completed, win levels, score, and available actions;
- current frame dimensions and palette;
- changed-cell mask and component movement relative to the previous frame; and
- exact action whose consequence is being observed.

An image interpretation is not direct observation merely because it is visually compelling.

### 2.2 Compact world model

A minimal symbolic account of the state needed to predict consequences:

```yaml
level: L?
entities:
  player: {shape: ?, position: ?, orientation: ?}
  target: {shape: ?, position: ?, state: ?}
variables:
  door_1: unknown
  hub_orientation: unknown
relations:
  - player left-of target
constraints:
  - walls block directional movement
source_events: [event-0001, event-0002]
residuals:
  - whether blue cells are obstacle or goal remains unresolved
```

The world model is not a transcript and not a complete ontology. Omit details that have no demonstrated bearing on action choice, but keep a source handle for every promoted state fact.

### 2.3 Action algebra

Stable local names for controls and effects:

```yaml
operators:
  ACTION1:
    candidate_meaning: move_up
    observed_effect: player delta (0,-1) on events 3 and 8
    exceptions: [event-11 blocked]
  ACTION5:
    candidate_meaning: interact
    observed_effect: unknown
```

An operator meaning is earned by repeated or uniquely discriminating consequences. A platform label such as `Move Up` is interface metadata; the game may still transform or reinterpret its effect.

### 2.4 Hypothesis set

Each hypothesis is conditional and falsifiable:

```yaml
hypothesis_id: H-004
claim: yellow region is the level goal
confidence: 0.62
support: [event-0021]
conflicts: []
shared_dependencies: [segmentation-v1]
prediction:
  action: ACTION4
  expected_change: player moves one cell toward yellow
falsifier: repeated contact with yellow produces no terminal or score change
next_discriminating_action: ACTION4
```

Confidence is an estimate inside a declared account, not authority. Two same-model Sparks are dependent evidence even when their reasoning routes differ.

### 2.5 Plan

An ordered proposal, separately versioned from the world model:

```yaml
plan_id: P-003
objective: reach the nearest hypothesized goal
based_on_world_model: WM-006
steps: [ACTION4, ACTION4, ACTION1, ACTION5]
abort_when:
  - observed displacement conflicts with predicted operator
  - terminal state changes
  - a cheaper discriminating action becomes available
```

A plan does not become true merely because the state model is accurate. Every observed mismatch reopens the remaining suffix.

## 3. Paired Sparks

Two Sparks receive the same bounded question and the same committed observation projection.

### Spark A — geometry and identity

Default lens:

- segment colors and connected components;
- track persistent shapes across frame changes;
- infer position, adjacency, symmetry, enclosure, path, and reachability;
- distinguish background, boundary, actor, control, target, and transient effect; and
- propose the action whose geometric consequence would separate its leading models.

### Spark B — causal and operational

Default lens:

- map action to observed delta;
- distinguish controllable state from animation and environment response;
- detect counters, modes, toggles, inventory, irreversible changes, and delayed effects;
- compare expected and actual consequences; and
- propose the cheapest action that separates its leading causal accounts.

The lens assignments may change, but the difference must be declared before the pair runs. Giving two Sparks different prose prompts after seeing the answer is not a preregistered comparison.

## 4. Static records

Each Spark writes its own immutable Static for one task version. Static is compact, source-linked shorthand, not hidden reasoning and not a substitute for the full event trail.

Minimum fields:

```yaml
schema: hearthline.spark-static.v1
task_id: task-...
spark_id: spark-...
lens: geometry | causal | other
observation_refs: [...]
claims:
  - id: C-...
    status: OBSERVED | INFERRED | ESTIMATED | UNRESOLVED
    text: ...
    evidence_refs: [...]
    confidence: null
candidate_world_model: {...}
proposed_action: {...}
predicted_consequence: {...}
residuals: [...]
```

A successor Static cites the previous Static and appends the material delta. It does not rewrite the source record.

## 5. Pair Scribe and Pair Static

The Pair Scribe compares Static A and Static B. It does **not** solve the original game state a third time. If it begins producing an independent substantive model, it has become another Spark and needs its own Static.

The Pair Scribe creates a third record:

```yaml
schema: hearthline.pair-static.v1
pair_id: pair-...
task_id: task-...
source_statics: [static-a, static-b]
agreement:
  claims: [...]
  shared_dependencies: [...]
disagreement:
  claims: [...]
  cause_candidates: [...]
estimates:
  spark_a: {...}
  spark_b: {...}
  pooling_rule: NONE
recommended_discriminating_action: {...}
expected_information_gain: qualitative-low | qualitative-medium | qualitative-high
unresolved: [...]
```

### No automatic averaging

Two numbers are normally two conditional estimates, not two independent samples. Preserve `(estimate A under account A, estimate B under account B)` unless a frozen pooling rule and dependence account justify combination. Agreement can reflect a shared model, shared prompt, shared segmentation error, or copied premise.

### Comparison classes

- `AGREEMENT_WITH_SHARED_SUPPORT`
- `AGREEMENT_WITH_DEPENDENT_SUPPORT`
- `COMPATIBLE_DIFFERENT_RESOLUTIONS`
- `CONFLICTING_CONDITIONAL_ESTIMATES`
- `CONFLICTING_WORLD_MODELS`
- `SAME_ACTION_DIFFERENT_REASONS`
- `INSUFFICIENT_FOR_COMPARISON`

The disagreement itself may be the useful output.

## 6. Thulia custody

Thulia keeps a partitioned index and prepares the smallest Hearthline-facing ledger needed for the next decision:

```yaml
pair_id: pair-...
current_task: ...
source_static_refs: [...]
pair_static_ref: ...
shared_result: ...
load_bearing_disagreement: ...
next_proposed_action: ...
expected_result: ...
stop_or_reopen_condition: ...
```

Thulia does not merge source ledgers, choose the environment action, manufacture confidence, approve her own summary, or erase a branch because a shorter record is convenient.

## 7. One action writer

Hearthline chooses one action from:

1. a low-cost discriminating probe;
2. a step in the current goal-directed plan whose premises still hold;
3. an undo when the interface supplies one and the reason is explicit;
4. a reset only under the run's reset policy; or
5. stop.

No Spark, Pair Scribe, or Thulia record directly calls the environment. The controller validates the official action set and the run budget immediately before effect.

## 8. Prediction receipt

Before action, record:

```yaml
prediction_id: pred-...
action: ACTION...
world_model_ref: WM-...
expected_change_region: ...
expected_state_change: ...
expected_score_direction: increase | same | decrease | unknown
confidence: ...
falsifier: ...
```

After action, append:

```yaml
outcome_id: outcome-...
official_state: ...
changed_cells: ...
changed_bbox: ...
score_delta: ...
prediction_class: MATCH | PARTIAL | MISMATCH | UNREADABLE
model_delta: ...
```

The outcome never overwrites the prediction. Keeping both is what makes calibration possible.

## 9. Atomic promotion

Before a run, decide which event fields may be promoted into compact state. A default proposal:

| Candidate | Promote when | Do not promote from |
|---|---|---|
| action meaning | same directional/effect signature twice, or one uniquely identifying transition | interface label alone |
| entity identity | component correspondence survives a declared matching rule across frames | color equality alone |
| goal identity | score/level/terminal evidence or repeated goal-consistent response | visual salience alone |
| obstacle | attempted motion is blocked while neighboring controls work | one no-change event without timing check |
| irreversible switch | change persists across later observations and undo semantics are checked | one animated frame |
| plan step | all premises are present and action remains available | stale world model |

Promotion is all-or-nothing for the named field. If evidence is mixed, keep the candidate in hypotheses rather than half-installing it as state.

## 10. Four-stage practice cadence

### Stage 1 — Calibration

- enumerate current actions;
- execute each safe non-reset action at most once before repeating, unless terminal safety requires otherwise;
- measure frame deltas and state/score changes;
- identify likely controllable component and gross action semantics;
- return after at most 12 actions.

### Stage 2 — Investigation

- instantiate Geometry and Causal Sparks on the same current task;
- form one Pair Static;
- choose the cheapest action that distinguishes their strongest disagreement;
- use at most 24 actions total for this stage.

### Stage 3 — Pressure

- select the best predictive world model;
- commit a short plan;
- test it across longer sequences and changed local contexts;
- actively search for the assumption most likely to break;
- use at most 48 actions total for this stage.

### Stage 4 — Goal attempt

- name one level or mechanism objective;
- freeze the world-model and plan versions used to begin;
- pursue it while checking predictions after every effect;
- use at most 96 actions total for this stage.

Budgets are ceilings, not targets. A terminal result, repeated zero-information loop, invalid interface, or material authorization change stops early.

## 11. Looking backward while moving forward

The founding prompt asks about turning around while still moving forward. Operationally, this becomes a two-view update:

- **forward view:** what action is expected to move toward the current objective;
- **backward view:** which earlier observation, action, or assumption explains the present state, and whether the current model could reconstruct the path that produced it.

A model that predicts the next frame but cannot account for the last transition may be exploiting a shallow correlation. A backward check is therefore run at checkpoints, not after every cell:

```text
Can the current world model explain the most recent material transition?
Can it distinguish two histories that lead to the same visible state when that history changes the next legal action?
```

Path history is retained only when it changes future predictions, permissions, inventory, counters, or reversibility.

## 12. Stop rules

Stop and return a receipt when:

- the official terminal state is `WIN` or `GAME_OVER`;
- the action, reset, wall-time, call, or cost ceiling is reached;
- environment contact or closure fails;
- available actions contradict the assumed interface;
- three consecutive actions produce no material observation and no preregistered reason predicts delayed response;
- the same state/action pair repeats without new information;
- a required credential, paid provider, private artifact, Kaggle action, or competition crossing appears;
- outcome is uncertain after a potentially irreversible dispatch; or
- the user interrupts.

A heartbeat reports only liveness or material change. With no authorized next action, append the heartbeat and suspend.

## 13. What this protocol does not claim

It does not claim to reproduce GPT-6 Astra's opaque provider state, ARC Prize's provider adapter, human efficiency, a winning ARC system, independent multi-model evidence, or a statistically validated Creature benefit. Public descriptions of compact symbolic world models motivate the external shape only. Any performance claim requires a frozen implementation, matched controls, exact costs, official terminal authority, and retained receipts.
