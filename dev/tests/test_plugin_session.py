"""Tests of plugins in the running game."""
import time

import pygame
import pytest

from conftest import plugin_create
from soullink.input.keys import Key
from ui_helpers import FakeProcess, dummy_app, input, fake_session

PROBE = '''
from soullink.plugin.api import Display, MenuEntry, Plugin, Tab


class ProbeTab(Tab):
    def __init__(self, plugin, nr, rid, replaced, position):
        self.plugin, self.nr, self.id, self.replaced, self.position = plugin, nr, rid, replaced, position
        self.keys = []

    def title(self, short=False):
        return "PRB" if short else "Probe"

    def event(self, key):
        self.keys.append(key)
        return key.name == "SOUTH"

    def draw(self, area, rect, u, time):
        if "tab_draw" in self.plugin.throw:
            raise RuntimeError("broken in Tab")
        self.plugin.calls.append(("tab_draw", self.nr))

    def hints(self):
        return [("A", "Probe")]


class ProbeDisplay(Display):
    ram_interval = 2.0

    def __init__(self, plugin):
        self.plugin = plugin

    def draw(self, area, rect, u, time):
        self.plugin.calls.append(("display", rect.width > 0))


class Probe(Plugin):
    def __init__(self, api):
        super().__init__(api)
        self.calls, self.events, self.triggered = [], [], []
        self.throw = set()
        self.on = False
        self.fits_value = True
        self.tab = [(api.id, None, 15)]
        self.menu = True
        self.runs = set()
        self.fast_forward = True
        self.symbol = []
        self.group = False
        self.command_data = None

    def _hook(self, name, *args):
        self.calls.append((name, *args))
        if name in self.throw:
            raise RuntimeError(f"broken in {name}")

    def display_names(self):
        return [("map", "Probe-Map")]

    def fits(self, session):
        return self.fits_value

    def process_group(self, session):
        return self.group

    def session_start(self, game):
        self.game = game
        self._hook("session_start")

    def update(self, dt):
        self._hook("update")
        if self.command_data is not None:
            self.game.worker_command(1, self.command_data)

    def event(self, nr, e):
        self._hook("event")
        self.events.append((nr, e))

    def player_menu(self, nr):
        if not self.menu or (isinstance(self.menu, set) and nr not in self.menu):
            return []
        return [MenuEntry("action", "Probe-Action", lambda: self.triggered.append(nr)),
                MenuEntry("switch", "Probe-Switch", self.toggle, switch=lambda: self.on),
                MenuEntry("gray", "Probe-Gray", lambda: self.triggered.append("gray"), reason="not right now"),
                MenuEntry("overlay", "Probe-Overlay", lambda: self.game.overlay_open(nr, "probe"))]

    def toggle(self):
        if "switch" in self.throw:
            raise RuntimeError("broken in Switch")
        self.on = not self.on

    def overlay_tab(self, nr):
        return [ProbeTab(self, nr, *r) for r in self.tab]

    def display(self, display_id):
        return ProbeDisplay(self) if display_id == "map" else None

    def draw_game_frame(self, area, nr, target, source):
        self._hook("draw_game_frame", nr, source, area.get_clip() == target)

    def symbols(self, nr):
        return list(self.symbol)

    def runs_in_menu(self, nr):
        return nr in self.runs

    def fast_forward_allowed(self, nr):
        return self.fast_forward

    def save(self):
        self._hook("save")

    def session_end(self):
        self._hook("session_end")


def create(api):
    return Probe(api)
'''


@pytest.fixture
def app(monkeypatch, tmp_path):
    """App with a dummy window and plugin support."""
    a = dummy_app(monkeypatch, tmp_path)
    yield a
    a.close()


def _create(app, pid="probe", code=PROBE, **data):
    """Creates and enables a probe plugin and returns its object."""
    plugin_create(app.base / "plugins", pid, code=code, data=data or None,
                   texts={"us": f"_name = {pid.title()}-Plugin\n"})
    app.plugins.new_read()
    app.plugins.set_(pid, True)
    return dict((i.id, p) for i, p in app.plugins.active())[pid]


