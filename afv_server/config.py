"""Runtime configuration for the standalone AFV server."""

from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _default_public_host() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _resolve_aliased_file() -> str:
    aliased_file = os.getenv("AFV_ALIASED_FILE", "").strip()
    if aliased_file:
        return aliased_file

    legacy = os.getenv("AFV_STATIONS_FILE", "").strip()
    if legacy and Path(legacy).suffix.lower() != ".db":
        logger.warning(
            "AFV_STATIONS_FILE is deprecated for aliased JSON; use AFV_ALIASED_FILE instead"
        )
        return legacy
    return ""


@dataclass(slots=True)
class StationAlias:
    """HF/VHF alias station entry returned to pilot clients."""

    id: str
    name: str
    frequency: int
    frequencyAlias: int

    @classmethod
    def from_mapping(cls, item: dict[str, Any]) -> "StationAlias":
        return cls(
            id=str(item.get("id", "")),
            name=str(item.get("name", "")),
            frequency=int(item.get("frequency", 0)),
            frequencyAlias=int(item.get("frequencyAlias", item.get("frequency_alias", 0))),
        )


@dataclass(slots=True)
class Config:
    """AFV server settings."""

    http_host: str = "0.0.0.0"
    http_port: int = 5000
    udp_host: str = "0.0.0.0"
    udp_port: int = 50000
    public_voice_host: str = field(default_factory=_default_public_host)
    public_voice_port: int = 50000
    auth_mode: str = "allow"
    auth_webhook_url: str = ""
    auth_webhook_secret: str = ""
    token_ttl_seconds: int = 3600
    reaper_interval_seconds: int = 30
    client_stale_seconds: int = 60
    aliased_stations: list[StationAlias] = field(default_factory=list)

    @property
    def voice_address(self) -> str:
        return f"{self.public_voice_host}:{self.public_voice_port}"

    @classmethod
    def from_env(cls) -> "Config":
        udp_port = _int_env("AFV_UDP_PORT", 50000)
        aliased_stations: list[StationAlias] = []
        aliased_file = _resolve_aliased_file()
        if aliased_file:
            raw = json.loads(Path(aliased_file).read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("AFV_ALIASED_FILE must contain a JSON list")
            aliased_stations = [StationAlias.from_mapping(item) for item in raw]

        return cls(
            http_host=os.getenv("AFV_HTTP_HOST", "0.0.0.0"),
            http_port=_int_env("AFV_HTTP_PORT", 5000),
            udp_host=os.getenv("AFV_UDP_HOST", "0.0.0.0"),
            udp_port=udp_port,
            public_voice_host=os.getenv("AFV_PUBLIC_VOICE_HOST") or _default_public_host(),
            public_voice_port=_int_env("AFV_PUBLIC_VOICE_PORT", udp_port),
            auth_mode=os.getenv("AFV_AUTH_MODE", "allow").lower(),
            auth_webhook_url=os.getenv("AFV_AUTH_WEBHOOK_URL", ""),
            auth_webhook_secret=os.getenv("AFV_AUTH_WEBHOOK_SECRET", ""),
            token_ttl_seconds=_int_env("AFV_TOKEN_TTL_SECONDS", 3600),
            reaper_interval_seconds=_int_env("AFV_REAPER_INTERVAL_SECONDS", 30),
            client_stale_seconds=_int_env("AFV_CLIENT_STALE_SECONDS", 60),
            aliased_stations=aliased_stations,
        )
