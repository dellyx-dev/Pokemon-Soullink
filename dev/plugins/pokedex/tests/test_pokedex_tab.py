"""Tests of the Pokedex tab."""
import pygame

from conftest import plugin_module
from soullink.dex import Dex, Pokemon
from soullink.input.keys import Key
from soullink.ui import graphics

PokedexTab = plugin_module("pokedex", "tab").PokedexTab


def _dex():
    """A small dex with a few Pokemon."""
    names = {1: "Zubat", 2: "Bulbasaur", 3: "Abra", 4: "Äffchen", 5: "Arbok"}
    pokemon = [Pokemon(nr, name, ["NORMAL"], [50] * 6, [], [(1, 1)]) for nr, name in names.items()]
    return Dex("BPRD", 3, pokemon, {}, {}, {})


def _tab(pokedex_api):
    """Tab with the small dex."""
    pokedex_api.dex_value = _dex()
    return PokedexTab(pokedex_api, 1)


def _names(tab):
    """Names of the Pokemon in the tab's list."""
    return [p.name for p in tab._list()]


def test_title_position_and_ram(pokedex_api):
    """The tab has its title, position and RAM interval."""
    r = PokedexTab(pokedex_api, 1)
    assert (r.id, r.position, r.ram_interval, r.title(), r.title(short=True)) == ("pokedex", 50, None, "Pokédex", "DEX")


def test_sorting_toggle_jumps_to_the_start(pokedex_api):
    """Toggling the sorting jumps to the start."""
    r = _tab(pokedex_api)
    assert _names(r) == ["Zubat", "Bulbasaur", "Abra", "Äffchen", "Arbok"]
    r.event(Key.DOWN)
    r.event(Key.WEST)
    assert _names(r) == ["Abra", "Äffchen", "Arbok", "Bulbasaur", "Zubat"]
    assert r.selection == 0
    r.event(Key.DOWN)
    r.event(Key.WEST)
    assert r.selection == 0 and not r.after_name


def test_a_to_z_jumps_by_letters(pokedex_api):
    """In A-Z sorting left and right jump by initial letter."""
    r = _tab(pokedex_api)
    r.event(Key.WEST)
    assert r._list()[r.selection].name == "Abra"
    r.event(Key.RIGHT)
    assert r._list()[r.selection].name == "Bulbasaur"
    r.event(Key.RIGHT)
    assert r._list()[r.selection].name == "Zubat"
    r.event(Key.LEFT)
    assert r._list()[r.selection].name == "Bulbasaur"
    r.event(Key.LEFT)
    assert r._list()[r.selection].name == "Abra"
    assert ("X", "By no.") in r.hints()


def test_details_and_search(pokedex_api):
    """Details and search work."""
    r = _tab(pokedex_api)
    assert ("X", "A–Z") in r.hints() and ("Y", "Search") in r.hints()
    r.event(Key.SOUTH)
    assert r.open_ and r.hints() == [("<>", "Previous / Next"), ("B", "Back")]
    r.event(Key.RIGHT)
    assert r.selection == 1 and r.event(Key.EAST) and not r.open_
    r.event(Key.NORTH)
    assert r.search.is_open
    r.keyboard_close()
    assert not r.search.is_open


def test_draw_both_sortings(pokedex_api):
    """Both sortings draw."""
    pygame.font.init()
    r = _tab(pokedex_api)
    area = pygame.Surface((800, 500))
    for _ in range(2):
        r.draw(area, pygame.Rect(0, 0, 800, 500), 30)
        r.event(Key.WEST)
    r.event(Key.SOUTH)
    r.draw(area, pygame.Rect(0, 0, 800, 500), 30)


def test_loads_and_error(pokedex_api, monkeypatch):
    """Loading and error states are shown."""
    pygame.font.init()
    r = PokedexTab(pokedex_api, 1)
    drawn, original = [], graphics.text
    monkeypatch.setattr(graphics, "text", lambda area, content, *a, **k: drawn.append(content)
                        or original(area, content, *a, **k))
    area = pygame.Surface((800, 500))
    r.draw(area, pygame.Rect(0, 0, 800, 500), 30)
    assert drawn == ["Loading the Pokédex of your ROM …"] and not r.event(Key.NORTH)
    pokedex_api.error = "Java not found"
    drawn.clear()
    r.draw(area, pygame.Rect(0, 0, 800, 500), 30)
    assert drawn == ["Pokédex data missing: Java not found"]
