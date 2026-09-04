"""Offline-default ARC-AGI-3 submission agent.

The public contract follows the official ARC-AGI-3 Kaggle starter: subclass
``agents.agent.Agent`` and implement ``is_done`` and ``choose_action``. This
module does not create an Arcade, open a network connection, read a credential,
or write a receipt. The competition framework alone owns environment effects.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from arcengine import FrameData, GameAction, GameState
from agents.agent import Agent


CONTEXT_PROFILE = "A0_MINIMAL"
ROLE_PROFILES: dict[str, frozenset[str]] = {
    "A0_FULL": frozenset({
        "A0BK_ADVISORY_GATE",
        "FBT_CONTINUATION_SPLIT",
        "GOLD_1_PLUS_5_LENS",
        "PAL_ROLE_LEDGER",
        "SINGLE_CUT_CHECKPOINT",
        "DISTINCTION_GROUPER",
        "ADVANCE_ATOMIC_PROMOTION",
        "GAME_EMBODIMENT_BOUNDARY",
    }),
    "A0_NO_A0BK": frozenset({
        "FBT_CONTINUATION_SPLIT",
        "GOLD_1_PLUS_5_LENS",
        "PAL_ROLE_LEDGER",
        "SINGLE_CUT_CHECKPOINT",
        "DISTINCTION_GROUPER",
        "ADVANCE_ATOMIC_PROMOTION",
        "GAME_EMBODIMENT_BOUNDARY",
    }),
    "A0_NO_FBT_CONTINUATION": frozenset({
        "A0BK_ADVISORY_GATE",
        "GOLD_1_PLUS_5_LENS",
        "PAL_ROLE_LEDGER",
        "SINGLE_CUT_CHECKPOINT",
        "DISTINCTION_GROUPER",
        "ADVANCE_ATOMIC_PROMOTION",
        "GAME_EMBODIMENT_BOUNDARY",
    }),
    "A0_NO_GOLD": frozenset({
        "A0BK_ADVISORY_GATE",
        "FBT_CONTINUATION_SPLIT",
        "PAL_ROLE_LEDGER",
        "SINGLE_CUT_CHECKPOINT",
        "DISTINCTION_GROUPER",
        "ADVANCE_ATOMIC_PROMOTION",
        "GAME_EMBODIMENT_BOUNDARY",
    }),
    "A0_MINIMAL": frozenset(),
}

DISTINCTION_GROUPS = (
    "DIRECT_OBSERVATION",
    "DERIVED",
    "HYPOTHESIS",
    "UNRESOLVED",
    "PLAN_ONLY",
)
ACTION_NAMES = frozenset({
    "RESET", "ACTION1", "ACTION2", "ACTION3",
    "ACTION4", "ACTION5", "ACTION6", "ACTION7",
})


def group_distinctions(records: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group copies of records without promoting or merging their status."""
    grouped = {name: [] for name in DISTINCTION_GROUPS}
    for record in records:
        status = str(record.get("status", "UNRESOLVED"))
        if status not in grouped:
            status = "UNRESOLVED"
        grouped[status].append(deepcopy(dict(record)))
    return grouped


@dataclass(frozen=True)
class AdvanceResult:
    promoted: bool
    successor: dict[str, Any]
    residual: str | None


def advance(
    current: Mapping[str, Any],
    field: str,
    value: Any,
    evidence_refs: Iterable[str],
    promotion_rule_passed: bool,
) -> AdvanceResult:
    """Atomically promote one field or return an unmodified deep copy."""
    refs = tuple(evidence_refs)
    successor = deepcopy(dict(current))
    if not promotion_rule_passed or not refs:
        return AdvanceResult(
            promoted=False,
            successor=successor,
            residual=f"{field} remains a hypothesis: promotion rule or evidence incomplete",
        )
    successor[field] = {"value": deepcopy(value), "evidence_refs": list(refs)}
    return AdvanceResult(promoted=True, successor=successor, residual=None)


def _canonical_json_bytes(value: object) -> bytes:
    """Seal one JSON value without retaining caller-owned mutable objects."""
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"framework action request is not strict JSON: {error}") from error


def _reject_nonfinite(token: str) -> None:
    raise ValueError(f"non-finite number {token}")


