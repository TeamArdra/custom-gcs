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

import threading
from typing import Any

import roslibpy

MISSION_STATE_TOPIC = "/mission/state"
BATTERY_TOPIC = "/mavros/battery"
POSE_TOPIC = "/mavros/local_position/pose"
MAP_TOPIC = "/slam/map"
SURVIVORS_TOPIC = "/vision/survivors"
HEARTBEAT_TOPIC = "/gcs/heartbeat"
COMMAND_TOPIC = "/gcs/command"

# Declared ROS types per docs/DATA_MODELS.md. These are metadata only as
# far as sim/rosbridge_sim is concerned (it doesn't validate them), but
# matter once this connects to a real rosbridge_server backed by an
# actual ROS graph.
_SUBSCRIBED_TOPIC_TYPES = {
    MISSION_STATE_TOPIC: "std_msgs/String",
    BATTERY_TOPIC: "sensor_msgs/BatteryState",
    POSE_TOPIC: "geometry_msgs/PoseStamped",
    MAP_TOPIC: "nav_msgs/OccupancyGrid",
    SURVIVORS_TOPIC: "nidar_airmouse/SurvivorDetection",
    HEARTBEAT_TOPIC: "std_msgs/Header",
}
_COMMAND_TOPIC_TYPE = "std_msgs/String"
VALID_COMMANDS = ("start", "abort")


class RosBridgeClient:
    def __init__(self, host: str, port: int, connect_timeout_s: float = 5.0) -> None:
        self._host = host
        self._port = port
        self._connect_timeout_s = connect_timeout_s
        self._ros = roslibpy.Ros(host=host, port=port)
        self._lock = threading.Lock()
        self._latest: dict[str, Any] = {}
        self._survivors: dict[int, dict] = {}
        self._subscriptions: list[roslibpy.Topic] = []
        self._command_topic: roslibpy.Topic | None = None

    def connect(self) -> None:
        self._ros.run(timeout=self._connect_timeout_s)
        for topic, msg_type in _SUBSCRIBED_TOPIC_TYPES.items():
            sub = roslibpy.Topic(self._ros, topic, msg_type)
            sub.subscribe(self._make_handler(topic))
            self._subscriptions.append(sub)
        self._command_topic = roslibpy.Topic(self._ros, COMMAND_TOPIC, _COMMAND_TOPIC_TYPE)
        self._command_topic.advertise()

    def disconnect(self) -> None:
        for sub in self._subscriptions:
            sub.unsubscribe()
        self._subscriptions.clear()
        if self._command_topic is not None:
            self._command_topic.unadvertise()
            self._command_topic = None
        self._ros.terminate()

    def _make_handler(self, topic: str):
        def handler(message: dict) -> None:
            with self._lock:
                if topic == SURVIVORS_TOPIC:
                    self._survivors[message["survivor_id"]] = message
                else:
                    self._latest[topic] = message

        return handler

    @property
    def is_connected(self) -> bool:
        return self._ros.is_connected

    def latest(self, topic: str) -> Any:
        with self._lock:
            return self._latest.get(topic)

    def survivors(self) -> list[dict]:
        with self._lock:
            return sorted(self._survivors.values(), key=lambda s: s["survivor_id"])

    def publish_command(self, command: str) -> None:
        """The entire GCS -> drone command surface. Deliberately accepts
        only "start"/"abort" -- see docs/REQUIREMENTS.md §4/§6."""
        if command not in VALID_COMMANDS:
            raise ValueError(f"invalid command: {command!r}; must be one of {VALID_COMMANDS}")
        if self._command_topic is None:
            raise RuntimeError("not connected to rosbridge")
        self._command_topic.publish(roslibpy.Message({"data": command}))
