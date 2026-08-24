# Engineering Decisions Log — NIDAR AirMouse GCS

This log tracks decisions that are **ours to make** — the competition
documents don't dictate them (contrast with [REQUIREMENTS.md](REQUIREMENTS.md),
which is only things the documents *do* dictate). Each entry: the
question, the current status, the leading option and why, and what would
change it.

Format inspired by lightweight ADRs. Add new entries at the top. Don't
delete superseded entries — mark them superseded and say why, so future-us
(or a teammate) can see the reasoning trail instead of just the current
answer.

---

## Open / Unresolved

### D-1: Drone ↔ GCS transport & link technology
**Status:** Open — blocked on drone-side hardware decisions and on
resolving REQUIREMENTS.md Open Question #1 (is a private/local Wi-Fi link
acceptable, given the rules ban "public Wi-Fi" specifically).
**Options on the table:** dedicated telemetry radio (e.g., SiK/RFD900-class)
for control/telemetry + a separate analog or digital video link; a single
private WiFi (ad-hoc or team-hosted AP, no internet) link carrying both;
a long-range digital link (e.g., ELRS-class) for control with a separate
video transmitter.
**Why not decided yet:** This is jointly owned with the drone-side
Onboard Autonomy team (per COMMUNICATION.md §4) and depends on real
constraints (weight budget within the 10 kg AUW cap, RF environment inside
a netted arena, achievable range/bandwidth) that aren't yet known.
**Revisit when:** drone-side hardware selection begins, or organiser
clarification on the Wi-Fi question arrives.

### D-2: Message protocol on the control/telemetry channel — custom vs. MAVLink
**Status:** Open, leaning toward a custom lightweight protocol for the
AirMouse-specific messages (map delta, survivor detection), possibly
alongside MAVLink for generic vehicle telemetry/heartbeat if the drone-side
flight stack is ArduPilot/PX4-based.
**Why:** MAVLink has no native message for a 1m×1m occupancy grid delta or
a survivor-detection-with-grid-reference — both would need custom
messages/extensions regardless, so adopting MAVLink buys compatibility for
generic telemetry but not for the mission-specific payloads. See
COMMUNICATION.md §2.4 for the full tradeoff.
**Revisit when:** the drone-side flight-control stack is chosen (a
custom/bare-metal FC vs. ArduPilot/PX4 changes this calculus a lot).

### D-3: Video protocol/format
**Status:** Open. No resolution, latency, or codec requirement exists in
the rules (REQUIREMENTS.md §10). Candidates: MJPEG-over-HTTP (simplest,
most robust to a lossy/low-bandwidth link, higher latency), RTSP+H.264
(better compression, more moving parts), WebRTC (lowest latency, most
implementation complexity). Leaning toward starting with MJPEG for
simplicity and revisiting if latency proves to be a problem in testing,
since a robust-but-laggy feed beats a low-latency feed that drops out.
**Revisit when:** the video transmitter hardware is chosen and real
link-bandwidth numbers exist.

### D-4: Grid coordinate labeling convention
**Status:** Open — see REQUIREMENTS.md Open Question #3. Need an
unambiguous convention (e.g., numeric `(col,row)` vs. chess-style `A1`)
and an agreed origin (most likely the entry/exit point, since it's the one
fixed reference both the team and the organisers know). Also need to
determine how/whether the team's independently-built grid is checked
against the organiser's reference grid at scoring time — not described in
the rules, may need direct clarification from organisers.
**Revisit when:** organiser clarification is available, or before the
mapping/localisation schema (DATA_MODELS.md §3–4) is finalized for
implementation.

### D-5: Mission logging / replay format
**Status:** Open, but leaning yes-build-it (see ARCHITECTURE.md §3.4). Not
a competition requirement. If built: format is likely a flat, append-only
local log (e.g., newline-delimited JSON of every message in
DATA_MODELS.md, plus timestamps) that a `sim/` replay tool can play back.
**Revisit when:** the Link/Bridge Layer's message types are stable enough
to log without constant format churn.

---

## Decided

### D-0: Overall technology stack (Presentation: React/TypeScript in a
native shell; Bridge: Python asyncio service; local transport: WebSocket +
separate video stream)
**Status:** Decided as the working default for Phase 0 planning purposes;
**not yet implemented**, and open to revision before real implementation
begins if the reasoning below stops holding.
**Reasoning:** see [ARCHITECTURE.md](ARCHITECTURE.md) §5 for the full
writeup. Summary: web rendering stack is the fastest path to a live
map+video+status UI for a student team on this timeline; Python bridge
minimizes translation distance to a likely ROS/Python-flavored drone-side
stack and is easy to iterate on before the drone interface stabilizes;
native shell (Tauri, with Electron and a plain local browser window as
fallbacks) serves the offline-only constraint and enables local file
access for mission logging.
**Alternatives considered and set aside (not ruled out):** a native
Qt/PySide desktop app (slower UI iteration, but worth reconsidering if the
team has strong existing Qt experience); implementing the bridge inside
Tauri's Rust backend directly (couples protocol iteration speed to Rust
familiarity/build times).
**Revisit when:** before writing the first line of application code —
this whole decision should be explicitly re-confirmed with whoever is
doing the implementation, not just inherited from Phase 0 planning.
