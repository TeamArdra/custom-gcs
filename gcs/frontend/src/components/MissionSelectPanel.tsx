import { useEffect, useState } from "react";
import Panel, { Row } from "./Panel";
import { getFlightTestStatus, getMissions, getMultiStepFlightTestStatus, postMissionStart } from "../api";
import type { FlightTestStatusResponse, Mission, MultiStepFlightTestStatusResponse, TelemetryResponse } from "../types";

const POLL_INTERVAL_MS = 1000; // matches useTelemetry.ts's cadence

// Dev/bench-only alternate start path -- gated entirely OFF App.tsx's
// VITE_ENABLE_MISSION_SELECT flag, never shown in a competition build.
// This panel adds no new kind of operator action: postMissionStart()
// still only ever results in the same real "start" ControlsPanel's
// plain START button sends, parameterized with which mission/scenario
// profile it applies to (gcs/backend/app/missions.py's static
// registry). ABORT is deliberately NOT duplicated here -- see
// ControlsPanel.tsx, which stays the single abort control. See
// custom-gcs/CLAUDE.md Important Constraint #1.

// "In progress" -- these are the only states that lock the selector.
// Everything else (idle/complete/aborted/failed) is a terminal outcome:
// the selector unlocks again, but the terminal state is still worth
// showing (see <LastRun> below) rather than silently vanishing,
// especially "failed", which must stay visually distinguishable from
// "aborted" even after the run has ended.
const MAIN_NIDAR_ACTIVE_STATES = new Set(["entering", "searching", "exiting"]);
const HOVER_IN_PROGRESS_STATES = new Set(["arming", "taking_off", "hovering", "landing"]);
const MULTI_STEP_IN_PROGRESS_STATES = new Set(["arming", "executing", "landing"]);

interface ActiveInfo {
  kind: "main_nidar" | "hover" | "multi_step";
  scenarioId: string;
}

function getActiveInfo(
  telemetry: TelemetryResponse | null,
  flightTestStatus: FlightTestStatusResponse | null,
  multiStepStatus: MultiStepFlightTestStatusResponse | null,
): ActiveInfo | null {
  if (telemetry?.mission_state && MAIN_NIDAR_ACTIVE_STATES.has(telemetry.mission_state)) {
    return { kind: "main_nidar", scenarioId: "full_mission" };
  }
  if (flightTestStatus?.state && HOVER_IN_PROGRESS_STATES.has(flightTestStatus.state)) {
    return { kind: "hover", scenarioId: flightTestStatus.scenario ?? "hover" };
  }
  if (multiStepStatus?.state && MULTI_STEP_IN_PROGRESS_STATES.has(multiStepStatus.state)) {
    return { kind: "multi_step", scenarioId: multiStepStatus.scenario_id ?? "" };
  }
  return null;
}

// Semantic color classes for a terminal state -- uses this codebase's
// existing tokens (tailwind.config.js), never invents new ones. "failed"
// (the scenario's own execution went wrong) must render distinctly from
// "aborted" (the operator hit ABORT) -- see
// types.ts's MultiStepFlightTestStatusResponse docstring.
function terminalStateClass(state: string | null): string {
  if (state === "failed") return "text-bad font-semibold";
  if (state === "aborted") return "text-warn font-semibold";
  if (state === "complete") return "text-ok font-semibold";
  return "";
}