def _game(app, tmp_path, count=2, system="gba", name="S", devices=("keyboard", "c1", "c2", "c3")):
    """Game screen with the given number of players."""
    from soullink.ui.game import GameScreen

    FakeProcess.instances = []
    bs = GameScreen(app, fake_session(tmp_path / name, count, system=system), list(devices[:count]),
                         process_factory=FakeProcess)
    app.switch(bs)
    bs.update(0.016)
    return bs


def press(bs, device, key, pressed=True):
    """Sends a key press or release of a device to the game."""
    input(bs, device, key, pressed)
    bs.update(0.016)


def _menu(bs, device="c1"):
    """Opens the player menu of a device."""
    press(bs, device, Key.L2)
    press(bs, device, Key.L2, False)


def _choose(bs, nr, action, device="c1"):
    """Chooses an action in the player's menu."""
    sp = bs.player[nr - 1]
    sp.menu.selection = sp.menu_actions.index(action)
    press(bs, device, Key.SOUTH)


def _log(app):
    """Content of error.log."""
    path = app.base / "error.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_without_plugins_no_submenu(app, tmp_path):
    """Without plugins there is no "Plugins" submenu."""
    bs = _game(app, tmp_path)
    _menu(bs)
    sp = bs.player[1]
    assert "overlay" in sp.menu_actions and "plugins" not in sp.menu_actions
    assert bs.plugins.plugins == [] and bs.plugins.worker_plugins() == []


def test_unfit_plugin_is_inactive_for_the_session(app, tmp_path):
    """A plugin that does not fit is inactive for the session."""
    probe = _create(app)
    probe.fits_value = "NDS only"
    other = _create(app, "other")
    bs = _game(app, tmp_path)
    assert [i.id for i, _ in bs.plugins.plugins] == ["other"]
    assert [(i.id, reason) for i, reason in bs.plugins.not_matching] == [("probe", "NDS only")]
    assert not probe.calls and bs.player[0].types.find("probe") is None
    assert "probe.map" not in [a for a, _, _ in bs.field.show] and other.calls[0] == ("session_start",)


def test_session_start_with_game_api(app, tmp_path):
    """session_start receives the game API."""
    probe = _create(app, worker="worker")
    bs = _game(app, tmp_path)
    api = probe.game
    assert api.id == "probe" and api.session is bs.session and api.t("_name") == "Probe-Plugin"
    assert api.player_numbers() == [1, 2] and api.playtime == bs.playtime
    info = api.player_info(2)
    assert (info["system"], info["code"], info["family"], info["game_name"]) == ("gba", "BPRD", "frlg", "FireRed")
    assert info["rom"] == bs.session.rom(2) and info["dir"] == bs.session.player_dir(2)
    assert api.ready_info(1)["plugins"] == {"probe": {}}
    assert api.dex(1) is None and api.dex_error(1) is None and api.location_name(1, 5) == "Location #5"
    dir = api.data_dir
    assert dir == bs.session.dir / "plugins" / "probe" and dir.is_dir()
    p1, p2 = FakeProcess.instances
    assert p1.plugins == [{"id": "probe", "dir": str(app.base / "plugins" / "probe"), "module": "worker",
                           "slot": 0}]
    api.worker_command(2, {"on": True})
    assert p2.hat("plugin") == [("plugin", "probe", {"on": True})] and not p1.hat("plugin")
    assert api.worker_data(1) is None
    p1.slots[0] = b"\x01\x02"
    assert api.worker_data(1) == b"\x01\x02"
    bs.player[0].crashed = True
    assert api.worker_data(1) is None
    bs.player[0].crashed = False
    api.report(1, "Hello")
    assert bs.player[0].hint == "Hello" and bs.player[1].hint != "Hello"
    p1.commands.clear()
    api.ram_request()
    assert p1.hat("ram")
    with pytest.raises(ValueError):
        api.player_info(7)


FIELDS = """
from soullink.plugin.api import Plugin


class Fields(Plugin):
    def session_start(self, game):
        numbers = game.player_numbers()
        self.fields = {"playtime": game.playtime, "dir": game.data_dir, "numbers": numbers,
                       "session": game.session.name, "info": [game.player_info(nr)["code"] for nr in numbers],
                       "ready": [game.ready_info(nr)["fps"] for nr in numbers], "dex": game.dex(1),
                       "dex_error": game.dex_error(1), "location": game.location_name(1, 5), "data": game.worker_data(1),
                       "setting": game.setting("exists_not"), "text": game.t("_name")}
        game.report(1, "Fields started")
        game.ram_request()
        game.worker_command(2, "start")


def create(api):
    return Fields(api)
"""


