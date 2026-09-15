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


def test_frontiers_flattens_marker_array_to_points():
    client, fake = make_client()
    fake.set_latest(
        "/frontiers",
        {
            "markers": [
                {"pose": {"position": {"x": 1.0, "y": 2.0, "z": 0.5}}},
                {"pose": {"position": {"x": 3.0, "y": 4.0, "z": 0.5}}},
            ]
        },
    )

    body = client.get("/api/frontiers").json()

    assert body["points"] == [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}]


def test_frontiers_before_any_data_received():
    client, _ = make_client()
    body = client.get("/api/frontiers").json()
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


def test_perception_detections_before_any_data_received():
    client, _ = make_client()
    body = client.get("/api/perception/detections").json()
    assert body == {
        "frame_width": None,
        "frame_height": None,
        "timestamp": None,
        "detections": [],
    }


def test_perception_detections_reflects_client_state_with_nested_bbox():
    client, fake = make_client()
    fake.set_perception_detections(
        {
            "frame_width": 1280,
            "frame_height": 720,
            "timestamp": 123.456,
            "detections": [
                {
                    "detection_id": "det-1",
                    "class_name": "person",
                    "confidence": 0.91,
                    "bbox": {"x_min": 10.0, "y_min": 20.0, "x_max": 110.0, "y_max": 220.0},
                    "center_x": 60.0,
                    "center_y": 120.0,
                    "track_id": "t-1",
                    "source": "yolov8n",
                    "model_name": "yolov8n.pt",
                },
                {
                    "detection_id": "det-2",
                    "class_name": "person",
                    "confidence": 0.75,
                    "bbox": {"x_min": 300.0, "y_min": 40.0, "x_max": 380.0, "y_max": 260.0},
                    "center_x": 340.0,
                    "center_y": 150.0,
                    "track_id": "t-2",
                    "source": "yolov8n",
                    "model_name": "yolov8n.pt",
                },
            ],
        }
    )

    body = client.get("/api/perception/detections").json()

    assert body["frame_width"] == 1280
    assert body["frame_height"] == 720
    assert body["timestamp"] == 123.456
    assert len(body["detections"]) == 2
    assert body["detections"][0]["detection_id"] == "det-1"
    assert body["detections"][0]["bbox"] == {
        "x_min": 10.0,
        "y_min": 20.0,
        "x_max": 110.0,
        "y_max": 220.0,
    }
    assert body["detections"][1]["detection_id"] == "det-2"
    assert body["detections"][1]["bbox"]["x_max"] == 380.0


def test_perception_status_before_any_data_received():
    client, _ = make_client()
    body = client.get("/api/perception/status").json()
    assert body == {
        "camera_connected": None,
        "detector_enabled": None,
        "detector_ready": None,
        "detector_backend": None,
        "model_name": None,
        "person_count": None,
        "fps": None,
        "frame_width": None,
        "frame_height": None,
        "last_detection_age_s": None,
    }


