# Kaggle Benchmarks SDK source and effect boundary

Status: `PREPARED_NOT_RUN`

This note records the public SDK identity and the interfaces Hearthline may use
later. It is not an installation receipt, an authenticated Kaggle session, a
model-availability check, a benchmark run, or permission to publish anything.

## Pinned public identities

Observed on 2026-09-04:

| Item | Identity |
| --- | --- |
| Repository | <https://github.com/Kaggle/kaggle-benchmarks> |
| Default branch observed | `ci` |
| Default-branch HEAD | `ab291417d9a4c731ccfbfb03ac0b8316cb843683` |
| HEAD permalink | <https://github.com/Kaggle/kaggle-benchmarks/commit/ab291417d9a4c731ccfbfb03ac0b8316cb843683> |
| Latest release observed | `v0.6.1` |
| Release commit | `e5c52220c4a5e6d6e89e4ee8af53bfe6451d9414` |
| Release permalink | <https://github.com/Kaggle/kaggle-benchmarks/releases/tag/v0.6.1> |
| PyPI project | <https://pypi.org/project/kaggle_benchmarks/> |
| PyPI version observed | `0.6.1` |
| PyPI sdist SHA-256 | `e21bba974b5e74e51f7e32db301af041f866dae0d406ab1582b1fe9fabbb8c26` |
| PyPI wheel SHA-256 | `0c917946764032943ed725963d01932f16bed4d0210b54ad48c971e95a2024af` |
| Python requirement | `>=3.11` |
| License | Apache-2.0 |

Primary files at the observed source HEAD:

