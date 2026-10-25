"""Other players plugin in the game: figures in the picture (gen 3, NDS), display Pokémon/marker, switch, plugin off."""
import io
import re
import string
import sys
from pathlib import Path

import pygame
import pytest

from soullink import language
from soullink.input.keys import Key
from ui_helpers import FakeProcess, input, fake_session

PLUGIN = Path(__file__).resolve().parents[1]


def _game(app, tmp_path, count=2, codes=("BPED", "AXVD"), system="gba", name="S"):
    """Game screen with the given players and game codes."""
    from soullink.ui.game import GameScreen

    FakeProcess.instances = []
    bs = GameScreen(app, fake_session(tmp_path / name, count, codes=codes, system=system),
                         ["keyboard", "c1", "c2", "c3"][:count], process_factory=FakeProcess)
    app.switch(bs)
    bs.update(0.016)
    return bs


def _plugin(app):
    """The loaded coplayer plugin object."""
    return dict((i.id, p) for i, p in app.plugins.active())["coplayer"]


def _world():
    """The core module soullink.world the plugin draws from."""
    from soullink import world

    return world


def _set(process, location):
    """Writes a location as the worker part would into the slot."""
    slot = next(p["slot"] for p in process.plugins if p["id"] == "coplayer")
    process.slots[slot] = _world().pack(location)


def press(bs, device, key, pressed=True):
    """Sends a key press or release of a device to the game."""
    input(bs, device, key, pressed)
    bs.update(0.016)


def _a(bs, device="c1"):
    """Presses A (south) of a device."""
    press(bs, device, Key.SOUTH)
    press(bs, device, Key.SOUTH, False)


def _submenu(bs, device="c1"):
    """Player menu (menu key) to "Plugins"."""
    sp = next(s for s in bs.player if s.device == device)
    press(bs, device, Key.L2)
    press(bs, device, Key.L2, False)
    sp.menu.selection = sp.menu_actions.index("plugins")
    _a(bs, device)
    assert sp.submenu == "plugins"
    return sp


def test_coplayer_as_stylus_in_game_frame(app, tmp_path):
    """With the stylus setting a coplayer is drawn as a stylus in the game frame."""
    bs = _game(app, tmp_path)
    w, plugin = _world(), _plugin(app)
    p1, p2 = FakeProcess.instances
    assert plugin.families == {1: "emerald", 2: "rs"}
    assert [p["id"] for p in p1.plugins] == ["coplayer"]
    _set(p1, w.Location(0, 3, 19, 39, 0x0800A, False))
    _set(p2, w.Location(0, 3, 21, 39, 0x0800A, False))
    bs.update(0.016)
    target = bs._screens(0)[0][0]
    tile = target.width / 15
    area = pygame.Surface(app.size)
    plugin.draw(area, 1, target, 10.0)
    x, y = round(target.x + 9.5 * tile), round(target.y + 5.5 * tile - tile * 0.6)
    assert area.get_at((x, y))[:3] != (0, 0, 0)
    assert area.get_at((round(target.x + 7.5 * tile), y))[:3] == (0, 0, 0)
    _set(p2, w.Location(0, 4, 21, 39, 0x0800A, False))
    bs.update(0.016)
    area.fill((0, 0, 0))
    plugin.draw(area, 1, target, 20.0)
    assert area.get_at((x, y))[:3] == (0, 0, 0)
    bs.leave()


def test_hook_draws_over_the_game_frame_and_switches_in_the_submenu(app, tmp_path):
    """The frame hook draws coplayers and the submenu switches them."""
    bs = _game(app, tmp_path)
    w = _world()
    p1, p2 = FakeProcess.instances
    _set(p1, w.Location(0, 3, 19, 39, 0x0800A, False))
    _set(p2, w.Location(0, 3, 21, 39, 0x0800A, False))
    sp2 = bs.player[1]
    for sp in bs.player:
        sp.images["gba"] = pygame.Surface(bs._screens(bs.player.index(sp))[0][0].size)
    bs.update(0.016)
    target = bs._screens(1)[0][0]
    tile = target.width / 15
    point = (round(target.x + 5.5 * tile), round(target.y + 5.5 * tile - tile * 0.6))
    bs.draw(app.area)
    assert app.area.get_at(point)[:3] != (0, 0, 0)
    _submenu(bs)
    assert sp2.menu.entries == ["Show other players"]
    assert bs.plugins.switch(*sp2.plugin_rows[0][:2]) is True
    bs.draw(app.area)
    _a(bs)
    assert bs.plugins.switch(*sp2.plugin_rows[0][:2]) is False and sp2.submenu == "plugins"
    press(bs, "c1", Key.EAST)
    press(bs, "c1", Key.EAST, False)
    sp2.menu = None
    sp2.pauses.discard("menu")
    bs.draw(app.area)
    assert app.area.get_at(point)[:3] == (0, 0, 0)
    assert _plugin(app).show == {1: True, 2: False}
    bs.leave()


