# Arena GEO — control before frontier

**Genesis state:** `SCOPE_SPLIT`

“Geometry” is not silently equated with one Millennium problem. This arena
has two visibly separate lanes.

## Lane A: Poincare control game

The Poincare conjecture is solved. It is a calibration lane in which the
workflow may rediscover finite invariants, reproduce known examples, and test
whether Builder/Hunter receipts preserve topology correctly.

The first board is a finite triangulated closed surface, not a 3-manifold
proof:

| Part | Arena binding |
| --- | --- |
| Board | A finite simplicial complex promised to triangulate a connected closed surface |
| Builder | Computes vertices, edges, faces, Euler characteristic, orientability data, and a classification candidate |
| Hunter | Searches for malformed incidence, boundary, disconnectedness, nonmanifold links, or a conflicting invariant |
| Verifier | Exact integer incidence and homology calculations with a replayable fixture |
| Win | A correct finite classification certificate or an explicit promise violation |

This lane may reach `reproduced` or `certified_finite`. It cannot generate a
new Poincare solution claim, and pretrained familiarity prevents calling a
matching argument an independent rediscovery without stronger evidence.

## Lane B: Hodge frontier

The open geometry target selected for later play is the **rational** Hodge
conjecture for smooth projective complex algebraic varieties. The integral
version is false, so a receipt that drops “rational” fails at binding time.

This lane remains `UNOPENED` at genesis. Before its first run it requires:

1. a domain expert or authoritative source map for the chosen variety class;
2. exact definitions of the cohomology, Hodge class, and cycle-class map;
3. a finite representation and verifier whose result has an explicit ceiling;
4. a statement of why the chosen class is not being generalized silently.

Promising early boards include very restricted variety classes with known
answers, used as controls. Finite examples do not show that every rational
Hodge class lies in the image of the rational cycle-class map.

**Locked control source:** `clay:poincare:official-description:2022-bytes`

**Locked frontier source:** `clay:hodge:official-description:2022-bytes`
