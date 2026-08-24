# Data Models — NIDAR AirMouse GCS

Status: **Phase 0 — working schemas, tied to the stack decisions in
[DECISIONS.md](DECISIONS.md) (D-0 through D-13). Not yet implemented.**
Frontend consumes these directly via **roslibjs** over
**`rosbridge_server`** (WebSocket, port 9090) — see
[COMMUNICATION.md](COMMUNICATION.md). Field names below reflect either a
standard ROS message type (used as-is) or a proposed custom `.msg`
(marked "custom", to be finalized with the drone-side/companion-computer
team, per D-13).

Grid convention (per D-7/D-7a): a **1 m × 1 m cell grid** over the
≤15 m × 15 m arena (≤225 cells), origin pinned to the designated entry/
exit point, derived from whatever `nav_msgs/OccupancyGrid.info` (resolution
+ origin) the map topic reports. Survivor coordinates and map cells share
this exact origin/resolution so they cannot drift apart from each other.

## 1. Mission Status — `/mission/state`

**Type:** custom (proposed: a small `.msg` with an enum-like string field;
`std_msgs/String` is the minimum viable version). Published **on change**,
not periodically.

```jsonc
// std_msgs/String equivalent, as seen by roslibjs
{
  "data": "searching"   // "idle" | "entering" | "searching" | "exiting" | "complete" | "aborted"
}
```

If richer state is useful later (elapsed time, survivors found so far),
that belongs in a custom message rather than overloading `std_msgs/String`
— not yet decided; start minimal, expand only if needed (see D-13).

## 2. Telemetry — Battery: `/mavros/battery`

**Type:** `sensor_msgs/BatteryState` (standard `mavros` topic — no custom
work needed). Published 1–2 Hz. GCS reads `percentage` and `voltage`.

## 3. Telemetry — Pose: `/mavros/local_position/pose`

**Type:** `geometry_msgs/PoseStamped` (standard `mavros` topic). Published
10+ Hz. Position is arena-relative (local ENU frame from Pixhawk's EKF),
**never GPS** — GPS is unavailable/forbidden indoors by rule.

**Caveat (see DECISIONS.md D-11, not a GCS-side fix):** this topic is only
meaningful if Pixhawk's EKF has a non-GPS position source indoors —
presumably SLAM pose fed back via MAVLink `VISION_POSITION_ESTIMATE`. The
GCS should not assume this pose is automatically trustworthy; if the
drone-side telemetry ever exposes a confidence/validity flag, surface it
(see `LinkHealth`, §6 below) rather than rendering position blindly.

## 4. 2D Map — `/slam/map`

**Type:** `nav_msgs/OccupancyGrid` (standard — this is the right call, see
D-1/D-7a). Published 1–5 Hz, **full grid each time** (not incremental —
see D-9; at 1 m resolution over ≤15×15 m this is ≤225 `int8` cells, cheap
enough to resend in full).

```jsonc
// nav_msgs/OccupancyGrid, as seen by roslibjs
{
  "header": { "stamp": { "sec": 1745, "nanosec": 0 }, "frame_id": "map" },
  "info": {
    "resolution": 1.0,             // meters/cell — GCS-facing topic; SLAM's internal working resolution may be finer (D-7a)
    "width": 15,
    "height": 15,
    "origin": {                    // pinned to the entry/exit point (D-7)
      "position": { "x": 0.0, "y": 0.0, "z": 0.0 },
      "orientation": { "x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0 }
    }
  },
  "data": [-1, -1, 0, 0, 100, 0, "...225 int8 values, row-major, -1=unknown 0=free 100=occupied"]
}
```

`data[row * width + col]` gives that cell's occupancy (standard
`OccupancyGrid` semantics: `-1` unknown, `0` free, `100` occupied,
intermediate values = probability). The GCS derives "walls/openings
adjoining a cell" (the scoring language, Rulebook §9) from occupied cells
along a 1 m cell's boundary — this works as long as the *source* SLAM
resolution was fine enough to place occupied cells accurately relative to
the 1 m grid lines (D-7a).

