"""Assignment of devices to players at start, as a state machine."""
from __future__ import annotations

from .devices import KEYBOARD_ID
from .keys import CONFIRM, BACK_KEYS, Key


class Assignment:
    """Assigns each player the device on which a key is pressed first."""

    def __init__(self, count: int):
        """Starts with all players unassigned."""
        self.player: list[str | None] = [None] * count
        self._order: list[int] = []

    @property
    def done(self) -> bool:
        """True when every player has a device."""
        return None not in self.player

    def event(self, device: str, key: Key) -> str | None:
        """Handles a key of a device: a new device joins ("joined"), a joined one can step back ("undo") or start ("start")
        once all players are assigned; otherwise None."""
        if device in self.player:
            if key in BACK_KEYS:
                self.player[self._order.pop()] = None
                return "undo"
            if key is Key.START and self.done:
                return "start"
            return None
        join = key in CONFIRM or (device == KEYBOARD_ID and key is Key.START)
        if not join or self.done:
            return None
        free = self.player.index(None)
        self.player[free] = device
        self._order.append(free)
        return "joined"

    def device_away(self, device: str) -> None:
        """Frees the player of a removed device."""
        if device in self.player:
            position = self.player.index(device)
            self.player[position] = None
            self._order.remove(position)