export default function MissionSelectPanel({ telemetry }: { telemetry: TelemetryResponse | null }) {
  const [missions, setMissions] = useState<Mission[] | null>(null);
  const [missionsError, setMissionsError] = useState<string | null>(null);
  const [selectedMissionId, setSelectedMissionId] = useState<string>("");
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("");
  const [flightTestStatus, setFlightTestStatus] = useState<FlightTestStatusResponse | null>(null);
  const [multiStepStatus, setMultiStepStatus] = useState<MultiStepFlightTestStatusResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    getMissions()
      .then((m) => {
        if (!mounted) return;
        setMissions(m);
        setSelectedMissionId((prev) => prev || m[0]?.id || "");
      })
      .catch((e) => {
        if (mounted) setMissionsError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    async function poll() {
      try {
        const [f, m] = await Promise.all([getFlightTestStatus(), getMultiStepFlightTestStatus()]);
        if (mounted) {
          setFlightTestStatus(f);
          setMultiStepStatus(m);
        }
      } catch {
        // Non-critical polling failure (not the real telemetry path) --
        // silently retry next tick, same as SimulationPanel's poll().
      }
    }

    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);

  const selectedMission = missions?.find((m) => m.id === selectedMissionId) ?? null;
  const selectedScenario = selectedMission?.scenarios.find((s) => s.id === selectedScenarioId) ?? null;
  const active = getActiveInfo(telemetry, flightTestStatus, multiStepStatus);
  const locked = active != null;

  function selectMission(missionId: string) {
    setSelectedMissionId(missionId);
    setSelectedScenarioId("");
  }

  async function start() {
    if (busy || locked || !selectedMission || !selectedScenario || !selectedScenario.implemented) return;
    setBusy(true);
    setStartError(null);
    try {
      await postMissionStart(selectedMission.id, selectedScenario.id);
    } catch (e) {
      setStartError(`START failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Mission / Test Select" className="border-dashed border-2 border-accent/60 bg-accent/5">
      <div className="inline-block px-2 py-0.5 mb-3 rounded bg-accent text-white text-[11px] font-bold tracking-wide">
        DEV / BENCH ONLY — ALTERNATE START PATH
      </div>

      {missionsError && <div className="mb-2.5 text-bad text-xs font-semibold">{missionsError}</div>}

      {locked && active ? (
        <ActiveStatus active={active} telemetry={telemetry} flightTestStatus={flightTestStatus} multiStepStatus={multiStepStatus} />
      ) : (
        <>
          <div className="flex flex-col gap-2 mb-3">
            <label className="block text-xs text-dim">
              Mission
              <select
                aria-label="Mission"
                className="mt-1 w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm text-text"
                value={selectedMissionId}
                disabled={!missions}
                onChange={(e) => selectMission(e.target.value)}
              >
                {(missions ?? []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-xs text-dim">
              Scenario
              <select
                aria-label="Scenario"
                className="mt-1 w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm text-text"
                value={selectedScenarioId}
                disabled={!selectedMission}
                onChange={(e) => setSelectedScenarioId(e.target.value)}
              >
                <option value="" disabled>
                  select a scenario
                </option>
                {(selectedMission?.scenarios ?? []).map((s) => (
                  <option key={s.id} value={s.id} disabled={!s.implemented}>
                    {s.name}
                    {s.implemented ? "" : " (coming soon)"}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {selectedScenario && selectedScenario.steps.length > 0 && (
            <div className="mb-3 text-xs text-dim">
              Steps: <span className="text-text">{selectedScenario.steps.join(" → ")}</span>
            </div>
          )}

          <LastRun flightTestStatus={flightTestStatus} multiStepStatus={multiStepStatus} />

          <button
            type="button"
            className="font-semibold px-4 py-2.5 rounded-md border border-ok bg-ok text-white disabled:opacity-40 disabled:cursor-not-allowed"
            disabled={busy || !selectedScenario || !selectedScenario.implemented}
            onClick={start}
          >
            START
          </button>

          {startError && <div className="mt-2.5 text-bad text-xs font-semibold">{startError}</div>}
        </>
      )}
    </Panel>
  );
}

function ActiveStatus({
  active,
  telemetry,
  flightTestStatus,
  multiStepStatus,
}: {
  active: ActiveInfo;
  telemetry: TelemetryResponse | null;
  flightTestStatus: FlightTestStatusResponse | null;
  multiStepStatus: MultiStepFlightTestStatusResponse | null;
}) {
  if (active.kind === "main_nidar") {
    return (
      <div className="text-xs">
        <div className="mb-1.5 font-semibold">ACTIVE — Main NIDAR Competition</div>
        <Row label="Mission state">{telemetry?.mission_state ?? "—"}</Row>
      </div>
    );
  }

  if (active.kind === "hover") {
    return (
      <div className="text-xs">
        <div className="mb-1.5 font-semibold">ACTIVE — Flight Test: Hover</div>
        <Row label="State">{flightTestStatus?.state ?? "—"}</Row>
        <Row label="Elapsed hover (s)">{flightTestStatus?.elapsed_hover_s ?? "—"}</Row>
        <Row label="Armed">{flightTestStatus?.armed ? "yes" : "no"}</Row>
      </div>
    );
  }

  const stepOf =
    multiStepStatus?.current_step_index != null && multiStepStatus?.total_steps
      ? `${multiStepStatus.current_step_index + 1} of ${multiStepStatus.total_steps}`
      : "—";

  return (
    <div className="text-xs">
      <div className="mb-1.5 font-semibold">ACTIVE — Flight Test: {active.scenarioId}</div>
      <Row label="State">{multiStepStatus?.state ?? "—"}</Row>
      <Row label="Step">{stepOf}</Row>
      <Row label="Current action">{multiStepStatus?.current_step_action ?? "—"}</Row>
    </div>
  );
}

// Shown once the selector is unlocked again, so a terminal outcome
// (especially "failed", distinct from "aborted") isn't silently
// dropped the moment the operator regains control of the dropdowns --
// see terminalStateClass()'s docstring above.
function LastRun({
  flightTestStatus,
  multiStepStatus,
}: {
  flightTestStatus: FlightTestStatusResponse | null;
  multiStepStatus: MultiStepFlightTestStatusResponse | null;
}) {
  const hoverState = flightTestStatus?.state ?? null;
  const showHover = hoverState != null && hoverState !== "idle";
  const multiStepState = multiStepStatus?.state ?? null;
  const showMultiStep = multiStepState != null && multiStepState !== "idle";

  if (!showHover && !showMultiStep) return null;

  return (
    <div className="mb-3 text-xs">
      {showHover && (
        <div>
          Last run — Hover:{" "}
          <span className={terminalStateClass(hoverState)}>{hoverState}</span>
        </div>
      )}
      {showMultiStep && (
        <div>
          Last run — {multiStepStatus?.scenario_id ?? "flight test"}:{" "}
          <span className={terminalStateClass(multiStepState)}>{multiStepState}</span>
        </div>
      )}
    </div>
  );
}
