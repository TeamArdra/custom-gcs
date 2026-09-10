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
    # Port of the Jetson's own lightweight MJPEG-over-HTTP server -- NOT
    # part of rosbridge (see docs/DECISIONS.md D-6, docs/DATA_MODELS.md
    # §7); this backend never proxies video bytes, only builds the URL.
    camera_stream_port: int = int(os.environ.get("CAMERA_STREAM_PORT", "8090"))

    def camera_stream_url(self) -> str:
        """Assumes the video server is co-located with the rosbridge host
        (i.e. the Jetson) -- a real deployment might need this decoupled
        into its own host setting later, out of scope for now."""
        return f"http://{self.rosbridge_host}:{self.camera_stream_port}/stream.mjpg"


def get_settings() -> Settings:
    return Settings()
