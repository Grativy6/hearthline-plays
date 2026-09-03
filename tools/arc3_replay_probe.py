#!/usr/bin/env python3
"""Replay one explicit public ARC-AGI-3 orientation request and capture receipts.

The script chooses no actions. It sends only the sequence already present in the
authorized request file and refuses unavailable actions. It uses no model-provider
API. The ARC service is the authority for returned environment state.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import enum
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import re
import sys
import traceback
from collections import Counter, deque
from pathlib import Path
from typing import Any

COLOR_MAP = {
    0: (255, 255, 255), 1: (204, 204, 204), 2: (153, 153, 153),
    3: (102, 102, 102), 4: (51, 51, 51), 5: (0, 0, 0),
    6: (229, 58, 163), 7: (255, 123, 204), 8: (249, 60, 49),
    9: (30, 147, 255), 10: (136, 216, 241), 11: (255, 220, 0),
    12: (255, 133, 27), 13: (146, 18, 49), 14: (79, 204, 48),
    15: (163, 86, 214),
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, enum.Enum):
        return value.name
    if dataclasses.is_dataclass(value):
        return {k: jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump())
    if hasattr(value, "tolist"):
        return jsonable(value.tolist())
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if hasattr(value, "__dict__"):
        return {k: jsonable(v) for k, v in vars(value).items() if not k.startswith("_")}
    return repr(value)


def state_name(frame_data: Any) -> str:
    state = getattr(frame_data, "state", None)
    return state.name if hasattr(state, "name") else str(state)


def action_names(frame_data: Any) -> list[str]:
    out = []
    for action in getattr(frame_data, "available_actions", []) or []:
        if hasattr(action, "name"):
            out.append(action.name)
            continue
        try:
            value = int(action)
        except (TypeError, ValueError):
            out.append(str(action))
            continue
        out.append(f"ACTION{value}" if 1 <= value <= 7 else str(value))
    return out


def frame_hash(grid: Any) -> str:
    payload = json.dumps(jsonable(grid), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def connected_components(grid: list[list[int]]) -> dict[str, Any]:
    if not grid or not grid[0]:
        return {"background": None, "components": []}
    h, w = len(grid), len(grid[0])
    counts = Counter(v for row in grid for v in row)
    background = counts.most_common(1)[0][0]
    seen: set[tuple[int, int]] = set()
    comps = []
    for y in range(h):
        for x in range(w):
            color = grid[y][x]
            if color == background or (x, y) in seen:
                continue
            q = deque([(x, y)])
            seen.add((x, y))
            cells = []
            while q:
                cx, cy = q.popleft()
                cells.append((cx, cy))
                for nx, ny in ((cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)):
                    if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen and grid[ny][nx] == color:
                        seen.add((nx, ny))
                        q.append((nx, ny))
            xs = [c[0] for c in cells]
            ys = [c[1] for c in cells]
            comps.append({
                "component_id": f"c{len(comps):03d}",
                "color": color,
                "size": len(cells),
                "bbox": [min(xs), min(ys), max(xs), max(ys)],
                "centroid": [round(sum(xs)/len(xs), 3), round(sum(ys)/len(ys), 3)],
            })
    comps.sort(key=lambda c: (-c["size"], c["color"], c["bbox"]))
    return {"background": background, "shape": [h, w], "components": comps[:256]}


def save_png(grid: list[list[int]], path: Path, scale: int = 8) -> None:
    from PIL import Image
    h, w = len(grid), len(grid[0])
    img = Image.new("RGB", (w, h))
    pixels = img.load()
    for y, row in enumerate(grid):
        for x, raw in enumerate(row):
            pixels[x, y] = COLOR_MAP.get(int(raw), (255, 0, 255))
    if scale > 1:
        img = img.resize((w * scale, h * scale), resample=Image.Resampling.NEAREST)
    img.save(path)


class Capture:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.records: list[dict[str, Any]] = []
        self.seen: set[tuple[int, str]] = set()

    def __call__(self, step: int, frame_data: Any) -> None:
        frames = jsonable(getattr(frame_data, "frame", []) or [])
        if not isinstance(frames, list):
            frames = []
        for idx, grid in enumerate(frames):
            if not isinstance(grid, list) or not grid or not isinstance(grid[0], list):
                continue
            digest = frame_hash(grid)
            key = (step, digest)
            if key in self.seen:
                continue
            self.seen.add(key)
            stem = f"step-{step:04d}-frame-{idx:03d}"
            frame_dir = self.out / "frames"
            frame_dir.mkdir(parents=True, exist_ok=True)
            (frame_dir / f"{stem}.json").write_text(
                json.dumps(grid, separators=(",", ":")) + "\n", encoding="utf-8"
            )
            save_png(grid, frame_dir / f"{stem}.png")
            summary = connected_components(grid)
            record = {
                "step": step,
                "frame_index": idx,
                "sha256": digest,
                "state": state_name(frame_data),
                "levels_completed": getattr(frame_data, "levels_completed", None),
                "win_levels": getattr(frame_data, "win_levels", None),
                "available_actions": action_names(frame_data),
                "symbolic_summary": summary,
                "grid_path": f"frames/{stem}.json",
                "image_path": f"frames/{stem}.png",
            }
            self.records.append(jsonable(record))
            print("FRAME_RECORD " + json.dumps(record, separators=(",", ":"), ensure_ascii=False))


def load_request(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema", "request_id", "game_id", "seed", "mode",
        "source_world_model", "actions", "max_actions",
        "close_scorecard", "grant_ref", "status",
    }
    if set(data) != required:
        raise ValueError(f"request fields mismatch: {sorted(set(data) ^ required)}")
    if data.get("schema") != "hearthline.arc3-orientation-request.v1":
        raise ValueError("wrong request schema")
    if not isinstance(data.get("request_id"), str) or not re.fullmatch(r"ORIENT-[0-9]{4}", data["request_id"]):
        raise ValueError("invalid request_id")
    if data.get("mode") != "PUBLIC_ORIENTATION":
        raise ValueError("only PUBLIC_ORIENTATION is permitted")
    if data.get("status") != "AUTHORIZED":
        raise ValueError("request is not authorized")
    if data.get("grant_ref") != "launch/RUN_GRANT_2026-09-03.md":
        raise ValueError("wrong grant reference")
    if data.get("game_id") not in {"ls20", "ft09", "vc33"}:
        raise ValueError("request is not one of the three anonymous public games")
    expected_model = f"practice/{data['game_id']}/world-model.json"
    if data.get("source_world_model") != expected_model:
        raise ValueError("source_world_model is not the exact public-game model path")
    if not isinstance(data.get("seed"), int) or data["seed"] < 0:
        raise ValueError("seed must be a nonnegative integer")
    if data.get("close_scorecard") is not True:
        raise ValueError("scorecard must close")
    actions = data.get("actions")
    if not isinstance(actions, list):
        raise ValueError("actions must be a list")
    max_actions = data.get("max_actions")
    if not isinstance(max_actions, int) or isinstance(max_actions, bool) or not (0 <= len(actions) <= max_actions <= 64):
        raise ValueError("invalid action bound")
    allowed_actions = {f"ACTION{i}" for i in range(1, 8)}
    for index, step in enumerate(actions, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"action {index} is not an object")
        if set(step) - {"action", "data", "hypothesis", "expected_observable"}:
            raise ValueError(f"action {index} has unknown fields")
        if step.get("action") not in allowed_actions:
            raise ValueError(f"action {index} has invalid action name")
        for field in ("hypothesis", "expected_observable"):
            if not isinstance(step.get(field), str) or not (1 <= len(step[field]) <= 400):
                raise ValueError(f"action {index} has invalid {field}")
        step_data = step.get("data", {})
        if not isinstance(step_data, dict):
            raise ValueError(f"action {index} data must be an object")
        if step["action"] == "ACTION6":
            if set(step_data) != {"x", "y"} or not all(
                isinstance(step_data[k], int) and not isinstance(step_data[k], bool) and 0 <= step_data[k] <= 63
                for k in ("x", "y")
            ):
                raise ValueError(f"action {index} ACTION6 requires exact integer x,y in 0..63")
        elif step_data:
            raise ValueError(f"action {index} data is permitted only for ACTION6")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    request = load_request(args.request)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "request.json").write_text(
        json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    receipt: dict[str, Any] = {
        "schema": "hearthline.arc3-orientation-receipt.v1",
        "request_id": request["request_id"],
        "game_id": request["game_id"],
        "started_at": utc_now(),
        "finished_at": None,
        "toolkit": {
            "install_source": "git+https://github.com/arcprize/ARC-AGI.git@f12822c4d550121c35a275008d964afbbed47d2f",
            "source_reference_commit": "f12822c4d550121c35a275008d964afbbed47d2f",
            "source_reference_tree": "9ee140e4183df0df109cec50b7cd0d2531c47168",
            "installed_version": None,
            "arcengine_version": None,
            "python": platform.python_version(),
        },
        "contact_status": "UNKNOWN",
        "contact_attempted": False,
        "action_results": [],
        "frame_records": [],
        "scorecard": None,
        "status": "ERROR",
        "residuals": [],
    }
    capture = Capture(args.out)
    arc = None
    scorecard_may_be_open = False
    outcome_unknown = False

    try:
        import arc_agi
        from arcengine import GameState

        receipt["toolkit"]["installed_version"] = importlib.metadata.version("arc-agi")
        receipt["toolkit"]["arcengine_version"] = importlib.metadata.version("arcengine")

        # Refuse ambient credentials or mode overrides. This run deliberately uses
        # the official anonymous public route and cannot enter competition mode.
        for key in ("ARC_API_KEY", "ARC_BASE_URL", "OPERATION_MODE"):
            os.environ.pop(key, None)
        quiet_logger = logging.getLogger("hearthline.arc3.public_probe")
        quiet_logger.handlers.clear()
        quiet_logger.addHandler(logging.StreamHandler(sys.stdout))
        quiet_logger.setLevel(logging.WARNING)
        quiet_logger.propagate = False

        receipt["contact_attempted"] = True
        arc = arc_agi.Arcade(
            arc_api_key="",
            arc_base_url="https://three.arcprize.org",
            operation_mode=arc_agi.OperationMode.ONLINE,
            recordings_dir=str(args.out / "recordings-not-retained"),
            logger=quiet_logger,
        )
        receipt["contact_status"] = "CONTACTED"
        print(f"OPEN_PUBLIC_GAME {request['game_id']}")
        scorecard_may_be_open = True
        env = arc.make(
            request["game_id"],
            seed=request["seed"],
            save_recording=False,
            include_frame_data=True,
            renderer=None,
        )
        if env is None:
            raise RuntimeError("Arcade.make returned None")

        initial = env.observation_space
        if initial is not None:
            capture(0, initial)

        for index, step in enumerate(request["actions"], start=1):
            available = {a.name: a for a in env.action_space}
            action_name = step["action"]
            if action_name not in available:
                receipt["action_results"].append({
                    "index": index,
                    "action": action_name,
                    "dispatch": "NOT_SENT",
                    "status": "BLOCKED_UNAVAILABLE_ACTION",
                    "available_actions": sorted(available),
                })
                receipt["status"] = "BLOCKED"
                receipt["residuals"].append(
                    f"{action_name} was not available at action index {index}; later actions were not sent."
                )
                break

            action = available[action_name]
            data = step.get("data") or {}
            if action_name == "ACTION6":
                if not all(isinstance(data.get(k), int) and 0 <= data[k] <= 63 for k in ("x", "y")):
                    raise ValueError("ACTION6 requires integer x,y in 0..63")
            else:
                data = {}

            public_reason = {
                "request_id": request["request_id"],
                "action_index": index,
                "hypothesis": step["hypothesis"],
                "expected_observable": step["expected_observable"],
            }
            print("DISPATCH " + json.dumps({"action": action_name, "data": data, "reasoning": public_reason}, separators=(",", ":")))
            try:
                obs = env.step(action, data=data, reasoning=public_reason)
            except Exception:
                outcome_unknown = True
                receipt["action_results"].append({
                    "index": index,
                    "action": action_name,
                    "dispatch": "MAY_HAVE_BEEN_SENT",
                    "status": "UNKNOWN_OUTCOME",
                })
                receipt["status"] = "UNKNOWN_OUTCOME"
                receipt["residuals"].append(
                    "An exception occurred after dispatch began; no retry was attempted."
                )
                raise

            if obs is None:
                outcome_unknown = True
                receipt["action_results"].append({
                    "index": index,
                    "action": action_name,
                    "dispatch": "SENT",
                    "status": "UNKNOWN_OUTCOME_NONE_RETURNED",
                })
                receipt["status"] = "UNKNOWN_OUTCOME"
                receipt["residuals"].append("Environment returned None after an action; no retry was attempted.")
                break

            capture(index, obs)
            result = {
                "index": index,
                "action": action_name,
                "data": data,
                "dispatch": "SENT",
                "status": "OBSERVED",
                "environment_state": state_name(obs),
                "levels_completed": getattr(obs, "levels_completed", None),
                "available_actions_after": action_names(obs),
            }
            receipt["action_results"].append(jsonable(result))
            if getattr(obs, "state", None) in (GameState.WIN, GameState.GAME_OVER):
                receipt["status"] = state_name(obs)
                break
        else:
            final = env.observation_space
            final_state = state_name(final) if final is not None else "UNKNOWN"
            receipt["status"] = final_state if final_state in {"WIN", "GAME_OVER"} else "ORIENTATION_COMPLETE"

    except Exception as exc:
        receipt["residuals"].append(f"{type(exc).__name__}: {exc}")
        (args.out / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc(), file=sys.stderr)
        if outcome_unknown:
            receipt["status"] = "UNKNOWN_OUTCOME"
        elif receipt["contact_status"] != "CONTACTED":
            receipt["status"] = "ERROR"
        elif receipt["status"] not in {"BLOCKED", "UNKNOWN_OUTCOME"}:
            receipt["status"] = "ERROR"
    finally:
        if arc is not None and scorecard_may_be_open:
            try:
                closed = arc.close_scorecard()
                receipt["scorecard"] = jsonable(closed)
                print("SCORECARD_CLOSED " + json.dumps(jsonable(closed), separators=(",", ":"), ensure_ascii=False))
            except Exception as exc:
                receipt["residuals"].append(f"scorecard_close_failed: {type(exc).__name__}: {exc}")
                if receipt["status"] not in {"UNKNOWN_OUTCOME"}:
                    receipt["status"] = "ERROR"
        receipt["frame_records"] = capture.records
        receipt["finished_at"] = utc_now()
        (args.out / "receipt.json").write_text(
            json.dumps(jsonable(receipt), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("FINAL_RECEIPT " + json.dumps({
            "request_id": receipt["request_id"],
            "contact_status": receipt["contact_status"],
            "status": receipt["status"],
            "actions_observed": sum(1 for r in receipt["action_results"] if r.get("status") == "OBSERVED"),
            "frames": len(receipt["frame_records"]),
            "residuals": receipt["residuals"],
        }, separators=(",", ":"), ensure_ascii=False))

    return 0 if receipt["status"] not in {"ERROR", "UNKNOWN_OUTCOME"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
