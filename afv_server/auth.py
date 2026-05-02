"""Authentication backends for the standalone AFV server."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import aiohttp

from .config import Config


@dataclass(slots=True)
class AuthResult:
    """AFV authentication result."""

    success: bool
    cid: str
    rating: int = 1
    error: str = ""


class Authenticator:
    """Authenticate AFV users locally or through web-backend."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def authenticate(
        self, username: str, password: str, client: str, network_version: str
    ) -> AuthResult:
        if self._config.auth_mode == "allow":
            return AuthResult(success=True, cid=username, rating=1)
        if self._config.auth_mode == "webhook":
            return await self._authenticate_webhook(
                username=username,
                password=password,
                client=client,
                network_version=network_version,
            )
        return AuthResult(
            success=False,
            cid=username,
            error=f"Unsupported AFV_AUTH_MODE {self._config.auth_mode!r}",
        )

    async def _authenticate_webhook(
        self, *, username: str, password: str, client: str, network_version: str
    ) -> AuthResult:
        if not self._config.auth_webhook_url:
            return AuthResult(success=False, cid=username, error="Auth webhook URL is not configured")
        if self._session is None:
            self._session = aiohttp.ClientSession()

        payload = {
            "cid": username,
            "password": password,
            "client": client,
            "networkversion": network_version,
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._config.auth_webhook_secret:
            parsed = urlparse(self._config.auth_webhook_url)
            path = parsed.path or "/"
            timestamp = str(int(time.time()))
            body_hash = hashlib.sha256(body).hexdigest()
            message = f"POST\n{path}\n{timestamp}\n{body_hash}"
            signature = hmac.new(
                self._config.auth_webhook_secret.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Request-Timestamp"] = timestamp
            headers["X-Request-Signature"] = signature

        try:
            async with self._session.post(
                self._config.auth_webhook_url,
                data=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            return AuthResult(success=False, cid=username, error=f"Auth webhook failed: {exc}")

        if data.get("success"):
            return AuthResult(
                success=True,
                cid=str(data.get("cid") or username),
                rating=int(data.get("rating") or 1),
            )
        return AuthResult(
            success=False,
            cid=username,
            error=str(data.get("error") or "Authentication failed"),
        )


def build_unsigned_jwt(payload: dict[str, Any]) -> str:
    """Create a JWT that pilotclient's bundled QJsonWebToken can decode.

    pilotclient only reads nbf/exp from the payload and does not call isValid(),
    but QJsonWebToken::setToken still rejects unsupported algorithms and expects
    Qt's standard Base64 format. Use HS256 plus an empty-key HMAC signature for
    parser compatibility.
    """

    header = {"alg": "HS256", "typ": "JWT"}
    header_part = _b64_json(header)
    payload_part = _b64_json(payload)
    signature = hmac.new(
        b"",
        f"{header_part}.{payload_part}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{header_part}.{payload_part}.{base64.b64encode(signature).decode('ascii')}"


def _b64_json(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")
