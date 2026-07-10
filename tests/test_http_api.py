import base64
import json
import time

from aiohttp.test_utils import TestClient, TestServer

from afv_server.auth import Authenticator
from afv_server.config import Config, StationAlias
from afv_server.http_api import create_app
from afv_server.models import AfvState


async def test_auth_and_callsign_lifecycle() -> None:
    config = Config(
        public_voice_host="203.0.113.10",
        public_voice_port=50123,
        token_ttl_seconds=600,
        aliased_stations=[
            StationAlias(
                id="11111111-1111-1111-1111-111111111111",
                name="SKY_CTR",
                frequency=17998000,
                frequencyAlias=125000000,
            )
        ],
    )
    state = AfvState()
    authenticator = Authenticator(config)
    app = create_app(config, state, authenticator)

    async with TestClient(TestServer(app)) as client:
        auth_response = await client.post(
            "/api/v1/auth",
            json={
                "username": "100001",
                "password": "secret",
                "networkversion": "3a5ddc6d-cf5d-4319-bd0e-d184f772db80",
                "client": "neoswift",
            },
        )
        assert auth_response.status == 200
        token = await auth_response.text()
        payload = _decode_unsigned_payload(token)
        assert payload["sub"] == "100001"
        assert payload["nbf"] <= int(time.time()) <= payload["exp"]

        response = await client.post(
            "/api/v1/users/100001/callsigns/SKY123",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status == 200
        callsign_data = await response.json()
        voice_server = callsign_data["voiceServer"]
        assert voice_server["addressIpV4"] == "203.0.113.10:50123"
        assert len(base64.b64decode(voice_server["channelConfig"]["aeadTransmitKey"])) == 32
        assert len(base64.b64decode(voice_server["channelConfig"]["aeadReceiveKey"])) == 32

        transceiver_response = await client.post(
            "/api/v1/users/100001/callsigns/SKY123/transceivers",
            headers={"Authorization": f"Bearer {token}"},
            json=[
                {
                    "ID": 0,
                    "Frequency": 122800000,
                    "LatDeg": 31.2,
                    "LonDeg": 121.5,
                    "HeightMslM": 1000,
                    "HeightAglM": 1000,
                }
            ],
        )
        assert transceiver_response.status == 204

        online_response = await client.get("/api/v1/network/online/callsigns")
        assert online_response.status == 200
        assert await online_response.json() == [
            {
                "callsign": "SKY123",
                "transceivers": [
                    {
                        "id": 0,
                        "frequency": 122800000,
                        "latDeg": 31.2,
                        "lonDeg": 121.5,
                        "heightMslM": 1000.0,
                        "heightAglM": 1000.0,
                    }
                ],
            }
        ]

        aliases_response = await client.get("/api/v1/stations/aliased")
        assert aliases_response.status == 200
        assert await aliases_response.json() == [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "SKY_CTR",
                "frequency": 17998000,
                "frequencyAlias": 125000000,
            }
        ]

        delete_response = await client.delete(
            "/api/v1/users/100001/callsigns/SKY123",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert delete_response.status == 204
        assert state.clients_by_callsign == {}

    await authenticator.close()


def _decode_unsigned_payload(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.b64decode(payload))