def test_session_start_can_read_all_fields(app, tmp_path):
    """session_start can read all fields of the game API."""
    fields = _create(app, "fields", code=FIELDS, worker="worker")
    bs = _game(app, tmp_path)
    assert [i.id for i, _ in bs.plugins.plugins] == ["fields"] and _log(app) == ""
    assert fields.fields == {"playtime": 0.0, "dir": bs.session.dir / "plugins" / "fields", "numbers": [1, 2],
                             "session": "Test ×2", "info": ["BPED", "BPRD"], "ready": [59.7275, 59.7275],
                             "dex": None, "dex_error": None, "location": "Location #5", "data": None, "setting": None,
                             "text": "Fields-Plugin"}
    p1, p2 = FakeProcess.instances
    assert bs.player[0].hint == "Fields started" and p1.hat("ram") and p2.hat("plugin")


def test_player_menu_submenu_plugins(app, tmp_path):
    """The player menu offers the "Plugins" submenu."""
    probe = _create(app)
    bs = _game(app, tmp_path)
    sp = bs.player[1]
    _menu(bs)
    assert sp.menu_actions.index("plugins") == sp.menu_actions.index("overlay") + 1
    assert [a for a, w in bs._menu_layout(sp) if a == "group"] == ["group"] * 2
    _choose(bs, 2, "plugins")
    assert sp.submenu == "plugins" and sp.menu.entries == ["Probe-Action", "Probe-Switch", "Probe-Gray",
                                                                   "Probe-Overlay"]
    assert bs._menu_layout(sp) == [("group", "Probe-Plugin"), ("row", 0), ("row", 1), ("row", 2),
                                    ("row", 3)]
    assert "pause" in bs._symbols(sp) and FakeProcess.instances[1].hat("pause")[-1] == ("pause", True)
    bs.draw(app.area)
    press(bs, "c1", Key.SOUTH)
    assert probe.triggered == [2] and sp.submenu == "plugins"
    press(bs, "c1", Key.DOWN)
    press(bs, "c1", Key.SOUTH)
    assert probe.on and sp.menu.selection == 1 and sp.submenu == "plugins"
    bs.draw(app.area)
    press(bs, "c1", Key.DOWN)
    press(bs, "c1", Key.SOUTH)
    assert probe.triggered == [2] and sp.submenu == "plugins"
    press(bs, "c1", Key.EAST)
    assert not sp.submenu and sp.menu_actions[sp.menu.selection] == "plugins"
    _choose(bs, 2, "plugins")
    sp.menu.selection = 3
    press(bs, "c1", Key.SOUTH)
    assert sp.menu is None and sp.types_open and sp.types.active.id == "probe" and "menu" not in sp.pauses
    probe.menu = False
    bs.overlay_open(2)
    press(bs, "c1", Key.EAST)
    _menu(bs)
    assert "plugins" not in sp.menu_actions
    bs.draw(app.area)


def test_submenu_only_for_players_with_entries(app, tmp_path):
    """The submenu appears only for players with entries."""
    probe = _create(app)
    probe.menu = {2}
    bs = _game(app, tmp_path)
    _menu(bs, "keyboard")
    _menu(bs, "c1")
    one, two = bs.player
    assert "plugins" not in one.menu_actions and "plugins" in two.menu_actions
    mismatching = _create(app, "zz_nds")
    mismatching.fits_value = "NDS only"
    bs = _game(app, tmp_path, name="T")
    _menu(bs, "keyboard")
    one = bs.player[0]
    assert "plugins" in one.menu_actions
    _choose(bs, 1, "plugins", "keyboard")
    assert one.menu.entries == ["Zz_Nds-Plugin"] and one.plugin_rows[0][2] == "Not active"


