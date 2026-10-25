"""DS link cable run: connects the players through the plugin, with a UDP relay in between that counts the packets. ROM and
save state are copies; they can be passed as arguments or through SOULLINK_LINK_ROM, SOULLINK_LINK_STATE and
SOULLINK_LINK_OUTPUT, and all players start from the same save."""
from __future__ import annotations

import os
import shutil
import socket
import sys
import threading

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import link_run  # noqa: E402

ID = "link_cable_nds"
_START = ("-:30 " + link_run.repeats(20, "A:5 -:70") +
           " -:900 -:600 A:5 -:90 A:5 -:90 A:5 -:90 A:5 -:90 A:5 -:150 A:5 -:150 -:60")
DEFAULT = (
    _START + " DOWN:5 -:20 A:5 -:200 -:100 A:5 -:300 -:400 IMAGE:u1 -:300 IMAGE:u2 A:5 -:300 IMAGE:u3 A:5 -:400 IMAGE:u4"
              " A:5 -:400 IMAGE:u5",
    _START + " A:5 -:200 -:100 A:5 -:300 A:5 -:400 IMAGE:u1 -:300 IMAGE:u2 A:5 -:300 IMAGE:u3 A:5 -:400 IMAGE:u4"
              " A:5 -:400 IMAGE:u5",
)


class Relay:
    """One UDP socket per player on 127.0.0.1: whatever arrives there is counted and passed on to the player's real port."""

    def __init__(self, count: int):
        """Opens the sockets and starts a thread per player."""
        self.socks = []
        for _ in range(count):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if hasattr(socket, "SIO_UDP_CONNRESET"):
                s.ioctl(socket.SIO_UDP_CONNRESET, False)
            s.bind(("127.0.0.1", 0))
            s.settimeout(0.05)
            self.socks.append(s)
        self.ports = [s.getsockname()[1] for s in self.socks]
        self.target: dict[int, int] = {}
        self.packets, self.bytes = [0] * count, [0] * count
        self._from = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._runs = True
        self._threads = [threading.Thread(target=self._pass_on, args=(i,), daemon=True) for i in range(count)]
        for t in self._threads:
            t.start()

    def _pass_on(self, i: int) -> None:
        """Thread body: forwards and counts the packets of one socket."""
        while self._runs:
            try:
                packet = self.socks[i].recv(65536)
            except OSError:
                continue
            self.packets[i] += 1
            self.bytes[i] += len(packet)
            if i in self.target:
                try:
                    self._from.sendto(packet, ("127.0.0.1", self.target[i]))
                except OSError:
                    pass

    def stop(self) -> None:
        """Stops the relay threads and closes the sockets."""
        self._runs = False
        for t in self._threads:
            t.join(1)
        for s in self.socks + [self._from]:
            s.close()


def main(argv: list[str] | None = None) -> int:
    """Runs the DS link session and prints the packet report."""
    from soullink.player import PlayerProcess

    a = link_run.arguments(__doc__.splitlines()[0], ".nds", argv)
    scripts = a.scripts or list(DEFAULT)
    player = [PlayerProcess(nr, link_run.player_dir(a.work, nr, a.rom, a.state, "nds"), False, system="nds",
                              plugins=[link_run.entry(ID)], base=a.work) for nr in range(1, len(scripts) + 1)]
    b = link_run.Observer(player, ID)
    relay = None
    try:
        for sp in player:
            sp.start()
        if not b.wait(lambda: all(sp.ready_info for sp in player), 120):
            print("Players do not start:", [sp.error for sp in player])
            return 1
        ports = {sp.nr - 1: sp.ready_info["plugins"][ID]["network_port"] for sp in player}
        relay = Relay(len(player))
        relay.target = dict(ports)
        print("ready, real ports", ports, "Relay", relay.ports)
        for sp in player:
            own = sp.nr - 1
            sp.plugin_command(ID, {"id": own, "targets": {k: relay.ports[k] for k in ports if k != own}})
        connected = b.wait(lambda: all(a_[-1:] == [True] for a_ in b.reply.values()), 10)
        print("connected", connected, b.reply)

        def photo(nr, name):
            """Takes a screenshot and prints the packet count so far."""
            print("Screenshot", nr, name, "packets so far", list(relay.packets))

        duration = link_run.play(b, [link_run.plan(s) for s in scripts], a.output_dir, log=photo)
        print("Scripts done after", round(duration, 1), "s")
        b.wait(lambda: False, 3)
        print("Packets arrived per player:", relay.packets, "Bytes:", relay.bytes)
        for sp in player:
            sp.plugin_command(ID, None)
        b.wait(lambda: all(a_[-1:] == [False] for a_ in b.reply.values()), 10)
        print("Replies of the worker part:", b.reply)
    finally:
        for sp in player:
            sp.end()
        if relay is not None:
            relay.stop()
        if a.own_work:
            shutil.rmtree(a.work, ignore_errors=True)
    print("error", [sp.error for sp in player], "ended", [sp.ended for sp in player])
    ok = connected and all(relay.packets) and not b.error and not any(sp.error for sp in player)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
