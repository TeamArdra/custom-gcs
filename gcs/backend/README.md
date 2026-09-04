# gcs/backend/

The GCS backend: a FastAPI service, and the only component in this repo
that talks to rosbridge (real Jetson later, `../../sim/` for now). See
`../../docs/ARCHITECTURE.md` §5.2 and `../../docs/DECISIONS.md` D-0.

Exposes a plain REST API to `../frontend/` (a minimal static page this
app also serves at `/ui`) — the frontend never needs to know what a
`PoseStamped` or an `OccupancyGrid` is.

## The entire mutating API surface

```
POST /api/command/start
POST /api/command/abort
```

That's it — no other route can affect the mission. This is a structural
property of the app (`app/main.py`), not a convention; see
`tests/test_api_with_fake_client.py::test_no_route_exists_beyond_the_documented_command_surface`.

## Run it

Requires a rosbridge-speaking server to point at — normally `../../sim/`
during development (see `../../sim/README.md`).

```sh
# terminal 1: the simulated drone
cd ../../sim && source .venv/bin/activate && python -m rosbridge_sim

# terminal 2: this backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000/docs** — full interactive Swagger UI,
every endpoint testable by clicking "Try it out," no frontend required.

To point at the real Jetson later: `ROSBRIDGE_HOST=<jetson-ip> ROSBRIDGE_PORT=9090 uvicorn app.main:app` — no code changes.

## Test it

```sh
source .venv/bin/activate
python -m pytest -q
```

`tests/test_api_with_fake_client.py` is fast and needs nothing running —
it swaps in a fake rosbridge client. `tests/test_backend_against_sim.py`
is a real end-to-end test: it launches a real `sim/` subprocess and drives
the real HTTP API against it. It auto-skips if `../../sim/.venv` isn't
set up.

## Layout

```
app/
  config.py      Settings (rosbridge host/port) -- swap sim/ for the real Jetson here
  ros_client.py   owns the roslibpy connection + latest-value cache
  schemas.py      REST response shapes (flattened, frontend-friendly JSON)
  main.py         FastAPI app + routes
tests/
  fakes.py                       in-memory stand-in for ros_client.RosBridgeClient
  test_api_with_fake_client.py    fast route/schema tests, no networking
  test_backend_against_sim.py     real end-to-end test against a real sim/ subprocess
```
