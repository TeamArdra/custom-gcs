"""Test double for RosBridgeClient -- same interface, no real networking.
Lets the route/schema layer be tested fast and in isolation; see
test_backend_against_sim.py for the real end-to-end counterpart."""

from __future__ import annotations

from typing import Any

from app.ros_client import VALID_COMMANDS, VALID_SIMULATION_COMMANDS


class FakeRosBridgeClient:
    def __init__(self, connected: bool = True) -> None:
        self.is_connected = connected
        self._latest: dict[str, Any] = {}
        self._ages: dict[str, float] = {}
        self._survivors: list[dict] = []
        self._statustext: list[dict] = []
        self.published_commands: list[str] = []
        self.published_simulation_commands: list[str] = []
        self._publish_exception: Exception | None = None
        self._publish_simulation_exception: Exception | None = None

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

    def fail_publish_with(self, exc: Exception) -> None:
        """Make subsequent publish_command calls raise `exc` instead of
        recording the command -- mirrors how the real RosBridgeClient
        raises RuntimeError("not connected to rosbridge") when its
        connection to rosbridge is unavailable (see
        app/ros_client.py:publish_command), so API-level tests can
        exercise that downstream-failure path without a real dead
        connection."""
        self._publish_exception = exc

    def publish_command(self, command: str) -> None:
        if command not in VALID_COMMANDS:
            raise ValueError(f"invalid command: {command!r}")
        if self._publish_exception is not None:
            raise self._publish_exception
        self.published_commands.append(command)

    def fail_publish_simulation_with(self, exc: Exception) -> None:
        self._publish_simulation_exception = exc

    def publish_simulation_command(self, command: str) -> None:
        """The fake's mirror of the real client's simulation-only publish
        method -- deliberately separate from publish_command()/
        published_commands above, so a test can assert a simulation route
        never touched the real command path."""
        if command not in VALID_SIMULATION_COMMANDS:
            raise ValueError(f"invalid simulation command: {command!r}")
        if self._publish_simulation_exception is not None:
            raise self._publish_simulation_exception
        self.published_simulation_commands.append(command)
