# Pre-Astra Lineage Seal — 2026-09-04T00:18:27Z

**Seal ID:** `PRE-ASTRA-20260904T001827Z`  
**Status:** `PRE_ASTRA_LINEAGE_ANCHOR`  
**Steward:** Christopher D. Pang  
**Repository:** `Grativy6/hearthline-plays`  
**Branch:** `arc-agi/titles/arc-agi-3-hearthline-launch-20260903`  
**Source cutoff:** `2026-09-04T00:18:27Z` / `2026-09-03T20:18:27-04:00`  
**Sealed parent commit:** `86cecd122705f1b82306405f535b7720c04e74ff`  
**Sealed parent tree:** `f6661ed6a05dd854ad5eafb3756149ea8b900065`

This receipt creates a named, immutable lineage point before any admitted use of GPT-6 Astra as a development, coding, strategy, review, or evaluation model. The canonical seal commit is the first commit that adds this file and its paired JSON manifest.

## Claim at the cut

At this cutoff:

- no GPT-6 Astra model output or API call is admitted into the sealed baseline;
- no Astra-generated code, strategy, review, hidden reasoning, or private evaluation output is admitted;
- public reporting about Astra had already been inspected and is preserved as **public analysis context**, not model use;
- this sealing action was prepared in ChatGPT chat mode by **GPT-5.6 Pro** through the connected GitHub tool;
- **GPT-5.6 Sol** is the intended model for the prospective pre-Astra development run, but this receipt does not relabel the sealing assistant or any unrecorded run as Sol.

This is a lineage anchor, not a claim that every later descendant remains pre-Astra. A descendant stays in the pre-Astra lineage only while every contributing model/tool invocation is recorded and no Astra output is admitted.

The absence claim is bounded to the inspected repository state and Christopher D. Pang's declaration at this cut. It cannot prove the absence of unrecorded activity outside those sources.

## Repository and source lock

The full parent tree hash above binds the complete branch state. The critical source identity is:

- `launch/source-lock.v2.json` — blob `7e79156fc73ef1cf71bbf4ba43f6bf32c5da943d`

That source lock pins these repository views:

| Repository | Branch | Commit |
|---|---|---|
| `Grativy6/hearthline` | `main` | `16eab7f3d584a8215a6e1e0b2a93b157c02f787a` |
| `Grativy6/hearthline-workshop` | `main` | `b5798da16bbd58b61453e42ba3a9e0b07727cb6e` |
| `Grativy6/hearthline-plays` | `arc-agi/titles/arc-agi-3-research-station` | `74728f8c4ec9409bd0e6c8064a0b6b356da776f6` |
| `Grativy6/strongwiz` | `main` | `edc88b80f872f766c22b3a050a7f6837d6e652d8` |
| `Grativy6/ARC3` | `main` | `a1b54f77fc73cc50641cbe6952a1b683c6b5d1fb` |

Official ARC surfaces already pinned at the cut:

| Surface | Version / commit |
|---|---|
| `arcprize/ARC-AGI` | `0.9.9`, commit `f12822c4d550121c35a275008d964afbbed47d2f` |
| `ARCAGI-Labs/arc-agi-3-benchmarking` | commit `d7e9a68a001bb95123013384eea287e95e8567e2` |

`launch/ASTRA_PUBLIC_BLUEPRINT.md` at blob `9ceb996ddf2f4f15f5520303062925d069adaaaf` records only publicly described evaluation behavior. Its presence does not mean Astra generated or reviewed this lineage.

## Harness configuration at the cut

The parent tree is the authoritative complete configuration. These are the principal human-readable and executable surfaces:

| Path | Blob |
|---|---|
| `launch/strategy/HEARTHLINE_ARC_PROTOCOL.md` | `216f5d96e4a8c5bd44379a7c8577f4886c0efbbb` |
| `design/PAIR_STATIC.md` | `5125bb6179fe99504e5323a5647ac008445f28a0` |
| `launch/schemas/orientation-receipt.v1.schema.json` | `c5f4e22d07db49db77ffac1c252fef7f6c4095ff` |
| `launch/schemas/pair-static.v1.schema.json` | `f399f2a7350f7ee3a733e214e8aed2a28b0340b9` |
| `launch/schemas/spark-static.v1.schema.json` | `6a31928c34d2a70b9047a83a9e9b4affb59537ca` |
| `.github/workflows/arc3-orientation-probe.yml` | `29a396188be6e5f8a396aead8ea1fd27b511b653` |
| `.github/workflows/launch-verify.yml` | `f86d76ec0abba22b54f78476a9c297b87d08ad24` |
| `.github/workflows/verify-launchpad.yml` | `3c52738df1cec1303832e29e1c4369ad2347a670` |
| `.github/workflows/verify.yml` | `615a746ff44e5ae0da53e029fe5439d94207b9db` |
| `practice/ls20/action-plan.json` | `4bdc87771d8f3165375eb2192f17f448e80a4cf9` |
| `practice/ls20/world-model.json` | `266219beb5d391e4c3e714ce2a8c8f2f5de029da` |
| `launch/status.json` | `9ccb259b5bde78dd190e8847fdeed5ecf97df931` |

