"""Execute the byte-verified pinned Kaggriculture interpreter without the full SDK.

The environment Python and JSON files are byte-identical to Git blobs recorded in
launch/source-lock.json.  This adapter supplies only the small state/configuration
objects normally provided by kaggle-environments.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from kaggle_environments.envs.kaggriculture import kaggriculture as upstream  # noqa: E402

Agent = Callable[[dict[str, Any]], dict[str, Any]]


class AttrDict(dict):
    """Dict with the attribute access used by Kaggle's Struct objects."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


@dataclass
class State:
    observation: AttrDict
    action: dict[str, Any] | None = None
    status: str = "ACTIVE"
    reward: float | None = None


class Env:
    def __init__(self, seed: int):
        self.configuration = AttrDict(
            episodeSteps=720,
            actTimeout=1,
            boardSize=10,
            startingMoney=3000,
            maxMarketOrdersPerTurn=10,
            turnsPerDay=24,
            shedCapacity=100,
            weedSpawnChance=0.005,
            townShopUnlockInterval=3,
            townShopSellInterval=4,
            townCenterSellInterval=24,
            seed=seed,
            farmHandCostMult=1,
            marketParams={},
        )
        self.info: dict[str, Any] = {}
        self.done = False


class UpstreamSimulator:
    def __init__(self, agents: list[Agent], seed: int):
        if len(agents) != 2:
            raise ValueError("exactly two agents are required")
        self.agents = agents
        self.seed = seed
        self.env = Env(seed)
        self.states = [
            State(AttrDict(step=0, player=i, farms=[], private={}, market={}, town={}, day=0, hour=0))
            for i in range(2)
        ]
        upstream.interpreter(self.states, self.env)
        self.step = 0
        self.actions: list[list[dict[str, Any]]] = []
        self.runtime_seconds = [0.0, 0.0]
        self.max_runtime_seconds = [0.0, 0.0]
        self.agent_exceptions = [0, 0]
        self.malformed_actions = [0, 0]
        self.state_hashes: list[str] = []

    @staticmethod
    def _plain(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: UpstreamSimulator._plain(v) for k, v in value.items()}
        if isinstance(value, list):
            return [UpstreamSimulator._plain(v) for v in value]
        return copy.deepcopy(value)

    def observation(self, player: int) -> dict[str, Any]:
        obs = self._plain(self.states[player].observation)
        obs["step"] = self.step
        return obs

    @staticmethod
    def _valid_action(action: Any, hand_count: int) -> bool:
        if not isinstance(action, dict):
            return False
        farmer = action.get("farmer")
        hands = action.get("hands")
        market = action.get("market")
        if not isinstance(farmer, list) or not farmer:
            return False
        if not isinstance(hands, list) or len(hands) != hand_count:
            return False
        if not all(isinstance(a, list) and a for a in hands):
            return False
        if not isinstance(market, list) or len(market) > 10:
            return False
        unit_ops = {"NORTH", "SOUTH", "EAST", "WEST", "PASS", "PICKUP", "PLANT", "WATER", "HARVEST", "FERTILIZE", "BUILD_COOP", "BUILD_PASTURE", "DIG", "PLACE", "DROP", "FEED", "COLLECT_FERTILIZER", "CARE"}
        if farmer[0] not in unit_ops or any(a[0] not in unit_ops for a in hands):
            return False
        market_ops = {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL", "HIRE", "BUY_LAND"}
        return all(isinstance(o, list) and o and o[0] in market_ops for o in market)

    def canonical_state(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "farms": self._plain(self.states[0].observation.farms),
            "privates": [self._plain(state.observation.private) for state in self.states],
            "market": self._plain(self.states[0].observation.market),
            "town": self._plain(self.states[0].observation.town),
        }

    def canonical_state_hash(self) -> str:
        payload = json.dumps(self.canonical_state(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def run(self) -> dict[str, Any]:
        while not self.env.done:
            actions: list[dict[str, Any]] = []
            for player, agent in enumerate(self.agents):
                started = time.perf_counter()
                try:
                    action = agent(self.observation(player))
                except Exception:
                    self.agent_exceptions[player] += 1
                    action = {
                        "farmer": ["PASS"],
                        "hands": [["PASS"] for _ in self.states[player].observation.farms[player].get("hands", [])],
                        "market": [],
                    }
                elapsed = time.perf_counter() - started
                self.runtime_seconds[player] += elapsed
                self.max_runtime_seconds[player] = max(self.max_runtime_seconds[player], elapsed)
                if not self._valid_action(action, len(self.states[player].observation.farms[player].get("hands", []))):
                    self.malformed_actions[player] += 1
                actions.append(action)
                self.states[player].action = action

            self.actions.append(copy.deepcopy(actions))
            # The SDK supplies the current framework step in the shared observation.
            self.states[0].observation.step = self.step
            self.states[1].observation.step = self.step
            upstream.interpreter(self.states, self.env)
            self.step += 1
            self.env.done = all(state.status == "DONE" for state in self.states)
            self.state_hashes.append(self.canonical_state_hash())

        farms = self.states[0].observation.farms
        remaining = []
        for player in range(2):
            private = self.states[player].observation.private
            remaining.append(
                {
                    "shed": {k: int(v) for k, v in private.get("shed", {}).items() if v},
                    "seeds": {k: int(v) for k, v in private.get("seeds", {}).items() if v},
                    "field": {
                        item: sum(inv.get(item, 0) for inv in private.get("inventories", []))
                        for item in upstream.PRODUCTS + list(upstream.ANIMALS)
                        if sum(inv.get(item, 0) for inv in private.get("inventories", []))
                    },
                }
            )
        return {
            "seed": self.seed,
            "steps_processed": self.step,
            "final_bank": [float(farm["money"]) for farm in farms],
            "rewards": [state.reward for state in self.states],
            "statuses": [state.status for state in self.states],
            "remaining_inventory": remaining,
            "town_shops": list(self.states[0].observation.town.get("unlocked_shops", [])),
            "agent_runtime_seconds": self.runtime_seconds,
            "max_agent_runtime_seconds": self.max_runtime_seconds,
            "agent_exceptions": self.agent_exceptions,
            "malformed_actions": self.malformed_actions,
            "canonical_state_hash": self.canonical_state_hash(),
        }


def starter_agent(obs: dict[str, Any]) -> dict[str, Any]:
    return upstream.starter_agent(obs)
