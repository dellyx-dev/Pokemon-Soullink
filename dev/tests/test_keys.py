"""Tests of the position keys."""

import pygame
import pytest

from soullink.input.keys import (
    CONFIRM,
    CONTROLLER,
    GBA_BIT,
    STICK_THRESHOLD,
    KEYBOARD,
    BACK_KEYS,
    Key,
    gba_mask,
)


def test_key_order():
    """The key enumeration order is stable."""
    assert [t.name for t in Key] == [
        "UP", "DOWN", "LEFT", "RIGHT", "SOUTH", "EAST",
        "WEST", "NORTH", "L", "R", "START", "SELECT", "STICK_L", "STICK_R", "L2", "R2",
    ]


def test_gba_bits():
    """The GBA button bits are as expected."""
    assert GBA_BIT == {
        Key.SOUTH: 0, Key.SELECT: 2, Key.START: 3, Key.UP: 4, Key.DOWN: 5,
        Key.LEFT: 6, Key.RIGHT: 7, Key.EAST: 8, Key.L: 10, Key.R: 11,
    }


def test_gba_mask():
    """The GBA mask is built from keys."""
    assert gba_mask({Key.SOUTH, Key.START, Key.RIGHT}) == 0b10001001


def test_west_and_north_are_no_game_buttons():
    """West and north keys do not count as game buttons."""
    assert gba_mask({Key.WEST, Key.NORTH}) == 0
    assert gba_mask(set()) == 0


def test_stick_clicks_have_no_gba_bit():
    """Stick clicks have no GBA bit."""
    assert Key.STICK_L not in GBA_BIT and Key.STICK_R not in GBA_BIT
    assert gba_mask({Key.STICK_L, Key.STICK_R}) == 0


@pytest.mark.parametrize("button, key", [
    (pygame.CONTROLLER_BUTTON_A, Key.SOUTH),
    (pygame.CONTROLLER_BUTTON_B, Key.EAST),
    (pygame.CONTROLLER_BUTTON_X, Key.WEST),
    (pygame.CONTROLLER_BUTTON_Y, Key.NORTH),
    (pygame.CONTROLLER_BUTTON_BACK, Key.SELECT),
    (pygame.CONTROLLER_BUTTON_START, Key.START),
    (pygame.CONTROLLER_BUTTON_LEFTSHOULDER, Key.L),
    (pygame.CONTROLLER_BUTTON_RIGHTSHOULDER, Key.R),
    (pygame.CONTROLLER_BUTTON_DPAD_UP, Key.UP),
    (pygame.CONTROLLER_BUTTON_DPAD_DOWN, Key.DOWN),
    (pygame.CONTROLLER_BUTTON_DPAD_LEFT, Key.LEFT),
    (pygame.CONTROLLER_BUTTON_DPAD_RIGHT, Key.RIGHT),
    (pygame.CONTROLLER_BUTTON_LEFTSTICK, Key.STICK_L),
    (pygame.CONTROLLER_BUTTON_RIGHTSTICK, Key.STICK_R),
])
def test_controller_keys_by_position(button, key):
    """Controller keys are mapped by position."""
    assert CONTROLLER[button] is key


def test_controller_has_all_keys():
    """The controller mapping covers all keys."""
    assert set(CONTROLLER.values()) | {Key.L2, Key.R2} == set(Key)


@pytest.mark.parametrize("key_keyboard, key", [
    (pygame.K_UP, Key.UP),
    (pygame.K_DOWN, Key.DOWN),
    (pygame.K_LEFT, Key.LEFT),
    (pygame.K_RIGHT, Key.RIGHT),
    (pygame.K_x, Key.SOUTH),
    (pygame.K_y, Key.EAST),
    (pygame.K_z, Key.EAST),
    (pygame.K_a, Key.L),
    (pygame.K_s, Key.R),
    (pygame.K_RETURN, Key.START),
    (pygame.K_BACKSPACE, Key.SELECT),
    (pygame.K_SPACE, Key.STICK_R),
    (pygame.K_TAB, Key.L2),
    (pygame.K_q, Key.STICK_L),
    (pygame.K_c, Key.WEST),
    (pygame.K_v, Key.NORTH),
])
def test_keyboard(key_keyboard, key):
    """The keyboard mapping is as configured."""
    assert KEYBOARD[key_keyboard] is key


def test_escape_is_not_bound():
    """Escape is not bound to a game function."""
    assert pygame.K_ESCAPE not in KEYBOARD


def test_confirm_keys_and_threshold():
    """Confirm keys and the trigger threshold are correct."""
    assert CONFIRM == {Key.SOUTH} and BACK_KEYS == {Key.EAST, Key.SELECT}
    assert STICK_THRESHOLD == 16000


def test_each_key_has_a_name():
    """Every key has a display name."""
    from soullink.input.keys import keys_name

    names = [keys_name(key) for key in Key]
    assert all(names) and not any(n.startswith("key.") for n in names)
