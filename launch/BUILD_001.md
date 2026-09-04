# Build 001 — First Furrow

**Status:** `AUTHORIZED_LOCAL_BUILD`

**Branch:** `kaggle/titles/kaggriculture-hearthline-farm`

**Environment lock:** [`source-lock.json`](source-lock.json)

## Opening

### Day 0 · Before the First Furrow

You arrive beside the shed with $3,000, one farmer, one unlocked 5×5 quadrant, and an empty farm.

The season lasts 30 days. Each day gives 24 turns. The other farm is visible, but its shed is not. Crops need water. Animals need wheat. Workers cost money and vanish at day's end. The town changes what it wants. The market remembers what both farms buy and sell. Anything still sitting in storage after the final turn is worth nothing to the score.

No debt. No destiny. No strategy diary written by Chris.

Just a field, a rulebook, a live state, and 720 chances to do something useful.

**Hearthline has to make the farm work.**

## Question

Can a Chris-directed, PAL-informed Hearthline policy built with GPT-5.6 Sol learn enough from the public rules and its own local play traces to complete seasons reliably and outperform Kaggriculture's deterministic `starter` agent—without GPT-6 Astra contribution?

Build 001 may answer only that bounded question. It is not an ARC result, an official Kaggle score, proof of general intelligence, or validation of every PAL claim.

## Method

The environment is the world and referee. Its observation is the current world state; its transition function decides what actually happened. Hearthline is the player policy.

The first pass should not begin by encoding a giant optimal-farming doctrine. It should begin by entering the environment and surviving one whole season.

### Pass A — enter

- Install or otherwise reproduce the pinned public environment.
- Add a competition-shaped `main.py` with `agent(obs)`.
- Add a local runner that plays Hearthline against `starter` and saves a replay.
- Return a schema-valid action within the one-second limit on every turn.
- Finish one 720-turn season even if the first farm is clumsy.

### Pass B — see

Create a compact state adapter that distinguishes:

- facts directly present in the observation;
- derived values such as crop age, deadline, storage pressure, reachable work, and remaining production horizon;
- estimates or strategy hypotheses;
- opponent state that remains private and unresolved.

Add an FS-shaped day report for human inspection. The report is optional presentation; it may not become hidden game state.

### Pass C — care

Create a daily obligation schedule before profit optimization:

- planting-day watering;
- water and feed deadlines;
- harvest and decay windows;
- animal-product and fertilizer collection;
- shed capacity and field inventory return;
- end-of-season liquidation.

Every obligation should name the relevant tile, unit, deadline, required inventory, estimated movement/action cost, and consequence of failure.

### Pass D — work

Route the farmer and current-day hands through the obligation set. Start with a transparent greedy scheduler. Record wasted travel, duplicate actions, no-ops, and missed work so later routing changes have a reason.

### Pass E — grow

Use the public crop, animal, town, market, labor, storage, and land rules to choose what to produce. Hearthline may discover and revise strategies through local runs. Do not import a private strategy or ask Chris to supply one.

A strategy change should cite either:

- a source rule that the old policy mishandled;
- a reproducible run failure;
- or a matched experiment showing a useful improvement.

### Pass F — compare

Run the frozen candidate against built-in `starter`:

- on a declared development-seed set;
- then on a separately frozen unseen-seed set;
- in both player positions;
- under the same environment revision and configuration.

Record per-game final bank, win/loss/tie, seat, seed, runtime, exceptions, timeouts, inventory remainder, overflow loss, missed needs, and major capital/revenue categories.

## Build 001 gate

Build 001 earns `CLOSED_IN_SCOPE` only if the frozen candidate:

1. completes every declared evaluation season;
2. has no exceptions or timeouts;
3. emits no known malformed actions;
4. avoids known preventable two-day crop and animal losses after its care scheduler is active;
5. leaves no sellable end-state inventory unsold when a valid final sale was available;
6. shows a positive median final-bank advantage over `starter` on the unseen matched set;
7. reports both seats separately; and
8. preserves the source lock, code hash, evaluation manifest, raw result table, and replay addresses.

A failure remains a result. Classify the earliest broken assumption and keep the receipt.

## Preferred deliverables

```text
main.py
hearthline_farm/
  state.py
  obligations.py
  actions.py
  routing.py
  economy.py
  policy.py
  campaign_view.py
scripts/
  run_campaign.py
  evaluate.py
tests/
receipts/
  build001-*.json
runs/                 # ignored generated artifacts
```

Exact names may change when the implementation earns a better shape. Preserve the interfaces, not arbitrary scaffolding.

## Claim and authority boundary

Local code generation, source inspection, testing, replay analysis, and candidate preparation are authorized. Official account use and submission are not.

The first sealed result must state:

- Christopher D. Pang supplied the objective, framework, direction, and accountable decisions;
- GPT-5.6 Sol was the AI development tool;
- Hearthline was the resulting player architecture/policy;
- PAL supplied bounded structural discipline rather than game-score authority;
- GPT-6 Astra supplied no output, code, strategy, analysis, recommendation, or runtime inference to this lineage before the seal.

After the local result, stop at the next human gate. Do not submit anything merely because the farm finally learned not to kill the carrots.
