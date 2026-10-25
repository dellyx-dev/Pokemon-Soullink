"""DS link cable: a switch per player; whoever plugs in gets the UDP ports of the other plugged-in players."""
from __future__ import annotations

from soullink.plugin.api import MenuEntry, Plugin


class LinkCableNds(Plugin):
    """Main-process side. The network id of a player is the number minus 1; the worker part (worker.py) reports the port in
    ready(), and a restarted process (after a crash) gets the ports again."""

    def __init__(self, api):
        """Creates the plugin with nobody plugged in."""
        super().__init__(api)
        self.game = None
        self.plugged_in: dict[int, bool] = {}
        self.sent: dict[int, dict | None] = {}
        self.connected: dict[int, bool] = {}

    def fits(self, session) -> bool:
        """Only NDS with at least two players; otherwise silently not responsible (no grey row)."""
        return session.system == "nds" and len(session.player) >= 2

    def session_start(self, game) -> None:
        """Remembers the game."""
        self.game = game
        numbers = game.player_numbers()
        self.plugged_in = dict.fromkeys(numbers, False)
        self.sent = dict.fromkeys(numbers)
        self.connected = dict.fromkeys(numbers, False)

    def session_end(self) -> None:
        """Forgets the game and the plug state."""
        self.game, self.plugged_in, self.sent, self.connected = None, {}, {}, {}

    def _port(self, nr: int) -> int | None:
        """UDP port from the ready info of the worker part; None while it starts or if the core has no netpacket."""
        info = (self.game.ready_info(nr) or {}).get("plugins") or {}
        return (info.get(self.api.id) or {}).get("network_port")

    def _apply(self) -> None:
        """Gives every plugged-in player with a port the ports of the other plugged-in players; whoever pulled disconnects."""
        ports = {nr - 1: port for nr, on in self.plugged_in.items() if on and (port := self._port(nr))}
        for nr, on in self.plugged_in.items():
            own = nr - 1
            if on and own in ports:
                connection = {"id": own, "targets": {k: v for k, v in ports.items() if k != own}}
            else:
                connection = None
            if connection != self.sent[nr]:
                self.sent[nr] = connection
                self.game.worker_command(nr, connection)

    def event(self, nr: int, e) -> None:
        """Handles the connection answer of a worker part."""
        if self.game is None or nr not in self.plugged_in:
            return
        if e[0] == "ready":
            self.sent[nr], self.connected[nr] = None, False
            if self.plugged_in[nr] and not self._port(nr):
                self.plugged_in[nr] = False
            if any(self.plugged_in.values()):
                self._apply()
        elif e[0] == "plugin":
            self.connected[nr] = bool(e[2])

    def player_menu(self, nr: int) -> list[MenuEntry]:
        """Menu switch to plug the cable in or out."""
        if self.game is None or not self._port(nr):
            return []
        return [MenuEntry("cable", self.api.t("cable"), lambda: self._toggle(nr),
                             switch=lambda: self.plugged_in.get(nr, False))]

    def _toggle(self, nr: int) -> None:
        """Plugs the cable of a player in or out."""
        self.plugged_in[nr] = not self.plugged_in[nr]
        self._apply()
        self.game.report(nr, self.api.t("plugged_in" if self.plugged_in[nr] else "pulled"))

    def symbols(self, nr: int) -> list[str]:
        """The "link" symbol while the cable is plugged in and connected."""
        return ["link"] if self.plugged_in.get(nr) and self.connected.get(nr) else []

    def runs_in_menu(self, nr: int) -> bool:
        """Plugged in, the own menu does not pause the game, or the partners would stand still too."""
        return self.plugged_in.get(nr, False)

    def fast_forward_allowed(self, nr: int) -> bool | str:
        """A reason text while plugged in, since all run in the same clock."""
        return self.api.t("no_fast_forward") if self.plugged_in.get(nr) else True


def create(api):
    """Creates the plugin object."""
    return LinkCableNds(api)
