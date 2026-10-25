"""Settings in the main menu: everything from settings.json (plus the data folder reference) operable with the controller,
in groups (General, Sound, Folders) with the settings of enabled plugins under their own heading."""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Callable, NamedTuple

import pygame

from .. import music, paths, language
from ..config import resolve, save_settings
from ..input.devices import KeysEvent
from ..input.keys import CONFIRM, BACK_KEYS, Key
from ..plugin.api import API_VERSION
from ..plugin.loader import ALTERNATING, CORE_DISPLAY, field_display, id_valid
from ..language import t
from . import graphics
from .app import Screen

DIR = "dir"
VALUE = "value"
REFERENCE = "reference"
PLUGIN = "plugin"
SWITCH, SELECTION, NUMBER = "switch", "selection", "number"


class Row(NamedTuple):
    """One row of the settings screen: key, label, kind and (for plugins) the plugin and its setting."""
    key: str
    label: str
    kind: str
    values: tuple | None = None
    display: Callable | None = None
    plugin: str | None = None
    text: str = ""

    @property
    def title(self) -> str:
        """Displayed label of the row."""
        return self.text or t(self.label)


ROWS = [
    ("language", "once.language", VALUE, None, lambda w: dict(language.available()).get(w, w.upper())),
    ("music_volume", "once.music_volume", VALUE, tuple(range(0, 101)),
     lambda w: t("once.percent", percent=w)),
    ("fast_forward_factor", "once.fast_forward", VALUE, (2, 3, 4, 5, 6, 8), lambda w: t("once.fast_forward_value", factor=w)),
    ("autosave_minutes", "once.autosave", VALUE, (1, 2, 3, 5, 10, 15, 30),
     lambda w: t("once.autosave_value", minutes=f"{w:g}")),
    ("ds_view", "once.ds_view", VALUE, ("hybrid", "columns"), lambda w: t(f"view.{w}")),
    ("free_field", "once.free_field", VALUE, None, None),
    ("rom_dir", "once.gba_roms", DIR, None, None),
    ("rom_dir_nds", "once.nds_roms", DIR, None, None),
    ("presets_dir", "once.presets", DIR, None, None),
    ("sessions_dir", "once.sessions", DIR, None, None),
    ("sound_dir", "once.music_dir", DIR, None, None),
]
GROUPS = {"language": "once.group_general", "music_volume": "once.group_general",
           "fast_forward_factor": "once.group_game", "autosave_minutes": "once.group_game",
           "ds_view": "once.group_game", "free_field": "once.group_game",
           "rom_dir": "once.group_dir", "rom_dir_nds": "once.group_dir",
           "presets_dir": "once.group_dir", "sessions_dir": "once.group_dir",
           "sound_dir": "once.group_dir", "base": "once.group_dir"}
STATUS_TEXT = {"incompatible": ("once.plugin_incompatible", "once.plugin_incompatible_text"),
               "broken": ("once.plugin_broken", "once.plugin_broken_text"),
               "error": ("once.plugin_error", "once.plugin_error_text")}
STATUS_KIND = {"rom_dir": "games", "rom_dir_nds": "games", "presets_dir": "presets",
              "sessions_dir": "sessions", "sound_dir": "title"}


def dir_count(dir: Path, key: str) -> int | None:
    """How much a folder holds (ROMs, presets, sessions, music); None if the folder is missing or unreadable."""
    suffixes = {"rom_dir": {".gba", ".zip"}, "rom_dir_nds": {".nds", ".zip"}, "presets_dir": {".rnqs"},
                "sound_dir": music.SUFFIXES}.get(key)
    try:
        with os.scandir(dir) as entries:
            if key == "sessions_dir":
                return sum(1 for e in entries if e.is_dir() and (Path(e.path) / "session.json").is_file())
            return sum(1 for e in entries if Path(e.name).suffix.lower() in suffixes and e.is_file())
    except OSError:
        return None


def status_text(key: str, count: int | None) -> tuple[str, tuple]:
    """Status of a folder as (text, color): "12 games" (green), "empty" (dimmed) or "folder missing" (red)."""
    if count is None:
        return t("once.status_missing"), graphics.ERROR
    if not count:
        return t("once.status_empty"), graphics.DIMMED
    kind = STATUS_KIND[key]
    return t(f"once.status_{kind}_1" if count == 1 else f"once.status_{kind}", count=count), graphics.OK


