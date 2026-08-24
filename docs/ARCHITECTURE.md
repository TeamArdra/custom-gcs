# Architecture — NIDAR AirMouse Ground Control Station

Status: **Phase 0 — proposed architecture, not yet implemented.** See
[CLAUDE.md](../CLAUDE.md) for current project phase and the rule against
writing application code before this is agreed.

This document proposes a system architecture for the GCS and the
technology stack to build it in, with reasoning for each major choice. It
distinguishes competition **requirements** (from
[REQUIREMENTS.md](REQUIREMENTS.md)) from **engineering decisions** we are
free to make, which are tracked with rationale in
[DECISIONS.md](DECISIONS.md).

---

## 1. Design Principles Driven Directly by the Rules

Before any stack discussion, three requirements shape the architecture more
than any technology choice does:

1. **The command surface is exactly two buttons: Start, Abort.** Any
   additional operator-facing control that could modify navigation, the
   map, or survivor tags is a scored penalty (−50/instance) and undermines
   the entire premise of the mission (autonomy). The GCS must be
   architected so that this isn't just a UI convention — there must be no
   code path from operator input to mission-affecting state. The frontend
   should not even *have* the wiring for "send waypoint" or "edit map" to
   exist as dead code that a rushed late-night change could accidentally
   expose.
2. **Everything must be live, and everything must be local.** No
   post-flight completion window, no external network, no cloud. The GCS
   consumes a real-time stream from the drone during the ≤30-minute flight
   and must render map/video/telemetry/survivor updates as they arrive —
   there is no "finalize" step. Corollary: the GCS must start from a
   correct, fully offline-capable baseline (bundled assets, no CDN
   dependencies, no phone-home behavior) rather than "works online, degrade
   gracefully offline."
3. **The GCS is a passive consumer of autonomy, not a participant in it.**
   Mapping, detection, localisation, and navigation all happen onboard.
   The GCS's job is to receive, render, and (for exactly two actions)
   command. This pushes essentially all of the "hard" autonomy problems
   (SLAM, detection, path planning) out of this repository and onto the
   drone-side system — which is out of scope here, but the interfaces to
   it are in scope (see [COMMUNICATION.md](COMMUNICATION.md)).

## 2. System Context

