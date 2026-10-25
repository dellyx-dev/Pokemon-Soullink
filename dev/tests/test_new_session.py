"""Tests of the new-session model."""

from datetime import date
from pathlib import Path

from soullink.roms import BaseRom
from soullink.ui.new_session import NewSessionModel

FIRERED = BaseRom(Path("Pokemon FireRed.gba"), None, "BPRD")
EMERALD = BaseRom(Path("Pokemon Emerald.zip"), "s.gba", "BPED")
TODAY = date(2026, 10, 19)


def _model(presets=()):
    """Model with two ROMs and the given presets."""
    return NewSessionModel([FIRERED, EMERALD], list(presets), TODAY)


def test_start_all_players_like_player_1():
    """By default all players start with player 1's game."""
    m = _model()
    assert m.count == 4
    assert [r.game for r in m.player_roms()] == ["FireRed"] * 4


def test_changing_player_1_pulls_the_others_along_only_in_the_same_system():
    """Changing player 1's system keeps the others in the same system."""
    m = _model()
    m.game_change(2, +1)
    assert m.player_roms()[1] == EMERALD and 2 in m.own
    m.game_change(1, +1)
    m.game_change(1, +1)
    assert [r.game for r in m.player_roms()] == ["FireRed", "Emerald", "FireRed", "FireRed"]


def test_count_limits():
    """The player count is limited."""
    m = _model()
    m.count_change(+1)
    assert m.count == 4
    m.count_change(-5)
    assert m.count == 1
    assert len(m.player_roms()) == 1


def test_name():
    """The session name is the entered or the suggested one."""
    m = _model()
    assert m.name == "2026-10-19 FireRed ×4"
    m.game_change(3, +1)
    assert m.name == "2026-10-19 Mixed ×4"
    m.own_name = "Couch-Evening"
    assert m.name == "Couch-Evening"


def test_presets():
    """Presets can be cycled, including "without randomizer"."""
    assert _model().preset is None
    m = _model([Path("a.rnqs"), Path("b.rnqs")])
    assert m.preset == Path("a.rnqs") and m.preset_name == "a"
    m.preset_change(-1)
    assert m.preset is None and m.preset_name == "No randomizer"


PLATINUM = BaseRom(Path("Pokemon Platinum.zip"), "p.nds", "CPUD", "nds")
BLACK = BaseRom(Path("Pokemon Black.nds"), None, "IRBD", "nds")


def test_one_system_per_session():
    """A session has exactly one system."""
    m = NewSessionModel([FIRERED, EMERALD, PLATINUM, BLACK], [], TODAY)
    m.game_change(2, +1)
    assert m.player_roms()[1] == EMERALD
    m.game_change(2, +1)
    assert m.player_roms()[1] == FIRERED
    m.game_change(1, +2)
    assert m.system == "nds"
    assert [r.system for r in m.player_roms()] == ["nds"] * 4
    m.game_change(3, +1)
    assert m.player_roms()[2] == BLACK
