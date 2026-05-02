from afv_server.crypto import pack_packet, unpack_packet
from afv_server.models import AfvState, Transceiver, VoiceClient
from afv_server.voice import DTO_AUDIO_TX, DTO_HEARTBEAT, VoiceDatagramProtocol


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))


def test_heartbeat_ack_is_encrypted_for_client_receive_key() -> None:
    state = AfvState()
    client = VoiceClient.create("100001", "SKY123")
    state.add_client(client)
    protocol = VoiceDatagramProtocol(state)
    transport = FakeTransport()
    protocol.connection_made(transport)  # type: ignore[arg-type]

    packet = pack_packet(
        channel_tag=client.channel_tag,
        sequence=0,
        key=client.client_to_server_key,
        dto_short_name=DTO_HEARTBEAT,
        dto=["SKY123"],
    )
    protocol.handle_datagram(packet, ("127.0.0.1", 40000))

    assert client.address == ("127.0.0.1", 40000)
    assert len(transport.sent) == 1
    response, addr = transport.sent[0]
    assert addr == ("127.0.0.1", 40000)
    decoded = unpack_packet(response, key=client.server_to_client_key)
    assert decoded.dto_name == b"HA"
    assert decoded.dto == []


def test_audio_is_relayed_to_matching_receiver_frequency() -> None:
    state = AfvState()
    sender = VoiceClient.create("100001", "SKY123")
    receiver = VoiceClient.create("100002", "CTR_A")
    sender.transceivers = {
        0: Transceiver(
            id=0,
            frequency=122800000,
            lat_deg=31.2,
            lon_deg=121.5,
            height_msl_m=1000,
            height_agl_m=1000,
        )
    }
    receiver.transceivers = {
        1: Transceiver(
            id=1,
            frequency=122800000,
            lat_deg=31.25,
            lon_deg=121.55,
            height_msl_m=300,
            height_agl_m=300,
        )
    }
    receiver.address = ("127.0.0.1", 40001)
    state.add_client(sender)
    state.add_client(receiver)
    protocol = VoiceDatagramProtocol(state)
    transport = FakeTransport()
    protocol.connection_made(transport)  # type: ignore[arg-type]

    packet = pack_packet(
        channel_tag=sender.channel_tag,
        sequence=5,
        key=sender.client_to_server_key,
        dto_short_name=DTO_AUDIO_TX,
        dto=["SKY123", 12, b"opus", False, [[0]]],
    )
    protocol.handle_datagram(packet, ("127.0.0.1", 40000))

    assert len(transport.sent) == 1
    response, addr = transport.sent[0]
    assert addr == receiver.address
    decoded = unpack_packet(response, key=receiver.server_to_client_key)
    assert decoded.dto_name == b"AR"
    assert decoded.dto[0] == "SKY123"
    assert decoded.dto[1] == 12
    assert decoded.dto[2] == b"opus"
    assert decoded.dto[3] is False
    assert decoded.dto[4][0][0] == 1
    assert decoded.dto[4][0][1] == 122800000
    assert 0 < decoded.dto[4][0][2] <= 1
