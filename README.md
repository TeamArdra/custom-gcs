# NIDAR AirMouse — Custom Ground Control Station

A custom-built Ground Control Station (GCS) for an autonomous, GPS-denied
indoor search-and-rescue drone, developed for **NIDAR AirMouse** — Track 1
(Drone Innovation), Problem Statement 2, of the National Innovation
Challenge for Drone Application and Research (NIDAR), 2026-27 edition,
organised by Drone Federation India under the MeitY SwaYaan initiative.

## What This Is

The competition scenario: an earthquake-damaged, GPS-denied indoor arena
(≤15 m × 15 m), up to 6 survivors hidden in different rooms. An autonomous
drone must enter through a designated point, explore the maze, detect and
localise survivors, build a live 2D map, tag survivor locations on it, and
exit — entirely autonomously, in ≤30 minutes, with no manual navigation
assistance permitted.

This repository builds the **Ground Control Station**: the single
authorized interface between the human operator and the mission. It must
display live video, a live-updating 2D map, tagged survivor locations, and
mission status — and it can send exactly two commands: **start the
mission** and **abort it**. Everything else about the mission (mapping,
detection, navigation) happens autonomously onboard the drone; the GCS is
a real-time viewer, not a controller.

This repository contains **only** the GCS. The drone, flight controller,
and onboard autonomy system are a separate, parallel workstream.

## Current Status: Phase 0 — Requirements & Architecture

**No application code has been written yet.** This is intentional. Phase 0
is: read the competition rules closely, extract exactly what the GCS is
required to do, propose (but not yet build) an architecture and technology
stack, and define the data interfaces between the GCS and the drone-side
system.

| Document | Contents |
|---|---|
| [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) | Everything the competition documents say about the GCS, organized by topic, with every claim traceable to a specific rule. Also lists open questions the documents don't resolve. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Proposed system architecture, subsystem boundaries, and technology stack with reasoning for each choice. |
| [`docs/COMMUNICATION.md`](docs/COMMUNICATION.md) | Proposed data interfaces between the drone, flight controller, onboard autonomy, mapping, survivor detection, video system, and the GCS. |
| [`docs/DATA_MODELS.md`](docs/DATA_MODELS.md) | Draft message schemas for the Drone ↔ GCS interface. |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Log of engineering decisions (and open ones) that the competition rules don't dictate — technology and protocol choices, with reasoning. |
| [`CLAUDE.md`](CLAUDE.md) | Project context and rules for AI-assisted development in this repo. |

## Source of Truth

All competition requirements trace back to two documents, kept outside
this repository (they are local reference material, not part of the
GitHub repo):

- `Mission Brief - NIDAR AirMouse.pdf`
- `NIDAR-26-27-Rulebook-Ver_2_1.pdf`

`docs/REQUIREMENTS.md` is the working extraction of what those documents
say about the GCS. If anything here seems to conflict with them, the PDFs
win.

## Repository Layout

```
custom-gcs/
├── CLAUDE.md          Project context & rules for AI-assisted development
├── README.md           This file
├── docs/                Engineering documentation (see table above)
├── gcs/
│   ├── backend/         FastAPI backend (Python) — the only component that talks to rosbridge.
│   │                    Exposes a plain REST API + Swagger docs at /docs. See gcs/backend/README.md.
│   └── frontend/        (planned) The GCS UI (React/TypeScript). Not started yet.
├── protocol/            (planned) Shared, versioned Drone↔GCS interface definitions. Empty — not started yet.
├── sim/                 Rosbridge-protocol simulator (Python) — a working stand-in for the real
│                        Jetson's rosbridge_server, for developing/testing without drone hardware.
│                        See sim/README.md to run and test it.
└── tools/               (planned) Dev scripts, log inspection, etc. Empty — not started yet.
```

## Current Status: Phase 1 — Implementation

Phase 0 (requirements/architecture) is closed; see the docs above for
what was decided and why. Implementation has begun:

- **Built:** `sim/` — a rosbridge-protocol-compatible simulator publishing
  synthetic telemetry/map/survivor data matching `docs/DATA_MODELS.md`.
- **Built:** `gcs/backend/` — a FastAPI service that connects to
  rosbridge (`sim/` today, the real Jetson later — a config change, not a
  code change) and re-exposes it as a plain REST API. The two-command
  operator surface (start/abort) is enforced structurally: those are the
  only mutating routes that exist. Testable directly via Swagger at
  `/docs`, no frontend required.
- **Not yet started:** the GCS frontend (`gcs/frontend/`), the shared
  protocol package (`protocol/`), and video handling.

## Next Step

Build the GCS frontend against `gcs/backend/`'s REST API (itself running
against `sim/` during development), starting with the two non-negotiable
pieces: rendering live telemetry/mission status (proving the link is
alive end-to-end) and the Start/Abort controls calling
`POST /api/command/start` / `POST /api/command/abort`.
