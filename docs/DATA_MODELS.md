# Data Models — NIDAR AirMouse GCS

Status: **Phase 0 — proposed schemas, illustrative, not yet implemented.**

These are draft message shapes for the Drone ↔ GCS interface defined in
[COMMUNICATION.md](COMMUNICATION.md). They exist to make the interface
concrete enough to review and to design a simulator against — they are
**not final** and should be revised jointly with the drone-side team once
the transport/protocol decision in [DECISIONS.md](DECISIONS.md) is made.
Field names and JSON framing here are illustrative; if MAVLink or another
existing protocol is adopted, these become "the fields we need," mapped
onto whatever wire format that protocol uses, rather than a literal JSON
schema.

Grid convention used throughout: a **1 m × 1 m cell grid** over the
≤15 m × 15 m arena (up to 225 cells), per Rulebook §9 scoring language —
see [REQUIREMENTS.md](REQUIREMENTS.md) §8–9. The exact origin/labeling
convention is an open question (REQUIREMENTS.md Open Question #3); `col`/
`row` integer indices are used below as a placeholder.

## 1. `MissionStatus` (Drone → GCS)

Overall mission state, sent periodically and on every state transition.

```jsonc
{
  "type": "mission_status",
  "timestamp": "2026-08-24T10:15:32.104Z",
  "state": "exploring",      // "idle" | "entering" | "exploring" | "exiting" | "complete" | "aborted"
  "elapsed_seconds": 214,
  "survivors_found": 3,
  "survivors_expected_max": 6
}
```

## 2. `TelemetryUpdate` (Drone → GCS)

Drone position/pose estimate and vehicle health. High frequency (e.g.
5–10 Hz), separate from the lower-frequency `MissionStatus`.

```jsonc
{
  "type": "telemetry",
  "timestamp": "2026-08-24T10:15:32.204Z",
  "position_estimate": { "x_m": 6.4, "y_m": 3.1, "heading_deg": 87.0 },
  "position_confidence": "high",   // qualitative, since there's no GPS ground truth indoors
  "battery_pct": 71,
  "flight_mode": "autonomous",
  "link_rssi": -62                 // optional, if the link technology exposes it
}
```

Position is arena-relative (meters from the entry/exit point or another
agreed local origin), never GPS — GPS is unavailable indoors by design.

## 3. `MapDelta` (Drone → GCS)

Incremental update to the shared 1 m × 1 m occupancy/connectivity grid.
Sent as new cells are explored/classified — never a full-map resend,
to keep bandwidth low over a constrained local link. The GCS accumulates
deltas into a persistent grid state for rendering.

```jsonc
{
  "type": "map_delta",
  "timestamp": "2026-08-24T10:15:33.500Z",
  "cells": [
    {
      "col": 4, "row": 2,
      "classification": "corridor",   // "wall" | "open" | "corridor" | "room" | "unknown"
      "walls": { "n": true, "e": false, "s": true, "w": false }, // which edges of the cell are blocked
      "confidence": 0.92
    }
  ]
}
```

The per-cell `walls`/edges shape is chosen to match the scoring language
directly ("correctly map the presence of walls, openings, corridors or
accessible directions adjoining that cell" — Rulebook §9, PS2 §2).

## 4. `SurvivorDetection` (Drone → GCS)

One message per newly detected (or updated/confirmed) survivor.

```jsonc
{
  "type": "survivor_detection",
  "timestamp": "2026-08-24T10:16:01.881Z",
  "survivor_id": "S3",          // stable id, so re-detections update rather than duplicate
  "grid_ref": { "col": 7, "row": 5 },
  "confidence": 0.88,
  "status": "confirmed"         // "tentative" | "confirmed" — optional, if the detection pipeline supports staged confidence
}
```

Capped at 6 distinct `survivor_id`s per the rules; the GCS should treat a
7th distinct id as a data/integration bug to surface, not silently accept.

## 5. `LinkHealth` (Drone → GCS, optional/recommended)

Not explicitly required by the rules for PS2 (see REQUIREMENTS.md Open
Question #5) but cheap to add and valuable given the operator's only tools
are "watch" and "abort."

```jsonc
{
  "type": "link_health",
  "timestamp": "2026-08-24T10:15:34.000Z",
  "telemetry_link_ok": true,
  "video_link_ok": true,
  "last_telemetry_age_ms": 120,
  "last_video_frame_age_ms": 90
}
```

## 6. `StartMission` (GCS → Drone)

The only mission-initiating command. Sent once, operator-triggered.

```jsonc
{
  "type": "start_mission",
  "timestamp": "2026-08-24T10:12:00.000Z",
  "operator_confirmed": true
}
```

## 7. `AbortMission` (GCS → Drone)

The only other permitted command, at any point after start.

```jsonc
{
  "type": "abort_mission",
  "timestamp": "2026-08-24T10:20:15.500Z",
  "reason": "operator_triggered"   // for the local mission log; not a rules requirement
}
```

## 8. What Deliberately Does Not Exist

No schema is defined — anywhere, even as an unused/future placeholder —
for: waypoint upload, path correction, map edit/correction, survivor tag
correction, or mission replanning. This omission is intentional (see
[ARCHITECTURE.md](ARCHITECTURE.md) Design Principle 1 and
[COMMUNICATION.md](COMMUNICATION.md) §2.2). If a future engineering need
seems to require one of these, treat that as a signal to revisit the
architecture and the rules together, not as a routine schema addition.

## 9. Video

Not modeled as a discrete message — it is a continuous media stream on a
separate channel (see COMMUNICATION.md §2.3), consumed directly by a
`<video>`-style element rather than parsed frame-by-frame as JSON. Format
TBD in [DECISIONS.md](DECISIONS.md).
