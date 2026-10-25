"""Level cap: gym leaders, Elite Four and champion of the own ROM with the highest level of their team. The trainers come
from dex.json (randomizer tags)."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Battle:
    """One cap-relevant battle: kind ("arena", "top4", "champ"), number (gym 1-16 or Elite Four place 1-4, champion 1),
    round_ (1 first fight, 2 rematch, only Elite Four and champion), name and highest team level."""
    kind: str
    number: int
    round_: int
    name: str
    level: int


def _hgss(rom_code: str) -> bool:
    """True for HeartGold and SoulSilver, which have 16 badges (Johto and Kanto)."""
    return rom_code[:3] in ("IPK", "IPG")


def _frlg(rom_code: str) -> bool:
    """True for FireRed and LeafGreen, where the champion is the rival."""
    return rom_code[:3] in ("BPR", "BPG")


def battles(dex) -> list[Battle]:
    """In game order: gyms 1-8, Elite Four and champion, (HGSS: gyms 9-16,) then, if present, Elite Four and champion again
    as rematch."""
    groups: dict[tuple[str, int], list] = {}
    for tr in dex.trainer:
        if m := re.fullmatch(r"GYM(\d+)-LEADER", tr.tag):
            key = ("arena", int(m.group(1)))
        elif m := re.fullmatch(r"ELITE(\d+)(?:-\d+)?", tr.tag):
            key = ("top4", int(m.group(1)))
        elif tr.tag == "CHAMPION":
            key = ("champ", 1)
        elif _frlg(dex.rom_code) and (m := re.fullmatch(r"RIVAL([89])(?:-\d+)?", tr.tag)):
            key = ("rival", int(m.group(1)))
        else:
            continue
        groups.setdefault(key, []).append(tr)
    max_arena = 16 if _hgss(dex.rom_code) else 8
    gyms, first, second = [], [], []
    for (kind, number), trainer in sorted(groups.items(), key=lambda e: (("arena", "top4", "champ", "rival").index(e[0][0]),
                                                                          e[0][1])):
        weak = min(trainer, key=lambda tr: (tr.max_level, tr.index))
        strong = max(trainer, key=lambda tr: (tr.max_level, -tr.index))
        if kind == "arena":
            if number <= max_arena:
                gyms.append(Battle("arena", number, 1, weak.name, weak.max_level))
        elif kind == "rival":
            target = first if number == 8 else second
            target.append(Battle("champ", 1, 1 if number == 8 else 2, strong.name, strong.max_level))
        else:
            first.append(Battle(kind, number, 1, weak.name, weak.max_level))
            if strong.max_level > weak.max_level:
                second.append(Battle(kind, number, 2, strong.name, strong.max_level))
    return [k for k in gyms if k.number <= 8] + first + [k for k in gyms if k.number > 8] + second
