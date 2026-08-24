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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .ros_client import BATTERY_TOPIC, MAP_TOPIC, MISSION_STATE_TOPIC, POSE_TOPIC, RosBridgeClient
from .schemas import (
    BatteryResponse,
    CommandResponse,
    HealthResponse,
    MapResponse,
    PoseResponse,
    PositionResponse,
    SurvivorResponse,
    TelemetryResponse,
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
        position = (pose_msg.get("pose") or {}).get("position")

        return TelemetryResponse(
            connected=ros_client.is_connected,
            mission_state=state_msg.get("data"),
            battery=BatteryResponse(
                voltage=battery_msg.get("voltage"), percentage=battery_msg.get("percentage")
            ),
            pose=PoseResponse(position=PositionResponse(**position) if position else None),
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

    @app.get("/api/survivors", response_model=list[SurvivorResponse], tags=["survivors"])
    def survivors() -> list[SurvivorResponse]:
        return [SurvivorResponse(**s) for s in ros_client.survivors()]

    @app.post("/api/command/start", response_model=CommandResponse, tags=["command"])
    def start_mission() -> CommandResponse:
        ros_client.publish_command("start")
        return CommandResponse(status="sent", command="start")

    @app.post("/api/command/abort", response_model=CommandResponse, tags=["command"])
    def abort_mission() -> CommandResponse:
        ros_client.publish_command("abort")
        return CommandResponse(status="sent", command="abort")

    return app


app = create_app()
