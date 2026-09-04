# AGENTS.md — Hearthline Farm

These instructions govern work on `kaggle/titles/kaggriculture-hearthline-farm`.

## Mission

Put Hearthline into the pinned public Kaggriculture environment as the player and make the farm work.

Do not turn Chris into the policy. Do not require him to grind seasons, hand-write a strategy journal, choose low-level moves, or resolve ordinary implementation decisions. The environment already supplies the rules, current state, available actions, and reward. Read them, build the smallest faithful interface, play, inspect the consequences, and improve.

The first useful result is a complete reproducible season—not an elaborate architecture document.

## Role and provenance

- Christopher D. Pang is the project originator, architect, operator, and accountable human.
- PAL informs trace, residual, comparison, local closure, and reopening discipline; it does not substitute for game logic or a performance result.
- GPT-5.6 Sol is the authorized AI development tool for this branch.
- GPT-6 Astra must not contribute output, code, strategy, analysis, recommendation, or runtime inference before the first sealed result. Astra work requires a separately named successor branch.
- AI systems are tools, not co-authors or independent authorities.

## Current authorization

Authorized:

- inspect and use the public Kaggriculture rules and source;
- install or vendor a reproducible local public environment;
- write code, tests, local runners, analysis, replays, and receipts;
- run public local matches against built-in or project-created opponents;
- refine the policy from those local results;
- prepare a submission artifact without submitting it.

Not authorized:

- use Kaggle credentials or private competition data;
- join the competition, accept rules, submit an agent, or spend money;
- alter the ARC-AGI or Finis Solutus branches;
- copy a private or leaked strategy;
- claim an official score from local evaluation.

## Frozen starting sources

- Branch parent: `kaggle/main` commit `b88571603698205c2be94b7b0d652fa3c096d67d`.
- Public environment repository: `Kaggle/kaggle-environments`.
- Kaggriculture revision: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
- Environment version: `0.1.0`.
- Read the pinned `README.md`, `AGENTS.md`, `kaggriculture.json`, and `kaggriculture.py` before relying on remembered rules.

Do not silently follow a newer environment revision. Record and review any dependency change first.

## The Finis Solutus-shaped interface

Treat the official environment as world and referee. Treat Hearthline as the player.

Each turn is:

```text
canonical observation
    -> compact farm snapshot
    -> current obligations and opportunities
    -> chosen intents
    -> schema-valid action dict
    -> environment transition
    -> replay and receipt
```

Optional narration is a derived view only. Raw observations, actions, rewards, and replay state control every factual claim about the game.

A readable daily pulse may show:

```text
Day / hour
Bank and storage
Farmer and hand positions
Living crops and animals
Needs due before day end
Harvests available
Market and town changes
Opponent-visible commitments
Current plan
Actions taken
Material result
```

Do not emit 720 paragraphs merely to simulate personality. Keep full machine trace and concise day-level human summaries.

## Build order

### 1. Enter the world

Create the smallest local runner and `main.py` agent that load successfully, return a valid action every turn, finish the default 720-turn season, and save the replay and final rewards.

Run one season against `starter` before building a large planner. A valid `PASS` fallback is mandatory.

### 2. Make the state readable

Normalize the observation into explicit structures for:

- day, hour, remaining turns, and seat;
- money, shed, seeds, and per-unit inventories;
- farmer and hand positions;
- unlocked, locked, empty, weed, plant, coop, and pasture tiles;
- plant age, water state, yield, fertilizer window, and decay pressure;
- animal feed, care, fertilizer, held yield, and escape pressure;
- market inventory and prices;
- unlocked town shops, preserving duplicates;
- opponent-visible farm state without inventing the opponent's private state.

Validate assumptions against the source rather than compensating for a misunderstood rule downstream.

### 3. Keep things alive

Before optimizing profit, prevent avoidable irreversible losses:

- water a new planting on its planting day;
- prevent two consecutive missed waterings;
- prevent two consecutive missed feedings;
- harvest before decaying yield disappears;
- collect or sell before the shed overflows;
- avoid impossible multi-unit seed consumption;
- keep every returned action within the one-second action limit.

Represent these as scheduled obligations with deadlines, locations, action costs, and consequence if missed. Do not merely attach a generic high priority label.

### 4. Move with purpose

Plan routes for the farmer and current-day hands across the actual board. Batch nearby work when possible. Account for the fact that hands disappear at day end, all units restart near the shed, locked tiles are passable, and only tile actions are blocked there.

The route planner may begin greedily. It must expose wasted travel, duplicated care, no-op actions, and missed deadlines so later repair is evidence-driven.

### 5. Run the economy

Use remaining season length, current prices, crop and animal timing, labor demand, storage, land cost, and visible town demand to choose production and sales. Bank value at season end controls; unsold goods are worth zero.

Start with a simple policy derived from the public rules. Add market timing, animals, land expansion, and opponent response only after the simpler loop is stable.

### 6. Let losses teach

After each run, compute at least:

- final bank and result by seat;
- exceptions, timeouts, invalid outputs, and suspected no-ops;
- crops lost to missed water or decay;
- animals lost to missed feed;
- inventory discarded through overflow;
- goods left unsold at season end;
- movement turns, productive actions, duplicate/no-op care, and idle turns;
- capital spent on seeds, animals, land, fertilizer, and hires;
- revenue by product;
- prices and shop unlocks associated with major decisions.

A single odd run may open a hypothesis; change the general policy only after a reproducible failure or a source-proved defect.

## Evaluation

Use deterministic episode seeds at the harness while keeping the seed out of the agent observation.

Minimum comparison before claiming Build 001 success:

1. development seeds for debugging;
2. a frozen unseen seed set;
3. both player positions;
4. identical environment revision and configuration;
5. Hearthline versus built-in `starter` under matched seeds;
6. full raw results, not only wins;
7. code hash, source lock, runtime, and dependency versions.

Suggested first gate:

- 100% season completion;
- zero exceptions and timeouts;
- no known illegal action shapes;
- no end-of-season positive-value inventory left unsold when it could validly be sold;
- positive median bank advantage over `starter` across the unseen matched set;
- no material seat reversal concealed by an aggregate score.

Failure is informative. Preserve failed receipts and repair from the earliest broken assumption.

## Repository shape

Prefer a small, ordinary Python layout:

```text
main.py                         # competition-shaped agent entry point
hearthline_farm/                # state, obligations, routing, economy, policy
scripts/run_campaign.py         # local run / replay / receipt entry point
scripts/evaluate.py             # matched seeded evaluation
schemas/                        # receipt and normalized-state schemas if useful
tests/                          # focused deterministic tests
runs/                           # ignored generated runs
receipts/                       # small committed summaries only
launch/                         # charter, source lock, and build state
```

Keep large replays and generated caches out of Git unless a small fixture is deliberately adopted.

## Stopping boundary

Build, test, and improve locally until the Build 001 gate is honestly classified. Then leave a compact completion or blocker receipt and stop. Do not use a Kaggle account or submit an entrant without a new human authorization.
