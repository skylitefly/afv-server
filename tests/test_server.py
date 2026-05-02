import asyncio

import pytest

from afv_server.config import Config
from afv_server.server import run


async def test_server_starts_http_and_udp_then_cancels() -> None:
    task = asyncio.create_task(
        run(
            Config(
                http_host="127.0.0.1",
                http_port=0,
                udp_host="127.0.0.1",
                udp_port=0,
                public_voice_host="127.0.0.1",
                public_voice_port=0,
            )
        )
    )
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
