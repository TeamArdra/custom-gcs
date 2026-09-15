"""FastAPI app factory.

`create_app()` with no arguments builds the real thing: connects to
rosbridge at startup per Settings (app/config.py) and disconnects at
shutdown. Tests instead pass `client=<a fake>` to get an app wired to a
test double with no real networking -- see tests/fakes.py.

The API surface is intentionally small. In particular: there is no route
that can modify navigation, the map, or survivor tags, and there are
exactly three mutating routes affecting the REAL mission (POST
/api/command/start, POST /api/mission/start, POST /api/command/abort).
Mission selection (POST /api/mission/start, backed by app/missions.py's
static registry) only ever parameterizes *which* mission profile a
subsequent real "start" applies to -- Main NIDAR Competition or Flight
Test -- it does not add a new kind of operator action beyond start/abort;
it still, ultimately, only ever publishes a "start" (plus routing
metadata on /gcs/mission_select, not a command) to the drone. That is not
a convention the frontend is trusted to respect -- it's true because no
other route touching the real mission/flight-control path exists. See
docs/REQUIREMENTS.md §6 and docs/CLAUDE.md "Important Constraints" §1.

Separately, POST /api/simulation/run and POST /api/simulation/reset
control a self-contained, ROS-topic-isolated simulation (see
onboard-autonomy/nidar_autonomy/simulation_node.py and
CHECKPOINT/CURRENT_STATE.md) -- these publish to /simulation/command,
NEVER to the real /gcs/command, and cannot affect the real mission state
machine or the real Pixhawk under any circumstance (that ROS node never
imports mavros_msgs/flight_command.py at all).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import Settings, get_settings
from .missions import (
    MISSION_REGISTRY,
    MissionDefinition,
    MissionNotFoundError,
    ScenarioDefinition,
    ScenarioNotFoundError,
    get_mission,
    get_scenario,
)
from .ros_client import (
    BATTERY_TOPIC,
    COVERAGE_GRID_TOPIC,
    FCU_STATE_TOPIC,
    FLIGHT_TEST_STATUS_TOPIC,
    FRONTIERS_TOPIC,
    GPS_TOPIC,
    HEARTBEAT_TOPIC,
    IMU_TOPIC,
    MAP_TOPIC,
    MISSION_STATE_TOPIC,
    MULTI_STEP_TEST_STATUS_TOPIC,
    PERCEPTION_DETECTIONS_TOPIC,
    PERCEPTION_STATUS_TOPIC,
    PLANNED_PATH_TOPIC,
    POSE_TOPIC,
    SIMULATION_COVERAGE_GRID_TOPIC,
    SIMULATION_MAP_TOPIC,
    SIMULATION_MISSION_STATE_TOPIC,
    SIMULATION_PLANNED_PATH_TOPIC,
    SIMULATION_STATUS_TOPIC,
    SIMULATION_TELEMETRY_STATE_TOPIC,
    TELEMETRY_STATE_TOPIC,
    VELOCITY_TOPIC,
    RosBridgeClient,
)
from .schemas import (
    AttitudeResponse,
    AutonomyStateResponse,
    BatteryResponse,
    CameraStatusResponse,
    CommandResponse,
    CoverageResponse,
    FcuStateResponse,
    FlightTestStatusResponse,
    FrontierPointResponse,
    FrontiersResponse,
    GpsResponse,
    HealthResponse,
    MapResponse,
    MappingStatusResponse,
    MissionResponse,
    MissionStartRequest,
    MissionStartResponse,
    MultiStepFlightTestStatusResponse,
    NavigationResponse,
    PathPointResponse,
    PathResponse,
    PerceptionDetectionsResponse,
    PerceptionStatusResponse,
    PoseResponse,
    PositionResponse,
    ScenarioResponse,
    SensorsResponse,
    SimulationCommandResponse,
    SimulationStatusResponse,
    StatusTextResponse,
    SurvivorResponse,
    TelemetryResponse,
    VelocityResponse,
)

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _scenario_to_response(scenario: ScenarioDefinition) -> ScenarioResponse:
    return ScenarioResponse(
        id=scenario.id,
        name=scenario.name,
        description=scenario.description,
        implemented=scenario.implemented,
        execution_config=scenario.execution_config,
        steps=list(scenario.steps),
    )


def _mission_to_response(mission: MissionDefinition) -> MissionResponse:
    return MissionResponse(
        id=mission.id,
        name=mission.name,
        description=mission.description,
        ui_panel=mission.ui_panel,
        required_nodes=list(mission.required_nodes),
        scenarios=[_scenario_to_response(s) for s in mission.scenarios],
    )


def create_app(client: RosBridgeClient | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    owns_client = client is None
    ros_client = client if client is not None else RosBridgeClient(
        settings.rosbridge_host, settings.rosbridge_port, settings.connect_timeout_s
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if owns_client:
            ros_client.connect()
        try:
            yield
        finally:
            if owns_client:
                ros_client.disconnect()

    app = FastAPI(
        title="NIDAR AirMouse GCS Backend",
        description=(
            "The entire operator command surface affecting the real mission "
            "is exactly three endpoints: POST /api/command/start, "
            "POST /api/mission/start, and POST /api/command/abort. Mission "
            "selection only parameterizes which mission profile a "
            "subsequent start applies to -- it is not a new kind of "
            "operator action. No other route can affect the mission -- see "
            "docs/REQUIREMENTS.md §6."
        ),
        lifespan=lifespan,
    )

    # Local-only dev convenience so a frontend on a different port (e.g. a
    # Vite dev server) can call this API. Never exposed beyond the local
    # link per the competition's no-external-network constraint.
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.get("/health", response_model=HealthResponse, tags=["status"])
    def health() -> HealthResponse:
        return HealthResponse(
            connected=ros_client.is_connected,
            rosbridge_host=settings.rosbridge_host,
            rosbridge_port=settings.rosbridge_port,
        )

    @app.get("/api/telemetry", response_model=TelemetryResponse, tags=["telemetry"])
    def telemetry() -> TelemetryResponse:
        state_msg = ros_client.latest(MISSION_STATE_TOPIC) or {}
        battery_msg = ros_client.latest(BATTERY_TOPIC) or {}
        pose_msg = ros_client.latest(POSE_TOPIC) or {}
        fcu_msg = ros_client.latest(FCU_STATE_TOPIC) or {}
        velocity_msg = ros_client.latest(VELOCITY_TOPIC) or {}
        gps_msg = ros_client.latest(GPS_TOPIC) or {}
        imu_msg = ros_client.latest(IMU_TOPIC) or {}
        position = (pose_msg.get("pose") or {}).get("position")
        linear_velocity = (velocity_msg.get("twist") or {}).get("linear")
        orientation = imu_msg.get("orientation")
        gps_status = gps_msg.get("status") or {}

        # Mapping/exploration/planning/autonomy state -- sourced entirely
        # from /telemetry/state (onboard-autonomy's normalized contract),
        # already parsed to a dict by RosBridgeClient. Missing/not-yet-
        # published fields fall back to each response model's own
        # defaults (never fabricated) rather than raising.
        telemetry_state = ros_client.latest(TELEMETRY_STATE_TOPIC) or {}
        autonomy = telemetry_state.get("autonomy") or {}
        sensors = telemetry_state.get("sensors") or {}
        mapping = telemetry_state.get("mapping") or {}
        navigation = telemetry_state.get("navigation") or {}

        return TelemetryResponse(
            connected=ros_client.is_connected,
            mission_state=state_msg.get("data"),
            fcu=FcuStateResponse(
                connected=fcu_msg.get("connected"),
                armed=fcu_msg.get("armed"),
                guided=fcu_msg.get("guided"),
                mode=fcu_msg.get("mode"),
                system_status=fcu_msg.get("system_status"),
            ),
            battery=BatteryResponse(
                voltage=battery_msg.get("voltage"),
                current=battery_msg.get("current"),
                percentage=battery_msg.get("percentage"),
            ),
            pose=PoseResponse(position=PositionResponse(**position) if position else None),
            velocity=VelocityResponse(**linear_velocity) if linear_velocity else None,
            attitude=AttitudeResponse(**orientation) if orientation else None,
            gps=GpsResponse(
                fix_status=gps_status.get("status"),
                satellites_visible=gps_msg.get("satellites_visible"),
                latitude=gps_msg.get("latitude"),
                longitude=gps_msg.get("longitude"),
                altitude=gps_msg.get("altitude"),
            )
            if gps_msg
            else None,
            statustext=[
                StatusTextResponse(severity=m.get("severity"), text=m.get("text"))
                for m in ros_client.statustext_history()
            ],
            heartbeat_age_s=ros_client.age_s(HEARTBEAT_TOPIC),
            autonomy=AutonomyStateResponse(
                state=autonomy.get("state"),
                objective=autonomy.get("objective"),
                target=autonomy.get("target"),
                next_action=autonomy.get("next_action"),
            ),
            sensors=SensorsResponse(
                slam=sensors.get("slam"),
                lidar=sensors.get("lidar"),
                rangefinder=sensors.get("rangefinder"),
                camera=sensors.get("camera"),
            ),
            mapping=MappingStatusResponse(
                available=bool(mapping.get("available", False)),
                resolution_m=mapping.get("resolution_m"),
                width_cells=mapping.get("width_cells"),
                height_cells=mapping.get("height_cells"),
                origin_x=mapping.get("origin_x"),
                origin_y=mapping.get("origin_y"),
                coverage_cell_size_m=mapping.get("coverage_cell_size_m"),
                explored_pct=mapping.get("explored_pct"),
            ),
            navigation=NavigationResponse(
                target=navigation.get("target"),
                frontier_count=navigation.get("frontier_count"),
                candidate_count=navigation.get("candidate_count"),
                blacklisted_count=navigation.get("blacklisted_count"),
                geofence_breached=navigation.get("geofence_breached"),
            ),
        )

    @app.get("/api/map", response_model=MapResponse, tags=["map"])
    def map_snapshot() -> MapResponse:
        msg = ros_client.latest(MAP_TOPIC)
        if msg is None:
            return MapResponse()
        info = msg.get("info", {})
        return MapResponse(
            resolution=info.get("resolution"),
            width=info.get("width"),
            height=info.get("height"),
            data=msg.get("data"),
        )

    @app.get("/api/coverage", response_model=CoverageResponse, tags=["map"])
    def coverage_snapshot() -> CoverageResponse:
        msg = ros_client.latest(COVERAGE_GRID_TOPIC)
        if msg is None:
            return CoverageResponse()
        info = msg.get("info", {})
        return CoverageResponse(
            resolution=info.get("resolution"),
            width=info.get("width"),
            height=info.get("height"),
            data=msg.get("data"),
        )

    @app.get("/api/path", response_model=PathResponse, tags=["map"])
    def planned_path() -> PathResponse:
        msg = ros_client.latest(PLANNED_PATH_TOPIC)
        if msg is None:
            return PathResponse()
        points = [
            PathPointResponse(
                x=(pose.get("pose") or {}).get("position", {}).get("x", 0.0),
                y=(pose.get("pose") or {}).get("position", {}).get("y", 0.0),
            )
            for pose in msg.get("poses", [])
        ]
        return PathResponse(points=points)

    @app.get("/api/frontiers", response_model=FrontiersResponse, tags=["map"])
    def frontiers() -> FrontiersResponse:
        msg = ros_client.latest(FRONTIERS_TOPIC)
        if msg is None:
            return FrontiersResponse()
        # visualization_msgs/Marker.pose is a plain geometry_msgs/Pose, one
        # level of nesting less than nav_msgs/Path's PoseStamped poses (see
        # planned_path() above) -- position is at marker["pose"]["position"],
        # not marker["pose"]["pose"]["position"].
        points = [
            FrontierPointResponse(
                x=(marker.get("pose") or {}).get("position", {}).get("x", 0.0),
                y=(marker.get("pose") or {}).get("position", {}).get("y", 0.0),
            )
            for marker in msg.get("markers", [])
        ]
        return FrontiersResponse(points=points)

    @app.get("/api/survivors", response_model=list[SurvivorResponse], tags=["survivors"])
    def survivors() -> list[SurvivorResponse]:
        return [SurvivorResponse(**s) for s in ros_client.survivors()]

    # -- Perception pipeline (Jetson-side, development-only pretrained
    # person-detector) -- read-only, and architecturally distinct from
    # /api/survivors above: raw/unconfirmed/image-space vs.
    # confirmed/localized/world-coordinate. See
    # PerceptionDetectionsResponse/DetectionResponse docstrings in
    # app/schemas.py. Video bytes never flow through this backend -- see
    # docs/DECISIONS.md D-6 -- /api/camera/status only reports health/
    # metadata plus the stream URL the frontend fetches directly.

    @app.get(
        "/api/perception/detections",
        response_model=PerceptionDetectionsResponse,
        tags=["perception"],
    )
    def perception_detections() -> PerceptionDetectionsResponse:
        msg = ros_client.latest(PERCEPTION_DETECTIONS_TOPIC)
        if not msg:
            return PerceptionDetectionsResponse()
        try:
            return PerceptionDetectionsResponse(**msg)
        except ValidationError:
            # A cached-but-malformed upstream payload (wrong field type from
            # a buggy/malfunctioning publisher) must degrade the same way
            # "no data yet" does, not surface as a bare 500 to every caller.
            return PerceptionDetectionsResponse()

    @app.get(
        "/api/perception/status",
        response_model=PerceptionStatusResponse,
        tags=["perception"],
    )
    def perception_status() -> PerceptionStatusResponse:
        msg = ros_client.latest(PERCEPTION_STATUS_TOPIC)
        if not msg:
            return PerceptionStatusResponse()
        allowed = set(PerceptionStatusResponse.model_fields)
        try:
            return PerceptionStatusResponse(**{k: v for k, v in msg.items() if k in allowed})
        except ValidationError:
            # See perception_detections above -- same degrade-not-500 rule.
            return PerceptionStatusResponse()

    @app.get("/api/camera/status", response_model=CameraStatusResponse, tags=["camera"])
    def camera_status() -> CameraStatusResponse:
        msg = ros_client.latest(PERCEPTION_STATUS_TOPIC)
        connected = bool(msg.get("camera_connected")) if msg else None
        try:
            return CameraStatusResponse(
                connected=connected,
                stream_url=settings.camera_stream_url() if connected else None,
                frame_width=(msg.get("frame_width") if msg else None),
                frame_height=(msg.get("frame_height") if msg else None),
                fps=(msg.get("fps") if msg else None),
            )
        except ValidationError:
            # See perception_detections above -- same degrade-not-500 rule.
            return CameraStatusResponse()

    @app.post("/api/command/start", response_model=CommandResponse, tags=["command"])
    def start_mission() -> CommandResponse:
        try:
            ros_client.publish_command("start")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=f"{exc} -- command not sent") from exc
        return CommandResponse(status="sent", command="start")

    @app.post("/api/command/abort", response_model=CommandResponse, tags=["command"])
    def abort_mission() -> CommandResponse:
        try:
            ros_client.publish_command("abort")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=f"{exc} -- command not sent") from exc
        return CommandResponse(status="sent", command="abort")

    # -- Multi-mission framework ---------------------------------------------
    #
    # app/missions.py's static registry is the only source of truth for
    # which missions/scenarios exist -- these routes only ever read it
    # (never mutate it) and, for POST /api/mission/start, publish routing
    # metadata (/gcs/mission_select) immediately before the same "start"
    # publish_command() above already sends. This does not add a new kind
    # of operator action: it is still only ever "start" or "abort"
    # reaching the drone, see the module docstring.

    @app.get("/api/missions", response_model=list[MissionResponse], tags=["missions"])
    def list_missions() -> list[MissionResponse]:
        return [_mission_to_response(m) for m in MISSION_REGISTRY]

    @app.get("/api/missions/{mission_id}", response_model=MissionResponse, tags=["missions"])
    def get_mission_detail(mission_id: str) -> MissionResponse:
        try:
            return _mission_to_response(get_mission(mission_id))
        except MissionNotFoundError:
            raise HTTPException(status_code=404, detail=f"unknown mission: {mission_id!r}")

    @app.get(
        "/api/missions/{mission_id}/scenarios",
        response_model=list[ScenarioResponse],
        tags=["missions"],
    )
    def get_mission_scenario_list(mission_id: str) -> list[ScenarioResponse]:
        try:
            mission = get_mission(mission_id)
        except MissionNotFoundError:
            raise HTTPException(status_code=404, detail=f"unknown mission: {mission_id!r}")
        return [_scenario_to_response(s) for s in mission.scenarios]

    @app.get("/api/flight-test/status", response_model=FlightTestStatusResponse, tags=["flight_test"])
    def flight_test_status() -> FlightTestStatusResponse:
        msg = ros_client.latest(FLIGHT_TEST_STATUS_TOPIC)
        if not msg:
            return FlightTestStatusResponse()
        allowed = set(FlightTestStatusResponse.model_fields)
        try:
            return FlightTestStatusResponse(**{k: v for k, v in msg.items() if k in allowed})
        except ValidationError:
            # Malformed cached data degrades to defaults, same
            # degrade-not-500 rule as the perception routes above.
            return FlightTestStatusResponse()

    @app.get(
        "/api/flight-test/multi-step/status",
        response_model=MultiStepFlightTestStatusResponse,
        tags=["flight_test"],
    )
    def multi_step_flight_test_status() -> MultiStepFlightTestStatusResponse:
        msg = ros_client.latest(MULTI_STEP_TEST_STATUS_TOPIC)
        if not msg:
            return MultiStepFlightTestStatusResponse()
        allowed = set(MultiStepFlightTestStatusResponse.model_fields)
        try:
            return MultiStepFlightTestStatusResponse(**{k: v for k, v in msg.items() if k in allowed})
        except ValidationError:
            # Same degrade-not-500 rule as flight_test_status above.
            return MultiStepFlightTestStatusResponse()

    @app.post("/api/mission/start", response_model=MissionStartResponse, tags=["missions"])
    def start_mission_by_id(body: MissionStartRequest) -> MissionStartResponse:
        try:
            scenario = get_scenario(body.mission, body.scenario)
        except MissionNotFoundError:
            raise HTTPException(status_code=404, detail=f"unknown mission: {body.mission!r}")
        except ScenarioNotFoundError:
            raise HTTPException(
                status_code=400,
                detail=f"unknown scenario {body.scenario!r} for mission {body.mission!r}",
            )
        if not scenario.implemented:
            raise HTTPException(status_code=400, detail=f"scenario {body.scenario!r} is not yet implemented")

        # Reject if anything is already active -- derived from real ROS
        # state, not backend bookkeeping. Both flight-test status topics
        # are checked (hover_test_node and multi_step_test_node are
        # separate ROS nodes, but only one flight-test scenario can
        # meaningfully run at a time from the operator's perspective) --
        # see MULTI_STEP_TEST_STATUS_TOPIC's docstring in app/ros_client.py
        # for why they're separate topics in the first place.
        mission_state_msg = ros_client.latest(MISSION_STATE_TOPIC) or {}
        real_mission_state = mission_state_msg.get("data")
        flight_test_msg = ros_client.latest(FLIGHT_TEST_STATUS_TOPIC) or {}
        flight_test_state = flight_test_msg.get("state")
        multi_step_msg = ros_client.latest(MULTI_STEP_TEST_STATUS_TOPIC) or {}
        multi_step_state = multi_step_msg.get("state")
        if real_mission_state in ("entering", "searching", "exiting"):
            raise HTTPException(
                status_code=409,
                detail=f"cannot start: Main NIDAR mission is already active (state={real_mission_state!r})",
            )
        if flight_test_state not in (None, "idle", "complete", "aborted"):
            raise HTTPException(
                status_code=409,
                detail=f"cannot start: Flight Test is already active (state={flight_test_state!r})",
            )
        if multi_step_state not in (None, "idle", "complete", "aborted", "failed"):
            raise HTTPException(
                status_code=409,
                detail=f"cannot start: Flight Test is already active (state={multi_step_state!r})",
            )

        try:
            ros_client.publish_mission_select(body.mission, body.scenario)
            ros_client.publish_command("start")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=f"{exc} -- command not sent") from exc
        return MissionStartResponse(status="sent", mission=body.mission, scenario=body.scenario)

    # -- Simulation control surface -----------------------------------------
    #
    # Entirely separate from the real command/telemetry surface above:
    # different publish method (publish_simulation_command, never
    # publish_command), different topic (/simulation/command, never
    # /gcs/command), different response type (SimulationStatusResponse,
    # never TelemetryResponse). See CHECKPOINT/CURRENT_STATE.md and
    # onboard-autonomy/nidar_autonomy/simulation_node.py.

    @app.post("/api/simulation/run", response_model=SimulationCommandResponse, tags=["simulation"])
    def run_simulation() -> SimulationCommandResponse:
        try:
            ros_client.publish_simulation_command("run")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=f"{exc} -- command not sent") from exc
        return SimulationCommandResponse(status="sent", command="run")

    @app.post("/api/simulation/reset", response_model=SimulationCommandResponse, tags=["simulation"])
    def reset_simulation() -> SimulationCommandResponse:
        try:
            ros_client.publish_simulation_command("reset")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=f"{exc} -- command not sent") from exc
        return SimulationCommandResponse(status="sent", command="reset")

    @app.get("/api/simulation/status", response_model=SimulationStatusResponse, tags=["simulation"])
    def simulation_status() -> SimulationStatusResponse:
        contract = ros_client.latest(SIMULATION_TELEMETRY_STATE_TOPIC) or {}
        status_msg = ros_client.latest(SIMULATION_STATUS_TOPIC) or {}
        mission_state_msg = ros_client.latest(SIMULATION_MISSION_STATE_TOPIC) or {}
        autonomy = contract.get("autonomy") or {}
        sensors = contract.get("sensors") or {}
        mapping = contract.get("mapping") or {}
        navigation = contract.get("navigation") or {}
        position = contract.get("position") or {}

        return SimulationStatusResponse(
            status=status_msg.get("data", "idle"),
            mission_state=mission_state_msg.get("data", "idle"),
            step=contract.get("simulation_step", 0),
            elapsed_sim_seconds=(contract.get("mission") or {}).get("elapsed_sec", 0.0) or 0.0,
            pose=PositionResponse(x=position["x"], y=position["y"], z=position["z"])
            if position.get("x") is not None
            else None,
            autonomy=AutonomyStateResponse(
                state=autonomy.get("state"),
                objective=autonomy.get("objective"),
                target=autonomy.get("target"),
                next_action=autonomy.get("next_action"),
            ),
            sensors=SensorsResponse(
                slam=sensors.get("slam"),
                lidar=sensors.get("lidar"),
                rangefinder=sensors.get("rangefinder"),
                camera=sensors.get("camera"),
            ),
            mapping=MappingStatusResponse(
                available=bool(mapping.get("available", False)),
                resolution_m=mapping.get("resolution_m"),
                width_cells=mapping.get("width_cells"),
                height_cells=mapping.get("height_cells"),
                origin_x=mapping.get("origin_x"),
                origin_y=mapping.get("origin_y"),
                coverage_cell_size_m=mapping.get("coverage_cell_size_m"),
                explored_pct=mapping.get("explored_pct"),
            ),
            navigation=NavigationResponse(
                target=navigation.get("target"),
                frontier_count=navigation.get("frontier_count"),
                candidate_count=navigation.get("candidate_count"),
                blacklisted_count=navigation.get("blacklisted_count"),
                geofence_breached=navigation.get("geofence_breached"),
            ),
            map_known_pct=mapping.get("explored_pct") or 0.0,
            coverage_search_pct=contract.get("coverage_search_pct", 0.0) or 0.0,
            error=contract.get("error"),
        )

    @app.get("/api/simulation/map", response_model=MapResponse, tags=["simulation"])
    def simulation_map() -> MapResponse:
        msg = ros_client.latest(SIMULATION_MAP_TOPIC)
        if msg is None:
            return MapResponse()
        info = msg.get("info", {})
        return MapResponse(
            resolution=info.get("resolution"),
            width=info.get("width"),
            height=info.get("height"),
            data=msg.get("data"),
        )

    @app.get("/api/simulation/coverage", response_model=CoverageResponse, tags=["simulation"])
    def simulation_coverage() -> CoverageResponse:
        msg = ros_client.latest(SIMULATION_COVERAGE_GRID_TOPIC)
        if msg is None:
            return CoverageResponse()
        info = msg.get("info", {})
        return CoverageResponse(
            resolution=info.get("resolution"),
            width=info.get("width"),
            height=info.get("height"),
            data=msg.get("data"),
        )

    @app.get("/api/simulation/path", response_model=PathResponse, tags=["simulation"])
    def simulation_path() -> PathResponse:
        msg = ros_client.latest(SIMULATION_PLANNED_PATH_TOPIC)
        if msg is None:
            return PathResponse()
        points = [
            PathPointResponse(
                x=(pose.get("pose") or {}).get("position", {}).get("x", 0.0),
                y=(pose.get("pose") or {}).get("position", {}).get("y", 0.0),
            )
            for pose in msg.get("poses", [])
        ]
        return PathResponse(points=points)

    # Static operator UI (React, built via `npm run build` in
    # gcs/frontend/ -- see gcs/frontend/README.md), mounted at /ui (not
    # /) so it can never intercept an unmatched API path -- StaticFiles
    # returns 405 for non-GET/HEAD requests to anything under its mount,
    # which would otherwise shadow
    # test_no_route_exists_beyond_the_documented_command_surface's 404
    # expectation for forbidden paths if mounted at "/". Serves the
    # *build output* (frontend/dist/), not frontend/ source, and is
    # simply absent (mount skipped) if dist/ hasn't been built yet --
    # /ui/ 404s rather than serving raw source or crashing. Calls this
    # same API over HTTP, nothing else -- see gcs/frontend/.
    if _FRONTEND_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")

    return app


app = create_app()