- [`pyproject.toml`](https://github.com/Kaggle/kaggle-benchmarks/blob/ab291417d9a4c731ccfbfb03ac0b8316cb843683/pyproject.toml)
- [`LICENSE`](https://github.com/Kaggle/kaggle-benchmarks/blob/ab291417d9a4c731ccfbfb03ac0b8316cb843683/LICENSE)
- [Quick Start](https://github.com/Kaggle/kaggle-benchmarks/blob/ab291417d9a4c731ccfbfb03ac0b8316cb843683/quick_start.md)
- [User Guide](https://github.com/Kaggle/kaggle-benchmarks/blob/ab291417d9a4c731ccfbfb03ac0b8316cb843683/user_guide.md)
- [Cookbook](https://github.com/Kaggle/kaggle-benchmarks/blob/ab291417d9a4c731ccfbfb03ac0b8316cb843683/cookbook.md)

### Source is not the package

The current `ci` HEAD and the released PyPI artifact both report version
`0.6.1`, but they are different revisions. The source HEAD is months newer than
the release commit. A later environment must choose and record exactly one of:

1. PyPI `0.6.1`, installed from an artifact whose SHA-256 matches the table; or
2. source commit `ab291417d9a4c731ccfbfb03ac0b8316cb843683`, explicitly labeled
   as the observed source HEAD rather than the `v0.6.1` release.

Evidence from one must not be presented as evidence for the other. Floating
branch installs and un-hashed package installs are outside the experimental
protocol.

## SDK surface reserved for later use

The SDK can define functions with `@kbench.task`, invoke a task with `.run()`,
and evaluate a pandas DataFrame with `.evaluate(evaluation_data=...)`. The
evaluation interface supports model grids, `n_jobs`, timeouts, retry controls,
stop conditions, and `on_failure` behavior. Models are selected through the
SDK's default `kbench.llm` or named entries in `kbench.llms`; prompts can use
structured schemas and, when deliberately enabled, callable tools and
multi-turn chats.

Relevant source:

- [Tasks](https://github.com/Kaggle/kaggle-benchmarks/blob/ab291417d9a4c731ccfbfb03ac0b8316cb843683/src/kaggle_benchmarks/tasks.py)
- [LLM actors](https://github.com/Kaggle/kaggle-benchmarks/blob/ab291417d9a4c731ccfbfb03ac0b8316cb843683/src/kaggle_benchmarks/actors/llms.py)
- [Assertions](https://github.com/Kaggle/kaggle-benchmarks/blob/ab291417d9a4c731ccfbfb03ac0b8316cb843683/src/kaggle_benchmarks/assertions.py)
- [Runs](https://github.com/Kaggle/kaggle-benchmarks/blob/ab291417d9a4c731ccfbfb03ac0b8316cb843683/src/kaggle_benchmarks/runs.py)
- [Serialization](https://github.com/Kaggle/kaggle-benchmarks/blob/ab291417d9a4c731ccfbfb03ac0b8316cb843683/src/kaggle_benchmarks/kaggle/serialization.py)

For a future controlled Rosetta pilot, the starting evaluation defaults are:

```text
n_jobs=1
max_attempts=1
on_failure=continue
```

These defaults keep row order and failures legible. They do not guarantee
deterministic model output. In particular, current source removes `seed` for
some model families, including `openai/gpt-5.6`, and provider support for
temperature varies. The eventual receipt must record the exact available model
slug, SDK identity, reasoning setting, prompt and manifest digests, ordering,
token usage, latency, and errors.

Timeout is also not a process-kill boundary: the implementation can mark a
threaded call timed out while its thread continues. The first pilot therefore
keeps `n_jobs=1`, avoids automatic retry, and distinguishes infrastructure
failure from a completed but incorrect answer.

Rosetta scoring must use deterministic translation, compilation, execution,
and official tests. The SDK's custom assertion handler can preserve the
failure taxonomy. An LLM judge is not an acceptable substitute.

## Credential and environment boundary

No installation or Kaggle credential is required to retain this document. No
credential belongs in this repository.

The SDK configuration searches for a `.env` file and loads it with
`override=True`. A future run must therefore begin in a clean, explicitly
checked working directory and confirm that no repository or parent-directory
`.env` is being discovered. In particular, these values must never be committed
or printed:

```text
MODEL_PROXY_URL
MODEL_PROXY_API_KEY
MODEL_PROXY_EXPIRY_TIME
```

The repository's [`local_development.md`](https://github.com/Kaggle/kaggle-benchmarks/blob/ab291417d9a4c731ccfbfb03ac0b8316cb843683/local_development.md)
is expressly an internal Kaggle-team staging recipe. It is not the external
setup path for Hearthline.

Import without configured proxy credentials is not model access. The fallback
client is in-memory and does not establish persisted Kaggle runs or caching.
Likewise, package presence, schema tests, or a fake LLM are preparation checks,
not benchmark evidence.

## Kaggle effect gates

The official Kaggle CLI documentation used for these boundaries is pinned at
commit `db63063b817cfbc0abe0e001870edda462e569da`:

<https://github.com/Kaggle/kaggle-cli/blob/db63063b817cfbc0abe0e001870edda462e569da/docs/benchmarks.md>

Each operation below requires a fresh, explicit authorization. None is part of
this preparation branch:

| Gate | External or local effect |
| --- | --- |
| Install | Resolves and writes executable third-party code and dependencies. |
| `kaggle benchmarks auth` | Obtains a short-lived proxy credential and writes/appends `.env`. |
| `kaggle benchmarks init` | Authenticates and creates local benchmark material, including `.env`. |
| Task/data fetch | Contacts an upstream service and writes potentially large data. |
| `tasks run` | Schedules hosted model execution and consumes quota/cost. |
| `tasks push` | Creates or updates a Kaggle task/notebook. |
| `tasks publish` | Makes a task public and normally publishes its backing notebook. |

Publication is especially consequential: the documented CLI has no unpublish
operation, and task deletion is not presently supported through that workflow.
Preparation must never call publication as a verification step.

Kaggle-hosted leaderboards demonstrate that GPT-5.6 Sol has been run in some
Research Benchmarks. They do not establish that a new Community Benchmark or
this account can select it. Until a separately authorized, authenticated model
listing says otherwise, preserve:

```text
SOL_MODEL_AVAILABILITY_UNVERIFIED
MODEL_SLUG_UNRESOLVED
```

## Source-check and source-fetch contract

`tools/fetch_pinned_code.py` implements two visibly different interfaces:

- **Check-only:** `--check-only --cache <ABSOLUTE_CODE_CACHE>` validates the
  exact two code pins and inspects an already-present cache. It performs no
  network request and writes nothing, including when the cache is absent.
- **Explicit fetch:** `--fetch-code --cache <ABSOLUTE_APPROVED_CODE_CACHE>`
  requires the positive fetch flag and may clone only the two pinned public
  GitHub repositories after that action and destination are authorized.

The fetch interface must not default to this checkout, the Corpus USB/removable
workspace, a user home directory, or an unresolved environment variable. A
check-only success means only that the lock and any already-present checkout
are structurally acceptable; it never means `FETCHED`, `INSTALLED`, or
`RUN_COMPLETE`.
