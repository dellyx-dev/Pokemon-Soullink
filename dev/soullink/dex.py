"""Pokedex of a player's own randomized ROM: the Java helper SoullinkDex reads it with ZX and writes pN/dex.json."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from soullink.randomizer import _FLAGS
from soullink.language import t
from soullink.types import TYPES

FORMAT = 2
FILE = "dex.json"
ZX_JAR = "PokeRandoZX.jar"

_TYPES = dict(zip(["NORMAL", "FIRE", "WATER", "GRASS", "ELECTRIC", "ICE", "FIGHTING", "POISON", "GROUND", "FLYING",
                   "PSYCHIC", "BUG", "ROCK", "GHOST", "DRAGON", "DARK", "STEEL"], TYPES))


@dataclass
class Evolution:
    """One evolution of a Pokemon: target, ZX evolution type and its value (level, item, move or Pokemon number)."""
    target: int
    kind: str
    value: int


@dataclass
class Pokemon:
    """Species with types, base stats, evolutions and learnset."""
    nr: int
    name: str
    types: list[str]
    values: list[int]
    evolutions: list[Evolution]
    learnset: list[tuple[int, int]]


@dataclass
class Move:
    """Move with type, power, accuracy, PP and damage category."""
    nr: int
    name: str
    type_: str | None
    strength: int
    accuracy: int
    ap: int
    category: str | None


@dataclass
class Trainer:
    """Gym leader, Elite Four member, champion or rival with level cap and team."""
    tag: str
    index: int
    name: str
    max_level: int
    team: list[tuple[int, int]]


@dataclass
class Dex:
    """All data read from one ROM: Pokemon, moves, items, locations and trainers."""
    rom_code: str
    generation: int
    pokemon: list[Pokemon]
    moves: dict[int, Move]
    items: dict[int, str]
    locations: dict[int, str]
    trainer: list[Trainer] = field(default_factory=list)
    pokemon_after_nr: dict[int, Pokemon] = field(init=False, repr=False)

    def __post_init__(self):
        """Indexes the Pokemon by number."""
        self.pokemon_after_nr = {p.nr: p for p in self.pokemon}

    def location(self, location_id: int) -> str:
        """Location name for an id, or a placeholder text if unknown."""
        return self.locations.get(location_id) or t("dex.location", id=location_id)

    def item(self, nr: int) -> str:
        """Item name for a number, or a placeholder text if unknown."""
        return self.items.get(nr) or t("dex.item", nr=nr)

    def move(self, nr: int) -> str:
        """Move name for a number, or a placeholder text if unknown."""
        move = self.moves.get(nr)
        return move.name if move else t("dex.move", nr=nr)

    def name(self, nr: int) -> str:
        """Pokemon name for a number, or "#<nr>" if unknown."""
        pokemon = self.pokemon_after_nr.get(nr)
        return pokemon.name if pokemon else f"#{nr}"


def load(path: Path) -> Dex:
    """Reads a dex.json file; raises ValueError for an unsupported format version."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(t("dex.format", format=data.get("format")))
    pokemon = [Pokemon(p["nr"], p["name"], list(p["types"]), list(p["values"]),
                       [Evolution(e["target"], e["kind"], e["value"]) for e in p["evolutions"]],
                       [(level, move) for level, move in p["learnset"]]) for p in data["pokemon"]]
    moves = {a["nr"]: Move(a["nr"], a["name"], a["type"], a["strength"], a["accuracy"], a["ap"],
                                 a["category"]) for a in data["moves"]}
    trainer = [Trainer(tr["tag"], tr["index"], tr["name"] or "?", tr["max_level"],
                       [(nr, level) for nr, level in tr["team"]]) for tr in data.get("trainer", [])]
    return Dex(data["rom_code"], data["generation"], pokemon, moves,
               {int(k): v for k, v in data["items"].items()}, {int(k): v for k, v in data["locations"].items()}, trainer)


def type_name(zx_type: str | None) -> str:
    """English type name used throughout the program for a ZX type; "???" for unknown types."""
    return _TYPES.get(zx_type or "", "???")


