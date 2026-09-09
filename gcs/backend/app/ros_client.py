"""Owns the single connection to rosbridge and caches the latest value per
topic. This is the hardware-isolation seam on the backend side: every
route in app/main.py only ever calls `latest()` / `survivors()` /
`publish_command()` on this class -- pointing at the real Jetson instead
of sim/rosbridge_sim is a Settings change (app/config.py), not a change
to anything that touches roslibpy directly.

Threading note: roslibpy runs its own connection thread (via Twisted),
independent of FastAPI/uvicorn's asyncio event loop. Subscription
callbacks fire on that thread, so the cache is protected by a plain lock
rather than assuming any particular event loop.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import roslibpy

MISSION_STATE_TOPIC = "/mission/state"
BATTERY_TOPIC = "/mavros/battery"
POSE_TOPIC = "/mavros/local_position/pose"
SURVIVORS_TOPIC = "/vision/survivors"
HEARTBEAT_TOPIC = "/gcs/heartbeat"
COMMAND_TOPIC = "/gcs/command"

# Mapping/exploration/telemetry topics -- adopted from onboard-autonomy's
# NIDAR Autonomy Migration (folding gps_denied/raj-dev's mapping stack in;
# see CHECKPOINT/CURRENT_STATE.md). `/map` supersedes the never-implemented
# `/slam/map` placeholder this backend used before that migration -- see
# docs/DATA_MODELS.md's changelog note. Full contract:
# CHECKPOINT/docs/gcs_telemetry_contract.md.
MAP_TOPIC = "/map"
COVERAGE_GRID_TOPIC = "/coverage_grid"
PLANNED_PATH_TOPIC = "/planned_path"
TELEMETRY_STATE_TOPIC = "/telemetry/state"

# Simulation-only topics -- the GCS "RUN SIMULATION" path. Every name
# lives under /simulation/, entirely separate from the real topics above
# (see onboard-autonomy/nidar_autonomy/topics.py's "Simulation-only
# topics" section and onboard-autonomy/nidar_autonomy/simulation_node.py,
# which is the only thing that ever publishes/subscribes these).
# publish_simulation_command() below is a SEPARATE method from
# publish_command() -- it can never reach COMMAND_TOPIC (the real
# /gcs/command), and publish_command() can never reach
# SIMULATION_COMMAND_TOPIC. See CHECKPOINT/CURRENT_STATE.md.
SIMULATION_COMMAND_TOPIC = "/simulation/command"
SIMULATION_MISSION_STATE_TOPIC = "/simulation/mission/state"
SIMULATION_STATUS_TOPIC = "/simulation/status"
SIMULATION_MAP_TOPIC = "/simulation/map"
SIMULATION_COVERAGE_GRID_TOPIC = "/simulation/coverage_grid"
SIMULATION_PLANNED_PATH_TOPIC = "/simulation/planned_path"
SIMULATION_TELEMETRY_STATE_TOPIC = "/simulation/telemetry/state"
VALID_SIMULATION_COMMANDS = ("run", "reset")

# Read-only FCU telemetry, subscribed directly via rosbridge -- same
# pattern already used for BATTERY_TOPIC/POSE_TOPIC above (both already
# read straight from mavros topics). This does NOT give the GCS any new
# command surface: every topic below is a subscription, never published
# to, and the only two things this client ever publishes are "start"/
# "abort" on COMMAND_TOPIC. See CHECKPOINT/INTEGRATION_CHECKPOINTS.md --
# the Jetson/mavros remain the only things that ever command the Pixhawk.
FCU_STATE_TOPIC = "/mavros/state"
STATUSTEXT_TOPIC = "/mavros/statustext/recv"
VELOCITY_TOPIC = "/mavros/local_position/velocity_local"
GPS_TOPIC = "/mavros/global_position/global"
IMU_TOPIC = "/mavros/imu/data"

# Declared ROS types per docs/DATA_MODELS.md (plus the mavros telemetry
# topics above, typed per the real mavros/ArduCopter message set). These
# are metadata only as far as sim/rosbridge_sim is concerned (it doesn't
# validate them), but matter once this connects to a real rosbridge_server
# backed by an actual ROS graph.
_SUBSCRIBED_TOPIC_TYPES = {
    MISSION_STATE_TOPIC: "std_msgs/String",
    BATTERY_TOPIC: "sensor_msgs/BatteryState",
    POSE_TOPIC: "geometry_msgs/PoseStamped",
    MAP_TOPIC: "nav_msgs/OccupancyGrid",
    SURVIVORS_TOPIC: "nidar_airmouse/SurvivorDetection",
    HEARTBEAT_TOPIC: "std_msgs/Header",
    FCU_STATE_TOPIC: "mavros_msgs/State",
    STATUSTEXT_TOPIC: "mavros_msgs/StatusText",
    VELOCITY_TOPIC: "geometry_msgs/TwistStamped",
    GPS_TOPIC: "sensor_msgs/NavSatFix",
    IMU_TOPIC: "sensor_msgs/Imu",
    COVERAGE_GRID_TOPIC: "nav_msgs/OccupancyGrid",
    PLANNED_PATH_TOPIC: "nav_msgs/Path",
    TELEMETRY_STATE_TOPIC: "std_msgs/String",
    SIMULATION_MISSION_STATE_TOPIC: "std_msgs/String",
    SIMULATION_STATUS_TOPIC: "std_msgs/String",
    SIMULATION_MAP_TOPIC: "nav_msgs/OccupancyGrid",
    SIMULATION_COVERAGE_GRID_TOPIC: "nav_msgs/OccupancyGrid",
    SIMULATION_PLANNED_PATH_TOPIC: "nav_msgs/Path",
    SIMULATION_TELEMETRY_STATE_TOPIC: "std_msgs/String",
}
_COMMAND_TOPIC_TYPE = "std_msgs/String"
VALID_COMMANDS = ("start", "abort")

# Rolling history of recent FCU status-text lines, newest last -- mirrors
# onboard-autonomy/flight_command.py's own STATUSTEXT history so the GCS
# can show recent warnings/failures, not just the single latest line.
_STATUSTEXT_HISTORY = 10


class RosBridgeClient:
    def __init__(self, host: str, port: int, connect_timeout_s: float = 5.0) -> None:
        self._host = host
        self._port = port
        self._connect_timeout_s = connect_timeout_s
        self._ros = roslibpy.Ros(host=host, port=port)
        self._lock = threading.Lock()
        self._latest: dict[str, Any] = {}
        self._last_seen: dict[str, float] = {}
        self._survivors: dict[int, dict] = {}
        self._statustext_history: list[dict] = []
        self._subscriptions: list[roslibpy.Topic] = []
        self._command_topic: roslibpy.Topic | None = None
        self._simulation_command_topic: roslibpy.Topic | None = None

    def connect(self) -> None:
        self._ros.run(timeout=self._connect_timeout_s)
        for topic, msg_type in _SUBSCRIBED_TOPIC_TYPES.items():
            sub = roslibpy.Topic(self._ros, topic, msg_type)
            sub.subscribe(self._make_handler(topic))
            self._subscriptions.append(sub)
        self._command_topic = roslibpy.Topic(self._ros, COMMAND_TOPIC, _COMMAND_TOPIC_TYPE)
        self._command_topic.advertise()
        self._simulation_command_topic = roslibpy.Topic(
            self._ros, SIMULATION_COMMAND_TOPIC, _COMMAND_TOPIC_TYPE
        )
        self._simulation_command_topic.advertise()

    def disconnect(self) -> None:
        for sub in self._subscriptions:
            sub.unsubscribe()
        self._subscriptions.clear()
        if self._command_topic is not None:
            self._command_topic.unadvertise()
            self._command_topic = None
        if self._simulation_command_topic is not None:
            self._simulation_command_topic.unadvertise()
            self._simulation_command_topic = None
        self._ros.terminate()

    def _make_handler(self, topic: str):
        def handler(message: dict) -> None:
            with self._lock:
                self._last_seen[topic] = time.time()
                if topic == SURVIVORS_TOPIC:
                    self._survivors[message["survivor_id"]] = message
                elif topic == STATUSTEXT_TOPIC:
                    self._statustext_history.append(message)
                    if len(self._statustext_history) > _STATUSTEXT_HISTORY:
                        self._statustext_history.pop(0)
                elif topic in (TELEMETRY_STATE_TOPIC, SIMULATION_TELEMETRY_STATE_TOPIC):
                    # std_msgs/String carrying a JSON-encoded normalized
                    # telemetry contract (see
                    # CHECKPOINT/docs/gcs_telemetry_contract.md) -- cache
                    # the *parsed* dict, not the raw String wrapper, so
                    # latest(TELEMETRY_STATE_TOPIC) returns the contract
                    # directly. A malformed payload is dropped (logged via
                    # the exception being swallowed here), not allowed to
                    # crash the roslibpy callback thread or poison the
                    # cache with stale/partial data.
                    try:
                        self._latest[topic] = json.loads(message["data"])
                    except (KeyError, TypeError, json.JSONDecodeError):
                        pass
                else:
                    self._latest[topic] = message

        return handler

    @property
    def is_connected(self) -> bool:
        return self._ros.is_connected

    def latest(self, topic: str) -> Any:
        with self._lock:
            return self._latest.get(topic)

    def age_s(self, topic: str) -> float | None:
        """Seconds since the last message on `topic` was received, or
        None if none has ever arrived -- lets callers distinguish "no
        data yet" from "data, but stale" rather than just reporting the
        last cached value forever."""
        with self._lock:
            last = self._last_seen.get(topic)
        return None if last is None else time.time() - last

    def survivors(self) -> list[dict]:
        with self._lock:
            return sorted(self._survivors.values(), key=lambda s: s["survivor_id"])

    def statustext_history(self) -> list[dict]:
        with self._lock:
            return list(self._statustext_history)

    def publish_command(self, command: str) -> None:
        """The entire GCS -> drone command surface. Deliberately accepts
        only "start"/"abort" -- see docs/REQUIREMENTS.md §4/§6."""
        if command not in VALID_COMMANDS:
            raise ValueError(f"invalid command: {command!r}; must be one of {VALID_COMMANDS}")
        if self._command_topic is None:
            raise RuntimeError("not connected to rosbridge")
        self._command_topic.publish(roslibpy.Message({"data": command}))

    def publish_simulation_command(self, command: str) -> None:
        """The ENTIRE simulation control surface -- deliberately a
        separate method from publish_command() above, publishing to a
        separate topic (SIMULATION_COMMAND_TOPIC, never COMMAND_TOPIC).
        Accepts only "run"/"reset" -- never "start"/"abort", which stay
        exclusively publish_command()'s vocabulary on the real
        /gcs/command topic. Nothing in this method can reach the real
        mission/flight-control path."""
        if command not in VALID_SIMULATION_COMMANDS:
            raise ValueError(
                f"invalid simulation command: {command!r}; must be one of {VALID_SIMULATION_COMMANDS}"
            )
        if self._simulation_command_topic is None:
            raise RuntimeError("not connected to rosbridge")
        self._simulation_command_topic.publish(roslibpy.Message({"data": command}))
