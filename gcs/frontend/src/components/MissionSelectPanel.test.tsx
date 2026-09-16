import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MissionSelectPanel from "./MissionSelectPanel";
import * as api from "../api";
import type { FlightTestStatusResponse, Mission, MultiStepFlightTestStatusResponse, TelemetryResponse } from "../types";

const IDLE_FLIGHT_TEST_STATUS: FlightTestStatusResponse = {
  scenario: null,
  state: null,
  target_altitude_m: null,
  current_altitude_m: null,
  current_position: null,
  duration_s: null,
  elapsed_hover_s: null,
  armed: null,
  execution_mode: null,
};

const IDLE_MULTI_STEP_STATUS: MultiStepFlightTestStatusResponse = {
  scenario_id: null,
  state: null,
  phase: null,
  current_step_index: null,
  current_step_action: null,
  total_steps: null,
  current_position: null,
  armed: null,
  execution_mode: null,
};

const MISSIONS: Mission[] = [
  {
    id: "main_nidar",
    name: "Main NIDAR Competition",
    description: "The complete mission.",
    ui_panel: "nidar",
    required_nodes: [],
    scenarios: [
      { id: "full_mission", name: "Full NIDAR Mission", description: "...", implemented: true, execution_config: {}, steps: [] },
    ],
  },
  {
    id: "flight_test",
    name: "Flight Test",
    description: "Bench validation.",
    ui_panel: "flight_test",
    required_nodes: [],
    scenarios: [
      { id: "hover", name: "Hover", description: "...", implemented: true, execution_config: {}, steps: ["takeoff", "hover", "land"] },
      {
        id: "forward_backward_hover", name: "Test 1: Forward / Backward / Hover", description: "...",
        implemented: true, execution_config: {}, steps: ["forward", "backward", "hover"],
      },
      { id: "not_yet_wired", name: "Not Yet Wired", description: "Registered but not implemented.", implemented: false, execution_config: {}, steps: [] },
    ],
  },
];

const IDLE_TELEMETRY = { mission_state: "idle" } as TelemetryResponse;

