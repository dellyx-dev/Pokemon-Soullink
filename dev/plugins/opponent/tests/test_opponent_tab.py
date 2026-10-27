"""Tests of the opponent tab."""
from types import SimpleNamespace

import pygame

from conftest import plugin_module
from soullink import types
from soullink.input.keys import Key
from soullink.pokemon_data import Opponent
from soullink.ui import graphics
from soullink.ui.types_overlay import TypesOverlay, TypesTab

OpponentTab = plugin_module("opponent", "tab").OpponentTab


def _texts(monkeypatch) -> list[str]:
    """All drawn texts (drawing itself keeps running)."""
    drawn, original = [], graphics.text
    monkeypatch.setattr(graphics, "text", lambda area, content, *a, **k: drawn.append(content)
                        or original(area, content, *a, **k))
    return drawn


def test_title_position_and_ram(opponent_api):
    """The tab has its title, position and RAM interval."""
    g = OpponentTab(opponent_api, 1)
    assert (g.id, g.position, g.ram_interval, g.title(), g.title(short=True)) == ("opponent", 20, 1.5, "Opponent", "OPP")


def test_defense_by_choosing_two_types(opponent_api):
    """The defense is computed for two chosen types."""
    o = TypesOverlay([OpponentTab(opponent_api, 1), TypesTab()])
    g = o.find("opponent")
    assert o.active is g and g.defender == ["Normal"]
    o.event(Key.RIGHT)
    o.event(Key.RIGHT)
    o.event(Key.DOWN)
    for _ in range(9):
        o.event(Key.RIGHT)
    assert g.defender == ["Water", "Ground"]
    o.event(Key.LEFT)
    o.event(Key.LEFT)
    assert g.defender == ["Water", "Fighting"]
    for _ in range(7):
        o.event(Key.LEFT)
    assert g.defender == ["Water"]
    assert ("<>", "Type") in g.hints() and ("^", "1st/2nd type") in g.hints()


def test_opponent_in_battle_and_strong_against(opponent_api, monkeypatch):
    """The opponent in battle and the types strong against it are shown."""
    pygame.font.init()
    g = OpponentTab(opponent_api, 1)
    o = TypesOverlay([g, TypesTab()])
    g.battle = [[Opponent(232, 2, 16), Opponent(41, 3, 9, True, ("Poison", "Flying"))]]
    assert g.active_opponent() == [g.battle[0][1]]
    g.battle = [[Opponent(232, 2, 0), Opponent(41, 3, 9)]]
    assert g.active_opponent() == [g.battle[0][1]]
    assert types.strong_against(["Fire"]) == ["Grass", "Ice", "Bug", "Steel"]
    assert types.strong_against(["Poison", "Flying"]) == ["Grass", "Fighting", "Bug"]
    g.battle = [[Opponent(41, 3, 9, True, ("Poison", "Flying"))]]
    opponent_api.dex_value = SimpleNamespace(pokemon_after_nr={}, name=lambda nr: "Zubat")
    assert g.hints() == [("L/R", "Page"), ("B", "Close")]
    assert not g.event(Key.RIGHT)
    area = pygame.Surface((1920, 1080))
    texts = _texts(monkeypatch)
    for range_, pixel in (((0, 0, 1920, 1080), 54), ((1035, 540, 810, 540), 27), ((0, 0, 480, 720), 24)):
        o.draw(area, pygame.Rect(range_), pixel)
    assert "Zubat" in texts and "Lv 3" in texts and "Moves of these types are …" in texts
    shown, original = [], g._not_send
    monkeypatch.setattr(g, "_not_send", lambda area, rect, u, list_, *a, **k:
                        shown.append(list_) or original(area, rect, u, list_, *a, **k))
    o.draw(area, pygame.Rect(0, 0, 1920, 1080), 54)
    assert ["Grass", "Fighting", "Bug"] in shown


def test_fighting_opponents_are_drawn(opponent_api):
    """Fighting opponents (Tyrogue, Croagunk) are drawn, alone and in a double battle."""
    pygame.font.init()
    g = OpponentTab(opponent_api, 1)
    o = TypesOverlay([g, TypesTab()])
    opponent_api.dex_value = SimpleNamespace(pokemon_after_nr={}, name=lambda nr: "Tyrogue")
    area = pygame.Surface((1920, 1080))
    for battle in ([[Opponent(236, 4, 18, True, ("Fighting",))]],
                   [[Opponent(236, 4, 18, True, ("Fighting",)), Opponent(453, 5, 20, True, ("Poison", "Fighting"))]]):
        g.battle = battle
        for range_, pixel in (((0, 0, 1920, 1080), 54), ((0, 0, 480, 720), 24)):
            o.draw(area, pygame.Rect(range_), pixel)


def _drawn_types(module, monkeypatch):
    """All drawn chips as (type, rectangle)."""
    card, original = [], module.draw_type
    monkeypatch.setattr(module, "draw_type", lambda area, type_, rect, *a, **k: card.append(
        (type_, pygame.Rect(rect))) or original(area, type_, rect, *a, **k))
    return card


