"""Tests of the Soullink plugin in the game."""
import json
import re
import string
import struct
import time
from pathlib import Path

import pygame
import pytest

from pokemon_helpers import G3_PC, G3_TEAM, flags_set, g3_pc_set, g3_sav, g3_team_set, pk3
from soullink import dex as D
from soullink import language
from soullink.input.keys import Key
from test_dex import DATA
from ui_helpers import FakeProcess, input, fake_session

PLUGIN = Path(__file__).resolve().parents[1]


def _game(app, tmp_path, count=2, name="S", **extra):
    """Game screen with the given players."""
    from soullink.ui.game import GameScreen

    FakeProcess.instances = []
    bs = GameScreen(app, fake_session(tmp_path / name, count), ["keyboard", "c1", "c2"][:count],
                         process_factory=FakeProcess, **extra)
    app.switch(bs)
    bs.update(0.016)
    return bs


def press(bs, device, key, pressed=True):
    """Sends a key press or release of a device to the game."""
    input(bs, device, key, pressed)
    bs.update(0.016)


def _a(bs, device="c1"):
    """Presses A (south) of a device."""
    press(bs, device, Key.SOUTH)
    press(bs, device, Key.SOUTH, False)


def _plugin(app):
    """The loaded Soullink plugin object."""
    return dict((i.id, p) for i, p in app.plugins.active())["soullink"]


def _dex(tmp_path, locations=None):
    """Writes a small dex.json and loads it."""
    path = tmp_path / "dex.json"
    path.write_text(json.dumps({**DATA, **({"locations": locations} if locations else {})}, ensure_ascii=False), encoding="utf-8")
    return D.load(path)


def _firered_ram(badge=()):
    """RAM dump of FireRed: team (Farfetch'd, Caterpie), two box Pokémon, SaveBlock1 with badge flags."""
    ewram, iwram = bytearray(0x40000), bytearray(0x8000)
    g3_team_set(ewram, 0x24284, G3_TEAM, 0x24029)
    g3_pc_set(ewram, 0x29384, G3_PC)
    struct.pack_into("<III", iwram, 0x5008, 0x02025590, 0x020245EC, 0x02029384)
    flags_set(ewram, 0x25590 + 0xEE0, [0x828] + [0x820 + n for n in badge])
    return {0x02000000: bytes(ewram), 0x03000000: bytes(iwram)}


def test_tab_order_and_title(app, tmp_path):
    """The tabs have their order and titles."""
    bs = _game(app, tmp_path)
    sp = bs.player[0]
    assert [r.id for r in sp.types.tab] == ["soullink", "level", "types"]
    assert [r.title() for r in sp.types.tab] == ["Soullink", "Levels", "Types"]
    assert [r.title(short=True) for r in sp.types.tab] == ["SLK", "LVL", "TYP"]
    bs.raw(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_t, mod=0, unicode="t", scancode=0))
    assert sp.types_open and sp.types.active.id == "soullink"
    bs.draw(app.area)


def test_player_menu_entry_opens_the_soullink_tab(app, tmp_path):
    """The menu entry opens the Soullink tab."""
    bs = _game(app, tmp_path)
    sp = bs.player[1]
    press(bs, "c1", Key.L2)
    press(bs, "c1", Key.L2, False)
    sp.menu.selection = sp.menu_actions.index("plugins")
    _a(bs)
    assert sp.submenu == "plugins" and sp.menu.entries == ["Soullink"]
    bs.draw(app.area)
    sp.types.show("types")
    _a(bs)
    assert sp.menu is None and sp.types_open and sp.types.active.id == "soullink"
    assert all(p.hat("ram") for p in FakeProcess.instances)


def test_catches_from_the_save_at_start_and_after_sram(app, tmp_path):
    """Catches come from the save at start and after SRAM saves."""
    s = fake_session(tmp_path / "S")
    s.sav(2).write_bytes(bytes(g3_sav(team=[pk3(25, "PIKA", location=88, level=5)])))
    bs = _game(app, tmp_path)
    data = _plugin(app).data
    assert [(z.location, sorted(z.catches)) for z in data.rows()] == [(88, [2])]
    s.sav(2).write_bytes(bytes(g3_sav(team=[pk3(25, "PIKA", location=88, level=5), pk3(16, "PIDGEY", location=89, level=3)])))
    FakeProcess.instances[1]._new.append(("sram",))
    bs.update(0.016)
    assert [z.location for z in data.rows()] == [88, 89]


def test_ram_for_catches_and_badge_level_cap(app, tmp_path):
    """RAM dumps update the catches and the level cap by badges."""
    bs = _game(app, tmp_path)
    plugin = _plugin(app)
    sp = bs.player[1]
    level = sp.types.find("level")
    assert level.ram_interval == 5.0 and sp.types.find("soullink").ram_interval == 5.0
    FakeProcess.instances[1]._new.append(("ram", _firered_ram(badge=[0, 1, 2])))
    bs.update(0.016)
    assert plugin.badge == {1: None, 2: 3}
    assert sorted((z.location, nr, f.kind) for z in plugin.data.rows() for nr, f in z.catches.items()) == \
        [(88, 2, 371), (89, 2, 25), (101, 2, 83), (102, 2, 10)]
    bs.rom_data._dex[2] = _dex(tmp_path)
    list_ = level.target._list()
    assert level.target.badge() == 3 and level.target.cap(list_) is None
    FakeProcess.instances[1]._new.append(("ram", _firered_ram(badge=[0])))
    bs.update(0.016)
    assert list_[level.target.cap(list_)].number == 2
    bs._types_open(sp)
    sp.types.show("level")
    bs.draw(app.area)


