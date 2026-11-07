import argparse
import socket
import sys

from utils import PacketHeader, compute_checksum

HEADER_SIZE = 16

# Packet types
START = 0
END = 1
DATA = 2
ACK = 3


def make_packet(pkt_type, seq_num, payload=b""):
    """Serialize one RTP packet: 16 byte header followed by the payload."""
    header = PacketHeader(
        type=pkt_type, seq_num=seq_num, length=len(payload), checksum=0
    )
    raw = bytes(header) + payload
    header.checksum = compute_checksum(raw)
    return bytes(header) + payload


def parse_packet(packet):
    """Return (header, payload) for an intact packet, or (None, None)."""
    if len(packet) < HEADER_SIZE:
        return None, None

    header = PacketHeader(packet[:HEADER_SIZE])
    if header.length < 0 or header.length > len(packet) - HEADER_SIZE:
        return None, None

    payload = packet[HEADER_SIZE : HEADER_SIZE + header.length]

    clean_header = PacketHeader(
        type=header.type,
        seq_num=header.seq_num,
        length=header.length,
        checksum=0,
    )
    if compute_checksum(bytes(clean_header) + payload) != header.checksum:
        return None, None

    return header, payload


def receiver(receiver_ip, receiver_port, window_size):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((receiver_ip, receiver_port))

    out = sys.stdout.buffer

    in_connection = False
    peer = None
    expected = 1  # next in-order sequence number the receiver expects
    buffered = {}  # out-of-order packets waiting for the gap to be filled

    while True:
        packet, address = sock.recvfrom(2048)
        header, payload = parse_packet(packet)

        # Corrupted packets are silently dropped (no ACK).
        if header is None:
            continue

        if header.type == START:
            if not in_connection:
                in_connection = True
                peer = address
                expected = 1
                buffered.clear()
                sock.sendto(make_packet(ACK, 1), address)
            elif address == peer:
                # Retransmitted START for the current connection.
                sock.sendto(make_packet(ACK, 1), address)
            continue

        # Everything else must belong to the active connection.
        if not in_connection or address != peer:
            continue

        if header.type == END:
            sock.sendto(make_packet(ACK, header.seq_num + 1), address)
            out.flush()
            return

        if header.type != DATA:
            continue

        seq = header.seq_num

        # Drop packets outside the receiver window [expected, expected + W).
        if seq >= expected + window_size:
            continue

        if seq < expected:
            # Duplicate of an already delivered packet.  The optimization is
            # to ACK the exact sequence number of the packet we received.
            sock.sendto(make_packet(ACK, seq), address)
            continue

        # In-order or buffered out-of-order packet: store it.
        if seq not in buffered:
            buffered[seq] = payload

        # Deliver contiguous data in order.
        while expected in buffered:
            out.write(buffered.pop(expected))
            expected += 1

        out.flush()
        # Individual (non-cumulative) ACK: echo the received sequence number.
        sock.sendto(make_packet(ACK, seq), address)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "receiver_ip", help="The IP address of the host that receiver is running on"
    )
    parser.add_argument(
        "receiver_port", type=int, help="The port number on which receiver is listening"
    )
    parser.add_argument(
        "window_size", type=int, help="Maximum number of outstanding packets"
    )
    args = parser.parse_args()

    receiver(args.receiver_ip, args.receiver_port, args.window_size)


if __name__ == "__main__":
    main()
