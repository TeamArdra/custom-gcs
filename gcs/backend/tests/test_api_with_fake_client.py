from fastapi.testclient import TestClient

from app.main import create_app

from .fakes import FakeRosBridgeClient


def make_client() -> tuple[TestClient, FakeRosBridgeClient]:
    fake = FakeRosBridgeClient()
    app = create_app(client=fake)
    return TestClient(app), fake


def test_health_reports_connection_state():
    client, _ = make_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["connected"] is True


def test_telemetry_is_all_none_before_any_data_arrives():
    client, _ = make_client()
    body = client.get("/api/telemetry").json()
    assert body["mission_state"] is None
    assert body["battery"] == {"voltage": None, "current": None, "percentage": None}
    assert body["pose"]["position"] is None
    assert body["fcu"] == {
        "connected": None,
        "armed": None,
        "guided": None,
        "mode": None,
        "system_status": None,
    }
    assert body["velocity"] is None
    assert body["attitude"] is None
    assert body["gps"] is None
    assert body["statustext"] == []
    assert body["heartbeat_age_s"] is None


def test_telemetry_reflects_latest_cached_values():
    client, fake = make_client()
    fake.set_latest("/mission/state", {"data": "searching"})
    fake.set_latest("/mavros/battery", {"voltage": 15.2, "current": 2.1, "percentage": 0.62})
    fake.set_latest(
        "/mavros/local_position/pose",
        {"pose": {"position": {"x": 3.0, "y": 4.0, "z": 0.0}}},
    )
    fake.set_latest(
        "/mavros/state",
        {"connected": True, "armed": True, "guided": False, "mode": "STABILIZE", "system_status": 4},
    )
    fake.set_latest(
        "/mavros/local_position/velocity_local",
        {"twist": {"linear": {"x": 0.1, "y": 0.0, "z": 0.0}}},
    )
    fake.set_latest(
        "/mavros/global_position/global",
        {"status": {"status": 0}, "satellites_visible": 8, "latitude": 1.0, "longitude": 2.0, "altitude": 3.0},
    )
    fake.set_latest(
        "/mavros/imu/data",
        {"orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}},
    )
    fake.set_statustext_history([{"severity": 6, "text": "Arming Checks Disabled"}])
    fake.set_age_s("/gcs/heartbeat", 0.4)

    body = client.get("/api/telemetry").json()

    assert body["mission_state"] == "searching"
    assert body["battery"] == {"voltage": 15.2, "current": 2.1, "percentage": 0.62}
    assert body["pose"]["position"] == {"x": 3.0, "y": 4.0, "z": 0.0}
    assert body["fcu"] == {
        "connected": True,
        "armed": True,
        "guided": False,
        "mode": "STABILIZE",
        "system_status": 4,
    }
    assert body["velocity"] == {"x": 0.1, "y": 0.0, "z": 0.0}
    assert body["attitude"] == {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    assert body["gps"] == {
        "fix_status": 0,
        "satellites_visible": 8,
        "latitude": 1.0,
        "longitude": 2.0,
        "altitude": 3.0,
    }
    assert body["statustext"] == [{"severity": 6, "text": "Arming Checks Disabled"}]
    assert body["heartbeat_age_s"] == 0.4


def test_map_snapshot_flattens_occupancy_grid():
    client, fake = make_client()
    fake.set_latest(
        "/slam/map",
        {"info": {"resolution": 1.0, "width": 5, "height": 5}, "data": [-1] * 25},
    )

    body = client.get("/api/map").json()

    assert body["width"] == 5
    assert body["height"] == 5
    assert body["resolution"] == 1.0
    assert len(body["data"]) == 25


def test_map_snapshot_before_any_map_received():
    client, _ = make_client()
    body = client.get("/api/map").json()
    assert body == {"resolution": None, "width": None, "height": None, "data": None}


def test_survivors_endpoint_reflects_client_state():
    client, fake = make_client()
    fake.set_survivors(
        [
            {"survivor_id": 1, "x": 1.0, "y": 2.0, "confidence": 0.9},
            {"survivor_id": 2, "x": 5.0, "y": 6.0, "confidence": 0.8},
        ]
    )

    body = client.get("/api/survivors").json()

    assert len(body) == 2
    assert body[0]["survivor_id"] == 1


def test_start_command_publishes_start_and_only_start():
    client, fake = make_client()
    resp = client.post("/api/command/start")
    assert resp.status_code == 200
    assert resp.json() == {"status": "sent", "command": "start"}
    assert fake.published_commands == ["start"]


def test_abort_command_publishes_abort_and_only_abort():
    client, fake = make_client()
    resp = client.post("/api/command/abort")
    assert resp.status_code == 200
    assert resp.json() == {"status": "sent", "command": "abort"}
    assert fake.published_commands == ["abort"]


def test_get_requests_never_mutate_command_state():
    client, fake = make_client()
    for _ in range(3):
        client.get("/health")
        client.get("/api/telemetry")
        client.get("/api/map")
        client.get("/api/survivors")
    assert fake.published_commands == []


def test_ui_serves_the_frontend_and_wires_the_documented_endpoints():
    """gcs/frontend/ is now a compiled React/Vite SPA, not the old
    single-file prototype -- /ui/ serves a minimal HTML shell (a
    `<div id="root">` plus a hashed, bundled `<script type="module">`)
    and the actual button/fetch logic lives inside that bundle, which
    this Python TestClient has no JS engine to execute. So this test can
    only prove what's still structurally true from the served HTML: the
    mount serves a real build (not an empty/broken directory) at /ui
    specifically. The "calls exactly /api/telemetry,
    /api/command/start, /api/command/abort" guarantee now lives on the
    frontend side -- see gcs/frontend/src/api.test.ts."""
    client, _ = make_client()

    resp = client.get("/ui/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert '<div id="root">' in body
    assert '<script type="module"' in body


def test_no_route_exists_beyond_the_documented_command_surface():
    """This is the structural guarantee the architecture is built around:
    the operator command surface is exactly start/abort because no other
    mutating route is defined -- not because the frontend promises not to
    call one. See docs/REQUIREMENTS.md §6."""
    client, _ = make_client()
    forbidden_paths = (
        "/api/command/waypoint",
        "/api/command/land",
        "/api/command/reset",
        "/api/command/tag_survivor",
        "/api/map/edit",
        "/api/navigation/goto",
    )
    for path in forbidden_paths:
        assert client.post(path).status_code == 404
        assert client.put(path).status_code == 404
