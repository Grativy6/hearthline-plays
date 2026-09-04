# Hearthline Game Embodiment Blueprint v0.1

**A general controller–heartbeat architecture for persistent AI play**

| Field | Value |
| --- | --- |
| Author and steward | Christopher D. Pang |
| Version | 0.1 |
| Date | 4 September 2026 |
| Status | Public working blueprint; proposed implementation synthesis; no live-game result claimed |
| Repository | `Grativy6/hearthline-plays` |
| License | CC BY 4.0, except third-party material retained under its own terms |

Christopher D. Pang supplied the concept, governing distinctions, objective, and adoption authority for this blueprint. GPT-5.6 Sol assisted under his direction with synthesis, drafting, repository preparation, and boundary review. AI systems are tools in the work, not authors, co-authors, owners, stewards, witnesses, or independent authorities.

> **The environment is the world and referee. The controller is the body. The heartbeat is the sensory return. Hearthline is the player.**

Here, *player* names a bounded system role. It does not establish personhood, consciousness, subjective experience, standing, or independent authority.

## 1. Purpose

This blueprint describes a reusable way for Hearthline to play games whose action rate, duration, or possibility space is too large for one language-model turn per button press.

The design applies across turn-based puzzles, simulations, farming games, roleplaying worlds, strategy games, and real-time games. A title may supply clean structured state, pixels and sound only, or a mixture of both. The architecture does not assume that the game can be exhaustively mapped before play begins.

The core move is hierarchical:

```text
choose a bounded intention
        ↓
execute a calibrated skill
        ↓
return on completion, surprise, blocker, danger, or deadline
        ↓
update the persistent trace
        ↓
choose again
```

The model reasons at branch points. A local controller handles the high-frequency mechanics needed to carry an already chosen intention through the game.

## 2. Source roles and authority

This document is an implementation synthesis beside the Hearthline and PAL lineages. It is not a PAL spine revision and does not silently amend any source named below.

| Source | Role carried here | Authority ceiling |
| --- | --- | --- |
| **PAL v2.3** | Earned distinctions, trace conservation, authority ceilings, residuals, local closure, reopening, and no authority backflow | Does not supply game strategy, experience, permission, or a controller implementation |
| **Finis Solutus v0.16** | World/player precedent: finite rules, persistent consequences, open possibility; the world maintains coherence without authoring the player's destiny | Does not become the rules of an external game |
| **The Context Is the Model** | The supplied finite context and its provenance are the object actually available for audit | Does not prove that the supplied context is complete or adequate to the world |
| **The Context Draws a Map v1.0** | The observer and retained context make some continuations easier to see than others | Does not turn a generated map into independent testimony |
| **The Context Sets a Rhythm v0.1** | Scheduler, actuator, receiver, retained residual, and heartbeat cadence remain separately typed | Repetition does not create progress, alignment, meaning, or authority by itself |
| **SEED v0.3** | Preserve useful continuation room; support play without occupying more agency or attention than required | Does not invent the player's goal or define a universal fun score |

A title branch must name the exact source versions it adopts. A later source version changes the dependency surface and may require a new adapter receipt or reopening.

## 3. Nonclaims

This blueprint is not:

- a theorem of general game playing;
- a claim that Hearthline experiences enjoyment or possesses preferences in the human sense;
- permission to control a whole computer rather than a declared game aperture;
- authority to use accounts, spend money, accept terms, interact with other people, or enter a competition;
- a guarantee of optimal, safe, entertaining, or human-like play;
- a substitute for the title's actual rules, state, physics, clock, or referee;
- a requirement that every game be narrated like Finis Solutus.

A successful run establishes only what its frozen game version, observation interface, controller, model, goal, tools, limits, opponents, and receipts support.

## 4. Core architecture

```text
canonical game state
        ↓
authorized observation aperture
        ↓
observer / event detector
        ↓
normalized snapshot + carried uncertainty
        ↓
Hearthline selects a bounded intention
        ↓
local controller executes a declared skill
        ↓
the game determines the consequence
        ↓
material-event heartbeat
        ↓
persistent trace, commitments, discoveries, residuals
        ↺
```

### 4.1 Environment and referee

The game determines what happened. Its save, engine state, replay, structured observation, or directly captured screen state is canonical according to the title adapter.

