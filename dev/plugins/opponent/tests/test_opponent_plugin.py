"""Opponent plugin in the game: tab before "Types", battle live from RAM, ROM data at start, plugin off, texts."""
import json
import re
import string
import struct
import time
from pathlib import Path

import pytest

from conftest import plugin_module
from pokemon_helpers import G3_TEAM, g3_team_set, gmain_set, pk3
from soullink import dex as D
from soullink import language
from soullink.pokemon_data import Opponent
from soullink.ui import graphics
from test_dex import DATA
from ui_helpers import FakeProcess, fake_session

PLUGIN = Path(__file__).resolve().parents[1]


def _game(app, tmp_path, count=2, **extra):
    """Game screen with the given players."""
    from soullink.ui.game import GameScreen

    FakeProcess.instances = []
    bs = GameScreen(app, fake_session(tmp_path / "S", count), ["keyboard", "c1", "c2"][:count],
                         process_factory=FakeProcess, **extra)
    app.switch(bs)
    bs.update(0.016)
    return bs


def _battle_ram(in_battle=True):
    """RAM dump of FireRed: own team and opposing team (Bulbasaur fainted, Onix with 12 HP)."""
    ewram, iwram = bytearray(0x40000), bytearray(0x8000)
    g3_team_set(ewram, 0x24284, G3_TEAM, 0x24029)
    opponent = [bytearray(pk3(1, "BULBASAUR", level=5, pid=21)), bytearray(pk3(95, "ONIX", level=14, pid=22))]
    struct.pack_into("<H", opponent[1], 0x56, 12)
    g3_team_set(ewram, 0x2402C, [bytes(g) for g in opponent])
    gmain_set(iwram, 0x3040, in_battle)
    return {0x02000000: bytes(ewram), 0x03000000: bytes(iwram)}


def _texts(monkeypatch) -> list[str]:
    """All texts drawn while the test runs."""
    drawn, original = [], graphics.text
    monkeypatch.setattr(graphics, "text", lambda area, content, *a, **k: drawn.append(content)
                        or original(area, content, *a, **k))
    return drawn


def test_tab_comes_before_types_and_asks_for_ram_every_one_and_a_half_seconds(plugin_app, tmp_path):
    """The tab sits before Types and asks for RAM every 1.5 seconds."""
    app = plugin_app("opponent")
    bs = _game(app, tmp_path)
    sp = bs.player[1]
    assert [r.id for r in sp.types.tab] == ["opponent", "types"]
    assert [(r.title(), r.title(short=True)) for r in sp.types.tab] == [("Opponent", "OPP"), ("Types", "TYP")]
    bs._types_open(sp)
    assert sp.types.active.id == "opponent"
    p1 = FakeProcess.instances[0]
    assert len(p1.hat("ram")) == 1
    bs.ram_requested = time.monotonic() - 2
    bs.update(0.016)
    assert len(p1.hat("ram")) == 2
    sp.types.show("types")
    bs.ram_requested = time.monotonic() - 6
    bs.update(0.016)
    assert len(p1.hat("ram")) == 2
    assert bs.plugins.menu(2) == []


def test_battle_live_from_the_ram(plugin_app, tmp_path, monkeypatch):
    """The battle is shown live from RAM."""
    app = plugin_app("opponent")
    bs = _game(app, tmp_path)
    sp = bs.player[1]
    tab = sp.types.find("opponent").target
    bs._types_open(sp)
    assert all(p.hat("ram") for p in FakeProcess.instances)
    FakeProcess.instances[0]._new.append(("ram", {0x02000000: bytes(16)}))
    FakeProcess.instances[1]._new.append(("ram", _battle_ram()))
    bs.update(0.016)
    assert tab.battle == [[Opponent(1, 5, 0), Opponent(95, 14, 12)]]
    assert bs.player[0].types.find("opponent").target.battle is None
    texts = _texts(monkeypatch)
    bs.draw(app.area)
    assert "Battle in progress – loading Pokédex data …" in texts and "Not in a battle right now" not in texts
    path = tmp_path / "dex.json"
    path.write_text(json.dumps(DATA, ensure_ascii=False), encoding="utf-8")
    bs.rom_data._dex[2] = D.load(path)
    texts.clear()
    bs.draw(app.area)
    assert "Onix" in texts and "Lv 14" in texts and "Bulbasaur" not in texts
    assert sp.types.active.hints() == [("L/R", "Page"), ("B", "Close")]
    FakeProcess.instances[1]._new.append(("ram", _battle_ram(in_battle=False)))
    bs.update(0.016)
    texts.clear()
    bs.draw(app.area)
    assert tab.battle is None and "Not in a battle right now" in texts


def test_rom_data_of_all_players_is_requested_at_start(plugin_app, tmp_path, monkeypatch):
    """ROM data of all players is requested at the start."""
    from soullink.ui.game import GameScreen

    loaded = []
    monkeypatch.setattr(GameScreen, "_dex_load", lambda self, nr: loaded.append(nr))
    bs = _game(plugin_app("opponent"), tmp_path, dex_load=True)
    assert bs.rom_data.requested == [1, 2]
    end = time.monotonic() + 5
    while len(loaded) < 2 and time.monotonic() < end:
        time.sleep(0.01)
    assert loaded == [1, 2]


def test_plugin_off_means_no_opponent_tab(plugin_app, tmp_path):
    """With the plugin off there is no opponent tab."""
    app = plugin_app("opponent")
    app.plugins.set_("opponent", False)
    bs = _game(app, tmp_path)
    assert [r.id for r in bs.player[1].types.tab] == ["types"]
    FakeProcess.instances[1]._new.append(("ram", _battle_ram()))
    bs.update(0.016)
    assert bs.rom_data.requested == []


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
    used = set(plugin_module("opponent", "tab").LEVELS_TEXT.values())
    for file in PLUGIN.glob("*.py"):
        for call in re.findall(r"api\.t\(([^)]*)\)", file.read_text(encoding="utf-8")):
            used |= set(re.findall(r"""["']([a-z_0-9]+)["']""", call.split("=")[0]))
    assert {"tab", "tab_short", "no_battle", "battle_loads", "battle_error", "lv", "level_4"} <= used
    assert not used - set(de), sorted(used - set(de))


@pytest.mark.parametrize("abbreviation", ["de", "us"])
def test_core_has_the_texts_no_more(abbreviation):
    """The core no longer holds the plugin's texts."""
    core = language.read_file(language.dir() / f"{abbreviation}.txt")
    assert not {"tab.opponent", "tab_short.opponent", "overlay.no_battle", "overlay.of_hand", "overlay.defeated",
                "overlay.strong_against", "overlay.attacken_are", "overlay.type", "overlay.first_second",
                "overlay.opponent_pokemon"} & set(core)
    assert not [k for k in core if k.startswith(("level.", "level.", "opponent."))]