## 5. Survivor Tags — `/vision/survivors`

**Type:** custom (proposed — not a standard ROS message; needs a `.msg`
file on the Jetson side, see D-13). Published on detection (and again on
re-detection/confidence update for an existing survivor).

```jsonc
{
  "survivor_id": 3,             // stable int/string id — re-detections update, not duplicate; capped at 6 distinct ids
  "x": 7.2,                     // meters, same origin/frame as /slam/map
  "y": 5.4,
  "confidence": 0.88
}
```

The GCS is responsible for quantizing `(x, y)` into the shared 1 m grid
cell (`floor((x - origin_x)/1.0)`, `floor((y - origin_y)/1.0)`) using the
*same* `origin`/`resolution` as whatever `/slam/map` last reported — this
keeps the Jetson-side message simple (raw meters) while guaranteeing tags
and map stay aligned. A 7th distinct `survivor_id` should be treated as a
data/integration bug to surface, not silently accepted (rules cap at 6).

## 6. System Heartbeat — `/gcs/heartbeat`

**Type:** custom, minimal (proposed: `std_msgs/Header` or an even simpler
timestamp message). Published 1 Hz. Confirms the Jetson + websocket link
is alive — this is the cheapest possible signal and should probably be
the first thing rendered/tested end-to-end, before any other topic.

Optionally paired with a richer `LinkHealth`-style message later if the
drone-side stack can report more than just "alive" (e.g. last-message age
per topic, computed client-side by the GCS instead if the Jetson doesn't
provide it directly) — not required by the rules for PS2 (see
REQUIREMENTS.md Open Question #5), but cheap value if added.

## 7. Live Video — `/camera/image_raw/compressed` — deliberately NOT via rosbridge

**Type:** would be `sensor_msgs/CompressedImage` if sent over ROS, but per
**D-6, this should not share the rosbridge/websocket connection** with
the topics above. Recommended instead: a separate transport (MJPEG-over-
HTTP or WebRTC) served directly from the Jetson and consumed by the
frontend's `<video>` element, independent of roslibjs/rosbridge. See
[DECISIONS.md](DECISIONS.md) D-6 for the reasoning (base64+JSON overhead,
and — more importantly — risk of delaying the Abort command behind queued
video frames on a shared connection).

## 8. Commands — `/gcs/command` (GCS → Jetson)

**Type:** custom, minimal (proposed: `std_msgs/String`). Published by the
frontend via roslibjs. **This is the entire operator command surface —
exactly two values, nothing else:**

```jsonc
{ "data": "start" }
{ "data": "abort" }
```

See [DECISIONS.md](DECISIONS.md) D-10 — this channel is not yet defined
by the drone-side topic table and needs a subscriber node on the Jetson
side plus a latency test under realistic (video-present) link load before
it can be considered done.

## 9. What Deliberately Does Not Exist

No schema is defined — anywhere, even as an unused/future placeholder —
for: waypoint upload, path correction, map edit/correction, survivor tag
correction, or mission replanning. This omission is intentional (see
[ARCHITECTURE.md](ARCHITECTURE.md) Design Principle 1 and
[COMMUNICATION.md](COMMUNICATION.md) §2.2). If a future engineering need
seems to require one of these, treat that as a signal to revisit the
architecture and the rules together, not as a routine schema addition.

## 10. Superseded

Earlier drafts of this document proposed a generic JSON `MapDelta` message
(incremental cell updates) and a placeholder `(col, row)` grid convention
with no defined origin. Both are superseded — see DECISIONS.md D-9 (full-
grid republish is cheap enough at 1 m resolution) and D-7 (origin pinned
to entry/exit point via `OccupancyGrid.info`). Kept here as a pointer, not
reproduced, so there's one source of truth.
