"""Game screen: all players at once with menus, audio, fast forward, autosave and crash protection. DS sessions show two
screens per player, either "hybrid" (large plus small, swappable per player) or "columns" (stacked); anyone can switch
the view for everybody in the player menu, and touch works through the right stick, d-pad mode or the mouse. Plugins
attach through plugin/session.py: overlay tabs, free-field displays and per-frame hooks, with the "Plugins" submenu in
plugin_menu.py."""
from __future__ import annotations

import time
from datetime import datetime

import pygame

from .. import layout
from ..image import Scaler, draw_symbol
from ..config import save_settings
from ..input.devices import KEYBOARD_ID, DeviceEvent, KeysEvent
from ..input.control import PlayerControl
from ..input.keys import CONFIRM, KEYBOARD, BACK_KEYS, Key
from ..input.key_binding import Function, KeyboardBinding, KeyBinding, key_name
from ..core.libretro import pointer_value
from ..plugin.session import PluginSession
from ..rom_data import RomData
from ..roms import code_from_file, family, game_name_from_file
from ..profile import MAX_NAME, kind_of
from ..session import candidates, with_name
from ..player import DEFAULT_OPTIONS, ProcessGroup, PlayerProcess
from ..language import current as language_current
from ..language import t
from ..audio import Mixer, AudioOutput
from . import graphics
from .app import Screen
from .menu import BACK, Menu, Repeater
from .start import VOLUME_STEP
from .free_field import FreeField, SessionDisplay
from .plugin_menu import PluginMenu
from .keys_menu import KeysMenu
from .keyboard import VirtualKeyboard, draw_name_input
from .types_overlay import TypesOverlay, TypesTab

MENU_GROUPS = {"audio": "menu.group_audio", "music": "menu.group_audio", "view": "menu.group_screen",
                 "swap": "menu.group_screen", "cross": "menu.group_screen",
                 "overlay": "menu.group_more", "plugins": "menu.group_more", "bind": "menu.group_more"}
SAVE_DEADLINE = 5.0
HINT_DURATION = 6.0
DEADZONE = 8000
CURSOR_TEMPO = 240.0
CURSOR_VISIBLE = 3.0
BUTTON_SHORT = {Key.SOUTH: "A", Key.EAST: "B", Key.WEST: "X", Key.NORTH: "Y", Key.L: "L", Key.R: "R",
              Key.L2: "L2", Key.R2: "R2", Key.STICK_L: "L3", Key.STICK_R: "R3", Key.START: "START",
              Key.SELECT: "SELECT", Key.UP: "button.up", Key.DOWN: "button.down", Key.LEFT: "button.left",
              Key.RIGHT: "button.right"}
MENU_NAVIGATION = CONFIRM | BACK_KEYS | {Key.START, Key.UP, Key.DOWN, Key.LEFT, Key.RIGHT,
                                                   Key.L, Key.R}
HOLD = 0.5
AUDIO_STEP = 1
MENU_KEY = {Function.A: Key.SOUTH, Function.B: Key.EAST, Function.X: Key.WEST, Function.Y: Key.NORTH,
               Function.L: Key.L, Function.R: Key.R, Function.START: Key.START, Function.SELECT: Key.SELECT,
               Function.UP: Key.UP, Function.DOWN: Key.DOWN, Function.LEFT: Key.LEFT,
               Function.RIGHT: Key.RIGHT}


def _rect(r: layout.Rect) -> pygame.Rect:
    """Converts a layout rectangle into a pygame.Rect."""
    return pygame.Rect(r.x, r.y, r.w, r.h)


class _Player:
    """State of one player in the game screen: device, process, volume, key bindings and profile, menus, overlay, crash and
    DS cursor state."""

    def __init__(self, nr: int, device: str | None, process, game_name: str, volume: int, system: str,
                 keys: dict | None = None, keyboard: dict | None = None, profile: str | None = None):
        """Creates the player state for a device and a worker process."""
        self.nr = nr
        self.device = device
        self.process = process
        self.game_name = game_name
        self.volume = volume
        self.volume_before = volume or 100
        self.system = system
        self.keys = KeyBinding.from_dict(keys, ds=system == "nds")
        self.keyboard = KeyboardBinding.from_dict(keyboard, ds=system == "nds")
        self.control = PlayerControl(self.keyboard if device == KEYBOARD_ID else self.keys)
        self.profile = profile
        self.profile_input: VirtualKeyboard | None = None
        self.repeat = Repeater()
        self.pauses: set[str] = set() if device else {"controller"}
        self.menu: Menu | None = None
        self.menu_actions: list[str] = []
        self.menu_question = False
        self.crashed = False
        self.fast_forward = False
        self.sent_pause = False
        self.scaler = {"gba": Scaler(), "top": Scaler(), "bottom": Scaler()}
        self.raw_image: pygame.Surface | None = None
        self.images: dict[str, pygame.Surface] = {}
        self.hint: str | None = None
        self.hint_until = 0.0
        self.swapped = False
        self.cursor = [128.0, 96.0]
        self.touch = False
        self.touch_cross = False
        self.mouse = False
        self.cursor_until = 0.0
        self.sent_pointer: tuple | None = None
        self.types = TypesOverlay()
        self.types_open = False
        self.family: str | None = None
        self.code = ""
        self.upper_since: float | None = None
        self.released = False
        self.submenu: str | bool = False
        self.plugin_rows: list[tuple] = []
        self.core_tab: list = []
        self.plugin_tab: list = []
        self.keys_menu: KeysMenu | None = None

    @property
    def audio(self) -> bool:
        """True while the game audio is on."""
        return self.volume > 0

    def device_set(self, device: str | None) -> None:
        """Assigns another device (or None) to the player and switches the key binding accordingly."""
        self.device = device
        self.control.release()
        self.repeat.stop()
        if device is not None:
            self.control.binding = self.keyboard if device == KEYBOARD_ID else self.keys

    def report(self, text: str) -> None:
        """Shows a short notice at the bottom of the player's frame."""
        self.hint, self.hint_until = text, time.monotonic() + HINT_DURATION