def test_perception_status_reflects_client_state_and_ignores_unexpected_keys():
    client, fake = make_client()
    fake.set_perception_status(
        {
            "camera_connected": True,
            "detector_enabled": True,
            "detector_ready": True,
            "detector_backend": "onnxruntime",
            "model_name": "yolov8n.pt",
            "person_count": 2,
            "fps": 12.5,
            "frame_width": 1280,
            "frame_height": 720,
            "last_detection_age_s": 0.2,
            "some_future_field_the_gcs_does_not_know_about": "unexpected",
        }
    )

    resp = client.get("/api/perception/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["camera_connected"] is True
    assert body["detector_backend"] == "onnxruntime"
    assert body["person_count"] == 2
    assert body["fps"] == 12.5
    assert "some_future_field_the_gcs_does_not_know_about" not in body


def test_camera_status_disconnected_has_no_stream_url():
    client, fake = make_client()
    fake.set_perception_status({"camera_connected": False})

    body = client.get("/api/camera/status").json()

    assert body["connected"] is False
    assert body["stream_url"] is None


def test_camera_status_before_any_data_received():
    client, _ = make_client()
    body = client.get("/api/camera/status").json()
    assert body["connected"] is None
    assert body["stream_url"] is None


def test_camera_status_connected_builds_stream_url_from_settings():
    client, fake = make_client()
    fake.set_perception_status(
        {"camera_connected": True, "frame_width": 1280, "frame_height": 720, "fps": 12.5}
    )

    body = client.get("/api/camera/status").json()

    assert body["connected"] is True
    assert body["stream_url"] == "http://127.0.0.1:8090/stream.mjpg"
    assert body["frame_width"] == 1280
    assert body["frame_height"] == 720
    assert body["fps"] == 12.5


def test_perception_detections_empty_dict_upstream_behaves_same_as_no_data_yet():
    """An empty-but-present `{}` payload (e.g. the topic has been
    advertised/echoed once with a blank body, distinct from never having
    published at all) must still degrade to the same all-defaults
    response as test_perception_detections_before_any_data_received --
    the route's `if not msg` check treats `None` and `{}` identically, so
    this pins that both code paths actually land on the same output."""
    client, fake = make_client()
    fake.set_perception_detections({})

    body = client.get("/api/perception/detections").json()

    assert body == {
        "frame_width": None,
        "frame_height": None,
        "timestamp": None,
        "detections": [],
    }


def test_perception_detections_malformed_upstream_field_type_degrades_to_defaults():
    """A message that HAS arrived but has a field of the wrong type (e.g.
    a non-numeric confidence) must degrade the same way "no data yet"
    does (see the empty-dict test above), not surface as a bare 500 to
    every caller: PerceptionDetectionsResponse(**msg) raises a pydantic
    ValidationError inside the route body, which the route now catches
    and falls back to the schema's own all-defaults response -- see the
    test-engineer finding: unlike ros_client.py's own json.loads() guard
    (which silently drops a malformed WIRE payload before it's ever
    cached), the route layer must separately guard a malformed-but-
    JSON-valid CACHED payload."""
    fake = FakeRosBridgeClient()
    fake.set_perception_detections(
        {
            "frame_width": 640,
            "frame_height": 480,
            "timestamp": 1.0,
            "detections": [{"confidence": "high"}],
        }
    )
    app = create_app(client=fake)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/perception/detections")

    assert resp.status_code == 200
    assert resp.json() == {
        "frame_width": None,
        "frame_height": None,
        "timestamp": None,
        "detections": [],
    }


def test_perception_status_malformed_upstream_field_type_degrades_to_defaults():
    fake = FakeRosBridgeClient()
    fake.set_perception_status({"camera_connected": True, "person_count": "two"})
    app = create_app(client=fake)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/perception/status")

    assert resp.status_code == 200
    assert resp.json() == {
        "camera_connected": None,
        "detector_enabled": None,
        "detector_ready": None,
        "detector_backend": None,
        "model_name": None,
        "person_count": None,
        "fps": None,
        "frame_width": None,
        "frame_height": None,
        "last_detection_age_s": None,
    }


def test_camera_status_malformed_upstream_field_type_degrades_to_defaults():
    fake = FakeRosBridgeClient()
    fake.set_perception_status({"camera_connected": True, "frame_width": "big"})
    app = create_app(client=fake)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/camera/status")

    assert resp.status_code == 200
    assert resp.json() == {
        "connected": None,
        "stream_url": None,
        "frame_width": None,
        "frame_height": None,
        "fps": None,
    }


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


def test_list_missions_returns_both_missions_with_correct_shape():
    client, _ = make_client()
    body = client.get("/api/missions").json()

    assert len(body) == 2
    ids = {m["id"] for m in body}
    assert ids == {"main_nidar", "flight_test"}
    main_nidar = next(m for m in body if m["id"] == "main_nidar")
    assert main_nidar["ui_panel"] == "nidar"
    assert len(main_nidar["scenarios"]) == 1
    flight_test = next(m for m in body if m["id"] == "flight_test")
    assert flight_test["ui_panel"] == "flight_test"
    assert len(flight_test["scenarios"]) == 9


def test_get_mission_detail_for_known_missions():
    client, _ = make_client()

    main_nidar = client.get("/api/missions/main_nidar")
    assert main_nidar.status_code == 200
    assert main_nidar.json()["id"] == "main_nidar"

    flight_test = client.get("/api/missions/flight_test")
    assert flight_test.status_code == 200
    assert flight_test.json()["id"] == "flight_test"


def test_get_mission_detail_unknown_mission_404s():
    client, _ = make_client()
    resp = client.get("/api/missions/bogus")
    assert resp.status_code == 404


def test_get_mission_scenario_list_returns_nine_scenarios_three_implemented():
    client, _ = make_client()
    body = client.get("/api/missions/flight_test/scenarios").json()

    assert len(body) == 9
    implemented = [s for s in body if s["implemented"] is True]
    assert {s["id"] for s in implemented} == {"hover", "forward_backward_hover", "sideways_hover_sideways_hover"}


def test_get_mission_scenario_list_includes_steps():
    client, _ = make_client()
    body = client.get("/api/missions/flight_test/scenarios").json()

    by_id = {s["id"]: s for s in body}
    assert by_id["forward_backward_hover"]["steps"] == ["forward", "backward", "hover"]
    assert by_id["sideways_hover_sideways_hover"]["steps"] == ["sideways", "hover", "sideways", "hover"]
    assert by_id["hover"]["steps"] == ["takeoff", "hover", "land"]
    assert by_id["forward"]["steps"] == []


def test_flight_test_status_before_any_data_arrives():
    client, _ = make_client()
    body = client.get("/api/flight-test/status").json()
    assert body == {
        "scenario": None,
        "state": None,
        "target_altitude_m": None,
        "current_altitude_m": None,
        "current_position": None,
        "duration_s": None,
        "elapsed_hover_s": None,
        "armed": None,
        "execution_mode": None,
    }


def test_flight_test_status_reflects_seeded_data():
    client, fake = make_client()
    fake.set_flight_test_status(
        {
            "schema_version": 1,
            "scenario": "hover",
            "state": "hovering",
            "target_altitude_m": 1.0,
            "current_altitude_m": 0.98,
            "current_position": [0.0, 0.0, 0.98],
            "duration_s": 10.0,
            "elapsed_hover_s": 3.2,
            "armed": True,
            "execution_mode": "mock",
            "timestamp": 1234567890.1,
        }
    )

    body = client.get("/api/flight-test/status").json()

    assert body["scenario"] == "hover"
    assert body["state"] == "hovering"
    assert body["target_altitude_m"] == 1.0
    assert body["current_altitude_m"] == 0.98
    assert body["current_position"] == [0.0, 0.0, 0.98]
    assert body["duration_s"] == 10.0
    assert body["elapsed_hover_s"] == 3.2
    assert body["armed"] is True
    assert body["execution_mode"] == "mock"


def test_flight_test_status_malformed_upstream_field_type_degrades_to_defaults():
    fake = FakeRosBridgeClient()
    fake.set_flight_test_status({"state": "hovering", "target_altitude_m": "not-a-number"})
    app = create_app(client=fake)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/flight-test/status")

    assert resp.status_code == 200
    assert resp.json() == {
        "scenario": None,
        "state": None,
        "target_altitude_m": None,
        "current_altitude_m": None,
        "current_position": None,
        "duration_s": None,
        "elapsed_hover_s": None,
        "armed": None,
        "execution_mode": None,
    }


def test_multi_step_flight_test_status_before_any_data_arrives():
    client, _ = make_client()
    body = client.get("/api/flight-test/multi-step/status").json()
    assert body == {
        "scenario_id": None,
        "state": None,
        "phase": None,
        "current_step_index": None,
        "current_step_action": None,
        "total_steps": None,
        "current_position": None,
        "armed": None,
        "execution_mode": None,
    }


def test_multi_step_flight_test_status_reflects_seeded_data():
    client, fake = make_client()
    fake.set_multi_step_flight_test_status(
        {
            "schema_version": 1,
            "mission_id": "flight_test",
            "scenario_id": "forward_backward_hover",
            "state": "executing",
            "phase": "step",
            "current_step_index": 0,
            "current_step_action": "forward",
            "total_steps": 3,
            "current_position": [1.0, 0.0, 1.0],
            "armed": True,
            "execution_mode": "mock",
            "timestamp": 1234567890.1,
        }
    )

    body = client.get("/api/flight-test/multi-step/status").json()

    assert body["scenario_id"] == "forward_backward_hover"
    assert body["state"] == "executing"
    assert body["phase"] == "step"
    assert body["current_step_index"] == 0
    assert body["current_step_action"] == "forward"
    assert body["total_steps"] == 3
    assert body["current_position"] == [1.0, 0.0, 1.0]
    assert body["armed"] is True
    assert body["execution_mode"] == "mock"


def test_multi_step_flight_test_status_can_report_failed_distinct_from_aborted():
    client, fake = make_client()
    fake.set_multi_step_flight_test_status({"state": "failed", "scenario_id": "forward_backward_hover"})
    body = client.get("/api/flight-test/multi-step/status").json()
    assert body["state"] == "failed"


def test_multi_step_flight_test_status_malformed_upstream_field_type_degrades_to_defaults():
    fake = FakeRosBridgeClient()
    fake.set_multi_step_flight_test_status({"state": "executing", "total_steps": "three"})
    app = create_app(client=fake)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/flight-test/multi-step/status")

    assert resp.status_code == 200
    assert resp.json() == {
        "scenario_id": None,
        "state": None,
        "phase": None,
        "current_step_index": None,
        "current_step_action": None,
        "total_steps": None,
        "current_position": None,
        "armed": None,
        "execution_mode": None,
    }


def test_mission_start_publishes_mission_select_then_start_in_order():
    client, fake = make_client()
    resp = client.post("/api/mission/start", json={"mission": "flight_test", "scenario": "hover"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "sent", "mission": "flight_test", "scenario": "hover"}
    assert fake.published_mission_selects == [("flight_test", "hover")]
    assert fake.published_commands == ["start"]


def test_mission_start_works_for_both_new_multi_step_scenarios():
    for scenario_id in ("forward_backward_hover", "sideways_hover_sideways_hover"):
        client, fake = make_client()
        resp = client.post("/api/mission/start", json={"mission": "flight_test", "scenario": scenario_id})

        assert resp.status_code == 200
        assert resp.json() == {"status": "sent", "mission": "flight_test", "scenario": scenario_id}
        assert fake.published_mission_selects == [("flight_test", scenario_id)]
        assert fake.published_commands == ["start"]


def test_mission_start_unknown_mission_404s_and_publishes_nothing():
    client, fake = make_client()
    resp = client.post("/api/mission/start", json={"mission": "bogus", "scenario": "hover"})

    assert resp.status_code == 404
    assert fake.published_mission_selects == []
    assert fake.published_commands == []


def test_mission_start_unknown_scenario_400s_and_publishes_nothing():
    client, fake = make_client()
    resp = client.post("/api/mission/start", json={"mission": "flight_test", "scenario": "bogus"})

    assert resp.status_code == 400
    assert fake.published_mission_selects == []
    assert fake.published_commands == []


def test_mission_start_not_implemented_scenario_400s_and_publishes_nothing():
    client, fake = make_client()
    resp = client.post("/api/mission/start", json={"mission": "flight_test", "scenario": "forward"})

    assert resp.status_code == 400
    assert fake.published_mission_selects == []
    assert fake.published_commands == []


def test_mission_start_rejected_when_real_mission_already_active():
    client, fake = make_client()
    fake.set_latest("/mission/state", {"data": "entering"})

    for mission, scenario in (("main_nidar", "full_mission"), ("flight_test", "hover")):
        resp = client.post("/api/mission/start", json={"mission": mission, "scenario": scenario})
        assert resp.status_code == 409

    assert fake.published_mission_selects == []
    assert fake.published_commands == []


def test_mission_start_rejected_when_flight_test_already_active():
    client, fake = make_client()
    fake.set_flight_test_status({"state": "hovering"})

    resp = client.post("/api/mission/start", json={"mission": "flight_test", "scenario": "hover"})

    assert resp.status_code == 409
    assert fake.published_mission_selects == []
    assert fake.published_commands == []


def test_mission_start_rejected_when_multi_step_scenario_already_active():
    """Extends the 409 already-active guard to the second, separate
    status topic (MULTI_STEP_TEST_STATUS_TOPIC) -- starting hover while a
    multi-step scenario is mid-flight must be rejected too, even though
    they're technically different ROS nodes/topics. See
    app/ros_client.py's MULTI_STEP_TEST_STATUS_TOPIC docstring."""
    client, fake = make_client()
    fake.set_multi_step_flight_test_status({"state": "executing"})

    resp = client.post("/api/mission/start", json={"mission": "flight_test", "scenario": "hover"})

    assert resp.status_code == 409
    assert fake.published_mission_selects == []
    assert fake.published_commands == []


def test_mission_start_allowed_when_multi_step_scenario_is_failed_or_aborted_or_complete():
    for terminal_state in ("failed", "aborted", "complete", "idle", None):
        client, fake = make_client()
        if terminal_state is not None:
            fake.set_multi_step_flight_test_status({"state": terminal_state})

        resp = client.post("/api/mission/start", json={"mission": "flight_test", "scenario": "hover"})

        assert resp.status_code == 200, f"expected start to succeed after multi-step state={terminal_state!r}"


def test_command_start_and_abort_behave_completely_unchanged():
    """Reuses the existing command/start/abort behavior verbatim -- the
    fact these still pass unmodified alongside the new mission-aware
    surface IS the proof /api/command/start and /api/command/abort were
    not touched."""
    client, fake = make_client()

    resp = client.post("/api/command/start")
    assert resp.status_code == 200
    assert resp.json() == {"status": "sent", "command": "start"}
    assert fake.published_commands == ["start"]

    resp = client.post("/api/command/abort")
    assert resp.status_code == 200
    assert resp.json() == {"status": "sent", "command": "abort"}
    assert fake.published_commands == ["start", "abort"]


def test_new_mission_get_routes_never_publish_anything():
    client, fake = make_client()
    for _ in range(3):
        client.get("/api/missions")
        client.get("/api/missions/main_nidar")
        client.get("/api/missions/flight_test/scenarios")
        client.get("/api/flight-test/status")
        client.get("/api/flight-test/multi-step/status")
    assert fake.published_commands == []
    assert fake.published_mission_selects == []


def test_main_source_contains_no_forbidden_command_surface_words():
    """Grep-style guard: no new route path or function name in main.py's
    source introduces a throttle/motor/joystick/manual control surface,
    mirroring test_no_route_exists_beyond_the_documented_command_surface's
    structural guarantee at the source-text level."""
    import inspect

    from app import main as main_module

    source = inspect.getsource(main_module)
    for forbidden in ("throttle", "motor", "joystick", "manual"):
        assert forbidden not in source.lower()


def test_new_perception_and_camera_routes_are_get_only():
    """The perception/camera routes added alongside coverage/survivors
    are read-only, same guarantee as
    test_no_route_exists_beyond_the_documented_command_surface above --
    POST/PUT to any of them must 404, since they were never defined as
    mutating routes."""
    client, _ = make_client()
    for path in ("/api/perception/detections", "/api/perception/status", "/api/camera/status"):
        # The path itself exists (only GET is registered), so the
        # wrong-method response is 405 Method Not Allowed, not 404 --
        # either way, no mutation is possible via these paths.
        assert client.post(path).status_code == 405
        assert client.put(path).status_code == 405
