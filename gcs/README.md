# gcs/

The GCS application: Presentation Layer (frontend) + Link/Bridge Layer
(backend) — see `../docs/ARCHITECTURE.md`.

- `backend/` — **built.** A FastAPI service, the only component that
  talks to rosbridge (real Jetson or `../sim/`). See `backend/README.md`.
- `frontend/` — **not started yet.** Will call the backend's REST API.
