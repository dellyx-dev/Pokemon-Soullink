"""End to end with a real core: new session, play, save and resume."""
import json
import shutil
import time

import pygame
import pytest

from soullink.input.devices import KeysEvent
from soullink.input.keys import Key
from ui_helpers import dummy_app, key


@pytest.fixture
def app(monkeypatch, tmp_path, test_rom):
    """App for the end-to-end run."""
    roms = tmp_path / "roms"
    roms.mkdir()
    shutil.copyfile(test_rom, roms / "Pokemon Emerald.gba")
    (tmp_path / "settings.json").write_text(json.dumps({"rom_dir": str(roms)}), encoding="utf-8")
    a = dummy_app(monkeypatch, tmp_path)
    yield a
    a.close()


def _until(app, condition, timeout=30):
    """Runs frames until the condition holds or the timeout expires."""
    end = time.monotonic() + timeout
    while time.monotonic() < end and not condition():
        app.run(max_images=1)
    return condition()


def _assign_and_start(app):
    """Assigns keyboard and a controller, confirms both default profiles and starts the game."""
    from soullink.ui.game import GameScreen

    key(pygame.K_RETURN)
    app.run(max_images=1)
    app.screen.event(KeysEvent("c42", Key.SOUTH, True))
    key(pygame.K_RETURN)
    app.run(max_images=1)
    app.screen.draw(app.area)
    app.screen.event(KeysEvent("c42", Key.SOUTH, True))
    app.run(max_images=1)
    assert isinstance(app.screen, GameScreen)
    return app.screen


def _save_and_end(app):
    """Saves and quits through the player menu."""
    from soullink.ui.start import StartScreen

    key(pygame.K_ESCAPE)
    key(pygame.K_UP)
    key(pygame.K_x)
    key(pygame.K_DOWN)
    key(pygame.K_x)
    assert _until(app, lambda: isinstance(app.screen, StartScreen))


def test_end_to_end(app, tmp_path):
    """New session, play, save and resume with a real core (needs a test ROM)."""
    from soullink.ui.assignment import AssignmentScreen

    key(pygame.K_RETURN)
    app.run(max_images=1)
    key(pygame.K_LEFT)
    key(pygame.K_LEFT)
    key(pygame.K_UP)
    key(pygame.K_x)
    assert _until(app, lambda: isinstance(app.screen, AssignmentScreen))
    session = app.screen.session

    game = _assign_and_start(app)
    assert _until(app, lambda: all(sp.images for sp in game.player)), [sp.process.error for sp in game.player]
    press_start = KeysEvent("keyboard", Key.START, True)
    game.event(press_start)
    _until(app, lambda: False, timeout=1.0)
    assert game.mixer is not None
    _save_and_end(app)

    for nr in (1, 2):
        assert session.state(nr).stat().st_size > 100_000
    data = json.loads((session.dir / "session.json").read_text(encoding="utf-8"))
    assert data["core_version"].startswith("0.11")
    assert data["playtime_seconds"] >= 1

    app.screen.locked_until = 0
    key(pygame.K_DOWN)
    key(pygame.K_RETURN)
    key(pygame.K_x)
    assert _until(app, lambda: isinstance(app.screen, AssignmentScreen))
    game = _assign_and_start(app)
    assert _until(app, lambda: all(sp.process.ready_info for sp in game.player))
    for sp in game.player:
        assert sp.process.ready_info["source"].endswith("state.state")
    _save_and_end(app)