def test_submenu_without_entries_returns_to_the_player_menu(app, tmp_path):
    """A submenu that runs out of entries returns to the player menu."""
    probe = _create(app)
    bs = _game(app, tmp_path)
    sp = bs.player[1]
    _menu(bs)
    _choose(bs, 2, "plugins")
    probe.menu = False
    press(bs, "c1", Key.SOUTH)
    assert probe.triggered == [2] and not sp.submenu
    assert "plugins" not in sp.menu_actions and sp.menu_actions[sp.menu.selection] == "overlay"
    probe.menu = True
    press(bs, "c1", Key.EAST)
    _menu(bs)
    _choose(bs, 2, "plugins")
    probe.menu = False
    bs.plugins.changed = True
    bs.update(0.016)
    assert not sp.submenu and sp.menu is not None and "plugins" not in sp.menu_actions


def test_only_unfit_plugins_show_the_entry_with_a_reason(app, tmp_path):
    """Only unfit plugins still show the entry, with their reason."""
    probe = _create(app)
    probe.fits_value = "NDS only"
    bs = _game(app, tmp_path)
    sp = bs.player[1]
    _menu(bs)
    assert "plugins" in sp.menu_actions
    _choose(bs, 2, "plugins")
    assert sp.menu.entries == ["Probe-Plugin"] and sp.plugin_rows[0][1].reason == "NDS only"
    assert bs._menu_layout(sp) == [("group", "Not active"), ("row", 0)]
    bs.draw(app.area)


@pytest.mark.parametrize("value", [None, ""])
def test_submenu_shows_unfit_plugins_greyed_out(app, tmp_path, value):
    """The submenu shows unfit plugins greyed out."""
    _create(app)
    mismatching = _create(app, "zz_nds")
    mismatching.fits_value = value
    bs = _game(app, tmp_path)
    sp = bs.player[1]
    _menu(bs)
    _choose(bs, 2, "plugins")
    assert sp.menu.entries[-1] == "Zz_Nds-Plugin" and bs._menu_layout(sp)[-2] == ("group", "Not active")
    assert sp.plugin_rows[-1][1].reason == "does not fit this session"
    bs.draw(app.area)


def test_fits_false_stays_silent(app, tmp_path):
    """fits() returning False hides the plugin silently."""
    probe = _create(app, worker="worker")
    probe.fits_value = False
    bs = _game(app, tmp_path)
    assert bs.plugins.plugins == [] and bs.plugins.not_matching == [] and bs.plugins.worker_plugins() == []
    assert not probe.calls and bs.player[0].types.find("probe") is None
    assert all(not p.plugins for p in FakeProcess.instances)
    _menu(bs)
    assert "plugins" not in bs.player[1].menu_actions
    other = _create(app, "other")
    other.fits_value = "NDS only"
    bs = _game(app, tmp_path, name="T")
    _menu(bs)
    _choose(bs, 2, "plugins")
    assert bs.player[1].menu.entries == ["Other-Plugin"]


def test_overlay_open_waits_while_the_player_is_busy(app, tmp_path):
    """overlay_open does nothing while the player is in another menu."""
    from soullink.ui.keyboard import VirtualKeyboard

    _create(app)
    bs = _game(app, tmp_path)
    sp = bs.player[1]
    bs._keys_open(sp)
    bs.overlay_open(2, "probe")
    assert not sp.types_open and sp.keys_menu is not None and "keys" in sp.pauses
    bs._keys_done(sp)
    sp.profile_input = VirtualKeyboard("", 10)
    bs.overlay_open(2)
    assert not sp.types_open and sp.profile_input is not None
    sp.profile_input = None
    _menu(bs)
    _choose(bs, 2, "end")
    bs.overlay_open(2)
    assert not sp.types_open and sp.menu_question == "save"
    press(bs, "c1", Key.EAST)
    press(bs, "c1", Key.EAST)
    sp.device_set(None)
    bs.overlay_open(2)
    assert not sp.types_open
    sp.device_set("c1")
    bs.overlay_open(2, "probe")
    assert sp.types_open and sp.types.active.id == "probe"


