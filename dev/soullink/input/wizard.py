"""Binding wizard for unknown controllers: asks for the keys one after another."""
from __future__ import annotations

from .keys import Key

STEPS = (
    Key.UP,
    Key.DOWN,
    Key.LEFT,
    Key.RIGHT,
    Key.SOUTH,
    Key.EAST,
    Key.WEST,
    Key.NORTH,
    Key.L,
    Key.R,
    Key.START,
    Key.SELECT,
)


class BindingWizard:
    """Collects one raw input source per requested key."""

    def __init__(self):
        """Starts with no key recorded."""
        self._result: dict[str, dict] = {}

    @property
    def current(self) -> Key | None:
        """The key being asked for now; None when all are done."""
        step = len(self._result)
        return STEPS[step] if step < len(STEPS) else None

    def event(self, source: dict) -> bool:
        """Accepts the source for the current step; True once all keys are bound."""
        key = self.current
        if key is not None and source not in self._result.values():
            self._result[key.name] = dict(source)
        return self.current is None

    @property
    def result(self) -> dict:
        """The recorded binding {key name: source}."""
        return dict(self._result)
