"""Test double for RosBridgeClient -- same interface, no real networking.
Lets the route/schema layer be tested fast and in isolation; see
test_backend_against_sim.py for the real end-to-end counterpart."""

from __future__ import annotations

from typing import Any

from app.ros_client import VALID_COMMANDS


class FakeRosBridgeClient:
    def __init__(self, connected: bool = True) -> None:
        self.is_connected = connected
        self._latest: dict[str, Any] = {}
        self._survivors: list[dict] = []
        self.published_commands: list[str] = []

    def set_latest(self, topic: str, message: dict) -> None:
        self._latest[topic] = message

    def latest(self, topic: str) -> Any:
        return self._latest.get(topic)

    def set_survivors(self, survivors: list[dict]) -> None:
        self._survivors = survivors

    def survivors(self) -> list[dict]:
        return self._survivors

    def publish_command(self, command: str) -> None:
        if command not in VALID_COMMANDS:
            raise ValueError(f"invalid command: {command!r}")
        self.published_commands.append(command)
