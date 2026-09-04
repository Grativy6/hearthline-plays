# Run receipt — PNP circuit garden N2 NAND

- **Receipt:** `MILLENNIUM-RUN-20260904T074434Z-PNP-NAND-N2`
- **Run time:** `2026-09-04T07:44:34Z`
- **Claim state:** `certified_finite`

The first public Playground move exhaustively enumerated every topologically
ordered two-input NAND circuit through five gates under the declared model.
At the five-gate layer it checked 56,700 circuit sequences. Together with the
smaller layers, this covers every circuit of the tested sizes, up to the
commutativity normalization of each NAND gate's two inputs.

All 16 Boolean functions of two variables were reached. Their exact minimum
NAND-gate counts in this model are:

| Gates | Functions |
| ---: | --- |
| 0 | `x0`, `x1` |
| 1 | `not_x0`, `not_x1`, `nand` |
| 2 | `and`, `true`, `x0_implies_x1`, `x1_implies_x0` |
| 3 | `false`, `not_x0_and_x1`, `x0_and_not_x1`, `or` |
| 4 | `nor`, `xor` |
| 5 | `xnor` |

The certificate contains a witness circuit for every function. Re-running the
enumerator reproduces the complete search and rejects any semantic alteration
to the certificate data:

```bash
python3 millennium/games/p-vs-np/circuit_garden.py \
  --verify millennium/games/p-vs-np/certificate-n2-nand.json
```

This proves only the finite statement above. It is neither evidence for
`P = NP` nor evidence for `P != NP`, and it is not an asymptotic circuit lower
bound.
