"""Tests for app/missions.py -- the static mission/scenario registry.
Pure data/lookup tests, no FastAPI/TestClient needed."""

from app.missions import (
    MISSION_REGISTRY,
    MissionNotFoundError,
    ScenarioNotFoundError,
    get_mission,
    get_scenario,
)


def test_registry_is_non_empty():
    assert len(MISSION_REGISTRY) > 0


def test_main_nidar_mission_has_exactly_one_scenario():
    mission = get_mission("main_nidar")
    assert mission.id == "main_nidar"
    assert len(mission.scenarios) == 1
    assert mission.scenarios[0].id == "full_mission"


def test_flight_test_mission_has_hover_scenario_implemented():
    mission = get_mission("flight_test")
    assert mission.id == "flight_test"
    hover = get_scenario("flight_test", "hover")
    assert hover.implemented is True


def test_flight_test_mission_has_two_new_multi_step_scenarios_implemented():
    forward_backward_hover = get_scenario("flight_test", "forward_backward_hover")
    assert forward_backward_hover.implemented is True
    assert forward_backward_hover.steps == ("forward", "backward", "hover")

    sideways = get_scenario("flight_test", "sideways_hover_sideways_hover")
    assert sideways.implemented is True
    assert sideways.steps == ("sideways", "hover", "sideways", "hover")


def test_hover_scenario_has_display_only_steps():
    hover = get_scenario("flight_test", "hover")
    assert hover.steps == ("takeoff", "hover", "land")


def test_every_other_flight_test_scenario_is_not_implemented():
    mission = get_mission("flight_test")
    still_coming_soon = {"forward", "backward", "left", "right", "yaw", "square"}
    for scenario in mission.scenarios:
        if scenario.id in still_coming_soon:
            assert scenario.implemented is False
            assert scenario.steps == ()


def test_flight_test_mission_has_exactly_nine_scenarios():
    mission = get_mission("flight_test")
    assert len(mission.scenarios) == 9
    implemented = [s for s in mission.scenarios if s.implemented]
    assert {s.id for s in implemented} == {"hover", "forward_backward_hover", "sideways_hover_sideways_hover"}


def test_get_mission_raises_for_unknown_mission():
    try:
        get_mission("bogus")
        assert False, "expected MissionNotFoundError"
    except MissionNotFoundError:
        pass


def test_get_scenario_raises_for_unknown_scenario():
    try:
        get_scenario("flight_test", "bogus")
        assert False, "expected ScenarioNotFoundError"
    except ScenarioNotFoundError:
        pass


def test_get_scenario_raises_mission_not_found_before_scenario_lookup():
    try:
        get_scenario("bogus", "hover")
        assert False, "expected MissionNotFoundError"
    except MissionNotFoundError:
        pass
