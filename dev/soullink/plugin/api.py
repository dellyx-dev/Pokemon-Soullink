"""Plugin interface in the main process: the base class with all hooks, settings, menu, tabs, displays and APIs."""
from __future__ import annotations

import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import paths, language

API_VERSION = 1
KINDS = ("switch", "selection", "number")


def error_log(base: Path, plugin_id: str, text: str) -> None:
    """Appends an entry to error.log in the data directory: a header with timestamp and plugin id, then the text (e.g. a
    traceback)."""
    try:
        with open(Path(base) / paths.ERROR_LOG, "a", encoding="utf-8") as log:
            log.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} Plugin {plugin_id}\n{text.rstrip()}\n\n")
    except OSError:
        pass


@dataclass
class Setting:
    """Main-menu setting of a plugin, one row in the plugin's group; kind is "switch", "selection" or "number", where
    selection and number require their allowed values and the default of a selection must be among them."""
    key: str
    text: str
    kind: str
    default: object
    values: tuple = ()
    display: Callable[[object], str] | None = None

    def valid(self, value) -> bool:
        """True if a stored value still fits the setting."""
        if self.kind == "switch":
            return isinstance(value, bool)
        if self.kind == "selection":
            return value in self.values
        return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass
class MenuEntry:
    """Row in the "Plugins" submenu of the player menu (Plugin.player_menu)."""
    id: str
    text: str
    trigger: Callable[[], None]
    switch: Callable[[], bool] | None = None
    reason: str = ""


class Tab:
    """Tab in the overlay (Plugin.overlay_tab); id and position are required, everything else is optional, and tabs are
    ordered by their own position."""
    id = ""
    position = 100
    replaced: str | None = None
    ram_interval: float | None = None

    def title(self, short: bool = False) -> str:
        """Label in the header; short is the abbreviation used when space is tight."""
        return self.id

    def event(self, key) -> bool:
        """Key pressed in the open tab; True means consumed, otherwise B/Y close the overlay."""
        return False

    def draw(self, area, rect, u: int, time: float) -> None:
        """Draws the content into rect; u is the base unit in pixels (font size about 0.6 u)."""

    def hints(self) -> list[tuple[str, str]]:
        """Button row at the bottom as (button, text) pairs, e.g. ("A", "Open")."""
        return []


class Display:
    """Display in the free screen field (Plugin.display), view only and without input."""
    ram_interval: float | None = None

    def draw(self, area, rect, u: int, time: float) -> None:
        """Draws the content into rect below the header (title, session and playtime are drawn by the program)."""


class PluginApi:
    """What a plugin receives from the program at create(api): texts, settings and log."""

    def __init__(self, plugin_id: str, dir: Path, base: Path, settings):
        """Creates the API for a plugin with its folder, the data directory and the settings."""
        self.id = plugin_id
        self.dir = Path(dir)
        self.base = Path(base)
        self._settings = settings
        self._definitions: dict[str, Setting] = {}

    def t(self, key: str, **values) -> str:
        """Text from the plugin's language files (internally "<id>.<key>")."""
        return language.t(f"{self.id}.{key}", **values)

    def setting(self, key: str):
        """Value of a main-menu setting: the stored one if valid, else its default; runs no plugin code, so it may be used
        inside settings()."""
        definition = self._definitions.get(key)
        values = self._settings.plugin_values.get(self.id)
        if isinstance(values, dict) and key in values:
            if definition is None or definition.valid(values[key]):
                return values[key]
        return definition.default if definition is not None else None

    def log(self, text: str) -> None:
        """Writes an entry with the plugin id to error.log."""
        error_log(self.base, self.id, text)


