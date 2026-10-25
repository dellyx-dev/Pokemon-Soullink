"""Tests of the game screen: input, menus, overlay, audio, autosave and crash handling."""

import json
import time

import pygame
import pytest

from soullink.input.devices import DeviceEvent, KeysEvent
from soullink.input.keys import Key
from soullink.plugin.api import Tab
from ui_helpers import FakeProcess, dummy_app, input, fake_session


class _ExtraTab(Tab):
    """Second overlay tab with a search, for tests without plugins."""
    id, position, ram_interval = "extra", 50, 1.5

    def __init__(self):
        """Creates the tab with an empty search."""
        from soullink.ui.keyboard import Search

        self.search = Search()

    def keyboard_close(self):
        """Closes the search keyboard."""
        self.search.close()


def _extra(sp) -> _ExtraTab:
    """Adds the extra tab to the player's overlay and returns it."""
    sp.types.tab_set(sp.core_tab + [_ExtraTab()])
    return sp.types.find("extra")


@pytest.fixture
def app(monkeypatch, tmp_path):
    """App with a dummy window."""
    a = dummy_app(monkeypatch, tmp_path)
    yield a
    a.close()


@pytest.fixture
def game(app, tmp_path):
    """Game screen with two players."""
    from soullink.ui.game import GameScreen

    FakeProcess.instances = []
    bs = GameScreen(app, fake_session(tmp_path / "S"), ["keyboard", "c1"], process_factory=FakeProcess)
    app.switch(bs)
    bs.update(0.016)
    return bs


def press(bs, device, key, pressed=True):
    """Sends a key press or release of a device to the game."""
    input(bs, device, key, pressed)
    bs.update(0.016)


def test_input_goes_to_the_correct_player(game):
    """Input reaches only the player owning the device."""
    p1, p2 = FakeProcess.instances
    assert p1.hat("start") and p2.hat("start")
    press(game, "keyboard", Key.SOUTH)
    assert p1.mask & (1 << 8) and p2.mask == 0
    press(game, "keyboard", Key.SOUTH, False)
    assert p1.mask == 0


def test_fast_forward(game):
    """Fast forward is toggled per player."""
    p1 = FakeProcess.instances[0]
    press(game, "keyboard", Key.STICK_R)
    assert p1.hat("tempo")[-1] == ("tempo", 3)
    press(game, "keyboard", Key.STICK_R, False)
    assert p1.hat("tempo") == [("tempo", 3)]
    press(game, "keyboard", Key.STICK_R)
    assert p1.hat("tempo")[-1] == ("tempo", 1)


def test_player_menu_pauses_only_the_own_game_and_switches_audio(game):
    """The player menu pauses only the own game and switches audio."""
    p1, p2 = FakeProcess.instances
    press(game, "c1", Key.L2)
    press(game, "c1", Key.L2, False)
    assert p2.hat("pause")[-1] == ("pause", True)
    assert not p1.hat("pause")
    press(game, "c1", Key.DOWN)
    press(game, "c1", Key.SOUTH)
    assert p2.hat("audio")[-1] == ("audio", True)
    assert game.session.player[1].audio is True
    press(game, "c1", Key.L2)
    assert p2.hat("pause")[-1] == ("pause", False)


def test_controller_removal_and_takeover(game):
    """A removed controller pauses the player and a free one takes over."""
    p2 = FakeProcess.instances[1]
    game.event(DeviceEvent("c1", "away"))
    game.update(0.016)
    assert p2.hat("pause")[-1] == ("pause", True)
    press(game, "c7", Key.SOUTH)
    assert game.player[1].device == "c7"
    assert p2.hat("pause")[-1] == ("pause", False)


def test_crash_and_restart(game):
    """A crashed player process is reported and can be restarted."""
    FakeProcess.instances[0].alive = False
    game.update(0.016)
    assert game.player[0].crashed
    press(game, "keyboard", Key.SOUTH)
    assert len(FakeProcess.instances) == 3
    assert not game.player[0].crashed
    assert game.player[0].process is FakeProcess.instances[2]


