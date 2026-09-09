import { useTelemetry } from "./hooks/useTelemetry";
import ConnectionPanel from "./components/ConnectionPanel";
import FlightPanel from "./components/FlightPanel";
import MissionPanel from "./components/MissionPanel";
import ControlsPanel from "./components/ControlsPanel";
import BatteryPanel from "./components/BatteryPanel";
import PositionVelocityPanel from "./components/PositionVelocityPanel";
import AttitudePanel from "./components/AttitudePanel";
import StatusTextPanel from "./components/StatusTextPanel";
import MapPanel from "./components/MapPanel";
import AutonomyPanel from "./components/AutonomyPanel";
import SurvivorsPanel from "./components/SurvivorsPanel";
import Footer from "./components/Footer";

export default function App() {
  const { data: telemetry, error, lastUpdatedAt } = useTelemetry();

  const subtitle = error
    ? `telemetry fetch failed: ${error}`
    : lastUpdatedAt
      ? `last updated ${lastUpdatedAt.toLocaleTimeString()}`
      : "connecting...";

  return (
    <div className="p-4">
      <h1 className="text-lg font-semibold mb-1">NIDAR AirMouse — Operator Panel</h1>
      <div className={`text-xs mb-4 ${error ? "text-bad font-semibold" : "text-dim"}`}>
        {subtitle}
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-3">
        <ConnectionPanel telemetry={telemetry} />
        <FlightPanel telemetry={telemetry} />
        <MissionPanel telemetry={telemetry} />
        <ControlsPanel />
        <BatteryPanel telemetry={telemetry} />
        <PositionVelocityPanel telemetry={telemetry} />
        <AttitudePanel telemetry={telemetry} />
        <AutonomyPanel telemetry={telemetry} />
        <SurvivorsPanel />
        <StatusTextPanel telemetry={telemetry} />
        <MapPanel telemetry={telemetry} />
      </div>

      <Footer />
    </div>
  );
}
