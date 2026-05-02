import hashlib
import hmac

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from afv_server.auth import Authenticator
from afv_server.config import Config


async def test_webhook_auth_signs_request_like_web_backend() -> None:
    secret = "shared-secret"

    async def webhook(request: web.Request) -> web.Response:
        body = await request.read()
        timestamp = request.headers["X-Request-Timestamp"]
        message = (
            f"POST\n{request.path}\n{timestamp}\n"
            f"{hashlib.sha256(body).hexdigest()}"
        )
        expected = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert request.headers["X-Request-Signature"] == expected
        data = await request.json()
        assert data["cid"] == "email@example.com"
        return web.json_response({"success": True, "rating": 5, "cid": "100001"})

    app = web.Application()
    app.router.add_post("/api/auth/pyfsd-auth/", webhook)

    async with TestClient(TestServer(app)) as client:
        config = Config(
            auth_mode="webhook",
            auth_webhook_url=str(client.make_url("/api/auth/pyfsd-auth/")),
            auth_webhook_secret=secret,
        )
        authenticator = Authenticator(config)
        result = await authenticator.authenticate(
            "email@example.com",
            "secret",
            "neoswift",
            "3a5ddc6d-cf5d-4319-bd0e-d184f772db80",
        )
        await authenticator.close()

    assert result.success is True
    assert result.cid == "100001"
    assert result.rating == 5
