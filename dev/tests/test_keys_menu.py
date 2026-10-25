"""Tests of the key binding menu."""

import pygame

from soullink.input.keys import Key
from soullink.input.key_binding import Function, KeyBinding
from soullink.ui.keys_menu import WAIT_TIME, KeysMenu


def test_only_gba_functions_without_ds():
    """Without a DS only GBA functions are listed."""
    m = KeysMenu(KeyBinding(), ds=False)
    assert Function.TOUCH not in m.rows and Function.SWAP not in m.rows
    assert m.rows[-1] == "default"
    assert Function.TOUCH in KeysMenu(KeyBinding(), ds=True).rows


def test_bind_with_swap():
    """Binding a used key swaps functions."""
    b = KeyBinding()
    m = KeysMenu(b, ds=False)
    assert m.rows[0] == Function.A
    assert m.event(Key.SOUTH, 0.0) is None
    assert m.waits == Function.A
    m.event(Key.SOUTH, 1.0)
    assert m.waits is None
    assert b.function(Key.SOUTH) == Function.A and b.function(Key.EAST) == Function.B


def test_each_key_is_bindable_including_select():
    """Every key is bindable, including Select."""
    b = KeyBinding()
    m = KeysMenu(b, ds=False)
    m.event(Key.DOWN, 0.0)
    m.event(Key.SOUTH, 0.0)
    m.event(Key.SELECT, 0.5)
    assert b.function(Key.SELECT) == Function.B


def test_wait_aborts_after_the_wait_time():
    """Waiting for a key aborts after the wait time."""
    b = KeyBinding()
    m = KeysMenu(b, ds=False)
    m.event(Key.SOUTH, 0.0)
    m.update(WAIT_TIME + 0.1)
    assert m.waits is None and b.is_default


def test_reset_to_default_and_done():
    """Resetting to the default and finishing work."""
    b = KeyBinding()
    b.bind(Function.A, Key.L2)
    m = KeysMenu(b, ds=False)
    m.selection = m.rows.index("default")
    m.event(Key.SOUTH, 0.0)
    assert b.is_default
    assert KeysMenu(b, ds=False).event(Key.START, 0.0) == "done"
    assert KeysMenu(b, ds=False).event(Key.EAST, 0.0) is None
    assert KeysMenu(b, ds=False).event(Key.SELECT, 0.0) is None


def test_draw():
    """The key menu draws."""
    pygame.font.init()
    area = pygame.Surface((1920, 1080))
    for ds in (False, True):
        m = KeysMenu(KeyBinding(), ds=ds)
        for range_, pixel in (((1035, 540, 810, 540), 27), ((20, 0, 600, 400), 20), ((0, 0, 1620, 1080), 54)):
            m.draw(area, pygame.Rect(range_), pixel, 0.0)
            m.selection = len(m.rows) - 1
            m.draw(area, pygame.Rect(range_), pixel, 0.0)
            m.event(Key.UP, 0.0)
            m.event(Key.UP, 0.0)
            m.event(Key.SOUTH, 0.0)
            m.draw(area, pygame.Rect(range_), pixel, 1.0)
            m.update(99.0)


def test_ds_shows_x_and_y():
    """The DS key menu shows X and Y."""
    m = KeysMenu(KeyBinding(ds=True), ds=True)
    assert m.rows[:4] == [Function.A, Function.B, Function.X, Function.Y]
    assert Function.X not in KeysMenu(KeyBinding(), ds=False).rows


def test_groups_and_draw():
    """The key menu is grouped and drawn."""
    import pygame

    from soullink.ui.keys_menu import GROUPS

    pygame.font.init()
    m = KeysMenu(KeyBinding(ds=True), ds=True, nr=2)
    layout = m._layout()
    assert [w for a, w in layout if a == "group"] == list(GROUPS)
    assert layout[-2] == ("gap", "") and m.rows[layout[-1][1]] == "default"
    area = pygame.Surface((640, 480))
    for selection in (0, len(m.rows) - 1):
        m.selection = selection
        m.draw(area, area.get_rect(), 24, 0.0)
