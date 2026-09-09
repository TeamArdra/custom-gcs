"""FastAPI app factory.

`create_app()` with no arguments builds the real thing: connects to
rosbridge at startup per Settings (app/config.py) and disconnects at
shutdown. Tests instead pass `client=<a fake>` to get an app wired to a
test double with no real networking -- see tests/fakes.py.

The API surface is intentionally small. In particular: there is no route
that can modify navigation, the map, or survivor tags, and there are
exactly two mutating routes in the whole app (POST /api/command/start,
POST /api/command/abort). That is not a convention the frontend is
trusted to respect -- it's true because no other route exists. See
docs/REQUIREMENTS.md §6 and docs/CLAUDE.md "Important Constraints" §1.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .ros_client import (
    BATTERY_TOPIC,
    COVERAGE_GRID_TOPIC,
    FCU_STATE_TOPIC,
    GPS_TOPIC,
    HEARTBEAT_TOPIC,
    IMU_TOPIC,
    MAP_TOPIC,
    MISSION_STATE_TOPIC,
    PLANNED_PATH_TOPIC,
    POSE_TOPIC,
    TELEMETRY_STATE_TOPIC,
    VELOCITY_TOPIC,
    RosBridgeClient,
)
from .schemas import (
    AttitudeResponse,
    AutonomyStateResponse,
    BatteryResponse,
    CommandResponse,
    CoverageResponse,
    FcuStateResponse,
    GpsResponse,
    HealthResponse,
    MapResponse,
    MappingStatusResponse,
    NavigationResponse,
    PathPointResponse,
    PathResponse,
    PoseResponse,
    PositionResponse,
    SensorsResponse,
    StatusTextResponse,
    SurvivorResponse,
    TelemetryResponse,
    VelocityResponse,
)

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"


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
            "The entire operator command surface is exactly two endpoints: "
            "POST /api/command/start and POST /api/command/abort. No other "
            "route can affect the mission -- see docs/REQUIREMENTS.md §6."
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

    @app.get("/api/survivors", response_model=list[SurvivorResponse], tags=["survivors"])
    def survivors() -> list[SurvivorResponse]:
        return [SurvivorResponse(**s) for s in ros_client.survivors()]

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
