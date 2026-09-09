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
        "/map",
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


def test_coverage_snapshot_flattens_occupancy_grid():
    client, fake = make_client()
    fake.set_latest(
        "/coverage_grid",
        {"info": {"resolution": 1.0, "width": 3, "height": 3}, "data": [0] * 9},
    )

    body = client.get("/api/coverage").json()

    assert body["width"] == 3
    assert body["height"] == 3
    assert len(body["data"]) == 9


def test_coverage_snapshot_before_any_data_received():
    client, _ = make_client()
    body = client.get("/api/coverage").json()
    assert body == {"resolution": None, "width": None, "height": None, "data": None}


def test_planned_path_flattens_pose_array_to_points():
    client, fake = make_client()
    fake.set_latest(
        "/planned_path",
        {
            "poses": [
                {"pose": {"position": {"x": 1.0, "y": 2.0}}},
                {"pose": {"position": {"x": 3.0, "y": 4.0}}},
            ]
        },
    )

    body = client.get("/api/path").json()

    assert body["points"] == [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}]


def test_planned_path_before_any_data_received():
    client, _ = make_client()
    body = client.get("/api/path").json()
    assert body == {"points": []}


def test_telemetry_reflects_mapping_autonomy_navigation_from_telemetry_state():
    """/telemetry/state is a normalized JSON contract from onboard-autonomy
    (see CHECKPOINT/docs/gcs_telemetry_contract.md); RosBridgeClient caches
    it already-parsed, so the fake stores the same shape a real client
    would after JSON-decoding the std_msgs/String payload."""
    client, fake = make_client()
    fake.set_latest(
        "/telemetry/state",
        {
            "autonomy": {
                "state": "SEARCHING_FRONTIER",
                "objective": "Explore unexplored region",
                "target": [4.2, 7.8],
                "next_action": "Navigate to frontier",
            },
            "sensors": {"slam": "ok", "lidar": "ok", "rangefinder": "not_integrated", "camera": "not_integrated"},
            "mapping": {
                "available": True,
                "resolution_m": 0.05,
                "width_cells": 320,
                "height_cells": 320,
                "origin_x": -8.5,
                "origin_y": -1.0,
                "coverage_cell_size_m": 1.0,
                "explored_pct": 63.5,
            },
            "navigation": {
                "target": [4.2, 7.8],
                "frontier_count": 3,
                "candidate_count": 5,
                "blacklisted_count": 1,
                "geofence_breached": False,
            },
        },
    )

    body = client.get("/api/telemetry").json()

    assert body["autonomy"]["state"] == "SEARCHING_FRONTIER"
    assert body["autonomy"]["target"] == [4.2, 7.8]
    assert body["sensors"]["slam"] == "ok"
    assert body["mapping"]["available"] is True
    assert body["mapping"]["explored_pct"] == 63.5
    assert body["navigation"]["frontier_count"] == 3
    assert body["navigation"]["geofence_breached"] is False


def test_telemetry_mapping_defaults_before_any_telemetry_state_received():
    client, _ = make_client()
    body = client.get("/api/telemetry").json()
    assert body["mapping"] == {
        "available": False, "resolution_m": None, "width_cells": None, "height_cells": None,
        "origin_x": None, "origin_y": None, "coverage_cell_size_m": None, "explored_pct": None,
    }
    assert body["autonomy"] == {"state": None, "objective": None, "target": None, "next_action": None}
    assert body["navigation"] == {
        "target": None, "frontier_count": None, "candidate_count": None,
        "blacklisted_count": None, "geofence_breached": None,
    }


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


def test_start_command_reports_sent_even_when_ros_client_reports_disconnected():
    """Pins the API's actual current contract, not a desired one: the
    route never checks `ros_client.is_connected` before calling
    `publish_command()` (see app/main.py:start_mission/abort_mission), so
    a disconnected-but-not-yet-raising client still gets a 200 "sent"
    response. This means the operator cannot distinguish "the drone
    received this command" from "the backend merely accepted the HTTP
    request" from this response alone -- see docs/COMMUNICATION.md's note
    that /gcs/command has no defined ack semantics yet (D-10). If a future
    change adds a pre-publish connectivity check, this test's expected
    response should change to match the new documented contract -- don't
    leave it passing on a stale assumption."""
    client, fake = make_client()
    fake.is_connected = False

    resp = client.post("/api/command/start")

    assert resp.status_code == 200
    assert resp.json() == {"status": "sent", "command": "start"}
    assert fake.published_commands == ["start"]


def test_command_route_surfaces_a_structured_503_when_the_downstream_publish_fails():
    """Exercises the one error path publish_command can actually raise in
    production: RuntimeError("not connected to rosbridge") when the
    RosBridgeClient was never connected (see app/ros_client.py). Both
    routes now wrap ros_client.publish_command() in a try/except that
    re-raises as fastapi.HTTPException(503, ...), so the operator gets a
    structured, actionable {"detail": ...} body distinguishing "not
    connected to the drone" from any other server-side bug, instead of an
    opaque bare 500 (see docs/DECISIONS.md D-10 on abort reliability)."""
    fake = FakeRosBridgeClient()
    fake.fail_publish_with(RuntimeError("not connected to rosbridge"))
    app = create_app(client=fake)
    client = TestClient(app)

    resp = client.post("/api/command/abort")

    assert resp.status_code == 503
    assert "not connected to rosbridge" in resp.json()["detail"]
    assert fake.published_commands == []


def test_start_command_also_surfaces_a_structured_503_when_disconnected():
    fake = FakeRosBridgeClient()
    fake.fail_publish_with(RuntimeError("not connected to rosbridge"))
    app = create_app(client=fake)
    client = TestClient(app)

    resp = client.post("/api/command/start")

    assert resp.status_code == 503
    assert "not connected to rosbridge" in resp.json()["detail"]
    assert fake.published_commands == []


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