class GameApi(PluginApi):
    """What a plugin receives at game start (session_start): the session, the players and the core services; it applies to
    one plugin and one game, and player numbers are those of the session."""

    def __init__(self, api: PluginApi, game, slot: int | None = None):
        """Creates the game API on top of the plugin API."""
        super().__init__(api.id, api.dir, api.base, api._settings)
        self._api = api
        self._game = game
        self._slot = slot
        self.session = game.session

    def setting(self, key: str):
        """Value of a main-menu setting (see PluginApi.setting)."""
        return self._api.setting(key)

    @property
    def data_dir(self) -> Path:
        """The plugin's folder inside the session (Sessions/<name>/plugins/<id>/), created on first access."""
        dir = Path(self.session.dir) / "plugins" / self.id
        dir.mkdir(parents=True, exist_ok=True)
        return dir

    @property
    def playtime(self) -> float:
        """Seconds played in the session (keeps running)."""
        return self._game.playtime

    def _player(self, nr: int):
        """The game's player object for a number; raises KeyError if the session has no such player."""
        for sp in self._game.player:
            if sp.nr == nr:
                return sp
        raise ValueError(f"Player {nr} does not exist in this session")

    def player_numbers(self) -> list[int]:
        """Numbers of all players of the session."""
        return [sp.nr for sp in self._game.player]

    def player_info(self, nr: int) -> dict:
        """Info about a player: system ("gba"/"nds"), code (ROM game code), family (roms.family), rom (path), game_name
        (with player name), dir (player folder of the session) and color (badge color, RGB)."""
        sp = self._player(nr)
        from ..ui.graphics import player_color

        return {"nr": nr, "system": sp.system, "code": sp.code, "family": sp.family, "rom": self.session.rom(nr),
                "game_name": sp.game_name, "dir": self.session.player_dir(nr), "color": player_color(nr)}

    def ready_info(self, nr: int) -> dict | None:
        """What the player process reports at start (fps, samplerate, version, ..., plugins: {id: ready() of the worker
        part}); None while it is still starting."""
        return self._player(nr).process.ready_info

    player_process_info = ready_info

    def dex(self, nr: int):
        """ROM data of the player (dex.Dex: Pokemon, moves, items, locations, trainers); None while loading, where the
        first call for a player starts loading in the background."""
        self._player(nr)
        return self._game.rom_data.dex(nr)

    def dex_error(self, nr: int) -> str | None:
        """Why the ROM data could not be loaded, else None."""
        self._player(nr)
        return self._game.rom_data.dex_error(nr)

    def location_name(self, nr: int, location: int) -> str:
        """Name of a location id from the player's ROM, or from another player's while that loads (ids are equal per
        generation); "Location #<id>" without data."""
        self._player(nr)
        return self._game.rom_data.location_name(nr, location)

    def location_key(self, nr: int, location: int) -> int:
        """Same-named locations count as one (FireRed has "Route 4" twice): the smallest id with the same name in the
        player's ROM or, as with location_name, another player's."""
        self._player(nr)
        return self._game.rom_data.location_key(nr, location)

    def ram_request(self) -> None:
        """Makes all players send a RAM dump, which arrives at all plugins as the event ("ram", blocks)."""
        self._game.ram_requests()

    def report(self, nr: int, text: str) -> None:
        """Short notice at the bottom of the player's frame."""
        self._player(nr).report(text)

    def overlay_open(self, nr: int, tab_id: str | None = None) -> None:
        """Opens the player's overlay (closing their menu), optionally on a given tab."""
        self._player(nr)
        self._game.overlay_open(nr, tab_id)

    def worker_command(self, nr: int, data) -> None:
        """Sends data to the plugin's worker part in the player process (command(data)); the data must be picklable or an
        exception is raised here, which counts as a plugin error in a hook."""
        sp = self._player(nr)
        pickle.dumps(data)
        sp.process.plugin_command(self.id, data)

    def worker_data(self, nr: int) -> bytes | None:
        """What the worker part last delivered from after_image(); None if nothing yet, there is no slot or the player
        process crashed, in which case its last state is kept."""
        sp = self._player(nr)
        return None if sp.crashed else sp.process.plugin_data(self._slot)


class Plugin:
    """Base class of a plugin: every hook is optional and does nothing unless overridden."""

    def __init__(self, api: PluginApi):
        """Stores the plugin API."""
        self.api = api

    def settings(self) -> list[Setting]:
        """Settings for the main menu, visible only while the plugin is enabled."""
        return []

    def display_names(self) -> list[tuple[str, str]]:
        """(id, title) of the displays for the free field setting, available without a session."""
        return []

    def fits(self, session) -> bool | str:
        """Whether the plugin is active for this session: True is active, a text is inactive and shown grey in the
        "Plugins" submenu with this reason, and False means not responsible at all."""
        return True

    def process_group(self, session) -> bool:
        """True if all GBA players must run in one process (link cable)."""
        return False

    def session_start(self, game) -> None:
        """At game start: create tabs, displays and data."""

    def update(self, dt: float) -> None:
        """Called once per frame."""

    def event(self, nr: int, e) -> None:
        """Event from a player process, e.g. ("sram",), ("ram", blocks) or ("ready", info)."""

    def player_menu(self, nr: int) -> list:
        """Entries for the "Plugins" submenu of the player menu."""
        return []

    def overlay_tab(self, nr: int) -> list:
        """Tabs for the overlay."""
        return []

    def display(self, display_id: str):
        """Display for the free field for an id from display_names()."""
        return None

    def draw_game_frame(self, area, nr: int, target, source) -> None:
        """Draws over the game frame (e.g. coplayers)."""

    def symbols(self, nr: int) -> list[str]:
        """Symbols in the player label (e.g. "link")."""
        return []

    def runs_in_menu(self, nr: int) -> bool:
        """True keeps the game running while the menu is open (link cable)."""
        return False

    def fast_forward_allowed(self, nr: int) -> bool | str:
        """False or a reason text blocks fast forward."""
        return True

    def save(self) -> None:
        """Called on autosave and at the end of the game."""

    def session_end(self) -> None:
        """Cleanup after the game."""