```
┌─────────────────────────────────────────────────────────────────────┐
│                              ARENA (offline)                         │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────┐    │
│   │                         DRONE                                │    │
│   │  ┌───────────────┐  ┌────────────────────┐  ┌────────────┐ │    │
│   │  │ Flight         │  │ Onboard Autonomy /  │  │  Camera /  │ │    │
│   │  │ Controller     │◄─►│ Companion Computer  │◄─►│  Video     │ │    │
│   │  │ (attitude,     │  │  - SLAM / mapping   │  │  encoder   │ │    │
│   │  │  motor control,│  │  - survivor detect  │  └──────┬─────┘ │    │
│   │  │  failsafes)    │  │  - path planning    │         │        │    │
│   │  └───────────────┘  │  - grid localisation │         │        │    │
│   │                     │  - link/radio driver │         │        │    │
│   │                     └──────────┬───────────┘         │        │    │
│   └────────────────────────────────┼──────────────────────┼───────┘    │
│                                     │ local wireless link   │           │
│                                     │ (telemetry+map+       │ video     │
│                                     │  detections+cmd)      │ stream    │
│                                     ▼                       ▼           │
│   ┌────────────────────────────────────────────────────────────┐      │
│   │                  GROUND CONTROL STATION (GCS)                │      │
│   │   operated by exactly one operator, this repository          │      │
│   └────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

Everything inside the dotted arena box must work with **no external
network**. The "local wireless link" and "video stream" are the team's own
RF link(s) — technology TBD, see [DECISIONS.md](DECISIONS.md) §Comm Link.

## 3. Major Subsystems and Boundaries

This repository (`custom-gcs`) owns only the **Ground Control Station**
box above. Within it:

### 3.1 Presentation Layer ("GCS UI")
Renders: live video, live 2D grid map with survivor markers and drone
position, mission status/progress, and exposes exactly two controls
(Start, Abort). Consumes a local, well-defined API from the Link/Bridge
Layer below — it does not talk to radios/serial ports/sockets directly.
This isolation matters because it lets the UI be developed and tested
entirely offline against a simulator (see §6) without any drone hardware.

### 3.2 Link / Bridge Layer ("GCS Backend")
Owns the actual communication with the drone: parses the inbound telemetry/
map/detection/video streams into the data model defined in
[DATA_MODELS.md](DATA_MODELS.md), and is the only component allowed to
transmit the two permitted commands upstream. Exposes a local, transport-
agnostic API (e.g., WebSocket + a local media stream) to the Presentation
Layer. Isolating this layer means the *actual* RF technology (see
[DECISIONS.md](DECISIONS.md)) can change without touching the UI, and the
UI can be exercised against recorded/simulated data.

### 3.3 Communication Link (protocol + transport)
The abstract contract for what bytes/messages cross the air gap between
drone and GCS. Defined in [COMMUNICATION.md](COMMUNICATION.md) and
[DATA_MODELS.md](DATA_MODELS.md). Treated as a subsystem in its own right
because it is co-designed with the drone-side team and is the seam where
most integration risk lives.

### 3.4 Mission Recording / Local Logging (proposed, non-mandated)
Not required by the rules, but recommended: persist everything the GCS
receives and sends (video, map deltas, detections, telemetry, commands,
timestamps) to local disk during the mission. This is cheap to add if the
Link/Bridge Layer already models these as discrete messages, and it is the
only way to reconstruct/debug a run afterward (e.g., for scoring disputes
or post-mortems) given the "no post-flight processing" rule leaves no
other record. See [DECISIONS.md](DECISIONS.md).

### 3.5 Out of Scope for This Repository (drone-side)
Explicitly *not* built here, but interfaced with:
- Flight controller / autopilot
- Onboard autonomy (SLAM/mapping, survivor detection, grid localisation,
  path planning, exploration strategy)
- Onboard camera + video encoding
- Onboard radio/link driver (the drone-side half of §3.3)

These live in a separate repository/workstream. This repo's job regarding
them is to pin down clear, versioned interface contracts so the two sides
can be developed in parallel — see [COMMUNICATION.md](COMMUNICATION.md).

## 4. Subsystem Interaction (data flow during a mission)

```
Drone-side autonomy                  Link            GCS Backend         GCS UI
──────────────────────               ────            ───────────         ──────
telemetry (pos, batt, state)  ──────►  │  ──────────►  parse/validate ──► status panel
map deltas (1m×1m cells)      ──────►  │  ──────────►  parse/merge    ──► map renderer
survivor detections (grid ref)──────►  │  ──────────►  parse/dedupe   ──► survivor markers
video frames                  ──────►  │  ──────────►  relay/decode   ──► video panel
                                        │
