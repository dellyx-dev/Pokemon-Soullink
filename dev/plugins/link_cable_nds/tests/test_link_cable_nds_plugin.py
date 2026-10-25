"""Tests of the DS link cable plugin in the game."""
import re
import string
from pathlib import Path

import pytest

from soullink import language
from soullink.input.keys import Key
from ui_helpers import FakeProcess, a_press, active_plugin, press, input, plugins_submenu, game_start, \
    player_menu

PLUGIN = Path(__file__).resolve().parents[1]
ID = "link_cable_nds"


def _ports(*processes, first=5000):
    """What the worker part reports in ready(): its UDP port."""
    for i, p in enumerate(processes):
        p.ready_info["plugins"][ID] = {"network_port": first + i}


def _last(process):
    """The last plugin command sent to a process."""
    commands = process.hat("plugin")
    return commands[-1][2] if commands else "nothing"


def test_ports_go_to_the_plugged_in_players(plugin_app, tmp_path):
    """Ports are passed to the plugged-in players."""
    app = plugin_app(ID)
    bs = game_start(app, tmp_path / "S", system="nds")
    assert bs.group is None
    p1, p2 = FakeProcess.instances
    _ports(p1, p2)

    def toggle(device):
        """Plugs the cable of a device in or out."""
        sp = plugins_submenu(bs, device)
        assert sp.menu.entries == ["Link cable"] and sp.plugin_rows[0][2] == "Link cable NDS"
        a_press(bs, device)
        press(bs, device, Key.EAST)
        press(bs, device, Key.EAST)
        return sp

    toggle("keyboard")
    assert _last(p1) == {"id": 0, "targets": {}} and _last(p2) == "nothing"
    toggle("c1")
    assert _last(p2) == {"id": 1, "targets": {0: 5000}}
    assert _last(p1) == {"id": 0, "targets": {1: 5001}}
    count = len(p1.hat("plugin")) + len(p2.hat("plugin"))
    active_plugin(app, ID)._apply()
    assert len(p1.hat("plugin")) + len(p2.hat("plugin")) == count
    sp = toggle("keyboard")
    assert _last(p1) is None and sp.hint == "Link cable unplugged"
    assert _last(p2) == {"id": 1, "targets": {}}


def test_latecomer_after_restart_gets_the_ports(plugin_app, tmp_path):
    """A restarted player gets the ports again."""
    app = plugin_app(ID)
    bs = game_start(app, tmp_path / "S", count=3, system="nds")
    p1, p2, p3 = FakeProcess.instances
    _ports(p1, p2, p3)
    plugin = active_plugin(app, ID)
    for nr in (1, 2, 3):
        plugin.player_menu(nr)[0].trigger()
    assert _last(p3) == {"id": 2, "targets": {0: 5000, 1: 5001}}
    p2.alive = False
    bs.update(0.016)
    input(bs, "c1", Key.SOUTH)
    new = FakeProcess.instances[3]
    _ports(new, first=6001)
    bs.update(0.016)
    assert new.hat("plugin") == [("plugin", ID, {"id": 1, "targets": {0: 5000, 2: 5002}})]
    assert _last(p1) == {"id": 0, "targets": {1: 6001, 2: 5002}}
    assert _last(p3) == {"id": 2, "targets": {0: 5000, 1: 6001}}


def test_restart_without_netpacket_unplugs_the_cable(plugin_app, tmp_path):
    """A restart without netpacket unplugs the cable."""
    app = plugin_app(ID)
    bs = game_start(app, tmp_path / "S", system="nds")
    p1, p2 = FakeProcess.instances
    _ports(p1, p2)
    plugin = active_plugin(app, ID)
    plugin.player_menu(1)[0].trigger()
    plugin.player_menu(2)[0].trigger()
    p1.alive = False
    bs.update(0.016)
    input(bs, "keyboard", Key.SOUTH)
    bs.update(0.016)
    assert not plugin.plugged_in[1] and plugin.player_menu(1) == [] and _last(FakeProcess.instances[2]) == "nothing"
    assert _last(p2) == {"id": 1, "targets": {}}


def test_plugged_in_runs_in_menu_without_fast_forward_with_symbol(plugin_app, tmp_path):
    """Plugged in, the game runs in the menu, fast forward is blocked and the symbol shows."""
    app = plugin_app(ID)
    bs = game_start(app, tmp_path / "S", system="nds")
    p1, p2 = FakeProcess.instances
    _ports(p1, p2)
    sp = plugins_submenu(bs, "c1")
    assert p2.hat("pause")[-1] == ("pause", True) and "pause" in bs._symbols(sp)
    a_press(bs, "c1")
    assert p2.hat("pause")[-1] == ("pause", False) and p2.mask == 0
    assert "link" not in bs._symbols(sp) and "pause" not in bs._symbols(sp)
    p2._new.append(("plugin", ID, True))
    bs.update(0.016)
    assert "link" in bs._symbols(sp)
    bs.draw(app.area)
    press(bs, "c1", Key.EAST)
    press(bs, "c1", Key.EAST)
    press(bs, "c1", Key.STICK_R)
    assert not p2.hat("tempo") and sp.hint == "No fast-forward while the link cable is plugged in"
    press(bs, "c1", Key.STICK_R, False)
    press(bs, "keyboard", Key.STICK_R)
    assert p1.hat("tempo")[-1] == ("tempo", 3)


@pytest.mark.parametrize("system, count", [("gba", 2), ("nds", 1)])
def test_not_responsible_stays_still(plugin_app, tmp_path, system, count):
    """An unfit session stays silent."""
    app = plugin_app(ID)
    bs = game_start(app, tmp_path / "S", count=count, system=system)
    assert bs.plugins.plugins == [] and bs.plugins.not_matching == []
    assert [i.id for i in bs.plugins.not_responsible] == [ID] and not FakeProcess.instances[0].plugins
    assert bs.group is None and "plugins" not in player_menu(bs, "keyboard").menu_actions


def test_without_port_no_switch(plugin_app, tmp_path):
    """Without a port there is no switch."""
    app = plugin_app(ID)
    game_start(app, tmp_path / "S", system="nds")
    assert active_plugin(app, ID).player_menu(1) == []


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
