import { useState } from "react";
import Panel from "./Panel";
import { postCommand } from "../api";
import type { Command } from "../types";

// The operator command surface is exactly START and ABORT -- see
// custom-gcs/CLAUDE.md Important Constraints #1. Do not add any other
// button/control that sends a command, and do not add a confirmation
// step before ABORT: abort must be able to preempt everything
// immediately, per onboard-autonomy/CLAUDE.md Hard Safety Rule 2 -- any
// added friction before an abort command is a safety regression, not a
// UX nicety.
export default function ControlsPanel() {
  // Independent busy state per button, deliberately -- a slow/hung START
  // request must never disable ABORT. See custom-gcs/docs/DECISIONS.md
  // D-10 and onboard-autonomy/CLAUDE.md Hard Safety Rule 2 ("Abort must
  // preempt everything ... immediately, regardless of what else is
  // running"). Do not collapse these back into one shared `busy` flag.
  const [startBusy, setStartBusy] = useState(false);
  const [abortBusy, setAbortBusy] = useState(false);
  // Independent error state per button too -- otherwise a START failure
  // and an ABORT failure landing close together could have one message
  // overwrite the other before the operator reads it, even though each
  // is already prefixed with the command name. Mirrors the busy split.
  const [startError, setStartError] = useState<string | null>(null);
  const [abortError, setAbortError] = useState<string | null>(null);

  async function send(command: Command) {
    const busy = command === "start" ? startBusy : abortBusy;
    const setBusy = command === "start" ? setStartBusy : setAbortBusy;
    const setError = command === "start" ? setStartError : setAbortError;
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await postCommand(command);
    } catch (e) {
      setError(`${command.toUpperCase()} failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Controls">
      <div className="flex gap-2.5 flex-wrap">
        <button
          type="button"
          className="font-semibold px-4 py-2.5 rounded-md border border-ok bg-ok text-white disabled:opacity-40 disabled:cursor-not-allowed"
          disabled={startBusy}
          onClick={() => send("start")}
        >
          START
        </button>
        <button
          type="button"
          className="font-semibold px-4 py-2.5 rounded-md border border-bad bg-bad text-white disabled:opacity-40 disabled:cursor-not-allowed"
          disabled={abortBusy}
          onClick={() => send("abort")}
        >
          STOP / ABORT
        </button>
      </div>

      {startError && <div className="mt-2.5 text-bad text-xs font-semibold">{startError}</div>}
      {abortError && <div className="mt-2.5 text-bad text-xs font-semibold">{abortError}</div>}

      <div className="mt-2.5 px-2.5 py-2 bg-warn/10 border border-warn/40 rounded-md text-warn text-xs font-semibold">
        BENCH TEST — PROPS REMOVED. START arms the vehicle through the
        Jetson mission logic (real ARM, via MAVROS) purely to demonstrate
        the command chain — it is not a flight/throttle control. No
        motor-throttle or setpoint interface is exposed here. ARM/DISARM
        are not separately exposed as operator buttons: the only operator
        command surface is START/ABORT, per the competition's minimal
        command-surface rule.
      </div>
    </Panel>
  );
}
