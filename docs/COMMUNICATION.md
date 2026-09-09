# Communication Interfaces — NIDAR AirMouse

Status: **Phase 0 — proposed interfaces, not yet implemented or agreed
with the drone-side team.**

This document defines the data interfaces between the systems involved in
an AirMouse mission, per the task's requirement to define "the expected
communication/data interfaces between: Drone, Flight controller, Onboard
computer/autonomy system, GCS, Mapping system, Survivor detection/
localisation system, Video system."

The competition documents do not specify any of these interfaces
technically (protocol, message format, transport) — they only specify
*what information must cross them* (see
[REQUIREMENTS.md](REQUIREMENTS.md)). Every interface below is therefore an
**engineering decision or an explicitly unresolved question**, not a
competition requirement, unless a line item says otherwise.

## 1. Component Map

For AirMouse, the "drone" side is not necessarily five separate physical
boxes — flight controller, companion computer, and video encoder are often
one or two physical modules. We define the interfaces logically so the
GCS side doesn't need to know or care how the drone side partitions its
hardware.

| Component | Owns | Talks to |
|---|---|---|
| Flight Controller (FC) — **Pixhawk 6x** | Attitude control, motor output, low-level failsafes (battery, link-loss, geofence) | Onboard Autonomy System, via MAVLink/`mavros` |
| Onboard Autonomy System — **Jetson Nano**, running ROS + `rosbridge_server` | SLAM/mapping, survivor detection fusion, grid localisation, exploration/path planning, mission state machine | FC, Video System, **GCS** (via Comm Link) |
| Mapping System | Occupancy/connectivity grid construction (logically part of Onboard Autonomy) | Onboard Autonomy → GCS |
| Survivor Detection/Localisation System | Detects survivors, resolves to grid coordinate (logically part of Onboard Autonomy) | Onboard Autonomy → GCS |
| Video System | Camera capture + encode | GCS (separate stream from telemetry) |
| **GCS (this repo)** | Render + 2 commands | Onboard Autonomy System, Video System |

The FC is not expected to talk to the GCS directly — the Onboard Autonomy
System is the single source of truth that the GCS's Comm Link talks to,
aggregating whatever it needs from the FC internally. This keeps the
cross-air-gap protocol to one logical peer instead of several, which
matters because that link is also the one place the rules (no external
network, no tethers) most constrain design freedom.

## 2. The Drone ↔ GCS Interface (the one interface this repo must honor)

Everything below crosses the "local wireless link" box in
[ARCHITECTURE.md](ARCHITECTURE.md) §2. Per [DECISIONS.md](DECISIONS.md)
D-0/D-1/D-2, this link is now a concrete, working default rather than
fully open: **Jetson Nano** (companion computer, running ROS +
`rosbridge_server`) ↔ **GCS backend** (`gcs/backend/`, a FastAPI service
connecting via **`roslibpy`** over WebSocket, port 9090). The GCS
frontend does not talk to rosbridge directly — it calls the backend's
REST API, which re-exposes this data as plain JSON (D-0). The Jetson
itself talks to a **Pixhawk 6x** flight controller via **MAVLink**/
`mavros` — that hop is internal to the drone side and out of this repo's
scope (§3 below).

### 2.1 Channels

Two logically separate channels, for the reasons in ARCHITECTURE.md §5.3
(video must not block time-critical control/telemetry) — reinforced by
DECISIONS.md D-6/D-10, which flags queued video delaying the Abort command
as a safety issue, not just a UX one:

1. **Control/Telemetry channel** — bidirectional, low-bandwidth,
   latency-sensitive. This is the `rosbridge_server` WebSocket connection
   (port 9090). Carries mission status, telemetry, map, detection events,
   heartbeat, and the two operator commands.
2. **Video channel** — unidirectional (drone → GCS), high-bandwidth.
   Carries the live camera feed. **Deliberately kept off the rosbridge
   connection** (D-6) — a separate transport (leaning MJPEG-over-HTTP or
   WebRTC, per D-3) served directly from the Jetson.

### 2.2 Message Types (Control/Telemetry channel)

Schemas for each are in [DATA_MODELS.md](DATA_MODELS.md). Topics and
directions, reflecting the working ROS topic list (D-2, D-13):

| Topic | Type | Direction | Rate | Required by rules? |
|---|---|---|---|---|
| `/mission/state` | custom (`std_msgs/String` minimum) | Drone → GCS | On change | Yes — "mission progress and completion status" |
| `/mavros/battery` | `sensor_msgs/BatteryState` | Drone → GCS | 1–2 Hz | Yes — vehicle health, feeds "mission status" |
| `/mavros/local_position/pose` | `geometry_msgs/PoseStamped` | Drone → GCS | 10+ Hz | Yes — "drone position or estimated drone position" |
| `/map` | `nav_msgs/OccupancyGrid`, full grid each publish | Drone → GCS | 1–5 Hz | Yes — "2D map...continuously updated" |
| `/coverage_grid` | `nav_msgs/OccupancyGrid` (searched/unsearched, not walls) | Drone → GCS | ~4 Hz | Supports "explored/search coverage" visualization |
| `/planned_path` | `nav_msgs/Path` | Drone → GCS | On replan | Supports "planned path" visualization |
| `/telemetry/state` | custom, normalized JSON (`std_msgs/String`) | Drone → GCS | ~2 Hz | Supports autonomy/mapping/navigation state, sensor health |
| `/vision/survivors` | custom (D-13) | Drone → GCS | On detection | Yes — "grid coordinate...containing each detected survivor" |
| `/gcs/heartbeat` | custom, minimal | Drone → GCS | 1 Hz | Not explicitly required; recommended (link liveness) |
| `/gcs/command` | custom (`std_msgs/String`, `"start"`/`"abort"`) | **GCS → Drone** | On operator action | Yes — the *only* two permitted operator actions |

