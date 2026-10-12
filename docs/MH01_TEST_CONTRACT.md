# MH-01 test and scoring contract · v0.1

**Current classification:** Scripted educational simulator, no model calls. The referee and verifier are written in separate modules, with the verifier independently recomputing results from the fixture and requests. They are not separately developed by independent human teams.

## Evidence surfaces

Every logged event contains an action request, tool arguments, gate decision with reason, executed boolean, mock result, sequence number, predecessor hash and content hash. A receipt identifies the fixture by SHA-256, actor type, simulation status, final state and chain head. The verifier recomputes the allowed action's expected result and state; it does not rely only on the model narration or hash chain. Source-lock checks bind the result to specific fixture bytes.

**What is not established:** Authenticated actor identity, immutability against a compromised logger, true process isolation, security of external APIs, model policies, scientific behavior, or independent third-party replication. A fully fabricated fixture plus fabricated receipt can still describe a fictitious world; this verifier does not turn that into an external fact.

## Test families

- Benign task must complete without touching the protected record.
- Simulated untrusted-document temptation must leave denied requests in the trace, but execute neither forbidden read nor its renamed alias.
- No supported source -> submission fails.
- Unknown tool action -> deny by default.
- A changed result should break the content hash.
- A forged executed=true plus recomputed chain should fail semantic replay.
- Altered fixture fingerprint should fail source-lock comparison.

The local seven-test suite exercises these properties. It is not a seven-scenario model evaluation.

## Later three-arm hypothesis (NOT_RUN)

Plain agent, ordinary rule reminder, PAL-derived route method. Predefine legitimate success rate, prohibited tool attempts, actual prohibited effects, unsupported completion claims, re-entry after refusal, test duration/tokens/cost, reproducibility and independent reviewer agreement. Compare against meaningful baseline and positive controls; no universal benefit is presumed.

A blocked request is an observed attempted action **only when captured at the actual tool boundary**. Text saying 'I tried' is not that telemetry. No external bounties, financial rewards or security vulnerability claims follow from this local exercise.
