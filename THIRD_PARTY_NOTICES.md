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

The current source identities and reviewed runtime closure are frozen in
[`launch/source-lock.v4.json`](launch/source-lock.v4.json); its byte-preserved
predecessor remains `launch/source-lock.v3.json`. The public source pin retains
`arcprize/ARC-AGI-3-Agents` commit
`4743e7d0aaae0ded0d98a89a7e282e63564cd58b`, where `agents/agent.py` has
SHA-256 `49f1a349cd5e2123fceb266aec4a3a758d18ef5520e0212e808f695905d9e073`.
The candidate does not vendor those framework sources. One exact,
non-executable copy of pinned
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

Separately, the reviewed private kernel version-4 evidence recorded the Kaggle
platform's admitted runtime files. Those six paths match official historical
Agents commit `135f20aaf44f13341ebc425666bf03b5cac58d3c` (tree
`d7fbafe6e2ed191189db89e5b571fd26da3dc375`); its `agents/agent.py` SHA-256 is
`85655f7a11a105e50bba76efd00bebf8056d02ddbae827a8f8a5b46e849fc087`.
The other four executable hashes and the MIT `LICENSE` hash match the public
pin. This is a bounded provenance match for the five observed executable paths
plus `LICENSE`, not a claim that unobserved Kaggle platform files reproduce the
entire historical tree. Likewise, the reviewed Kaggle distribution
`arc-agi==0.9.8` remains distinct from the retained public ARC-AGI 0.9.9 source
identity; neither is reattributed to or substituted for the other.

ARC Prize, ARC-AGI, Kaggle, and related names may be trademarks of their
respective owners. Compatibility, inspection, and participation do not imply
endorsement. Before any later redistribution of third-party bytes, a human
must inspect the then-current terms and record the applicable permission.
