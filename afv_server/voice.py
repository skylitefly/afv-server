"""UDP voice server for AFV encrypted DTOs."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from typing import Any

from .crypto import pack_packet, peek_channel_tag, unpack_packet
from .models import (
    AfvState,
    Transceiver,
    VoiceClient,
    distance_ratio,
    frequency_matches,
)

DTO_HEARTBEAT = b"H"
DTO_HEARTBEAT_ACK = b"HA"
DTO_AUDIO_TX = b"AT"
DTO_AUDIO_RX = b"AR"


class VoiceDatagramProtocol(asyncio.DatagramProtocol):
    """AFV UDP protocol implementation."""

    def __init__(self, state: AfvState) -> None:
        self.state = state
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            self.handle_datagram(data, addr)
        except (ValueError, KeyError, IndexError, TypeError):
            return

    def handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        channel_tag = peek_channel_tag(data)
        client = self.state.client_for_channel(channel_tag)
        if client is None:
            return
        packet = unpack_packet(data, key=client.client_to_server_key)
        client.address = addr
        client.last_seen_at = time.time()

        if packet.dto_name == DTO_HEARTBEAT:
            self._send(client, DTO_HEARTBEAT_ACK, [])
        elif packet.dto_name == DTO_AUDIO_TX:
            audio = _parse_audio_tx(packet.dto)
            if audio["callsign"] != client.callsign:
                return
            self._relay_audio(client, audio)

    def _relay_audio(self, sender: VoiceClient, audio: dict[str, Any]) -> None:
        sender_transceivers = _tx_source_transceivers(sender, audio["transceivers"])
        if not sender_transceivers:
            return

        for receiver in self.state.clients_by_callsign.values():
            if receiver.callsign == sender.callsign or receiver.address is None:
                continue
            rx_transceivers = list(_matching_rx_transceivers(sender_transceivers, receiver))
            if not rx_transceivers:
                continue
            dto = [
                sender.callsign,
                int(audio["sequenceCounter"]),
                audio["audio"],
                bool(audio["lastPacket"]),
                rx_transceivers,
            ]
            self._send(receiver, DTO_AUDIO_RX, dto)

    def _send(self, client: VoiceClient, dto_name: bytes, dto: Any) -> None:
        if self.transport is None or client.address is None:
            return
        packet = pack_packet(
            channel_tag=client.channel_tag,
            sequence=client.next_sequence(),
            key=client.server_to_client_key,
            dto_short_name=dto_name,
            dto=dto,
        )
        self.transport.sendto(packet, client.address)


def _parse_audio_tx(dto: Any) -> dict[str, Any]:
    callsign, sequence, audio, last_packet, transceivers = dto
    return {
        "callsign": str(callsign),
        "sequenceCounter": int(sequence),
        "audio": _audio_bytes(audio),
        "lastPacket": bool(last_packet),
        "transceivers": [int(item[0]) for item in transceivers],
    }


def _audio_bytes(audio: Any) -> bytes:
    if isinstance(audio, bytes):
        return audio
    if isinstance(audio, bytearray):
        return bytes(audio)
    return bytes(int(item) & 0xFF for item in audio)


def _tx_source_transceivers(sender: VoiceClient, tx_ids: Iterable[int]) -> list[Transceiver]:
    result: list[Transceiver] = []
    for tx_id in tx_ids:
        transceiver = sender.transceivers.get(int(tx_id))
        if transceiver is not None:
            result.append(transceiver)
    return result


def _matching_rx_transceivers(
    sender_transceivers: Iterable[Transceiver], receiver: VoiceClient
) -> Iterable[list[Any]]:
    seen: set[int] = set()
    for sender_tx in sender_transceivers:
        for receiver_rx in receiver.transceivers.values():
            if receiver_rx.id in seen:
                continue
            if not frequency_matches(sender_tx.frequency, receiver_rx.frequency):
                continue
            ratio = distance_ratio(sender_tx, receiver_rx)
            if ratio <= 0:
                continue
            seen.add(receiver_rx.id)
            yield [receiver_rx.id, receiver_rx.frequency, float(ratio)]
