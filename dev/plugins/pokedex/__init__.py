"""Pokedex plugin: the tab "Pokedex" lists all Pokemon of the player's own ROM with details, sorting and search."""
from __future__ import annotations

from soullink.plugin.api import Plugin

from .tab import PokedexTab


class PokedexPlugin(Plugin):
    """Provides the Pokedex tab for every player."""

    def __init__(self, api):
        """Creates the plugin without game data."""
        super().__init__(api)
        self._tab: dict[int, PokedexTab] = {}

    def session_start(self, game) -> None:
        """Resets everything for a new game, because the plugin object survives across games."""
        numbers = game.player_numbers()
        self._tab = {nr: PokedexTab(game, nr) for nr in numbers}
        for nr in numbers:
            game.dex(nr)

    def overlay_tab(self, nr: int) -> list:
        """The Pokedex tab of a player."""
        return [self._tab[nr]] if nr in self._tab else []


def create(api):
    """Creates the plugin object."""
    return PokedexPlugin(api)
