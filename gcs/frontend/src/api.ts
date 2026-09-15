// Typed fetch wrappers around the FastAPI backend's REST API. Root-
// relative paths only -- never construct a URL with a host, so the same
// build works unmodified in dev (Vite proxy, see vite.config.ts) and in
// production (served from the same origin via FastAPI's /ui mount).

import type {
  CameraStatusResponse,
  CommandResponse,
  Command,
  CoverageResponse,
  FlightTestStatusResponse,
  FrontiersResponse,
  HealthResponse,
  MapResponse,
  Mission,
  MissionStartResponse,
  MultiStepFlightTestStatusResponse,
  PathResponse,
  PerceptionDetectionsResponse,
  PerceptionStatusResponse,
  SimulationCommand,
  SimulationCommandResponse,
  SimulationStatusResponse,
  SurvivorResponse,
  TelemetryResponse,
} from "./types";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`GET ${path} failed: HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

// FastAPI error responses carry a JSON {"detail": "..."} body (e.g. the
// 503 the backend raises for /api/command/* when rosbridge isn't
// connected -- see gcs/backend/app/main.py). Best-effort only: a non-JSON
// or bodyless error response must not itself throw here, or the operator
// would see a confusing secondary error instead of the HTTP status.
async function extractErrorDetail(res: Response): Promise<string | null> {
  try {
    const body: unknown = await res.json();
    const detail = (body as { detail?: unknown } | null)?.detail;
    return typeof detail === "string" ? detail : null;
  } catch {
    return null;
  }
}

export function getHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>("/health");
}

export function getTelemetry(): Promise<TelemetryResponse> {
  return getJson<TelemetryResponse>("/api/telemetry");
}

export function getMap(): Promise<MapResponse> {
  return getJson<MapResponse>("/api/map");
}

export function getCoverage(): Promise<CoverageResponse> {
  return getJson<CoverageResponse>("/api/coverage");
}

export function getPath(): Promise<PathResponse> {
  return getJson<PathResponse>("/api/path");
}

export function getFrontiers(): Promise<FrontiersResponse> {
  return getJson<FrontiersResponse>("/api/frontiers");
}

export function getSurvivors(): Promise<SurvivorResponse[]> {
  return getJson<SurvivorResponse[]>("/api/survivors");
}

// Perception (dev-only person-detector) -- deliberately separate from
// getSurvivors() above, see types.ts's Detection/SurvivorResponse comment.
export function getPerceptionDetections(): Promise<PerceptionDetectionsResponse> {
  return getJson<PerceptionDetectionsResponse>("/api/perception/detections");
}

export function getPerceptionStatus(): Promise<PerceptionStatusResponse> {
  return getJson<PerceptionStatusResponse>("/api/perception/status");
}

export function getCameraStatus(): Promise<CameraStatusResponse> {
  return getJson<CameraStatusResponse>("/api/camera/status");
}

// -- Multi-mission framework -- gated entirely behind
// MissionSelectPanel.tsx (VITE_ENABLE_MISSION_SELECT), see App.tsx and
// custom-gcs/CLAUDE.md Important Constraint #1. These calls are metadata/
// selection only, mirroring gcs/backend/app/missions.py's registry --
// postMissionStart() below still only ever results in the same "start"
// postCommand("start") already sends, parameterized with which mission
// profile it applies to.

export function getMissions(): Promise<Mission[]> {
  return getJson<Mission[]>("/api/missions");
}

export function getMissionDetail(missionId: string): Promise<Mission> {
  return getJson<Mission>(`/api/missions/${missionId}`);
}

export function getFlightTestStatus(): Promise<FlightTestStatusResponse> {
  return getJson<FlightTestStatusResponse>("/api/flight-test/status");
}

export function getMultiStepFlightTestStatus(): Promise<MultiStepFlightTestStatusResponse> {
  return getJson<MultiStepFlightTestStatusResponse>("/api/flight-test/multi-step/status");
}

// Bounded so a hung/slow request (backend or rosbridge stall) can't hold
// a command button's busy state open indefinitely -- a stuck START must
// never be able to delay the operator's ability to send ABORT. See
// docs/DECISIONS.md D-10 and onboard-autonomy/CLAUDE.md Hard Safety Rule 2.
const COMMAND_TIMEOUT_MS = 5000;

// ABORT gets its own, much shorter bound. Per onboard-autonomy/CLAUDE.md
// Hard Safety Rule 2, abort is the single most safety-critical behaviour
// in the system, and the operator's fallback if the software path fails
// is the physical kill switch -- so a hung ABORT must surface as "use the
// kill switch" well before a hung START would ever time out.
const ABORT_TIMEOUT_MS = 1500;

async function postAction<T>(path: string, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(path, { method: "POST", signal: controller.signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error(`POST ${path} timed out after ${timeoutMs}ms`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    const detail = await extractErrorDetail(res);
    throw new Error(`POST ${path} failed: HTTP ${res.status}${detail ? `: ${detail}` : ""}`);
  }
  return (await res.json()) as T;
}

export function postCommand(cmd: Command): Promise<CommandResponse> {
  const timeoutMs = cmd === "abort" ? ABORT_TIMEOUT_MS : COMMAND_TIMEOUT_MS;
  return postAction<CommandResponse>(`/api/command/${cmd}`, timeoutMs);
}

// Same bounded-timeout/error-detail behavior as postAction() above, but
// for the one POST route in this file that needs a JSON body
// (/api/mission/start's {mission, scenario} -- see
// gcs/backend/app/schemas.py's MissionStartRequest). Ordinary
// COMMAND_TIMEOUT_MS bound, not ABORT_TIMEOUT_MS -- mission-start is not
// the safety-critical abort path.
async function postJson<T>(path: string, body: unknown, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error(`POST ${path} timed out after ${timeoutMs}ms`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    const detail = await extractErrorDetail(res);
    throw new Error(`POST ${path} failed: HTTP ${res.status}${detail ? `: ${detail}` : ""}`);
  }
  return (await res.json()) as T;
}

export function postMissionStart(mission: string, scenario: string): Promise<MissionStartResponse> {
  return postJson<MissionStartResponse>("/api/mission/start", { mission, scenario }, COMMAND_TIMEOUT_MS);
}

// Simulation control -- see api.ts's module comment and
// CHECKPOINT/CURRENT_STATE.md. Deliberately a separate function hitting
// separate `/api/simulation/*` paths -- never `/api/command/*`. A
// generous, single timeout is fine here (no safety-critical abort-
// latency concern like the real command path has, since nothing here
// can affect real flight).
const SIMULATION_COMMAND_TIMEOUT_MS = 5000;

export function postSimulationCommand(cmd: SimulationCommand): Promise<SimulationCommandResponse> {
  return postAction<SimulationCommandResponse>(`/api/simulation/${cmd}`, SIMULATION_COMMAND_TIMEOUT_MS);
}

export function getSimulationStatus(): Promise<SimulationStatusResponse> {
  return getJson<SimulationStatusResponse>("/api/simulation/status");
}

export function getSimulationMap(): Promise<MapResponse> {
  return getJson<MapResponse>("/api/simulation/map");
}

export function getSimulationCoverage(): Promise<CoverageResponse> {
  return getJson<CoverageResponse>("/api/simulation/coverage");
}

export function getSimulationPath(): Promise<PathResponse> {
  return getJson<PathResponse>("/api/simulation/path");
}
