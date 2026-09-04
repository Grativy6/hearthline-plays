#!/usr/bin/env python3
"""Read-only suitability check for a future Biohub competition data home."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import shutil
import sys
from typing import Callable, Iterable, Sequence


GIB = 1024**3
WINDOWS_DRIVE_TYPES = {
    0: "unknown",
    1: "invalid",
    2: "removable",
    3: "fixed",
    4: "remote",
    5: "optical",
    6: "ramdisk",
}


class DataHomeError(ValueError):
    """Raised when a data-home path cannot be assessed safely."""


@dataclass(frozen=True)
class VolumeInfo:
    mount: str
    filesystem: str
    drive_type: str
    free_bytes: int


def nearest_existing_parent(path: Path) -> Path:
    """Return *path* or its nearest existing parent without creating anything."""

    candidate = path
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            raise DataHomeError(f"no existing parent can be inspected for {path}")
        candidate = parent
    if not candidate.is_dir():
        candidate = candidate.parent
    return candidate


def _contains(parent: Path, child: Path) -> bool:
    """Case-normalized containment check that also works across Windows drives."""

    parent_text = os.path.normcase(str(parent))
    child_text = os.path.normcase(str(child))
    try:
        return os.path.commonpath((parent_text, child_text)) == parent_text
    except ValueError:
        return False


def _windows_volume_info(path: Path) -> VolumeInfo:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    get_volume_path_name = kernel32.GetVolumePathNameW
    get_volume_path_name.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    get_volume_path_name.restype = wintypes.BOOL
    get_volume_information = kernel32.GetVolumeInformationW
    get_volume_information.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    get_volume_information.restype = wintypes.BOOL
    get_drive_type = kernel32.GetDriveTypeW
    get_drive_type.argtypes = [wintypes.LPCWSTR]
    get_drive_type.restype = wintypes.UINT

    volume_path = ctypes.create_unicode_buffer(32768)
    if not get_volume_path_name(str(path), volume_path, len(volume_path)):
        raise OSError(ctypes.get_last_error(), f"GetVolumePathNameW failed for {path}")

    filesystem = ctypes.create_unicode_buffer(256)
    if not get_volume_information(
        volume_path.value,
        None,
        0,
        None,
        None,
        None,
        filesystem,
        len(filesystem),
    ):
        raise OSError(
            ctypes.get_last_error(),
            f"GetVolumeInformationW failed for {volume_path.value}",
        )

    drive_code = int(get_drive_type(volume_path.value))
    free_bytes = shutil.disk_usage(path).free
    return VolumeInfo(
        mount=volume_path.value,
        filesystem=filesystem.value.upper(),
        drive_type=WINDOWS_DRIVE_TYPES.get(drive_code, f"windows-code-{drive_code}"),
        free_bytes=free_bytes,
    )


def probe_volume(path: Path) -> VolumeInfo:
    """Inspect the volume containing an existing path without modifying it."""

    if os.name == "nt":
        return _windows_volume_info(path)
    usage = shutil.disk_usage(path)
    return VolumeInfo(
        mount=path.anchor or "/",
        filesystem="UNKNOWN",
        drive_type="unknown",
        free_bytes=usage.free,
    )


def assess_data_home(
    proposed: Path,
    *,
    repo_root: Path,
    min_free_gib: float = 200.0,
    acknowledge_removable: bool = False,
    forbidden_roots: Iterable[Path] = (),
    forbid_repo_volume: bool = True,
    volume_probe: Callable[[Path], VolumeInfo] = probe_volume,
) -> dict[str, object]:
    """Return a deterministic report; this function never creates the path."""

    if not math.isfinite(min_free_gib) or min_free_gib <= 0:
        raise DataHomeError("minimum free GiB must be finite and greater than zero")

    proposed = proposed.expanduser().resolve(strict=False)
    repo_root = repo_root.expanduser().resolve(strict=True)
    inspected_path = nearest_existing_parent(proposed).resolve(strict=True)
    volume = volume_probe(inspected_path)
    errors: list[str] = []

    roots = list(forbidden_roots or ())
    # The station must not place the dataset anywhere on the repository's
    # current Windows volume (E: in the prepared branch). Additional CLI roots
    # are additive and cannot disable this invariant.
    if forbid_repo_volume and os.name == "nt":
        roots.insert(0, Path(repo_root.anchor))
    resolved_forbidden = [root.expanduser().resolve(strict=False) for root in roots]

    # Reject both directions. A child would put data in Git; a broad ancestor
    # (for example E:\) could accidentally encompass the repository itself.
    if _contains(repo_root, proposed) or _contains(proposed, repo_root):
        errors.append("data home must be wholly separate from the repository")
    if proposed.exists() and not proposed.is_dir():
        errors.append("data home path exists but is not a directory")
    for forbidden in resolved_forbidden:
        if _contains(forbidden, proposed):
            errors.append(f"data home is on forbidden root {forbidden}")
            break

    filesystem = volume.filesystem.strip().upper()
    if filesystem in {"FAT", "FAT32"}:
        errors.append(f"filesystem {filesystem} is not suitable for competition data")

    if os.name == "nt" or volume.drive_type != "unknown":
        if volume.drive_type not in {"fixed", "removable"}:
            errors.append(f"drive type {volume.drive_type!r} is not an approved data volume")
        elif volume.drive_type == "removable" and not acknowledge_removable:
            errors.append(
                "removable storage requires the explicit --allow-removable flag"
            )

    required_bytes = math.ceil(min_free_gib * GIB)
    if volume.free_bytes < required_bytes:
        errors.append(
            f"only {volume.free_bytes / GIB:.2f} GiB free; {min_free_gib:g} GiB required"
        )

    return {
        "schema_version": "1.0",
        "accepted": not errors,
        "proposed_path": str(proposed),
        "proposed_path_exists": proposed.exists(),
        "inspected_existing_path": str(inspected_path),
        "minimum_free_gib": min_free_gib,
        "acknowledge_removable": acknowledge_removable,
        "forbidden_roots": [str(root) for root in resolved_forbidden],
        "volume": {
            **asdict(volume),
            "free_gib": round(volume.free_bytes / GIB, 3),
        },
        "errors": errors,
        "read_only": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="proposed data-home directory")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--min-free-gib", type=float, default=200.0)
    parser.add_argument(
        "--allow-removable",
        "--acknowledge-removable",
        dest="acknowledge_removable",
        action="store_true",
        help="explicitly acknowledge use of a suitable removable volume",
    )
    parser.add_argument(
        "--forbid-root",
        action="append",
        type=Path,
        default=None,
        help="add another rejected root (repeatable; repository volume is always rejected)",
    )
    parser.add_argument("--json", action="store_true", help="emit the full JSON report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = assess_data_home(
            args.path,
            repo_root=args.repo_root,
            min_free_gib=args.min_free_gib,
            acknowledge_removable=args.acknowledge_removable,
            forbidden_roots=args.forbid_root,
        )
    except (DataHomeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report["accepted"]:
        volume = report["volume"]
        assert isinstance(volume, dict)
        print(
            "PASS: suitable data home "
            f"({volume['filesystem']}, {volume['drive_type']}, {volume['free_gib']} GiB free)"
        )
    else:
        for error in report["errors"]:
            print(f"FAIL: {error}", file=sys.stderr)
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
