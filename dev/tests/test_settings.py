"""Tests of the settings screen."""

import json
from pathlib import Path

import pygame
import pytest

from conftest import plugin_create
from soullink.input.devices import KeysEvent
from soullink.input.keys import Key
from ui_helpers import dummy_app

WITH_SETTINGS = """from soullink.plugin.api import Setting, Plugin


class Testplugin(Plugin):
    def settings(self):
        t = self.api.t
        return [Setting("display", t("display"), "selection", "pokemon", ("pokemon", "stylus"),
                            lambda w: t("display_" + w)),
                Setting("frame", t("frame"), "switch", True),
                Setting("tempo", t("tempo"), "number", 3, (1, 2, 3, 4, 5), lambda w: t("tempo_value", value=w))]

    def display_names(self):
        return [("list", self.api.t("list"))]


def create(api):
    return Testplugin(api)
"""
TEXTS = ("_name = {name}\n_description = Shows the other players in your own world\ndisplay = Display\n"
         "display_pokemon = Pokémon\ndisplay_stylus = Stylus\nframe = Frame around the game picture\n"
         "tempo = Speed\ntempo_value = Level {{value}}\nlist = List {name}\n")


@pytest.fixture
def app(monkeypatch, tmp_path):
    """App with a dummy window."""
    a = dummy_app(monkeypatch, tmp_path)
    yield a
    a.close()


@pytest.fixture
def app_with_plugins(monkeypatch, tmp_path):
    """App with two sample plugins."""
    for pid, name in (("alpha", "Other players"), ("beta", "Link cable GBA")):
        plugin_create(tmp_path / "plugins", pid, code=WITH_SETTINGS, texts={"us": TEXTS.format(name=name)})
    a = dummy_app(monkeypatch, tmp_path)
    yield a
    a.close()


def press(bs, key):
    """Sends a key press to the screen."""
    bs.event(KeysEvent("c1", key, True))


def _open(app):
    """Opens the settings screen."""
    from soullink.ui.settings import SettingsScreen
    from soullink.ui.start import SETTINGS

    start = app.screen
    start.menu.selection = SETTINGS
    press(start, Key.SOUTH)
    assert isinstance(app.screen, SettingsScreen)
    return app.screen


def _row(bs, key):
    """Selects the row with the given key."""
    bs.selection = [z[0] for z in bs.rows].index(key)


def _saved(app):
    """The stored settings.json content."""
    return json.loads((app.base / "settings.json").read_text(encoding="utf-8"))


def test_values_change_and_save(app):
    """Changing values saves the settings."""
    bs = _open(app)
    _row(bs, "fast_forward_factor")
    press(bs, Key.RIGHT)
    assert app.settings.fast_forward_factor == 4 and _saved(app)["fast_forward_factor"] == 4
    _row(bs, "ds_view")
    press(bs, Key.LEFT)
    assert _saved(app)["ds_view"] == "columns"
    _row(bs, "autosave_minutes")
    for _ in range(10):
        press(bs, Key.RIGHT)
    assert app.settings.autosave_minutes == 30
    _row(bs, "music_volume")
    press(bs, Key.LEFT)
    assert app.music.volume == 49 and _saved(app)["music_volume"] == 49
    bs.draw(app.area)
    press(bs, Key.EAST)
    from soullink.ui.start import StartScreen

    assert isinstance(app.screen, StartScreen)


def test_dir_choice(app, tmp_path):
    """A folder is chosen in the browser."""
    roms = tmp_path / "Games" / "gba"
    roms.mkdir(parents=True)
    (tmp_path / "Games" / "nds").mkdir()
    bs = _open(app)
    _row(bs, "rom_dir")
    app.settings.rom_dir = str(tmp_path / "Games" / "missing")
    press(bs, Key.SOUTH)
    choice = bs.choice
    assert choice is not None and choice.path == tmp_path / "Games"
    assert [t for t, _, _ in choice.entries][2:] == ["gba", "nds"]
    bs.draw(app.area)
    choice.selection = 2
    press(bs, Key.SOUTH)
    assert choice.path == roms
    press(bs, Key.SOUTH)
    assert bs.choice is None and _saved(app)["rom_dir"] == str(Path("Games") / "gba")
    assert app.rom_dir == roms


