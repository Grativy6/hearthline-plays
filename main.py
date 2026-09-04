"""Hearthline Farm Build 001 competition entry point.

The policy is deterministic, observation-only, and uses no model inference at runtime.
It deliberately starts small: sixteen nearby plots, cheap daily labor, melon cycles,
a late carrot cycle, continuous care, and prompt liquidation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

# Public values from the pinned Kaggriculture 0.1.0 source.
CROPS: dict[str, dict[str, Any]] = {
    "WHEAT": {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "max_yield": 6, "ongoing": False},
    "CARROT": {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "max_yield": 4, "ongoing": False},
    "TOMATO": {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "max_yield": 4, "ongoing": True},
    "MELON": {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "max_yield": 6, "ongoing": False},
}

SELLABLE = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")
MOVES = {
    (1, 0): "EAST",
    (-1, 0): "WEST",
    (0, 1): "SOUTH",
    (0, -1): "NORTH",
}

# Sixteen plots in the unlocked NW quadrant, close enough for a farmer plus five
# cheap daily hands to service reliably.  The center-adjacent tile (4, 4) is
# intentionally included; standing there can still access the shed.
PLOTS: tuple[tuple[int, int], ...] = tuple(
    (x, y)
    for y in range(1, 5)
    for x in (4, 3, 2, 1) if y % 2 == 1
) + tuple(
    (x, y)
    for y in range(1, 5)
    for x in (1, 2, 3, 4) if y % 2 == 0
)

# The comprehension above produces row-paired ordering.  Preserve one instance
# of each coordinate in deterministic order.
PLOTS = tuple(dict.fromkeys(PLOTS))
DESIRED_HANDS = 5
LAST_MELON_PLANT_DAY = 16
LAST_CARROT_PLANT_DAY = 23


@dataclass(frozen=True)
class Task:
    priority: int
    x: int
    y: int
    action: tuple[Any, ...]
    reason: str

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)


def _pass_action(hand_count: int = 0) -> dict[str, Any]:
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hand_count)], "market": []}


def _desired_crop(day: int) -> str | None:
    if day <= LAST_MELON_PLANT_DAY:
        return "MELON"
    if day <= LAST_CARROT_PLANT_DAY:
        return "CARROT"
    return None


def _owned(tile: Any) -> bool:
    return tile != "LOCKED"


def _make_tasks(obs: dict[str, Any], farm: dict[str, Any], private: dict[str, Any]) -> list[Task]:
    day = int(obs.get("day", 0))
    desired = _desired_crop(day)
    seeds_remaining = int((private.get("seeds") or {}).get(desired, 0)) if desired else 0
    tasks: list[Task] = []

    for plot_rank, (x, y) in enumerate(PLOTS):
        tile = farm["tiles"][y][x]
        if not _owned(tile):
            continue

        if tile is None:
            if desired and seeds_remaining > 0:
                tasks.append(Task(60 + plot_rank, x, y, ("PLANT", desired), f"plant {desired.lower()}"))
                seeds_remaining -= 1
            continue

        if not isinstance(tile, dict):
            continue

        kind = tile.get("kind")
        if kind == "WEED":
            tasks.append(Task(12 + plot_rank, x, y, ("DIG",), "clear weed"))
            continue

        if kind != "PLANT":
            continue

        crop = str(tile.get("crop", ""))
        cd = CROPS.get(crop)
        if not cd:
            continue

        age = day - int(tile.get("planted_day", day))
        watered = bool(tile.get("watered_today", False))
        consecutive_unwatered = int(tile.get("consecutive_unwatered", 0))
        yield_units = int(tile.get("yield_units", 0))

        # Basic care outranks profit.  A planting begins with one unwatered mark,
        # so same-day watering is urgent.  At max-yield day, take one final bonus
        # watering before harvest when it can still increase the crop.
        can_bonus_now = (
            not cd["ongoing"]
            and age >= (int(cd["max_yield_day"]) + 1) // 2
            and age <= int(cd["max_yield_day"])
            and yield_units < int(cd["max_yield"])
        )
        if not watered and (consecutive_unwatered >= 1 or can_bonus_now):
            tasks.append(Task(0 + plot_rank, x, y, ("WATER",), "prevent loss / earn yield"))
            continue

        harvestable = age >= int(cd["first_yield_day"]) and yield_units > 0
        at_or_past_max = age >= int(cd["max_yield_day"])
        full_yield = yield_units >= int(cd["max_yield"])
        if harvestable and (full_yield or at_or_past_max):
            tasks.append(Task(25 + plot_rank, x, y, ("HARVEST",), "harvest before decay"))
            continue

        if not watered:
            tasks.append(Task(8 + plot_rank, x, y, ("WATER",), "daily care"))

    return sorted(tasks, key=lambda t: (t.priority, t.y, t.x, t.action))


def _distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _move_toward(src: tuple[int, int], dst: tuple[int, int], unit_index: int) -> list[str]:
    sx, sy = src
    dx, dy = dst
    # Alternate axis preference by unit index to reduce bunching while staying
    # fully deterministic.  Locked tiles are traversable in the official world.
    horizontal_first = (unit_index % 2 == 0)
    candidates: list[tuple[int, int]] = []
    if horizontal_first:
        if dx != sx:
            candidates.append((1 if dx > sx else -1, 0))
        if dy != sy:
            candidates.append((0, 1 if dy > sy else -1))
    else:
        if dy != sy:
            candidates.append((0, 1 if dy > sy else -1))
        if dx != sx:
            candidates.append((1 if dx > sx else -1, 0))
    return [MOVES[candidates[0]]] if candidates else ["PASS"]


def _assign_actions(positions: list[tuple[int, int]], tasks: list[Task]) -> list[list[Any]]:
    actions: list[list[Any]] = [["PASS"] for _ in positions]
    free_units = set(range(len(positions)))
    remaining = list(tasks)

    # First take exact-position work.  This prevents a worker standing on an
    # urgent crop from walking away because another task has a slightly lower id.
    for task in list(remaining):
        colocated = [u for u in free_units if positions[u] == task.pos]
        if not colocated:
            continue
        unit = min(colocated)
        actions[unit] = list(task.action)
        free_units.remove(unit)
        remaining.remove(task)

    # Globally greedy assignment by priority, then travel distance.  Each task is
    # unique and each unit receives at most one target this turn.
    while free_units and remaining:
        best: tuple[int, int, int, int, Task] | None = None
        for unit in free_units:
            for task_index, task in enumerate(remaining):
                key = (task.priority, _distance(positions[unit], task.pos), unit, task_index, task)
                if best is None or key[:4] < best[:4]:
                    best = key
        assert best is not None
        _, _, unit, task_index, task = best
        actions[unit] = _move_toward(positions[unit], task.pos, unit)
        free_units.remove(unit)
        remaining.pop(task_index)

    return actions


def _market_orders(obs: dict[str, Any], farm: dict[str, Any], private: dict[str, Any]) -> list[list[Any]]:
    orders: list[list[Any]] = []
    shed = private.get("shed") or {}
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))

    # Turn inventory into bank value promptly.  Sell orders are emitted before
    # purchases so endgame liquidation cannot be crowded out by the 10-order cap.
    for item in SELLABLE:
        n = int(shed.get(item, 0) or 0)
        if n > 0:
            orders.append(["SELL", item, n])

    # Hands are deliberately cheap and ephemeral.  Hire only once at the start
    # of each day, up to the transparent five-hand budget.
    if hour == 0:
        missing = max(0, DESIRED_HANDS - int(farm.get("hires_today", 0)))
        orders.extend([["HIRE"] for _ in range(missing)])

    desired = _desired_crop(day)
    if desired:
        seeds = int((private.get("seeds") or {}).get(desired, 0) or 0)
        empty = 0
        for x, y in PLOTS:
            tile = farm["tiles"][y][x]
            if tile is None:
                empty += 1
        need = max(0, empty - seeds)
        if need > 0:
            affordable = int(float(farm.get("money", 0)) // int(CROPS[desired]["seed"]))
            need = min(need, affordable)
            if need > 0:
                orders.append(["BUY_SEED", desired, need])

    return orders[:10]


def agent(obs: dict[str, Any]) -> dict[str, Any]:
    """Return one schema-shaped action from the supplied observation."""
    try:
        player = int(obs.get("player", 0))
        farms = obs.get("farms") or []
        if not farms or player < 0 or player >= len(farms):
            return _pass_action()
        farm = farms[player]
        private = obs.get("private") or {}
        hand_positions = [tuple(p) for p in (farm.get("hands") or [])]
        positions = [tuple(farm.get("farmer", (4, 4))), *hand_positions]
        tasks = _make_tasks(obs, farm, private)
        unit_actions = _assign_actions(positions, tasks)
        market = _market_orders(obs, farm, private)
        return {
            "farmer": unit_actions[0] if unit_actions else ["PASS"],
            "hands": unit_actions[1:],
            "market": market,
        }
    except Exception:
        # The competition boundary must always receive a valid fallback.  The
        # local harness records exceptions separately; runtime output stays safe.
        hand_count = 0
        try:
            farms = obs.get("farms") or []
            player = int(obs.get("player", 0))
            hand_count = len((farms[player].get("hands") or [])) if farms else 0
        except Exception:
            hand_count = 0
        return _pass_action(hand_count)
