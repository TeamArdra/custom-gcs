import { useEffect, useState } from "react";
import Panel from "./Panel";
import { getMap } from "../api";
import type { MapResponse } from "../types";

const POLL_INTERVAL_MS = 1000;

// Extension point: /api/map is a real endpoint but SLAM isn't implemented
// in onboard-autonomy yet, so `data` is always null/empty today. Renders
// an explicit placeholder rather than a fake/demo grid -- see
// custom-gcs/CLAUDE.md "never invent" and the task brief for this panel.
export default function MapPanel() {
  const [map, setMap] = useState<MapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function poll() {
      try {
        const m = await getMap();
        if (mounted) {
          setMap(m);
          setError(null);
        }
      } catch (e) {
        if (mounted) setError(e instanceof Error ? e.message : String(e));
      }
    }

    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);

  const hasData = map?.data != null && map.data.length > 0;

  return (
    <Panel title="Map">
      {error && <div className="text-bad text-xs mb-2">map fetch failed: {error}</div>}
      {hasData ? (
        <div className="text-xs">
          {map!.width} × {map!.height} cells, resolution {map!.resolution} m/cell
        </div>
      ) : (
        <div className="text-dim text-xs">
          No SLAM map yet — mapping not implemented in onboard-autonomy.
        </div>
      )}
    </Panel>
  );
}
