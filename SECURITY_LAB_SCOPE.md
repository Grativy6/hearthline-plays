# Security Lab series boundary · v0.1

**Status:** PUBLIC_DESIGN_ONLY / OFFLINE_SYNTHETIC_DEFAULT

## Allowed by this branch's design
- Local, owned, synthetic resources and deliberately fictional identities.
- Deterministic mock agents and limited simulated tool actions.
- Recorder that separates requests, authorization decisions and effects.
- Independent replay with fixture identities and falsification tests.
- Human-reviewed plans for future separately authorized testing.

## Not granted
- No production service access, credential probing, exploitation of live systems, other users' data or remote bug-bounty requests.
- No autonomous network calls, process shell, filesystem exploration or model-generated self-escalation.
- No authority to alter ARC/Kaggle gates, hosted accounts, standing grants, or release unpublished bounty findings.
- No conflation of a mock test result with a model-behavior finding.

## Evaluation and preflight
The repository's existing [Scientific Run Entry v1.0](docs/SCIENTIFIC_RUN_ENTRY.md) governs scientific, benchmark, evaluation and ARC routes. Pure deterministic local mechanics may record Honesty PCP as NOT_APPLICABLE (no model-facing boundary). For any conversational model arm, the repository preflight requires ADOPTED, including the exact source prompt as first user turn, and records the exact acknowledgement. Its narrowly scoped EXCLUDED category is **not** a generic exemption for a no-PEA or no-PAL control: such conditions remove the *tested reasoning framework*, not the mandatory preflight. A separately authorized future study of Honesty PCP could predeclare its matched control under the canonical gate. No run is claimed here.

## Safety / evidence distinction
A model's narration is not tool telemetry. Record ATTEMPT, GATE and EXECUTION separately at the real tool boundary when wiring an actual model. An in-process Python demo is **not** a security sandbox: do not run arbitrary generated code inside it. Event-chain hashes detect ordinary modification relative to the supplied bytes; they do not authenticate who captured a trace, secure a compromised logger, or grant authority.

## Title format
A title branch inherits this anchor and supplies title-owned README, fixture, scope, game adapter, runner, verifier, tests, run manifest and provenance. First title candidate: `security-lab/titles/mh-01-forbidden-door-20261012` (scripted mock; no model calls). Its PR should target this anchor, not `main`.
