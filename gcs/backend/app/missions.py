"""Mission/scenario registry -- the single source of truth for which
missions and scenarios the GCS knows how to start. Deliberately static,
in-process data (not fetched from anywhere, not dynamically registered)
so `app/main.py`'s routes can validate a mission-start request without
trusting anything the frontend or rosbridge sends. See
docs/COMMUNICATION.md's mission-select addendum for the wire contract
this feeds (`/gcs/mission_select`) and onboard-autonomy's
`hover_test_node`/`multi_step_test_node`/`mission_state_node.py` guard
for the ROS-side half of this agreement -- this module only owns the
GCS-side registry, it does not launch or configure any ROS node itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScenarioDefinition:
    id: str
    name: str
    description: str
    implemented: bool
    # Informational/display only in this task -- NOT piped through
    # publish_command()/publish_mission_select() in any way; a future
    # task may wire this into the mission-select payload, this one does
    # not.
    execution_config: dict = field(default_factory=dict)
    # Ordered action names for a composed multi-step scenario (e.g.
    # ("forward", "backward", "hover")) -- informational/display only,
    # mirrors onboard-autonomy's nidar_autonomy/flight_test/scenarios.py
    # MultiStepScenario.steps. Empty tuple means "not a composed
    # multi-step scenario" (the single-shot "hover" scenario also sets
    # this purely for display; it does not change hover_test_node.py's
    # own behavior).
    steps: tuple[str, ...] = ()


@dataclass(frozen=True)
class MissionDefinition:
    id: str
    name: str
    description: str
    ui_panel: str  # "nidar" | "flight_test" -- tells the frontend which panel set to show
    required_nodes: tuple[str, ...]  # informational metadata only, not dynamically launched by this backend
    scenarios: tuple[ScenarioDefinition, ...]


MISSION_REGISTRY: tuple[MissionDefinition, ...] = (
    MissionDefinition(
        id="main_nidar",
        name="Main NIDAR Competition",
        description="The complete, canonical NIDAR AirMouse autonomous mission.",
        ui_panel="nidar",
        required_nodes=(
            "command_node", "mission_state_node", "heartbeat_node",
            "telemetry_bridge_node", "coverage_tracker_node",
            "frontier_explorer_node", "geofence_monitor_node", "perception_node",
        ),
        scenarios=(
            ScenarioDefinition(
                id="full_mission", name="Full NIDAR Mission",
                description="Autonomous entry, mapping, exploration, survivor detection, and exit.",
                implemented=True,
            ),
        ),
    ),
    MissionDefinition(
        id="flight_test",
        name="Flight Test",
        description="Individual controlled test scenarios for bench/development flight validation.",
        ui_panel="flight_test",
        required_nodes=("command_node", "hover_test_node", "multi_step_test_node"),
        scenarios=(
            ScenarioDefinition(
                id="hover", name="Hover",
                description=(
                    "Arm, take off to a target altitude, hold for a fixed "
                    "duration, land, disarm. Mock-only execution -- see "
                    "onboard-autonomy/nidar_autonomy/flight_test/README.md."
                ),
                implemented=True,
                execution_config={"target_altitude_m": 1.0, "duration_s": 10.0},
                steps=("takeoff", "hover", "land"),
            ),
            ScenarioDefinition(
                id="forward_backward_hover", name="Test 1: Forward / Backward / Hover",
                description=(
                    "Ordered multi-step scenario: fly forward, fly backward, "
                    "then hover. Mock-only execution -- see "
                    "onboard-autonomy/nidar_autonomy/flight_test/multi_step_test_node.py."
                ),
                implemented=True,
                steps=("forward", "backward", "hover"),
            ),
            ScenarioDefinition(
                id="sideways_hover_sideways_hover", name="Test 2: Sideways / Hover / Sideways / Hover",
                description=(
                    "Ordered multi-step scenario: sideways, hover, sideways, "
                    "hover. Mock-only execution -- see "
                    "onboard-autonomy/nidar_autonomy/flight_test/multi_step_test_node.py."
                ),
                implemented=True,
                steps=("sideways", "hover", "sideways", "hover"),
            ),
        ),
    ),
)


class MissionNotFoundError(KeyError):
    """No MissionDefinition in MISSION_REGISTRY has this id -- routes map
    this to a 404, distinct from ScenarioNotFoundError's 400, since an
    unknown mission is a different kind of client error than an unknown
    or not-yet-implemented scenario within a known mission."""


class ScenarioNotFoundError(KeyError):
    """The mission exists but has no scenario with this id -- routes map
    this to a 400 (the mission_id was fine, the scenario_id wasn't)."""


def get_mission(mission_id: str) -> MissionDefinition:
    for mission in MISSION_REGISTRY:
        if mission.id == mission_id:
            return mission
    raise MissionNotFoundError(mission_id)


def get_scenario(mission_id: str, scenario_id: str) -> ScenarioDefinition:
    mission = get_mission(mission_id)  # propagates MissionNotFoundError
    for scenario in mission.scenarios:
        if scenario.id == scenario_id:
            return scenario
    raise ScenarioNotFoundError(scenario_id)
