"""pilotclient-compatible AFV CryptoDto serialization."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

import msgpack
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


class CryptoDtoMode(IntEnum):
    """AFV crypto DTO modes."""

    UNDEFINED = 0
    NONE = 1
    AEAD_CHACHA20_POLY1305 = 2


@dataclass(slots=True)
class DecodedPacket:
    """Decoded AFV UDP packet."""

    channel_tag: str
    sequence: int
    dto_name: bytes
    dto: Any


def pack_packet(
    *,
    channel_tag: str,
    sequence: int,
    key: bytes,
    dto_short_name: bytes,
    dto: Any,
) -> bytes:
    """Serialize and encrypt a DTO using the same packet layout as pilotclient."""

    if len(key) != 32:
        raise ValueError("AEAD key must be 32 bytes")

    header = [channel_tag, sequence, int(CryptoDtoMode.AEAD_CHACHA20_POLY1305)]
    header_bytes = msgpack.packb(header, use_bin_type=True)
    dto_bytes = msgpack.packb(dto, use_bin_type=True)
    plaintext = (
        struct.pack("<H", len(dto_short_name))
        + dto_short_name
        + struct.pack("<H", len(dto_bytes))
        + dto_bytes
    )
    associated_data = struct.pack("<H", len(header_bytes)) + header_bytes
    nonce = struct.pack("<IQ", 0, sequence)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, associated_data)
    return associated_data + ciphertext


def peek_channel_tag(packet: bytes) -> str:
    """Read the unencrypted channel tag from an AFV UDP packet."""

    header_len = _read_u16(packet, 0)
    header = msgpack.unpackb(packet[2 : 2 + header_len], raw=False)
    return str(header[0])


def unpack_packet(packet: bytes, *, key: bytes) -> DecodedPacket:
    """Decrypt and deserialize an AFV UDP packet."""

    if len(key) != 32:
        raise ValueError("AEAD key must be 32 bytes")

    header_len = _read_u16(packet, 0)
    header_bytes = packet[2 : 2 + header_len]
    header = msgpack.unpackb(header_bytes, raw=False)
    channel_tag = str(header[0])
    sequence = int(header[1])
    mode = int(header[2])
    if mode != int(CryptoDtoMode.AEAD_CHACHA20_POLY1305):
        raise ValueError(f"Unsupported CryptoDtoMode {mode}")

    associated_data = packet[: 2 + header_len]
    ciphertext = packet[2 + header_len :]
    nonce = struct.pack("<IQ", 0, sequence)
    plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, associated_data)

    name_len = _read_u16(plaintext, 0)
    name_start = 2
    name_end = name_start + name_len
    dto_name = plaintext[name_start:name_end]
    dto_len = _read_u16(plaintext, name_end)
    dto_start = name_end + 2
    dto_end = dto_start + dto_len
    dto = msgpack.unpackb(plaintext[dto_start:dto_end], raw=False)
    return DecodedPacket(
        channel_tag=channel_tag,
        sequence=sequence,
        dto_name=dto_name,
        dto=dto,
    )


def _read_u16(data: bytes, offset: int) -> int:
    if offset + 2 > len(data):
        raise ValueError("Truncated AFV packet")
    return struct.unpack_from("<H", data, offset)[0]
