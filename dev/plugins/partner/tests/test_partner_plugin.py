"""Tests of the partner plugin in the game: Pokemon behind the player, no eggs and no HeartGold/SoulSilver, switch, language files."""
from pathlib import Path

import pygame

from ui_helpers import FakeProcess, fake_session

PLUGIN = Path(__file__).resolve().parents[1]
RED, BLUE = (255, 0, 0), (0, 0, 255)


class FakeIcons:
    """Icon source that returns a red or blue square depending on the frame number."""

    def image(self, kind, number):
        """A 32x32 square, red for even and blue for odd frame numbers."""
        f = pygame.Surface((32, 32))
        f.fill(RED if number % 2 == 0 else BLUE)
        return f


def _game(app, tmp_path, codes=("BPED",), system="gba", name="S"):
    """Game screen with the given game codes."""
    from soullink.ui.game import GameScreen

    FakeProcess.instances = []
    bs = GameScreen(app, fake_session(tmp_path / name, len(codes), codes=codes, system=system),
                    ["keyboard", "c1", "c2", "c3"][:len(codes)], process_factory=FakeProcess)
    app.switch(bs)
    bs.update(0.016)
    return bs


def _plugin(app):
    """The loaded partner plugin object."""
    return dict((i.id, p) for i, p in app.plugins.active())["partner"]


def _world():
    """The core module soullink.world the plugin draws from."""
    from soullink import world

    return world


def _set(process, location):
    """Writes a location into the partner's slot as the worker part would."""
    slot = next(p["slot"] for p in process.plugins if p["id"] == "partner")
    process.slots[slot] = _world().pack(location)


def test_partner_stands_behind_the_player(partner_app, tmp_path):
    """The first team Pokemon is drawn one tile below the player; none for no Pokemon or an egg."""
    bs = _game(partner_app, tmp_path)
    plugin, w = _plugin(partner_app), _world()
    (p1,) = FakeProcess.instances
    assert [p["id"] for p in p1.plugins] == ["partner"] and plugin.show == {1: True}
    plugin.icons[1] = FakeIcons()
    _set(p1, w.Location(0, 3, 19, 39, 0x0800A, False, kind=25))
    bs.update(0.016)
    target = bs._screens(0)[0][0]
    tile = target.width / 15
    area = pygame.Surface(partner_app.size)
    plugin.draw(area, 1, target, 10.0)
    below = (round(target.x + 7.5 * tile), round(target.y + 6.5 * tile - tile * 0.5))
    assert area.get_at(below)[:3] in (RED, BLUE)
    assert area.get_at((round(target.x + 7.5 * tile), round(target.y + 3.5 * tile)))[:3] == (0, 0, 0)
    for kind in (0, 412):
        _set(p1, w.Location(0, 3, 19, 39, 0x0800A, False, kind=kind))
        bs.update(0.016)
        area.fill((0, 0, 0))
        plugin.draw(area, 1, target, 10.0)
        assert area.get_at(below)[:3] == (0, 0, 0)
    bs.leave()


class FootIcons:
    """Icon source with a transparent margin of 4 pixels below the Pokemon's feet."""

    def image(self, kind, number):
        """A 32x32 icon whose red body ends 4 pixels above the bottom edge."""
        f = pygame.Surface((32, 32), pygame.SRCALPHA)
        f.fill(RED, (8, 8, 16, 20))
        return f


def test_partner_feet_stand_on_the_players_ground_line(partner_app, tmp_path):
    """The icon is drawn in game pixel size and its lowest pixel sits where the player's feet are, beside the player."""
    bs = _game(partner_app, tmp_path)
    plugin, w = _plugin(partner_app), _world()
    (p1,) = FakeProcess.instances
    plugin.icons[1] = FootIcons()
    _set(p1, w.Location(0, 3, 19, 39, 0x0800A, False, kind=25))
    bs.update(0.016)
    plugin.trails[1].points = [(plugin.trails[1].points[-1][0] - 1, plugin.trails[1].points[-1][1]),
                               plugin.trails[1].points[-1]]
    target = bs._screens(0)[0][0]
    tile = target.width / 15
    area = pygame.Surface(partner_app.size, pygame.SRCALPHA)
    area.fill((0, 0, 0, 0))
    plugin.draw(area, 1, target, 10.0)
    (body,) = pygame.mask.from_threshold(area, RED + (255,), (1, 1, 1, 1)).get_bounding_rects()
    assert abs(body.bottom - (target.y + 5.5 * tile - tile / 16)) <= 1
    assert abs(body.width - tile) <= 1
    assert abs(body.centerx - (target.x + 6.5 * tile)) <= 1
    bs.leave()


def test_hook_and_switch(partner_app, tmp_path):
    """The frame hook draws the partner and the menu switch hides it."""
    bs = _game(partner_app, tmp_path)
    plugin, w = _plugin(partner_app), _world()
    (p1,) = FakeProcess.instances
    plugin.icons[1] = FakeIcons()
    _set(p1, w.Location(0, 3, 19, 39, 0x0800A, False, kind=25))
    bs.player[0].images["gba"] = pygame.Surface(bs._screens(0)[0][0].size)
    bs.update(0.016)
    target = bs._screens(0)[0][0]
    tile = target.width / 15
    point = (round(target.x + 7.5 * tile), round(target.y + 6.5 * tile - tile * 0.5))
    bs.draw(partner_app.area)
    assert partner_app.area.get_at(point)[:3] in (RED, BLUE)
    plugin.player_menu(1)[0].trigger()
    bs.draw(partner_app.area)
    assert partner_app.area.get_at(point)[:3] == (0, 0, 0) and plugin.show == {1: False}
    bs.leave()


def test_soulsilver_gets_no_partner(partner_app, tmp_path):
    """SoulSilver gets no menu entry, no icons and no worker part."""
    bs = _game(partner_app, tmp_path, codes=("IPGD",), system="nds")
    plugin = _plugin(partner_app)
    assert plugin.player_menu(1) == [] and plugin.icons == {}
    assert FakeProcess.instances[0].plugins == []
    bs.leave()


def test_fits_only_with_a_suitable_game(partner_app, tmp_path):
    """The plugin fits a GBA session and gives a reason for SoulSilver."""
    plugin = _plugin(partner_app)
    assert plugin.fits(fake_session(tmp_path / "a", 1, codes=("BPED",), system="gba")) is True
    assert isinstance(plugin.fits(fake_session(tmp_path / "b", 1, codes=("IPGD",), system="nds")), str)


def test_language_files_equal():
    """Both language files define the same keys."""
    def keys(k):
        """Keys of one language file."""
        text = (PLUGIN / "language" / f"{k}.txt").read_text(encoding="utf-8")
        return {z.split("=")[0].strip() for z in text.splitlines() if "=" in z}
    assert keys("de") == keys("us")
