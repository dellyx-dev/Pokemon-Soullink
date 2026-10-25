"""Tests of the assignment screen with profiles."""

import json

import pygame
import pytest

from soullink.input.wizard import STEPS
from soullink.input.devices import RawEvent, KeysEvent
from soullink.input.keys import Key
from ui_helpers import dummy_app, fake_session, key


@pytest.fixture
def app(monkeypatch, tmp_path):
    """App with a prepared session and fake devices."""
    a = dummy_app(monkeypatch, tmp_path)
    yield a
    a.close()


def test_keyboard_and_controller_start_game(app, tmp_path, monkeypatch):
    """A keyboard and a controller join and start the game."""
    from soullink.ui import game, assignment

    started = {}

    def fake_game(a, s, devices):
        """Fake game screen constructor that remembers the devices."""
        started["devices"] = devices
        return assignment.Screen(a)

    monkeypatch.setattr(game, "GameScreen", fake_game)
    s = fake_session(tmp_path / "S")
    bs = assignment.AssignmentScreen(app, s)
    app.switch(bs)
    key(pygame.K_RETURN)
    app.run(max_images=2)
    assert bs.assignment.player == ["keyboard", None]
    bs.event(KeysEvent("c5", Key.SOUTH, True))
    assert bs.assignment.done and "devices" not in started
    key(pygame.K_RETURN)
    app.run(max_images=2)
    assert bs.choice[0].phase == "ready" and "devices" not in started
    bs.event(KeysEvent("c5", Key.EAST, True))
    assert bs.assignment.player == ["keyboard", None]
    bs.event(KeysEvent("c5", Key.SOUTH, True))
    bs.draw(app.area)
    bs.event(KeysEvent("c5", Key.SOUTH, True))
    assert started["devices"] == ["keyboard", "c5"]
    assert [sp.profile for sp in s.player] == [None, None]


def _started(monkeypatch):
    """Replaces the game screen with a fake that records the devices."""
    from soullink.ui import game, assignment

    started = {}

    def fake_game(a, s, devices):
        """Fake game screen constructor that remembers the devices."""
        started["devices"] = devices
        return assignment.Screen(a)

    monkeypatch.setattr(game, "GameScreen", fake_game)
    return started


def test_new_profile_is_created_bound_and_chosen(app, tmp_path, monkeypatch):
    """A new profile is named, bound and then chosen."""
    from soullink.ui import assignment

    started = _started(monkeypatch)
    s = fake_session(tmp_path / "S")
    bs = assignment.AssignmentScreen(app, s)
    app.switch(bs)
    for device in ("c1", "c2"):
        bs.event(KeysEvent(device, Key.SOUTH, True))
    bs.event(KeysEvent("c1", Key.LEFT, True))
    assert bs.choice[0].profile == assignment.NEW
    bs.event(KeysEvent("c1", Key.SOUTH, True))
    assert bs.choice[0].phase == "name"
    bs.draw(app.area)
    bs.event(KeysEvent("c1", Key.SOUTH, True))
    bs.event(KeysEvent("c1", Key.START, True))
    assert bs.choice[0].phase == "bind" and bs.choice[0].profile == "A"
    bs.draw(app.area)
    bs.event(KeysEvent("c1", Key.SOUTH, True))
    bs.event(KeysEvent("c1", Key.WEST, True))
    bs.event(KeysEvent("c1", Key.EAST, True))
    assert bs.choice[0].phase == "bind"
    bs.event(KeysEvent("c1", Key.START, True))
    assert bs.choice[0].phase == "profile"
    assert app.profile.binding("controller", "A", "gba")["WEST"] == "A"
    bs.event(KeysEvent("c2", Key.RIGHT, True))
    assert bs.choice[1].profile == "A"
    bs.event(KeysEvent("c2", Key.SOUTH, True))
    bs.event(KeysEvent("c1", Key.SOUTH, True))
    assert started["devices"] == ["c1", "c2"]
    data = json.loads((s.dir / "session.json").read_text(encoding="utf-8"))
    assert [sp["profile"] for sp in data["player"]] == ["A", "A"]


def test_legacy_own_binding_becomes_a_profile(app, tmp_path, monkeypatch):
    """A session's old own binding is converted to a profile."""
    from soullink.ui import assignment

    _started(monkeypatch)
    s = fake_session(tmp_path / "S")
    s.player[0].keys = {"WEST": "A", "SOUTH": "B", "L2": "MENU"}
    bs = assignment.AssignmentScreen(app, s)
    app.switch(bs)
    bs.event(KeysEvent("c1", Key.SOUTH, True))
    assert bs.choice[0].profile == "Player 1" and s.player[0].keys is None
    assert app.profile.binding("controller", "Player 1", "gba")["WEST"] == "A"
    bs.event(KeysEvent("c1", Key.NORTH, True))
    assert bs.choice[0].phase == "bind"


