#!/usr/bin/env python3
"""Run a bounded provider-independent orientation session on public ARC-AGI-3.

This is not a competition runner and does not call an LLM provider. It uses the
pinned public ``arcprize/ARC-AGI`` interface, a deterministic state-novelty
policy, compact frame diagnostics, and an append-only local event trail.

Network contact is refused unless ``--allow-public-contact`` is supplied.
Secrets and server-issued keys are never written by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import platform
import random
import sys
import time
import uuid
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from frame_probe import diff_grids, summarize_grid

OFFICIAL_REPOSITORY = "arcprize/ARC-AGI"
OFFICIAL_COMMIT = "f12822c4d550121c35a275008d964afbbed47d2f"
OFFICIAL_TREE = "9ee140e4183df0df109cec50b7cd0d2531c47168"
POLICY_ID = "hearthline-state-novelty-v0.1"

DIRECTION_ORDER = ["ACTION1", "ACTION4", "ACTION2", "ACTION3"]
SAFE_ORDER = DIRECTION_ORDER + ["ACTION5"]
OPPOSITE = {
    "ACTION1": "ACTION2",
    "ACTION2": "ACTION1",
    "ACTION3": "ACTION4",
    "ACTION4": "ACTION3",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(canonical_bytes(value) + b"\n")
    tmp.replace(path)


def append_jsonl(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(value)
    with path.open("ab") as handle:
        handle.write(payload + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    return sha256_bytes(payload)


def enum_name(value: Any) -> str:
    return str(getattr(value, "name", value))


def to_grid(response: Any) -> list[list[int]] | None:
    frames = getattr(response, "frame", None)
    if not frames:
        return None
    grid = frames[-1]
    if hasattr(grid, "tolist"):
        grid = grid.tolist()
    if not isinstance(grid, list) or not grid or not isinstance(grid[0], list):
        return None
    return [[int(cell) for cell in row] for row in grid]


def state_signature(response: Any, grid: list[list[int]] | None) -> str:
    value = {
        "state": enum_name(getattr(response, "state", "UNKNOWN")),
        "levels_completed": getattr(response, "levels_completed", None),
        "win_levels": getattr(response, "win_levels", None),
        "available_actions": sorted(str(item) for item in getattr(response, "available_actions", []) or []),
        "grid": grid,
    }
    return sha256_bytes(canonical_bytes(value))[:24]


def component_click_targets(summary: dict[str, Any]) -> list[dict[str, int]]:
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
    """A deterministic low-assumption explorer with explicit no-loop pressure."""

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
        available = self._available_map(env)
        if not available:
            return None

        self.state.state_visits[state_id] += 1
        self.state.recent_states.append(state_id)
        tried = self.state.tried_by_state[state_id]

        # First pass: each ordinary control once in a fixed orientation order.
        for index in range(self.state.calibration_cursor, len(SAFE_ORDER)):
            name = SAFE_ORDER[index]
            self.state.calibration_cursor = index + 1
            if name in available and name not in tried:
                tried.add(name)
                return available[name], {}, {
                    "phase": "CALIBRATION",
                    "reason": f"first declared probe of {name}",
                    "expected_change": "unknown",
                }

        # Clicks are explored by stable component centroids, never random pixels.
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
                        "reason": "probe an untested stable component centroid",
                        "expected_change": "unknown",
                    }

        ordinary = [name for name in SAFE_ORDER if name in available]
        untried = [name for name in ordinary if name not in tried]
        if untried:
            untried.sort(
                key=lambda name: (
                    -self.state.action_stats[name].yield_rate,
                    self.state.action_stats[name].attempts,
                    SAFE_ORDER.index(name),
                )
            )
            name = untried[0]
            tried.add(name)
            stats = self.state.action_stats[name]
            return available[name], {}, {
                "phase": "INVESTIGATION",
                "reason": "untested action in this exact visible state",
                "expected_change": "material" if stats.yield_rate >= 0.5 else "unknown",
            }

        # Prefer an explicit undo when the complete local action set was tested.
        if "ACTION7" in available and "ACTION7" not in tried:
            tried.add("ACTION7")
            return available["ACTION7"], {}, {
                "phase": "PRESSURE",
                "reason": "reopen the previous local branch after exhausting this state",
                "expected_change": "material",
            }

        # Otherwise choose the ordinary action with the best observed yield and
        # least local/global repetition. Deterministic hash jitter breaks ties.
        if ordinary:
            def rank(name: str) -> tuple[float, int, int, str]:
                stats = self.state.action_stats[name]
                tie = sha256_bytes(f"{self.state.seed}:{state_id}:{name}".encode())
                return (-stats.yield_rate, stats.attempts, SAFE_ORDER.index(name), tie)

            name = min(ordinary, key=rank)
            return available[name], {}, {
                "phase": "PRESSURE",
                "reason": "best observed material-yield action after local probes were exhausted",
                "expected_change": "material" if self.state.action_stats[name].yield_rate > 0 else "unknown",
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
            "schema": "hearthline.orientation-world-model.v1",
            "policy": POLICY_ID,
            "states_observed": len(self.state.state_visits),
            "state_visit_counts": dict(sorted(self.state.state_visits.items())),
            "action_effects": {
                name: self.state.action_stats[name].as_dict()
                for name in sorted(self.state.action_stats)
            },
            "recent_state_path": list(self.state.recent_states),
            "transition_tail": [
                {"from": start, "action": action, "to": end}
                for start, action, end in self.state.transition_stack[-32:]
            ],
            "interpretive_status": (
                "Structural transition inventory only. Entity roles, goal identity, "
                "and causal mechanisms remain unresolved unless a later reviewed Static earns them."
            ),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-contact", action="store_true")
    parser.add_argument("--game-id", default="ls20")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-actions", type=int, default=48)
    parser.add_argument("--max-resets", type=int, default=2)
    parser.add_argument("--max-wall-seconds", type=int, default=3600)
    parser.add_argument("--output-root", default="launch/runs")
    parser.add_argument("--print-events", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.allow_public_contact:
        raise SystemExit(
            "Refusing network contact. Re-run with --allow-public-contact after reviewing the run scope."
        )
    if args.max_actions < 0 or args.max_resets < 0 or args.max_wall_seconds < 0:
        raise SystemExit("budgets must be nonnegative")

    started_monotonic = time.monotonic()
    started_at = utc_now()
    receipt_id = f"orientation-{started_at[:10]}-{uuid.uuid4().hex[:12]}"
    run_dir = Path(args.output_root) / receipt_id
    run_dir.mkdir(parents=True, exist_ok=False)
    events_path = run_dir / "events.jsonl"
    world_model_path = run_dir / "world-model.json"
    heartbeat_path = run_dir / "heartbeat.json"
    receipt_path = run_dir / "receipt.json"

    contact: dict[str, Any] = {
        "anonymous_key_requested": not bool(os.getenv("ARC_API_KEY")),
        "games_endpoint_contacted": False,
        "scorecard_opened": False,
        "environment_opened": False,
        "scorecard_closed": False,
    }
    counts: Counter[str] = Counter()
    status = "BLOCKED_BEFORE_CONTACT"
    stop_reason = "initialization_not_completed"
    official_terminal_state: str | None = None
    levels_completed: int | None = None
    win_levels: int | None = None
    available_game_ids: list[str] = []
    errors: list[str] = []
    policy = StateNoveltyPolicy(args.seed)
    arcade: Any = None
    env: Any = None
    response: Any = None
    previous_grid: list[list[int]] | None = None
    scorecard_close_value: Any = None

    quiet_logger = logging.getLogger(f"hearthline.orientation.{receipt_id}")
    quiet_logger.handlers.clear()
    quiet_logger.addHandler(logging.StreamHandler(sys.stderr))
    quiet_logger.setLevel(logging.WARNING)
    quiet_logger.propagate = False

    try:
        from arc_agi import Arcade, OperationMode

        arcade = Arcade(
            operation_mode=OperationMode.NORMAL,
            recordings_dir=str(run_dir / "official-recordings"),
            logger=quiet_logger,
        )
        contact["games_endpoint_contacted"] = True
        available_game_ids = sorted(
            {
                str(getattr(item, "game_id", ""))
                for item in arcade.get_environments()
                if getattr(item, "game_id", "")
            }
        )
        if not available_game_ids:
            stop_reason = "official_surface_returned_no_public_games"
            status = "BLOCKED_AFTER_CONTACT"
            return_code = 2
        else:
            selected_game = args.game_id
            if selected_game not in available_game_ids:
                matching = [item for item in available_game_ids if item.split("-", 1)[0] == selected_game]
                if matching:
                    selected_game = matching[0]
                else:
                    stop_reason = "requested_game_not_available"
                    status = "BLOCKED_AFTER_CONTACT"
                    return_code = 2
                    selected_game = ""
            if selected_game:
                env = arcade.make(
                    selected_game,
                    seed=args.seed,
                    save_recording=True,
                    include_frame_data=True,
                )
                contact["scorecard_opened"] = bool(getattr(arcade, "_default_scorecard_id", None))
                if env is None:
                    stop_reason = "official_surface_failed_to_open_environment"
                    status = "BLOCKED_AFTER_CONTACT"
                    return_code = 2
                else:
                    contact["environment_opened"] = True
                    response = env.observation_space
                    if response is None:
                        response = env.reset()
                        if response is not None:
                            counts["resets"] += 1
                    if response is None:
                        stop_reason = "environment_returned_no_initial_observation"
                        status = "BLOCKED_AFTER_CONTACT"
                        return_code = 2
                    else:
                        status = "PUBLIC_ORIENTATION_PARTIAL"
                        return_code = 0
                        while counts["actions"] < args.max_actions:
                            elapsed = time.monotonic() - started_monotonic
                            if elapsed >= args.max_wall_seconds:
                                stop_reason = "wall_time_budget_reached"
                                break

                            grid = to_grid(response)
                            summary = summarize_grid(grid) if grid is not None else {"grid_status": "UNREADABLE"}
                            state_id = state_signature(response, grid)
                            terminal_before = enum_name(getattr(response, "state", "UNKNOWN"))
                            official_terminal_state = terminal_before
                            levels_completed = getattr(response, "levels_completed", None)
                            win_levels = getattr(response, "win_levels", None)

                            if terminal_before == "WIN":
                                stop_reason = "official_win_observed"
                                break
                            if terminal_before == "GAME_OVER":
                                if counts["resets"] >= args.max_resets:
                                    stop_reason = "official_game_over_and_reset_budget_reached"
                                    break
                                response = env.reset()
                                counts["resets"] += 1
                                previous_grid = None
                                if response is None:
                                    stop_reason = "reset_returned_no_observation"
                                    break
                                continue

                            choice = policy.choose(env, response, summary, state_id)
                            if choice is None:
                                stop_reason = "no_supported_action_available"
                                break
                            action, action_data, prediction = choice
                            action_name = enum_name(action)

                            before_grid = grid
                            before_state_id = state_id
                            before_levels = levels_completed
                            before_win_levels = win_levels
                            event_id = f"event-{counts['actions'] + 1:06d}"
                            prediction_record = {
                                "prediction_id": f"prediction-{counts['actions'] + 1:06d}",
                                "action": action_name,
                                "data": action_data,
                                "state_ref": before_state_id,
                                **prediction,
                            }

                            next_response = env.step(
                                action,
                                data=action_data or None,
                                reasoning={
                                    "policy": POLICY_ID,
                                    "event_id": event_id,
                                    "phase": prediction["phase"],
                                },
                            )
                            counts["actions"] += 1
                            if next_response is None:
                                stop_reason = "action_returned_no_observation"
                                break

                            after_grid = to_grid(next_response)
                            after_state_id = state_signature(next_response, after_grid)
                            terminal_after = enum_name(getattr(next_response, "state", "UNKNOWN"))
                            terminal_changed = terminal_before != terminal_after
                            if before_grid is not None and after_grid is not None:
                                diff = diff_grids(before_grid, after_grid)
                                changed_cells = int(diff.get("changed_cells", 0)) if diff.get("comparable") else 0
                            else:
                                diff = {"comparable": False, "reason": "unreadable_grid"}
                                changed_cells = 0

                            level_changed = before_levels != getattr(next_response, "levels_completed", None)
                            wins_changed = before_win_levels != getattr(next_response, "win_levels", None)
                            material = changed_cells > 0 or terminal_changed or level_changed or wins_changed
                            counts["material_changes" if material else "zero_change_actions"] += 1

                            expected = prediction.get("expected_change")
                            if expected == "unknown":
                                prediction_class = "UNREADABLE"
                            elif expected == "material" and material:
                                prediction_class = "MATCH"
                                counts["prediction_matches"] += 1
                            elif expected == "material" and not material:
                                prediction_class = "MISMATCH"
                                counts["prediction_mismatches"] += 1
                            else:
                                prediction_class = "PARTIAL"

                            policy.observe(
                                before_state=before_state_id,
                                after_state=after_state_id,
                                action_name=action_name,
                                changed_cells=changed_cells,
                                terminal_changed=terminal_changed or level_changed or wins_changed,
                            )
                            event = {
                                "schema": "hearthline.public-orientation-event.v1",
                                "event_id": event_id,
                                "recorded_at_utc": utc_now(),
                                "action_index": counts["actions"],
                                "before_state_ref": before_state_id,
                                "after_state_ref": after_state_id,
                                "prediction": prediction_record,
                                "outcome": {
                                    "official_state": terminal_after,
                                    "levels_completed": getattr(next_response, "levels_completed", None),
                                    "win_levels": getattr(next_response, "win_levels", None),
                                    "available_actions": sorted(
                                        str(item) for item in getattr(next_response, "available_actions", []) or []
                                    ),
                                    "diff": diff,
                                    "prediction_class": prediction_class,
                                },
                                "claim_ceiling": "One public environment transition; no mechanism or goal identity inferred by this event alone.",
                            }
                            event_hash = append_jsonl(events_path, event)
                            if args.print_events:
                                print(
                                    json.dumps(
                                        {
                                            "event": event_id,
                                            "action": action_name,
                                            "changed_cells": changed_cells,
                                            "state": terminal_after,
                                            "levels_completed": getattr(next_response, "levels_completed", None),
                                            "event_sha256": event_hash,
                                        },
                                        sort_keys=True,
                                    ),
                                    flush=True,
                                )

                            response = next_response
                            previous_grid = after_grid
                            atomic_json(
                                world_model_path,
                                {
                                    **policy.world_model(),
                                    "current_state_ref": after_state_id,
                                    "current_official_state": terminal_after,
                                    "current_levels_completed": getattr(response, "levels_completed", None),
                                    "current_win_levels": getattr(response, "win_levels", None),
                                },
                            )
                            atomic_json(
                                heartbeat_path,
                                {
                                    "schema": "hearthline.orientation-heartbeat.v1",
                                    "receipt_id": receipt_id,
                                    "recorded_at_utc": utc_now(),
                                    "actions": counts["actions"],
                                    "resets": counts["resets"],
                                    "official_state": terminal_after,
                                    "material_change": material,
                                    "latest_event": event_id,
                                    "authority_effect": "NONE",
                                },
                            )

                            if terminal_after == "WIN":
                                stop_reason = "official_win_observed"
                                break
                            if terminal_after == "GAME_OVER" and counts["resets"] >= args.max_resets:
                                stop_reason = "official_game_over_and_reset_budget_reached"
                                break
                        else:
                            stop_reason = "action_budget_reached"

                        if contact["environment_opened"]:
                            status = "PUBLIC_ORIENTATION_COMPLETE"
    except KeyboardInterrupt:
        status = "PUBLIC_ORIENTATION_PARTIAL" if contact["environment_opened"] else "BLOCKED_AFTER_CONTACT"
        stop_reason = "operator_interrupt"
        return_code = 130
    except Exception as exc:  # boundary receipt must survive unexpected library/network failures
        status = "BLOCKED_AFTER_CONTACT" if any(contact.values()) else "BLOCKED_BEFORE_CONTACT"
        stop_reason = f"exception:{type(exc).__name__}"
        errors.append(f"{type(exc).__name__}: {exc}")
        return_code = 2
    finally:
        if arcade is not None and contact["scorecard_opened"]:
            try:
                scorecard_close_value = arcade.close_scorecard()
                contact["scorecard_closed"] = scorecard_close_value is not None
            except Exception as exc:
                errors.append(f"scorecard_close:{type(exc).__name__}: {exc}")

        ended_at = utc_now()
        elapsed_seconds = time.monotonic() - started_monotonic
        if response is not None:
            official_terminal_state = enum_name(getattr(response, "state", "UNKNOWN"))
            levels_completed = getattr(response, "levels_completed", None)
            win_levels = getattr(response, "win_levels", None)
        if not world_model_path.exists():
            atomic_json(world_model_path, policy.world_model())

        artifact_hashes = {
            "world_model_json": sha256_file(world_model_path),
        }
        if events_path.exists():
            artifact_hashes["events_jsonl"] = sha256_file(events_path)
        if heartbeat_path.exists():
            artifact_hashes["heartbeat_json"] = sha256_file(heartbeat_path)

        receipt = {
            "schema": "hearthline.public-arc-orientation-receipt.v1",
            "receipt_id": receipt_id,
            "status": status,
            "started_at_utc": started_at,
            "ended_at_utc": ended_at,
            "official_surface": {
                "repository": OFFICIAL_REPOSITORY,
                "commit": OFFICIAL_COMMIT,
                "tree": OFFICIAL_TREE,
            },
            "scope": {
                "public_practice_only": True,
                "competition_mode": False,
                "paid_provider": False,
                "kaggle": False,
                "private_holdout": False,
            },
            "configuration": {
                "game_id": args.game_id,
                "seed": args.seed,
                "max_actions": args.max_actions,
                "max_resets": args.max_resets,
                "max_wall_seconds": args.max_wall_seconds,
                "policy": POLICY_ID,
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "contact": contact,
            "counts": {
                "actions": counts["actions"],
                "resets": counts["resets"],
                "material_changes": counts["material_changes"],
                "zero_change_actions": counts["zero_change_actions"],
                "prediction_matches": counts["prediction_matches"],
                "prediction_mismatches": counts["prediction_mismatches"],
                "states_observed": len(policy.state.state_visits),
            },
            "result": {
                "official_terminal_state": official_terminal_state,
                "levels_completed": levels_completed,
                "win_levels": win_levels,
                "win_observed": official_terminal_state == "WIN",
                "stop_reason": stop_reason,
                "elapsed_seconds": elapsed_seconds,
                "available_game_ids": available_game_ids,
            },
            "artifact_hashes": artifact_hashes,
            "residuals": errors,
            "claim_ceiling": (
                "This receipt covers one bounded public orientation session. A win is only the "
                "official terminal state for the bound public session; no absence of win proves "
                "impossibility, and no result authorizes Kaggle, competition, paid-provider, or private-holdout use."
            ),
        }
        atomic_json(receipt_path, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True), flush=True)
        print(f"receipt_path={receipt_path}", flush=True)

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