def test_dead_mark_and_misses_are_written_to_soullink_json(app, tmp_path):
    """Dead marks and misses are written to soullink.json."""
    bs = _game(app, tmp_path)
    plugin = _plugin(app)
    sp = bs.player[1]
    FakeProcess.instances[1]._new.append(("ram", _firered_ram()))
    bs.update(0.016)
    bs.rom_data._dex[1] = bs.rom_data._dex[2] = _dex(tmp_path, {"88": "Pallet Town", "89": "Viridian City",
                                                                 "101": "Route 1", "102": "Route 2", "5": "Route 5"})
    bs._types_open(sp)
    sp.types.show("soullink")
    file = bs.session.dir / "soullink.json"
    _a(bs)
    _a(bs)
    assert json.loads(file.read_text(encoding="utf-8"))["dead"] == [88]
    bs.draw(app.area)
    press(bs, "c1", Key.EAST)
    press(bs, "c1", Key.WEST)
    tab = sp.types.active.target
    assert tab.location_choice and [o[1] for o in tab._free_locations()] == ["Route 5"]
    press(bs, "c1", Key.NORTH)
    assert tab.location_search.is_open
    _a(bs)
    assert tab.location_search.text
    bs.draw(app.area)
    press(bs, "c1", Key.START)
    assert not tab.location_search.is_open and tab.location_search.active
    press(bs, "c1", Key.EAST)
    assert not tab.location_search.active and tab.location_choice
    _a(bs)
    assert tab.poke_choice == (5, 2)
    _a(bs)
    data = json.loads(file.read_text(encoding="utf-8"))
    assert data["encounters"] == {"5": {"2": 1}} and data["dead"] == [5, 88]
    bs.draw(app.area)
    assert plugin.data.dead == {5, 88}


def test_free_field_shows_the_soullink_list(app, tmp_path):
    """The free field shows the Soullink list."""
    app.settings.free_field = "core.soullink"
    bs = _game(app, tmp_path, count=3)
    assert len(bs.cells) == 4
    assert bs.field.current(app.settings.free_field, bs.time)[:2] == ("soullink.list", "Soullink list")
    bs.ram_requested = time.monotonic() - 11
    bs.update(0.016)
    assert all(p.hat("ram") for p in FakeProcess.instances)
    FakeProcess.instances[1]._new.append(("ram", _firered_ram()))
    bs.update(0.016)
    assert len(_plugin(app).data.rows()) == 4
    bs.draw(app.area)
    app.settings.free_field = "alternating"
    bs.time = 0.0
    seen = []
    for _ in range(3):
        seen.append(bs.field.current("alternating", bs.time)[0])
        bs.update(15.0)
    assert seen == ["soullink.list", "core.session", "soullink.list"]


def test_rom_data_of_all_players_is_requested_at_start(app, tmp_path, monkeypatch):
    """ROM data of all players is requested at the start."""
    from soullink.ui.game import GameScreen

    loaded = []
    monkeypatch.setattr(GameScreen, "_dex_load", lambda self, nr: loaded.append(nr) or _dex(tmp_path))
    bs = _game(app, tmp_path, dex_load=True)
    assert bs.rom_data.requested == [1, 2]
    end = time.monotonic() + 5
    while len(loaded) < 2 and time.monotonic() < end:
        time.sleep(0.01)
    assert loaded == [1, 2]


def test_plugin_off_means_no_soullink_tab(app, tmp_path):
    """With the plugin off there is no Soullink tab."""
    app.plugins.set_("soullink", False)
    bs = _game(app, tmp_path, count=3)
    sp = bs.player[1]
    assert [r.id for r in sp.types.tab] == ["types"]
    press(bs, "c1", Key.L2)
    press(bs, "c1", Key.L2, False)
    assert "plugins" not in sp.menu_actions
    assert bs.field.current("", 0)[0] == "core.session" and bs.field.show == []
    assert not (bs.session.dir / "soullink.json").exists()


def test_next_game_gets_own_data_and_tab(app, tmp_path):
    """The next game gets its own data and tab."""
    first = _game(app, tmp_path, name="A")
    first.player[0].types.find("soullink").target.data.toggle(5)
    second = _game(app, tmp_path, name="B")
    plugin = _plugin(app)
    tab = second.player[0].types.find("soullink").target
    assert plugin.data is tab.data and tab.data.dir == second.session.dir and tab.data.dead == set()
    assert second.field.current("", 0)[2].target._tab.data is plugin.data


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
    assert not any(k.startswith(("soullink.", "level.")) for k in de)
    used = set()
    for file in PLUGIN.glob("*.py"):
        for call in re.findall(r"api\.t\(([^)]*)\)", file.read_text(encoding="utf-8")):
            used |= set(re.findall(r"""["']([a-z_0-9]+)["']""", call.split("=")[0]))
    assert {"dead", "alive", "tab_level_short", "display", "level_badge"} <= used
    assert not used - set(de), sorted(used - set(de))


@pytest.mark.parametrize("abbreviation", ["de", "us"])
def test_core_has_the_texts_no_more(abbreviation):
    """The core no longer holds the plugin's texts."""
    core = language.read_file(language.dir() / f"{abbreviation}.txt")
    assert not [k for k in core if k.startswith("soullink.")]
    assert not {"tab.soullink", "tab.level", "tab_short.soullink", "tab_short.level"} & set(core)
    assert not [k for k in core if k.startswith("level.")]