def test_coplayer_as_pokemon_icon(app, tmp_path, icon_rom):
    """With the Pokemon setting a coplayer is drawn as the party icon."""
    bs = _game(app, tmp_path)
    w, plugin = _world(), _plugin(app)
    p1, p2 = FakeProcess.instances
    plugin.icons[2] = w.PokemonIcons(icon_rom)
    _set(p1, w.Location(0, 3, 19, 39, 0x0800A, False))
    _set(p2, w.Location(0, 3, 21, 39, 0x0800A, False, kind=25))
    bs.update(0.016)
    target = bs._screens(0)[0][0]
    tile = target.width / 15
    area = pygame.Surface(app.size)
    plugin.draw(area, 1, target, 10.0)
    middle = (round(target.x + 9.5 * tile), round(target.y + 5.5 * tile - tile * 0.5))
    assert area.get_at(middle)[:3] in ((255, 0, 0), (0, 0, 255))
    _set(p2, w.Location(0, 3, 21, 39, 0x0800A, False))
    bs.update(0.016)
    area.fill((0, 0, 0))
    plugin.draw(area, 1, target, 20.0)
    assert area.get_at(middle)[:3] not in ((0, 0, 0), (255, 0, 0), (0, 0, 255))
    bs.leave()


def test_stylus_setting_draws_the_stylus_even_with_icons(app, tmp_path, icon_rom, monkeypatch):
    """The stylus setting draws the stylus even if icons exist."""
    loaded = []
    module = sys.modules["soullink_plugins.coplayer"]
    monkeypatch.setattr(module, "icons_load", lambda rom, family: loaded.append(family))
    app.plugins.value_set("coplayer", "display", "stylus")
    bs = _game(app, tmp_path)
    w, plugin = _world(), _plugin(app)
    assert plugin.display == "stylus" and plugin.icons == {} and loaded == []
    plugin.icons[2] = w.PokemonIcons(icon_rom)
    p1, p2 = FakeProcess.instances
    _set(p1, w.Location(0, 3, 19, 39, 0x0800A, False))
    _set(p2, w.Location(0, 3, 21, 39, 0x0800A, False, kind=25))
    bs.update(0.016)
    target = bs._screens(0)[0][0]
    tile = target.width / 15
    area = pygame.Surface(app.size)
    plugin.draw(area, 1, target, 10.0)
    middle = (round(target.x + 9.5 * tile), round(target.y + 5.5 * tile - tile * 0.5))
    assert area.get_at(middle)[:3] not in ((0, 0, 0), (255, 0, 0), (0, 0, 255))
    bs.leave()


def test_icons_only_for_player_with_shared_world(app, tmp_path, monkeypatch):
    """Icons are loaded only for players in a shared world."""
    loaded = []
    module = sys.modules["soullink_plugins.coplayer"]
    monkeypatch.setattr(module, "icons_load", lambda rom, family: loaded.append((Path(rom).parent.name, family)))
    bs = _game(app, tmp_path, count=3, codes=("BPED", "AXVD", "BPRD"))
    assert _plugin(app).display == "pokemon"
    assert loaded == [("p1", "emerald"), ("p2", "rs")]
    bs.leave()


def test_switch_only_with_another_player_in_the_same_world(app, tmp_path):
    """The switch appears only with another player in the same world."""
    bs = _game(app, tmp_path, count=3, codes=("BPED", "AXVD", "BPRD"))
    plugin = _plugin(app)
    assert [[e.switch is not None for e in plugin.player_menu(nr)] for nr in (1, 2, 3)] == [[True], [True], [False]]
    sp3 = _submenu(bs, "c2")
    entry = sp3.plugin_rows[0][1]
    assert (sp3.menu.entries, entry.reason) == (["Show other players"], "no other player in the same world")
    bs.draw(app.area)
    _a(bs, "c2")
    assert sp3.submenu == "plugins" and plugin.show == {1: True, 2: True, 3: True}
    bs.leave()


def test_no_entry_without_pokemon_game(app, tmp_path):
    """There is no menu entry without a Pokemon game."""
    bs = _game(app, tmp_path, count=3, codes=("BPED", "AXVD", "AMKE"))
    plugin = _plugin(app)
    assert plugin.families[3] is None and plugin.player_menu(3) == []
    bs.leave()


def test_session_end_releases_icons_and_game(app, tmp_path, icon_rom):
    """session_end releases the icons and the game."""
    plugin = _plugin(app)
    first = _game(app, tmp_path, name="A")
    plugin.icons[2] = _world().PokemonIcons(icon_rom)
    second = _game(app, tmp_path, name="B")
    assert plugin.game is not None and plugin.movement
    assert first.plugins._ended
    second.leave()
    assert (plugin.game, plugin.icons, plugin.movement) == (None, {}, {})
    plugin.update(0.016)
    plugin.draw_game_frame(pygame.Surface((240, 160)), 1, pygame.Rect(0, 0, 240, 160), "gba")


def test_does_not_fit_without_a_shared_world(app, tmp_path):
    """The plugin does not fit without a shared world."""
    bs = _game(app, tmp_path, codes=("BPED", "BPRD"))
    assert [i.id for i, _ in bs.plugins.not_matching] == ["coplayer"]
    assert all(p.plugins == [] for p in FakeProcess.instances)
    sp = _submenu(bs)
    assert sp.plugin_rows[0][1].reason == "no other player in the same world"
    bs.draw(app.area)
    bs.leave()