def test_tab_with_position_and_replaced(app, tmp_path):
    """Tabs are ordered by position and can replace others."""
    probe = _create(app)
    probe.tab = [("probe", None, 15), ("my_types", "types", 40), ("still_a", "types", 41)]
    bs = _game(app, tmp_path)
    sp = bs.player[0]
    assert [r.id for r in sp.types.tab] == ["probe", "my_types"]
    assert "still_a" in _log(app)
    assert sp.types.find("probe").title(short=True) == "PRB"
    bs._types_open(sp)
    sp.types.show("probe")
    press(bs, "keyboard", Key.SOUTH)
    press(bs, "keyboard", Key.EAST)
    assert not sp.types_open and sp.types.find("probe").target.keys == [Key.SOUTH, Key.EAST]


def test_display_in_free_field_and_alternating(app, tmp_path):
    """Displays appear in the free field and can alternate."""
    probe = _create(app)
    app.settings.free_field = "probe.map"
    bs = _game(app, tmp_path, count=3)
    assert [a for a, _, _ in bs.field.show] == ["probe.map"]
    assert bs.field.current("probe.map", 0)[1] == "Probe-Map"
    bs.draw(app.area)
    assert ("display", True) in probe.calls
    bs.ram_requested = time.monotonic() - 2.5
    bs.update(0.016)
    assert all(p.hat("ram") for p in FakeProcess.instances)
    app.settings.free_field = "alternating"
    bs.time = 0.0
    seen = []
    for _ in range(4):
        seen.append(bs.field.current("alternating", bs.time)[0])
        bs.update(15.0)
    assert seen == ["probe.map", "core.session", "probe.map", "core.session"]
    app.settings.free_field = ""
    assert bs.field.current("", 0)[0] == "probe.map"


@pytest.mark.parametrize("hook, message", [("update", "RuntimeError: broken in update"),
                                           ("event", "RuntimeError: broken in event"),
                                           ("draw_game_frame", "RuntimeError: broken in draw_game_frame"),
                                           ("tab_draw", "RuntimeError: broken in Tab")])
def test_hook_error_switches_the_plugin_off_for_the_session(app, tmp_path, hook, message):
    """A hook error switches the plugin off for the session."""
    probe = _create(app)
    other = _create(app, "other")
    bs = _game(app, tmp_path)
    sp = bs.player[0]
    sp.images["gba"] = pygame.Surface(bs._screens(0)[0][0].size)
    bs._types_open(sp)
    sp.types.show("probe")
    probe.throw.add(hook)
    FakeProcess.instances[0]._new.append(("sram",))
    bs.update(0.016)
    bs.draw(app.area)
    bs.update(0.016)
    assert [i.id for i, _ in bs.plugins.plugins] == ["other"]
    assert message in _log(app) and "Plugin probe" in _log(app)
    assert probe.calls.count(("session_end",)) == 1
    assert all("Probe-Plugin" in (s.hint or "") for s in bs.player)
    assert [i.id for i, _ in app.plugins.active()] == ["other", "probe"]
    assert sp.types.find("probe") is None and sp.types_open
    counter = len(probe.calls)
    press(bs, "c1", Key.SOUTH)
    bs.draw(app.area)
    assert FakeProcess.instances[1].mask and len(probe.calls) == counter
    assert ("update",) in other.calls[-3:]
    bs.leave()
    assert probe.calls.count(("session_end",)) == 1 and other.calls[-1] == ("session_end",)


def test_error_in_session_end_is_called_only_once(app, tmp_path):
    """An error in session_end is handled with a single call."""
    probe = _create(app)
    other = _create(app, "other")
    probe.throw = {"session_end"}
    bs = _game(app, tmp_path)
    bs.leave()
    assert probe.calls.count(("session_end",)) == 1 and _log(app).count("broken in session_end") == 1
    assert other.calls.count(("session_end",)) == 1
    bs.leave()
    assert probe.calls.count(("session_end",)) == 1


def test_error_in_session_end_only_goes_to_the_log(app, tmp_path):
    """An error in session_end only goes to the log."""
    probe = _create(app)
    probe.throw = {"update", "session_end"}
    bs = _game(app, tmp_path)
    bs.update(0.016)
    assert bs.plugins.plugins == [] and "broken in update" in _log(app)
    assert "broken in session_end" in _log(app) and probe.calls.count(("session_end",)) == 1
    bs.leave()
    assert probe.calls.count(("session_end",)) == 1