def _next(values: tuple, current, step: int):
    """Next value of a selection: text values cycle, numbers stop at the ends."""
    if isinstance(values[0], str):
        i = values.index(current) if current in values else 0
        return values[(i + step) % len(values)]
    i = min(range(len(values)), key=lambda k: abs(values[k] - current))
    return values[max(0, min(len(values) - 1, i + step))]


def path_short(text: str, pixel: int, width: int, weight: str = "Medium") -> str:
    """Shortens a long path at the front (".../Roms/gba"), since the end is what matters."""
    font = graphics.load_font(pixel, weight)
    if font.size(text)[0] <= width:
        return text
    while text and font.size("…" + text)[0] > width:
        text = text[1:]
    return "…" + text


class DirChoice:
    """Browse folders: "use this folder" on top, then ".." and the subfolders, and the drives at the very top."""

    def __init__(self, start: Path | None):
        """Starts browsing at the given folder."""
        self.path: Path | None = None
        self.selection = 0
        self.entries: list[tuple[str, Path | None, str]] = []
        while start is not None and not start.is_dir():
            start = start.parent if start.parent != start else None
        self.open_(start)

    @staticmethod
    def _roots() -> list[Path]:
        """The drive roots."""
        return [Path(d) for d in os.listdrives()]

    def open_(self, path: Path | None) -> None:
        """Shows the contents of a folder (None shows the drives)."""
        self.path, self.selection = path, 0
        if path is None:
            self.entries = [(str(w), w, "dir") for w in self._roots()]
            return
        self.entries = [(t("dir.take"), path, "take"), (t("dir.up"), None, "up")]
        try:
            dir = sorted((p for p in path.iterdir() if p.is_dir() and not p.name.startswith((".", "$"))),
                            key=lambda p: p.name.lower())
        except OSError:
            self.entries.append((t("dir.no_access"), None, "nothing"))
            return
        self.entries += [(p.name, p, "dir") for p in dir[:500]]

    def event(self, key: Key) -> Path | str | None:
        """The chosen folder, "cancel" or None."""
        if key in BACK_KEYS:
            return "cancel"
        step = {Key.UP: -1, Key.DOWN: 1, Key.LEFT: -10, Key.RIGHT: 10}.get(key)
        if step is not None and self.entries:
            self.selection = (self.selection + step) % len(self.entries) if abs(step) == 1 else \
                max(0, min(len(self.entries) - 1, self.selection + step))
            return None
        if key == Key.START and self.path is not None:
            return self.path
        if key not in CONFIRM or not self.entries:
            return None
        text, target, kind = self.entries[self.selection]
        if kind == "take":
            return target
        if kind == "up":
            self.open_(None if self.path.parent == self.path else self.path.parent)
        elif kind == "dir":
            self.open_(target)
        return None


