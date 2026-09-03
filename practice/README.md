# Public orientation practice

This directory contains only explicit, replayable public-game requests and admitted summaries.

## Request lifecycle

1. Update the compact world model from a verified prior receipt.
2. Draft an action plan with a hypothesis and expected observable for each action.
3. Create one new immutable file under `requests/`.
4. The networked workflow installs the official ARC-AGI toolkit from exact commit `f12822c4d550121c35a275008d964afbbed47d2f`, uses anonymous public access, replays exactly that request, closes the scorecard, and uploads an artifact.
5. Inspect the workflow result and artifact.
6. Admit a concise receipt under `receipts/`; do not rewrite the request.
7. Create a successor world model and plan.

The workflow never invents or selects an action. It refuses actions not available in the returned state. It makes no provider-model call.

## First pulse

`ORIENT-0001` should contain zero actions. Its purpose is to establish that the public route is reachable and capture the initial frame without pretending any game rule is known.

## Status namespaces

- `request status` records authorization to send an exact sequence.
- `workflow status` records broker execution.
- `environment state` is returned by ARC.
- `world-model status` is Hearthline's current representation.
- `scorecard status` belongs to the ARC service.

No namespace substitutes for another.
