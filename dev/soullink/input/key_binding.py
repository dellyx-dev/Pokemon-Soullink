"""Own key binding per player: which key (by position) triggers which function."""
from __future__ import annotations

import functools
import json
import warnings
from enum import Enum, auto
from pathlib import Path

import pygame

from .. import paths
from ..language import t
from .keys import Key, keys_name


class Function(Enum):
    """Functions a key can trigger in the game; X and Y exist only on the DS, fast forward is a toggle and menu opens the
    player menu on a short press and the types overlay when held."""
    A = auto()
    B = auto()
    X = auto()
    Y = auto()
    L = auto()
    R = auto()
    START = auto()
    SELECT = auto()
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    FAST_FORWARD = auto()
    MENU = auto()
    SWAP = auto()
    TOUCH = auto()


GAME_KEYS = frozenset({Function.A, Function.B, Function.X, Function.Y, Function.L, Function.R})
ONLY_DS = frozenset({Function.X, Function.Y, Function.SWAP, Function.TOUCH})


def function_name(function: Function, ds: bool) -> str:
    """Display name of a function in the current language, for DS or GBA labeling."""
    if function in GAME_KEYS:
        return f"{'DS' if ds else 'GBA'}-{function.name}"
    return t(f"function.{function.name.lower()}")


JOYPAD_BIT = {Function.B: 0, Function.Y: 1, Function.SELECT: 2, Function.START: 3, Function.UP: 4,
              Function.DOWN: 5, Function.LEFT: 6, Function.RIGHT: 7, Function.A: 8, Function.X: 9,
              Function.L: 10, Function.R: 11}

def _key_code(name: str) -> int | None:
    """pygame key code for a key name; None if unknown."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return pygame.key.key_code(name)
    except ValueError:
        return None


def _read(path) -> dict:
    """Reads a JSON file; an empty dict if it is missing or invalid."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


@functools.cache
def default_binding(kind: str, system: str) -> dict:
    """Default binding from default-keys.json for the kind "controller" or "keyboard" and the system "gba" or "nds", as
    {key or key code: function}; a custom file in the data directory takes precedence."""
    section = None
    for path in paths.default_keys_files():
        section = _read(path).get(kind, {}).get(system)
        if isinstance(section, dict):
            break
    if not isinstance(section, dict):
        raise RuntimeError(f"{paths.DEFAULT_KEYS}: section {kind}/{system} missing")
    assignment = {}
    for function, keys in section.items():
        if function not in Function.__members__:
            continue
        for name in [keys] if isinstance(keys, str) else keys:
            key = Key[name] if kind == "controller" and name in Key.__members__ else \
                _key_code(name) if kind == "keyboard" else None
            if key is not None:
                assignment[key] = Function[function]
    return assignment


_OLD_NAMES = {"GBA_A": "A", "GBA_W": "B", "GBA_L": "L", "GBA_R": "R"}


class KeyBinding:
    """Maps the position keys of a controller to functions."""

    def __init__(self, assignment: dict[Key, Function] | None = None, ds: bool = False):
        """Creates the binding from an assignment, the default if none is given."""
        self.ds = ds
        self._assignment = dict(self._default if assignment is None else assignment)

    @property
    def _default(self) -> dict[Key, Function]:
        """The default assignment for the system."""
        return default_binding("controller", "nds" if self.ds else "gba")

    def function(self, key: Key) -> Function | None:
        """Function triggered by a key; None if unbound."""
        return self._assignment.get(key)

    def _inputs(self) -> list:
        """All inputs that can be bound."""
        return list(Key)

    def keys_for(self, function: Function) -> list[Key]:
        """Keys bound to a function."""
        return [t for t in self._inputs() if self._assignment.get(t) == function]

    def name(self, input) -> str:
        """Display name of an input."""
        return keys_name(input)

    @property
    def is_default(self) -> bool:
        """True if the binding equals the default."""
        return self._assignment == self._default

    def bind(self, function: Function, key: Key) -> None:
        """Binds the key to the function; a function displaced from the key receives the key that was freed."""
        old_keys = self.keys_for(function)
        displaced = self._assignment.get(key)
        for t in old_keys:
            del self._assignment[t]
        self._assignment[key] = function
        if displaced is not None and displaced != function and old_keys:
            self._assignment[old_keys[0]] = displaced

    def default(self) -> None:
        """Resets to the default binding."""
        self._assignment = dict(self._default)

    def to_dict(self) -> dict[str, str] | None:
        """Serializable form for the profile; None means the default."""
        return None if self.is_default else {t.name: f.name for t, f in self._assignment.items()}

    @classmethod
    def from_dict(cls, data: dict | None, ds: bool = False) -> "KeyBinding":
        """Restores a binding from its serialized form."""
        assignment = {}
        for key, function in (data or {}).items():
            function = _OLD_NAMES.get(function, function)
            if key in Key.__members__ and function in Function.__members__:
                assignment[Key[key]] = Function[function]
        if ds and not {Function.X, Function.Y} & set(assignment.values()):
            assignment = {}
        return cls(assignment or None, ds)


_NAMED = {"space", "return", "backspace", "tab", "escape", "up", "down", "left", "right", "left shift", "right shift",
            "left ctrl", "right ctrl", "left alt", "right alt", "caps lock", "delete", "insert", "home", "end",
            "page up", "page down", "enter"}


def key_name(code: int) -> str:
    """Readable name of a keyboard key (pygame code), e.g. "X", "Space" or "Up"."""
    raw = pygame.key.name(code)
    if raw in _NAMED:
        return t("keyboard." + raw.replace(" ", "_"))
    if raw.startswith("[") and raw.endswith("]"):
        return t("keyboard.numpad", key=raw[1:-1])
    return raw.upper() if len(raw) == 1 else raw.capitalize() or t("keyboard.key", code=code)


class KeyboardBinding(KeyBinding):
    """The keyboard as a player: real keys (pygame codes) instead of positions."""

    @property
    def _default(self) -> dict[int, Function]:
        """The default assignment of the keyboard for the system."""
        return default_binding("keyboard", "nds" if self.ds else "gba")

    def _inputs(self) -> list:
        """All keys currently bound."""
        return list(self._assignment)

    def name(self, input) -> str:
        """Display name of a key code."""
        return key_name(input)

    def to_dict(self) -> dict[str, str] | None:
        """Serializable form with pygame key names; None means the default."""
        return None if self.is_default else {pygame.key.name(c): f.name for c, f in self._assignment.items()}

    @classmethod
    def from_dict(cls, data: dict | None, ds: bool = False) -> "KeyboardBinding":
        """Restores a keyboard binding from its serialized form."""
        assignment = {}
        for name, function in (data or {}).items():
            code = _key_code(name)
            if code is not None and function in Function.__members__:
                assignment[code] = Function[function]
        return cls(assignment or None, ds)
