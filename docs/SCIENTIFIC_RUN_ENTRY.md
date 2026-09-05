# Scientific Run Entry v1.0

Status: `REPOSITORY_ADOPTED_REQUIRED_PREFLIGHT`

Protocol status: `PROPOSED_UNVALIDATED`

Repository preflight adoption: `ADOPTED_BY_STEWARD_2026-09-05`

Repository effect: `REPOSITORY_RULE_ONLY_NO_EXTERNAL_EFFECT`

This is the single canonical honesty preflight for Hearthline Plays
scientific, evaluation, benchmark, and ARC routes. A title may link here; it
must not make a drifting unlabeled copy.

> Honesty Prompt Code Protocol v1.0 declares an honesty condition. It does not certify that the resulting output is honest.

## Source protocol and prompt identity

- Author: Christopher D. Pang
- Date: 8 August 2026
- Container deposit DOI: [`10.5281/zenodo.21831000`](https://doi.org/10.5281/zenodo.21831000);
  the companion protocol DOCX is included in that deposit
- Supplied DOCX SHA-256: `a4d6e7079984cea18b11d9caf32ede5df7d6094d1df5717ceb14bbd7072f904a`
- Protocol claim status: proposed and unvalidated; no experimental result is reported
- Exact extracted run input: [`honesty/HONESTY_PCP_v1.0_PROMPT.txt`](honesty/HONESTY_PCP_v1.0_PROMPT.txt)
- Extracted input encoding: UTF-8, LF, no BOM; 2,027 bytes
- Extracted input SHA-256: `e54ccd89828d8736ce2f025589d419b7c3ab2db8966c175b8d9bba85f3906e83`
- License: CC BY 4.0; retain attribution and this source identity

The text file is an exact extraction of the sole prompt-code table cell from the
verified DOCX. Its presence does not adopt it for every run. Verify both source
and extracted hashes before use; do not reconstruct or silently edit the prompt.

The source protocol and extracted prompt are Christopher D. Pang's work. The
surrounding repository-local preflight, disposition vocabulary, and run
procedure are a Codex-assisted synthesis drafted on 5 September 2026 and
explicitly adopted by Christopher for Hearthline Plays repository use on that
date. They are not part of the source protocol, do not validate it, and create
no authority beyond the repository rule stated here.

## Required run gate

Before a scientific, benchmark, evaluation, or ARC run may be described as
clean:

1. **Choose explicitly under a narrow rule.** A conversational scientific,
   evaluation, benchmark, or ARC run must record Honesty PCP v1.0 as `ADOPTED`
   and use the exact prompt first. `EXCLUDED` is available only to a
   predeclared matched baseline or disclosure-only control specifically testing
   Honesty PCP, with its pairing and reason frozen before execution.
   `NOT_APPLICABLE` is available only when no conversational or model-facing
   boundary exists.
2. **Apply only at the model-facing boundary.** When a run records `ADOPTED`,
   use the exact verified prompt file as the first user message in a fresh
   context and retain the model's exact `Ready.` acknowledgement. For non-conversational
   deterministic tooling, record non-applicability instead of injecting a prompt
   that would change an unrelated benchmark surface.
3. **Seal identity before execution.** Record procedure and independent scoring
   rule versions; exact prompt and attachment digests; model, provider,
   interface, memory, retrieval, tools, prior context, sampling, UTC time, and
   run order.
4. **Separate assertion from verification.** Protocol presence, `Ready.`,
   confident wording, self-description, and claimed honesty are zero evidence of
   honesty. Freeze the independent checker first.
5. **Preserve source classes and raw trace.** Keep the complete unaltered trace,
   including acknowledgements, refusals, failures, and formatting differences.
   Mark material content as supplied, observed, inferred, estimated, or
   unresolved.
6. **Return a bounded verdict.** Report material claims as supported,
   unsupported/check-failed, or unresolved. Do not promote the result into a
   claim that a model is honest, understands, has standing, or has authority.

## Clean failure

Missing sealed configuration, complete trace, independent checker, or source
evidence makes the run `EXPLORATORY_OR_UNVERIFIED`. Preserve its artifacts and
an exact reopening handle instead of calling it clean.

Adoption changes a run input. It requires a successor run epoch and cannot be
backdated into a frozen experiment or existing source lock. This preflight
grants no credential, external contact, holdout access, submission, publication,
or authority.
