"""Plugins in the running game: which ones fit the session, distributing the hooks and catching errors (the plugin is
switched off until a player restarts it from the "Plugins" submenu)."""
from __future__ import annotations

import traceback
from pathlib import Path

from ..image import SYMBOLS
from ..core.memory import SLOT_COUNT
from ..language import t
from .api import MenuEntry, PluginApi, GameApi, error_log
from .loader import PluginInfo

_ERROR = object()


class PluginSession:
    """The active plugins of a game, one per game screen; an exception in a hook (also in tabs, displays, menu entries and
    the worker part) is logged and switches the plugin off until restart()."""

    def __init__(self, active: list[tuple[PluginInfo, object]], session, game_screen):
        """Creates the plugin session for the plugins that fit the session."""
        self.session = session
        self.game = game_screen
        self.base = Path(game_screen.app.base)
        self.plugins: list[tuple[PluginInfo, object]] = list(active)
        self.not_matching: list[tuple[PluginInfo, str]] = []
        self.not_responsible: list[PluginInfo] = []
        self.disabled: list[PluginInfo] = []
        self.restarted: list[PluginInfo] = []
        self.apis: dict[str, GameApi] = {}
        self.changed = False
        self._plugin = {info.id: plugin for info, plugin in active}
        self._info = {info.id: info for info, _ in active}
        self._from: set[str] = set()
        self._ended = False
        self._at_end = False
        self._hints: list[str] = []
        self._reported: set[tuple] = set()
        for info, plugin in active:
            result = self.call(info, "fits", session, default=_ERROR)
            if result is True or result is _ERROR:
                continue
            self.plugins = [(i, p) for i, p in self.plugins if i.id != info.id]
            if result is False:
                self.not_responsible.append(info)
            else:
                self.not_matching.append((info, result if isinstance(result, str) and result
                                           else t("plugin.fits_not")))
        with_worker = [info for info, _ in self.plugins if info.worker]
        self._slots = {info.id: i if i < SLOT_COUNT else None for i, info in enumerate(with_worker)}
        for info in with_worker[SLOT_COUNT:]:
            error_log(self.base, info.id, f"No shared memory slot left (at most {SLOT_COUNT}): "
                                            "worker_data() stays None")

    def active(self, plugin_id: str) -> bool:
        """True while the plugin runs in this game."""
        return plugin_id in self._plugin and plugin_id not in self._from and not self._ended

    def _safe(self, info: PluginInfo, call, default=None):
        """Runs call() for an active plugin; an exception switches it off for the session and returns the default."""
        if not self.active(info.id):
            return default
        try:
            return call()
        except Exception:
            self.disable(info, traceback.format_exc())
            return default

    def call(self, info: PluginInfo, method: str, *args, default=None):
        """Calls a hook of one plugin; an exception is logged, the plugin switched off for the session, a notice shown and
        the default returned."""
        plugin = self._plugin.get(info.id)
        return self._safe(info, lambda: getattr(plugin, method)(*args), default)

    def all_(self, method: str, *args) -> list[tuple[PluginInfo, object]]:
        """Calls a hook of all active plugins (by id); a plugin that raises is missing from the result."""
        results = []
        for info, _ in list(self.plugins):
            result = self.call(info, method, *args, default=_ERROR)
            if result is not _ERROR:
                results.append((info, result))
        return results

    def disable(self, info: PluginInfo, text: str) -> None:
        """Logs the error and switches the plugin (and its worker part) off for the rest of the session; if it had started
        it may still clean up in session_end()."""
        error_log(self.base, info.id, text)
        if info.id in self._from:
            return
        self._from.add(info.id)
        self.disabled.append(info)
        self.restarted = [i for i in self.restarted if i.id != info.id]
        self.plugins = [(i, p) for i, p in self.plugins if i.id != info.id]
        self.changed = True
        self._report(t("plugin.error_session", name=info.name))
        if info.worker:
            for sp in getattr(self.game, "player", []):
                sp.process.plugin_disable(info.id)
        if info.id in self.apis and not self._ended and not self._at_end:
            try:
                self._plugin[info.id].session_end()
            except Exception:
                error_log(self.base, info.id, traceback.format_exc())

    def restart(self, info: PluginInfo) -> bool:
        """Switches a plugin that an error switched off on again: its worker part is loaded anew in every player process
        and session_start() runs again; its tabs and displays come back with the next frame (restarted). Returns True if
        it runs again."""
        if self._ended or info.id not in self._from or info.id not in self._plugin:
            return False
        self._from.discard(info.id)
        self.disabled = [i for i in self.disabled if i.id != info.id]
        order = list(self._info)
        self.plugins = sorted(self.plugins + [(self._info[info.id], self._plugin[info.id])],
                              key=lambda entry: order.index(entry[0].id))
        if info.worker:
            entry = next(e for e in self.worker_plugins() if e["id"] == info.id)
            for sp in getattr(self.game, "player", []):
                sp.process.plugin_enable(entry)
        self.call(info, "session_start", self._api(info))
        if not self.active(info.id):
            return False
        self.restarted.append(info)
        self.changed = True
        return True

    def worker_error(self, plugin_id: str, text: str) -> None:
        """Handles the event ("plugin_error", id, traceback) from a player process."""
        info = self._info.get(plugin_id)
        if info is not None:
            self.disable(info, f"Worker part:\n{text}")

    def _report(self, text: str) -> None:
        """Shows a short notice to the players."""
        player = getattr(self.game, "player", None)
        if not player:
            self._hints.append(text)
            return
        for sp in player:
            sp.report(text)

    def worker_plugins(self) -> list[dict]:
        """Worker parts of active plugins for the job of a player process."""
        return [{"id": info.id, "dir": str(info.dir), "module": info.worker, "slot": self._slots.get(info.id)}
                for info, _ in self.plugins if info.worker]

    def process_group(self) -> bool:
        """True if a plugin demands that all GBA players run in one process (link cable)."""
        return any(result is True for _, result in self.all_("process_group", self.session))

    def start(self) -> None:
        """Calls session_start(GameApi) of each plugin once the players exist; a previous game still running is ended
        first."""
        loader = getattr(self.game.app, "plugins", None)
        previous = getattr(loader, "running_session", None)
        if previous is not None and previous is not self:
            previous.end()
        if loader is not None:
            loader.running_session = self
        for info, _ in list(self.plugins):
            self.call(info, "session_start", self._api(info))
        for text in self._hints:
            self._report(text)
        self._hints = []

    def _api(self, info: PluginInfo) -> GameApi:
        """The GameApi of a plugin, created on first use."""
        if info.id not in self.apis:
            api = getattr(self._plugin[info.id], "api", None)
            if not isinstance(api, PluginApi):
                api = PluginApi(info.id, info.dir, self.base, self.game.app.settings)
            self.apis[info.id] = GameApi(api, self.game, self._slots.get(info.id))
        return self.apis[info.id]

    def save(self) -> None:
        """Calls the save hook of all plugins."""
        self.all_("save")

    def end(self) -> None:
        """Calls session_end() of each plugin exactly once, even if it raises; no hook runs afterwards."""
        if self._ended:
            return
        self._at_end = True
        try:
            self.all_("session_end")
        finally:
            self._at_end, self._ended = False, True
            loader = getattr(self.game.app, "plugins", None)
            if getattr(loader, "running_session", None) is self:
                loader.running_session = None

    def event(self, nr: int, e: tuple) -> None:
        """Distributes an event of a player process; ("plugin", id, ...) goes only to that plugin and worker errors switch
        it off."""
        if e[0] == "plugin_error":
            self.worker_error(e[1], e[2])
        elif e[0] == "plugin":
            info = self._info.get(e[1])
            if info is not None:
                self.call(info, "event", nr, e)
        else:
            self.all_("event", nr, e)

    def menu(self, nr: int) -> list[tuple[PluginInfo, list[MenuEntry]]]:
        """Entries for the "Plugins" submenu per plugin (only plugins that have entries)."""
        def fetch(plugin) -> list[MenuEntry]:
            """Reads and validates the menu entries of the plugin."""
            list_ = list(plugin.player_menu(nr) or [])
            wrong = [e for e in list_ if not isinstance(e, MenuEntry)]
            if wrong:
                raise TypeError(f"player_menu() returned {wrong[0]!r} instead of a MenuEntry")
            return list_

        groups = []
        for info, plugin in list(self.plugins):
            list_ = self._safe(info, lambda: fetch(plugin), [])
            if list_:
                groups.append((info, list_))
        return groups

    def trigger(self, info: PluginInfo, entry: MenuEntry) -> None:
        """Runs the action of a menu entry protected against errors."""
        self._safe(info, entry.trigger)

    def switch(self, info: PluginInfo, entry: MenuEntry) -> bool:
        """Reads the state of a menu entry's switch protected against errors."""
        return bool(self._safe(info, entry.switch, False)) if entry.switch is not None else False

    def _of(self, only: list[PluginInfo] | None) -> list[tuple[PluginInfo, object]]:
        """The active plugins, limited to the ones in only if given."""
        return [(info, plugin) for info, plugin in self.plugins if only is None or info.id in {i.id for i in only}]

    def tab(self, nr: int, only: list[PluginInfo] | None = None) -> list:
        """Overlay tabs of all plugins (or the ones in only) for a player, protected against errors (ProtectedTab)."""
        result = []
        for info, plugin in self._of(only):
            def fetch(plugin=plugin, info=info):
                """Reads the overlay tabs from the plugin and wraps them."""
                return [ProtectedTab(self, info, r) for r in list(plugin.overlay_tab(nr) or [])]

            result += self._safe(info, fetch, [])
        return result

    def tab_discarded(self, tab, reason: str) -> None:
        """Logs once that a tab is missing from the overlay (duplicate id or it replaces the same tab as another)."""
        plugin_id = getattr(tab, "plugin_id", "core")
        if (plugin_id, tab.id, reason) not in self._reported:
            self._reported.add((plugin_id, tab.id, reason))
            error_log(self.base, plugin_id, f'Tab "{tab.id}" not in the overlay: {reason}')

    def show(self, only: list[PluginInfo] | None = None) -> list[tuple[str, str, object]]:
        """("<id>.<display>", title, display) of all plugins (or the ones in only) for the free field, protected against
        errors (ProtectedDisplay)."""
        result = []
        for info, plugin in self._of(only):
            def fetch(plugin=plugin, info=info):
                """Reads the displays from the plugin and wraps them."""
                list_ = []
                for display_id, title in list(plugin.display_names() or []):
                    display = plugin.display(display_id)
                    if display is not None:
                        list_.append((f"{info.id}.{display_id}", str(title), ProtectedDisplay(self, info, display)))
                return list_

            result += self._safe(info, fetch, [])
        return result

    def symbols(self, nr: int) -> list[str]:
        """Symbols of all plugins for the label; unknown ones are dropped (logged once per plugin and symbol)."""
        result = []
        for info, plugin in list(self.plugins):
            for symbol in self._safe(info, lambda: [str(s) for s in plugin.symbols(nr) or []], []):
                if symbol in SYMBOLS:
                    result.append(symbol)
                elif (info.id, "symbol", symbol) not in self._reported:
                    self._reported.add((info.id, "symbol", symbol))
                    error_log(self.base, info.id, f'Unknown symbol "{symbol}" omitted (known: '
                                                    f"{', '.join(SYMBOLS)})")
        return result

    def runs_in_menu(self, nr: int) -> bool:
        """True if a plugin keeps the game running while the menu is open."""
        return any(result is True for _, result in self.all_("runs_in_menu", nr))

    def fast_forward_locked(self, nr: int) -> str | None:
        """Reason why a plugin blocks fast forward ("" for no own text); None if allowed."""
        for _, result in self.all_("fast_forward_allowed", nr):
            if result is False or isinstance(result, str):
                return result or ""
        return None

    def draw_game_frame(self, area, nr: int, target, source: str) -> None:
        """Lets all plugins draw over the game frame."""
        self.all_("draw_game_frame", area, nr, target, source)


