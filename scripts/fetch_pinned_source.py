#!/usr/bin/env python3
"""Fetch and verify the two pinned public Kaggriculture referee files.

No credential is required. The files are downloaded from the exact public commit
recorded by Build 001 and admitted only when their Git blob identities match the
source lock.
"""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
BASE = f"https://raw.githubusercontent.com/Kaggle/kaggle-environments/{COMMIT}/kaggle_environments/envs/kaggriculture"
FILES = {
    "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
}


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def main() -> int:
    package = ROOT / "vendor" / "kaggle_environments"
    target = package / "envs" / "kaggriculture"
    target.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text('"""Minimal local namespace for the pinned referee."""\n', encoding="utf-8")
    (package / "envs" / "__init__.py").write_text("", encoding="utf-8")
    (target / "__init__.py").write_text("", encoding="utf-8")
    # The pinned interpreter imports only resolve_episode_seed from upstream utils.
    (package / "utils.py").write_text(
        '"""Minimal seed compatibility for the pinned Kaggriculture interpreter."""\n'
        'from __future__ import annotations\n\n'
        'import random\nfrom typing import Any\n\n'
        'def resolve_episode_seed(env: Any, *, config_key: str = "seed", info_key: str = "seed") -> int:\n'
        '    configured = getattr(env.configuration, config_key, None)\n'
        '    seed = int(configured) if configured is not None else random.SystemRandom().randrange(0, 2**31)\n'
        '    env.info[info_key] = seed\n'
        '    try:\n        del env.configuration[config_key]\n    except Exception:\n        pass\n'
        '    return seed\n',
        encoding="utf-8",
    )

    for name, expected in FILES.items():
        with urllib.request.urlopen(f"{BASE}/{name}", timeout=60) as response:
            data = response.read()
        observed = git_blob_sha1(data)
        if observed != expected:
            raise SystemExit(f"{name}: expected {expected}, observed {observed}")
        (target / name).write_bytes(data)
        print(f"verified {name} {observed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
