// Mirrors gcs/backend/app/schemas.py exactly. Keep in sync by hand --
// there is no shared codegen between the Python and TypeScript sides
// (see custom-gcs/CLAUDE.md: "Docs and interfaces before code" -- this
// file is the frontend half of that contract).

export interface HealthResponse {
  connected: boolean;
  rosbridge_host: string;
  rosbridge_port: number;
}

export interface BatteryResponse {
  voltage: number | null;
  current: number | null;
  percentage: number | null;
}

export interface PositionResponse {
  x: number;
  y: number;
  z: number;
}

export interface PoseResponse {
  position: PositionResponse | null;
}

export interface VelocityResponse {
  x: number;
  y: number;
  z: number;
}

// Orientation quaternion straight from /mavros/imu/data -- left as a
// quaternion rather than converted to Euler angles, so the frontend
// doesn't silently pick a convention the backend didn't ask for either.
export interface AttitudeResponse {
  x: number;
  y: number;
  z: number;
  w: number;
}

export interface GpsResponse {
  fix_status: number | null;
  satellites_visible: number | null;
  latitude: number | null;
  longitude: number | null;
  altitude: number | null;
}

export interface StatusTextResponse {
  severity: number;
  text: string;
}

// `connected` here is the FCU<->MAVROS link (distinct from
// TelemetryResponse.connected, which is the GCS<->rosbridge link) --
// both can fail independently and the operator needs to tell them apart.
export interface FcuStateResponse {
  connected: boolean | null;
  armed: boolean | null;
  guided: boolean | null;
  mode: string | null;
  system_status: number | null;
}

// Structured "Active Thinking" panel state -- fixed vocabulary only, never
// free-form/LLM-generated text. See
// CHECKPOINT/docs/gcs_telemetry_contract.md.
export interface AutonomyStateResponse {
  state: string | null;
  objective: string | null;
  target: [number, number] | null;
  next_action: string | null;
}

export interface SensorsResponse {
  slam: string | null;
  lidar: string | null;
  rangefinder: string | null;
  camera: string | null;
}

// Lightweight mapping *summary* -- the full occupancy grid is fetched
// separately via getMap(), not duplicated here.
export interface MappingStatusResponse {
  available: boolean;
  resolution_m: number | null;
  width_cells: number | null;
  height_cells: number | null;
  origin_x: number | null;
  origin_y: number | null;
  coverage_cell_size_m: number | null;
  explored_pct: number | null;
}

export interface NavigationResponse {
  target: [number, number] | null;
  frontier_count: number | null;
  candidate_count: number | null;
  blacklisted_count: number | null;
  geofence_breached: boolean | null;
}

export interface TelemetryResponse {
  connected: boolean;
  mission_state: string | null;
  fcu: FcuStateResponse;
  battery: BatteryResponse;
  pose: PoseResponse;
  velocity: VelocityResponse | null;
  attitude: AttitudeResponse | null;
  gps: GpsResponse | null;
  statustext: StatusTextResponse[];
  heartbeat_age_s: number | null;
  autonomy: AutonomyStateResponse;
  sensors: SensorsResponse;
  mapping: MappingStatusResponse;
  navigation: NavigationResponse;
}

export interface MapResponse {
  resolution: number | null;
  width: number | null;
  height: number | null;
  data: number[] | null;
}

// Same shape as MapResponse -- the coverage grid is also a
// nav_msgs/OccupancyGrid, just with different cell semantics (-1=unknown,
// 0=free-not-yet-searched, 100=searched).
export interface CoverageResponse {
  resolution: number | null;
  width: number | null;
  height: number | null;
  data: number[] | null;
}

export interface PathPointResponse {
  x: number;
  y: number;
}

export interface PathResponse {
  points: PathPointResponse[];
}

export interface SurvivorResponse {
  survivor_id: number;
  x: number;
  y: number;
  confidence: number;
}

// -- Perception (dev-only pretrained person-detector, image-space, raw
// detections) -- deliberately NOT SurvivorResponse: a detection here is
// unconfirmed and in image (pixel) coordinates, not a localized,
// world-x/y survivor tag. See custom-gcs/CLAUDE.md and
// gcs/backend/app/schemas.py's perception models.

export interface BBox {
  x_min: number | null;
  y_min: number | null;
  x_max: number | null;
  y_max: number | null;
}

export interface Detection {
  detection_id: string | null;
  class_name: string | null;
  confidence: number | null;
  bbox: BBox;
  center_x: number | null;
  center_y: number | null;
  track_id: string | null;
  source: string | null;
  model_name: string | null;
}

export interface PerceptionDetectionsResponse {
  frame_width: number | null;
  frame_height: number | null;
  timestamp: number | null;
  detections: Detection[];
}

export interface PerceptionStatusResponse {
  camera_connected: boolean | null;
  detector_enabled: boolean | null;
  detector_ready: boolean | null;
  detector_backend: string | null;
  model_name: string | null;
  person_count: number | null;
  fps: number | null;
  frame_width: number | null;
  frame_height: number | null;
  last_detection_age_s: number | null;
}

// Video bytes bypass the backend entirely (see docs/DECISIONS.md D-6) --
// this endpoint only tells the frontend where to point an <img> tag, it
// does not itself carry any video data.
export interface CameraStatusResponse {
  connected: boolean | null;
  stream_url: string | null;
  frame_width: number | null;
  frame_height: number | null;
  fps: number | null;
}

export interface CommandResponse {
  status: string;
  command: string;
}

// The operator command surface is exactly these two -- see
// custom-gcs/CLAUDE.md Important Constraints #1. Do not widen this type.
export type Command = "start" | "abort";

// -- Simulation ("RUN SIMULATION") -- completely separate from the real
// mission command/telemetry types above. See
// CHECKPOINT/CURRENT_STATE.md and
// onboard-autonomy/nidar_autonomy/simulation_node.py.

export interface SimulationCommandResponse {
  status: string;
  command: string;
}

// Deliberately NOT TelemetryResponse -- see gcs/backend/app/schemas.py's
// SimulationStatusResponse docstring for why this stays a distinct type
// even though several nested shapes match.
export interface SimulationStatusResponse {
  source: "simulation";
  status: "idle" | "running" | "completed" | "failed";
  mission_state: string;
  step: number;
  elapsed_sim_seconds: number;
  pose: PositionResponse | null;
  autonomy: AutonomyStateResponse;
  sensors: SensorsResponse;
  mapping: MappingStatusResponse;
  navigation: NavigationResponse;
  map_known_pct: number;
  coverage_search_pct: number;
  error: string | null;
}

// The simulation control surface is exactly these two -- never
// "start"/"abort" (that vocabulary stays exclusive to Command above).
export type SimulationCommand = "run" | "reset";
