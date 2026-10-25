"""Tests of the app main loop and the main menu."""

import pygame
import pytest


@pytest.fixture
def app(monkeypatch, tmp_path):
    """App in a headless pygame window."""
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    monkeypatch.setenv("SOULLINK_BASE", str(tmp_path))
    from soullink.ui.app import App

    a = App(tmp_path, window=True)
    yield a
    if pygame.get_init() or pygame.display.get_init():
        a.close()


def key(key):
    """Posts a key press event to pygame."""
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, mod=0, unicode="", scancode=0))


def test_start_and_end(app):
    """The app starts, runs a few frames and ends."""
    from soullink.ui.start import StartScreen

    app.run(max_images=3)
    assert isinstance(app.screen, StartScreen)
    assert app.size == (1280, 720)
    key(pygame.K_UP)
    key(pygame.K_RETURN)
    app.run(max_images=3)
    assert app.runs and app.screen.question is not None
    key(pygame.K_RETURN)
    app.run(max_images=3)
    assert app.runs and app.screen.question is None
    assert app.screen.menu.selection == 4
    key(pygame.K_RETURN)
    key(pygame.K_DOWN)
    key(pygame.K_RETURN)
    app.run(max_images=3)
    assert not app.runs


def test_after_the_game_input_is_briefly_locked(app):
    """The main menu ignores input briefly after a game ended."""
    import time

    from soullink.input.devices import KeysEvent
    from soullink.input.keys import Key
    from soullink.ui.start import StartScreen

    bs = StartScreen(app, lock=0.3)
    bs.event(KeysEvent("c1", Key.UP, True))
    assert bs.menu.selection == 0
    time.sleep(0.35)
    bs.event(KeysEvent("c1", Key.UP, True))
    assert bs.menu.selection == 4


def test_main_menu_without_music_with_about(app):
    """The main menu offers About, and music is not started without files."""
    from soullink.input.devices import KeysEvent
    from soullink.input.keys import Key
    from soullink.ui.start import ENTRIES, ABOUT
    from soullink.ui.about import AboutScreen

    assert "start.music" not in ENTRIES
    assert all((app.base / d).is_dir() for d in ("sessions", "presets", "sound", "roms/gba", "roms/nds"))
    bs = app.screen
    bs.draw(app.area)
    bs.menu.selection = ABOUT
    bs.event(KeysEvent("c1", Key.SOUTH, True))
    assert isinstance(app.screen, AboutScreen)
    app.screen.draw(app.area)
    app.screen.event(KeysEvent("c1", Key.EAST, True))
    assert not isinstance(app.screen, AboutScreen)


def test_hold_repeats_in_main_menu(app):
    """Holding a direction key repeats it in the main menu."""
    from soullink.input.devices import KeysEvent
    from soullink.input.keys import Key

    bs = app.screen
    app.input(KeysEvent("c1", Key.DOWN, True))
    assert bs.menu.selection == 1
    app.repeat()
    assert bs.menu.selection == 1
    for _ in range(2):
        app.hold.next_ = 0.0
        app.repeat()
    assert bs.menu.selection == 3
    app.input(KeysEvent("c2", Key.DOWN, False))
    assert app.hold.key == Key.DOWN
    app.input(KeysEvent("c1", Key.DOWN, False))
    app.hold.next_ = 0.0
    app.repeat()
    assert bs.menu.selection == 3


def test_main_menu_names_author(app):
    """The main menu shows the author's name."""
    from soullink import AUTHOR
    from soullink.language import t

    assert AUTHOR in t("start.of", author=AUTHOR)
    app.screen.draw(app.area)
