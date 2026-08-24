"""Backend configuration. Pointing at the real Jetson instead of
sim/rosbridge_sim during development is a host/port change here, not a
code change anywhere else."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    rosbridge_host: str = os.environ.get("ROSBRIDGE_HOST", "127.0.0.1")
    rosbridge_port: int = int(os.environ.get("ROSBRIDGE_PORT", "9090"))
    connect_timeout_s: float = float(os.environ.get("ROSBRIDGE_CONNECT_TIMEOUT_S", "5"))


def get_settings() -> Settings:
    return Settings()