operator "Start"  ◄────────────────────│◄────────────  command send   ◄── Start button
operator "Abort"  ◄────────────────────│◄────────────  command send   ◄── Abort button
```

Only two arrows point from GCS UI back toward the drone. That is
deliberate and load-bearing — see Design Principle 1.

## 5. Proposed Technology Stack

**We are proposing, not implementing.** Nothing below has been built. Each
choice is an engineering decision (not a competition requirement) and is
also logged in [DECISIONS.md](DECISIONS.md) with status.

### 5.1 Presentation Layer: Desktop web app (React + TypeScript) in a native shell (Tauri, tentative) or plain browser window

**Reasoning:**
- The UI's hard problems — a real-time 2D grid-map renderer with live
  survivor markers and drone position, plus a live video panel, updating
  continuously during a timed mission — are exactly what the web
  rendering stack (Canvas/WebGL, `<video>`, CSS layout) is good at, and
  where a student team gets the most velocity per hour invested.
- React + TypeScript gives strong typing across the message boundary
  (pairs naturally with the schemas in [DATA_MODELS.md](DATA_MODELS.md)),
  a huge ecosystem, and is a skill set most student teams already have or
  can pick up fast — this matters given the competition timeline (Design
  Review in Jan 2027, per the Rulebook's competition timeline) leaves
  limited runway.
  Given the timeline runs 2026-08-24 → January 2027, "fast to build,
  fast to debug under time pressure" outweighs "most resource-efficient."
- A native shell (Tauri is the current lean toward — see
  [DECISIONS.md](DECISIONS.md)) rather than a plain browser tab gets us:
  file-system access for local mission logging, no dependency on a
  separately-launched browser, a controllable offline environment, and no
  reliance on internet-fetched resources at runtime — directly serving the
  "no external network" constraint. Electron is the fallback if Tauri's
  Rust toolchain proves to be more friction than it's worth for this team;
  a plain local browser window is the zero-setup fallback if neither native
  shell is worth the packaging effort before finals.
- **Alternative considered:** a native Qt/PySide desktop app. Rejected as
  the default because it's slower to iterate UI in, though it remains a
  reasonable alternative if the team has strong Qt experience already —
  flagged as an open alternative, not ruled out.

### 5.2 Link / Bridge Layer: Python service (asyncio)

**Reasoning:**
- Drone-side autonomy stacks in this space overwhelmingly land on
  ROS/ROS2 and Python/C++ (SLAM libraries, detection models, MAVLink-based
  flight stacks are all Python-friendly). A Python bridge minimizes the
  translation distance to whatever the drone side ends up emitting, and
  makes it easy to prototype protocol adapters before the drone-side
  interface is finalized.
- Python has mature, low-friction libraries for exactly the transports in
  play here: serial/radio I/O, WebSockets, JSON/binary parsing, and (if
  MAVLink is adopted per [DECISIONS.md](DECISIONS.md)) `pymavlink`/MAVSDK.
- Keeping this layer as a separate local process (talking to the UI over a
  local WebSocket + local media stream) means it can be developed and unit
  tested completely independently of the UI, and swapped or rewritten
  (e.g., in Rust, if performance ever demands it) without the UI caring.
- **Alternative considered:** implement the bridge directly inside the
  Tauri app's Rust backend. Rejected as the default because it couples
  protocol/parsing iteration speed to Rust build times and Rust
  familiarity, which is a worse trade for a fast-moving student team than
  the small latency cost of an extra local process boundary. Revisit if
  profiling shows the process boundary is a real bottleneck.

### 5.3 Local Transport (UI ↔ Bridge)

- Control/telemetry/map/detections: local **WebSocket**, JSON messages
  matching [DATA_MODELS.md](DATA_MODELS.md).
- Video: a separate low-latency path from the control channel (e.g., a
  local HTTP MJPEG/WebRTC endpoint the bridge serves and the UI's `<video>`
  element consumes) so that heavy video traffic never head-of-line-blocks
  time-critical telemetry or the abort command.

### 5.4 Drone ↔ GCS Link (open, pending decision)

Not chosen yet — this depends on drone-side hardware decisions made in
parallel and on resolving Open Question #1 in
[REQUIREMENTS.md](REQUIREMENTS.md) (whether a private/local Wi-Fi link is
acceptable). Candidates and tradeoffs are recorded in
[DECISIONS.md](DECISIONS.md) rather than decided here.

## 6. Offline Development Strategy

Because the real drone/arena won't be available for most of the
development timeline, and because the rules forbid any runtime dependency
on external services anyway, the architecture treats a **local simulator/
replay tool** as a first-class, permanent part of the system rather than a
throwaway test harness:

- A simulator can emit synthetic telemetry, map-delta, and detection
  messages matching the exact schemas the real drone-side system will
  produce, letting the entire GCS (UI + bridge) be built and demoed long
  before flight hardware is ready.
- A replay tool can play back logged mission data (§3.4) for debugging and
  demos.
- Because the Presentation Layer only ever talks to the Bridge's local
  API (§4), it cannot tell the difference between a simulator and a real
  drone — this is a direct consequence of Design Principle 3, not extra
  work.

This is reflected in the repository's project structure (see
[README.md](../README.md)) as a `sim/` directory, planned but not yet
implemented.

## 7. Non-Goals

Explicitly out of scope for this repository, to keep boundaries clear:

- Flight control, autopilot, or any control-loop logic — that is the
  drone's onboard system.
- SLAM/mapping algorithms, survivor detection models, path planning —
  drone-side.
- Any UI affordance for manual navigation, map editing, or survivor
  tagging — forbidden by the rules (§6 of
  [REQUIREMENTS.md](REQUIREMENTS.md)), and therefore also forbidden by
  this architecture.
- Any dependency, at mission runtime, on internet/cloud services.
