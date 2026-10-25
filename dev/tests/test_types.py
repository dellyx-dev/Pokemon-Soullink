"""Tests of the type table."""

import pytest

from soullink import types


def test_seventeen_types_without_fairy():
    """There are 17 types and no Fairy."""
    assert len(types.TYPES) == 17
    assert "Fee" not in types.TYPES
    assert set(types.COLORS) == set(types.TYPES)
    assert all(len(types.short(x)) == 3 and types.display(x) for x in types.TYPES)


@pytest.mark.parametrize("attacker, defender, factor", [
    ("Normal", "Ghost", 0), ("Ghost", "Normal", 0), ("Ground", "Flying", 0), ("Electric", "Ground", 0),
    ("Psychic", "Dark", 0), ("Fighting", "Ghost", 0), ("Poison", "Steel", 0),
    ("Fire", "Grass", 2), ("Water", "Fire", 2), ("Electric", "Water", 2), ("Ice", "Dragon", 2),
    ("Fighting", "Dark", 2), ("Bug", "Psychic", 2), ("Dragon", "Dragon", 2), ("Ground", "Steel", 2),
    ("Fire", "Water", 0.5), ("Grass", "Flying", 0.5), ("Steel", "Steel", 0.5),
    ("Ghost", "Steel", 0.5), ("Dark", "Steel", 0.5),
    ("Water", "Steel", 1), ("Normal", "Normal", 1),
])
def test_single_factors(attacker, defender, factor):
    """Single damage factors are correct."""
    assert types.factor(attacker, defender) == factor


def test_steel_has_eleven_resistances_and_an_immunity():
    """Steel has eleven resistances and an immunity."""
    against_steel = {a: types.factor(a, "Steel") for a in types.TYPES}
    assert sorted(a for a, f in against_steel.items() if f == 0.5) == sorted(
        ["Normal", "Grass", "Ice", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel"])
    assert [a for a, f in against_steel.items() if f == 0] == ["Poison"]
    assert sorted(a for a, f in against_steel.items() if f == 2) == ["Fighting", "Fire", "Ground"]


def test_defense_with_two_types():
    """Defense combines two types."""
    swampert = types.defense(["Water", "Ground"])
    assert swampert[4] == ["Grass"]
    assert swampert[0] == ["Electric"]
    skarmory = types.defense(["Steel", "Flying"])
    assert sorted(skarmory[2]) == ["Electric", "Fire"]
    assert sorted(skarmory[0]) == ["Ground", "Poison"]
    assert "Grass" in skarmory[0.25] and "Bug" in skarmory[0.25]
    assert 1 not in skarmory


def test_defense_single_and_doubled_type_are_equal():
    """A single type and the same type twice defend equally."""
    assert types.defense(["Fire"]) == types.defense(["Fire", "Fire"])


def test_attack():
    """Attack factors against all types are correct."""
    fire = types.attack("Fire")
    assert sorted(fire[2]) == ["Bug", "Grass", "Ice", "Steel"]
    assert sorted(fire[0.5]) == ["Dragon", "Fire", "Rock", "Water"]
    assert 0 not in fire
    assert types.attack("Normal")[0] == ["Ghost"]
