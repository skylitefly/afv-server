"""AFV protocol models and in-memory server state."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt
from typing import Any


@dataclass(slots=True)
class Transceiver:
    """Radio transceiver registered by a pilot client."""

    id: int
    frequency: int
    lat_deg: float = 0.0
    lon_deg: float = 0.0
    height_msl_m: float = 0.0
    height_agl_m: float = 0.0

    @classmethod
    def from_json(cls, item: dict[str, Any]) -> "Transceiver":
        return cls(
            id=int(item.get("id", item.get("ID", 0))),
            frequency=int(item.get("frequency", item.get("Frequency", 0))),
            lat_deg=float(item.get("latDeg", item.get("LatDeg", 0.0))),
            lon_deg=float(item.get("lonDeg", item.get("LonDeg", 0.0))),
            height_msl_m=float(item.get("heightMslM", item.get("HeightMslM", 0.0))),
            height_agl_m=float(item.get("heightAglM", item.get("HeightAglM", 0.0))),
        )

    def to_client_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "frequency": self.frequency,
            "latDeg": self.lat_deg,
            "lonDeg": self.lon_deg,
            "heightMslM": self.height_msl_m,
            "heightAglM": self.height_agl_m,
        }


@dataclass(slots=True)
class ApiToken:
    """Issued AFV API token."""

    token: str
    username: str
    expires_at: int


@dataclass(slots=True)
class VoiceClient:
    """Authenticated callsign state."""

    username: str
    callsign: str
    channel_tag: str
    client_to_server_key: bytes
    server_to_client_key: bytes
    hmac_key: bytes
    created_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)
    address: tuple[str, int] | None = None
    outgoing_sequence: int = 0
    transceivers: dict[int, Transceiver] = field(default_factory=dict)

    @classmethod
    def create(cls, username: str, callsign: str) -> "VoiceClient":
        return cls(
            username=username,
            callsign=callsign,
            channel_tag=secrets.token_urlsafe(18),
            client_to_server_key=secrets.token_bytes(32),
            server_to_client_key=secrets.token_bytes(32),
            hmac_key=secrets.token_bytes(32),
        )

    def next_sequence(self) -> int:
        value = self.outgoing_sequence
        self.outgoing_sequence += 1
        return value


class AfvState:
    """In-memory state for AFV HTTP and UDP services."""

    def __init__(self) -> None:
        self.tokens: dict[str, ApiToken] = {}
        self.clients_by_callsign: dict[str, VoiceClient] = {}
        self.clients_by_channel: dict[str, VoiceClient] = {}

    def issue_token(self, token: str, username: str, expires_at: int) -> ApiToken:
        api_token = ApiToken(token=token, username=username, expires_at=expires_at)
        self.tokens[token] = api_token
        return api_token

    def validate_token(self, token: str) -> ApiToken | None:
        api_token = self.tokens.get(token)
        if api_token is None:
            return None
        if api_token.expires_at <= int(time.time()):
            self.tokens.pop(token, None)
            return None
        return api_token

    def add_client(self, client: VoiceClient) -> None:
        existing = self.clients_by_callsign.get(client.callsign)
        if existing is not None:
            self.remove_client(existing.callsign)
        self.clients_by_callsign[client.callsign] = client
        self.clients_by_channel[client.channel_tag] = client

    def remove_client(self, callsign: str) -> None:
        client = self.clients_by_callsign.pop(callsign, None)
        if client is not None:
            self.clients_by_channel.pop(client.channel_tag, None)

    def client_for_channel(self, channel_tag: str) -> VoiceClient | None:
        return self.clients_by_channel.get(channel_tag)


def frequency_matches(left: int, right: int) -> bool:
    """Return whether two AFV frequencies should share a voice room."""

    return int(left) == int(right)


def distance_ratio(sender: Transceiver, receiver: Transceiver) -> float:
    """Compute AFV-style reception quality ratio.

    HF frequencies are treated as long range. VHF uses a radio-horizon estimate
    and returns 1.0 nearby, approaching 0.0 at the edge of range.
    """

    if sender.frequency < 30_000_000:
        return 1.0

    distance_km = _great_circle_km(
        sender.lat_deg,
        sender.lon_deg,
        receiver.lat_deg,
        receiver.lon_deg,
    )
    sender_h = max(sender.height_msl_m, sender.height_agl_m, 1.0)
    receiver_h = max(receiver.height_msl_m, receiver.height_agl_m, 1.0)
    horizon_km = 4.12 * (sqrt(sender_h) + sqrt(receiver_h))
    horizon_km = max(horizon_km, 10.0)
    if distance_km > horizon_km:
        return 0.0
    return max(0.05, min(1.0, 1.0 - distance_km / horizon_km))


def _great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    rlat1 = radians(lat1)
    rlat2 = radians(lat2)
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))
