# Reliable Transport (RTP over UDP)

Implementation of a simple reliable transport protocol built on top of UDP.
The protocol provides in-order, reliable delivery of a byte stream in the
presence of packet loss, delay, corruption, duplication, and reordering.

## Structure

| Folder | Contents |
| --- | --- |
| `RTP-base/` | Part 1 & 2: sliding-window sender with cumulative ACKs and a buffering receiver. |
| `RTP-opt/` | Part 3: per-packet ACKs; the sender retransmits only the packets that were not acknowledged. |

Each folder contains `sender.py`, `receiver.py` and `utils.py` (packet header
definition and CRC32 helper).

## Protocol summary

- 16-byte header: `type`, `seq_num`, `length`, `checksum` (32-bit CRC).
- Packet types: `START` (0), `END` (1), `DATA` (2), `ACK` (3).
- Maximum UDP payload: 1472 bytes, so at most 1456 bytes of data per packet.
- 500 ms retransmission timer.

## Requirements

- Python 3
- [scapy](https://scapy.net/)

```bash
pip install scapy
```

## Usage

Receiver:

```bash
python3 receiver.py <receiver_ip> <receiver_port> <window_size> > output.txt
```

Sender (reads the message from stdin):

```bash
python3 sender.py <receiver_ip> <receiver_port> <window_size> < message.txt
```

The receiver writes the reassembled message to stdout and exits after the
`END` packet has been acknowledged.
