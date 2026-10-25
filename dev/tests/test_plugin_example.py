"""Tests that the documented example plugin loads and works."""
import shutil
from pathlib import Path

import pygame

from ui_helpers import FakeProcess, dummy_app, fake_session

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "plugin-example" / "hello"


def test_example_plugin_runs(monkeypatch, tmp_path):
    """The documented example plugin loads and works."""
    shutil.copytree(EXAMPLE, tmp_path / "plugins" / "hello")
    app = dummy_app(monkeypatch, tmp_path)
    try:
        app.plugins.new_read()
        info = app.plugins.info("hello")
        assert (info.status, info.name) == ("ok", "Hello")
        assert not app.plugins.enabled("hello")
        app.plugins.set_("hello", True)
        (_, plugin), = app.plugins.active()
        assert [e.key for e in plugin.settings()] == ["loud"]
        assert plugin.display_names() == [("clock", "Play time in minutes")]

        from soullink.ui.game import GameScreen

        FakeProcess.instances = []
        bs = GameScreen(app, fake_session(tmp_path / "S", 3), ["keyboard", "c1", "c2"], process_factory=FakeProcess)
        app.switch(bs)
        bs.update(0.016)
        assert [r.id for r in bs.player[0].types.tab] == ["types", "hello"]
        (entry,) = plugin.player_menu(1)
        entry.trigger()
        assert plugin.greetings[1] == 1 and bs.player[0].hint == "Hello!"
        area = pygame.Surface((1280, 720))
        bs.player[0].types.show("hello")
        bs._types_open(bs.player[0])
        bs.draw(area)
        assert plugin.api.id == "hello" and app.plugins.enabled("hello")
    finally:
        app.close()
