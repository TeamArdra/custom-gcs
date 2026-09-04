import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import * as api from "./api";
import type { TelemetryResponse } from "./types";

const TELEMETRY: TelemetryResponse = {
  connected: true,
  mission_state: "searching",
  fcu: { connected: true, armed: true, guided: true, mode: "GUIDED", system_status: 4 },
  battery: { voltage: 12.4, current: 3.1, percentage: 0.75 },
  pose: { position: { x: 1, y: 2, z: 0.5 } },
  velocity: { x: 0.1, y: 0, z: 0 },
  attitude: { x: 0, y: 0, z: 0, w: 1 },
  gps: { fix_status: 3, satellites_visible: 9, latitude: 12.9, longitude: 77.6, altitude: 900 },
  statustext: [{ severity: 6, text: "boot complete" }],
  heartbeat_age_s: 0.3,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("renders operator panels and reflects telemetry once loaded", async () => {
    vi.spyOn(api, "getTelemetry").mockResolvedValue(TELEMETRY);
    vi.spyOn(api, "getMap").mockResolvedValue({ resolution: null, width: null, height: null, data: null });
    vi.spyOn(api, "getSurvivors").mockResolvedValue([]);
    vi.spyOn(api, "getHealth").mockResolvedValue({
      connected: true,
      rosbridge_host: "127.0.0.1",
      rosbridge_port: 9090,
    });

    render(<App />);

    expect(screen.getByText("NIDAR AirMouse — Operator Panel")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("searching")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "START" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "STOP / ABORT" })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/rosbridge target: 127\.0\.0\.1:9090/)).toBeInTheDocument(),
    );
  });

  it("shows a telemetry-fetch-failed banner instead of a blank page on failure", async () => {
    vi.spyOn(api, "getTelemetry").mockRejectedValue(new Error("network error"));
    vi.spyOn(api, "getMap").mockResolvedValue({ resolution: null, width: null, height: null, data: null });
    vi.spyOn(api, "getSurvivors").mockResolvedValue([]);
    vi.spyOn(api, "getHealth").mockResolvedValue({
      connected: false,
      rosbridge_host: "127.0.0.1",
      rosbridge_port: 9090,
    });

    render(<App />);

    expect(
      await screen.findByText(/telemetry fetch failed: network error/),
    ).toBeInTheDocument();
  });
});