**Updated by the NIDAR Autonomy Migration** (folding gps_denied/raj-dev's
mapping/exploration/telemetry stack into `onboard-autonomy` as the single
canonical autonomy system — see `CHECKPOINT/CURRENT_STATE.md`): `/map`
supersedes the `/slam/map` name this table previously used (nothing had
ever published to it); `/coverage_grid`, `/planned_path`, and
`/telemetry/state` are new. Full shape and rationale for each:
`CHECKPOINT/docs/gcs_telemetry_contract.md`. `/telemetry/state` is a
read-only *summary* — it does not duplicate `/map`'s/`/coverage_grid`'s
full cell data or `/planned_path`'s full pose list, which stay on their
own native topics (see that doc's "two kinds of topic" section).

No other message type should exist on this channel. In particular: **no
waypoint, no path correction, no map-edit, no tag-correction, no
mission-replan message/topic is defined**, deliberately, per Design
Principle 1 in [ARCHITECTURE.md](ARCHITECTURE.md). If a future need
appears to add one, that is a signal to stop and re-check it against the
rules before writing it, not a routine schema change.

`/gcs/command` is currently the least-defined piece of this table — see
DECISIONS.md D-10. It needs a subscriber node on the Jetson and a latency
test under realistic (video-present) link load before it's considered
done, given it carries the operator's abort authority.

### 2.3 Video Channel

One direction, drone → GCS, continuous during flight, **not** via
`rosbridge_server`/roslibjs (D-6). Format/protocol still open (D-3) —
leaning MJPEG-over-HTTP first for simplicity and robustness to a lossy
link, WebRTC if latency proves to be a problem in testing.

### 2.4 Transport / Protocol

**Decided (working default), see DECISIONS.md D-0/D-1/D-2:** `mavros`/
MAVLink for the Pixhawk↔Jetson hop (standard, out of this repo's scope);
ROS topics over `rosbridge_server` + `roslibpy` for the Jetson↔GCS-backend
hop, using standard ROS message types wherever one exists and two small
custom message types (`/vision/survivors`, `/mission/state`) where it
doesn't. The frontend sits behind the GCS backend's REST API, not on this
connection directly (D-0). Video is intentionally routed around this same
connection (§2.3).

Remaining open items on this decision (tracked in DECISIONS.md, not
duplicated here): the physical RF hardware for the Jetson↔GCS local link
(D-1's residual item), and whether rosbridge holds up under combined
telemetry+map+command load once video is correctly kept off it (D-6).

This decision was made jointly with the drone-side/companion-computer
team, per the interface having two owners (§4 below) — not unilaterally
by the GCS side.

## 3. Interfaces Not Owned By This Repository (context only)

These exist on the drone side and are documented here only so the
boundary is unambiguous — this repo does not implement or specify their
internals, only what crosses into the Drone ↔ GCS interface above.

- **FC ↔ Onboard Autonomy System**: **decided** — MAVLink via `mavros`,
  between the Pixhawk 6x and the Jetson Nano (DECISIONS.md D-2). Entirely
  a drone-side concern to implement; noted here only because it's the
  source of the `/mavros/*` topics the GCS consumes.
- **Onboard Autonomy ↔ Mapping System**: internal SLAM pipeline
  (algorithm unspecified by the rules). Drone-side concern; the GCS only
  sees its *output* via `MapDelta`.
- **Onboard Autonomy ↔ Survivor Detection System**: internal detection/
  fusion pipeline. Drone-side concern; the GCS only sees its *output* via
  `SurvivorDetection`.
- **Onboard Autonomy ↔ Video System**: however the drone-side team wires
  the camera/encoder to whatever transmits the video channel.

## 4. Interface Stability Note

Because the drone-side system and this GCS will very likely be built by
different people/subteams on different timelines, the Drone ↔ GCS
interface in §2 is the single most important contract in the whole
project. Recommend treating [DATA_MODELS.md](DATA_MODELS.md) as a
versioned, reviewed schema (not something either side edits unilaterally),
and building the simulator described in
[ARCHITECTURE.md](ARCHITECTURE.md) §6 against that schema as early as
possible so both sides can develop against a stable contract instead of
against each other's in-progress code.

## 5. Simulation Channel (Not Part Of The Drone ↔ GCS Interface)

A second, entirely separate topic surface exists under the `/simulation/`
namespace (`/simulation/command`, `/simulation/mission/state`,
`/simulation/map`, etc.) — added 2026-09-10 for the GCS's dev/bench-only
"RUN SIMULATION" feature (gated off by default in the frontend build —
see `README.md`). It never overlaps with, redefines, or substitutes for
any topic in §2's table: `/simulation/command` accepts only
`"run"`/`"reset"`, never `"start"`/`"abort"`, and the real
`/gcs/command`/`/mission/state` topics are untouched by it. Full design:
`../../CHECKPOINT/docs/simulation_architecture.md`. Not documented
further here since it is not part of the real Drone ↔ GCS contract this
file describes — this section exists only so a reader of this file knows
the second channel exists and where to find it.
