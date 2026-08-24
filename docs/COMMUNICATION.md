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
| Flight Controller (FC) | Attitude control, motor output, low-level failsafes (battery, link-loss, geofence) | Onboard Autonomy System |
| Onboard Autonomy System | SLAM/mapping, survivor detection fusion, grid localisation, exploration/path planning, mission state machine | FC, Video System, **GCS** (via Comm Link) |
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
[ARCHITECTURE.md](ARCHITECTURE.md) §2. This is the interface this
repository's Link/Bridge Layer implements the GCS side of.

### 2.1 Channels

Two logically separate channels, for the reasons in ARCHITECTURE.md §5.3
(video must not block time-critical control/telemetry):

1. **Control/Telemetry channel** — bidirectional, low-bandwidth,
   latency-sensitive. Carries telemetry, map deltas, detection events,
   mission status, and the two operator commands.
2. **Video channel** — unidirectional (drone → GCS), high-bandwidth.
   Carries the live camera feed.

Whether these are two physically separate radios or two logical streams
over one radio is an open engineering decision — see
[DECISIONS.md](DECISIONS.md).

### 2.2 Message Types (Control/Telemetry channel)

Schemas for each are in [DATA_MODELS.md](DATA_MODELS.md). Directions:

| Message | Direction | Required by rules? |
|---|---|---|
| `MissionStatus` | Drone → GCS | Yes — "mission progress and completion status" |
| `TelemetryUpdate` (position/pose estimate, battery, flight state) | Drone → GCS | Yes — "drone position or estimated drone position" |
| `MapDelta` (incremental 1m×1m grid cell updates) | Drone → GCS | Yes — "2D map...continuously updated" |
| `SurvivorDetection` (grid ref, confidence, id) | Drone → GCS | Yes — "grid coordinate...containing each detected survivor" |
| `LinkHealth` (comm/system health) | Drone → GCS | Not explicitly required for PS2 (see REQUIREMENTS.md Open Question #5); recommended anyway |
| `StartMission` | GCS → Drone | Yes — the one non-abort permitted command |
| `AbortMission` | GCS → Drone | Yes — the one abort/emergency-stop permitted command |

No other message type should exist on this channel. In particular: **no
waypoint, no path correction, no map-edit, no tag-correction, no
mission-replan message type is defined**, deliberately, per Design
Principle 1 in [ARCHITECTURE.md](ARCHITECTURE.md). If a future need
appears to add one, that is a signal to stop and re-check it against the
rules before writing it, not a routine schema change.

### 2.3 Video Channel

One direction, drone → GCS, continuous during flight. Format/protocol is
an open engineering decision (see [DECISIONS.md](DECISIONS.md)) —
candidates include an MJPEG stream, RTSP, or a WebRTC connection over the
local link, depending on what the chosen radio/link hardware supports and
what bandwidth is realistically available inside a netted 15 m × 15 m
arena.

### 2.4 Transport / Protocol (open)

Not decided. Two broad options, both consistent with "locally deployed
communication systems, no external network":

- **A generic point-to-point digital link** (e.g., a telemetry radio pair
  or a private/local WiFi link — pending Open Question #1 in
  REQUIREMENTS.md) carrying a custom lightweight message protocol (e.g.,
  JSON or a compact binary framing) designed specifically around the
  message types in §2.2.
- **MAVLink** over the same class of link. MAVLink is explicitly
  compatible with the rules (Rulebook §8.2 permits open-source protocols/
  software) and is well-trodden for telemetry + command + video-adjacent
  metadata, but it is designed around GPS-referenced, waypoint-style
  missions and doesn't have a native message for "1m×1m occupancy grid
  delta" or "survivor detection with grid reference" — those would need to
  be custom MAVLink messages/extensions regardless. Reusing MAVLink's
  existing messages for telemetry/heartbeat/battery/mode while defining
  custom messages for map/survivor data is a middle path worth
  considering once the drone-side stack (ArduPilot/PX4 vs. fully custom
  autonomy) is chosen.

This decision is deferred to [DECISIONS.md](DECISIONS.md) and should be
made jointly with whoever owns the drone-side Onboard Autonomy System, not
unilaterally by the GCS side — the interface has two owners.

## 3. Interfaces Not Owned By This Repository (context only)

These exist on the drone side and are documented here only so the
boundary is unambiguous — this repo does not implement or specify their
internals, only what crosses into the Drone ↔ GCS interface above.

- **FC ↔ Onboard Autonomy System**: however the drone-side team chooses
  (e.g., MAVLink/ROS2 over a serial or internal network link between FC
  and companion computer). Entirely a drone-side concern.
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
