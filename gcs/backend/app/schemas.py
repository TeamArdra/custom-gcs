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


class AutonomyStateResponse(BaseModel):
    """Structured "Active Thinking" panel state -- fixed vocabulary only,
    never free-form/LLM-generated text. See
    CHECKPOINT/docs/gcs_telemetry_contract.md and
    onboard-autonomy/nidar_autonomy/telemetry_contract.py."""

    state: str | None = None
    objective: str | None = None
    target: list[float] | None = None
    next_action: str | None = None


class SensorsResponse(BaseModel):
    slam: str | None = None
    lidar: str | None = None
    rangefinder: str | None = None
    camera: str | None = None


class MappingStatusResponse(BaseModel):
    """Lightweight mapping *summary* -- the full occupancy grid is served
    separately via GET /api/map, not duplicated here."""

    available: bool = False
    resolution_m: float | None = None
    width_cells: int | None = None
    height_cells: int | None = None
    origin_x: float | None = None
    origin_y: float | None = None
    coverage_cell_size_m: float | None = None
    explored_pct: float | None = None


class NavigationResponse(BaseModel):
    target: list[float] | None = None
    frontier_count: int | None = None
    candidate_count: int | None = None
    blacklisted_count: int | None = None
    geofence_breached: bool | None = None


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
    # Mapping/exploration/planning/autonomy state, sourced from
    # /telemetry/state (onboard-autonomy's normalized contract -- see
    # CHECKPOINT/docs/gcs_telemetry_contract.md). Independent of the
    # fields above, which stay sourced directly from raw mavros topics
    # exactly as before this was added -- this is additive, not a
    # replacement of an already-verified source of truth (Checkpoint 1-4).
    autonomy: AutonomyStateResponse = AutonomyStateResponse()
    sensors: SensorsResponse = SensorsResponse()
    mapping: MappingStatusResponse = MappingStatusResponse()
    navigation: NavigationResponse = NavigationResponse()


class MapResponse(BaseModel):
    resolution: float | None = None
    width: int | None = None
    height: int | None = None
    data: list[int] | None = None


class CoverageResponse(BaseModel):
    """Same shape as MapResponse -- the coverage grid is also a
    nav_msgs/OccupancyGrid, just with different cell semantics (-1=unknown,
    0=free-not-yet-searched, 100=searched). See
    CHECKPOINT/docs/gcs_telemetry_contract.md."""

    resolution: float | None = None
    width: int | None = None
    height: int | None = None
    data: list[int] | None = None


class PathPointResponse(BaseModel):
    x: float
    y: float


class PathResponse(BaseModel):
    """Flattened from nav_msgs/Path -- the frontend only needs the
    waypoint list, not the full PoseStamped structure per point."""

    points: list[PathPointResponse] = []


class SurvivorResponse(BaseModel):
    survivor_id: int
    x: float
    y: float
    confidence: float


class CommandResponse(BaseModel):
    status: str
    command: str


class SimulationCommandResponse(BaseModel):
    """Deliberately a DIFFERENT type from CommandResponse -- see
    SimulationStatusResponse's own docstring for why this repo never
    reuses a real-telemetry/real-command response type for simulation
    data, even where the shape would otherwise match."""

    status: str
    command: str


class SimulationStatusResponse(BaseModel):
    """The simulation's own status -- a DELIBERATELY DIFFERENT Pydantic
    type from TelemetryResponse, not just a relabeled copy, so a
    simulation response can never be structurally confused with real
    Pixhawk telemetry even by a caller that forgot to check `source`.
    See CHECKPOINT/CURRENT_STATE.md and
    onboard-autonomy/nidar_autonomy/simulation_node.py, the only thing
    that ever produces the data behind this response.

    `status` is the simulation's own lifecycle ("idle"/"running"/
    "completed"/"failed") -- distinct from `mission_state`, which is the
    simulated MISSION's lifecycle (idle/entering/searching/exiting/
    complete/aborted, same vocabulary as the real system's
    /mission/state, but from this simulator's own, separate state
    machine instance)."""

    source: str = "simulation"
    status: str = "idle"
    mission_state: str = "idle"
    step: int = 0
    elapsed_sim_seconds: float = 0.0
    pose: PositionResponse | None = None
    autonomy: AutonomyStateResponse = AutonomyStateResponse()
    sensors: SensorsResponse = SensorsResponse()
    mapping: MappingStatusResponse = MappingStatusResponse()
    navigation: NavigationResponse = NavigationResponse()
    # Two different metrics -- see
    # onboard-autonomy/nidar_autonomy/mission_simulator.py's
    # SimulationSnapshot docstring for why they diverge sharply and both
    # matter: map_known_pct is "how much of the arena has been
    # discovered" (grows progressively -- render this as the headline
    # exploration-progress indicator); coverage_search_pct is "of what's
    # currently known, how much has the camera actually searched"
    # (saturates near 100% quickly -- a different, narrower question).
    map_known_pct: float = 0.0
    coverage_search_pct: float = 0.0
    error: str | None = None
