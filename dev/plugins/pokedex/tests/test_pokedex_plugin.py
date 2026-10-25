"""Tests of the Pokedex plugin in the game."""
import re
import string
import time
from pathlib import Path

import pygame
import pytest

from soullink import language
from soullink.input.keys import Key
from ui_helpers import FakeProcess, input, fake_session

PLUGIN = Path(__file__).resolve().parents[1]


def _game(app, tmp_path, count=2, **extra):
    """Game screen with the given players."""
    from soullink.ui.game import GameScreen

    FakeProcess.instances = []
    bs = GameScreen(app, fake_session(tmp_path / "S", count), ["keyboard", "c1", "c2", "c3"][:count],
                         process_factory=FakeProcess, **extra)
    app.switch(bs)
    bs.update(0.016)
    return bs


def press(bs, device, key, pressed=True):
    """Sends a key press or release of a device to the game."""
    input(bs, device, key, pressed)
    bs.update(0.016)


def test_tab_is_last_and_needs_no_ram(plugin_app, tmp_path):
    """The Pokedex tab comes last and needs no RAM."""
    app = plugin_app("pokedex")
    bs = _game(app, tmp_path)
    sp = bs.player[1]
    assert [r.id for r in sp.types.tab] == ["types", "pokedex"]
    assert [(r.title(), r.title(short=True)) for r in sp.types.tab] == [("Types", "TYP"), ("Pokédex", "DEX")]
    bs._types_open(sp)
    sp.types.show("pokedex")
    p1 = FakeProcess.instances[0]
    bs.ram_requested = time.monotonic() - 60
    bs.update(0.016)
    assert len(p1.hat("ram")) == 1
    assert bs.plugins.menu(2) == []
    bs.draw(app.area)


def test_closing_the_overlay_closes_the_search(plugin_app, tmp_path):
    """Closing the overlay closes the search."""
    app = plugin_app("pokedex")
    bs = _game(app, tmp_path)
    sp = bs.player[1]
    bs._types_open(sp)
    press(bs, "c1", Key.R)
    assert sp.types.active.id == "pokedex"
    search = sp.types.active.target.search
    search.open()
    press(bs, "c1", Key.L2)
    assert not sp.types_open and not search.is_open


def test_rom_data_of_all_players_is_requested_at_start(plugin_app, tmp_path, monkeypatch):
    """ROM data of all players is requested at the start."""
    from soullink.ui.game import GameScreen

    loaded = []
    monkeypatch.setattr(GameScreen, "_dex_load", lambda self, nr: loaded.append(nr))
    bs = _game(plugin_app("pokedex"), tmp_path, dex_load=True)
    assert bs.rom_data.requested == [1, 2]
    end = time.monotonic() + 5
    while len(loaded) < 2 and time.monotonic() < end:
        time.sleep(0.01)
    assert loaded == [1, 2]


def test_all_bundled_tabs_in_order(plugin_app, tmp_path):
    """All bundled tabs appear in order."""
    app = plugin_app("soullink", "opponent", "pokedex")
    bs = _game(app, tmp_path, count=4)
    for sp in bs.player:
        assert [r.id for r in sp.types.tab] == ["soullink", "opponent", "level", "types", "pokedex"]
        bs._types_open(sp)
    sp = bs.player[0]
    assert [r.title() for r in sp.types.tab] == ["Soullink", "Opponent", "Levels", "Types", "Pokédex"]
    assert [r.title(short=True) for r in sp.types.tab] == ["SLK", "OPP", "LVL", "TYP", "DEX"]
    for _ in sp.types.tab:
        bs.draw(app.area)
        for s in bs.player:
            s.types.event(Key.R)


def test_plugin_off_means_no_pokedex_tab(plugin_app, tmp_path):
    """With the plugin off there is no Pokedex tab."""
    app = plugin_app("pokedex")
    app.plugins.set_("pokedex", False)
    bs = _game(app, tmp_path)
    assert [r.id for r in bs.player[0].types.tab] == ["types"]
    bs.raw(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_t, mod=0, unicode="t", scancode=0))
    bs.draw(app.area)
    assert bs.player[0].types_open and bs.rom_data.requested == []


def _file(abbreviation):
    """Texts of one of the plugin's language files."""
    return language.read_file(PLUGIN / "language" / f"{abbreviation}.txt")


def _placeholder(text):
    """Placeholder names used in a text."""
    return {field for _, field, _, _ in string.Formatter().parse(text) if field}


def test_language_files_complete_and_equal():
    """The plugin's language files are complete and use the same placeholders."""
    de, us = _file("de"), _file("us")
    assert set(de) == set(us) and {"_name", "_description"} <= set(de)
    assert not {k for k in de if _placeholder(de[k]) != _placeholder(us[k])}
    used = set()
    for file in PLUGIN.glob("*.py"):
        for call in re.findall(r"api\.t\(([^)]*)\)", file.read_text(encoding="utf-8")):
            used |= set(re.findall(r"""["']([a-z_0-9]+)["']""", call.split("=")[0]))
    assert {"tab", "tab_short", "loads", "details", "a_z", "after_nr", "letter", "before_back"} <= used
    assert not used - set(de), sorted(used - set(de))


@pytest.mark.parametrize("abbreviation", ["de", "us"])
def test_core_has_the_texts_no_more(abbreviation):
    """The core no longer holds the plugin's texts."""
    core = language.read_file(language.dir() / f"{abbreviation}.txt")
    assert not {"tab.pokedex", "tab_short.pokedex"} & set(core)
    assert not [k for k in core if k.startswith("pokedex.")]
    assert {"tab.types", "dex.missing", "dex.loads", "osk.search"} <= set(core)