class SettingsScreen(Screen):
    """The settings screen of the main menu."""

    def __init__(self, app):
        """Builds the rows from the settings and the plugins."""
        super().__init__(app)
        self.rows: list[Row] = []
        self.selection = 0
        self.choice: DirChoice | None = None
        self.hint = ""
        self._show: dict[str, str] = {}
        self._state = -1
        self._unsaved = False
        self.app.plugins.new_read()
        self._rows_build()
        self.status: dict[str, int | None] = {}
        self._status_read(list(STATUS_KIND))

    def _rows_build(self) -> None:
        """Builds the core rows, one "Plugins" row per found plugin and the settings of enabled plugins; rebuilt after
        every change while the selection stays on its row."""
        old = self.rows[self.selection].key if self.rows else None
        plugins = self.app.plugins
        own = [Row(f"{info.id}:{e.key}", "", e.kind, e.values, e.display, info.id, e.text)
                  for info, _ in plugins.active() for e in plugins.settings_of(info.id)]
        self._show = dict(plugins.show())
        rows = []
        for row in (Row(*z) for z in ROWS):
            if row.key == "free_field":
                row = row._replace(values=(CORE_DISPLAY, *self._show, ALTERNATING), display=self._field_title)
            rows.append(row)
        if paths.is_built():
            rows.append(Row("base", "once.data_dir", REFERENCE))
        rows += [Row(f"plugin:{info.id}", "", PLUGIN, plugin=info.id, text=info.name) for info in plugins.infos]
        active = {info.id for info, _ in plugins.active()}
        self.rows = rows + [z for z in own if z.plugin in active]
        key = [z.key for z in self.rows]
        self.selection = key.index(old) if old in key else min(self.selection, len(self.rows) - 1)
        self._state = plugins.state

    def _field_title(self, value: str) -> str:
        """Display title of a free-field value."""
        if value == CORE_DISPLAY:
            return t("once.field_session")
        if value == ALTERNATING:
            return t("once.field_alternating")
        return self._show.get(value, value)

    def _current_hold(self) -> None:
        """Rebuilds the rows if a plugin has meanwhile reported an error and switched itself off."""
        if self._state != self.app.plugins.state:
            self._rows_build()

    def _status_read(self, key: list[str]) -> None:
        """Reads the folder status of the given setting keys."""
        for s in key:
            self.status.pop(s, None)
        for s in key:
            path = resolve(self.app.base, str(self._value(s)))
            threading.Thread(target=lambda s=s, path=path: self.status.__setitem__(s, dir_count(path, s)),
                             daemon=True, name=f"dir-status-{s}").start()

    def _value(self, key: str):
        """Current value of a core setting."""
        if key == "base":
            return str(self.app.base)
        if key == "language":
            return language.current()
        if key == "free_field":
            return field_display(self.app.settings.free_field, list(self._show))
        return getattr(self.app.settings, key)

    def _rows_value(self, row: Row):
        """Current value shown for a row."""
        if row.kind == PLUGIN:
            return self.app.plugins.enabled(row.plugin)
        if row.plugin is not None:
            return self.app.plugins.value(row.plugin, row.key.split(":", 1)[1])
        return self._value(row.key)

    def _display_text(self, row: Row, value) -> str:
        """Text for the row's value; a plugin's display function runs protected (on error the plugin is switched off and
        the raw value shown)."""
        if row.display is None:
            return str(value)
        if row.plugin is None:
            return row.display(value)
        return str(self.app.plugins.safe(row.plugin, lambda _: row.display(value), value))

    def _plugin_change(self, row: Row, step: int, save: bool = True) -> None:
        """Switches a plugin on or off (step 0 toggles, -1 off, 1 on) or changes one of its settings; while a key is held
        (save=False) the value is stored only on release."""
        plugins = self.app.plugins
        if row.kind == PLUGIN:
            info = plugins.info(row.plugin)
            if info is not None and info.status in ("ok", "error"):
                plugins.set_(info.id, not plugins.enabled(info.id) if step == 0 else step > 0)
        else:
            current = self._rows_value(row)
            if plugins.api(row.plugin) is None:
                self._rows_build()
                return
            if row.kind == SWITCH:
                new = not current if step == 0 else step > 0
            elif row.kind == SELECTION:
                i = row.values.index(current) if current in row.values else 0
                new = row.values[(i + (step or 1)) % len(row.values)]
            else:
                new = _next(row.values, current, step or 1)
            plugins.value_set(row.plugin, row.key.split(":", 1)[1], new, save)
            self._unsaved = self._unsaved or not save
        self._rows_build()

    def _resave(self) -> None:
        """Stores plugin values changed while a key was held (on release or leaving)."""
        if self._unsaved:
            self._unsaved = False
            self._save()

    def _description(self) -> str:
        """Footer of a plugin row: its description or what is wrong with the plugin."""
        row = self.rows[self.selection]
        info = self.app.plugins.info(row.plugin) if row.kind == PLUGIN else None
        if info is None:
            return ""
        if not id_valid(info.id):
            return t("once.plugin_broken_id")
        if info.status in STATUS_TEXT:
            return t(STATUS_TEXT[info.status][1], api=info.api, expected=API_VERSION)
        return info.description

    def _save(self) -> None:
        """Writes settings.json."""
        save_settings(self.app.base, self.app.settings)

    def _dir_set(self, key: str, dir: Path) -> None:
        """Applies a chosen folder to the setting."""
        if key == "base":
            reference = Path(sys.executable).resolve().parent / paths.REFERENCE
            reference.write_text(str(dir) + "\n", encoding="utf-8")
            self.hint = "once.data_dir_restart"
            return
        try:
            value = str(dir.resolve().relative_to(self.app.base.resolve()))
        except ValueError:
            value = str(dir)
        setattr(self.app.settings, key, value)
        self._save()
        if key == "sound_dir":
            self.app.music_new()
        if key in STATUS_KIND:
            self._status_read([key])

    def _value_change(self, key: str, values: tuple, step: int, save: bool = True) -> None:
        """Changes a core setting by a step; the language cycles through all files of the language folder."""
        if key == "language":
            codes = [k for k, _ in language.available()] or [language.REFERENCE]
            new = _next(tuple(codes), language.current(), step)
            self.app.settings.language = language.set_(new)
            self._save()
            self.app.plugins.new_read()
            self._rows_build()
            return
        if key == "music_volume":
            self.app.volume_change(_next(values, self.app.music.volume, step) - self.app.music.volume,
                                         save)
            return
        setattr(self.app.settings, key, _next(values, self._value(key), step))
        self._save()

    def raw(self, ev) -> None:
        """Handles Escape."""
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if self.choice is not None:
                self.choice = None
            else:
                self._back()

    def repeat_kind(self, key: Key) -> str | None:
        """Held direction: the music slider is fast; selections that cycle (language, DS view) do not repeat."""
        if self.choice is not None or key in (Key.UP, Key.DOWN):
            return "list"
        row = self.rows[self.selection]
        if row.kind == NUMBER:
            return "list"
        if row.kind != VALUE or row.key == "language" or not row.values or isinstance(row.values[0], str):
            return None
        return "slider" if row.key == "music_volume" else "list"

    def leave(self) -> None:
        """Stores a still-held music slider value."""
        self.app.volume_change(0)
        self._resave()

    def event(self, e) -> None:
        """Handles a key."""
        if not isinstance(e, KeysEvent):
            return
        if not e.pressed:
            if e.key in (Key.LEFT, Key.RIGHT):
                self.app.volume_change(0)
                self._resave()
            return
        if self.choice is not None:
            result = self.choice.event(e.key)
            if result == "cancel":
                self.choice = None
            elif isinstance(result, Path):
                self._dir_set(self.rows[self.selection].key, result)
                self.choice = None
            return
        self._current_hold()
        row = self.rows[self.selection]
        key, kind, values = row.key, row.kind, row.values
        direction = {Key.LEFT: -1, Key.RIGHT: 1}.get(e.key, 0)
        if e.key in (Key.UP, Key.DOWN):
            self.selection = (self.selection + (1 if e.key == Key.DOWN else -1)) % len(self.rows)
        elif e.key in BACK_KEYS:
            self._back()
        elif kind in (PLUGIN, SWITCH, SELECTION, NUMBER) and e.key in (Key.LEFT, Key.RIGHT, *CONFIRM):
            self._plugin_change(row, direction, save=not e.repeats)
        elif kind == VALUE and e.key in (Key.LEFT, Key.RIGHT, *CONFIRM):
            self._value_change(key, values, -1 if e.key == Key.LEFT else 1, save=not e.repeats)
        elif (e.key in CONFIRM or e.key == Key.START) and kind in (DIR, REFERENCE):
            self.choice = DirChoice(resolve(self.app.base, str(self._value(key))))

    def _back(self) -> None:
        """Returns to the start screen."""
        from .start import StartScreen

        self.app.switch(StartScreen(self.app))

    def _group(self, row: Row) -> tuple[str, str] | None:
        """(id, heading) of a row's group; settings of a plugin are listed under its name."""
        if row.plugin is not None and row.kind != PLUGIN:
            info = self.app.plugins.info(row.plugin)
            return f"plugin:{row.plugin}", info.name if info else row.plugin
        key = "once.group_plugins" if row.kind == PLUGIN else GROUPS.get(row.key)
        return (key, t(key)) if key else None

    def _layout(self) -> list[tuple[str, int | str]]:
        """Rows top to bottom as ("group", heading), ("plugin_group", plugin name) or ("row", index)."""
        layout, group = [], None
        for i, row in enumerate(self.rows):
            new = self._group(row)
            if new is not None and new[0] != group:
                layout.append(("plugin_group" if new[0].startswith("plugin:") else "group", new[1]))
            group = new[0] if new else None
            layout.append(("row", i))
        return layout

    def draw(self, area) -> None:
        """Draws the settings screen."""
        def g(n):
            """Scales a base size to the screen."""
            return graphics.size(area, n)

        self._current_hold()
        width = min(area.get_width() - g(120), g(1200))
        x = (area.get_width() - width) // 2
        graphics.text(area, t("once.title"), (x, g(110)), g(64), graphics.TEXT, "midleft", weight="ExtraBold")
        if self.choice is not None:
            self._draw_choice(area, pygame.Rect(x, g(170), width, area.get_height() - g(290)), g)
            return
        range_ = pygame.Rect(x, g(160), width, area.get_height() - g(160) - g(130))
        height, gap = g(60), g(10)
        mass = {"row": height + gap, "group": g(46), "plugin_group": g(52)}
        layout, positions, y = self._layout(), [], 0
        for kind, value in layout:
            positions.append(y)
            y += mass[kind]
        total = y
        middle = next(pos for (kind, value), pos in zip(layout, positions) if kind == "row" and value == self.selection)
        offset = max(0, min(middle + height // 2 - range_.height // 2, total - range_.height))
        if total > range_.height:
            graphics.text(area, f"{self.selection + 1} / {len(self.rows)}", (range_.right, g(110)), g(24),
                        graphics.DIMMED, "midright", weight="Medium")
        column = max(graphics.load_font(g(28), "SemiBold").size(z.title)[0] for z in self.rows if z.kind in (DIR, REFERENCE))
        old_clip = area.get_clip()
        area.set_clip(range_.clip(old_clip))
        for (kind, value), pos in zip(layout, positions):
            top = range_.y + pos - offset
            if top + mass[kind] < range_.y or top > range_.bottom:
                continue
            if kind == "group":
                graphics.text(area, graphics.shorten(value, g(22), width - g(16)), (x + g(8), top + g(28)), g(22),
                            graphics.DIMMED, "midleft", weight="SemiBold")
            elif kind == "plugin_group":
                self._draw_plugin_header(area, x, top + g(31), width, value, g)
            elif kind == "row":
                self._draw_row(area, pygame.Rect(x, top, width, height), value, x + g(28) + column + g(40), g)
        area.set_clip(old_clip)
        if self.hint:
            graphics.text(area, t(self.hint), (x, range_.bottom + g(30)), g(26), graphics.WARNING, "midleft",
                        weight="SemiBold")
        elif self._description():
            graphics.text(area, graphics.shorten(self._description(), g(24), width, "Medium"),
                        (x + g(8), range_.bottom + g(30)), g(24), graphics.DIMMED, "midleft", weight="Medium")
        graphics.footer(area, self._foot_hints())

    @staticmethod
    def _draw_plugin_header(area, x: int, middle: int, width: int, name: str, g) -> None:
        """Heading over the settings of a plugin: a gradient "PLUGIN" mark with the plugin name beside it."""
        mark = t("once.plugin_mark")
        pixel = g(20)
        rect = pygame.Rect(0, 0, graphics.load_font(pixel, "ExtraBold").size(mark)[0] + g(26), g(32))
        rect.midleft = (x + g(8), middle)
        area.blit(graphics.gradient_rect(rect.size, rect.height // 2), rect)
        graphics.text(area, mark, (rect.centerx, rect.centery + 1), pixel, (255, 255, 255), "center",
                    weight="ExtraBold")
        graphics.text(area, graphics.shorten(name, g(24), width - rect.width - g(32), "Bold"),
                    (rect.right + g(14), middle + 1), g(24), graphics.TEXT, "midleft", weight="Bold")

    def _foot_hints(self) -> list[tuple[str, str]]:
        """Button hints for the selected row."""
        row = self.rows[self.selection]
        back = ("B", t("hint.back"))
        if row.kind == PLUGIN:
            info = self.app.plugins.info(row.plugin)
            switchable = info is not None and info.status in ("ok", "error")
            return [("A", t("once.on_off")), back] if switchable else [back]
        if row.kind == SWITCH:
            return [("A", t("once.on_off")), back]
        if row.kind in (VALUE, SELECTION, NUMBER):
            return [("<>", t("hint.change")), back]
        return [("A", t("once.dir_choose")), back]

    def _draw_row(self, area, rect: pygame.Rect, i: int, path_x: int, g) -> None:
        """Draws the label on the left and on the right a slider, toggle, switch, "< value >" or a path with the folder
        content."""
        row = self.rows[i]
        key, kind, values, display = row.key, row.kind, row.values, row.display
        chosen = i == self.selection
        info = self.app.plugins.info(row.plugin) if kind == PLUGIN else None
        graphics.card(area, rect, chosen, radius=rect.height // 3, glowing=False)
        if row.plugin is not None and kind != PLUGIN:
            stripe = pygame.Rect(rect.x + g(13), rect.y + g(15), g(5), rect.height - g(30))
            color = (255, 255, 255, 220) if chosen else (*graphics.ACCENT1, 255)
            area.blit(graphics.rounded_rect(stripe.size, stripe.width // 2, color), stripe)
        title = row.title if row.plugin is None else graphics.shorten(row.title, g(28), rect.width * 55 // 100)
        color = graphics.DIMMED if info is not None and info.status in ("incompatible", "broken") else graphics.TEXT
        graphics.text(area, title, (rect.x + g(28), rect.centery + 1), g(28),
                    (255, 255, 255) if chosen else color, "midleft", weight="SemiBold")
        right = (rect.right - g(28), rect.centery)
        bright = (235, 235, 255) if chosen else graphics.DIMMED
        if kind == PLUGIN:
            if info is None:
                return
            status_right = right[0]
            if info.status in ("ok", "error"):
                status_right = graphics.switch(area, right, self.app.plugins.enabled(info.id), g(26), chosen).x - g(24)
            if info.status in STATUS_TEXT:
                red = info.status != "incompatible"
                graphics.text(area, t(STATUS_TEXT[info.status][0]), (status_right, right[1] + 1), g(24),
                            (255, 255, 255) if chosen else graphics.ERROR if red else graphics.DIMMED, "midright",
                            weight="SemiBold")
        elif kind == SWITCH:
            graphics.switch(area, right, bool(self._rows_value(row)), g(26), chosen)
        elif kind in (SELECTION, NUMBER):
            text = graphics.shorten(self._display_text(row, self._rows_value(row)), g(24), rect.width * 35 // 100,
                                  "Medium")
            graphics.text(area, f"‹  {text}  ›" if chosen else text, (right[0], right[1] + 1), g(24), bright,
                        "midright", weight="Medium")
        elif key == "music_volume":
            value = self.app.music.volume
            graphics.text(area, t("once.percent", percent=value), (right[0], right[1] + 1), g(24),
                        (255, 255, 255) if chosen else graphics.TEXT, "midright", weight="SemiBold")
            graphics.slider(area, pygame.Rect(right[0] - g(110) - g(300), rect.centery - g(5), g(300), g(10)), value,
                          chosen)
        elif key == "ds_view":
            graphics.toggle(area, right, [display(w) for w in values], values.index(self._value(key))
                              if self._value(key) in values else 0, g(22), chosen)
        elif kind == VALUE:
            text = graphics.shorten(display(self._value(key)), g(24), rect.width * 45 // 100, "Medium")
            graphics.text(area, f"‹  {text}  ›" if chosen else text, (right[0], right[1] + 1), g(24), bright,
                        "midright", weight="Medium")
        elif kind in (DIR, REFERENCE):
            status_right = right[0]
            if kind == DIR:
                if key in self.status:
                    content, color = status_text(key, self.status[key])
                else:
                    content, color = "…", graphics.DIMMED
                r = graphics.text(area, content, (right[0], right[1] + 1), g(24),
                                (255, 255, 255) if chosen else color, "midright", weight="SemiBold")
                status_right = r.x - g(32)
            path = str(resolve(self.app.base, str(self._value(key))))
            graphics.text(area, path_short(path, g(24), status_right - path_x), (path_x, rect.centery + 1), g(24),
                        bright, "midleft", weight="Medium")

    def _draw_choice(self, area, rect: pygame.Rect, g) -> None:
        """Draws the folder browser."""
        choice = self.choice
        title = self.rows[self.selection].title
        location = str(choice.path) if choice.path is not None else t("dir.drives")
        graphics.text(area, path_short(f"{title}:  {location}", g(28), rect.width, "SemiBold"), (rect.x, rect.y + g(14)),
                    g(28), graphics.ACCENT2, "midleft", weight="SemiBold")
        list_ = pygame.Rect(rect.x, rect.y + g(48), rect.width, rect.height - g(48))
        height = g(54)
        visible = max(1, list_.height // height)
        first = min(max(0, choice.selection - visible // 2), max(0, len(choice.entries) - visible))
        for i in range(first, min(len(choice.entries), first + visible)):
            text, _, kind = choice.entries[i]
            row = pygame.Rect(list_.x, list_.y + (i - first) * height, list_.width, height - g(6))
            chosen = i == choice.selection
            graphics.card(area, row, chosen, radius=row.height // 3, glowing=False)
            color = graphics.OK if kind == "take" and not chosen else (255, 255, 255) if chosen else graphics.TEXT
            graphics.text(area, graphics.shorten(text, g(26), row.width - g(48)), (row.x + g(24), row.centery + 1),
                        g(26), color, "midleft", weight="Bold" if kind == "take" else "Medium")
        graphics.footer(area, [("A", t("dir.open_take")), ("START", t("dir.this")),
                                   ("<>", t("hint.ten_next")), ("B", t("hint.cancel"))])