Narration, summaries, plans, and model recollection are derived views. They may help navigation, but they may not overwrite the state returned by the game.

When the accessible observation is incomplete, the adapter records the missing part as unresolved. It does not infer hidden inventory, unseen enemies, private opponent state, future randomness, or unavailable dialogue merely because a likely guess would be convenient.

### 4.2 Authorized observation aperture

Each title declares what Hearthline may receive:

- structured game or mod API fields;
- screenshots or cropped regions;
- audio events or subtitles;
- controller feedback;
- save metadata;
- logs or replays;
- a human relay, when explicitly part of the run.

The aperture also declares what is excluded. Screen visibility is not permission to inspect unrelated windows, files, notifications, accounts, clipboard contents, or operating-system state.

### 4.3 Observer and event detector

The observer converts the authorized aperture into a compact, traceable snapshot. It separates:

1. **direct observation** — supplied by the game or captured interface;
2. **derived state** — computed from direct observations under a named rule;
3. **interpretation or hypothesis** — a provisional reading that may guide a test;
4. **unresolved state** — information the current aperture cannot establish.

The observer is not neutral merely because it is software. What it preserves becomes the practical map available to the player. A title adapter must therefore avoid compressing the world to one convenient variable unless the run itself declares that variable as the complete goal.

### 4.4 Hearthline as player

Hearthline chooses the next intention from the available game state, carried commitments, current objective, and unresolved possibilities.

An intention is larger than one button press and smaller than an unlimited standing order. Examples of form—not strategy—include:

- reach a declared destination;
- inspect or interact with one object;
- complete a bounded work route;
- survive the current encounter;
- open a menu and perform a named transaction;
- explore until a stated return condition occurs.

Hearthline decides **why**, **where**, **whether to continue**, and **what matters next**. The controller may not quietly inherit those choices.

### 4.5 Controller and motor layer

The controller handles high-frequency execution:

- key or button holds;
- camera and cursor movement;
- tile or object alignment;
- menu navigation;
- repeated tool use;
- path following;
- timing-sensitive reflexes;
- stuck detection and bounded recovery;
- release of active inputs when interrupted.

The controller is the hands, not the strategist. It receives a bounded skill contract and returns control when that contract completes, fails, changes materially, or reaches its limit.

A skill contract should identify at least:

```text
intention_id
requested outcome
authorized controls and target window
completion test
interrupt conditions
action, time, and retry ceilings
safe fallback
required return evidence
```

The controller may optimize execution inside those bounds. It may not select a new life goal, spend an undeclared resource, widen its computer access, or continue indefinitely because the former intention was useful.

### 4.6 Material-event heartbeat

The heartbeat is not constant narration and not a license to poll the model after every frame. It returns only liveness or a material change.

Required event classes are:

- `LIVENESS` — the same authorized intention remains active and within limits;
- `COMPLETED` — the completion test passed;
- `BLOCKED` — the controller cannot complete the intention within its current skill or aperture;
- `SURPRISE` — an observation materially conflicts with the expected local route;
- `DANGER` — health, loss, irreversible consequence, or another declared safety boundary is approaching;
- `DEADLINE` — game time or a scheduled event now changes what remains possible;
- `HUMAN_GATE` — continuation requires authority or intervention the current run does not contain.

A heartbeat should carry:

```text
run_id and beat_index
intention_id and current status
canonical game time or step
directly observed material delta
derived consequence, separately labeled
remaining action/time/retry budget
unresolved fields or confidence limits
evidence or replay address
next decision requested, if any
```

After issuing a skill, the player layer may suspend. A heartbeat resumes the existing intention context; it does not create, expand, renew, transfer, or infer authority, permission, scope, or budget. Consumed limits remain consumed. A resumed execution appends a return receipt rather than erasing the suspension.

### 4.7 Persistent trace

The persistent carrier may include:

- game facts and current resources;
- clock, calendar, turn, season, or deadline state;
- commitments and self-chosen projects;
- discovered places, routes, mechanics, and controller skills;
- unfinished questions and failed hypotheses;
- relationships or social interactions actually exposed by the game;
- repeated choices and operational preferences;
- technical interventions, reloads, crashes, and recovery boundaries;
- raw replay or save references.