def test_keyboard_profile_is_bound_with_real_keys(app, tmp_path, monkeypatch):
    """A keyboard profile is bound with real key presses."""
    from soullink.ui import assignment

    _started(monkeypatch)
    s = fake_session(tmp_path / "S")
    name = app.profile.create("keyboard", "gba", "Keys")
    bs = assignment.AssignmentScreen(app, s)
    app.switch(bs)
    key(pygame.K_RETURN)
    app.run(max_images=2)
    assert bs.choice[0].kind == "keyboard"
    bs.choice[0].profile = name
    bs.event(KeysEvent("keyboard", Key.NORTH, True))
    bs.choice[0].menu.selection = 0
    bs.event(KeysEvent("keyboard", Key.SOUTH, True))
    bs.raw(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_k, mod=0, unicode="k", scancode=0))
    bs.event(KeysEvent("keyboard", Key.EAST, True))
    assert bs.choice[0].phase == "bind"
    bs.raw(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0))
    assert bs.choice[0].phase == "bind"
    bs.raw(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode="\r", scancode=0))
    bs.event(KeysEvent("keyboard", Key.START, True))
    assert bs.choice[0].phase == "profile" and app.profile.binding("keyboard", "Keys", "gba")["k"] == "A"


def test_back_without_assignment_returns_to_the_start(app, tmp_path):
    """Back without any joined player returns to the start screen."""
    from soullink.ui.start import StartScreen
    from soullink.ui.assignment import AssignmentScreen

    app.switch(AssignmentScreen(app, fake_session(tmp_path / "S")))
    app.screen.event(KeysEvent("c1", Key.EAST, True))
    assert isinstance(app.screen, StartScreen)


def test_wizard_for_unknown_joystick(app, tmp_path, monkeypatch):
    """An unknown joystick starts the setup wizard."""
    from soullink.ui.assignment import AssignmentScreen

    monkeypatch.setattr(app.devices, "unknown", lambda g: g == "j9")
    monkeypatch.setattr(app.devices, "guid", lambda g: "guid-cheap")
    bs = AssignmentScreen(app, fake_session(tmp_path / "S"))
    app.switch(bs)
    bs.event(RawEvent("j9", {"type": "button", "index": 0}))
    assert bs.wizard is not None
    for i in range(len(STEPS)):
        bs.event(RawEvent("j9", {"type": "button", "index": i}))
    app.run(max_images=1)
    assert bs.wizard is None
    data = json.loads((tmp_path / "controller-bindings.json").read_text(encoding="utf-8"))
    assert len(data["guid-cheap"]) == len(STEPS)


def test_list_only_offers_profiles_of_the_system(app, tmp_path, monkeypatch):
    """A GBA session lists only GBA profiles, an NDS session only NDS profiles."""
    from soullink.ui import assignment

    _started(monkeypatch)
    app.profile.create("controller", "gba", "Gba")
    app.profile.create("controller", "nds", "Nds")
    for system, name in (("gba", "Gba"), ("nds", "Nds")):
        bs = assignment.AssignmentScreen(app, fake_session(tmp_path / system, system=system))
        bs.event(KeysEvent("c1", Key.SOUTH, True))
        assert bs._options(bs.choice[0]) == [None, name, assignment.NEW]


def test_profile_is_deleted_after_confirmation(app, tmp_path, monkeypatch):
    """X asks before deleting; B keeps the profile, A deletes it and players who had it fall back."""
    from soullink.ui import assignment

    _started(monkeypatch)
    app.profile.create("controller", "gba", "A")
    app.profile.create("controller", "gba", "B")
    bs = assignment.AssignmentScreen(app, fake_session(tmp_path / "S"))
    app.switch(bs)
    for device in ("c1", "c2"):
        bs.event(KeysEvent(device, Key.SOUTH, True))
        bs.event(KeysEvent(device, Key.DOWN, True))
    assert [bs.choice[i].profile for i in (0, 1)] == ["A", "A"]
    bs.event(KeysEvent("c2", Key.SOUTH, True))
    bs.event(KeysEvent("c1", Key.WEST, True))
    assert bs.choice[0].phase == "delete"
    bs.draw(app.area)
    bs.event(KeysEvent("c1", Key.EAST, True))
    assert bs.choice[0].phase == "profile" and app.profile.exists("controller", "A", "gba")
    bs.event(KeysEvent("c1", Key.WEST, True))
    bs.event(KeysEvent("c1", Key.SOUTH, True))
    assert not app.profile.exists("controller", "A", "gba")
    assert bs.choice[0].phase == "profile" and bs.choice[0].profile == "B"
    assert bs.choice[1].phase == "profile" and bs.choice[1].profile is None
    bs.event(KeysEvent("c1", Key.UP, True))
    bs.event(KeysEvent("c1", Key.WEST, True))
    assert bs.choice[0].phase == "profile"
