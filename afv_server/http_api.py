"""HTTP API compatible with pilotclient's AFV API connection."""

from __future__ import annotations

import base64
import time
from typing import Any

from aiohttp import web

from .auth import Authenticator, build_unsigned_jwt
from .config import Config
from .models import AfvState, Transceiver, VoiceClient

CONFIG_KEY = web.AppKey("config", Config)
STATE_KEY = web.AppKey("state", AfvState)
AUTHENTICATOR_KEY = web.AppKey("authenticator", Authenticator)


def create_app(config: Config, state: AfvState, authenticator: Authenticator) -> web.Application:
    """Create the AFV HTTP application."""

    app = web.Application()
    app[CONFIG_KEY] = config
    app[STATE_KEY] = state
    app[AUTHENTICATOR_KEY] = authenticator
    app.add_routes(
        [
            web.post("/api/v1/auth", handle_auth),
            web.post("/api/v1/users/{username}/callsigns/{callsign}", handle_add_callsign),
            web.delete("/api/v1/users/{username}/callsigns/{callsign}", handle_remove_callsign),
            web.post(
                "/api/v1/users/{username}/callsigns/{callsign}/transceivers",
                handle_update_transceivers,
            ),
            web.get("/api/v1/stations/aliased", handle_aliased_stations),
            web.get("/api/v1/network/online/callsigns", handle_online_callsigns),
        ]
    )
    return app


async def handle_auth(request: web.Request) -> web.Response:
    data = await request.json()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    client = str(data.get("client", ""))
    network_version = str(data.get("networkversion", ""))
    if not username or not password:
        return web.json_response({"error": "Missing username or password"}, status=400)

    authenticator = request.app[AUTHENTICATOR_KEY]
    result = await authenticator.authenticate(username, password, client, network_version)
    if not result.success:
        return web.json_response({"error": result.error or "Authentication failed"}, status=401)

    config = request.app[CONFIG_KEY]
    state = request.app[STATE_KEY]
    now = int(time.time())
    expires_at = now + config.token_ttl_seconds
    token = build_unsigned_jwt(
        {
            "sub": result.cid,
            "cid": result.cid,
            "rating": result.rating,
            "client": client,
            "networkversion": network_version,
            "nbf": now,
            "iat": now,
            "exp": expires_at,
        }
    )
    state.issue_token(token, result.cid, expires_at)
    return web.Response(text=token, content_type="text/plain")


async def handle_add_callsign(request: web.Request) -> web.Response:
    api_token = _require_token(request)
    username = request.match_info["username"]
    callsign = request.match_info["callsign"]
    if api_token.username != username:
        username = api_token.username

    state = request.app[STATE_KEY]
    client = VoiceClient.create(username=username, callsign=callsign)
    state.add_client(client)
    config = request.app[CONFIG_KEY]
    return web.json_response(
        {
            "voiceServer": {
                "addressIpV4": config.voice_address,
                "addressIpV6": config.voice_address,
                "channelConfig": {
                    "channelTag": client.channel_tag,
                    "aeadReceiveKey": _b64(client.server_to_client_key),
                    "aeadTransmitKey": _b64(client.client_to_server_key),
                    "hmacKey": _b64(client.hmac_key),
                },
            }
        }
    )


async def handle_remove_callsign(request: web.Request) -> web.Response:
    _require_token(request)
    state = request.app[STATE_KEY]
    state.remove_client(request.match_info["callsign"])
    return web.Response(status=204)


async def handle_update_transceivers(request: web.Request) -> web.Response:
    _require_token(request)
    body = await request.json()
    if not isinstance(body, list):
        return web.json_response({"error": "Transceivers payload must be a list"}, status=400)
    callsign = request.match_info["callsign"]
    state = request.app[STATE_KEY]
    client = state.clients_by_callsign.get(callsign)
    if client is None:
        return web.json_response({"error": "Unknown callsign"}, status=404)
    transceivers = [Transceiver.from_json(item) for item in body if isinstance(item, dict)]
    client.transceivers = {transceiver.id: transceiver for transceiver in transceivers}
    return web.Response(status=204)


async def handle_aliased_stations(request: web.Request) -> web.Response:
    config = request.app[CONFIG_KEY]
    return web.json_response(
        [
            {
                "id": station.id,
                "name": station.name,
                "frequency": station.frequency,
                "frequencyAlias": station.frequencyAlias,
            }
            for station in config.stations
        ]
    )


async def handle_online_callsigns(request: web.Request) -> web.Response:
    state = request.app[STATE_KEY]
    payload: list[dict[str, Any]] = []
    for client in state.clients_by_callsign.values():
        payload.append(
            {
                "callsign": client.callsign,
                "transceivers": [
                    transceiver.to_client_json()
                    for transceiver in client.transceivers.values()
                ],
            }
        )
    return web.json_response(payload)


def _require_token(request: web.Request):
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise web.HTTPUnauthorized(text="Missing bearer token")
    token = header.split(" ", 1)[1].strip()
    state = request.app[STATE_KEY]
    api_token = state.validate_token(token)
    if api_token is None:
        raise web.HTTPUnauthorized(text="Invalid or expired bearer token")
    return api_token


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")