def test_save_and_end_through_the_player_menu(app, game):
    """Save and quit works through the player menu."""
    from soullink.ui.start import StartScreen

    game.update(10.0)
    _menu(game, "c1")
    _choose(game, 2, "end", "c1")
    press(game, "c1", Key.DOWN)
    press(game, "c1", Key.SOUTH)
    for p in FakeProcess.instances:
        assert p.hat("save") and p.hat("end")
    data = json.loads((game.session.dir / "session.json").read_text(encoding="utf-8"))
    assert data["playtime_seconds"] >= 10
    assert data["core_version"] == "0.11-test"
    assert isinstance(app.screen, StartScreen)


def test_player_menu_confirmation(app, game):
    """The player menu asks for confirmation before quitting."""
    from soullink.ui.start import StartScreen

    press(game, "keyboard", Key.L2)
    press(game, "keyboard", Key.L2, False)
    press(game, "keyboard", Key.UP)
    press(game, "keyboard", Key.SOUTH)
    assert game.player[0].menu_question
    press(game, "keyboard", Key.DOWN)
    press(game, "keyboard", Key.SOUTH)
    assert isinstance(app.screen, StartScreen)


def test_autosave(app, game):
    """Autosave saves all players periodically."""
    app.settings.autosave_minutes = 0.001
    game.autosave_rest = 0.06
    game.update(1.0)
    for p in FakeProcess.instances:
        assert p.hat("save")


def test_draw_in_all_states(app, game):
    """Drawing works in all game states."""
    area = app.area
    game.draw(area)
    press(game, "c1", Key.L2)
    press(game, "c1", Key.L2, False)
    game.draw(area)
    game.event(DeviceEvent("keyboard", "away"))
    FakeProcess.instances[1].alive = False
    game.update(0.016)
    game.draw(area)


def test_audio_is_pushed_in_per_frame(app, game):
    """Audio is pushed to the mixer every frame."""
    assert game.output is not None
    calls = []
    real = game.output.refill
    game.output.refill = lambda: calls.append(1) or real()
    game.update(0.016)
    game.update(0.016)
    assert len(calls) == 2


def test_north_key_opens_the_menu_on_release(game):
    """A short press of the north key opens the menu on release."""
    press(game, "c1", Key.L2)
    assert game.player[1].menu is None
    press(game, "c1", Key.L2, False)
    assert game.player[1].menu is not None
    assert "Overlay" in game.player[1].menu.entries


def test_north_key_hold_opens_the_overlay(game):
    """Holding the north key opens the types overlay."""
    import time

    p2 = FakeProcess.instances[1]
    press(game, "c1", Key.L2)
    game.player[1].upper_since = time.monotonic() - 1
    game.update(0.016)
    sp = game.player[1]
    assert sp.types_open and p2.hat("pause")[-1] == ("pause", True)
    press(game, "c1", Key.L2, False)
    assert sp.menu is None and sp.types_open
    search = _extra(sp).search
    press(game, "c1", Key.R)
    assert sp.types.page == 1 and p2.mask == 0
    search.open()
    press(game, "c1", Key.L2)
    assert not sp.types_open and p2.hat("pause")[-1] == ("pause", False)
    assert not search.is_open


def test_types_overlay_through_the_menu_and_key_t(app, game):
    """The types overlay opens through the menu and key T."""
    press(game, "c1", Key.L2)
    press(game, "c1", Key.L2, False)
    sp = game.player[1]
    sp.menu.selection = sp.menu_actions.index("overlay")
    press(game, "c1", Key.SOUTH)
    assert sp.menu is None and sp.types_open
    game.raw(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_t, mod=0, unicode="t", scancode=0))
    assert game.player[0].types_open
    game.raw(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_t, mod=0, unicode="t", scancode=0))
    assert not game.player[0].types_open
    game.draw(app.area)


def _menu(game, device):
    """Opens the player menu of a device."""
    press(game, device, Key.L2)
    press(game, device, Key.L2, False)


def _choose(game, nr, action, device):
    """Chooses an action in the player's menu."""
    sp = game.player[nr - 1]
    sp.menu.selection = sp.menu_actions.index(action)
    press(game, device, Key.SOUTH)


def test_rebind_and_controller_switch(game):
    """Rebinding and controller switching are offered."""
    _menu(game, "c1")
    _choose(game, 2, "bind", "c1")
    sp = game.player[1]
    assert sp.menu.entries == ["Switch controller", "Remap buttons"]
    _choose(game, 2, "controller", "c1")
    assert sp.device is None and sp.menu is None and "controller" in sp.pauses and sp.released
    press(game, "c1", Key.SOUTH, False)
    press(game, "c9", Key.SOUTH)
    assert sp.device == "c9" and not sp.pauses and not sp.released