def test_unpicklable_worker_command_is_a_plugin_error(app, tmp_path):
    """A worker command that cannot be pickled is a plugin error."""
    probe = _create(app, worker="worker")
    bs = _game(app, tmp_path)
    probe.command_data = lambda: "not picklable"
    bs.update(0.016)
    assert bs.plugins.plugins == [] and "pickle" in _log(app).lower()
    assert not FakeProcess.instances[0].hat("plugin")
    with pytest.raises(Exception):
        probe.game.worker_command(2, lambda: 1)
    probe.game.worker_command(2, {"goes": [1, 2]})
    assert FakeProcess.instances[1].hat("plugin") == [("plugin", "probe", {"goes": [1, 2]})]


def test_error_in_switch_and_unknown_symbol(app, tmp_path):
    """Errors in switches and unknown symbols are handled."""
    probe = _create(app)
    bs = _game(app, tmp_path)
    sp = bs.player[1]
    _menu(bs)
    _choose(bs, 2, "plugins")
    probe.throw.add("switch")
    sp.menu.selection = 1
    press(bs, "c1", Key.SOUTH)
    assert bs.plugins.plugins == [] and "broken in Switch" in _log(app)
    assert sp.submenu == "plugins" and sp.menu.entries == ["Probe-Plugin"]
    assert sp.plugin_rows[0][1].reason == "error – off for this session" and sp.plugin_rows[0][2] == "Not active"
    bs.draw(app.area)
    second = _create(app, "second")
    second.symbol = ["flash", "link"]
    bs2 = _game(app, tmp_path, name="T")
    for _ in range(3):
        bs2.draw(app.area)
        bs2.update(0.016)
    assert "second" in [i.id for i, _ in bs2.plugins.plugins]
    assert "link" in bs2._symbols(bs2.player[0]) and "flash" not in bs2._symbols(bs2.player[0])
    assert _log(app).count("\"flash\"") == 1


def test_symbols_and_draw_game_frame(app, tmp_path):
    """Symbols and frame drawing hooks work."""
    probe = _create(app)
    probe.symbol = ["link"]
    bs = _game(app, tmp_path, system="nds")
    sp = bs.player[0]
    assert "link" in bs._symbols(sp)
    for source in ("top", "bottom"):
        target = next(r for r, q in bs._screens(0) if q == source)
        sp.images[source] = pygame.Surface(target.size)
    bs.draw(app.area)
    calls = [a for a in probe.calls if a[0] == "draw_game_frame"]
    assert ("draw_game_frame", 1, "top", True) in calls and ("draw_game_frame", 1, "bottom", True) in calls
    assert not any(a[1] == 2 for a in calls)


def test_runs_in_menu_prevents_pause(app, tmp_path):
    """runs_in_menu keeps the game from pausing."""
    probe = _create(app)
    probe.runs = {2}
    bs = _game(app, tmp_path)
    p1, p2 = FakeProcess.instances
    _menu(bs, "c1")
    _menu(bs, "keyboard")
    assert not p2.hat("pause") and p2.mask == 0
    assert p1.hat("pause")[-1] == ("pause", True)
    one, two = bs.player
    assert "pause" in bs._symbols(one) and "pause" not in bs._symbols(two)
    two.crashed = True
    assert "pause" in bs._symbols(two)


def test_previous_game_ends_before_the_next_starts(app, tmp_path):
    """The previous game ends before the next one starts."""
    from soullink.ui.game import GameScreen

    probe = _create(app)
    first = _game(app, tmp_path, name="A")
    assert app.plugins.running_session is first.plugins
    FakeProcess.instances = []
    second = GameScreen(app, fake_session(tmp_path / "B", 2), ["keyboard", "c1"], process_factory=FakeProcess)
    run = [a for a in probe.calls if a[0] in ("session_start", "session_end")]
    assert run == [("session_start",), ("session_end",), ("session_start",)]
    assert probe.game.session is second.session and app.plugins.running_session is second.plugins
    counter = len(probe.calls)
    first.update(0.016)
    assert len(probe.calls) == counter
    app.switch(second)
    assert probe.calls.count(("session_end",)) == 1
    second.leave()
    assert probe.calls.count(("session_end",)) == 2 and app.plugins.running_session is None