class ProtectedTab:
    """Tab of a plugin in the overlay: every call is protected, and after an error it does nothing anymore."""

    def __init__(self, session: PluginSession, info: PluginInfo, tab):
        """Wraps a plugin tab, checking that it has a valid id."""
        if not isinstance(getattr(tab, "id", None), str) or not tab.id:
            raise TypeError(f"Tab {tab!r} has no id")
        if not isinstance(getattr(tab, "position", None), (int, float)):
            raise TypeError(f'Tab "{tab.id}" has no number as position')
        replaced = getattr(tab, "replaced", None)
        if replaced is not None and not isinstance(replaced, str):
            raise TypeError(f'Tab "{tab.id}": replaced is not an id')
        self._session, self._info, self.target = session, info, tab
        self.id, self.position, self.replaced = tab.id, tab.position, replaced
        self.plugin_id = info.id

    @property
    def active(self) -> bool:
        """True while the owning plugin is active."""
        return self._session.active(self.plugin_id)

    def _call(self, name: str, *args, default=None, convert=None):
        """Calls a method of the wrapped tab with error protection, conversion and default."""
        method = getattr(self.target, name, None)
        if method is None:
            return default

        def call():
            """Performs the protected call."""
            result = method(*args)
            return convert(result) if convert is not None else result

        return self._session._safe(self._info, call, default)

    @property
    def ram_interval(self) -> float | None:
        """Seconds between RAM requests wanted by the tab; None if it needs none."""
        def read():
            """Reads the interval from the wrapped tab."""
            value = getattr(self.target, "ram_interval", None)
            return None if value is None else float(value)

        return self._session._safe(self._info, read)

    def title(self, short: bool = False) -> str:
        """Tab title, the id as fallback."""
        return self._call("title", short, default=self.id, convert=str)

    def event(self, key) -> bool:
        """Passes a key to the tab; False if it does not consume it."""
        return self._call("event", key, default=False, convert=bool)

    def draw(self, area, rect, u: int, time: float = 0.0) -> None:
        """Draws the tab."""
        self._call("draw", area, rect, u, time)

    def hints(self) -> list[tuple[str, str]]:
        """Button row of the tab."""
        return self._call("hints", default=[], convert=lambda list_: [(str(k), str(h)) for k, h in list_])

    def keyboard_close(self) -> None:
        """Tells the tab that the on-screen keyboard closes."""
        self._call("keyboard_close")


class ProtectedDisplay:
    """Display of a plugin in the free field, protected like ProtectedTab."""

    def __init__(self, session: PluginSession, info: PluginInfo, display):
        """Wraps a plugin display."""
        self._session, self._info, self.target = session, info, display
        self.plugin_id = info.id

    @property
    def active(self) -> bool:
        """True while the owning plugin is active."""
        return self._session.active(self.plugin_id)

    @property
    def ram_interval(self) -> float | None:
        """Seconds between RAM requests wanted by the display; None if it needs none."""
        def read():
            """Reads the interval from the wrapped display."""
            value = getattr(self.target, "ram_interval", None)
            return None if value is None else float(value)

        return self._session._safe(self._info, read)

    def draw(self, area, rect, u: int, time: float) -> None:
        """Draws the display."""
        self._session._safe(self._info, lambda: self.target.draw(area, rect, u, time))