def test_two_players_swap_controllers_through_the_switch(game):
    """Two players swap controllers through the controller switch."""
    for nr, device in ((1, "keyboard"), (2, "c1")):
        _menu(game, device)
        _choose(game, nr, "bind", device)
        _choose(game, nr, "controller", device)
    press(game, "c1", Key.SOUTH)
    press(game, "keyboard", Key.SOUTH)
    assert [s.device for s in game.player] == ["c1", "keyboard"]


def test_binding_keys_creates_a_profile_from_the_default(app, game):
    """Binding keys creates a profile from the default."""
    p2 = FakeProcess.instances[1]
    _menu(game, "c1")
    _choose(game, 2, "bind", "c1")
    _choose(game, 2, "keys", "c1")
    sp = game.player[1]
    assert sp.menu_question == "profile" and sp.keys_menu is None
    game.draw(app.area)
    _choose(game, 2, "no", "c1")
    assert sp.submenu and sp.menu.selection == 1
    _choose(game, 2, "keys", "c1")
    _choose(game, 2, "yes", "c1")
    assert sp.profile_input is not None and p2.hat("pause")[-1] == ("pause", True)
    game.draw(app.area)
    press(game, "c1", Key.SOUTH)
    press(game, "c1", Key.START)
    assert sp.profile == "A" and sp.keys_menu is not None and sp.keys_menu.title == "Edit profile “A”"
    press(game, "c1", Key.SOUTH)
    press(game, "c1", Key.WEST)
    press(game, "c1", Key.EAST)
    assert sp.keys_menu is not None
    press(game, "c1", Key.START)
    assert sp.keys_menu is None and p2.hat("pause")[-1] == ("pause", False)
    press(game, "c1", Key.WEST)
    assert p2.mask == 1 << 8
    assert app.profile.binding("controller", "A", "gba")["WEST"] == "A"
    data = json.loads((game.session.dir / "session.json").read_text(encoding="utf-8"))
    assert data["player"][1]["profile"] == "A" and data["player"][1]["keys"] is None


def test_own_profile_is_bound_directly_and_applies_to_all_with_it(app, tmp_path):
    """An own profile is bound directly and applies to all controllers using it."""
    from soullink.ui.game import GameScreen

    name = app.profile.create("controller", "gba", "Team")
    s = fake_session(tmp_path / "P")
    for info in s.player:
        info.profile = name
    FakeProcess.instances = []
    bs = GameScreen(app, s, ["c1", "c2"], process_factory=FakeProcess)
    app.switch(bs)
    _menu(bs, "c1")
    _choose(bs, 1, "bind", "c1")
    _choose(bs, 1, "keys", "c1")
    sp1, sp2 = bs.player
    assert sp1.keys_menu is not None
    press(bs, "c1", Key.SOUTH)
    press(bs, "c1", Key.WEST)
    press(bs, "c1", Key.START)
    press(bs, "c2", Key.WEST)
    assert FakeProcess.instances[1].mask == 1 << 8


def test_menu_on_another_key(game):
    """The menu function can be moved to another key."""
    from soullink.input.key_binding import Function

    sp = game.player[1]
    sp.control.binding.bind(Function.MENU, Key.WEST)
    press(game, "c1", Key.L2)
    press(game, "c1", Key.L2, False)
    assert sp.menu is None
    press(game, "c1", Key.WEST)
    press(game, "c1", Key.WEST, False)
    assert sp.menu is not None


def test_binding_is_loaded_from_the_session(app, tmp_path):
    """The binding is loaded from the session."""
    from soullink.ui.game import GameScreen

    s = fake_session(tmp_path / "T")
    s.player[0].keys = {"SOUTH": "GBA_A", "EAST": "GBA_W", "NORTH": "MENU"}
    FakeProcess.instances = []
    bs = GameScreen(app, s, ["keyboard", "c1"], process_factory=FakeProcess)
    app.switch(bs)
    press(bs, "keyboard", Key.SOUTH)
    assert FakeProcess.instances[0].mask == 1 << 8


