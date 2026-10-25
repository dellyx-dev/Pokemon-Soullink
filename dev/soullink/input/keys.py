"""Keys by position, GBA button bits and the fixed bindings for controllers and keyboard; the south key is GBA B (bit 1
stays free), the east key GBA A, and west, north and the stick clicks are program keys."""
from __future__ import annotations

from enum import Enum, auto

import pygame

from ..language import t


class Key(Enum):
    """Controller keys by position (d-pad, south/east/west/north, shoulders, sticks and trigger axes L2/R2, start, select)."""
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    SOUTH = auto()
    EAST = auto()
    WEST = auto()
    NORTH = auto()
    L = auto()
    R = auto()
    START = auto()
    SELECT = auto()
    STICK_L = auto()
    STICK_R = auto()
    L2 = auto()
    R2 = auto()


GBA_BIT = {
    Key.SOUTH: 0,
    Key.SELECT: 2,
    Key.START: 3,
    Key.UP: 4,
    Key.DOWN: 5,
    Key.LEFT: 6,
    Key.RIGHT: 7,
    Key.EAST: 8,
    Key.L: 10,
    Key.R: 11,
}


def gba_mask(keys: set) -> int:
    """Joypad bit mask for the GBA from a set of keys."""
    mask = 0
    for key in keys:
        if key in GBA_BIT:
            mask |= 1 << GBA_BIT[key]
    return mask


CONTROLLER = {
    pygame.CONTROLLER_BUTTON_A: Key.SOUTH,
    pygame.CONTROLLER_BUTTON_B: Key.EAST,
    pygame.CONTROLLER_BUTTON_X: Key.WEST,
    pygame.CONTROLLER_BUTTON_Y: Key.NORTH,
    pygame.CONTROLLER_BUTTON_BACK: Key.SELECT,
    pygame.CONTROLLER_BUTTON_START: Key.START,
    pygame.CONTROLLER_BUTTON_LEFTSHOULDER: Key.L,
    pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: Key.R,
    pygame.CONTROLLER_BUTTON_DPAD_UP: Key.UP,
    pygame.CONTROLLER_BUTTON_DPAD_DOWN: Key.DOWN,
    pygame.CONTROLLER_BUTTON_DPAD_LEFT: Key.LEFT,
    pygame.CONTROLLER_BUTTON_DPAD_RIGHT: Key.RIGHT,
    pygame.CONTROLLER_BUTTON_LEFTSTICK: Key.STICK_L,
    pygame.CONTROLLER_BUTTON_RIGHTSTICK: Key.STICK_R,
}

STICK_THRESHOLD = 16000

KEYBOARD = {
    pygame.K_UP: Key.UP,
    pygame.K_DOWN: Key.DOWN,
    pygame.K_LEFT: Key.LEFT,
    pygame.K_RIGHT: Key.RIGHT,
    pygame.K_x: Key.SOUTH,
    pygame.K_y: Key.EAST,
    pygame.K_z: Key.EAST,
    pygame.K_a: Key.L,
    pygame.K_s: Key.R,
    pygame.K_RETURN: Key.START,
    pygame.K_BACKSPACE: Key.SELECT,
    pygame.K_SPACE: Key.STICK_R,
    pygame.K_TAB: Key.L2,
    pygame.K_c: Key.WEST,
    pygame.K_v: Key.NORTH,
    pygame.K_q: Key.STICK_L,
}

CONFIRM = frozenset({Key.SOUTH})
BACK_KEYS = frozenset({Key.EAST, Key.SELECT})

def keys_name(key: Key) -> str:
    """Display name of a position key in the current language (language key key.<name>)."""
    return t(f"key.{key.name.lower()}")
