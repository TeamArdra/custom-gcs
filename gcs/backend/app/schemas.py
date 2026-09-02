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
    current: float | None = None
    percentage: float | None = None


class PositionResponse(BaseModel):
    x: float
    y: float
    z: float


class PoseResponse(BaseModel):
    position: PositionResponse | None = None


class VelocityResponse(BaseModel):
    x: float
    y: float
    z: float


class AttitudeResponse(BaseModel):
    """Orientation quaternion straight from /mavros/imu/data -- left as a
    quaternion rather than converted to Euler angles here, so the backend
    doesn't silently pick a convention the frontend didn't ask for."""

    x: float
    y: float
    z: float
    w: float


class GpsResponse(BaseModel):
    fix_status: int | None = None
    satellites_visible: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None


class StatusTextResponse(BaseModel):
    severity: int
    text: str


class FcuStateResponse(BaseModel):
    """Straight from /mavros/state. `connected` here is the FCU<->MAVROS
    link (distinct from TelemetryResponse.connected, which is the GCS<->
    rosbridge link) -- both can fail independently and the operator needs
    to tell them apart."""

    connected: bool | None = None
    armed: bool | None = None
    guided: bool | None = None
    mode: str | None = None
    system_status: int | None = None


class TelemetryResponse(BaseModel):
    connected: bool
    mission_state: str | None = None
    fcu: FcuStateResponse = FcuStateResponse()
    battery: BatteryResponse
    pose: PoseResponse
    velocity: VelocityResponse | None = None
    attitude: AttitudeResponse | None = None
    gps: GpsResponse | None = None
    statustext: list[StatusTextResponse] = []
    heartbeat_age_s: float | None = None


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
