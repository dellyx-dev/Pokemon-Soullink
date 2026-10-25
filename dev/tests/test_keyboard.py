"""Tests of the on-screen keyboard and the search."""

import pygame

from soullink.input.keys import Key
from soullink.ui.keyboard import Search, VirtualKeyboard, simplified


def tap(keyboard, *keys):
    """Sends the keys to the keyboard and returns the last result."""
    result = None
    for key in keys:
        result = keyboard.event(key)
    return result


def test_tap_delete_clear_case_and_done():
    """Typing, deleting, clearing, case and finishing work."""
    k = VirtualKeyboard()
    tap(k, Key.SOUTH)
    tap(k, Key.RIGHT, Key.SOUTH)
    tap(k, Key.WEST, Key.SOUTH)
    tap(k, Key.NORTH)
    assert k.text == "ABb "
    tap(k, Key.EAST)
    assert k.text == "ABb"
    assert tap(k, Key.START) == "done"


def test_navigation_with_wide_special_keys():
    """Navigation works across keys of different widths."""
    k = VirtualKeyboard()
    tap(k, Key.UP)
    assert k.chosen() == "empty"
    tap(k, Key.RIGHT)
    assert k.chosen() == "delete"
    tap(k, Key.RIGHT, Key.RIGHT)
    assert k.chosen() == "done"
    tap(k, Key.UP)
    assert k.chosen() == ")"
    tap(k, Key.DOWN)
    assert tap(k, Key.SOUTH) == "done"


def test_cancel_only_with_an_empty_field():
    """B cancels only when the field is empty."""
    k = VirtualKeyboard("X")
    assert tap(k, Key.EAST) is None and k.text == ""
    assert tap(k, Key.EAST) == "cancel"
    assert VirtualKeyboard().event(Key.SELECT) == "cancel"


def test_maximum_length():
    """The maximum length is respected."""
    k = VirtualKeyboard(max_length=3)
    tap(k, *[Key.SOUTH] * 5)
    assert k.text == "AAA"


def test_search_ignores_accents_and_case():
    """The search ignores accents and case."""
    s = Search()
    assert not s.is_open and not s.active
    s.open()
    assert s.is_open and s.active
    for _ in range(26):
        if s.keyboard.chosen() == "Ä":
            break
        s.keyboard.event(Key.RIGHT if s.keyboard.row == 2 else Key.DOWN)
    s.event(Key.SOUTH)
    assert s.text == "Ä" and s.fits("Arbok") and s.fits("Äffchen") and not s.fits("Jigglypuff")
    assert simplified("Äffchen") == "affchen"
    assert s.event(Key.START) == "done" and not s.is_open and s.active
    s.open()
    s.close()
    assert not s.is_open and s.text == "Ä"
    s.clear()
    assert not s.active and s.fits("Zubat")


def test_draw():
    """The keyboard draws."""
    pygame.font.init()
    area = pygame.Surface((800, 600))
    s = Search()
    s.open()
    rest = s.draw(area, pygame.Rect(0, 0, 800, 600), 30, 0.0, 12)
    assert 0 < rest.height < 600 and rest.top > 0
    s.event(Key.START)
    s.text = "to"
    rest = s.draw(area, pygame.Rect(0, 0, 800, 600), 30, 0.0, 3)
    assert rest.bottom == 600
