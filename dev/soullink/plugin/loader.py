"""Finds, validates, imports and enables or disables the plugins in the plugins folder."""
from __future__ import annotations

import importlib
import json
import re
import sys
import traceback
import types
from dataclasses import dataclass
from pathlib import Path

from .. import paths, language
from ..config import Settings, save_settings
from .api import API_VERSION, KINDS, Setting, Plugin, PluginApi, error_log

PACKET = "soullink_plugins"
DESCRIPTION = "plugin.json"
ID_PATTERN = re.compile(r"[a-z0-9_]+")
CORE_DISPLAY = "core.session"
ALTERNATING = "alternating"
_JSON_VALUES = (str, int, float, bool)


@dataclass
class PluginInfo:
    """What is known about a plugin without importing it: id, folder, version, author, API level, worker module, licence
    file, name, description, status ("ok", "broken", "incompatible" or "error") and error text."""
    id: str
    dir: Path
    version: str
    author: str
    api: int
    worker: str | None
    license: str | None
    name: str
    description: str
    status: str
    error: str = ""


def _read(file: Path) -> dict:
    """Content of plugin.json; raises ValueError with the reason if the file is missing or invalid."""
    try:
        data = json.loads(file.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ValueError("plugin.json missing") from None
    except (OSError, ValueError) as e:
        raise ValueError(f"plugin.json invalid: {e}") from None
    if not isinstance(data, dict):
        raise ValueError("plugin.json is not an object")
    if not isinstance(data.get("api"), int) or isinstance(data.get("api"), bool):
        raise ValueError('"api" missing or not a number')
    for field in ("version", "author"):
        if not isinstance(data.get(field, ""), str):
            raise ValueError(f'"{field}" is not a text')
    for field in ("worker", "license"):
        if data.get(field) is not None and not isinstance(data[field], str):
            raise ValueError(f'"{field}" is not a text')
    return data


def _text(plugin_id: str, key: str) -> str:
    """Plugin text from its language files, falling back to a default."""
    full = f"{plugin_id}.{key}"
    return language.t(full) if language.present(full) else ""


def id_valid(plugin_id: str) -> bool:
    """True if the folder name is a valid plugin id: only a-z, 0-9 and _, and "core" is reserved for the core (display
    "core.session")."""
    return ID_PATTERN.fullmatch(plugin_id) is not None and plugin_id != "core"


def _info(path: Path) -> PluginInfo:
    """Reads the information of one plugin folder."""
    pid = path.name
    if not id_valid(pid):
        return PluginInfo(pid, path, "", "", 0, None, None, pid, "", "broken",
                          "Folder name is not a valid id (only a-z, 0-9, _; not \"core\")")
    language.plugin_texts(pid, path)
    info = PluginInfo(pid, path, "", "", 0, None, None, _text(pid, "_name") or pid, _text(pid, "_description"),
                      "broken")
    try:
        data = _read(path / DESCRIPTION)
    except ValueError as e:
        info.error = str(e)
        return info
    info.version, info.author, info.api = data.get("version", ""), data.get("author", ""), data["api"]
    info.worker, info.license = data.get("worker"), data.get("license")
    if info.api != API_VERSION:
        info.status, info.error = "incompatible", f"API {info.api}, this program has API {API_VERSION}"
    else:
        info.status = "ok"
    return info


def find(dir: Path) -> list[PluginInfo]:
    """All plugin folders sorted by id; only plugin.json and the language files are read, nothing is imported."""
    try:
        paths_ = [p for p in Path(dir).iterdir() if p.is_dir() and not p.name.startswith((".", "_"))]
    except OSError:
        return []
    return sorted((_info(p) for p in paths_), key=lambda i: i.id)


def _parent_package(plugin_dir: Path) -> None:
    """Synthetic package `soullink_plugins` whose __path__ is the plugin folder (a different folder resets everything)."""
    path = str(Path(plugin_dir))
    packet = sys.modules.get(PACKET)
    if packet is None or list(getattr(packet, "__path__", [])) != [path]:
        for name in [n for n in list(sys.modules) if n.startswith(PACKET + ".")]:
            del sys.modules[name]
        packet = types.ModuleType(PACKET)
        packet.__path__ = [path]
        sys.modules[PACKET] = packet
    importlib.invalidate_caches()


def import_(plugin_dir: Path, module: str):
    """Imports the module `soullink_plugins.<module>` (e.g. "<id>" or "<id>.worker") from the plugin folder."""
    _parent_package(plugin_dir)
    return importlib.import_module(f"{PACKET}.{module}")


def import_without_init(plugin_dir: Path, plugin_id: str, module: str):
    """For the worker: imports `soullink_plugins.<id>.<module>` without running the plugin's __init__.py, using an empty
    package for the id."""
    _parent_package(plugin_dir)
    name = f"{PACKET}.{plugin_id}"
    if name not in sys.modules:
        packet = types.ModuleType(name)
        packet.__path__ = [str(Path(plugin_dir) / plugin_id)]
        packet.__package__ = name
        sys.modules[name] = packet
    return importlib.import_module(f"{name}.{module}")


def field_display(value: str, show: list[str]) -> str:
    """What the free field shows: the stored value if it exists, otherwise (empty or plugin off) the first display of a
    plugin."""
    if value in (CORE_DISPLAY, ALTERNATING) or value in show:
        return value
    return show[0] if show else CORE_DISPLAY


def _setting_ok(e) -> bool:
    """True for a known kind and values that fit settings.json; selection and number need their allowed values."""
    if not isinstance(e, Setting) or e.kind not in KINDS or not isinstance(e.values, tuple):
        return False
    if e.kind == "switch":
        return isinstance(e.default, bool)
    if not e.values:
        return False
    if e.kind == "number":
        return all(isinstance(w, (int, float)) and not isinstance(w, bool) for w in (e.default, *e.values))
    return e.default in e.values and all(isinstance(w, _JSON_VALUES) for w in e.values)


def _settings_check(list_) -> list[Setting]:
    """Validates a plugin's settings list and raises ValueError for an invalid one."""
    list_ = list(list_)
    wrong = [e for e in list_ if not _setting_ok(e)]
    if wrong:
        raise ValueError(f"invalid setting: {wrong[0]!r}")
    return list_


class Plugins:
    """The plugins in the data directory: the list for the main menu, on/off state (settings.json) and the loaded plugins;
    nothing disabled is ever executed."""

    def __init__(self, base: Path, settings: Settings):
        """Reads the plugin folder and imports the plugins that are enabled."""
        self.base = Path(base)
        self.settings = settings
        self.dir = paths.plugin_dir(self.base)
        self.infos: list[PluginInfo] = []
        self.state = 0
        self._loaded: dict[str, tuple[Plugin, PluginApi]] = {}
        self._error: dict[str, str] = {}
        self.running_session = None
        self.new_read()

    def new_read(self) -> None:
        """Re-reads the folder (new, changed, deleted plugins) and imports enabled plugins that are not loaded yet."""
        old = {i.id for i in self.infos}
        self.infos = find(self.dir)
        found = {i.id: i for i in self.infos}
        for pid in old - set(found):
            language.plugin_texts(pid, None)
        for pid in [p for p in self._loaded if p not in found or found[p].status != "ok"]:
            del self._loaded[pid]
        for pid in [p for p in self._error if p not in found]:
            del self._error[pid]
        for info in self.infos:
            if info.status == "ok" and info.id in self._error:
                info.status, info.error = "error", self._error[info.id]
            elif info.status == "ok" and self.enabled(info.id) and info.id not in self._loaded:
                self._load(info)

    def info(self, plugin_id: str) -> PluginInfo | None:
        """Info about a plugin; None if unknown."""
        return next((i for i in self.infos if i.id == plugin_id), None)

    def enabled(self, plugin_id: str) -> bool:
        """True if the plugin is switched on."""
        return self.settings.plugins.get(plugin_id) is True

    def set_(self, plugin_id: str, on: bool) -> None:
        """Switches a plugin on or off, remembers it in settings.json and imports it immediately when switched on."""
        self.settings.plugins[plugin_id] = bool(on)
        save_settings(self.base, self.settings)
        if not on:
            self._loaded.pop(plugin_id, None)
            return
        info = self.info(plugin_id)
        if info is not None and info.status in ("ok", "error") and plugin_id not in self._loaded:
            self._error.pop(plugin_id, None)
            info.status, info.error = "ok", ""
            self._load(info)

    def active(self) -> list[tuple[PluginInfo, Plugin]]:
        """Enabled, imported and healthy plugins sorted by id."""
        return [(i, self._loaded[i.id][0]) for i in self.infos
                if i.status == "ok" and self.enabled(i.id) and i.id in self._loaded]

    def api(self, plugin_id: str) -> PluginApi | None:
        """The API object of a loaded plugin; None if not loaded."""
        entry = self._loaded.get(plugin_id)
        return entry[1] if entry else None

    def _load(self, info: PluginInfo) -> None:
        """Imports a plugin and creates its object; a failure disables it and is logged."""
        api = PluginApi(info.id, info.dir, self.base, self.settings)
        try:
            plugin = import_(self.dir, info.id).create(api)
            if not isinstance(plugin, Plugin):
                raise TypeError(f"create(api) returned {type(plugin).__name__} instead of a plugin")
        except (Exception, SystemExit):
            self._disable(info.id, traceback.format_exc())
            return
        self._loaded[info.id] = (plugin, api)
        for _ in range(2):
            self.settings_of(info.id)

    def _disable(self, plugin_id: str, text: str) -> None:
        """Logs the error; the plugin stays off until the next enable or program start."""
        error_log(self.base, plugin_id, text)
        rows = text.strip().splitlines()
        self._error[plugin_id] = rows[-1] if rows else "?"
        self._loaded.pop(plugin_id, None)
        module = f"{PACKET}.{plugin_id}"
        for name in [n for n in list(sys.modules) if n == module or n.startswith(module + ".")]:
            del sys.modules[name]
        info = self.info(plugin_id)
        if info is not None:
            info.status, info.error = "error", self._error[plugin_id]
        self.state += 1

    def safe(self, plugin_id: str, call, default=None):
        """Runs call(plugin) for a loaded, enabled plugin; an exception disables it (error.log) and returns the default, as
        for a disabled plugin."""
        entry = self._loaded.get(plugin_id)
        if entry is None or not self.enabled(plugin_id):
            return default
        try:
            return call(entry[0])
        except Exception:
            self._disable(plugin_id, traceback.format_exc())
            return default

    def settings_of(self, plugin_id: str) -> list[Setting]:
        """Validated main-menu settings of a loaded plugin; also remembers them for api.setting()."""
        api = self.api(plugin_id)

        def fetch(plugin) -> list[Setting]:
            """Reads and validates the settings from the plugin."""
            list_ = _settings_check(plugin.settings())
            api._definitions = {e.key: e for e in list_}
            return list_

        return self.safe(plugin_id, fetch, [])

    def value(self, plugin_id: str, key: str):
        """Current value of a plugin setting."""
        api = self.api(plugin_id)
        return self.safe(plugin_id, lambda p: api.setting(key)) if api else None

    def value_set(self, plugin_id: str, key: str, value, save: bool = True) -> None:
        """Stores a plugin setting (plugin_values); save=False postpones writing settings.json."""
        values = self.settings.plugin_values.get(plugin_id)
        if not isinstance(values, dict):
            values = self.settings.plugin_values[plugin_id] = {}
        values[key] = value
        if save:
            save_settings(self.base, self.settings)

    def show(self) -> list[tuple[str, str]]:
        """("<id>.<display>", title) of all displays of active plugins for the free field."""
        def fetch(plugin) -> list[tuple[str, str]]:
            """Reads the display names from the plugin."""
            return [(str(a), str(title)) for a, title in plugin.display_names()]

        return [(f"{info.id}.{a}", title) for info, _ in self.active() for a, title in self.safe(info.id, fetch, [])]