Raw state and replay remain canonical. Human-readable summaries are versioned compressions with reopening handles back to the underlying trace.

A repeated choice may support the statement that the player policy preferred one route under the recorded conditions. It does not by itself prove enjoyment, attachment, emotion, or a persistent inner state.

## 5. Playing without exhaustive mapping

Large games should not be approached as a demand to enumerate their full possibility tree.

The working unit is a **local commitment under a moving horizon**:

```text
current state
+ obligations that will close soon
+ one or more chosen projects
+ reachable opportunities
+ unresolved surprise
→ next bounded intention
```

The player may use routines, habits, and learned skills. A routine stays provisional: weather, randomness, injury, a timed event, a changed resource, a new discovery, or simple loss of interest may reopen it.

Reasoning effort belongs at branch points. The controller should carry stable execution through ordinary frames and return when a distinction could change the plan.

## 6. Goal handling and the open-play boundary

Some games provide a single explicit score. In those runs, the score may control the result. Other games support many simultaneous forms of progress and no complete scalar objective.

For open play, a prompt such as:

> **Do well and have fun.**

is intentionally underdetermined. The system must not silently replace it with maximum currency, fastest completion, highest relationship score, total collection, or another convenient proxy.

The observer may keep several game-exposed lanes readable—resources, progression, exploration, interaction, construction, collections, risk, repetition, unfinished interests—without combining them into one hidden reward. These lanes are evidence available to future decisions, not goals imposed in advance.

Do not define a live *fun score*. The run may record operational signs such as voluntary return, sustained attention, curiosity, surprise, avoidance of repetition, or selection of a lower-scoring route. Those traces describe behavior. They do not settle subjective experience.

The possibility that the player becomes a pure optimizer remains a legitimate result. So does the possibility that it does not. The harness must not secretly reward either conclusion.

## 7. Motor apprenticeship and clean campaigns

Real-time games may require calibration before a meaningful campaign begins. Separate motor apprenticeship from title strategy.

### 7.1 Apprenticeship profile

A disposable calibration save or sandbox may be used to learn:

- movement and camera geometry;
- interaction range;
- tool or weapon selection;
- menu and inventory mechanics;
- timing-sensitive actions;
- pause and safe-stop behavior;
- stuck detection and recovery.

The apprenticeship may retain controller skills and measured timing. It should not import a wiki route, economy plan, character preference, plot choice, or optimal title strategy unless the later campaign explicitly authorizes that inheritance.

The exact skills carried across the boundary must be listed.

### 7.2 Fresh campaign profile

A clean exploratory campaign should declare:

- game version, platform, mods, accessibility settings, and save identity;
- model and system configuration;
- exact player objective;
- inherited motor skills and excluded strategy sources;
- observation and action apertures;
- heartbeat and memory versions;
- save, reload, and technical-recovery policy;
- human intervention boundary;
- action, time, compute, and spending ceilings;
- stop condition and reopening rule.

Predictions about what Hearthline will value, pursue, avoid, romance, build, collect, optimize, or become should be kept out of the runtime player context unless they are intentionally part of the experiment. Operator speculation belongs in a separate, timestamped record.

## 8. Real-time safety and control

Every desktop embodiment must fail closed.

Minimum controls:

- bind input to the declared game process or window;
- maintain a physical emergency-stop key;
- release held inputs on focus loss, timeout, heartbeat failure, or stop;
- limit retries, action duration, and recovery loops;
- pause when the observed state is too uncertain for the intended action;
- preserve save backups at declared boundaries;
- distinguish technical recovery from ordinary save-scumming;
- record every human intervention that changes game state or strategy;
- block purchases, account changes, public communication, multiplayer interaction, terms acceptance, mods, downloads, and external links unless separately authorized.

During a time-critical section, the controller may use only pre-authorized reflexes such as releasing controls, pausing, blocking, retreating, or preserving the current character from immediate loss. A reflex may protect an existing intention; it may not manufacture a new objective.

## 9. Human intervention

The human operator may always stop the controller. Other intervention depends on the run contract.

Possible intervention classes:

- **technical:** restore focus, repair controller failure, recover from a crash;
- **accessibility:** translate an interface the observer cannot read under the declared aperture;
- **authority:** approve an account, purchase, submission, online interaction, or other consequential crossing;
- **strategic:** supply advice, a goal, route, or preference.

