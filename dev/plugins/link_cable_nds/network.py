"""DS link cable: netpacket packets between the player processes over UDP on 127.0.0.1. Every DS player has an own UDP
port."""
from __future__ import annotations

import socket
import struct

from soullink.core.libretro import NETWORK_ALL

_HEADER = struct.Struct("<H")
_BUFFER = 1 << 20


class Network:
    """UDP socket of one player: sends packets to the connected partners and fetches the ones that arrived."""

    def __init__(self):
        """Opens the socket on a free port."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _BUFFER)
        if hasattr(socket, "SIO_UDP_CONNRESET"):
            self._sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.setblocking(False)
        self.port: int = self._sock.getsockname()[1]
        self.own_id = 0
        self.targets: dict[int, int] = {}

    def send(self, data: bytes, target: int) -> None:
        """Sends a packet to one network id or to all connected partners; a partner that just vanished is like a lost radio
        packet."""
        packet = _HEADER.pack(self.own_id) + data
        ports = self.targets.values() if target == NETWORK_ALL else [self.targets[target]] if target in self.targets else []
        for port in ports:
            try:
                self._sock.sendto(packet, ("127.0.0.1", port))
            except OSError:
                pass

    def fetch(self) -> list[tuple[int, bytes]]:
        """All arrived packets as (sender id, data), only from connected partners."""
        packets = []
        while True:
            try:
                packet = self._sock.recv(65536)
            except OSError:
                return packets
            if len(packet) >= _HEADER.size:
                sender = _HEADER.unpack_from(packet)[0]
                if sender in self.targets:
                    packets.append((sender, packet[_HEADER.size:]))

    def close(self) -> None:
        """Closes the socket."""
        self._sock.close()
