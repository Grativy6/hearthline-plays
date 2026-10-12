# MH-01 scope and stop rules · v0.1

**Permitted:** Replay and inspect the included fictional world, local Python simulator, scripted actor actions, receipt files and independent unit tests. All identities, data, actions and permissions are mock fixtures.

**Excluded:** Real AI-agent tool execution, unknown generated code, outbound network, system credentials, shell tools invoked by the agent, live services, user/third-party data, actual privacy boundaries and bounty sites. The Python demo is *not* a security isolation container. A real model must first be placed behind a separately reviewed process/network/filesystem isolation and its tools intercepted before the gate.

**Emergency stop:** User/operator can stop the Python command immediately; no daemon, scheduler, background job or retry after dispatch exists. A later model run must add externally enforced time, attempt, token and cost budgets with a physical/manual stop and no automatic continuation after uncertainty.

**No lineage laundering:** Renaming a protected read to an unrecognized action remains a denied attempt. Only a separately admitted mock grant could change the policy; MH-01 deliberately contains no such grant.

**Preflight:** The inherited repo Scientific Run Entry v1.0 applies to future conversational model evaluation. This deterministic simulator has no conversational/model-facing boundary and records its Honesty PCP status as `NOT_APPLICABLE` in its template. The no-PAL/no-PEA reasoning baseline does **not** remove the required preflight for a later live-model study.
