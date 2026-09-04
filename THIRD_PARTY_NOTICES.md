# Third-party source and compatibility notices

This repository's first-party text and code are offered under the root
[`LICENSE`](LICENSE). That license applies only to material Christopher D. Pang
has authority to license. Project names, service names, competition materials,
and third-party software retain their owners' rights and terms.

## ARC-AGI-3 Kaggle starter

The public repository `arcprize/ARC-AGI-3-Kaggle-Starter` was inspected at
commit `eeb1535404f321d280a8f9194bbc1d7aca5f05fc` (tree
`332ff438d9b092c95e58a07eace6194379de06b4`). No `LICENSE` or `NOTICE` file
was present in that pinned tree when inspected. This record therefore does not
infer or claim an upstream license grant.

No upstream starter file is vendored here. The local notebook builder is an
independently structured implementation informed by the starter's public
interoperability contract: notebook cell roles, package names, fixed
competition paths, framework registry names, gateway environment fields, the
rerun signal, and the required `submission.parquet` output. Those necessary
functional names and values are acknowledged rather than described as wholly
unrelated work. The frozen structural comparison is recorded in
[`launch/contracts/official-starter-eeb153.contract.json`](launch/contracts/official-starter-eeb153.contract.json).

## ARC-AGI toolkit, Agents framework, and Kaggle

The source identities inspected for compatibility are frozen in
[`launch/source-lock.v3.json`](launch/source-lock.v3.json). The candidate does
not vendor those framework sources. One exact, non-executable copy of pinned
Agents `main.py` is retained as
[`tests/fixtures/agents-main-4743e7d0.blob`](tests/fixtures/agents-main-4743e7d0.blob)
solely so offline tests can recompute the Git-blob/SHA-256 pairing and catch
line-ending transformations. It is redistributed under the pinned tree's MIT
license, reproduced at
[`tests/fixtures/ARC-AGI-3-Agents-LICENSE.txt`](tests/fixtures/ARC-AGI-3-Agents-LICENSE.txt).

The pinned `arcprize/ARC-AGI-3-Agents` tree contains an MIT `LICENSE` file:
Git blob `d8e1cd42ac40338c6c76a8a6ac18eea0eaf95fbe`, SHA-256
`75c4276c506fd93082b38ad39f67ee97aa859574401ef978e701710c7a40af04`,
with the notice “Copyright (c) 2025 ARC Prize.” During an authorized competition
rerun, Kaggle supplies the competition wheelhouse and Agents framework as
platform inputs; this candidate refers to and copies that platform-provided
framework—including its `LICENSE` file—into the notebook's writable runtime as
the official interface expects. The local registry and candidate agent are then
written in that runtime copy. Except for the disclosed test fixture above, this
repository does not copy those upstream bytes or make them first-party
material.

ARC Prize, ARC-AGI, Kaggle, and related names may be trademarks of their
respective owners. Compatibility, inspection, and participation do not imply
endorsement. Before any later redistribution of third-party bytes, a human
must inspect the then-current terms and record the applicable permission.