function mockApis(overrides: {
  missions?: Mission[];
  flightTestStatus?: FlightTestStatusResponse;
  multiStepStatus?: MultiStepFlightTestStatusResponse;
} = {}) {
  vi.spyOn(api, "getMissions").mockResolvedValue(overrides.missions ?? MISSIONS);
  vi.spyOn(api, "getFlightTestStatus").mockResolvedValue(overrides.flightTestStatus ?? IDLE_FLIGHT_TEST_STATUS);
  vi.spyOn(api, "getMultiStepFlightTestStatus").mockResolvedValue(overrides.multiStepStatus ?? IDLE_MULTI_STEP_STATUS);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MissionSelectPanel", () => {
  it("loads missions and renders them in the mission dropdown", async () => {
    mockApis();
    render(<MissionSelectPanel telemetry={IDLE_TELEMETRY} />);

    await waitFor(() => expect(api.getMissions).toHaveBeenCalled());
    expect(await screen.findByText("Main NIDAR Competition")).toBeInTheDocument();
    expect(screen.getByText("Flight Test")).toBeInTheDocument();
  });

  it("selecting an implemented scenario enables START, unselected disables it", async () => {
    mockApis();
    render(<MissionSelectPanel telemetry={IDLE_TELEMETRY} />);
    await waitFor(() => expect(api.getMissions).toHaveBeenCalled());

    expect(screen.getByRole("button", { name: "START" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Mission"), { target: { value: "flight_test" } });
    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "hover" } });

    expect(screen.getByRole("button", { name: "START" })).not.toBeDisabled();
  });

  it("never renders a not-implemented scenario as an option at all", async () => {
    // Only scenarios the team has actually implemented are ever offered --
    // no "coming soon" placeholder, greyed-out or otherwise. The backend
    // registry (app/missions.py) is the primary guard (it no longer
    // carries placeholder entries); this is the UI's defense-in-depth
    // filter for the same rule.
    mockApis();
    render(<MissionSelectPanel telemetry={IDLE_TELEMETRY} />);
    await waitFor(() => expect(api.getMissions).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Mission"), { target: { value: "flight_test" } });
    expect(screen.queryByRole("option", { name: /Not Yet Wired/ })).not.toBeInTheDocument();
  });

  it("shows the ordered steps for the selected scenario", async () => {
    mockApis();
    render(<MissionSelectPanel telemetry={IDLE_TELEMETRY} />);
    await waitFor(() => expect(api.getMissions).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Mission"), { target: { value: "flight_test" } });
    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "forward_backward_hover" } });

    expect(screen.getByText(/forward → backward → hover/)).toBeInTheDocument();
  });

  it("START calls postMissionStart with the selected mission/scenario ids", async () => {
    mockApis();
    const postSpy = vi
      .spyOn(api, "postMissionStart")
      .mockResolvedValue({ status: "sent", mission: "flight_test", scenario: "hover" });

    render(<MissionSelectPanel telemetry={IDLE_TELEMETRY} />);
    await waitFor(() => expect(api.getMissions).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Mission"), { target: { value: "flight_test" } });
    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "hover" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "START" }));
    });

    expect(postSpy).toHaveBeenCalledWith("flight_test", "hover");
  });

  it("locks the selector while the multi-step scenario is active", async () => {
    mockApis({ multiStepStatus: { ...IDLE_MULTI_STEP_STATUS, scenario_id: "forward_backward_hover", state: "executing", current_step_index: 0, current_step_action: "forward", total_steps: 3 } });
    render(<MissionSelectPanel telemetry={IDLE_TELEMETRY} />);

    await waitFor(() => expect(screen.getByText(/ACTIVE/)).toBeInTheDocument());
    expect(screen.queryByLabelText("Mission")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "START" })).not.toBeInTheDocument();
    expect(screen.getByText("forward")).toBeInTheDocument();
    expect(screen.getByText("1 of 3")).toBeInTheDocument();
  });

  it("unlocks the selector again once the multi-step scenario completes", async () => {
    const flightTestStatus = IDLE_FLIGHT_TEST_STATUS;
    let multiStepStatus: MultiStepFlightTestStatusResponse = {
      ...IDLE_MULTI_STEP_STATUS, scenario_id: "forward_backward_hover", state: "executing",
    };
    vi.spyOn(api, "getMissions").mockResolvedValue(MISSIONS);
    vi.spyOn(api, "getFlightTestStatus").mockResolvedValue(flightTestStatus);
    vi.spyOn(api, "getMultiStepFlightTestStatus").mockImplementation(() => Promise.resolve(multiStepStatus));

    render(<MissionSelectPanel telemetry={IDLE_TELEMETRY} />);
    await waitFor(() => expect(screen.getByText(/ACTIVE/)).toBeInTheDocument());

    multiStepStatus = { ...IDLE_MULTI_STEP_STATUS, state: "complete" };

    await waitFor(() => expect(screen.getByLabelText("Mission")).toBeInTheDocument(), { timeout: 3000 });
  });

  it("renders a terminal 'failed' state distinctly (from a completed/unlocked selector)", async () => {
    mockApis({ multiStepStatus: { ...IDLE_MULTI_STEP_STATUS, scenario_id: "forward_backward_hover", state: "failed" } });
    render(<MissionSelectPanel telemetry={IDLE_TELEMETRY} />);

    const failedText = await screen.findByText("failed");
    expect(failedText.className).toMatch(/text-bad/);
    // The selector is unlocked again (failed is terminal), but the
    // outcome is still shown -- see MissionSelectPanel.tsx's LastRun.
    expect(screen.getByLabelText("Mission")).toBeInTheDocument();
  });

  it("renders a terminal 'aborted' state distinctly from 'failed'", async () => {
    mockApis({ multiStepStatus: { ...IDLE_MULTI_STEP_STATUS, scenario_id: "forward_backward_hover", state: "aborted" } });
    render(<MissionSelectPanel telemetry={IDLE_TELEMETRY} />);

    const abortedText = await screen.findByText("aborted");
    expect(abortedText.className).toMatch(/text-warn/);
    expect(abortedText.className).not.toMatch(/text-bad/);
  });
});