@pytest.mark.parametrize("value, hint", [("Probe blocks", "Probe blocks"), (False, "Fast-forward is blocked right now")])
def test_fast_forward_allowed_locks(app, tmp_path, value, hint):
    """fast_forward_allowed can lock fast forward."""
    probe = _create(app)
    bs = _game(app, tmp_path)
    p2 = FakeProcess.instances[1]
    probe.fast_forward = value
    press(bs, "c1", Key.STICK_R)
    press(bs, "c1", Key.STICK_R, False)
    sp = bs.player[1]
    assert not p2.hat("tempo") and not sp.fast_forward and not sp.control.fast and sp.hint == hint
    probe.fast_forward = True
    press(bs, "c1", Key.STICK_R)
    assert p2.hat("tempo")[-1] == ("tempo", 3)


def test_process_group(app, tmp_path):
    """A plugin can demand a process group."""
    from soullink.player import ProcessGroup
    from soullink.ui import game as game_module

    assert not hasattr(game_module, "_core_process_group")
    bs = _game(app, tmp_path, name="B")
    assert bs.group is None and all(p.group is None for p in FakeProcess.instances)
    probe = _create(app)
    bs = _game(app, tmp_path, name="A")
    assert bs.group is None
    probe.group = "yes"
    assert _game(app, tmp_path, name="F").group is None
    probe.group = True
    bs = _game(app, tmp_path, name="C")
    assert isinstance(bs.group, ProcessGroup) and all(p.group is bs.group for p in FakeProcess.instances)
    assert _game(app, tmp_path, name="D", system="nds").group is None
    assert _game(app, tmp_path, name="E", count=1).group is None


def test_events_go_to_the_plugins(app, tmp_path):
    """Player process events are passed to the plugins."""
    probe = _create(app, worker="worker")
    bs = _game(app, tmp_path)
    p1 = FakeProcess.instances[0]
    assert (1, ("ready", p1.ready_info)) in probe.events
    for e in (("sram",), ("ram", {0: b""}), ("plugin", "probe", 42), ("plugin", "foreign", 1)):
        p1._new.append(e)
    bs.update(0.016)
    assert probe.events[-3:] == [(1, ("sram",)), (1, ("ram", {0: b""})), (1, ("plugin", "probe", 42))]
    p1._new.append(("plugin_error", "probe", "Traceback (most recent call last):\nValueError: in the worker"))
    bs.update(0.016)
    assert bs.plugins.plugins == [] and "ValueError: in the worker" in _log(app)
    assert all(p.hat("plugin_disable") == [("plugin_disable", "probe")] for p in FakeProcess.instances)
    assert bs.player[0].hint and "Probe-Plugin" in bs.player[0].hint


def test_restart_after_a_crash_keeps_the_worker_parts(app, tmp_path):
    """A restarted process gets its worker parts again."""
    _create(app, worker="worker")
    bs = _game(app, tmp_path)
    FakeProcess.instances[0].alive = False
    bs.update(0.016)
    press(bs, "keyboard", Key.SOUTH)
    assert len(FakeProcess.instances) == 3 and FakeProcess.instances[2].plugins[0]["id"] == "probe"


def test_save_and_session_end(app, tmp_path):
    """save and session_end hooks are called."""
    probe = _create(app)
    bs = _game(app, tmp_path)
    bs.autosave()
    assert probe.calls.count(("save",)) == 1
    bs.save_and_end()
    bs.update(0.016)
    assert probe.calls.count(("save",)) == 2 and probe.calls[-1] == ("session_end",)
    counter = len(probe.calls)
    bs.leave()
    assert len(probe.calls) == counter


def test_setting_in_the_game_api(app, tmp_path):
    """Settings can be read through the game API."""
    code = PROBE.replace('''    def display_names(self):''', '''    def settings(self):
        from soullink.plugin.api import Setting

        return [Setting("mode", "Mode", "selection", "a", ("a", "b"))]

    def display_names(self):''')
    probe = _create(app, code=code)
    app.plugins.value_set("probe", "mode", "b")
    bs = _game(app, tmp_path)
    assert probe.game.setting("mode") == "b"
    assert bs.plugins.apis["probe"] is probe.game
