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
}

export interface MapResponse {
  resolution: number | null;
  width: number | null;
  height: number | null;
  data: number[] | null;
}

export interface SurvivorResponse {
  survivor_id: number;
  x: number;
  y: number;
  confidence: number;
}

export interface CommandResponse {
  status: string;
  command: string;
}

// The operator command surface is exactly these two -- see
// custom-gcs/CLAUDE.md Important Constraints #1. Do not widen this type.
export type Command = "start" | "abort";
