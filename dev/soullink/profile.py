"""Named key profiles for controllers and keyboards, stored in profile.json per game system; a session only remembers
the profile name."""
from __future__ import annotations

import json
from pathlib import Path

from .atomic import atomic_write
from .input.devices import KEYBOARD_ID

FILE = "profile.json"
KINDS = ("controller", "keyboard")
VERSION = 2
MAX_NAME = 12


def kind_of(device: str | None) -> str:
    """Profile kind for a device: the keyboard has its own profiles, all controllers share the others."""
    return "keyboard" if device == KEYBOARD_ID else "controller"


def _migrate(data: dict) -> dict:
    """Converts the old layout (kind, name, system) into the current one (kind, system, name)."""
    new: dict = {}
    for kind in KINDS:
        for name, profile in (data.get(kind) or {}).items() if isinstance(data.get(kind), dict) else ():
            for system, binding in (profile or {}).items() if isinstance(profile, dict) else ():
                new.setdefault(kind, {}).setdefault(str(system), {})[str(name)] = binding
    return new


class Profile:
    """Persistent store of key profiles per kind and game system; a profile belongs to exactly one system."""

    def __init__(self, base: Path):
        """Loads the profiles from the data directory."""
        self.path = Path(base) / FILE
        self._data = self._load()

    def _load(self) -> dict:
        """Reads profile.json, migrating the old layout and dropping malformed entries."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        if data.get("version") != VERSION:
            data = _migrate(data)
        return {kind: {str(system): {str(name): b for name, b in profiles.items() if b is None or isinstance(b, dict)}
                       for system, profiles in data[kind].items() if isinstance(profiles, dict)}
                for kind in KINDS if isinstance(data.get(kind), dict)}

    def save(self) -> None:
        """Writes the profiles atomically."""
        atomic_write(self.path, json.dumps({"version": VERSION, **self._data}, indent=2,
                                           ensure_ascii=False).encode("utf-8"))

    def _profiles(self, kind: str, system: str) -> dict:
        """Profiles of a kind for one system (read only)."""
        return self._data.get(kind, {}).get(system, {})

    def names(self, kind: str, system: str) -> list[str]:
        """Profile names of a kind and system in case-insensitive order."""
        return sorted(self._profiles(kind, system), key=str.casefold)

    def exists(self, kind: str, name: str | None, system: str) -> bool:
        """True if the named profile exists for that kind and system."""
        return name is not None and name in self._profiles(kind, system)

    def binding(self, kind: str, name: str | None, system: str) -> dict | None:
        """Key binding of the profile for the given system; None means the default."""
        if name is None:
            return None
        return self._profiles(kind, system).get(name)

    def free_name(self, kind: str, system: str, wish: str) -> str:
        """Unused profile name derived from the wish, truncated and numbered if needed."""
        base = " ".join(wish.split())[:MAX_NAME] or "Profile"
        name, n = base, 2
        while self.exists(kind, name, system):
            name, n = f"{base[:MAX_NAME - len(str(n)) - 1]} {n}", n + 1
        return name

    def create(self, kind: str, system: str, wish: str, binding: dict | None = None) -> str:
        """Creates a profile for one system with an optional binding and returns its actual unused name."""
        name = self.free_name(kind, system, wish)
        self._data.setdefault(kind, {}).setdefault(system, {})[name] = binding
        self.save()
        return name

    def set_(self, kind: str, name: str, system: str, binding: dict | None) -> None:
        """Stores the binding of a profile for one system and saves."""
        self._data.setdefault(kind, {}).setdefault(system, {})[name] = binding
        self.save()

    def delete(self, kind: str, name: str, system: str) -> None:
        """Removes a profile of one system and saves."""
        profiles = self._profiles(kind, system)
        if name in profiles:
            del profiles[name]
            self.save()