def test_dir_choice_up_and_cancel(app, tmp_path):
    """The folder browser goes up and cancels."""
    bs = _open(app)
    _row(bs, "presets_dir")
    before = app.settings.presets_dir
    press(bs, Key.SOUTH)
    start = bs.choice.path
    bs.choice.selection = 1
    press(bs, Key.SOUTH)
    assert bs.choice.path == start.parent
    press(bs, Key.EAST)
    assert bs.choice is None and app.settings.presets_dir == before


def test_music_hold_accelerates_and_saves_on_release(app):
    """Holding the music slider accelerates and saves on release."""
    bs = _open(app)
    _row(bs, "music_volume")
    app.input(KeysEvent("c1", Key.RIGHT, True))
    assert app.music.volume == 51 and _saved(app)["music_volume"] == 51
    assert app.hold.kind == "slider"
    for _ in range(5):
        app.hold.next_ = 0.0
        app.repeat()
    assert app.music.volume == 56 and _saved(app)["music_volume"] == 51
    app.input(KeysEvent("c1", Key.RIGHT, False))
    assert _saved(app)["music_volume"] == 56
    app.hold.next_ = 0.0
    app.repeat()
    assert app.music.volume == 56


def test_hold_scrolls_rows_but_does_not_cycle_the_language(app):
    """Holding scrolls rows but does not cycle the language."""
    bs = _open(app)
    app.input(KeysEvent("c1", Key.DOWN, True))
    app.hold.next_ = 0.0
    app.repeat()
    assert bs.selection == 2
    app.input(KeysEvent("c1", Key.DOWN, False))
    _row(bs, "language")
    app.input(KeysEvent("c1", Key.RIGHT, True))
    assert app.hold.key is None


def test_dir_status(tmp_path):
    """Folder status texts are computed."""
    from soullink.ui import graphics
    from soullink.ui.settings import dir_count, status_text

    roms = tmp_path / "gba"
    roms.mkdir()
    for name in ("a.gba", "b.GBA", "c.zip", "d.nds", "e.txt"):
        (roms / name).write_bytes(b"x")
    (roms / "subdir.gba").mkdir()
    assert dir_count(roms, "rom_dir") == 3
    sessions = tmp_path / "Sessions"
    (sessions / "one").mkdir(parents=True)
    (sessions / "one" / "session.json").write_text("{}", encoding="utf-8")
    (sessions / "broken").mkdir()
    assert dir_count(sessions, "sessions_dir") == 1
    assert dir_count(tmp_path / "missing", "presets_dir") is None
    assert status_text("rom_dir", 3) == ("3 games", graphics.OK)
    assert status_text("sessions_dir", 1) == ("1 session", graphics.OK)
    assert status_text("sound_dir", 0)[1] == graphics.DIMMED
    assert status_text("presets_dir", None) == ("Folder missing", graphics.ERROR)


def test_settings_draw_all_rows(app):
    """All rows draw."""
    import time

    bs = _open(app)
    end = time.monotonic() + 5
    while len(bs.status) < 5 and time.monotonic() < end:
        time.sleep(0.01)
    assert bs.status["sound_dir"] == 0
    for selection in range(len(bs.rows)):
        bs.selection = selection
        bs.draw(app.area)


def _key(bs):
    """Keys of all rows."""
    return [z.key for z in bs.rows]


def _groups(bs):
    """Headings of all groups."""
    return [value for kind, value in bs._layout() if kind in ("group", "plugin_group")]


def test_without_plugins_no_plugin_group(app):
    """Without plugins there is no plugin group."""
    bs = _open(app)
    assert _groups(bs) == ["General", "Game", "Folders"]
    assert not any(s.startswith("plugin:") for s in _key(bs))


