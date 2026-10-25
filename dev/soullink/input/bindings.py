"""controller-bindings.json (one binding per SDL GUID) and evaluation of raw joystick states."""
from __future__ import annotations

import json
from pathlib import Path

from ..atomic import atomic_write
from .keys import STICK_THRESHOLD, Key


class Bindings:
    """Key bindings for joysticks SDL does not know as controllers; identical controllers share the GUID."""

    def __init__(self, path: Path):
        """Loads the bindings from the file."""
        self.path = Path(path)
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        """Reads the bindings, falling back to the .bak file."""
        for file in (self.path, self.path.with_name(self.path.name + ".bak")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                return data
        return {}

    def for_(self, guid: str) -> dict | None:
        """Binding for a GUID; None if unknown."""
        return self._data.get(guid)

    def set_(self, guid: str, binding: dict) -> None:
        """Stores and saves the binding for a GUID."""
        self._data[guid] = binding
        text = json.dumps(self._data, indent=2, ensure_ascii=False)
        atomic_write(self.path, text.encode("utf-8"))


class RawState:
    """Buttons, hats and axes of a joystick; axis values are in the SDL range of +-32767."""

    def __init__(self):
        """Starts with nothing pressed."""
        self.buttons: set[int] = set()
        self.hats: dict[int, tuple[int, int]] = {}
        self.axes: dict[int, int] = {}

    def button(self, i: int, pressed: bool) -> None:
        """Records a button press or release."""
        if pressed:
            self.buttons.add(i)
        else:
            self.buttons.discard(i)

    def hat(self, i: int, value) -> None:
        """Records a hat position."""
        self.hats[i] = (int(value[0]), int(value[1]))

    def axis(self, i: int, value: int) -> None:
        """Records an axis value."""
        self.axes[i] = value

    def active(self, source: dict) -> bool:
        """True if the described input source is currently active."""
        type_, index = source.get("type"), source.get("index")
        if type_ == "button":
            return index in self.buttons
        if type_ == "hat":
            x, y = self.hats.get(index, (0, 0))
            should_x, should_y = source["value"]
            return (should_x, should_y) != (0, 0) and should_x in (0, x) and should_y in (0, y)
        if type_ == "axis":
            return self.axes.get(index, 0) * source["direction"] > STICK_THRESHOLD
        return False

    def keys(self, binding: dict) -> set[Key]:
        """Position keys that are active according to the binding."""
        return {
            Key[name]
            for name, source in binding.items()
            if name in Key.__members__ and self.active(source)
        }
