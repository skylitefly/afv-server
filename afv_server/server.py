"""Server lifecycle orchestration."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiohttp import web

from .auth import Authenticator
from .config import Config
from .http_api import create_app
from .models import AfvState
from .voice import VoiceDatagramProtocol

LOGGER = logging.getLogger(__name__)


async def run(config: Config) -> None:
    """Run HTTP and UDP AFV services until cancelled."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    state = AfvState()
    authenticator = Authenticator(config)
    app = create_app(config, state, authenticator)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.http_host, config.http_port)
    await site.start()

    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: VoiceDatagramProtocol(state),
        local_addr=(config.udp_host, config.udp_port),
    )

    LOGGER.info("AFV HTTP listening on %s:%s", config.http_host, config.http_port)
    LOGGER.info("AFV UDP listening on %s:%s", config.udp_host, config.udp_port)
    LOGGER.info("AFV voice address advertised as %s", config.voice_address)
    try:
        await asyncio.Event().wait()
    finally:
        transport.close()
        await runner.cleanup()
        await authenticator.close()


def run_blocking(config: Config) -> None:
    """Run the AFV server with Ctrl-C shutdown."""

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(config))
