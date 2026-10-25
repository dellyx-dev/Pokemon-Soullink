"""Tests of the game screen with DS players."""
import json

import pygame
import pytest

from soullink.input.devices import KeysEvent
from soullink.input.keys import Key
from soullink.core.libretro import pointer_value
from ui_helpers import FakeProcess, dummy_app, input, fake_session


@pytest.fixture
def app(monkeypatch, tmp_path):
    """App with a dummy window."""
    a = dummy_app(monkeypatch, tmp_path)
    yield a
    a.close()


@pytest.fixture
def game(app, tmp_path):
    """Game screen with two DS players."""
    from soullink.ui.game import GameScreen

    FakeProcess.instances = []
    bs = GameScreen(app, fake_session(tmp_path / "S", 2, system="nds"), ["keyboard", "c1"],
                         process_factory=FakeProcess)
    app.switch(bs)
    bs.update(0.016)
    return bs


def key(bs, device, t, pressed=True, dt=0.016):
    """Sends a key event of a device to the game."""
    input(bs, device, t, pressed)
    bs.update(dt)


def test_nds_processes_and_names(game):
    """NDS players get processes and game names."""
    assert all(p.system == "nds" for p in FakeProcess.instances)
    assert [sp.game_name for sp in game.player] == ["Platinum", "HeartGold"]


def test_view_switch_in_the_player_menu_applies_to_all(app, game, tmp_path):
    """The DS view switch in the player menu applies to everybody."""
    assert game.view == "hybrid"
    before = game._screens(0)
    sp, other = game.player[1], game.player[0]
    key(game, "c1", Key.L2)
    key(game, "c1", Key.L2, False)
    game._menu_open(other, 0)
    assert "swap" in sp.menu_actions and "view" in sp.menu_actions
    sp.menu.selection = sp.menu_actions.index("view")
    key(game, "c1", Key.SOUTH)
    assert game.view == "columns" and game._screens(0) != before
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["ds_view"] == "columns"
    assert "swap" not in sp.menu_actions and sp.menu_actions[sp.menu.selection] == "view"
    assert "swap" not in other.menu_actions
    key(game, "c1", Key.RIGHT)
    assert game.view == "hybrid" and sp.repeat.key is None


def test_l3_swaps_only_the_own_player(game):
    """L3 swaps the screens of only the own player."""
    (large, source), _ = game._screens(1)
    assert source == "top"
    key(game, "c1", Key.STICK_L)
    assert game._screens(1)[0][1] == "bottom" and game._screens(0)[0][1] == "top"


def test_mouse_taps_on_lower_screen(game):
    """The mouse taps on the lower screen."""
    p1 = FakeProcess.instances[0]
    bottom = game._bottom(0)
    game.raw(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=bottom.center))
    game.update(0.016)
    x, y, pressed = p1.pointer_values
    assert pressed and x == pointer_value(128, 256) and y == pointer_value(192 + 96, 384)
    game.raw(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=bottom.center))
    game.update(0.016)
    assert p1.pointer_values[2] is False


def test_right_stick_and_r3(app, game, monkeypatch):
    """The right stick moves the touch cursor and R3 taps."""
    p2 = FakeProcess.instances[1]
    axes = {pygame.CONTROLLER_AXIS_RIGHTX: 32767}
    monkeypatch.setattr(app.devices, "axis", lambda g, i: axes.get(i, 0) if g == "c1" else 0)
    start = game.player[1].cursor[0]
    game.update(0.25)
    assert game.player[1].cursor[0] > start + 30
    key(game, "c1", Key.R2)
    assert p2.pointer_values[2] is True
    key(game, "c1", Key.R2, False)
    key(game, "c1", Key.STICK_R)
    assert p2.hat("tempo")[-1] == ("tempo", 3) and p2.pointer_values[2] is False


def test_touch_with_dpad(game):
    """Touch works with the d-pad."""
    p1 = FakeProcess.instances[0]
    key(game, "keyboard", Key.L2)
    key(game, "keyboard", Key.L2, False)
    menu = game.player[0].menu
    menu.selection = game.player[0].menu_actions.index("cross")
    key(game, "keyboard", Key.SOUTH)
    key(game, "keyboard", Key.L2)
    assert game.player[0].touch_cross
    key(game, "keyboard", Key.RIGHT, dt=0.5)
    assert game.player[0].cursor[0] > 128 and p1.mask == 0
    key(game, "keyboard", Key.EAST)
    assert p1.pointer_values[2] is True


def test_draw_both_views(app, game):
    """Both DS views draw without errors."""
    game.draw(app.area)
    game.view_switch()
    game.draw(app.area)


def test_ds_x_y_stay_in_the_game_and_l2_opens_the_menu(game):
    """On the DS X and Y go to the game and L2 opens the menu."""
    p2 = FakeProcess.instances[1]
    key(game, "c1", Key.NORTH)
    key(game, "c1", Key.WEST)
    assert p2.mask == (1 << 9) | (1 << 1)
    key(game, "c1", Key.NORTH, False)
    key(game, "c1", Key.WEST, False)
    assert game.player[1].menu is None
    key(game, "c1", Key.L2)
    key(game, "c1", Key.L2, False)
    assert game.player[1].menu is not None
    key(game, "c1", Key.L2)
    assert game.player[1].menu is None


def test_label_lies_under_menu_and_overlay(app, game):
    """The label is drawn under menu and overlay."""
    from soullink.ui import graphics

    free = game.cells[0].free
    assert game.view == "hybrid" and free is not None
    pixel = max(12, min(free.h // 9, free.w // 12))
    point = (free.x + pixel + 4, free.y + round(pixel * 1.6))

    def badge_visible():
        """True if the badge pixel is visible after drawing."""
        game.draw(app.area)
        return max(abs(a - b) for a, b in zip(app.area.get_at(point)[:3], graphics.player_color(1))) < 20

    assert badge_visible()
    sp = game.player[0]
    game._types_open(sp)
    assert not badge_visible()
    game._types_close(sp)
    game._menu_open(sp, 0)
    assert not badge_visible()


def test_without_plugins_no_link_cable(game):
    """Without plugins there is no DS link cable entry."""
    sp = game.player[1]
    key(game, "c1", Key.L2)
    key(game, "c1", Key.L2, False)
    assert "plugins" not in sp.menu_actions and "link" not in sp.menu_actions
    assert not any(p.plugins for p in FakeProcess.instances)


def test_new_nds_session_gets_own_device_addresses(app, tmp_path):
    """A new NDS session gives each player an own device address."""
    from soullink.ui.game import GameScreen

    session = fake_session(tmp_path / "M", 2, system="nds")
    for s in session.player:
        s.mac = f"00:09:BF:53:4C:0{s.nr}"
    receive = []

    class WithOptions(FakeProcess):
        """Fake process that records its core options."""

        def __init__(self, nr, dir, audio, core=None, system="gba", core_options=None, **rest):
            """Creates the fake and stores the core options."""
            super().__init__(nr, dir, audio, core, system, **rest)
            receive.append(core_options)

    bs = GameScreen(app, session, ["keyboard", "c1"], process_factory=WithOptions)
    assert [o["melonds_mac_address_mode"] for o in receive] == ["00:09:BF:53:4C:01", "00:09:BF:53:4C:02"]
    assert all(o["melonds_show_cursor"] == "disabled" for o in receive)
    bs.leave()
