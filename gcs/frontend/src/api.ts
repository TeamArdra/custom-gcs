// Typed fetch wrappers around the FastAPI backend's REST API. Root-
// relative paths only -- never construct a URL with a host, so the same
// build works unmodified in dev (Vite proxy, see vite.config.ts) and in
// production (served from the same origin via FastAPI's /ui mount).

import type {
  CommandResponse,
  Command,
  HealthResponse,
  MapResponse,
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

export function getHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>("/health");
}

export function getTelemetry(): Promise<TelemetryResponse> {
  return getJson<TelemetryResponse>("/api/telemetry");
}

export function getMap(): Promise<MapResponse> {
  return getJson<MapResponse>("/api/map");
}

export function getSurvivors(): Promise<SurvivorResponse[]> {
  return getJson<SurvivorResponse[]>("/api/survivors");
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

export async function postCommand(cmd: Command): Promise<CommandResponse> {
  const path = `/api/command/${cmd}`;
  const timeoutMs = cmd === "abort" ? ABORT_TIMEOUT_MS : COMMAND_TIMEOUT_MS;
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
    throw new Error(`POST ${path} failed: HTTP ${res.status}`);
  }
  return (await res.json()) as CommandResponse;
}
