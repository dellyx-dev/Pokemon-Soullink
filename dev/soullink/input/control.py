"""Key state of a player in the game: joypad mask, fast forward and player menu, through the player's key binding."""
from __future__ import annotations

from .keys import Key
from .key_binding import JOYPAD_BIT, Function, KeyBinding


class PlayerControl:
    """Evaluates the pressed keys of one player through the binding."""

    def __init__(self, binding: KeyBinding | None = None):
        """Creates the control with a binding, the default if none is given."""
        self.binding = binding or KeyBinding()
        self._pressed: set[Key] = set()
        self.fast = False

    def event(self, key: Key, pressed: bool) -> str | None:
        """Records a key press or release (pressing the fast-forward key toggles fast forward) and returns "menu" when the
        menu key is pressed, else None."""
        if pressed:
            if key not in self._pressed and self.binding.function(key) == Function.FAST_FORWARD:
                self.fast = not self.fast
            self._pressed.add(key)
        else:
            self._pressed.discard(key)
        return "menu" if pressed and self.binding.function(key) == Function.MENU else None

    def _functions(self) -> set[Function]:
        """Functions of all currently pressed keys."""
        return {f for f in map(self.binding.function, self._pressed) if f is not None}

    @property
    def mask(self) -> int:
        """Joypad button mask for the core."""
        mask = 0
        for function in self._functions():
            if function in JOYPAD_BIT:
                mask |= 1 << JOYPAD_BIT[function]
        return mask

    @property
    def fast_forward(self) -> bool:
        """True while fast forward is switched on."""
        return self.fast

    def holds(self, key: Key) -> bool:
        """True if the key is pressed."""
        return key in self._pressed

    def holds_function(self, function: Function) -> bool:
        """True if a key with this function is pressed."""
        return function in self._functions()

    def release(self) -> None:
        """Releases all keys."""
        self._pressed.clear()
