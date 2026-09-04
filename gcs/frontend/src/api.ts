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

export async function postCommand(cmd: Command): Promise<CommandResponse> {
  const path = `/api/command/${cmd}`;
  const res = await fetch(path, { method: "POST" });
  if (!res.ok) {
    throw new Error(`POST ${path} failed: HTTP ${res.status}`);
  }
  return (await res.json()) as CommandResponse;
}