def _strict_json_object(data: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(
            data,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise RuntimeError(f"sealed {label} is not strict JSON: {error}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"sealed {label} is not an object with string keys")
    if _canonical_json_bytes(value) != data:
        raise RuntimeError(f"sealed {label} is not canonical")
    return value


@dataclass(frozen=True, slots=True)
class _FrameworkActionRequest:
    """An immutable, instance-local request for the pinned Agent boundary.

    ``GameAction`` members are process-wide enum singletons.  Their upstream
    ``set_data`` method mutates that singleton, so preparing ACTION6 in two
    Swarm workers can overwrite one worker's coordinates or reasoning before
    it reaches ``EnvironmentWrapper.step``.  This envelope carries only the
    action name and sealed per-decision JSON; no enum member is mutated.
    """

    action_name: str
    payload_json: bytes
    reasoning_json: bytes

    def __post_init__(self) -> None:
        if self.action_name not in ACTION_NAMES:
            raise RuntimeError("sealed framework action name is outside the fixed vocabulary")
        _strict_json_object(self.payload_json, "framework action payload")
        _strict_json_object(self.reasoning_json, "framework action reasoning")

    @property
    def name(self) -> str:
        """Preserve the ``action.name`` surface used by the pinned runner."""
        return self.action_name

    def payload(self) -> dict[str, object]:
        return _strict_json_object(self.payload_json, "framework action payload")

    def reasoning(self) -> dict[str, object]:
        return _strict_json_object(self.reasoning_json, "framework action reasoning")


def _instance_local_payload(
    action: GameAction,
    values: Mapping[str, object],
) -> dict[str, object]:
    """Validate action data without reading or mutating singleton state."""
    action_type = getattr(action, "action_type", None)
    if action_type is None:
        # Some framework versions represent simple actions without a model.
        # The proposed values are already instance-local and simple actions
        # supply no values in this agent.
        return dict(values)
    if not callable(action_type):
        raise RuntimeError("framework GameAction has a non-callable action type")
    try:
        action_data = action_type(**dict(values))
    except Exception as error:
        raise RuntimeError(f"framework rejected instance-local action data: {error}") from error
    dumper = getattr(action_data, "model_dump", None)
    if not callable(dumper):
        raise RuntimeError("framework action data cannot be serialized")
    serialized = dumper()
    if not isinstance(serialized, dict) or not all(
        isinstance(key, str) for key in serialized
    ):
        raise RuntimeError("framework action data serialization has the wrong shape")
    return serialized


def _seal_action_request(
    action: GameAction,
    values: Mapping[str, object],
    reasoning: Mapping[str, object],
) -> _FrameworkActionRequest:
    name = getattr(action, "name", None)
    if not isinstance(name, str):
        raise RuntimeError("framework GameAction has no string name")
    payload = _instance_local_payload(action, values)
    return _FrameworkActionRequest(
        action_name=name,
        payload_json=_canonical_json_bytes(payload),
        reasoning_json=_canonical_json_bytes(dict(reasoning)),
    )


class MyAgent(Agent):
    """Deterministic bounded controller with an off-by-default context profile."""

    MAX_ACTIONS = 80
    CONTEXT_PROFILE = CONTEXT_PROFILE
    LS20_LEVEL1_ROUTE = (
        "ACTION3", "ACTION3", "ACTION3",
        "ACTION1", "ACTION1", "ACTION1", "ACTION1",
        "ACTION4", "ACTION4", "ACTION4",
        "ACTION1", "ACTION1", "ACTION1",
    )
    BASELINE_ORDER = ("ACTION1", "ACTION4", "ACTION2", "ACTION3")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.CONTEXT_PROFILE not in ROLE_PROFILES:
            raise ValueError(f"unknown context profile: {self.CONTEXT_PROFILE}")
        if type(self.MAX_ACTIONS) is not int or self.MAX_ACTIONS <= 0:
            raise ValueError("MAX_ACTIONS must be a positive integer, not a boolean")
        self.enabled_roles = ROLE_PROFILES[self.CONTEXT_PROFILE]
        self._actions_chosen = 0
        self._ls20_cursor = 0
        self._baseline_cursor = 0

    @property
    def name(self) -> str:
        return f"{super().name}.hearthline-v2.{self.CONTEXT_PROFILE}.{self.MAX_ACTIONS}"

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        del frames
        return latest_frame.state is GameState.WIN or self._actions_chosen >= self.MAX_ACTIONS

    @staticmethod
    def _available_names(latest_frame: FrameData) -> set[str] | None:
        declared = getattr(latest_frame, "available_actions", None)
        if declared is None:
            return None
        # An explicit empty list means "no action is available".  It is not
        # interchangeable with an absent/unknown availability field.
        return {str(getattr(item, "name", item)) for item in declared}

    @staticmethod
    def _action(name: str) -> GameAction:
        return getattr(GameAction, name)

    @staticmethod
    def _decorate(
        action: GameAction,
        reason: dict[str, Any],
    ) -> _FrameworkActionRequest:
        values: dict[str, object] = {}
        is_complex = getattr(action, "is_complex", None)
        if callable(is_complex) and is_complex():
            values = {"x": 31, "y": 31}
        return _seal_action_request(action, values, reason)

    def _choose_name(self, latest_frame: FrameData) -> tuple[str, str]:
        available = self._available_names(latest_frame)
        if available == set():
            raise RuntimeError("framework declared no available action")
        game_prefix = str(self.game_id).split("-")[0]
        levels_completed = getattr(latest_frame, "levels_completed", 0)
        if type(levels_completed) is not int or levels_completed < 0:
            raise RuntimeError("levels_completed must be a non-negative integer, not a boolean")

        if game_prefix == "ls20" and levels_completed == 0:
            while self._ls20_cursor < len(self.LS20_LEVEL1_ROUTE):
                name = self.LS20_LEVEL1_ROUTE[self._ls20_cursor]
                self._ls20_cursor += 1
                if available is None or name in available:
                    return name, "LS20-WM-0001 exact level-one route"

        for _ in range(len(self.BASELINE_ORDER)):
            name = self.BASELINE_ORDER[self._baseline_cursor % len(self.BASELINE_ORDER)]
            self._baseline_cursor += 1
            if available is None or name in available:
                return name, "deterministic minimal baseline"

        if available is not None:
            for name in ("ACTION5", "ACTION6", "ACTION7", "RESET"):
                if name in available:
                    return name, "only declared bounded fallback"
            raise RuntimeError("no supported action appears in the declared availability set")
        return "RESET", "availability was absent; bounded reset fallback"

    def choose_action(
        self,
        frames: list[FrameData],
        latest_frame: FrameData,
    ) -> _FrameworkActionRequest:
        del frames
        if self._actions_chosen >= self.MAX_ACTIONS:
            raise RuntimeError("action cap reached; framework must stop before another dispatch")
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            available = self._available_names(latest_frame)
            if available is not None and "RESET" not in available:
                raise RuntimeError(
                    "framework state requires RESET but RESET is not declared available"
                )
            self._ls20_cursor = 0
            action = self._action("RESET")
            self._actions_chosen += 1
            return self._decorate(action, {
                "policy": "hearthline-offline-default-v2",
                "profile": self.CONTEXT_PROFILE,
                "why": "framework state requires bounded reset",
                "authority": "framework-owned effect only",
            })

        name, why = self._choose_name(latest_frame)
        action = self._action(name)
        self._actions_chosen += 1
        return self._decorate(action, {
            "policy": "hearthline-offline-default-v2",
            "profile": self.CONTEXT_PROFILE,
            "enabled_roles": sorted(self.enabled_roles),
            "why": why,
            "world_model": "practice/ls20/world-model.v2.json" if why.startswith("LS20") else None,
            "authority": "proposal only until framework dispatch and returned FrameData",
        })

    def do_action_request(self, action: object) -> FrameData:
        """Submit one sealed request at the pinned framework effect boundary."""
        if not isinstance(action, _FrameworkActionRequest):
            raise RuntimeError("official wrapper received an unsealed action request")
        member = self._action(action.name)
        environment = getattr(self, "arc_env", None)
        step = getattr(environment, "step", None)
        if not callable(step):
            raise RuntimeError("official wrapper has no callable environment step")
        raw = step(
            member,
            data=action.payload(),
            reasoning=action.reasoning(),
        )
        converter = getattr(self, "_convert_raw_frame_data", None)
        if not callable(converter):
            raise RuntimeError("official wrapper has no frame conversion boundary")
        return converter(raw)
