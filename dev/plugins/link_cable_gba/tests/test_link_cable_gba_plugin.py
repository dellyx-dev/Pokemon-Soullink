"""Link cable GBA in the game: process group only with the plugin, switch under Plugins, pause, fast forward, icon,
texts."""
import re
import string
from pathlib import Path

import pytest

from soullink import language
from soullink.input.keys import Key
from ui_helpers import (FakeProcess, a_press, active_plugin, press, input, plugins_submenu, game_start,
                       player_menu)

PLUGIN = Path(__file__).resolve().parents[1]
ID = "link_cable_gba"


def _can(*processes, link=True):
    """What the worker part reports in ready(): the core can connect."""
    for p in processes:
        p.ready_info["plugins"][ID] = {"link": link}


def _confirm(bs, process):
    """The worker part answers the last command: connected when plugged in."""
    process._new.append(("plugin", ID, process.hat("plugin")[-1][2]))
    bs.update(0.016)


def test_process_group_only_with_plugin(plugin_app, tmp_path):
    """A process group is requested only with the plugin."""
    from soullink.player import ProcessGroup

    app = plugin_app(ID)
    bs = game_start(app, tmp_path / "S")
    assert isinstance(bs.group, ProcessGroup) and all(p.group is bs.group for p in FakeProcess.instances)
    assert [p["id"] for p in FakeProcess.instances[0].plugins] == [ID]
    assert game_start(app, tmp_path / "E", count=1).group is None
    assert game_start(app, tmp_path / "N", system="nds").group is None
    assert not FakeProcess.instances[0].plugins
    app.plugins.set_(ID, False)
    bs = game_start(app, tmp_path / "A")
    assert bs.group is None and all(p.group is None and not p.plugins for p in FakeProcess.instances)


def test_switch_plugs_the_cable_in_and_out(plugin_app, tmp_path):
    """The switch plugs the cable in and out."""
    app = plugin_app(ID)
    bs = game_start(app, tmp_path / "S")
    p1, p2 = FakeProcess.instances
    sp = player_menu(bs, "c1")
    assert "plugins" not in sp.menu_actions
    press(bs, "c1", Key.EAST)
    _can(p1, p2)
    sp = plugins_submenu(bs, "c1")
    assert sp.menu.entries == ["Link cable"] and sp.plugin_rows[0][2] == "Link cable GBA"
    assert sp.plugin_rows[0][1].switch() is False and p2.hat("pause")[-1] == ("pause", True)
    assert "pause" in bs._symbols(sp)
    a_press(bs, "c1")
    assert p2.hat("plugin") == [("plugin", ID, True)] and not p1.hat("plugin")
    assert sp.hint == "Link cable plugged in – connected to everyone else who plugged in"
    assert sp.plugin_rows[0][1].switch() is True and sp.submenu == "plugins"
    assert p2.hat("pause")[-1] == ("pause", False) and p2.mask == 0
    assert "pause" not in bs._symbols(sp)
    assert "link" not in bs._symbols(sp)
    _confirm(bs, p2)
    assert "link" in bs._symbols(sp) and "link" not in bs._symbols(bs.player[0])
    bs.draw(app.area)
    press(bs, "c1", Key.EAST)
    press(bs, "c1", Key.EAST)
    press(bs, "c1", Key.STICK_R)
    assert not p2.hat("tempo") and not sp.fast_forward and sp.hint == "No fast-forward while the link cable is plugged in"
    press(bs, "c1", Key.STICK_R, False)
    sp = plugins_submenu(bs, "c1")
    a_press(bs, "c1")
    assert p2.hat("plugin")[-1] == ("plugin", ID, False) and sp.hint == "Link cable unplugged"
    assert p2.hat("pause")[-1] == ("pause", True) and "pause" in bs._symbols(sp)
    _confirm(bs, p2)
    assert "link" not in bs._symbols(sp)
    press(bs, "c1", Key.EAST)
    press(bs, "c1", Key.EAST)
    press(bs, "c1", Key.STICK_R)
    assert p2.hat("tempo")[-1] == ("tempo", 3)


def test_core_without_link_no_switch(plugin_app, tmp_path):
    """A core without link support gets no switch."""
    app = plugin_app(ID)
    bs = game_start(app, tmp_path / "S")
    _can(*FakeProcess.instances, link=False)
    assert active_plugin(app, ID).player_menu(2) == []
    assert "plugins" not in player_menu(bs, "c1").menu_actions


@pytest.mark.parametrize("can_afterwards", [False, True])
def test_restart_after_crash(plugin_app, tmp_path, can_afterwards):
    """After a crash the cable state is restored."""
    app = plugin_app(ID)
    bs = game_start(app, tmp_path / "S")
    p1, p2 = FakeProcess.instances
    _can(p1, p2)
    plugin = active_plugin(app, ID)
    plugin.player_menu(1)[0].trigger()
    _confirm(bs, p1)
    assert plugin.plugged_in[1] and plugin.connected[1]
    p1.alive = False
    bs.update(0.016)
    input(bs, "keyboard", Key.SOUTH)
    new = FakeProcess.instances[2]
    if can_afterwards:
        _can(new)
    bs.update(0.016)
    assert not plugin.connected[1] and plugin.plugged_in[1] is can_afterwards
    assert new.hat("plugin") == ([("plugin", ID, True)] if can_afterwards else [])
    assert plugin.runs_in_menu(1) is can_afterwards and ("link" in bs._symbols(bs.player[0])) is False


@pytest.mark.parametrize("system, count", [("nds", 2), ("gba", 1)])
def test_not_responsible_stays_still(plugin_app, tmp_path, system, count):
    """An unfit session stays silent."""
    app = plugin_app(ID)
    bs = game_start(app, tmp_path / "S", count=count, system=system)
    assert bs.plugins.plugins == [] and bs.plugins.not_matching == []
    assert [i.id for i in bs.plugins.not_responsible] == [ID] and not FakeProcess.instances[0].plugins
    assert "plugins" not in player_menu(bs, "keyboard").menu_actions


def test_next_game_starts_without_a_cable(plugin_app, tmp_path):
    """The next game starts with the cable unplugged."""
    app = plugin_app(ID)
    plugin = active_plugin(app, ID)
    first = game_start(app, tmp_path / "A")
    _can(*FakeProcess.instances)
    plugin.player_menu(2)[0].trigger()
    second = game_start(app, tmp_path / "B")
    assert plugin.plugged_in == {1: False, 2: False} and plugin.game is not None
    assert first.state == "ended" and second.state == "playing"
    second.leave()
    assert plugin.game is None


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
    assert used == set(de) - {"_name", "_description"}, sorted(used ^ (set(de) - {"_name", "_description"}))


@pytest.mark.parametrize("abbreviation", ["de", "us"])
def test_core_has_the_texts_no_more(abbreviation):
    """The core no longer holds the plugin's texts."""
    core = language.read_file(language.dir() / f"{abbreviation}.txt")
    assert not {"menu.link", "game.link_an", "game.link_from", "game.link_no_fast_forward"} & set(core)
