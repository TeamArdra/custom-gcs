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
├── gcs/                 (planned) The GCS application itself — UI + bridge. Empty in Phase 0.
├── protocol/            (planned) Shared, versioned Drone↔GCS interface definitions. Empty in Phase 0.
├── sim/                 (planned) Offline simulator/replay tooling for developing the GCS without drone hardware. Empty in Phase 0.
└── tools/               (planned) Dev scripts, log inspection, etc. Empty in Phase 0.
```

The `gcs/`, `protocol/`, `sim/`, and `tools/` directories currently
contain only a short README stating their intended purpose — they are
placeholders for Phase 1 (implementation), not yet in use.

## Next Step

Review the Phase 0 documents above, resolve or accept the open questions
in `docs/REQUIREMENTS.md` and `docs/DECISIONS.md`, confirm the proposed
architecture/stack, then begin Phase 1 implementation.
