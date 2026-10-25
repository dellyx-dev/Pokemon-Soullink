"""Opponent plugin: the tab "Opponent" shows the opposing Pokemon in battle live from RAM, otherwise types entered by hand."""
from __future__ import annotations

from soullink.plugin.api import Plugin

from .battle import read_battle_ram
from .tab import OpponentTab


class OpponentPlugin(Plugin):
    """Every RAM dump ("ram") delivers the player's running battle; names and types come from the player's ROM."""

    def __init__(self, api):
        """Creates the plugin without game data."""
        super().__init__(api)
        self._tab: dict[int, OpponentTab] = {}
        self._codes: dict[int, str] = {}

    def session_start(self, game) -> None:
        """Resets everything for a new game, because the plugin object survives across games."""
        numbers = game.player_numbers()
        self._codes = {nr: game.player_info(nr)["code"] or "" for nr in numbers}
        self._tab = {nr: OpponentTab(game, nr) for nr in numbers}
        for nr in numbers:
            game.dex(nr)

    def event(self, nr: int, e) -> None:
        """Passes the battle read from a RAM dump to the player's tab."""
        if e[0] == "ram" and nr in self._tab:
            self._tab[nr].battle = read_battle_ram(e[1], self._codes.get(nr, ""))

    def overlay_tab(self, nr: int) -> list:
        """The opponent tab of a player."""
        return [self._tab[nr]] if nr in self._tab else []


def create(api):
    """Creates the plugin object."""
    return OpponentPlugin(api)
