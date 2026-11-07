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


def receiver(receiver_ip, receiver_port, window_size):
    """TODO: Listen on socket and print received message to sys.stdout."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((receiver_ip, receiver_port))

    in_connection = False
    peer = None
    expected = 1  # next in-order sequence number the receiver expects
    buffered = {}  # out-of-order packets waiting for the gap to be filled

    while True:
        # Receive packet; address includes both IP and port
        pkt, address = s.recvfrom(2048)

        # Extract header and payload
        pkt_header = PacketHeader(pkt[:16])
        msg = pkt[16 : 16 + pkt_header.length]

        # Verity checksum
        pkt_checksum = pkt_header.checksum
        pkt_header.checksum = 0
        computed_checksum = compute_checksum(pkt_header / msg)
        if pkt_checksum != computed_checksum:
            # print("checksums not match")
            continue
        # print(msg)

        if pkt_header.type == START:
            if not in_connection:
                # A new connection begins.  Ignore any leftover data.
                in_connection = True
                peer = address
                expected = 1
                buffered.clear()
                s.sendto(make_packet(ACK, 1), address)
            elif address == peer:
                # Retransmitted START for the connection we are already in:
                # re-ACK it without resetting any state.
                s.sendto(make_packet(ACK, 1), address)
            # START from a different sender while busy is ignored.
            continue

        # Everything else must belong to the active connection.
        if not in_connection or address != peer:
            continue

        if pkt_header.type == END:
            s.sendto(make_packet(ACK, pkt_header.seq_num + 1), address)
            sys.stdout.buffer.flush()
            return

        if pkt_header.type != DATA:
            continue

        seq = pkt_header.seq_num

        # Drop packets outside the receiver window [expected, expected + W).
        if seq >= expected + window_size:
            continue

        if seq < expected:
            # Already delivered: ACK the next expected sequence number.
            s.sendto(make_packet(ACK, expected), address)
            continue

        # In-order or buffered out-of-order packet: store it.
        if seq not in buffered:
            buffered[seq] = msg

        # Deliver everything that is now contiguous, in order.
        while expected in buffered:
            sys.stdout.buffer.write(buffered.pop(expected))
            expected += 1

        sys.stdout.buffer.flush()
        # Cumulative ACK: the next sequence number we expect.
        s.sendto(make_packet(ACK, expected), address)


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