class GameScreen(Screen):
    """The game screen for a session and the devices of its players."""
    quieter_background = True

    def __init__(self, app, session, devices_the_player: list[str | None], process_factory=PlayerProcess,
                 dex_load: bool | None = None):
        """Creates the player states and processes, the plugin session, the free field and the audio mixer."""
        super().__init__(app)
        self.session = session
        self.factory = process_factory
        self.ds = session.system == "nds"
        self.view = app.settings.ds_view if app.settings.ds_view in layout.VIEWS else "hybrid"
        self._cells_compute()
        self.plugins = PluginSession(app.plugins.active(), session, self)
        self.plugin_menu = PluginMenu(self)
        several = len(session.player) >= 2 and session.system == "gba" and self.plugins.process_group()
        self.group = ProcessGroup(len(session.player)) if several else None
        self.player: list[_Player] = []
        for info, device in zip(session.player, devices_the_player):
            process = self._start(info.nr, info.audio_percent > 0, info.system)
            name = with_name(game_name_from_file(session.rom(info.nr)) or "?", info.name)
            keys, keyboard, kind = info.keys, info.keyboard, kind_of(device)
            profile = info.profile if app.profile.exists(kind, info.profile, info.system) else None
            if profile is not None:
                data = app.profile.binding(kind, profile, info.system)
                keys, keyboard = (keys, data) if kind == "keyboard" else (data, keyboard)
            self.player.append(_Player(info.nr, device, process, name, info.audio_percent, info.system, keys,
                                         keyboard, profile))
        for sp in self.player:
            sp.code = code_from_file(session.rom(sp.nr)) or ""
            sp.family = family(sp.code)
        if dex_load is None:
            dex_load = process_factory is PlayerProcess
        self.rom_data = RomData([sp.nr for sp in self.player], self._dex_load if dex_load else None)
        self.ram_requested = 0.0
        self.mixer: Mixer | None = None
        self.output: AudioOutput | None = None
        self.music_before = app.music.volume or 50
        self.state = "playing"
        self.memory_jobs: dict[int, int] = {}
        self.save_until = 0.0
        self.afterwards_end = False
        self._keyboard_consumed = False
        self.playtime = float(session.playtime_seconds)
        self.autosave_rest = app.settings.autosave_minutes * 60
        self.core_version = session.core_version
        self.time = 0.0
        if self.ds:
            pygame.mouse.set_visible(True)
        self._plugins_start()

    def _plugins_start(self) -> None:
        """Calls session_start of all plugins last, so the GameApi finds everything, then collects their overlay tabs and
        free-field displays."""
        self.plugins.start()
        for sp in self.player:
            sp.core_tab, sp.plugin_tab = self._core_tab(sp), self.plugins.tab(sp.nr)
            sp.types = TypesOverlay(sp.core_tab + sp.plugin_tab, self.plugins.tab_discarded)
        self.field = FreeField(self.plugins.show(), SessionDisplay([(sp.nr, sp.game_name) for sp in self.player]))

    def _start(self, nr: int, audio: bool, system: str):
        """Starts the worker process of a player."""
        extra = {}
        mac = next((s.mac for s in self.session.player if s.nr == nr), None)
        if mac:
            extra["core_options"] = {**DEFAULT_OPTIONS.get(system, {}), "melonds_mac_address_mode": mac}
        if self.group is not None and not self.group.started:
            extra["group"] = self.group
        process = self.factory(nr, self.session.player_dir(nr), audio, system=system,
                              plugins=self.plugins.worker_plugins(), base=self.app.base, **extra)
        process.start()
        return process

    @staticmethod
    def _core_tab(sp: _Player) -> list:
        """The core's overlay tabs: only the type table (plugins bring everything else)."""
        return [TypesTab()]

    def _player_nr(self, nr: int) -> _Player:
        """The player state for a player number."""
        return next(sp for sp in self.player if sp.nr == nr)

    def _dex_load(self, nr: int):
        """Loads the dex of a player from its ROM (blocking; runs in a background thread)."""
        from .. import dex, paths

        path = dex.ensure(self.session.player_dir(nr), self.session.rom(nr), paths.java_program(),
                                 paths.dex_jar())
        return dex.load(path)

    def _cells_compute(self) -> None:
        """Computes the cell layout for the current window size."""
        count = len(self.session.player)
        if self.ds:
            self.cells = layout.compute_ds(count, *self.app.size, self.view)
        else:
            self.cells = layout.compute(count, *self.app.size)

    def _screens(self, i: int) -> list[tuple[pygame.Rect, str]]:
        """(target rectangle, source) per screen of a cell; the source is "gba", "top" or "bottom"."""
        z = self.cells[i]
        if not self.ds:
            return [(_rect(z.game), "gba")]
        if self.view == "hybrid" and self.player[i].swapped:
            return [(_rect(z.large), "bottom"), (_rect(z.small), "top")]
        return [(_rect(z.large), "top"), (_rect(z.small), "bottom")]

    def _game_area(self, i: int) -> pygame.Rect:
        """Rectangle that contains all screens of a player."""
        rects = [r for r, _ in self._screens(i)]
        return rects[0].unionall(rects[1:]) if len(rects) > 1 else rects[0]

    def _bottom(self, i: int) -> pygame.Rect | None:
        """Rectangle of the DS touch screen; None for GBA."""
        return next((r for r, source in self._screens(i) if source == "bottom"), None)

    def _scale(self, i: int) -> None:
        """Rescales the player's frames to their target rectangles."""
        sp = self.player[i]
        if sp.raw_image is None:
            return
        for target, source in self._screens(i):
            if source == "gba":
                image = sp.raw_image
            else:
                y = 0 if source == "top" else layout.DS_H
                image = sp.raw_image.subsurface((0, y, layout.DS_W, layout.DS_H))
            sp.images[source] = sp.scaler[source].scale(image, target.size)

    def view_switch(self) -> None:
        """Switches the DS view between hybrid and columns."""
        if not self.ds:
            return
        self.view = "columns" if self.view == "hybrid" else "hybrid"
        self.app.settings.ds_view = self.view
        save_settings(self.app.base, self.app.settings)
        self._cells_compute()
        for i in range(len(self.player)):
            self._scale(i)
        self._menus_refresh()

    def _swap(self, sp: _Player) -> None:
        """Swaps the large and the small DS screen of a player."""
        sp.swapped = not sp.swapped
        self._scale(self.player.index(sp))

    def repeat_kind(self, key) -> None:
        """Held keys are repeated by each player itself, so the app repeats nothing."""
        return None

    def _menu_entries(self, sp: _Player) -> list[tuple[str, str]]:
        """Entries of the player menu; music and DS view apply to everybody."""
        entries = [("next", t("general.next")), ("audio", t("menu.audio")), ("music", t("menu.music"))]
        if sp.system == "nds":
            entries.append(("view", t("menu.view")))
            if self.view == "hybrid":
                entries.append(("swap", t("menu.swap")))
            entries.append(("cross", t("menu.cross")))
        entries.append(("overlay", t("menu.overlay")))
        if self.plugin_menu.visible(sp.nr):
            entries.append(("plugins", t("menu.plugins")))
        entries.append(("bind", t("menu.new_bind")))
        entries.append(("end", t("menu.save")))
        return entries

    def _menus_refresh(self) -> None:
        """Relabels open player menus after music or view changed."""
        for sp in self.player:
            if sp.menu is not None and not sp.menu_question and not sp.submenu:
                self._menu_open(sp)

    def _menu_index(self, sp: _Player, action: str) -> int:
        """Index of an action in the player's menu."""
        actions = [a for a, _ in self._menu_entries(sp)]
        return actions.index(action) if action in actions else 0

    def overlay_open(self, nr: int, tab_id: str | None = None) -> None:
        """Opens a player's overlay (for plugins) and closes their menu; nothing happens while the player is busy with
        something else (rebinding keys, profile name, confirmation)."""
        sp = self._player_nr(nr)
        if sp.crashed or sp.device is None or sp.keys_menu is not None or sp.profile_input is not None \
                or sp.menu_question:
            return
        sp.menu, sp.menu_question, sp.submenu = None, False, False
        sp.pauses.discard("menu")
        if tab_id is not None:
            sp.types.show(tab_id)
        if not sp.types_open:
            self._types_open(sp)

    def _menu_open(self, sp: _Player, selection: int | None = None) -> None:
        """Opens the player menu."""
        entries = self._menu_entries(sp)
        old = sp.menu.selection if sp.menu is not None and selection is None else (selection or 0)
        sp.menu_actions = [a for a, _ in entries]
        sp.menu, sp.menu_question, sp.submenu = Menu([t for _, t in entries]), False, False
        sp.menu.selection = min(old, len(entries) - 1)

    def raw(self, ev) -> None:
        """Handles raw pygame events: Escape, keyboard players and the mouse; the same key arrives afterwards as a position
        key, and a key consumed raw is dropped."""
        self._keyboard_consumed = False
        if self.state != "playing":
            return
        if ev.type in (pygame.KEYDOWN, pygame.KEYUP):
            sp = next((s for s in self.player if s.device == KEYBOARD_ID), None)
            if sp is not None and self._keyboard_raw(sp, ev):
                self._keyboard_consumed = True
                return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_t:
            sp = next((s for s in self.player if s.device == KEYBOARD_ID), None)
            if sp is not None and sp.menu is None and not sp.crashed:
                self._types_close(sp) if sp.types_open else self._types_open(sp)
        elif self.ds:
            self._mouse(ev)

    def _keyboard_raw(self, sp: _Player, ev) -> bool:
        """Keyboard player: all keys arrive raw with the player's binding, in the game and in the menus; True means
        consumed."""
        pressed = ev.type == pygame.KEYDOWN
        if sp.keys_menu is not None and sp.keys_menu.waits is not None:
            if pressed and ev.key == pygame.K_ESCAPE:
                sp.keys_menu.waits = None
            elif pressed:
                sp.keys_menu.bind_with(ev.key)
            return True
        if self._in_game(sp):
            if ev.key == pygame.K_ESCAPE:
                if pressed:
                    sp.control.release()
                    self._menu_open(sp, 0)
                    sp.pauses.add("menu")
                return True
            if sp.control.binding.function(ev.key) is None:
                return False
            self._game_input(sp, ev.key, pressed)
            return True
        key = self._menu_key(sp, ev.key, KEYBOARD.get(ev.key, Key.EAST if ev.key == pygame.K_ESCAPE else None))
        if key is None:
            return False
        self._menu_input(sp, key, pressed, ev.key)
        return True

    @staticmethod
    def _menu_key(sp: _Player, input, fallback: Key | None) -> Key | None:
        """Menu key for a pressed input: the function from the player's own binding, else the position."""
        return MENU_KEY.get(sp.control.binding.function(input), fallback)

    @staticmethod
    def _in_game(sp: _Player) -> bool:
        """True if the player is in the running game and not in a menu, overlay or crash message."""
        return not sp.crashed and sp.menu is None and sp.keys_menu is None and not sp.types_open \
            and sp.profile_input is None

    def _mouse(self, ev) -> None:
        """Handles mouse input for the DS touch screen."""
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for i, sp in enumerate(self.player):
                bottom = self._bottom(i)
                if bottom is not None and bottom.collidepoint(ev.pos) and not sp.pauses and not sp.crashed:
                    sp.mouse = True
                    self._cursor_on(sp, bottom, ev.pos)
        elif ev.type == pygame.MOUSEMOTION:
            for i, sp in enumerate(self.player):
                if sp.mouse:
                    self._cursor_on(sp, self._bottom(i), ev.pos)
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            for sp in self.player:
                sp.mouse = False

    @staticmethod
    def _cursor_on(sp: _Player, bottom: pygame.Rect, pos) -> None:
        """Moves the touch cursor to a mouse position over the bottom screen."""
        sp.cursor = [(pos[0] - bottom.x) * layout.DS_W / bottom.width, (pos[1] - bottom.y) * layout.DS_H / bottom.height]
        sp.cursor_until = time.monotonic() + CURSOR_VISIBLE

    def event(self, e) -> None:
        """Handles a key or device event."""
        if self.state != "playing":
            return
        if isinstance(e, DeviceEvent):
            if e.kind == "away":
                for sp in self.player:
                    if sp.device == e.device:
                        sp.device_set(None)
                        sp.menu = None
                        sp.pauses.discard("menu")
                        self._types_close(sp)
                        if sp.keys_menu is not None:
                            self._keys_done(sp)
                        sp.upper_since = None
                        sp.pauses.add("controller")
            return
        if not isinstance(e, KeysEvent):
            return
        if e.device == KEYBOARD_ID and self._keyboard_consumed:
            return
        sp = next((s for s in self.player if s.device == e.device), None)
        if sp is None:
            free = next((s for s in self.player if s.device is None), None)
            if free is not None and e.pressed and e.key in CONFIRM:
                free.device_set(e.device)
                free.released = False
                free.pauses.discard("controller")
                free.report(t("game.controller_applied", name=self.app.devices.name(e.device)))
            return
        if sp.device == KEYBOARD_ID:
            return
        if self._in_game(sp):
            self._game_input(sp, e.key, e.pressed)
        else:
            self._menu_input(sp, self._menu_key(sp, e.key, e.key), e.pressed, e.key)

    def _menu_input(self, sp: _Player, key: Key, pressed: bool, raw) -> None:
        """Routes input to the crash message, player menu, key menu or overlay; key is the menu key from the player's
        binding and raw the really pressed input (position key or keyboard code)."""
        if not pressed:
            if sp.repeat.stop(key):
                self.app.volume_change(0)
            return
        if sp.repeat.stop():
            self.app.volume_change(0)
        bound_now = sp.keys_menu is not None and sp.keys_menu.waits is not None
        self._menu_press(sp, key, raw)
        kind = self._repeat_kind(sp, key)
        if kind is not None and not bound_now and not self._in_game(sp):
            sp.repeat.start(key, time.monotonic(), kind)

    def _menu_press(self, sp: _Player, key: Key, raw, repeats: bool = False) -> None:
        """Handles a menu key press of one player."""
        if sp.crashed:
            if key in CONFIRM:
                self._restart(sp)
            return
        if sp.menu is not None:
            self._player_menu(sp, key, raw, repeats)
            return
        if sp.profile_input is not None:
            result = sp.profile_input.event(key)
            name = sp.profile_input.text.strip()
            if result == "done" and name:
                self._profile_create(sp, name)
            elif result is not None:
                sp.profile_input = None
                sp.pauses.discard("profile")
                sp.pauses.add("menu")
                self._new_bind(sp, 1)
            return
        if sp.keys_menu is not None:
            input = raw if sp.keys_menu.waits is not None else key
            if sp.keys_menu.event(input, time.monotonic()) == "done":
                self._keys_done(sp)
            return
        if sp.types_open:
            if sp.types.event(key) == "close" or self._is_menu_key(sp, key, raw):
                self._types_close(sp)

    def _repeat_kind(self, sp: _Player, key: Key) -> str | None:
        """How a held key repeats: sliders faster than lists, the view switch not at all (it would flicker)."""
        if key not in (Key.UP, Key.DOWN, Key.LEFT, Key.RIGHT):
            return None
        if key in (Key.LEFT, Key.RIGHT):
            action = self._action(sp)
            if action in ("audio", "music"):
                return "slider"
            if action == "view":
                return None
        return "list"

    @staticmethod
    def _action(sp: _Player) -> str | None:
        """Chosen entry of the player menu (without confirmation and submenu)."""
        if sp.menu is None or sp.menu_question or sp.submenu:
            return None
        return sp.menu_actions[sp.menu.selection]

    def _game_input(self, sp: _Player, input, pressed: bool) -> None:
        """Input in the running game; input is a position key (controller) or key code (keyboard)."""
        function = sp.control.binding.function(input)
        if function == Function.MENU:
            if pressed:
                sp.upper_since = time.monotonic()
            elif sp.upper_since is not None:
                sp.upper_since = None
                sp.control.release()
                self._menu_open(sp, 0)
                sp.pauses.add("menu")
            return
        sp.control.event(input, pressed)
        if self.ds and function == Function.SWAP and pressed and self.view == "hybrid":
            self._swap(sp)

    def _player_menu(self, sp: _Player, key: Key, raw=None, repeats: bool = False) -> None:
        """Handles a key in the player menu."""
        chosen = self._action(sp)
        if key in (Key.LEFT, Key.RIGHT) and chosen in ("audio", "music", "view"):
            direction = 1 if key == Key.RIGHT else -1
            if chosen == "audio":
                self._audio_set(sp, sp.volume + direction * AUDIO_STEP)
            elif chosen == "music":
                self._music_set(self.app.music.volume + direction * VOLUME_STEP, not repeats)
            else:
                self.view_switch()
            return
        choice = sp.menu.event(key)
        if sp.menu_question == "profile":
            if choice == 1:
                self._profile_names_ask(sp)
            elif choice == 0 or choice == BACK or self._is_menu_key(sp, key, raw):
                self._new_bind(sp, 1)
            return
        if sp.menu_question:
            if choice == 1:
                self.save_and_end()
            elif choice == 0 or choice == BACK or self._is_menu_key(sp, key, raw):
                self._menu_open(sp, len(self._menu_entries(sp)) - 1)
            return
        if sp.submenu == "plugins":
            self.plugin_menu.key(sp, choice, self._is_menu_key(sp, key, raw))
            return
        if sp.submenu:
            action = sp.menu_actions[choice] if isinstance(choice, int) else None
            if choice == BACK or self._is_menu_key(sp, key, raw):
                self._menu_open(sp, self._menu_index(sp, "bind"))
            elif action == "controller":
                self._controller_release(sp)
            elif action == "keys" and sp.profile is None:
                sp.menu, sp.menu_question, sp.submenu = Menu([t("general.no"), t("general.yes")]), "profile", False
                sp.menu_actions = ["no", "yes"]
            elif action == "keys":
                self._keys_open(sp)
            return
        if choice == BACK or self._is_menu_key(sp, key, raw):
            action = "next"
        elif isinstance(choice, int):
            action = sp.menu_actions[choice]
        else:
            return
        if action == "next":
            sp.menu = None
            sp.pauses.discard("menu")
        elif action == "audio":
            self._audio_set(sp, 0 if sp.audio else sp.volume_before)
        elif action == "music":
            self._music_set(0 if self.app.music.volume else self.music_before)
        elif action == "view":
            self.view_switch()
        elif action == "swap":
            self._swap(sp)
        elif action == "overlay":
            sp.menu = None
            sp.pauses.discard("menu")
            self._types_open(sp)
        elif action == "plugins":
            self.plugin_menu.open_(sp)
        elif action == "bind":
            self._new_bind(sp)
        elif action == "cross":
            sp.touch_cross = not sp.touch_cross
            sp.cursor_until = time.monotonic() + CURSOR_VISIBLE
            self._menu_open(sp)
        elif action == "end":
            sp.menu, sp.menu_question = Menu([t("general.no"), t("general.yes")]), "save"
            sp.menu_actions = ["no", "yes"]

    @staticmethod
    def _new_bind(sp: _Player, selection: int = 0) -> None:
        """Opens the "rebind" submenu."""
        sp.menu_actions = ["controller", "keys"]
        sp.menu = Menu([t("menu.controller_switch"), t("keys.title")])
        sp.menu.selection = selection
        sp.menu_question, sp.submenu = False, "bind"

    @staticmethod
    def _profile_names_ask(sp: _Player) -> None:
        """Opens the input for a new profile name."""
        sp.menu, sp.menu_question = None, False
        sp.pauses.discard("menu")
        sp.pauses.add("profile")
        sp.profile_input = VirtualKeyboard("", MAX_NAME)

    def _profile_create(self, sp: _Player, name: str) -> None:
        """Creates a new profile as a copy of the current binding (usually the default) and starts binding right away."""
        sp.profile_input = None
        sp.pauses.discard("profile")
        sp.profile = self.app.profile.create(kind_of(sp.device), sp.system, name, sp.control.binding.to_dict())
        info = self.session.player[sp.nr - 1]
        info.profile = sp.profile
        self.session.save()
        self._keys_open(sp)

    def _keys_open(self, sp: _Player) -> None:
        """Opens the key binding menu."""
        sp.menu, sp.submenu = None, False
        sp.pauses.discard("menu")
        sp.control.release()
        keyboard = sp.device == KEYBOARD_ID
        title = t("keys.title_profile", name=sp.profile) if sp.profile else \
            t("keys.title_keyboard" if keyboard else "keys.title")
        sp.keys_menu = KeysMenu(sp.control.binding, self.ds, title, only_raw=keyboard, nr=sp.nr)
        sp.pauses.add("keys")

    def _music_set(self, percent: int, save: bool = True) -> None:
        """Sets the music volume for everybody; while a key is held it is saved only on release."""
        if self.app.music.volume:
            self.music_before = self.app.music.volume
        self.app.volume_change(percent - self.app.music.volume, save)
        self._menus_refresh()

    def _audio_set(self, sp: _Player, percent: int) -> None:
        """Sets the game volume of a player in percent."""
        sp.volume = max(0, min(100, percent))
        if sp.volume:
            sp.volume_before = sp.volume
        sp.process.audio(sp.audio)
        if self.mixer is not None:
            self.mixer.volume(sp.nr, sp.volume)
            if not sp.audio:
                self.mixer.clear(sp.nr)
        info = self.session.player[sp.nr - 1]
        info.volume, info.audio = sp.volume, sp.audio
        self._menu_open(sp)

    @staticmethod
    def _is_menu_key(sp: _Player, key: Key, raw=None) -> bool:
        """True if the key is the one the player assigned to "menu" (unless it is used for navigation)."""
        input = key if raw is None else raw
        return sp.control.binding.function(input) == Function.MENU and key not in MENU_NAVIGATION

    @staticmethod
    def _controller_release(sp: _Player) -> None:
        """"Change controller": the player waits for a free controller, the smallest free player first."""
        sp.device_set(None)
        sp.menu, sp.submenu = None, False
        sp.pauses.discard("menu")
        sp.released = True
        sp.pauses.add("controller")

    def _keys_done(self, sp: _Player) -> None:
        """Closes the key binding menu and stores the binding."""
        sp.keys_menu = None
        sp.pauses.discard("keys")
        sp.control.release()
        if sp.profile is not None:
            kind, data = kind_of(sp.device), sp.control.binding.to_dict()
            self.app.profile.set_(kind, sp.profile, sp.system, data)
            for other in self.player:
                if other is not sp and other.profile == sp.profile and kind_of(other.device) == kind \
                        and other.system == sp.system:
                    if kind == "keyboard":
                        other.keyboard = KeyboardBinding.from_dict(data, ds=other.system == "nds")
                    else:
                        other.keys = KeyBinding.from_dict(data, ds=other.system == "nds")
                    other.device_set(other.device)
            self.session.player[sp.nr - 1].profile = sp.profile
        elif sp.control.binding is sp.keyboard:
            self.session.player[sp.nr - 1].keyboard = sp.keyboard.to_dict()
        else:
            self.session.player[sp.nr - 1].keys = sp.keys.to_dict()
        self.session.save()

    def ram_requests(self) -> None:
        """Makes all workers send their memory, which goes to all plugins as ("ram", blocks)."""
        self.ram_requested = time.monotonic()
        for s in self.player:
            if s.process.alive and not s.crashed:
                s.process.ram_request()

    def _ram_interval(self) -> float | None:
        """Shortest RAM interval of the open tabs and the free-field display; None if none is wanted."""
        intervals = [sp.types.active.ram_interval for sp in self.player if sp.types_open and sp.types.active]
        if len(self.cells) > len(self.player):
            intervals.append(self.field.current(self.app.settings.free_field, self.time)[2].ram_interval)
        intervals = [i for i in intervals if i]
        return min(intervals) if intervals else None

    def _types_open(self, sp: _Player) -> None:
        """Opens the overlay of a player."""
        self.ram_requests()
        sp.types_open = True
        sp.upper_since = None
        sp.control.release()
        sp.pauses.add("types")

    @staticmethod
    def _types_close(sp: _Player) -> None:
        """Closes the overlay of a player."""
        sp.types_open = False
        sp.types.close()
        sp.repeat.stop()
        sp.pauses.discard("types")

    def _restart(self, sp: _Player) -> None:
        """Restarts the worker process of a crashed player."""
        sp.process.end()
        sp.process = self._start(sp.nr, sp.audio, sp.system)
        sp.crashed = sp.fast_forward = sp.sent_pause = False
        sp.raw_image, sp.images, sp.sent_pointer = None, {}, None
        sp.control.release()
        sp.report(t("game.new_started"))

    def _session_update(self) -> None:
        """Updates playtime, last played and autosave countdown of the session."""
        s = self.session
        s.last_played = datetime.now().isoformat(timespec="seconds")
        s.playtime_seconds = int(self.playtime)
        s.core_version = self.core_version or s.core_version
        for sp in self.player:
            s.player[sp.nr - 1].audio, s.player[sp.nr - 1].volume = sp.audio, sp.volume

    def _alive(self) -> list[_Player]:
        """Players whose process runs and has not crashed."""
        return [sp for sp in self.player if sp.process.alive and not sp.crashed]

    def autosave(self) -> None:
        """Saves all running players."""
        for sp in self._alive():
            sp.process.save()
        self.plugins.save()
        self._session_update()
        self.session.save()

    def save_and_end(self) -> None:
        """Saves all players and ends the game."""
        if self.state != "playing":
            return
        self.state = "saving"
        for sp in self.player:
            sp.menu = None
        self.memory_jobs = {sp.nr: sp.process.save() for sp in self._alive()}
        self.save_until = time.monotonic() + SAVE_DEADLINE

    def _finish(self) -> None:
        """Writes the session and ends the plugins after saving."""
        self.plugins.save()
        self._session_update()
        self.session.save()
        self._clean_up()
        if self.afterwards_end:
            self.app.end()
        else:
            from .start import AFTER_GAME_LOCK, StartScreen

            self.app.switch(StartScreen(self.app, lock=AFTER_GAME_LOCK))

    def _clean_up(self) -> None:
        """Ends all processes, audio and plugins."""
        if self.state == "ended":
            return
        self.state = "ended"
        self.plugins.end()
        for sp in self.player:
            sp.process.end()
        if self.output is not None:
            self.output.close()
            self.output = None
        if self.ds and not self.app.window:
            pygame.mouse.set_visible(False)

    def close_requested(self) -> None:
        """The window is being closed: save first, then quit."""
        self.afterwards_end = True
        if self.state == "playing":
            self.save_and_end()

    def leave(self) -> None:
        """Cleans up when another screen takes over."""
        self._clean_up()

    def _audio_start(self, samplerate: int) -> None:
        """Starts the audio mixer and output for the sample rate."""
        self.mixer = Mixer(samplerate)
        for sp in self.player:
            self.mixer.volume(sp.nr, sp.volume)
        try:
            self.output = AudioOutput(self.mixer, samplerate)
        except Exception:
            self.output = None

    def _events_fetch(self, sp: _Player) -> None:
        """Processes the events of a player's process."""
        for e in sp.process.fetch():
            if e[0] == "ready":
                self._ready(sp, e[1])
            self.plugins.event(sp.nr, e)

    def _ready(self, sp: _Player, info: dict) -> None:
        """A player's process reported ready."""
        self.core_version = info.get("version") or self.core_version
        if self.mixer is None:
            self._audio_start(info["samplerate"])
        source = info.get("source")
        if source and source.endswith(".bak"):
            sp.report(t("game.backup_loaded"))
        elif source is None and candidates(self.session.sav(sp.nr)):
            sp.report(t("game.ingame_start"))

    def _touch(self, sp: _Player, pause: bool, dt: float) -> None:
        """Moves the touch cursor through the right stick, d-pad mode or the mouse and taps through the touch key (default
        R2), A or a click."""
        now = time.monotonic()
        pressed = False
        if sp.device is not None and not pause:
            devices = self.app.devices
            for k, axis in enumerate((pygame.CONTROLLER_AXIS_RIGHTX, pygame.CONTROLLER_AXIS_RIGHTY)):
                value = devices.axis(sp.device, axis)
                if abs(value) > DEADZONE:
                    sp.cursor[k] += value / 32767 * CURSOR_TEMPO * dt
                    sp.cursor_until = now + CURSOR_VISIBLE
            pressed = sp.control.holds_function(Function.TOUCH)
            if sp.touch_cross:
                holds = sp.control.holds_function
                dx = holds(Function.RIGHT) - holds(Function.LEFT)
                dy = holds(Function.DOWN) - holds(Function.UP)
                sp.cursor[0] += dx * CURSOR_TEMPO * 0.6 * dt
                sp.cursor[1] += dy * CURSOR_TEMPO * 0.6 * dt
                pressed = pressed or holds(Function.A) or holds(Function.B)
        pressed = (pressed or sp.mouse) and not pause
        sp.cursor = [min(max(sp.cursor[0], 0.0), layout.DS_W - 1.0), min(max(sp.cursor[1], 0.0), layout.DS_H - 1.0)]
        if pressed:
            sp.cursor_until = now + CURSOR_VISIBLE
        sp.touch = pressed
        pointer = (pointer_value(sp.cursor[0], layout.DS_W), pointer_value(layout.DS_H + sp.cursor[1], 2 * layout.DS_H),
                  pressed)
        if pointer != sp.sent_pointer:
            sp.process.pointer(*pointer)
            sp.sent_pointer = pointer

    def update(self, dt: float) -> None:
        """Advances the game by dt seconds: events, audio, autosave, touch and the plugin hooks."""
        self.time += dt
        if self.state == "ended":
            return
        global_pause = self.state == "saving"
        factor = max(1, int(self.app.settings.fast_forward_factor))
        now = time.monotonic()
        if self.plugins.changed:
            self.plugin_menu.new_order()
        interval = self._ram_interval()
        if interval is not None and now - self.ram_requested > interval:
            self.ram_requests()
        for i, sp in enumerate(self.player):
            if sp.upper_since is not None and now - sp.upper_since >= HOLD and sp.menu is None:
                self._types_open(sp)
            if sp.keys_menu is not None:
                sp.keys_menu.update(now)
            if (key := sp.repeat.due(now)) is not None:
                if self._in_game(sp) or (sp.keys_menu is not None and sp.keys_menu.waits is not None):
                    sp.repeat.stop()
                else:
                    self._menu_press(sp, key, None, repeats=True)
            self._events_fetch(sp)
            audio = sp.process.audio_fetch()
            if self.mixer is not None and sp.audio:
                for data in audio:
                    self.mixer.feed(sp.nr, data)
            if not sp.crashed and not sp.process.alive:
                sp.crashed = True
                if self.mixer is not None:
                    self.mixer.clear(sp.nr)
            locked = bool(sp.pauses) or global_pause
            next_ = locked and not global_pause and self.plugins.runs_in_menu(sp.nr)
            pause = global_pause or (locked and not next_)
            if pause != sp.sent_pause:
                sp.process.pause(pause)
                sp.sent_pause = pause
            sp.process.input(0 if locked or sp.touch_cross else sp.control.mask)
            if sp.control.fast and (reason := self.plugins.fast_forward_locked(sp.nr)) is not None:
                sp.control.fast = False
                sp.report(reason or t("game.fast_forward_locked"))
            fast_forward = sp.control.fast_forward and not pause
            if fast_forward != sp.fast_forward:
                sp.process.tempo(factor if fast_forward else 1)
                sp.fast_forward = fast_forward
            if sp.system == "nds":
                self._touch(sp, pause, dt)
            new = sp.process.image()
            if new is not None:
                sp.raw_image = new
                self._scale(i)
        if self.output is not None:
            self.output.refill()
        self.plugins.all_("update", dt)

        if self.state == "playing":
            if not global_pause:
                self.playtime += dt
            self.autosave_rest -= dt
            if self.autosave_rest <= 0:
                self.autosave()
                self.autosave_rest = self.app.settings.autosave_minutes * 60
        elif self.state == "saving":
            done = all(self.memory_jobs[sp.nr] in sp.process.saved_ids
                         for sp in self.player if sp.nr in self.memory_jobs)
            if done or time.monotonic() > self.save_until:
                self._finish()

    def draw(self, area) -> None:
        """Draws all players, menus, labels, overlay and the free field."""
        now = time.monotonic()
        for i, cell in enumerate(self.cells):
            if i >= len(self.player):
                self._draw_free_cell(area, cell)
                continue
            sp = self.player[i]
            range_ = self._game_area(i)
            pixel = max(14, min(cell.cell.w, cell.cell.h) // 20)
            for target, source in self._screens(i):
                image = sp.images.get(source)
                if image is not None and image.get_size() == target.size:
                    area.blit(image, target)
                else:
                    pygame.draw.rect(area, (0, 0, 0), target)
            if self.ds:
                self._draw_ds_frame(area, i, sp)
            self._draw_plugins_game_frame(area, i, sp)
            self._draw_label(area, cell, sp, pixel, range_)
            if not sp.images and not sp.crashed:
                graphics.spinner(area, (range_.centerx, range_.centery - pixel), pixel, self.time)
                graphics.text(area, t("game.starts"), (range_.centerx, range_.centery + pixel), pixel,
                            graphics.DIMMED,
                            "midtop", weight="Medium")
            if sp.crashed:
                self._message(area, range_, t("game.crashed"), t("game.crashed_hint"), pixel,
                              graphics.ERROR)
            elif "controller" in sp.pauses:
                title = t("menu.controller_switch" if sp.released else "game.controller_separated")
                self._message(area, range_, title, t("game.free_controller"), pixel, graphics.WARNING)
            elif sp.menu is not None:
                self._draw_player_menu(area, range_, sp, pixel)
            elif sp.keys_menu is not None:
                sp.keys_menu.draw(area, range_, pixel, now)
            elif sp.profile_input is not None:
                graphics.dim(area, range_, 205)
                margin = max(6, pixel // 3)
                panel = range_.inflate(-2 * margin, -2 * margin)
                graphics.panel(area, panel)
                draw_name_input(area, panel.inflate(-pixel, -pixel // 2), pixel, sp.nr,
                                      t("assignment.profile_name"), sp.profile_input, self.time,
                                      t("assignment.profile_example"))
            elif sp.types_open:
                sp.types.draw(area, range_, pixel, self.time)
            elif self.ds:
                self._draw_cursor(area, i, sp, now)
            if sp.hint and now < sp.hint_until:
                self._toast(area, range_, sp.hint, pixel)
        if self.state == "saving":
            def g(n):
                """Scales a base size to the screen."""
                return graphics.size(area, n)

            graphics.dim(area, area.get_rect())
            rect = pygame.Rect(0, 0, g(520), g(200))
            rect.center = area.get_rect().center
            graphics.panel(area, rect)
            graphics.spinner(area, (rect.x + g(90), rect.centery), g(26), self.time)
            graphics.text(area, t("game.save"), (rect.x + g(150), rect.centery), g(44), graphics.TEXT, "midleft",
                        weight="Bold")

    def _draw_plugins_game_frame(self, area, i: int, sp: _Player) -> None:
        """Lets plugins draw over each visible game frame, clipped to its rectangle."""
        old_crop = area.get_clip()
        for target, source in self._screens(i):
            image = sp.images.get(source)
            if image is not None and image.get_size() == target.size:
                area.set_clip(target)
                self.plugins.draw_game_frame(area, sp.nr, target, source)
        area.set_clip(old_crop)

    def _draw_ds_frame(self, area, i: int, sp: _Player) -> None:
        """Draws the two DS screens of a player."""
        if self.view == "hybrid":
            small = self._screens(i)[1][0]
            color = graphics.player_color(sp.nr)
            area.blit(graphics.rounded_rect((small.width + 6, small.height + 6), 8, (0, 0, 0, 0), 3, (*color, 170)),
                         (small.x - 3, small.y - 3))
        else:
            top = self._screens(i)[0][0]
            pygame.draw.line(area, (0, 0, 0), (top.left, top.bottom), (top.right - 1, top.bottom), 2)

    def _draw_cursor(self, area, i: int, sp: _Player, now: float) -> None:
        """Draws the DS touch cursor."""
        bottom = self._bottom(i)
        if bottom is None or not (sp.touch_cross or sp.touch or now < sp.cursor_until):
            return
        x = bottom.x + round(sp.cursor[0] * bottom.width / layout.DS_W)
        y = bottom.y + round(sp.cursor[1] * bottom.height / layout.DS_H)
        r = max(6, bottom.width // 40)
        color = graphics.player_color(sp.nr)
        pygame.draw.circle(area, (0, 0, 0), (x, y), r + 2, 3)
        if sp.touch:
            pygame.draw.circle(area, color, (x, y), r)
        pygame.draw.circle(area, color, (x, y), r, 3)

    def _draw_player_menu(self, area, game: pygame.Rect, sp: _Player, pixel: int) -> None:
        """Draws the player menu over the game area."""
        graphics.dim(area, game, 170)
        self._draw_main_menu(area, game, sp, pixel)

    def _menu_layout(self, sp: _Player) -> list[tuple[str, int | str]]:
        """Order in the player menu: ("row", index), ("group", text), ("question", language key) or ("gap", "");
        confirmation, "Rebind" and "Plugins" share the same layout."""
        if sp.menu_question:
            question = "menu.question_profile" if sp.menu_question == "profile" else "menu.question_save"
            return [("question", question), ("row", 0), ("row", 1)]
        if sp.submenu == "plugins":
            return PluginMenu.layout(sp)
        if sp.submenu:
            return [("group", t("menu.new_bind")), ("row", 0), ("row", 1)]
        layout, group = [], None
        for i, action in enumerate(sp.menu_actions):
            new = MENU_GROUPS.get(action)
            if action == "end":
                layout.append(("gap", ""))
            elif new is not None and new != group:
                layout.append(("group", t(new)))
            group = new
            layout.append(("row", i))
        return layout

    def _menu_size(self, sp: _Player, game: pygame.Rect, pixel: int) -> int:
        """Largest font size (at most pixel) at which the whole menu fits into the game area; remembered per layout."""
        key = (tuple(sp.menu_actions), tuple(sp.menu.entries), sp.menu_question, sp.submenu, game.size,
                      pixel, language_current(), tuple(e.reason for _, e, _ in sp.plugin_rows))
        if getattr(sp, "menu_mass", (None,))[0] == key:
            return sp.menu_mass[1]
        layout = self._menu_layout(sp)
        for p in range(pixel, 9, -1):
            height = self._menu_height(layout, p)
            if height <= game.height - 8 and self._layout_width(sp, layout, p) + 2 * p <= game.width - 8:
                break
        sp.menu_mass = (key, p)
        return p

    @staticmethod
    def _menu_height(layout, p: int) -> int:
        """Height of the menu for a font size, including header and legend."""
        height = round(p * 2.6) + round(p * 2.0)
        for kind, _ in layout:
            height += {"row": round(p * 1.95) + round(p * 0.3), "group": round(p * 1.25), "gap": round(p * 0.5),
                      "question": round(p * 2.0)}[kind]
        return height + p

    def _layout_width(self, sp: _Player, layout, p: int) -> int:
        """Widest content: rows including their control, the confirmation in bold."""
        widths = [self._row_width(sp, i, p) for kind, i in layout if kind == "row"]
        widths += [graphics.load_font(round(p * 1.05), "Bold").size(t(k))[0] + p for kind, k in layout if kind == "question"]
        return max(widths)

    def _row_width(self, sp: _Player, i: int, p: int) -> int:
        """Space for label and control of row i."""
        load_font, action = graphics.load_font(p, "SemiBold"), sp.menu_actions[i]
        width = load_font.size(sp.menu.entries[i])[0] + round(p * 1.8)
        if action == "plugin":
            width += PluginMenu.extra_width(sp, i, p)
        elif action in ("audio", "music"):
            width += round(p * 9.5)
        elif action == "view":
            width += sum(load_font.size(t(f"view.{a}"))[0] + p for a in ("hybrid", "columns")) + p
        elif action == "cross":
            width += round(p * 3.6)
        if action in ("music", "view"):
            width += graphics.load_font(round(p * 0.62), "Medium").size(t("menu.all"))[0] + p // 2
        return width

    def _draw_main_menu(self, area, game: pygame.Rect, sp: _Player, pixel: int) -> None:
        """Draws the player menu with groups: audio (slider), screen (toggle, switch) and more; save is shown greyed out,
        and the confirmation before saving and quitting works the same way."""
        p = self._menu_size(sp, game, pixel)
        layout = self._menu_layout(sp)
        width = self._layout_width(sp, layout, p) + 2 * p
        width = min(game.width - 8, max(width, p * 18))
        rect = pygame.Rect(0, 0, width, min(game.height - 8, self._menu_height(layout, p)))
        rect.center = game.center
        graphics.panel(area, rect)
        y = rect.y + round(p * 1.4)
        badge_rect = graphics.badge(area, (rect.x + p, y), sp.nr, round(p * 0.95))
        graphics.text(area, graphics.shorten(sp.game_name, round(p * 1.05), rect.right - badge_rect.right - p * 2, "Bold"),
                    (badge_rect.right + p // 2, y + 1), round(p * 1.05), graphics.TEXT, "midleft", weight="Bold")
        y = rect.y + round(p * 2.6)
        for kind, value in layout:
            if kind == "group":
                graphics.text(area, graphics.shorten(value, round(p * 0.62), rect.width - 2 * p, "SemiBold"),
                            (rect.x + p + p // 4, y + round(p * 0.75)), round(p * 0.62), graphics.DIMMED, "midleft",
                            weight="SemiBold")
                y += round(p * 1.25)
            elif kind == "question":
                graphics.text(area, graphics.shorten(t(value), round(p * 1.05), rect.width - 2 * p, "Bold"),
                            (rect.x + p + p // 4, y + round(p * 0.95)), round(p * 1.05), graphics.WARNING, "midleft",
                            weight="Bold")
                y += round(p * 2.0)
            elif kind == "gap":
                y += round(p * 0.5)
            else:
                row = pygame.Rect(rect.x + p, y, rect.width - 2 * p, round(p * 1.95))
                self._draw_menu_row(area, row, sp, value, p)
                y += row.height + round(p * 0.3)
        legend = [("A", t("hint.select")), ("B", t("hint.back"))]
        if not sp.menu_question and not sp.submenu:
            legend.insert(1, ("<>", t("hint.change")))
        graphics.button_row(area, (rect.centerx, rect.bottom - round(p * 1.25)), legend, round(p * 0.9), round(p * 0.6),
                          p, rect.width - 2 * p)

    def _draw_menu_row(self, area, row: pygame.Rect, sp: _Player, i: int, p: int) -> None:
        """Draws one row of the player menu."""
        action, chosen = sp.menu_actions[i], i == sp.menu.selection
        radius = row.height // 3
        if chosen:
            graphics.card(area, row, True, radius=radius, glowing=False)
        elif action in ("end", "yes"):
            area.blit(graphics.rounded_rect(row.size, radius, (*graphics.ERROR, 18), 2, (*graphics.ERROR, 150)), row)
        else:
            graphics.card(area, row, False, radius=radius)
        if action == "plugin":
            self.plugin_menu.draw_row(area, row, sp, i, p, chosen)
            return
        color = (255, 255, 255) if chosen else graphics.ERROR if action in ("end", "yes") else graphics.TEXT
        left = graphics.text(area, sp.menu.entries[i], (row.x + round(p * 0.8), row.centery + 1), p, color,
                            "midleft")
        if action in ("music", "view"):
            graphics.text(area, t("menu.all"), (left.right + p // 2, row.centery + 1), round(p * 0.62),
                        (235, 235, 255) if chosen else graphics.DIMMED, "midleft", weight="Medium")
        right = (row.right - round(p * 0.8), row.centery)
        if action in ("audio", "music"):
            percent = sp.volume if action == "audio" else self.app.music.volume
            number = pygame.Rect(0, 0, round(p * 2.4), row.height)
            number.midright = right
            graphics.text(area, str(percent) if percent else t("menu.from"), number.midright, round(p * 0.85),
                        (255, 255, 255) if chosen else graphics.TEXT if percent else graphics.DIMMED, "midright")
            graphics.slider(area, pygame.Rect(number.x - round(p * 6.6), row.centery - p // 5, round(p * 6.2),
                                               max(4, round(p * 0.38))), percent, chosen)
        elif action == "view":
            graphics.toggle(area, right, [t("view.hybrid"), t("view.columns")],
                              0 if self.view == "hybrid" else 1, round(p * 0.75), chosen)
        elif action == "cross":
            graphics.switch(area, right, sp.touch_cross, p, chosen)

    def _symbols(self, sp: _Player) -> list[str]:
        """Status symbols of a player (mute, fast forward, link, pause, controller and those of plugins)."""
        symbols = []
        if not sp.audio:
            symbols.append("mute")
        if sp.fast_forward:
            symbols.append("fast_forward")
        symbols += [s for s in self.plugins.symbols(sp.nr) if s not in symbols]
        if sp.crashed or (sp.pauses and not self.plugins.runs_in_menu(sp.nr)):
            symbols.append("pause")
        if sp.device is None:
            symbols.append("controller")
        return symbols

    def _draw_label(self, area, cell, sp: _Player, pixel: int, range_: pygame.Rect) -> None:
        """Draws the player label (badge, game name, symbols) in the margin."""
        symbols = self._symbols(sp)
        margin = getattr(cell, "free", None) if self.ds else cell.margin
        if self.ds and self.view == "hybrid" and margin is not None:
            self._draw_hybrid_label(area, _rect(margin), sp, symbols)
        elif margin is not None and cell.vertical:
            margin = _rect(margin)
            small = max(12, min(pixel, margin.width // 3))
            badge_rect = graphics.badge(area, (margin.centerx, margin.top + small), sp.nr, small, anchor="midtop")
            r = graphics.text(area, sp.game_name, (margin.centerx, badge_rect.bottom + small // 2), small, graphics.TEXT,
                            "midtop", rotate=True, weight="Medium")
            y, s = r.bottom + small, round(small * 1.1)
            for kind in symbols:
                draw_symbol(area, kind, pygame.Rect(margin.centerx - s // 2, y, s, s))
                y += s + small // 2
        elif margin is not None:
            margin = _rect(margin)
            badge_rect = graphics.badge(area, (margin.left + pixel, margin.centery), sp.nr, pixel)
            r = graphics.text(area, sp.game_name, (badge_rect.right + pixel // 2, margin.centery + 1), pixel, graphics.TEXT,
                            "midleft", weight="Medium")
            x, s = r.right + pixel, round(pixel * 1.1)
            for kind in symbols:
                draw_symbol(area, kind, pygame.Rect(x, margin.centery - s // 2, s, s))
                x += s + pixel // 2
        else:
            small = max(11, pixel * 3 // 4)
            height = round(small * 1.9)
            width = (round(small * 0.85 * 2.4) + small // 2 + small // 3
                      + graphics.load_font(small, "Medium").size(sp.game_name)[0] + len(symbols) * (small + 6) + small)
            pill = pygame.Rect(range_.left + 6, range_.top + 6, width, height)
            area.blit(graphics.rounded_rect(pill.size, height // 2, (14, 12, 30, 190)), pill)
            badge_rect = graphics.badge(area, (pill.left + small // 3, pill.centery), sp.nr, round(small * 0.85))
            r = graphics.text(area, sp.game_name, (badge_rect.right + small // 2, pill.centery + 1), small, graphics.TEXT,
                            "midleft", weight="Medium")
            x = r.right + 6
            for kind in symbols:
                draw_symbol(area, kind, pygame.Rect(x, pill.centery - small // 2, small, small))
                x += small + 6

    def _draw_hybrid_label(self, area, free: pygame.Rect, sp: _Player, symbols: list[str]) -> None:
        """Label in the free area beside or below the small screen: badge, game, symbols and swap hint."""
        pixel = max(12, min(free.height // 9, free.width // 12))
        x, y = free.x + pixel, free.y + round(pixel * 1.6)
        badge_rect = graphics.badge(area, (x, y), sp.nr, pixel)
        graphics.text(area, graphics.shorten(sp.game_name, round(pixel * 1.1), free.right - badge_rect.right - pixel * 2, "Medium"),
                    (badge_rect.right + pixel // 2, y + 1), round(pixel * 1.1), graphics.TEXT, "midleft", weight="Medium")
        y += round(pixel * 2.2)
        s = round(pixel * 1.1)
        for kind in symbols:
            draw_symbol(area, kind, pygame.Rect(x, y - s // 2, s, s))
            x += s + pixel // 2
        if symbols:
            y += round(pixel * 2)
        x = free.x + pixel
        top_large = not sp.swapped
        graphics.text(area, t("game.top_large" if top_large else "game.bottom_large"), (x, y), round(pixel * 0.9),
                    graphics.DIMMED,
                    "midleft", weight="Medium")
        y += round(pixel * 1.7)
        swap = sp.control.binding.keys_for(Function.SWAP)
        if swap:
            short = t(BUTTON_SHORT[swap[0]]) if isinstance(swap[0], Key) else key_name(swap[0])
            r = graphics.button(area, (x, y), short, round(pixel * 1.3))
            graphics.text(area, t("game.swap"), (r.right + pixel // 2, y + 1), round(pixel * 0.9), graphics.DIMMED,
                        "midleft", weight="Medium")
        if sp.touch_cross:
            y += round(pixel * 1.9)
            graphics.text(area, t("game.touch_cross"), (x, y), round(pixel * 0.9), graphics.player_color(sp.nr), "midleft",
                        weight="SemiBold")

    @staticmethod
    def _message(area, game: pygame.Rect, title: str, row: str, pixel: int, color) -> None:
        """Draws a full-frame message with title and row."""
        graphics.dim(area, game, 170)
        needed = graphics.load_font(pixel, "Medium").size(row)[0] + pixel * 3
        rect = pygame.Rect(0, 0, min(game.width - pixel * 2, max(needed, pixel * 16)), round(pixel * 5.2))
        rect.center = game.center
        graphics.panel(area, rect)
        graphics.text(area, title, (rect.centerx, rect.y + round(pixel * 1.7)), round(pixel * 1.3), color, "center",
                    weight="Bold")
        graphics.text(area, graphics.shorten(row, pixel, rect.width - pixel * 2, "Medium"),
                    (rect.centerx, rect.y + round(pixel * 3.6)), pixel, graphics.TEXT, "center", weight="Medium")

    @staticmethod
    def _toast(area, game: pygame.Rect, content: str, pixel: int) -> None:
        """Draws a short notice at the bottom of the frame."""
        width = graphics.load_font(pixel, "Medium").size(content)[0] + pixel * 2
        rect = pygame.Rect(0, 0, min(width, game.width - pixel), round(pixel * 2))
        rect.midbottom = (game.centerx, game.bottom - pixel // 2)
        area.blit(graphics.rounded_rect(rect.size, rect.height // 2, (14, 12, 30, 215), 2, (*graphics.ACCENT2, 160)), rect)
        graphics.text(area, graphics.shorten(content, pixel, rect.width - pixel, "Medium"), rect.center, pixel,
                    graphics.TEXT, "center", weight="Medium")

    def _draw_free_cell(self, area, cell) -> None:
        """Free field (e.g. 3 GBA players): header with session and playtime and the chosen display below."""
        self.field.draw(area, _rect(cell.cell), self.app.settings.free_field, self.time,
                           self.session.name, self.playtime)
