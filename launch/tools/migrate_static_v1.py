#!/usr/bin/env python3
"""One-way converter for either legacy Spark Static v1 dialect."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from static_pair_v2 import StaticV2Error, migrate_v1_static


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        raw = args.source.read_bytes()
        value = json.loads(raw)
        result = migrate_v1_static(value, hashlib.sha256(raw).hexdigest())
    except (OSError, json.JSONDecodeError, StaticV2Error) as exc:
        raise SystemExit(f"migrate_static_v1: {exc}") from exc
    text = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
