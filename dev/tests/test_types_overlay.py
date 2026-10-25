"""Tests of the types overlay."""

import pygame

from soullink.input.keys import Key
from soullink.plugin.api import Tab
from soullink.ui.types_overlay import TypesOverlay, TypesTab, tab_order


class _R(Tab):
    """Minimal tab with an id, position and a tab it replaces."""

    def __init__(self, rid, position, replaced=None):
        """Creates the tab."""
        self.id, self.position, self.replaced = rid, position, replaced


def test_without_plugins_only_the_types_tab():
    """Without plugins only the types tab exists."""
    o = TypesOverlay()
    assert [r.id for r in o.tab] == ["types"] and o.active.id == "types"
    o.event(Key.R)
    assert o.active.id == "types" and o.page == 0


def test_l_and_r_page_through_tabs():
    """L and R page through the tabs."""
    o = TypesOverlay([TypesTab(), _R("opponent", 20)])
    assert [r.id for r in o.tab] == ["opponent", "types"] and o.active.id == "opponent"
    o.event(Key.R)
    assert o.active.id == "types"
    o.event(Key.R)
    assert o.active.id == "opponent"
    o.event(Key.L)
    assert o.active.id == "types"


def test_table_cursor():
    """The type table cursor moves."""
    o = TypesOverlay()
    table = o.find("types")
    o.event(Key.DOWN)
    o.event(Key.RIGHT)
    o.event(Key.RIGHT)
    o.event(Key.RIGHT)
    assert (table.row, table.column) == (1, 3)
    o.event(Key.UP)
    o.event(Key.UP)
    assert table.row == 16


def test_close():
    """Closing the overlay closes tab keyboards."""
    o = TypesOverlay()
    assert o.event(Key.NORTH) == "close"
    assert o.event(Key.SELECT) == "close"
    assert o.event(Key.SOUTH) is None


def test_core_tab_title_position_and_ram():
    """The core tab has its title, position and RAM interval."""
    tab = TypesTab()
    assert (tab.id, tab.position, tab.ram_interval, tab.title(), tab.title(True)) == \
        ("types", 40, None, "Types", "TYP")


def test_order_by_position_and_replaced():
    """Tabs are ordered by position and replacements apply."""
    discarded = []
    core = [_R("opponent", 20), TypesTab()]
    new = [_R("list", 10), _R("end", 99), _R("my_types", 40, replaced="types"), _R("different", 45, replaced="types"),
           _R("list", 11)]
    list_ = tab_order(core + new, lambda r, reason: discarded.append((r.id, r.position, reason)))
    assert [r.id for r in list_] == ["list", "opponent", "my_types", "end"]
    assert [(i, p) for i, p, _ in discarded] == [("different", 45), ("list", 11)]
    equal = _R("opponent", 25, replaced="opponent")
    assert [(r.id, r.position) for r in tab_order(core + [equal])] == [("opponent", 25), ("types", 40)]
    chain = tab_order(core + [_R("x", 20, replaced="opponent"), _R("y", 21, replaced="x")])
    assert [r.id for r in chain] == ["y", "types"]


def test_overlay_with_own_tabs_and_show():
    """The overlay accepts own tabs and can open one by id."""
    o = TypesOverlay(core := [TypesTab()])
    o.tab_set(core + [_R("list", 10)])
    assert [r.id for r in o.tab] == ["list", "types"]
    assert o.show("types") and o.active.id == "types" and not o.show("exists_not")
    o.tab_set(core + [_R("list", 10), _R("end", 99)])
    assert o.active.id == "types" and o.page == 1
    o.tab_set([_R("list", 10)])
    assert o.active.id == "list"


def test_tab_that_consumes_l_and_r(monkeypatch):
    """A tab can consume L and R itself."""
    from soullink.ui import graphics

    pygame.font.init()
    buttons, rows = [], []
    button, button_row = graphics.button, graphics.button_row

    def button_remember(area, pos, name, *rest, **named):
        """Remembers the drawn button names."""
        buttons.append(name)
        return button(area, pos, name, *rest, **named)

    def row_remember(area, middle, entries, *rest):
        """Remembers the drawn button rows."""
        rows.append([symbol for symbol, _ in entries])
        return button_row(area, middle, entries, *rest)

    monkeypatch.setattr(graphics, "button", button_remember)
    monkeypatch.setattr(graphics, "button_row", row_remember)
    area = pygame.Surface((960, 540))
    o = TypesOverlay()
    o.draw(area, pygame.Rect(0, 0, 960, 540), 27)
    assert not {"L", "R"} & set(buttons) and rows == [["<>", "B"]]
    o.tab_set([TypesTab(), _R("list", 10)])
    o.show("list")
    o.draw(area, pygame.Rect(0, 0, 960, 540), 27)
    assert {"L", "R"} <= set(buttons) and rows[-1] == []
    o.show("types")
    o.draw(area, pygame.Rect(0, 0, 960, 540), 27)
    assert rows[-1] == ["<>", "L/R", "B"]


def test_draw_all_sizes():
    """The overlay draws at all sizes."""
    pygame.font.init()
    area = pygame.Surface((1920, 1080))
    o = TypesOverlay()
    o.event(Key.DOWN)
    o.event(Key.RIGHT)
    for range_, pixel in (((0, 0, 1920, 1080), 54), ((1035, 540, 810, 540), 27), ((20, 0, 600, 400), 20),
                           ((0, 0, 480, 720), 24)):
        o.draw(area, pygame.Rect(range_), pixel)