def test_plugin_row_switches_and_shows_its_settings(app_with_plugins):
    """A plugin row switches the plugin and shows its settings."""
    app = app_with_plugins
    bs = _open(app)
    assert _groups(bs) == ["General", "Game", "Folders", "Plugins"]
    assert [s for s in _key(bs) if ":" in s] == ["plugin:alpha", "plugin:beta"]
    _row(bs, "plugin:alpha")
    press(bs, Key.SOUTH)
    assert app.plugins.enabled("alpha") and _saved(app)["plugins"] == {"alpha": True}
    assert bs.rows[bs.selection].key == "plugin:alpha"
    assert _groups(bs) == ["General", "Game", "Folders", "Plugins", "Other players"]
    assert ("plugin_group", "Other players") in bs._layout()
    assert [s for s in _key(bs) if s.startswith("alpha:")] == ["alpha:display", "alpha:frame",
                                                                      "alpha:tempo"]
    assert bs._description() == "Shows the other players in your own world"
    press(bs, Key.LEFT)
    assert not app.plugins.enabled("alpha") and _saved(app)["plugins"] == {"alpha": False}
    assert not any(s.startswith("alpha:") for s in _key(bs))
    press(bs, Key.RIGHT)
    press(bs, Key.RIGHT)
    assert app.plugins.enabled("alpha")
    assert bs.repeat_kind(Key.RIGHT) is None


def test_plugin_setting_changes_plugin_values(app_with_plugins):
    """A plugin setting changes the stored plugin values."""
    app = app_with_plugins
    app.plugins.set_("alpha", True)
    bs = _open(app)
    api = app.plugins.api("alpha")
    _row(bs, "alpha:display")
    assert bs.repeat_kind(Key.RIGHT) is None
    press(bs, Key.RIGHT)
    assert api.setting("display") == "stylus"
    assert _saved(app)["plugin_values"] == {"alpha": {"display": "stylus"}}
    press(bs, Key.RIGHT)
    assert api.setting("display") == "pokemon"
    _row(bs, "alpha:frame")
    press(bs, Key.SOUTH)
    assert api.setting("frame") is False and _saved(app)["plugin_values"]["alpha"]["frame"] is False
    _row(bs, "alpha:tempo")
    assert bs.repeat_kind(Key.RIGHT) == "list"
    for _ in range(5):
        press(bs, Key.RIGHT)
    assert api.setting("tempo") == 5
    press(bs, Key.LEFT)
    assert _saved(app)["plugin_values"]["alpha"]["tempo"] == 4
    assert bs._display_text(bs.rows[bs.selection], 4) == "Level 4"
    for selection in range(len(bs.rows)):
        bs.selection = selection
        bs.draw(app.area)


def test_free_field(app_with_plugins):
    """The free-field setting cycles through the displays."""
    app = app_with_plugins
    bs = _open(app)
    _row(bs, "free_field")
    assert bs.rows[bs.selection].values == ("core.session", "alternating")
    assert bs._value("free_field") == "core.session"
    app.plugins.set_("alpha", True)
    app.plugins.set_("beta", True)
    app.settings.free_field = "core.soullink"
    bs = _open_new(app)
    _row(bs, "free_field")
    row = bs.rows[bs.selection]
    assert row.values == ("core.session", "alpha.list", "beta.list", "alternating")
    assert [bs._display_text(row, w) for w in row.values] == \
        ["Session", "List Other players", "List Link cable GBA", "Rotating"]
    assert bs._value("free_field") == "alpha.list"
    assert bs.repeat_kind(Key.RIGHT) is None
    press(bs, Key.RIGHT)
    assert app.settings.free_field == "beta.list" and _saved(app)["free_field"] == "beta.list"
    press(bs, Key.RIGHT)
    press(bs, Key.RIGHT)
    assert _saved(app)["free_field"] == "core.session"
    press(bs, Key.LEFT)
    assert _saved(app)["free_field"] == "alternating"


