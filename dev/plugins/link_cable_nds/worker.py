"""Worker part of the DS link cable: passes the core's netpacket packets on to the other players over UDP."""
from __future__ import annotations

from .network import Network


class NetworkPart:
    """Own UDP port per player (ready). The command {"id": own network id, "targets": {network id: port}} plugs in or sets
    new partners, None pulls the cable; the answer says whether it is connected."""

    def __init__(self, core):
        """Creates the part with its socket."""
        self.core = core
        self.network = Network()
        self.connected = False

    def ready(self) -> dict:
        """Reports the UDP port of this player."""
        return {"network_port": self.network.port}

    def _fetch(self) -> None:
        """Hands the arrived packets to the core."""
        for sender, data in self.network.fetch():
            self.core.network_receive(data, sender)

    def before_image(self) -> None:
        """Hands in the arrived packets before every core step (the core also asks itself in the middle of a frame)."""
        if self.connected:
            self._fetch()

    def command(self, connection) -> bool:
        """Plugs in, changes partners or pulls the cable; returns the connection state."""
        if connection:
            self.network.own_id = int(connection["id"])
            self.network.targets = {int(k): int(v) for k, v in connection["targets"].items()}
            if not self.connected:
                self.core.network_start(self.network.own_id, self.network.send, self._fetch)
                self.connected = True
        elif self.connected:
            self.core.network_stop()
            self.network.targets = {}
            self.connected = False
        return self.connected

    def end(self) -> None:
        """Stops the network connection and closes the socket."""
        if self.connected:
            self.core.network_stop()
            self.connected = False
        self.network.close()


def create(core, job: dict, shared: dict) -> NetworkPart | None:
    """Creates the part only if the core supports netpacket (melonDS DS); otherwise no socket is opened."""
    return NetworkPart(core) if core.can_network else None