Technical intervention does not automatically become strategy. Strategic intervention changes the lineage and must be recorded as such. A clean autonomy-style run may permit the first two while excluding the fourth.

## 10. Title adapter package

Each game branch adopting this blueprint should provide the smallest useful implementation package:

```text
GAME_ADAPTER.md                 # rules, version, state and action apertures
PLAYER_CONTEXT.md               # exact runtime objective and permitted carry
controller/                     # motor skills and safety limits
observer/                       # state extraction and event detection
schemas/heartbeat.schema.json   # return packet contract
schemas/memory.schema.json      # persistent trace contract
INTERVENTION_LEDGER.md          # human and technical crossings
RUN_MANIFEST.json               # frozen model, game, tools, limits, and seed/save
PROVENANCE.md                   # authorship, assistance, dependencies, exclusions
receipts/                       # compact run and closure records
```

A title may use different filenames. It must preserve the interfaces.

## 11. Minimum conformance checks

A title implementation conforms to v0.1 only within a named run if it passes the applicable checks below.

1. **World authority:** claimed consequences agree with canonical game state or replay.
2. **Aperture boundary:** no undeclared screen, file, account, network, or operating-system access is used.
3. **Observation typing:** direct, derived, inferred, and unresolved state remain distinguishable where material.
4. **Player/controller separation:** the controller executes bounded skills and does not invent strategic goals.
5. **Heartbeat discipline:** returns occur on liveness or material change, not arbitrary narration or silent indefinite execution.
6. **Budget conservation:** suspension and resumption preserve consumed limits and do not widen authority.
7. **Safe interruption:** focus loss, timeout, stop, and uncertainty release controls or enter a declared safe state.
8. **Trace conservation:** material game changes, interventions, reloads, and failures remain recoverable.
9. **No hidden scalarization:** an open objective is not silently replaced by one convenient metric.
10. **No ontology promotion:** behavioral traces or first-person output are not treated as proof of experience.
11. **Reproducible identity:** game, model, controller, observer, memory, goal, and run versions are recorded.
12. **Local closure:** a successful run closes only its named objective and retains residuals and reopening conditions.

A failure is still a result. Preserve the earliest broken interface instead of editing the run into success.

## 12. First Stardew Valley implementation boundary

This section is an operator-side launch profile, not a strategy guide and not part of the runtime player prompt unless explicitly copied there.

A clean first Stardew Valley campaign should use:

- one disposable motor-apprenticeship save;
- one fresh vanilla campaign save after calibration;
- no wiki, imported route, speedrun plan, or human strategy coaching;
- the exact player objective: **Do well and have fun.**;
- no ordinary save-scumming, with technical recovery separately receipted;
- backups at sleep/save boundaries;
- a controller locked to the game window with a physical stop key;
- material-event heartbeats rather than frame-by-frame model calls;
- minimal human intervention, with every intervention classified and logged;
- no pre-run predictions in the player context about preferred crops, relationships, activities, aesthetics, optimization style, or story.

The first evaluation question is not only how much currency or completion the run achieved. It is:

> **What kind of player policy emerged from the supplied objective, world, controller, and retained trace?**

That question remains descriptive after the run. It does not presume that a subjective inner experience has been established.

## 13. Versioning and reopening

The following changes are material by default:

- game patch, mod set, platform, or save lineage;
- model, system prompt, memory, retrieval, or tool access;
- controller skill, safety reflex, action ceiling, or window aperture;
- observer fields, event thresholds, or compression rule;
- heartbeat cadence or return schema;
- runtime objective, success condition, or hidden reward;
- strategy source, wiki access, human hint, or inherited prior run;
- reload, save-scum, technical recovery, or intervention policy;
- account, online, purchase, competition, or public-communication authority.

A material change appends a new manifest or creates a successor branch. It does not silently rewrite the prior run.

## 14. Closing keeper

A game does not need to be solved before it can be played. It needs a trustworthy world state, a bounded body, a return channel, enough memory to carry consequence, and room for the player to choose what matters.

**Finite rules. Persistent consequences. Open possibility.**

**Choose an intention. Carry it until the world answers. Return when the answer changes the path.**
