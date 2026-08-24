"""API response shapes. Deliberately re-shaped/flattened from the raw ROS
message dicts (see docs/DATA_MODELS.md) into plain, frontend-friendly
JSON -- the frontend should never need to know what a PoseStamped or an
OccupancyGrid is."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    connected: bool
    rosbridge_host: str
    rosbridge_port: int


class BatteryResponse(BaseModel):
    voltage: float | None = None
    percentage: float | None = None


class PositionResponse(BaseModel):
    x: float
    y: float
    z: float


class PoseResponse(BaseModel):
    position: PositionResponse | None = None


class TelemetryResponse(BaseModel):
    connected: bool
    mission_state: str | None = None
    battery: BatteryResponse
    pose: PoseResponse


class MapResponse(BaseModel):
    resolution: float | None = None
    width: int | None = None
    height: int | None = None
    data: list[int] | None = None


class SurvivorResponse(BaseModel):
    survivor_id: int
    x: float
    y: float
    confidence: float


class CommandResponse(BaseModel):
    status: str
    command: str