def test_b_closes_player_menu_and_overlay(game):
    """B closes the player menu and the overlay."""
    sp = game.player[1]
    press(game, "c1", Key.L2)
    press(game, "c1", Key.L2, False)
    assert sp.menu is not None
    press(game, "c1", Key.EAST)
    assert sp.menu is None and "menu" not in sp.pauses
    game._types_open(sp)
    press(game, "c1", Key.EAST)
    assert not sp.types_open


def _raw(bs, key, pressed=True):
    """Sends a raw keyboard event to the game."""
    bs.raw(pygame.event.Event(pygame.KEYDOWN if pressed else pygame.KEYUP, key=key, mod=0, unicode="", scancode=0))
    bs.update(0.016)


def test_keyboard_binds_with_real_keys(game):
    """The keyboard player binds with real keys."""
    p1 = FakeProcess.instances[0]
    _menu(game, "keyboard")
    _choose(game, 1, "bind", "keyboard")
    _choose(game, 1, "keys", "keyboard")
    _choose(game, 1, "yes", "keyboard")
    sp = game.player[0]
    sp.profile_input.text = "Keys"
    press(game, "keyboard", Key.START)
    menu = sp.keys_menu
    assert menu.title == "Edit profile “Keys”" and "X" in menu._keys_text(menu.rows[0])
    press(game, "keyboard", Key.SOUTH)
    _raw(game, pygame.K_k)
    assert sp.keys_menu.waits is None and sp.keys_menu._keys_text(sp.keys_menu.rows[0]) == "K"
    press(game, "keyboard", Key.START)
    assert sp.keys_menu is None
    _raw(game, pygame.K_k)
    assert p1.mask == 1 << 8
    _raw(game, pygame.K_k, False)
    assert game.app.profile.binding("keyboard", "Keys", "gba")["k"] == "A"
    data = json.loads((game.session.dir / "session.json").read_text(encoding="utf-8"))
    assert data["player"][0]["profile"] == "Keys" and data["player"][0]["keyboard"] is None


def test_keyboard_binding_stays_with_the_player(app, tmp_path):
    """The keyboard binding stays with the player."""
    from soullink.ui.game import GameScreen

    s = fake_session(tmp_path / "K")
    s.player[0].keyboard = {"k": "A", "tab": "MENU"}
    FakeProcess.instances = []
    bs = GameScreen(app, s, ["keyboard", "c1"], process_factory=FakeProcess)
    app.switch(bs)
    _raw(bs, pygame.K_k)
    assert FakeProcess.instances[0].mask == 1 << 8
    _raw(bs, pygame.K_k, False)
    _raw(bs, pygame.K_x)
    assert FakeProcess.instances[0].mask == 0


def test_overlay_requests_ram(game):
    """Opening the overlay requests a RAM dump."""
    sp = game.player[0]
    game._types_open(sp)
    assert all(p.hat("ram") for p in FakeProcess.instances)
    FakeProcess.instances[0]._new.append(("ram", {0x02000000: bytes(16)}))
    game.update(0.016)
    assert not hasattr(sp, "opponent")


def test_without_plugins_only_types(game):
    """Without plugins the overlay has only the types tab."""
    sp = game.player[1]
    assert [r.id for r in sp.types.tab] == ["types"]
    _menu(game, "c1")
    assert "plugins" not in sp.menu_actions and not hasattr(game, "left")
    assert game.rom_data.requested == []


def test_own_binding_applies_in_the_overlay_with_keyboard(game):
    """The own binding applies in the overlay with the keyboard."""
    from soullink.input.key_binding import Function

    sp = game.player[0]
    sp.keyboard.bind(Function.L, pygame.K_q)
    sp.keyboard.bind(Function.R, pygame.K_e)
    _raw(game, pygame.K_t)
    _extra(sp)
    assert sp.types_open and sp.types.active.id == "types"
    _raw(game, pygame.K_e)
    assert sp.types.active.id == "extra"
    _raw(game, pygame.K_q)
    assert sp.types.active.id == "types"


def test_own_binding_applies_in_the_overlay_with_controller(game):
    """The own binding applies in the overlay with a controller."""
    from soullink.input.key_binding import Function

    sp = game.player[1]
    sp.keys.bind(Function.R, Key.R2)
    game._types_open(sp)
    _extra(sp)
    press(game, "c1", Key.R2)
    assert sp.types.active.id == "extra"