def test_double_battle_shows_all_effects(opponent_api, monkeypatch):
    """A double battle shows the effects for both opponents."""
    pygame.font.init()
    module = plugin_module("opponent", "tab")
    g = module.OpponentTab(opponent_api, 1)
    g.battle = [[Opponent(41, 3, 9, True, ("Poison", "Flying")), Opponent(25, 7, 20, True, ("Electric",))]]
    opponent_api.dex_value = SimpleNamespace(pokemon_after_nr={}, name=lambda nr: "Zubat")
    short, original = [], module.draw_type
    monkeypatch.setattr(module, "draw_type", lambda *a, **k: (short.append(a[1]) if k.get("short") else None)
                        or original(*a, **k))
    card = _drawn_types(module, monkeypatch)
    mass, groups = [], g._groups
    monkeypatch.setattr(g, "_groups", lambda area, rect, u, gr, m, *a, **k: mass.append(m)
                        or groups(area, rect, u, gr, m, *a, **k))
    range_ = pygame.Rect(23, 220, 593, 285)
    g.draw(pygame.Surface((1280, 720)), range_, 27)
    drawn = [type_ for type_, _ in card]
    for defender in (["Poison", "Flying"], ["Electric"]):
        expected = [type_ for list_ in types.defense(defender).values() for type_ in list_]
        expected += types.strong_against(defender)
        assert all(drawn.count(type_) >= 1 for type_ in expected), (defender, expected, drawn)
    assert "Ground" in drawn
    assert all(range_.contains(r) for _, r in card)
    assert not short
    assert mass and all(m.columns == 1 for m in mass)


def test_do_not_send_comes_before_the_effects(opponent_api, monkeypatch):
    """"Do not send" comes before the effects."""
    pygame.font.init()
    g = OpponentTab(opponent_api, 1)
    g.battle = [[Opponent(41, 3, 9, True, ("Poison", "Flying"))]]
    opponent_api.dex_value = SimpleNamespace(pokemon_after_nr={}, name=lambda nr: "Zubat")
    texts = _texts(monkeypatch)
    g.draw(pygame.Surface((1920, 1080)), pygame.Rect(0, 0, 1920, 1080), 54)
    assert texts.index("Don't send") < texts.index("Moves of these types are …")
    assert "Zubat hits them super effectively" in texts


def test_double_battle_two_opponents(opponent_api):
    """A double battle shows two opponents."""
    g = OpponentTab(opponent_api, 1)
    g.battle = [[Opponent(41, 3, 9, True), Opponent(25, 4, 7, True), Opponent(16, 2, 5)]]
    assert g.active_opponent() == g.battle[0][:2]
    g.battle = [[Opponent(41, 3, 9)], [Opponent(25, 4, 0), Opponent(16, 2, 5)]]
    assert g.active_opponent() == [g.battle[0][0], g.battle[1][1]]


def test_cards_stay_inside_the_tab(opponent_api, monkeypatch):
    """The cards stay inside the tab."""
    pygame.font.init()
    module = plugin_module("opponent", "tab")
    g = module.OpponentTab(opponent_api, 1)
    g.battle = [[Opponent(41, 3, 9, True, ("Poison", "Flying")), Opponent(25, 7, 20, True, ("Electric",))]]
    opponent_api.dex_value = SimpleNamespace(pokemon_after_nr={}, name=lambda nr: "Zubat")
    card, original = [], module.draw_type
    monkeypatch.setattr(module, "draw_type", lambda area, type_, rect, *a, **k: card.append(pygame.Rect(rect))
                        or original(area, type_, rect, *a, **k))
    area = pygame.Surface((1280, 720))
    for range_, u in (((23, 220, 593, 285), 27), ((10, 60, 280, 200), 13), ((0, 0, 1200, 600), 40)):
        card.clear()
        g.draw(area, pygame.Rect(range_), u)
        assert card and all(pygame.Rect(range_).contains(r) for r in card), range_


def test_in_battle_without_rom_data_shows_loading(opponent_api, monkeypatch):
    """In battle without ROM data the tab shows that it loads."""
    pygame.font.init()
    g = OpponentTab(opponent_api, 1)
    area = pygame.Surface((800, 500))
    texts = _texts(monkeypatch)
    g.battle = [[Opponent(41, 3, 9, True, ("Poison", "Flying"))]]
    g.draw(area, pygame.Rect(0, 0, 800, 500), 30)
    assert texts[0] == "Battle in progress – loading Pokédex data …" and "Not in a battle right now" not in texts
    assert "Pick types:" in texts and g.event(Key.RIGHT)
    opponent_api.error = "Java not found"
    texts.clear()
    g.draw(area, pygame.Rect(0, 0, 800, 500), 30)
    assert texts[0] == "Battle in progress – Pokédex data missing: Java not found"
    g.battle = None
    texts.clear()
    g.draw(area, pygame.Rect(0, 0, 800, 500), 30)
    assert texts[0] == "Not in a battle right now"


def test_draw_all_sizes(opponent_api):
    """The tab draws at all sizes."""
    pygame.font.init()
    area = pygame.Surface((1920, 1080))
    g = OpponentTab(opponent_api, 1)
    o = TypesOverlay([g, TypesTab()])
    o.event(Key.DOWN)
    o.event(Key.RIGHT)
    for range_, pixel in (((0, 0, 1920, 1080), 54), ((1035, 540, 810, 540), 27), ((20, 0, 600, 400), 20),
                           ((0, 0, 480, 720), 24)):
        o.draw(area, pygame.Rect(range_), pixel)
