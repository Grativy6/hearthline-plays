"""Small human-readable views over canonical simulator snapshots."""
from __future__ import annotations

from typing import Any


def _count_tiles(farm: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {"empty": 0, "locked": 0, "weed": 0}
    for row in farm.get("tiles", []):
        for tile in row:
            if tile is None:
                out["empty"] += 1
            elif tile == "LOCKED":
                out["locked"] += 1
            elif isinstance(tile, dict):
                if tile.get("kind") == "WEED":
                    out["weed"] += 1
                elif tile.get("kind") == "PLANT":
                    key = str(tile.get("crop", "plant")).lower()
                    out[key] = out.get(key, 0) + 1
                elif "animal" in tile:
                    key = str(tile.get("animal", "animal")).lower()
                    out[key] = out.get(key, 0) + 1
                else:
                    key = str(tile.get("kind", "structure")).lower()
                    out[key] = out.get(key, 0) + 1
    return {k: v for k, v in out.items() if v}


def day_report(snapshot: dict[str, Any], player: int) -> str:
    farm = snapshot["farms"][player]
    private = snapshot["privates"][player]
    shed = {k: v for k, v in private.get("shed", {}).items() if v}
    seeds = {k: v for k, v in private.get("seeds", {}).items() if v}
    tile_counts = _count_tiles(farm)
    shops = snapshot.get("town", {}).get("unlocked_shops", [])
    return (
        f"Day {snapshot.get('day', 0):02d} · ${farm.get('money', 0):.0f} · "
        f"tiles {tile_counts} · shed {shed or '{}'} · seeds {seeds or '{}'} · "
        f"shops {shops or '[]'}"
    )


def campaign_markdown(snapshots: list[dict[str, Any]], player: int, title: str) -> str:
    lines = [f"# {title}", "", "Canonical state remains the replay; this is a compact derived view.", ""]
    for snapshot in snapshots:
        lines.append(day_report(snapshot, player))
    lines.append("")
    return "\n".join(lines)
