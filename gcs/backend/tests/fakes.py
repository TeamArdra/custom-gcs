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
        self._ages: dict[str, float] = {}
        self._survivors: list[dict] = []
        self._statustext: list[dict] = []
        self.published_commands: list[str] = []

    def set_latest(self, topic: str, message: dict) -> None:
        self._latest[topic] = message

    def latest(self, topic: str) -> Any:
        return self._latest.get(topic)

    def set_age_s(self, topic: str, age_s: float | None) -> None:
        self._ages[topic] = age_s

    def age_s(self, topic: str) -> float | None:
        return self._ages.get(topic)

    def set_survivors(self, survivors: list[dict]) -> None:
        self._survivors = survivors

    def survivors(self) -> list[dict]:
        return self._survivors

    def set_statustext_history(self, history: list[dict]) -> None:
        self._statustext = history

    def statustext_history(self) -> list[dict]:
        return self._statustext

    def publish_command(self, command: str) -> None:
        if command not in VALID_COMMANDS:
            raise ValueError(f"invalid command: {command!r}")
        self.published_commands.append(command)
