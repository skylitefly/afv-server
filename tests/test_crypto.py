import base64

from afv_server.crypto import pack_packet, peek_channel_tag, unpack_packet


def test_crypto_packet_round_trip_with_afv_layout() -> None:
    key = b"1" * 32
    packet = pack_packet(
        channel_tag="test-channel",
        sequence=42,
        key=key,
        dto_short_name=b"H",
        dto=["ABC123"],
    )

    assert peek_channel_tag(packet) == "test-channel"
    decoded = unpack_packet(packet, key=key)

    assert decoded.channel_tag == "test-channel"
    assert decoded.sequence == 42
    assert decoded.dto_name == b"H"
    assert decoded.dto == ["ABC123"]
    assert base64.b64encode(key).decode("ascii")
