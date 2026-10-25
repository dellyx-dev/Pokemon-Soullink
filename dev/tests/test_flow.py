"""Tests of the flow through new-session, randomize, assignment, resume and deletion."""

import json
import time

import pygame
import pytest

from conftest import fake_gba
from soullink.randomizer import Result
from ui_helpers import dummy_app, key


@pytest.fixture
def app(monkeypatch, tmp_path):
    """App with ROMs and presets."""
    roms = tmp_path / "roms"
    roms.mkdir()
    (roms / "Pokemon Emerald.gba").write_bytes(fake_gba("BPED"))
    (tmp_path / "settings.json").write_text(json.dumps({"rom_dir": str(roms)}), encoding="utf-8")
    a = dummy_app(monkeypatch, tmp_path)
    yield a
    a.close()


def _until(app, condition, timeout=10):
    """Runs frames until the condition holds or the timeout expires."""
    end = time.monotonic() + timeout
    while time.monotonic() < end and not condition():
        app.run(max_images=1)
    return condition()


def _new_session_with_two_players(app):
    """Opens the new-session screen and sets two players."""
    from soullink.ui.new_session import NewSessionScreen

    key(pygame.K_RETURN)
    app.run(max_images=2)
    assert isinstance(app.screen, NewSessionScreen)
    assert app.screen.model.preset is None
    key(pygame.K_LEFT)
    key(pygame.K_LEFT)
    app.run(max_images=2)
    assert app.screen.model.count == 2
    key(pygame.K_UP)
    key(pygame.K_x)
    app.run(max_images=2)


def test_new_session_without_randomizer(app, tmp_path):
    """A new session without randomizer is created and listed."""
    from soullink.ui.assignment import AssignmentScreen

    _new_session_with_two_players(app)
    assert _until(app, lambda: isinstance(app.screen, AssignmentScreen))
    sessions = tmp_path / "Sessions"
    (dir,) = list(sessions.iterdir())
    assert dir.name.endswith("Emerald-x2")
    assert (dir / "p1" / "rom.gba").read_bytes() == fake_gba("BPED")
    assert (dir / "p2" / "rom.gba").exists()
    assert not list(dir.glob("basis-*"))
    data = json.loads((dir / "session.json").read_text(encoding="utf-8"))
    assert [(s["audio"], s["volume"]) for s in data["player"]] == [(False, 0), (False, 0)]


def test_randomizer_error_offers_another_game(app, tmp_path, monkeypatch):
    """A randomizer error offers choosing another game."""
    from soullink.ui import randomize
    from soullink.ui.new_session import NewSessionScreen

    real = randomize.without_randomizer
    monkeypatch.setattr(randomize, "without_randomizer",
                        lambda nr, q, o: Result(nr, False, None, "broken") if nr == 2 else real(nr, q, o))
    _new_session_with_two_players(app)
    assert _until(app, lambda: app.screen.menu is not None)
    assert app.screen.results[2].message == "broken"
    key(pygame.K_DOWN)
    key(pygame.K_x)
    app.run(max_images=2)
    assert isinstance(app.screen, NewSessionScreen)
    assert app.screen.model.count == 2
    assert not list((tmp_path / "Sessions").iterdir())


def test_resume_lists_session(app, tmp_path):
    """The resume screen lists the saved session."""
    from soullink.ui.resume import ResumeScreen
    from soullink.ui.start import StartScreen
    from soullink.ui.assignment import AssignmentScreen

    _new_session_with_two_players(app)
    assert _until(app, lambda: isinstance(app.screen, AssignmentScreen))
    app.switch(StartScreen(app))
    key(pygame.K_DOWN)
    key(pygame.K_RETURN)
    app.run(max_images=2)
    assert isinstance(app.screen, ResumeScreen)
    assert len(app.screen.sessions) == 1
    assert "Emerald" in app.screen.menu.entries[0]
    key(pygame.K_x)
    app.run(max_images=2)
    assert isinstance(app.screen, AssignmentScreen)


def _press(bs, key_):
    """Sends a key press to the screen."""
    from soullink.input.devices import KeysEvent

    bs.event(KeysEvent("keyboard", key_, True))


def test_player_name_via_the_on_screen_keyboard(app, tmp_path):
    """A player name is entered with the on-screen keyboard."""
    from soullink.input.keys import Key
    from soullink.ui.new_session import NewSessionScreen
    from soullink.ui.assignment import AssignmentScreen

    bs = NewSessionScreen(app)
    app.switch(bs)
    _press(bs, Key.LEFT)
    _press(bs, Key.LEFT)
    _press(bs, Key.DOWN)
    _press(bs, Key.SOUTH)
    assert bs.keyboard is not None and bs.keyboard_for == 1
    bs.draw(app.area)
    _press(bs, Key.SOUTH)
    _press(bs, Key.START)
    assert bs.keyboard is None and bs.model.names == {1: "A"} and bs.rows()[1][1] == "A"
    _press(bs, Key.DOWN)
    _press(bs, Key.SOUTH)
    _press(bs, Key.START)
    assert bs.model.names == {1: "A"} and bs.rows()[2][1] == "Player 2"
    bs.draw(app.area)
    _press(bs, Key.START)
    assert _until(app, lambda: isinstance(app.screen, AssignmentScreen))
    assert app.screen.game_names == ["A · Emerald", "Emerald"]
    (dir,) = list((tmp_path / "Sessions").iterdir())
    data = json.loads((dir / "session.json").read_text(encoding="utf-8"))
    assert [s["name"] for s in data["player"]] == ["A", None]


def test_session_is_deleted_only_after_typing_delete(app, tmp_path):
    """A session is deleted only after typing DELETE."""
    from soullink.input.keys import Key
    from soullink.ui.resume import ResumeScreen
    from soullink.ui.assignment import AssignmentScreen

    _new_session_with_two_players(app)
    assert _until(app, lambda: isinstance(app.screen, AssignmentScreen))
    (dir,) = list((tmp_path / "Sessions").iterdir())
    bs = ResumeScreen(app)
    app.switch(bs)
    _press(bs, Key.WEST)
    assert bs.delete is not None
    _press(bs, Key.EAST)
    assert bs.delete is None and dir.exists()
    _press(bs, Key.WEST)
    _press(bs, Key.SOUTH)
    _press(bs, Key.START)
    assert bs.wrong and bs.delete is not None and dir.exists()
    bs.draw(app.area)
    bs.delete.text = "DELETE"
    _press(bs, Key.START)
    assert bs.delete is None and not dir.exists() and bs.sessions == []
    bs.draw(app.area)
    _press(bs, Key.WEST)
    assert bs.delete is None