def test_crashed_coplayer_is_not_shown(app, tmp_path):
    """A crashed coplayer is not shown."""
    bs = _game(app, tmp_path)
    w, plugin = _world(), _plugin(app)
    p1, p2 = FakeProcess.instances
    _set(p1, w.Location(0, 3, 19, 39, 0x0800A, False))
    _set(p2, w.Location(0, 3, 21, 39, 0x0800A, False))
    bs.update(0.016)
    assert plugin.movement[2].location is not None
    p2.alive = False
    bs.update(0.016)
    assert bs.player[1].crashed and plugin.movement[2].location is None
    bs.leave()


def test_plugin_off_means_no_worker_part_and_no_switch(app, tmp_path):
    """With the plugin off there is no worker part and no switch."""
    app.plugins.set_("coplayer", False)
    bs = _game(app, tmp_path)
    assert all(p.plugins == [] for p in FakeProcess.instances)
    sp = bs.player[1]
    press(bs, "c1", Key.L2)
    press(bs, "c1", Key.L2, False)
    assert "plugins" not in sp.menu_actions and "coplayer" not in sp.menu_actions
    assert not hasattr(bs, "icons") and not hasattr(sp, "movement")
    bs.leave()


def test_nds_coplayer_on_the_upper_screen(app, tmp_path, nds_icon_rom):
    """On the DS the coplayer is drawn on the upper screen."""
    bs = _game(app, tmp_path, codes=("IPGD", "IPKD"), system="nds")
    w, plugin = _world(), _plugin(app)
    p1, p2 = FakeProcess.instances
    assert plugin.families == {1: "hgss", 2: "hgss"}
    plugin.icons[2] = w.NdsIcons(io.BytesIO(nds_icon_rom), "hgss")
    camera = w._default_camera(466.5, 3.0, 258.5)
    _set(p1, w.Location(0, 73, 466.5, 258.5, 0, False, True, 0, 3.0, camera))
    _set(p2, w.Location(0, 34, 470.5, 261.5, 0, False, True, 25, 3.0, w._default_camera(470.5, 3.0, 261.5)))
    bs.update(0.016)
    top = next(r for r, source in bs._screens(0) if source == "top")
    empty = pygame.Surface(app.size, pygame.SRCALPHA)
    plugin.draw_game_frame(empty, 1, next(r for r, q in bs._screens(0) if q == "bottom"), "bottom")
    assert empty.get_bounding_rect().size == (0, 0)
    plugin.draw_game_frame(empty, 1, top, "top")
    assert empty.get_bounding_rect().size != (0, 0)
    area = pygame.Surface(app.size)
    plugin.draw(area, 1, top, 10.0)
    px, py, scale = w.projection(camera, 470.5, 3.0, 261.5)
    s = top.width / 256
    point = (round(top.x + px * s), round(top.y + (py - scale * 0.6) * s))
    assert area.get_at(point)[:3] == (0, 0, 255)
    assert area.get_at((round(top.x + 128 * s), round(top.y + 80 * s)))[:3] == (0, 0, 0)
    _set(p1, w.Location(0, 73, 466.5, 258.5, 0, False, False, 0, 3.0, camera))
    bs.update(0.016)
    area.fill((0, 0, 0))
    plugin.draw(area, 1, top, 11.0)
    assert area.get_at(point)[:3] == (0, 0, 0)
    assert len(plugin.player_menu(1)) == 1
    bs.leave()


def test_display_setting_in_the_main_menu(app):
    """The display setting appears in the main menu."""
    from soullink.ui.settings import SettingsScreen

    bs = SettingsScreen(app)
    app.switch(bs)
    row = next(z for z in bs.rows if z.key == "coplayer:display")
    assert (row.title, row.kind, row.values) == ("Display", "selection", ("pokemon", "stylus"))
    assert bs._display_text(row, bs._rows_value(row)) == "Pokémon"
    bs.selection = bs.rows.index(row)
    bs.event(_key(Key.RIGHT))
    assert app.settings.plugin_values["coplayer"] == {"display": "stylus"}
    assert bs._display_text(row, bs._rows_value(row)) == "Marker"
    assert app.plugins.api("coplayer").setting("display") == "stylus"
    bs.draw(app.area)


def _key(key):
    """Posts a key press event of a device."""
    from soullink.input.devices import KeysEvent

    return KeysEvent("c1", key, True)


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
            used |= set(re.findall(r"""["']([a-z_0-9]+)["']""", call))
    used |= {f"display_{w}" for w in ("pokemon", "stylus")}
    assert {"show", "display", "no_partner"} <= used
    assert not used - set(de), sorted(used - set(de))


@pytest.mark.parametrize("abbreviation", ["de", "us"])
def test_core_has_the_texts_no_more(abbreviation):
    """The core no longer holds the plugin's texts."""
    core = language.read_file(language.dir() / f"{abbreviation}.txt")
    assert not [k for k in core if k.startswith("coplayer.")] and "menu.coplayer" not in core
