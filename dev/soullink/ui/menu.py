"""Selection menu operable with any controller and the keyboard."""
from __future__ import annotations

from ..input.keys import CONFIRM, BACK_KEYS, Key

BACK = "back"
REPEAT_DELAY, REPEAT_INTERVAL = 0.35, 0.12
REPEAT_CLOCK = {"list": (0.05, 0.04), "slider": (0.03, 0.08)}


class Repeater:
    """Remembers the held key; due() returns it once the next repeat is due."""

    def __init__(self):
        """Starts with no key held."""
        self.key: Key | None = None
        self.since = self.next_ = 0.0
        self.kind = "list"

    def start(self, key: Key, now: float, kind: str = "list") -> None:
        """Starts repeating a held key of the given kind."""
        self.key, self.since, self.next_, self.kind = key, now, now + REPEAT_DELAY, kind

    def stop(self, key: Key | None = None) -> bool:
        """Releases the held key (only that key) or any key when none is given; True if something was held."""
        if self.key is None or (key is not None and key != self.key):
            return False
        self.key = None
        return True

    def due(self, now: float) -> Key | None:
        """The key if its next repeat is due now, else None."""
        if self.key is None or now < self.next_:
            return None
        shortest, acceleration = REPEAT_CLOCK[self.kind]
        clock = REPEAT_INTERVAL - acceleration * (now - self.since - REPEAT_DELAY)
        self.next_ = now + max(shortest, clock)
        return self.key


class Menu:
    """List of entries with a selection that wraps around."""

    def __init__(self, entries: list[str]):
        """Creates the menu with its entries."""
        self.entries = list(entries)
        self.selection = 0

    def event(self, key: Key) -> int | str | None:
        """Index of the entry on confirm (A), BACK on B/Select, else None."""
        if key in BACK_KEYS:
            return BACK
        if not self.entries:
            return None
        if key == Key.UP:
            self.selection = (self.selection - 1) % len(self.entries)
        elif key == Key.DOWN:
            self.selection = (self.selection + 1) % len(self.entries)
        elif key in CONFIRM or key == Key.START:
            return self.selection
        return None