def evolution_text(dev: Evolution, dex: Dex) -> str:
    """Human readable evolution condition, e.g. "Lv. 16", "Fire Stone" or "Trade holding Metal Coat"."""
    kind, value = dev.kind, dev.value
    item, level = dex.item(value), t("evo.level", level=value)
    texts = {
        "LEVEL": "evo.level", "LEVEL_CREATE_EXTRA": "evo.level", "LEVEL_IS_EXTRA": "evo.level_slot",
        "LEVEL_ATTACK_HIGHER": "evo.level_attack_higher", "LEVEL_DEFENSE_HIGHER": "evo.level_defense_higher",
        "LEVEL_ATK_DEF_SAME": "evo.level_equal", "LEVEL_LOW_PV": "evo.level_random", "LEVEL_HIGH_PV": "evo.level_random",
        "LEVEL_MALE_ONLY": "evo.level_male", "LEVEL_FEMALE_ONLY": "evo.level_female", "LEVEL_DAY": "evo.level_day",
        "LEVEL_NIGHT": "evo.level_night", "LEVEL_HIGH_BEAUTY": "evo.beauty", "STONE": "evo.stone",
        "STONE_ULTRA": "evo.stone", "STONE_MALE_ONLY": "evo.stone_male", "STONE_FEMALE_ONLY": "evo.stone_female",
        "TRADE": "evo.trade", "TRADE_ITEM": "evo.trade_item", "TRADE_SPECIAL": "evo.trade_partner",
        "HAPPINESS": "evo.friendship", "HAPPINESS_DAY": "evo.friendship_day",
        "HAPPINESS_NIGHT": "evo.friendship_night", "LEVEL_ITEM_DAY": "evo.item_day",
        "LEVEL_ITEM_NIGHT": "evo.item_night", "LEVEL_WITH_MOVE": "evo.move", "LEVEL_WITH_OTHER": "evo.partner",
        "LEVEL_ELECTRIFIED_AREA": "evo.electrified_area", "LEVEL_MOSS_ROCK": "evo.moss_rock", "LEVEL_ICY_ROCK": "evo.icy_rock",
    }
    if kind in texts:
        return t(texts[kind], level=value, item=item, move=dex.move(value), pokemon=dex.name(value))
    return level if kind.startswith("LEVEL") and value else t("evo.special")


def _current(target: Path, rom: Path) -> bool:
    """True if the dex file is newer than the ROM and has the current format."""
    try:
        if target.stat().st_mtime < rom.stat().st_mtime:
            return False
        return json.loads(target.read_text(encoding="utf-8")).get("format") == FORMAT
    except (OSError, ValueError):
        return False


def command(java: Path, jar: Path, rom: Path, target: Path) -> list[str]:
    """Command line that runs the SoullinkDex helper on a ROM."""
    classpath = f"{Path(jar).with_name(ZX_JAR)}{os.pathsep}{jar}"
    return [str(java), "-cp", classpath, "SoullinkDex", str(rom), str(target)]


def ensure(player_dir: Path, rom: Path, java: Path | None, jar: Path, run=subprocess.run) -> Path:
    """Creates pN/dex.json if it is missing or older than the ROM (blocking); raises RuntimeError if the helper fails."""
    target = Path(player_dir) / FILE
    if _current(target, Path(rom)):
        return target
    if java is None:
        raise RuntimeError(t("dex.java_missing"))
    try:
        run = run(command(java, jar, rom, target), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, creationflags=_FLAGS)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(t("dex.not_startable", java=java, error=error)) from error
    if run.returncode != 0 or not target.exists():
        rows = [z.strip() for z in ((run.stderr or "") + "\n" + (run.stdout or "")).splitlines() if z.strip()]
        error = [z[len("ERROR:"):].strip() for z in rows if z.startswith("ERROR:")]
        raise RuntimeError(error[0] if error else rows[0] if rows else t("dex.failed"))
    return target