def test_hold_repeats_in_overlay(game):
    """Holding a key repeats in the overlay."""
    import time

    sp = game.player[1]
    game._types_open(sp)
    assert sp.types.show("types")
    press(game, "c1", Key.DOWN)
    assert sp.types.active.row == 1 and sp.repeat.key == Key.DOWN
    sp.repeat.since, sp.repeat.next_ = time.monotonic() - 3, time.monotonic() - 0.01
    game.update(0.016)
    assert sp.types.active.row == 2
    press(game, "c1", Key.DOWN, False)
    assert sp.repeat.key is None


def test_audio_slider_in_player_menu(game):
    """The audio slider works in the player menu."""
    p2 = FakeProcess.instances[1]
    sp = game.player[1]
    assert sp.volume == 0
    _menu(game, "c1")
    sp.menu.selection = sp.menu_actions.index("audio")
    press(game, "c1", Key.RIGHT)
    press(game, "c1", Key.RIGHT, False)
    press(game, "c1", Key.RIGHT)
    press(game, "c1", Key.RIGHT, False)
    assert sp.volume == 2 and p2.hat("audio")[-1] == ("audio", True)
    assert sp.menu_actions[sp.menu.selection] == "audio"
    press(game, "c1", Key.SOUTH)
    assert sp.volume == 0 and p2.hat("audio")[-1] == ("audio", False)
    press(game, "c1", Key.SOUTH)
    assert sp.volume == 2
    assert game.session.player[1].volume == 2 and game.session.player[1].audio


def _three_player(app, tmp_path, name="D"):
    """Game screen with three players."""
    from soullink.ui.game import GameScreen

    FakeProcess.instances = []
    bs = GameScreen(app, fake_session(tmp_path / name, 3), ["keyboard", "c1", "c2"], process_factory=FakeProcess)
    app.switch(bs)
    return bs


def test_free_field_without_plugins_shows_the_session(app, tmp_path):
    """Without plugins the free field shows the session display."""
    import time

    bs = _three_player(app, tmp_path)
    assert len(bs.cells) == 4
    for setting in ("", "core.soullink", "alternating", "core.session"):
        app.settings.free_field = setting
        for now in (0.0, 15.0, 30.0):
            assert bs.field.current(setting, now)[:2] == ("core.session", "Session")
    bs.ram_requested = time.monotonic() - 60
    bs.update(0.016)
    assert not any(p.hat("ram") for p in FakeProcess.instances)
    bs.draw(app.area)


def test_without_plugins_no_rom_data_is_loaded(app, tmp_path, monkeypatch):
    """Without plugins no ROM data (Java) is ever loaded."""
    from soullink.ui.game import GameScreen

    loaded = []
    monkeypatch.setattr(GameScreen, "_dex_load", lambda self, nr: loaded.append(nr))
    FakeProcess.instances = []
    bs = GameScreen(app, fake_session(tmp_path / "R"), ["keyboard", "c1"], process_factory=FakeProcess,
                         dex_load=True)
    app.switch(bs)
    for _ in range(3):
        bs.update(0.016)
        bs.draw(app.area)
    bs._types_open(bs.player[1])
    FakeProcess.instances[1]._new.append(("ram", {0x02000000: bytes(16)}))
    bs.update(0.016)
    bs.draw(app.area)
    time.sleep(0.05)
    assert bs.rom_data.requested == [] and loaded == []


def test_ram_interval_from_open_tab(game):
    """The RAM interval follows the open tab."""
    import time

    sp = game.player[1]
    game._types_open(sp)
    p1 = FakeProcess.instances[0]
    _extra(sp)
    assert sp.types.show("types")
    game.ram_requested = time.monotonic() - 6
    game.update(0.016)
    assert len(p1.hat("ram")) == 1
    sp.types.show("extra")
    game.ram_requested = time.monotonic() - 2
    game.update(0.016)
    assert len(p1.hat("ram")) == 2


