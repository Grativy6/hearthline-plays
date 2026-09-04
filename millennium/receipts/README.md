# Receipt ledger

Receipts are append-only claim and provenance events.

- JSON is the machine-readable authority.
- A paired Markdown file may explain the same event to humans.
- Corrections name the superseded receipt and append a successor; they do not
  replace history.
- Event IDs content-address canonical receipt payloads. A Git commit identifies
  repository bytes. Human signatures and trusted time evidence, when
  available, append as separate sidecars under `attestations/`; they must not
  be fabricated or inserted into old receipts.
- Private reveal material stays outside this directory and outside Git.

The founding event is
[`20260904T073424Z-genesis.json`](20260904T073424Z-genesis.json).
The first finite game event is
[`20260904T074434Z-pnp-circuit-garden.json`](20260904T074434Z-pnp-circuit-garden.json).
