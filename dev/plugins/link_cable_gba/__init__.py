"""GBA link cable: a switch per player, all GBA players in one process, connected in lockstep (mGBA lockstep)."""
from __future__ import annotations

from soullink.plugin.api import MenuEntry, Plugin


class LinkCableGba(Plugin):
    """Main-process side. The worker part (worker.py) attaches the core to the shared lockstep coordinator of the process
    group and answers every command with whether it is connected now."""

    def __init__(self, api):
        """Creates the plugin with nobody plugged in."""
        super().__init__(api)
        self.game = None
        self.plugged_in: dict[int, bool] = {}
        self.connected: dict[int, bool] = {}

    def fits(self, session) -> bool:
        """Only GBA with at least two players; otherwise silently not responsible (no grey row)."""
        return session.system == "gba" and len(session.player) >= 2

    def process_group(self, session) -> bool:
        """mGBA lockstep links only cores in the same process."""
        return session.system == "gba" and len(session.player) >= 2

    def session_start(self, game) -> None:
        """Remembers the game."""
        self.game = game
        numbers = game.player_numbers()
        self.plugged_in = dict.fromkeys(numbers, False)
        self.connected = dict.fromkeys(numbers, False)

    def session_end(self) -> None:
        """Forgets the game and the plug state."""
        self.game, self.plugged_in, self.connected = None, {}, {}

    def _can(self, nr: int) -> bool:
        """True if the worker part runs (in the group) and its core can connect (own mGBA build)."""
        info = (self.game.ready_info(nr) or {}).get("plugins") or {}
        return bool((info.get(self.api.id) or {}).get("link"))

    def event(self, nr: int, e) -> None:
        """Handles the connection answer of a worker part."""
        if self.game is None or nr not in self.plugged_in:
            return
        if e[0] == "ready":
            self.connected[nr] = False
            if self.plugged_in[nr]:
                if self._can(nr):
                    self.game.worker_command(nr, True)
                else:
                    self.plugged_in[nr] = False
        elif e[0] == "plugin":
            self.connected[nr] = bool(e[2])

    def player_menu(self, nr: int) -> list[MenuEntry]:
        """Menu switch to plug the cable in or out."""
        if self.game is None or not self._can(nr):
            return []
        return [MenuEntry("cable", self.api.t("cable"), lambda: self._toggle(nr),
                             switch=lambda: self.plugged_in.get(nr, False))]

    def _toggle(self, nr: int) -> None:
        """Plugs the cable of a player in or out."""
        self.plugged_in[nr] = not self.plugged_in[nr]
        self.game.worker_command(nr, self.plugged_in[nr])
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
    return LinkCableGba(api)