def _open_new(app):
    """Opens the settings screen as new, after plugins changed."""
    from soullink.ui.settings import SettingsScreen

    bs = SettingsScreen(app)
    app.switch(bs)
    return bs


def test_plugin_status_incompatible_broken_error(monkeypatch, tmp_path):
    """Incompatible, broken and failing plugins show their status."""
    from soullink.ui.settings import PLUGIN

    dir = tmp_path / "plugins"
    plugin_create(dir, "old", data={"api": 99})
    plugin_create(dir, "broken").joinpath("plugin.json").write_text("{", encoding="utf-8")
    plugin_create(dir, "throws", code="raise RuntimeError('Import')\n")
    (dir / "Mein-Plugin").mkdir()
    app = dummy_app(monkeypatch, tmp_path)
    try:
        bs = _open(app)
        _row(bs, "plugin:old")
        press(bs, Key.SOUTH)
        assert not app.plugins.enabled("old")
        assert bs._description() == "Built for plugin API 99, this program has API 1"
        _row(bs, "plugin:broken")
        press(bs, Key.SOUTH)
        assert not app.plugins.enabled("broken") and bs._description() == "plugin.json is missing or invalid"
        _row(bs, "plugin:Mein-Plugin")
        assert bs._description() == "Folder name is not a valid plugin ID (only a–z, 0–9 and _)"
        _row(bs, "plugin:throws")
        press(bs, Key.SOUTH)
        assert app.plugins.enabled("throws") and app.plugins.info("throws").status == "error"
        assert "error.log" in bs._description() and (tmp_path / "error.log").exists()
        press(bs, Key.SOUTH)
        assert not app.plugins.enabled("throws")
        assert [z.kind for z in bs.rows if z.plugin] == [PLUGIN] * 4
        for selection in range(len(bs.rows)):
            bs.selection = selection
            bs.draw(app.area)
    finally:
        app.close()


def test_new_plugin_appears_when_opened(app, tmp_path):
    """A newly added plugin appears when the screen opens."""
    bs = _open(app)
    assert not any(s.startswith("plugin:") for s in _key(bs))
    plugin_create(tmp_path / "plugins", "later")
    bs._back()
    bs = _open(app)
    assert "plugin:later" in _key(bs)


def test_settings_with_plugins_draw_and_render_to_png(app_with_plugins, tmp_path):
    """The settings screen with plugins draws and renders to a PNG."""
    from soullink.ui import graphics

    app = app_with_plugins
    app.plugins.set_("alpha", True)
    bs = _open(app)
    for name, key in (("settings_plugins.png", "plugin:alpha"),
                             ("settings_plugin_values.png", "alpha:display")):
        _row(bs, key)
        app.area.blit(graphics.background(app.size), (0, 0))
        bs.draw(app.area)
        pygame.image.save(app.area, str(tmp_path / name))


def test_plugin_number_hold_saves_on_release(app_with_plugins):
    """Holding a numeric plugin setting saves on release."""
    app = app_with_plugins
    app.plugins.set_("alpha", True)
    bs = _open(app)
    _row(bs, "alpha:tempo")
    app.input(KeysEvent("c1", Key.LEFT, True))
    assert _saved(app)["plugin_values"]["alpha"]["tempo"] == 2
    app.hold.next_ = 0.0
    app.repeat()
    assert app.plugins.value("alpha", "tempo") == 1 and _saved(app)["plugin_values"]["alpha"]["tempo"] == 2
    app.input(KeysEvent("c1", Key.LEFT, False))
    assert _saved(app)["plugin_values"]["alpha"]["tempo"] == 1
    app.input(KeysEvent("c1", Key.RIGHT, True))
    app.hold.next_ = 0.0
    app.repeat()
    bs._back()
    assert _saved(app)["plugin_values"]["alpha"]["tempo"] == 3
