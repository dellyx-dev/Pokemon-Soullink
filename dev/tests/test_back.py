"""B and Escape go back in all screens (the Steam Controller maps B to Escape)."""
import json

import pygame
import pytest

from conftest import fake_gba
from soullink.randomizer import Result
from ui_helpers import dummy_app, fake_session


@pytest.fixture
def app(monkeypatch, tmp_path):
    """App with ROMs and presets for the screens."""
    roms = tmp_path / "roms"
    roms.mkdir()
    (roms / "Pokemon Emerald.gba").write_bytes(fake_gba("BPED"))
    (tmp_path / "settings.json").write_text(json.dumps({"rom_dir": str(roms)}), encoding="utf-8")
    a = dummy_app(monkeypatch, tmp_path)
    yield a
    a.close()


def esc(screen):
    """Sends an Escape key event to the screen."""
    screen.raw(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="\x1b", scancode=41))


def test_new_session(app):
    """B in the new-session screen returns to the start screen."""
    from soullink.ui.new_session import NewSessionScreen
    from soullink.ui.start import StartScreen

    app.switch(NewSessionScreen(app))
    esc(app.screen)
    assert isinstance(app.screen, StartScreen)


def test_new_session_closes_the_name_input_first(app):
    """B in the new-session screen closes the name input first."""
    from soullink.ui.new_session import NewSessionScreen

    from soullink.ui.keyboard import VirtualKeyboard

    bs = NewSessionScreen(app)
    app.switch(bs)
    bs.keyboard = VirtualKeyboard("Evening")
    esc(bs)
    assert app.screen is bs and bs.keyboard is None


def test_resume(app):
    """B in the resume screen returns to the start screen."""
    from soullink.ui.resume import ResumeScreen
    from soullink.ui.start import StartScreen

    app.switch(ResumeScreen(app))
    esc(app.screen)
    assert isinstance(app.screen, StartScreen)


def test_randomize_error(app, monkeypatch):
    """B in the randomize error menu returns to the new-session screen."""
    from soullink.ui import randomize
    from soullink.ui.new_session import NewSessionScreen, NewSessionModel
    from soullink.roms import find_base_roms
    from datetime import date

    monkeypatch.setattr(randomize, "without_randomizer", lambda nr, q, o: Result(nr, False, None, "broken"))
    model = NewSessionModel(find_base_roms(app.rom_dir), [], date.today())
    bs = randomize.RandomizeScreen(app, model)
    app.switch(bs)
    bs._thread.join()
    bs.update(0.016)
    assert bs.menu is not None
    esc(bs)
    assert isinstance(app.screen, NewSessionScreen)


def test_randomize_without_java(app, monkeypatch, tmp_path):
    """Without Java the randomize screen asks for an installation instead of starting."""
    from soullink import paths
    from soullink.language import t
    from soullink.ui import randomize
    from soullink.ui.new_session import NewSessionModel
    from soullink.roms import find_base_roms
    from datetime import date

    monkeypatch.setattr(paths, "java_program", lambda: None)
    model = NewSessionModel(find_base_roms(app.rom_dir), [tmp_path / "p.rnqs"], date.today())
    bs = randomize.RandomizeScreen(app, model)
    assert bs.error == t("randomize.java_missing") and bs._thread is None


def test_assignment(app, tmp_path):
    """B in the assignment screen returns to the start screen."""
    from soullink.ui.start import StartScreen
    from soullink.ui.assignment import AssignmentScreen

    app.switch(AssignmentScreen(app, fake_session(tmp_path / "S")))
    esc(app.screen)
    assert isinstance(app.screen, StartScreen)


def test_start_stays(app):
    """B in the start screen stays there."""
    from soullink.ui.start import StartScreen

    esc(app.screen)
    assert isinstance(app.screen, StartScreen) and app.runs
