from main import PLOTS, agent


def empty_observation() -> dict:
    tiles = [[None if x < 5 and y < 5 else "LOCKED" for x in range(10)] for y in range(10)]
    farm = {
        "money": 3000.0,
        "tiles": tiles,
        "farmer": [4, 4],
        "hands": [],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    private = {
        "shed": {},
        "seeds": {"WHEAT": 0, "CARROT": 0, "TOMATO": 0, "STRAWBERRY": 0, "MELON": 0},
        "inventories": [{}],
    }
    return {"player": 0, "farms": [farm, farm.copy()], "private": private, "day": 0, "hour": 0}


def test_plot_roster_is_sixteen_unique_owned_tiles() -> None:
    assert len(PLOTS) == 16
    assert len(set(PLOTS)) == 16
    assert all(0 <= x < 5 and 0 <= y < 5 for x, y in PLOTS)


def test_initial_action_shape_and_budget() -> None:
    action = agent(empty_observation())
    assert set(action) == {"farmer", "hands", "market"}
    assert isinstance(action["farmer"], list) and action["farmer"]
    assert action["hands"] == []
    assert len(action["market"]) <= 10
    assert sum(order[0] == "HIRE" for order in action["market"]) == 5
    assert any(order[:2] == ["BUY_SEED", "MELON"] for order in action["market"])


def test_missing_state_returns_valid_pass() -> None:
    assert agent({}) == {"farmer": ["PASS"], "hands": [], "market": []}
