"""Type effectiveness of generations 2-5 (17 types, no Fairy; Steel still resists Ghost and Dark). Attacker -> {defender:
factor} in _TABLE, missing means 1."""
from __future__ import annotations

from .language import t

TYPES = ["Normal", "Fire", "Water", "Grass", "Electric", "Ice", "Fighting", "Poison", "Ground", "Flying", "Psychic",
         "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel"]



def _key(type_: str) -> str:
    """Language key suffix of a type name."""
    return type_.lower()


def display(type_: str) -> str:
    """Name of the type in the current language (internally the English names from TYPES are used)."""
    return t(f"type.{_key(type_)}")


def short(type_: str) -> str:
    """Three-letter abbreviation of the type in the current language."""
    return t(f"type_short.{_key(type_)}")


COLORS = {"Normal": (168, 167, 122), "Fire": (238, 129, 48), "Water": (99, 144, 240), "Grass": (122, 199, 76),
          "Electric": (247, 208, 44), "Ice": (150, 217, 214), "Fighting": (194, 46, 40), "Poison": (163, 62, 161),
          "Ground": (226, 191, 101), "Flying": (169, 143, 243), "Psychic": (249, 85, 135), "Bug": (166, 185, 26),
          "Rock": (182, 161, 54), "Ghost": (115, 87, 151), "Dragon": (111, 53, 252), "Dark": (112, 87, 70),
          "Steel": (183, 183, 206)}

_TABLE = {
    "Normal": {"Rock": 0.5, "Steel": 0.5, "Ghost": 0},
    "Fire": {"Fire": 0.5, "Water": 0.5, "Grass": 2, "Ice": 2, "Bug": 2, "Rock": 0.5, "Dragon": 0.5,
              "Steel": 2},
    "Water": {"Fire": 2, "Water": 0.5, "Grass": 0.5, "Ground": 2, "Rock": 2, "Dragon": 0.5},
    "Electric": {"Water": 2, "Electric": 0.5, "Grass": 0.5, "Ground": 0, "Flying": 2, "Dragon": 0.5},
    "Grass": {"Fire": 0.5, "Water": 2, "Grass": 0.5, "Poison": 0.5, "Ground": 2, "Flying": 0.5, "Bug": 0.5,
                "Rock": 2, "Dragon": 0.5, "Steel": 0.5},
    "Ice": {"Fire": 0.5, "Water": 0.5, "Grass": 2, "Ice": 0.5, "Ground": 2, "Flying": 2, "Dragon": 2, "Steel": 0.5},
    "Fighting": {"Normal": 2, "Ice": 2, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Rock": 2, "Ghost": 0,
              "Dark": 2, "Steel": 2},
    "Poison": {"Grass": 2, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Ghost": 0.5, "Steel": 0},
    "Ground": {"Fire": 2, "Electric": 2, "Grass": 0.5, "Poison": 2, "Flying": 0, "Bug": 0.5, "Rock": 2, "Steel": 2},
    "Flying": {"Electric": 0.5, "Grass": 2, "Fighting": 2, "Bug": 2, "Rock": 0.5, "Steel": 0.5},
    "Psychic": {"Fighting": 2, "Poison": 2, "Psychic": 0.5, "Dark": 0, "Steel": 0.5},
    "Bug": {"Fire": 0.5, "Grass": 2, "Fighting": 0.5, "Poison": 0.5, "Flying": 0.5, "Psychic": 2, "Ghost": 0.5,
              "Dark": 2, "Steel": 0.5},
    "Rock": {"Fire": 2, "Ice": 2, "Fighting": 0.5, "Ground": 0.5, "Flying": 2, "Bug": 2, "Steel": 0.5},
    "Ghost": {"Normal": 0, "Psychic": 2, "Ghost": 2, "Dark": 0.5, "Steel": 0.5},
    "Dragon": {"Dragon": 2, "Steel": 0.5},
    "Dark": {"Fighting": 0.5, "Psychic": 2, "Ghost": 2, "Dark": 0.5, "Steel": 0.5},
    "Steel": {"Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2, "Rock": 2, "Steel": 0.5},
}


def factor(attacker: str, defender: str) -> float:
    """Damage factor of an attacking type against a defending type."""
    return _TABLE[attacker].get(defender, 1)


def _group(values: dict[str, float]) -> dict[float, list[str]]:
    """Groups types by damage factor in TYPES order, leaving out neutral (1x) ones."""
    groups: dict[float, list[str]] = {}
    for type_ in TYPES:
        if values[type_] != 1:
            groups.setdefault(values[type_], []).append(type_)
    return groups


def defense(types_: list[str]) -> dict[float, list[str]]:
    """How strongly each attacking type hits a Pokemon with these one or two types."""
    different = list(dict.fromkeys(types_))
    values = {}
    for attacker in TYPES:
        value = 1.0
        for defender in different:
            value *= factor(attacker, defender)
        values[attacker] = value
    return _group(values)


def strong_against(types_: list[str]) -> list[str]:
    """Types that at least one of the given types hits super effectively (2x), in TYPES order."""
    return [v for v in TYPES if any(factor(a, v) == 2 for a in types_)]


def attack(type_: str) -> dict[float, list[str]]:
    """How strongly an attack of this type hits each defending type."""
    return _group({defender: factor(type_, defender) for defender in TYPES})
