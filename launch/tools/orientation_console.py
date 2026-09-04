#!/usr/bin/env python3
"""Retired public runner; retain only its deterministic policy for offline tests.

The former executable opened arbitrary ARC environments and selected actions.
Its 2026-09-03 grant is expired and spent. This successor imports no ARC
runtime, reads no environment variables, opens no network connection, and
writes no run artifact. The pure policy remains available for fixture tests and
historical replay analysis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any


OFFICIAL_REPOSITORY = "arcprize/ARC-AGI"
OFFICIAL_COMMIT = "f12822c4d550121c35a275008d964afbbed47d2f"
OFFICIAL_TREE = "9ee140e4183df0df109cec50b7cd0d2531c47168"
POLICY_ID = "hearthline-state-novelty-v0.1"
EXECUTION_STATUS = "RETIRED_OFFLINE_ONLY"

DIRECTION_ORDER = ["ACTION1", "ACTION4", "ACTION2", "ACTION3"]
SAFE_ORDER = DIRECTION_ORDER + ["ACTION5"]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def enum_name(value: Any) -> str:
    return str(getattr(value, "name", value))


def component_click_targets(summary: dict[str, Any]) -> list[dict[str, int]]:
    """Return deterministic, bounded component centroids for fixture analysis."""
    targets: list[tuple[int, int, int]] = []
    components = summary.get("components_4_neighbor", {})
    for color_text, items in components.items():
        try:
            color = int(color_text)
        except ValueError:
            color = 999
        for item in items:
            centroid = item.get("centroid", {})
            x = int(round(float(centroid.get("x", 31))))
            y = int(round(float(centroid.get("y", 31))))
            size = int(item.get("size", 0))
            targets.append((-size, color, y * 64 + x))

    out: list[dict[str, int]] = []
    seen: set[tuple[int, int]] = set()
    for _, _, packed in sorted(targets):
        x, y = packed % 64, packed // 64
        point = (max(0, min(63, x)), max(0, min(63, y)))
        if point not in seen:
            seen.add(point)
            out.append({"x": point[0], "y": point[1]})
    for point in ((31, 31), (16, 16), (47, 16), (16, 47), (47, 47)):
        if point not in seen:
            out.append({"x": point[0], "y": point[1]})
    return out


@dataclass
class EffectStats:
    attempts: int = 0
    material_changes: int = 0
    total_changed_cells: int = 0
    terminal_changes: int = 0

    @property
    def yield_rate(self) -> float:
        return self.material_changes / self.attempts if self.attempts else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempts": self.attempts,
            "material_changes": self.material_changes,
            "yield_rate": self.yield_rate,
            "total_changed_cells": self.total_changed_cells,
            "terminal_changes": self.terminal_changes,
        }


@dataclass
class PolicyState:
    seed: int
    tried_by_state: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    state_visits: Counter[str] = field(default_factory=Counter)
    action_stats: dict[str, EffectStats] = field(default_factory=lambda: defaultdict(EffectStats))
    click_index_by_state: dict[str, int] = field(default_factory=dict)
    transition_stack: list[tuple[str, str, str]] = field(default_factory=list)
    recent_states: deque[str] = field(default_factory=lambda: deque(maxlen=12))
    calibration_cursor: int = 0


class StateNoveltyPolicy:
    """Pure deterministic explorer; it has no authority or effect adapter."""

    def __init__(self, seed: int) -> None:
        self.state = PolicyState(seed=seed)
        self.random = random.Random(seed)

    @staticmethod
    def _available_map(env: Any) -> dict[str, Any]:
        return {enum_name(action): action for action in env.action_space}

    def choose(
        self,
        env: Any,
        response: Any,
        summary: dict[str, Any],
        state_id: str,
    ) -> tuple[Any, dict[str, Any], dict[str, Any]] | None:
        del response
        available = self._available_map(env)
        if not available:
            return None

        self.state.state_visits[state_id] += 1
        self.state.recent_states.append(state_id)
        tried = self.state.tried_by_state[state_id]

        for index in range(self.state.calibration_cursor, len(SAFE_ORDER)):
            name = SAFE_ORDER[index]
            self.state.calibration_cursor = index + 1
            if name in available and name not in tried:
                tried.add(name)
                return available[name], {}, {
                    "phase": "CALIBRATION",
                    "reason": f"first declared fixture probe of {name}",
                    "expected_change": "unknown",
                }

        if "ACTION6" in available:
            targets = component_click_targets(summary)
            click_index = self.state.click_index_by_state.get(state_id, 0)
            while click_index < len(targets):
                data = targets[click_index]
                key = f"ACTION6:{data['x']}:{data['y']}"
                click_index += 1
                self.state.click_index_by_state[state_id] = click_index
                if key not in tried:
                    tried.add(key)
                    return available["ACTION6"], data, {
                        "phase": "INVESTIGATION",
                        "reason": "unseen stable component centroid in an offline fixture",
                        "expected_change": "unknown",
                    }

        ordinary = [name for name in SAFE_ORDER if name in available]
        untried = [name for name in ordinary if name not in tried]
        if untried:
            name = min(
                untried,
                key=lambda item: (
                    -self.state.action_stats[item].yield_rate,
                    self.state.action_stats[item].attempts,
                    SAFE_ORDER.index(item),
                ),
            )
            tried.add(name)
            return available[name], {}, {
                "phase": "INVESTIGATION",
                "reason": "untested action in this fixture state",
                "expected_change": "unknown",
            }

        if "ACTION7" in available and "ACTION7" not in tried:
            tried.add("ACTION7")
            return available["ACTION7"], {}, {
                "phase": "PRESSURE",
                "reason": "fixture undo candidate after local probes",
                "expected_change": "material",
            }

        if ordinary:
            def rank(name: str) -> tuple[float, int, int, str]:
                stats = self.state.action_stats[name]
                tie = sha256_bytes(f"{self.state.seed}:{state_id}:{name}".encode())
                return (-stats.yield_rate, stats.attempts, SAFE_ORDER.index(name), tie)

            name = min(ordinary, key=rank)
            return available[name], {}, {
                "phase": "PRESSURE",
                "reason": "best prior fixture yield after local probes",
                "expected_change": "material" if self.state.action_stats[name].yield_rate else "unknown",
            }
        return None

    def observe(
        self,
        before_state: str,
        after_state: str,
        action_name: str,
        changed_cells: int,
        terminal_changed: bool,
    ) -> None:
        stats = self.state.action_stats[action_name]
        stats.attempts += 1
        stats.total_changed_cells += changed_cells
        if changed_cells > 0 or before_state != after_state or terminal_changed:
            stats.material_changes += 1
        if terminal_changed:
            stats.terminal_changes += 1
        if before_state != after_state:
            self.state.transition_stack.append((before_state, action_name, after_state))

    def world_model(self) -> dict[str, Any]:
        return {
            "schema": "hearthline.arc3.offline-policy-summary.v2",
            "policy": POLICY_ID,
            "execution_status": EXECUTION_STATUS,
            "states_observed": len(self.state.state_visits),
            "action_effects": {
                name: self.state.action_stats[name].as_dict()
                for name in sorted(self.state.action_stats)
            },
            "recent_state_path": list(self.state.recent_states),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explain", action="store_true", help="print the retirement manifest")
    parser.parse_args()
    print(json.dumps({
        "schema": "hearthline.arc3.retired-runner.v2",
        "status": EXECUTION_STATUS,
        "policy": POLICY_ID,
        "successor": "No orientation executor is currently authorized.",
        "claim_ceiling": "Pure fixture policy only; no environment contact or action authority.",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
