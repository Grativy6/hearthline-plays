# Public ARC-AGI-3 orientation runbook

This runbook performs a bounded provider-independent practice session against the public ARC surface. It is not the ARC-AGI-3 model benchmark harness, a Kaggle notebook, a competition submission, or a paid model call.

## 1. Freeze the workspaces

From a clean parent directory:

```bash
git clone \
  --branch arc-agi/titles/arc-agi-3-hearthline-launch-20260903 \
  --single-branch \
  https://github.com/Grativy6/hearthline-plays.git

cd hearthline-plays

git clone \
  --no-checkout \
  https://github.com/arcprize/ARC-AGI.git \
  .work/ARC-AGI

git -C .work/ARC-AGI checkout \
  f12822c4d550121c35a275008d964afbbed47d2f

git -C .work/ARC-AGI status --short
git -C .work/ARC-AGI rev-parse HEAD
```

The expected official commit is:

```text
f12822c4d550121c35a275008d964afbbed47d2f
```

Do not substitute a moving `main` branch without reopening [`../research/official-surfaces.lock.json`](../research/official-surfaces.lock.json).

## 2. Create an isolated environment

The pinned public toolkit declares Python 3.12 or newer.

Using `uv`:

```bash
uv venv --python 3.12 .venv-arc-public
source .venv-arc-public/bin/activate       # POSIX
# .venv-arc-public\Scripts\Activate.ps1    # PowerShell
uv pip install -e .work/ARC-AGI
```

Using standard `venv`:

```bash
python3.12 -m venv .venv-arc-public
source .venv-arc-public/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .work/ARC-AGI
```

No model-provider key is required by `orientation_console.py`. The official public toolkit may request an anonymous ARC key for its public remote route. The runner suppresses that value and never writes it.

## 3. Verify the launch kit without network contact

```bash
python -m unittest discover -s launch/tests -p 'test_*.py'
python -m py_compile launch/tools/*.py
python -m json.tool launch/research/official-surfaces.lock.json >/dev/null
python -m json.tool launch/schemas/spark-static.v1.schema.json >/dev/null
python -m json.tool launch/schemas/pair-static.v1.schema.json >/dev/null
python -m json.tool launch/schemas/orientation-receipt.v1.schema.json >/dev/null
```

The runner refuses public contact unless the explicit contact flag is present:

```bash
python launch/tools/orientation_console.py --max-actions 0
# expected: refusal before contact
```

## 4. Calibration run

```bash
python launch/tools/orientation_console.py \
  --allow-public-contact \
  --game-id ls20 \
  --seed 0 \
  --max-actions 12 \
  --max-resets 1 \
  --max-wall-seconds 900 \
  --print-events
```

Expected local output:

```text
launch/runs/orientation-YYYY-MM-DD-*/
├── events.jsonl
├── heartbeat.json
├── official-recordings/
├── receipt.json
└── world-model.json
```

The `launch/runs/` directory is ignored. Review before publishing any artifact.

## 5. Investigation run

Only after the calibration receipt is readable:

```bash
python launch/tools/orientation_console.py \
  --allow-public-contact \
  --game-id ls20 \
  --seed 0 \
  --max-actions 48 \
  --max-resets 2 \
  --max-wall-seconds 3600 \
  --print-events
```

This policy performs deterministic state-novelty exploration. It is intentionally modest: it records available controls, exact frame changes, state revisits, and action-yield statistics. It does not pretend to be a visual foundation model or the provider-adapter system described in public GPT-6 Astra analysis.

## 6. Inspect one frame or transition

Export a frame or frame envelope as JSON, then:

```bash
python launch/tools/frame_probe.py current-frame.json --output current-summary.json
python launch/tools/frame_probe.py current-frame.json \
  --previous previous-frame.json \
  --output transition-summary.json
```

The probe returns direct grid structure only. Semantic labels belong in Spark Static records.

## 7. Compile a paired comparison

Copy the blank templates and fill two separately identified same-task records:

```bash
cp launch/templates/spark-static.blank.json /tmp/static-a.json
cp launch/templates/spark-static.blank.json /tmp/static-b.json

python launch/tools/static_pair.py \
  /tmp/static-a.json \
  /tmp/static-b.json \
  --pair-id pair-0001 \
  --pair-static-id pair-static-0001 \
  --output /tmp/pair-static-0001.json
```

The compiler keeps both source identities, uses `pooling_rule: NONE`, and never dispatches the recommended action.

## 8. Sanitized publication checklist

Before committing a run receipt:

- remove API keys, cookies, headers, scorecard tokens, and server-issued anonymous identifiers;
- do not publish private or competition-only frames;
- retain exact public source commit and configuration;
- report actual action, reset, call, wall-time, and cost counts;
- distinguish environment contact from a completed run;
- distinguish `WIN_OBSERVED`, `NO_WIN_OBSERVED`, and `UNRESOLVED`;
- preserve failure and partial receipts rather than editing them into success; and
- state that a public result grants no Kaggle or competition authority.

A sanitized receipt may be copied into a later `launch/receipts/` successor directory after review. Raw recordings remain local by default.

## 9. Stop and reopen

Stop immediately when a credential, paid API, private artifact, competition mode, Kaggle submission, uncertain irreversible effect, or changed official interface appears. Preserve the receipt and reopen at the earliest changed boundary.

When no material change occurs and no authorized next action remains:

```text
heartbeat() -> ``
```

The empty beat records a safe suspension point. It does not claim unseen work or keep a process alive.
