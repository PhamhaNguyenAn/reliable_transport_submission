import argparse
import socket
import sys
import time

from utils import PacketHeader, compute_checksum

HEADER_SIZE = 16
MAX_PAYLOAD = 1472 - HEADER_SIZE  # 1456 bytes of data per packet
TIMEOUT = 0.5  # 500 ms retransmission timer

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
    """Return (header, payload) if the packet is well formed and intact."""
    if len(packet) < HEADER_SIZE:
        return None, None

    header = PacketHeader(packet[:HEADER_SIZE])
    if header.length > len(packet) - HEADER_SIZE:
        return None, None

    payload = packet[HEADER_SIZE : HEADER_SIZE + header.length]

    # Recompute the checksum over a freshly built header (checksum field = 0).
    clean_header = PacketHeader(
        type=header.type,
        seq_num=header.seq_num,
        length=header.length,
        checksum=0,
    )
    if compute_checksum(bytes(clean_header) + payload) != header.checksum:
        return None, None

    return header, payload


def receive_ack(sock, timeout):
    """Wait at most `timeout` seconds for one valid ACK; return its seq or None."""
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return None
        sock.settimeout(remaining)
        try:
            packet, _ = sock.recvfrom(2048)
        except socket.timeout:
            return None
        header, _ = parse_packet(packet)
        if header is not None and header.type == ACK:
            return header.seq_num


def sender(receiver_ip, receiver_port, window_size):
    """TODO: Open socket and send message from sys.stdin."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # pkt_header = PacketHeader(type=2, seq_num=10, length=14)
    # pkt_header.checksum = compute_checksum(pkt_header / "Hello, world!\n")
    # pkt = pkt_header / "Hello, world!\n"
    # s.sendto(bytes(pkt), (receiver_ip, receiver_port))

    data = sys.stdin.buffer.read()
    chunks = [data[i : i + MAX_PAYLOAD] for i in range(0, len(data), MAX_PAYLOAD)]
    total = len(chunks)  # DATA packets are numbered 1..total

    dest = (receiver_ip, receiver_port)

    # ------------------------------------------------------------- START phase
    # The first START packet has seq_num 0 and its ACK has seq_num 1.
    start_packet = make_packet(START, 0)
    while True:
        s.sendto(start_packet, dest)
        ack = receive_ack(s, TIMEOUT)
        if ack is not None and ack >= 1:
            break
        # START (or its ACK) was lost: retransmit the START packet.

    # -------------------------------------------------------------- DATA phase
    packets = [None] * (total + 2)
    for seq in range(1, total + 1):
        packets[seq] = make_packet(DATA, seq, chunks[seq - 1])

    base = 1  # lowest sequence number that has not been acknowledged
    next_seq = 1  # next sequence number that has never been sent
    sent = set()  # sequence numbers sent but not acknowledged

    def fill_window():
        """Send new packets until the sender window is full."""
        nonlocal next_seq
        while next_seq <= total and next_seq < base + window_size:
            s.sendto(packets[next_seq], dest)
            sent.add(next_seq)
            next_seq += 1

    fill_window()
    timer = time.time()

    while base <= total:
        ack = receive_ack(s, 0.02)

        if ack is not None and ack > base:
            # Cumulative ACK: every packet with seq < ack has arrived.
            ack = min(ack, next_seq)
            for seq in range(base, ack):
                sent.discard(seq)
            base = ack
            # The window moved forward: reset the retransmission timer.
            fill_window()
            timer = time.time()

        if time.time() - timer >= TIMEOUT:
            # The window has not advanced: retransmit everything in it.
            for seq in sorted(sent):
                s.sendto(packets[seq], dest)
            timer = time.time()

    # --------------------------------------------------------------- END phase
    end_packet = make_packet(END, total + 1)
    s.sendto(end_packet, dest)

    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        ack = receive_ack(s, max(0.0, deadline - time.time()))
        if ack is not None and ack >= total + 1:
            break
    # Whether or not the END ACK arrived, 500 ms after sending END we are done.
    s.close()


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

    sender(args.receiver_ip, args.receiver_port, args.window_size)


if __name__ == "__main__":
    main()
