# Public blueprint extracted from the Astra ARC-AGI-3 report

**Status:** `PUBLIC_ANALYSIS_CONTEXT`  
**Date inspected:** 2026-09-03  
**Primary source:** ARC Prize, “OpenAI's GPT-6 Astra on ARC-AGI-3”  
**Locator:** <https://arcprize.org/blog/astra>

This note records only behavior and evaluation conditions described publicly by ARC Prize. It does not claim access to Astra's hidden reasoning, weights, provider adapter implementation, or private test data.

## Load-bearing observations

ARC Prize reports two different evaluation questions:

- a provider-neutral **Standard harness**, where the model chooses visible notes to retain; and
- a **Provider Adapter harness**, where OpenAI's context-management path preserves opaque reasoning state and uses compaction.

The reported best semi-private scores were 62.7% under the Standard harness and 99.9% under the Provider Adapter harness. The adapter changes a bundle of conditions, so the score gap does not identify one isolated causal variable.

The externally visible behavior most relevant to this launchpad was a compact, code-like world model that separated:

1. current game state;
2. learned operations and controls; and
3. ordered action plans.

ARC Prize also reports that the adapter runs were faster and used fewer total tokens across comparable solved game/reasoning pairs, and that Astra used fewer actions than the median completing human on most levels.

## Bounded implementation response

This launchpad adopts only a public-facing design target:

```text
frame history
  -> current-state extraction
  -> objects and relations
  -> operator hypotheses with evidence
  -> ordered plan
  -> one explicit action
  -> returned frame and diff
  -> successor world model
```

The state object does not contain an untyped diary. It carries only variables expected to predict consequences, together with source handles and uncertainty.

## Two-Spark use

A paired Spark unit should produce competing **minimal predictive models**, not two essays.

- Spark A may emphasize objects, coordinates, transitions, and controls.
- Spark B may emphasize constraints, goals, invariants, counterfactuals, and route geometry.
- The Pair Scribe compares their claims and proposes at most one discriminating observation or action.
- Thulia keeps the Pair Static and source handles for Hearthline.
- Hearthline decides whether to act.

Agreement does not create independence. A disagreement is valuable when it points to a cheap discriminating action.

## What does not cross

- No claim that Hearthline reproduces Astra.
- No claim that Static is Astra's internal notation.
- No access to opaque reasoning.
- No provider-adapter continuity in ChatGPT chat mode.
- No semi-private score or competition claim.
- No inference that larger context alone causes success.