The status object at the cut records:

```text
phase = PUBLIC_ORIENTATION_AUTHORIZED
competition_mode = false
environment_action_count = 0
public_arc_contact_count = 0
kaggle_contact_count = 0
private_holdout_access = false
paid_provider_calls = 0
```

## Public-game lineage carried into the comparison

These are bounded historical records, not new results produced by this seal.

| Experiment | Recorded result | Evidence boundary |
|---|---|---|
| ARC3 Build 003 / Campaign 37 | `NOT_FINISHED`; 4/6 levels; 259 official submissions; 256 non-reset actions; 0 holdout exposure; frozen candidate prefix `0173ab4` | Prior development journal and archived ARC3 lineage; not re-executed here |
| Model Scientist | Public `WIN` recorded in a previously audited receipt; 1,327 winning-session actions; 2,315 total recorded actions; 71,244.6 s | Prior local receipt comparison; artifact bytes are not copied into this seal |
| Wise Scientist v2 | Public clean-room `ls20-9607627b` `WIN`; 7/7; 917 actions; 11 aggregate reset events; 9,748.8 s; receipt SHA-256 `34c9af3709d77218d501fb261656702e2aaadac3eacb849dcdec86c5a0587953` | Not a Kaggle `MyAgent`, private-set, RHAE, or prize claim |
| Strongwiz Calibration 001, attempt 002 | `PARTIAL`; `NOT_FINISHED`; 4/7; 754 non-reset actions; 4 resets; 758 calls; commit `9ea900c361dceb176562487893798c536cc1669e` | No credentials, competition entry, or submission |

Agreement among these runs is not treated as independent corroboration when they share models, source frameworks, environments, or inherited mechanics.

## Required final freeze before a private run

This anchor is earlier than the final candidate freeze. Before any separately authorized Kaggle/private evaluation, append a new immutable receipt binding:

1. exact candidate commit and tree;
2. exact evaluated runtime and model identity;
3. model weights, tokenizer, and inference runtime when local;
4. dependency lock and container/image identity;
5. seed or seed schedule;
6. action, compute, wall-clock, and memory budgets;
7. closed-stdin and network-disabled verification;
8. submission artifact digest;
9. an explicit no-Astra chain covering every contributing development and evaluation invocation.

A hosted GPT-5.6 Sol session may develop the candidate, but the evaluated offline package must record what actually runs behind the private curtain. Development authorship and evaluated runtime are separate facts.

This seal does **not** authorize Kaggle access, credentials, competition mode, a submission, or any private evaluation.

## Pre-registered ablations

These comparisons are declared before a private result so they cannot be selected only after seeing which story is flattering.

| ID | Frozen change | Question |
|---|---|---|
| `A0_FULL` | No change | Reference condition |
| `A1_NO_PAIR_STATIC` | Replace differentiated paired Sparks and Pair Static with one investigator trace | Does pairwise comparison contribute beyond duplicated work? |
| `A2_NO_PERSISTENT_TRACE` | Retain only current state; remove recoverable cross-step trace and source handles | What does trace custody contribute? |
| `A3_NO_RESIDUAL_REOPEN` | Remove explicit residuals and reopening handles; use ordinary overwrite/closure | Does preserved unresolved burden improve recovery and transfer? |
| `A4_NO_OPERATOR_MEMORY` | Remove retained mechanic/operator hypotheses while preserving perception and action interfaces | What does learned causal/world-model carryover contribute? |
| `A5_NO_EXPLICIT_PLAN_CENTER` | Remove ordered goal/subgoal planning and choose from present state only | What does explicit task-centered multi-step planning contribute? |

Hold constant, as far as the platform permits:

- model weights and inference runtime;
- perception and environment adapter except for the named ablation;
- environment/version set;
- seed schedule;
- action and compute budgets;
- evaluator and terminal-state rule.

Record score, levels, actions, resets, wall-clock, compute/token use, invalid actions, prediction error, and recovery after surprise or failure.

Do not repeatedly probe or tune on the competition private holdout. Run ablations on frozen public, synthetic, or separately authorized validation surfaces unless the competition rules expressly permit otherwise. A full-system advantage would support the named mechanisms only under the tested aperture; it would not by itself prove PAL as a complete theory or isolate every component.

## Contamination and fork rule

At the first admitted use of Astra, record:

- the first affected commit;
- the displayed/provider model identifier;
- the provider surface;
- the files, data, strategies, or reviews touched;
- the exact scope of the contribution.

Recommended comparison branches:

```text
pre-astra-sol     descendants preserving the no-Astra chain
astra-comparison  descendants admitting Astra and naming the first crossing
```

If Astra contribution cannot be ruled out, mark `ASTRA_PROVENANCE_UNRESOLVED` rather than claiming no-Astra. Public reporting about Astra remains source context; Astra-generated output is the lineage crossing.

## Claim ceiling and reopening

This receipt preserves a comparison baseline. It is not a competition result, prize claim, proof of AGI, proof that PAL caused performance, or authority to use credentials or private evaluation surfaces.

Append successor receipts. Never rewrite this seal to absorb later model use, results, or ablations.
