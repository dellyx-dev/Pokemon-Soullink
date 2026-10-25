"""Tests of the in-game key state of a player."""

from soullink.input.control import PlayerControl
from soullink.input.keys import Key


def test_l2_opens_the_menu_and_is_no_game_button():
    """L2 opens the menu and does not count as a game button."""
    s = PlayerControl()
    assert s.event(Key.L2, True) == "menu"
    assert s.mask == 0
    assert s.event(Key.L2, False) is None


def test_mask():
    """The pressed keys produce the expected joypad mask."""
    s = PlayerControl()
    assert s.event(Key.SOUTH, True) is None
    s.event(Key.START, True)
    s.event(Key.RIGHT, True)
    assert s.mask == (1 << 8) | (1 << 3) | (1 << 7)
    s.event(Key.START, False)
    assert s.mask == (1 << 8) | (1 << 7)


def test_r3_toggles_fast_forward():
    """R3 toggles fast forward."""
    s = PlayerControl()
    assert not s.fast_forward
    s.event(Key.STICK_R, True)
    assert s.fast_forward
    assert s.mask == 0
    s.event(Key.STICK_R, True)
    s.event(Key.STICK_R, False)
    assert s.fast_forward
    s.event(Key.STICK_R, True)
    s.event(Key.STICK_R, False)
    assert not s.fast_forward


def test_release():
    """Releasing clears all pressed keys."""
    s = PlayerControl()
    s.event(Key.SOUTH, True)
    s.event(Key.STICK_R, True)
    s.release()
    assert s.mask == 0
    assert s.fast_forward


def test_holds():
    """holds() reports pressed keys."""
    s = PlayerControl()
    s.event(Key.RIGHT, True)
    assert s.holds(Key.RIGHT) and not s.holds(Key.LEFT)
    s.event(Key.RIGHT, False)
    assert not s.holds(Key.RIGHT)
