"""Soullink plugin: the Soullink list of all players' catches (dead/alive), the level cap by badges and the list in the
free field."""
from __future__ import annotations

from soullink.plugin.api import MenuEntry, Plugin

from .catches import read_catches, read_catches_ram, read_badge_ram
from .link_list import LinkData
from .tab import LevelTab, SoullinkList, SoullinkTab

DISPLAY = "list"


class SoullinkPlugin(Plugin):
    """Catches come from the saves at game start, then live from the RAM dumps ("ram") and after saving in the game
    ("sram"); the dead state is stored in Sessions/<name>/soullink.json."""

    def __init__(self, api):
        """Creates the plugin without game data."""
        super().__init__(api)
        self.game = None
        self.data: LinkData | None = None
        self.badge: dict[int, int | None] = {}
        self._tab: dict[int, list] = {}

    def display_names(self) -> list[tuple[str, str]]:
        """The free-field display "Soullink list"."""
        return [(DISPLAY, self.api.t("display"))]

    def session_start(self, game) -> None:
        """Resets everything for a new game, because the plugin object survives across games and the old game's session_end
        may even come after this start."""
        self.game, self._tab = game, {}
        numbers = game.player_numbers()
        codes = {nr: game.player_info(nr)["code"] for nr in numbers}
        self.data = LinkData(game.session.dir, numbers, codes, game.session.sav, read_catches, game,
                               read_catches_ram)
        self.data.all_new()
        self.data.dex_load_start()
        self.badge = dict.fromkeys(numbers)

    def event(self, nr: int, e) -> None:
        """Re-reads the catches after an in-game save ("sram") and reads team, boxes and badges live from a RAM dump
        ("ram")."""
        if self.data is None:
            return
        if e[0] == "sram":
            self.data.catches_new(nr)
        elif e[0] == "ram":
            self.data.catches_from_ram(nr, e[1])
            self.badge[nr] = read_badge_ram(e[1], self.data.codes.get(nr) or "")

    def player_menu(self, nr: int) -> list[MenuEntry]:
        """Menu entry that opens the Soullink tab."""
        return [MenuEntry("soullink", self.api.t("menu"),
                             lambda: self.game.overlay_open(nr, SoullinkTab.id))]

    def overlay_tab(self, nr: int) -> list:
        """The Soullink and Level tabs of a player."""
        if nr not in self._tab:
            self._tab[nr] = [SoullinkTab(self.game, self.data, nr),
                                LevelTab(self.game, self.data, nr, lambda: self.badge.get(nr))]
        return self._tab[nr]

    def display(self, display_id: str):
        """The Soullink list for the free field."""
        if display_id != DISPLAY or self.data is None:
            return None
        return SoullinkList(self.game, self.data)


def create(api):
    """Creates the plugin object."""
    return SoullinkPlugin(api)
