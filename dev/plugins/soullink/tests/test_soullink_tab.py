"""Tab "Soullink" and the display in the free panel: rows, dead/alive, Pokémon not caught, scrolling."""
from dataclasses import dataclass

import pygame

from conftest import plugin_module
from soullink.dex import Dex, Pokemon
from soullink.input.keys import Key

LinkData = plugin_module("soullink", "link_list").LinkData
tab = plugin_module("soullink", "tab")
SoullinkTab, pendulum = tab.SoullinkTab, tab.pendulum


@dataclass
class F:
    """Minimal catch for the tests."""
    kind: int
    location: int
    team: bool = True
    box: int | None = None
    slot: int = 0
    day: object = None
    ei: bool = False
    hatched: bool = False
    nickname: str = ""
    level: int | None = 5


def _dex():
    """A small dex with a few Pokemon."""
    names = {1: "Zubat", 2: "Bulbasaur", 3: "Abra", 4: "Äffchen", 5: "Arbok"}
    pokemon = [Pokemon(nr, name, ["NORMAL"], [50] * 6, [], [(1, 1)]) for nr, name in names.items()]
    return Dex("BPRD", 3, pokemon, {}, {}, {})


def test_dead_row_draw(tmp_path, api):
    """A dead row draws with its hatching."""
    pygame.font.init()
    data = LinkData(tmp_path, [1, 2], {}, lambda nr: "x", lambda b, c: [])
    data._catches = {1: [F(2, 5), F(3, 6)], 2: [F(1, 5)]}
    data.rom._dex = {1: _dex(), 2: _dex()}
    data.toggle(5)
    r = SoullinkTab(api, data, 1)
    area = pygame.Surface((800, 400))
    r.draw(area, pygame.Rect(0, 0, 800, 400), 30)
    r.event(Key.SOUTH)
    assert r.open_
    r.draw(area, pygame.Rect(0, 0, 800, 400), 30)


def test_entering_a_miss_through_the_location_choice(tmp_path, api):
    """A miss is entered through the location choice."""
    pygame.font.init()
    data = LinkData(tmp_path, [1, 2], {}, lambda nr: "x", lambda b, c: [])
    r = SoullinkTab(api, data, 1)
    area, rect = pygame.Surface((800, 400)), pygame.Rect(0, 0, 800, 400)
    assert ("X", "Not caught") in r.hints()
    r.event(Key.WEST)
    assert r.location_choice and ("A", "Continue") in r.hints()
    r.draw(area, rect, 30)
    dex = Dex("BPRD", 3, _dex().pokemon, {}, {}, {101: "Route 1", 102: "Route 2"})
    data.rom._dex = {1: dex, 2: dex}
    r.draw(area, rect, 30)
    r.event(Key.DOWN)
    r.event(Key.SOUTH)
    assert not r.location_choice and r.poke_choice == (102, 1) and not r.poke_search.is_open and data.dead == set()
    r.draw(area, rect, 30)
    r.event(Key.EAST)
    assert r.location_choice and r.poke_choice is None
    r.event(Key.SOUTH)
    r.event(Key.SOUTH)
    assert r.poke_choice is None and not r.location_choice
    assert data.encounters == {102: {1: 3}} and data.dead == {102}
    row = data.rows()[r.selection]
    assert row.location == 102 and row.catches == {} and row.missed == {1: 3} and row.dead
    r.draw(area, rect, 30)
    r.event(Key.WEST)
    assert [o[1] for o in r._free_locations()] == ["Route 1"]
    r.event(Key.EAST)
    assert not r.location_choice
    r.event(Key.WEST)
    r.event(Key.NORTH)
    assert r.location_search.is_open
    r.keyboard_close()
    assert not r.location_search.is_open


def test_pendulum_scrolls_up_and_down():
    """The pendulum scroll goes up and down."""
    assert pendulum(5.0, 0, 10) == 0
    assert [pendulum(z, 100, 10, pause=3) for z in (0, 2.9, 8, 13, 15, 21, 26, 26.5)] == [0, 0, 50, 100, 100, 50, 0, 0]


def test_display_with_many_locations_scrolls(tmp_path, api):
    """The display scrolls with many locations."""
    pygame.font.init()
    data = LinkData(tmp_path, [1], {}, lambda nr: "x", lambda b, c: [])
    data._catches = {1: [F(1, location) for location in range(30)]}
    data.rom._dex = {1: _dex()}
    r = SoullinkTab(api, data, 0)
    area = pygame.Surface((600, 300))
    images = []
    for time in (0.0, 8.0):
        area.fill((0, 0, 0))
        r.draw_display(area, pygame.Rect(0, 0, 600, 300), 20, time)
        images.append(pygame.image.tobytes(area, "RGB"))
    assert images[0] != images[1]


def test_entering_the_missed_pokemon(tmp_path, api):
    """The missed Pokemon is entered."""
    pygame.font.init()
    data = LinkData(tmp_path, [1, 2], {}, lambda nr: "x", lambda b, c: [])
    data._catches = {1: [F(2, 5)]}
    data.rom._dex = {1: _dex(), 2: _dex()}
    r = SoullinkTab(api, data, 1)
    area, rect = pygame.Surface((800, 500)), pygame.Rect(0, 0, 800, 500)
    r.event(Key.SOUTH)
    r.event(Key.RIGHT)
    assert ("X", "Not caught") in r.hints()
    r.event(Key.WEST)
    assert r.poke_choice == (5, 2) and not r.poke_search.is_open
    r.draw(area, rect, 30)
    assert [p.name for p in r._poke_list()] == ["Abra", "Äffchen", "Arbok", "Bulbasaur", "Zubat"]
    r.event(Key.UP)
    r.event(Key.SOUTH)
    assert r.poke_choice is None and data.encounters == {5: {2: 1}} and data.rows()[0].dead
    r.draw(area, rect, 30)
    r.open_ = False
    r.draw(area, rect, 30)
    r.event(Key.SOUTH)
    r.event(Key.RIGHT)
    r.event(Key.WEST)
    assert r._poke_list()[0] is None
    r.event(Key.SOUTH)
    assert data.encounters == {}
