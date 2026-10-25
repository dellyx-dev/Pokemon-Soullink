"""Tests of the About screen."""

import pytest

from soullink.input.devices import KeysEvent
from soullink.input.keys import Key
from ui_helpers import dummy_app


@pytest.fixture
def app(monkeypatch, tmp_path):
    """App with plugin and licence setup for the About screen."""
    a = dummy_app(monkeypatch, tmp_path)
    yield a
    a.close()


def press(bs, key):
    """Sends a key press to the screen."""
    bs.event(KeysEvent("c1", key, True))


def test_all_license_texts_present():
    """All licence texts listed in the About screen exist."""
    from soullink.ui.about import THIRD, license_text

    for name, *_, files in THIRD:
        rows = license_text(files)
        assert len(rows) > 20 and not any("not found" in z for z in rows), name


def test_missing_license_text(monkeypatch, tmp_path):
    """A missing licence text is shown as a notice instead of failing."""
    from soullink import paths
    from soullink.ui.about import license_text

    monkeypatch.setattr(paths, "license_dir", lambda: tmp_path)
    assert license_text(["GPL-3.0.txt"]) == ["License text not found: GPL-3.0.txt"]


def test_row_choose_text_page_and_back(app):
    """A row opens its licence text, which can be paged and closed again."""
    from soullink.ui.start import StartScreen
    from soullink.ui.about import THIRD, AboutScreen

    bs = AboutScreen(app)
    app.switch(bs)
    press(bs, Key.UP)
    assert bs.selection == len(THIRD) - 1
    press(bs, Key.DOWN)
    press(bs, Key.DOWN)
    press(bs, Key.SOUTH)
    assert bs.open_ == 1
    bs.draw(app.area)
    press(bs, Key.RIGHT)
    assert bs.scroll == bs._page - 1
    for _ in range(100):
        press(bs, Key.RIGHT)
    assert bs.scroll == len(bs._rows) - bs._page
    bs.draw(app.area)
    press(bs, Key.EAST)
    assert bs.open_ is None and isinstance(app.screen, AboutScreen)
    bs.draw(app.area)
    press(bs, Key.EAST)
    assert isinstance(app.screen, StartScreen)


def test_about_lists_active_plugins_with_license(monkeypatch, tmp_path):
    """The About screen lists enabled plugins together with their licence."""
    import pygame

    from conftest import plugin_create
    from soullink.ui import graphics
    from soullink.ui.about import THIRD, AboutScreen

    dir = tmp_path / "plugins"
    path = plugin_create(dir, "coplayer", data={"version": "1.2.0", "author": "Dellyx", "license": "LICENSE"},
                          texts={"us": "_name = Other players\n"})
    (path / "LICENSE").write_text("MIT License\n\nCopyright (c) 2026 Dellyx\n", encoding="utf-8")
    plugin_create(dir, "without_license", texts={"us": "_name = Without license\n"})
    plugin_create(dir, "from")
    app = dummy_app(monkeypatch, tmp_path)
    try:
        app.plugins.set_("coplayer", True)
        app.plugins.set_("without_license", True)
        bs = AboutScreen(app)
        app.switch(bs)
        assert [i.id for i in bs.plugins] == ["coplayer", "without_license"]
        press(bs, Key.UP)
        assert bs.selection == len(THIRD) + 1
        app.area.blit(graphics.background(app.size), (0, 0))
        bs.draw(app.area)
        pygame.image.save(app.area, str(tmp_path / "about_plugins.png"))
        press(bs, Key.SOUTH)
        assert bs.open_ is None
        press(bs, Key.UP)
        press(bs, Key.SOUTH)
        assert bs.open_ == len(THIRD)
        bs.draw(app.area)
        assert bs._rows[:3] == ["MIT License", "", "Copyright (c) 2026 Dellyx"]
        press(bs, Key.EAST)
        assert bs.open_ is None
    finally:
        app.close()
