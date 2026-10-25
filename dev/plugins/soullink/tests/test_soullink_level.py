"""Tests of the level cap list and tab."""
import json

import pygame
import pytest

from conftest import plugin_module
from soullink import dex as D
from soullink.input.keys import Key
from test_dex import DATA

level = plugin_module("soullink", "level")
Battle, battles = level.Battle, level.battles
LevelTab = plugin_module("soullink", "tab").LevelTab


@pytest.fixture
def dex(tmp_path) -> D.Dex:
    """A dex with gym leaders, Elite Four and champion."""
    path = tmp_path / "dex.json"
    path.write_text(json.dumps(DATA, ensure_ascii=False), encoding="utf-8")
    return D.load(path)


def test_level_list_first_battle_and_rematch(dex):
    """The level list has first fights and rematches."""
    list_ = [(k.kind, k.number, k.round_, k.name, k.level) for k in battles(dex)]
    assert list_ == [("arena", 1, 1, "Rocko", 14), ("arena", 2, 1, "Misty", 21),
                     ("top4", 1, 1, "Lorelei", 54), ("champ", 1, 1, "Blue", 63),
                     ("top4", 1, 2, "Lorelei", 66), ("champ", 1, 2, "Blue", 75)]


def test_level_list_hgss_has_16_gyms(dex):
    """The HGSS level list has 16 gyms."""
    dex.rom_code = "IPGD"
    gyms = [k.number for k in battles(dex) if k.kind == "arena"]
    assert gyms == [1, 2, 9]
    assert not any(k.kind == "champ" for k in battles(dex))


def test_level_order_hgss_gyms_9_to_16_after_the_first_elite_four(dex):
    """HGSS gyms 9-16 come after the first Elite Four."""
    dex.rom_code = "IPGD"
    order = [(k.kind, k.number, k.round_) for k in battles(dex)]
    assert order == [("arena", 1, 1), ("arena", 2, 1), ("top4", 1, 1), ("arena", 9, 1), ("top4", 1, 2)]


def test_level_cap_by_badge_count(api):
    """The level cap follows the badge count."""
    list_ = [Battle("arena", n, 1, "", 10) for n in range(1, 9)] + [Battle("top4", 1, 1, "", 50)] + \
        [Battle("arena", n, 1, "", 60) for n in range(9, 17)] + [Battle("top4", 1, 2, "", 70)]
    r = LevelTab(api, None, 1)
    for badge, kind_number in ((0, ("arena", 1)), (7, ("arena", 8)), (8, ("top4", 1)), (9, ("arena", 10)),
                              (15, ("arena", 16)), (16, ("top4", 1))):
        r.badge = lambda o=badge: o
        k = list_[r.cap(list_)]
        assert (k.kind, k.number) == kind_number, badge
    assert list_[r.cap(list_)].round_ == 2


def test_level_tab_draws_cap_and_hook(api, dex):
    """The level tab draws the cap and its hook works."""
    class Data:
        """Fake data source for the tab."""

        def dex(self, nr):
            """The prepared dex."""
            return dex

        def dex_error(self, nr):
            """No error."""
            return None

    pygame.font.init()
    r = LevelTab(api, Data(), 1, lambda: 1)
    assert r.title() == "Levels" and r.title(short=True) == "LVL"
    assert [r.group(k, False) for k in battles(dex)][:3] == ["Gyms", "Gyms", "Elite Four"]
    assert r.label(battles(dex)[0]) == "Gym 1" and r.cap(battles(dex)) == 1
    r.draw(pygame.Surface((600, 400)), pygame.Rect(0, 0, 600, 400), 24)
    assert r.event(Key.DOWN) and r.selection == 1
