import { useEffect, useRef, useState } from "react";
import Panel from "./Panel";
import { getCoverage, getMap, getPath } from "../api";
import type { CoverageResponse, MapResponse, PathResponse, TelemetryResponse } from "../types";

const POLL_INTERVAL_MS = 1000;

// Palette matches tailwind.config.js's dark operator-panel colors --
// canvas fills can't reference Tailwind classes, so the same hex values
// are duplicated here deliberately (see tailwind.config.js comment: the
// visual language should stay one system).
const COLOR_UNKNOWN = "#26313d"; // border
const COLOR_FREE = "#0b0f14"; // bg
const COLOR_OCCUPIED = "#e6edf3"; // text
const COLOR_SEARCHED = "rgba(46, 160, 67, 0.35)"; // ok, translucent
const COLOR_PATH = "#388bfd"; // accent
const COLOR_DRONE = "#388bfd"; // accent
const COLOR_TARGET = "#d29922"; // warn

// nav_msgs/OccupancyGrid cell semantics (standard for /map; /coverage_grid
// reuses the same encoding with different meaning -- see
// CHECKPOINT/docs/gcs_telemetry_contract.md).
const UNKNOWN = -1;
const OCCUPIED_THRESHOLD = 65;

function worldToCanvas(
  x: number,
  y: number,
  originX: number,
  originY: number,
  resolution: number,
  cellPx: number,
): [number, number] {
  return [((x - originX) / resolution) * cellPx, ((y - originY) / resolution) * cellPx];
}

// Extension point: /api/map has no real data until onboard-autonomy's
// SLAM/mapping pipeline is running (AUTONOMY_ROADMAP.md Phase 4/5 -- see
// the NIDAR Autonomy Migration report, CHECKPOINT/CURRENT_STATE.md, for
// current status) -- renders an explicit "no map yet" placeholder rather
// than a fake/demo grid, same posture as before this panel had real
// rendering logic. Once /api/map has real data (or the sim/rosbridge_sim
// synthetic feed is used for testing), this renders it for real: occupied/
// free/unknown cells, a coverage overlay, the planned path, the drone's
// current position, and the current frontier/target -- see
// custom-gcs/CLAUDE.md "never invent" for why nothing here is fabricated
// beyond what the backend actually reports.
export default function MapPanel({ telemetry }: { telemetry: TelemetryResponse | null }) {
  const [map, setMap] = useState<MapResponse | null>(null);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [path, setPath] = useState<PathResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    let mounted = true;

    async function poll() {
      try {
        const [m, c, p] = await Promise.all([getMap(), getCoverage(), getPath()]);
        if (mounted) {
          setMap(m);
          setCoverage(c);
          setPath(p);
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

  const hasMap = map?.data != null && map.data.length > 0 && map.width != null && map.height != null;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !hasMap || !map || map.width == null || map.height == null || map.resolution == null) {
      return;
    }

    const cellPx = 8;
    const width = map.width * cellPx;
    const height = map.height * cellPx;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    // Map origin is always (0,0) here: /api/map doesn't carry the origin
    // separately (see MapResponse) -- it's derived from the telemetry
    // mapping block when available, defaulting to (0,0) otherwise.
    const originX = telemetry?.mapping?.origin_x ?? 0;
    const originY = telemetry?.mapping?.origin_y ?? 0;

    // -- occupancy grid --
    for (let row = 0; row < map.height; row++) {
      for (let col = 0; col < map.width; col++) {
        const v = map.data![row * map.width + col];
        ctx.fillStyle = v === UNKNOWN ? COLOR_UNKNOWN : v >= OCCUPIED_THRESHOLD ? COLOR_OCCUPIED : COLOR_FREE;
        // Canvas Y grows downward; occupancy grid Y grows "up" (world
        // convention) -- flip the row so north is up on screen.
        ctx.fillRect(col * cellPx, (map.height - 1 - row) * cellPx, cellPx, cellPx);
      }
    }

    // -- coverage overlay (searched cells only; leaves unsearched/unknown transparent) --
    if (coverage?.data != null && coverage.width != null && coverage.height != null) {
      const covCellPx = (map.width * cellPx) / coverage.width;
      const covCellPy = (map.height * cellPx) / coverage.height;
      for (let row = 0; row < coverage.height; row++) {
        for (let col = 0; col < coverage.width; col++) {
          const v = coverage.data[row * coverage.width + col];
          if (v >= OCCUPIED_THRESHOLD) {
            ctx.fillStyle = COLOR_SEARCHED;
            ctx.fillRect(col * covCellPx, (coverage.height - 1 - row) * covCellPy, covCellPx, covCellPy);
          }
        }
      }
    }

    // -- planned path --
    if (path?.points && path.points.length > 1 && map.resolution) {
      ctx.strokeStyle = COLOR_PATH;
      ctx.lineWidth = 2;
      ctx.beginPath();
      path.points.forEach((pt, i) => {
        const [px, py] = worldToCanvas(pt.x, pt.y, originX, originY, map.resolution!, cellPx);
        const canvasY = height - py;
        if (i === 0) ctx.moveTo(px, canvasY);
        else ctx.lineTo(px, canvasY);
      });
      ctx.stroke();
    }

    // -- drone position --
    const dronePos = telemetry?.pose?.position;
    if (dronePos && map.resolution) {
      const [dx, dy] = worldToCanvas(dronePos.x, dronePos.y, originX, originY, map.resolution, cellPx);
      ctx.fillStyle = COLOR_DRONE;
      ctx.beginPath();
      ctx.arc(dx, height - dy, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // -- current frontier/target --
    const target = telemetry?.autonomy?.target ?? telemetry?.navigation?.target;
    if (target && map.resolution) {
      const [tx, ty] = worldToCanvas(target[0], target[1], originX, originY, map.resolution, cellPx);
      ctx.strokeStyle = COLOR_TARGET;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(tx, height - ty, 6, 0, Math.PI * 2);
      ctx.stroke();
    }
  }, [map, coverage, path, telemetry, hasMap]);

  return (
    <Panel title="Map" className="col-span-full">
      {error && <div className="text-bad text-xs mb-2">map fetch failed: {error}</div>}
      {hasMap ? (
        <div>
          <div className="text-xs text-dim mb-2">
            {map!.width} × {map!.height} cells, resolution {map!.resolution} m/cell
            {telemetry?.mapping?.explored_pct != null && ` — ${telemetry.mapping.explored_pct}% searched`}
          </div>
          <div className="overflow-auto border border-border rounded">
            <canvas ref={canvasRef} data-testid="map-canvas" />
          </div>
        </div>
      ) : (
        <div className="text-dim text-xs">
          No map data yet — mapping requires onboard-autonomy's SLAM/exploration stack
          to be running and publishing `/map` (see AUTONOMY_ROADMAP.md Phase 4/5).
        </div>
      )}
    </Panel>
  );
}