def test_audio_slider_hold_becomes_faster(game):
    """Holding the audio slider key accelerates."""
    import time

    sp = game.player[1]
    _menu(game, "c1")
    sp.menu.selection = sp.menu_actions.index("audio")
    press(game, "c1", Key.RIGHT)
    assert sp.volume == 1 and sp.repeat.kind == "slider"
    sp.repeat.since = time.monotonic() - 3
    for _ in range(4):
        sp.repeat.next_ = 0.0
        game.update(0.016)
    assert sp.volume == 5
    press(game, "c1", Key.RIGHT, False)
    sp.repeat.next_ = 0.0
    game.update(0.016)
    assert sp.volume == 5


def test_music_slider_hold_in_the_player_menu(app, game):
    """The music slider works with held keys in the player menu."""
    import json

    sp = game.player[1]
    _menu(game, "c1")
    game._menu_open(game.player[0], 0)
    sp.menu.selection = sp.menu_actions.index("music")
    before = app.music.volume
    press(game, "c1", Key.LEFT)
    assert app.music.volume == before - 1 and sp.repeat.kind == "slider"
    sp.repeat.next_ = 0.0
    game.update(0.016)
    assert app.music.volume == before - 2
    game.draw(app.area)

    def saved():
        """The stored music volume."""
        return json.loads((app.base / "settings.json").read_text(encoding="utf-8"))["music_volume"]

    assert saved() == before - 1
    press(game, "c1", Key.LEFT, False)
    assert saved() == before - 2


def test_repeater_is_faster_for_sliders_than_for_lists():
    """Sliders repeat faster than lists."""
    from soullink.ui.menu import Repeater

    def count(kind, seconds=4.0):
        """Number of repeats of a key held for the given seconds."""
        w = Repeater()
        w.start(Key.RIGHT, 0.0, kind)
        now, n = 0.0, 0
        while now < seconds:
            now += 0.001
            n += w.due(now) is not None
        return n

    assert 50 < count("list") < 65
    assert count("slider", 4.1) >= 99


def test_hold_scrolls_the_player_menu(game):
    """Holding a key scrolls the player menu."""
    sp = game.player[1]
    _menu(game, "c1")
    press(game, "c1", Key.DOWN)
    assert sp.menu.selection == 1 and sp.repeat.kind == "list"
    sp.repeat.next_ = 0.0
    game.update(0.016)
    assert sp.menu.selection == 2
    press(game, "c1", Key.DOWN, False)
    sp.repeat.next_ = 0.0
    game.update(0.016)
    assert sp.menu.selection == 2


def test_escape_and_f2_work_without_an_own_menu(game):
    """Escape and F2 work without an own menu."""
    def key_raw(key):
        """Sends a raw key to the game."""
        game.raw(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))
        game.raw(pygame.event.Event(pygame.KEYUP, key=key, mod=0, unicode="", scancode=0))
        game.update(0.016)

    key_raw(pygame.K_F2)
    assert not hasattr(game, "global_menu")
    sp = game.player[0]
    key_raw(pygame.K_ESCAPE)
    assert sp.menu is not None and "menu" in sp.pauses
    assert game.player[1].menu is None and not game.player[1].pauses
    key_raw(pygame.K_ESCAPE)
    assert sp.menu is None and not sp.pauses


def test_player_menu_groups_and_draw(app, game):
    """The player menu is grouped and drawn."""
    sp = game.player[1]
    _menu(game, "c1")
    assert [a for a, _ in game._menu_layout(sp)] == ["row", "group", "row", "row", "group", "row", "row",
                                                       "gap", "row"]
    for selection in range(len(sp.menu_actions)):
        sp.menu.selection = selection
        game.draw(app.area)
    small = pygame.Rect(0, 0, 300, 260)
    p = game._menu_size(sp, small, 40)
    assert 10 <= p < 40 and game._menu_height(game._menu_layout(sp), p) <= small.height - 8


def test_without_plugins_no_link_cable(app, game):
    """Without plugins there is no link cable entry."""
    p1, p2 = FakeProcess.instances
    assert game.group is None and p1.group is None and p2.group is None
    sp = game.player[1]
    _menu(game, "c1")
    assert sp.menu_actions == ["next", "audio", "music", "overlay", "bind", "end"]
    assert p2.hat("pause")[-1] == ("pause", True)
    press(game, "c1", Key.EAST)
    press(game, "c1", Key.STICK_R)
    assert p2.hat("tempo")[-1] == ("tempo", 3) and "link" not in game._symbols(sp)
