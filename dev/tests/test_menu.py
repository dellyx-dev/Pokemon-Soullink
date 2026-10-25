"""Tests of the selection menu."""

from soullink.input.keys import Key
from soullink.ui.menu import BACK, Menu


def test_navigation_wraps_around():
    """Menu navigation wraps around."""
    m = Menu(["a", "b", "c"])
    m.event(Key.DOWN)
    m.event(Key.DOWN)
    assert m.selection == 2
    m.event(Key.DOWN)
    assert m.selection == 0
    m.event(Key.UP)
    assert m.selection == 2


def test_confirm_and_back():
    """Confirm returns the index and back returns BACK."""
    m = Menu(["a", "b"])
    assert m.event(Key.SOUTH) == 0
    assert m.event(Key.SOUTH) == 0
    assert m.event(Key.START) == 0
    assert m.event(Key.SELECT) == BACK
    assert m.event(Key.EAST) == BACK
    assert m.event(Key.L) is None


def test_empty_menu():
    """An empty menu does nothing."""
    m = Menu([])
    assert m.event(Key.DOWN) is None
    assert m.event(Key.SOUTH) is None
    assert m.event(Key.SELECT) == BACK
