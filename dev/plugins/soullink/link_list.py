"""Soullink list: the catches of all players linked per catch location, plus the shared dead state per location. The
catches come from the saves, and the dead state is stored in soullink.json of the session."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from soullink.atomic import atomic_write
from soullink.rom_data import RomData

FILE = "soullink.json"


@dataclass
class Row:
    """One location of the list: id, name, the catches per player number (missing means nothing caught there), the dead
    flag and the missed encounters per player number."""
    location: int
    name: str
    catches: dict
    dead: bool
    missed: dict = field(default_factory=dict)


def _order(catch) -> tuple:
    """Sort key for the first catch: earliest date (gen 4/5), otherwise team before box, then box and slot order."""
    return (catch.day or date.max, 0 if catch.team else 1, catch.box if catch.box is not None else -1, catch.slot)


def link(catches: dict[int, list], player: list[int], dead: set[int], location_name, key=None,
                encounters: dict | None = None) -> list[Row]:
    """Per location the first catch of each player; `key` merges same-named locations (location to shared id) and
    `encounters` adds the entered misses."""
    key = key or (lambda location: location)
    dead = {key(location) for location in dead}
    missed: dict[int, dict] = {}
    for location, entries in (encounters or {}).items():
        missed.setdefault(key(location), {}).update({nr: kind for nr, kind in entries.items() if nr in player})
    locations: dict[int, dict] = {}
    for nr in player:
        for catch in sorted((f for f in catches.get(nr, []) if not f.ei and not f.hatched), key=_order):
            locations.setdefault(key(catch.location), {}).setdefault(nr, catch)
    for location in (dead | {o for o, e in missed.items() if e}) - locations.keys():
        locations[location] = {}
    rows = [Row(location, location_name(location), pair, location in dead,
                    {nr: kind for nr, kind in missed.get(location, {}).items() if nr not in pair})
              for location, pair in locations.items()]
    rows.sort(key=lambda z: (natural(z.name), z.location))
    return rows


def natural(text: str) -> list:
    """Sort key A-Z with numbers as numbers ("Route 2" before "Route 10") and umlauts like their base letter."""
    simple = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return [int(part) if i % 2 else part for i, part in enumerate(re.split(r"(\d+)", simple))]


class LinkData:
    """Shared data of all players in the game; Pokemon and location data come from `rom`: the GameApi (or in tests a
    rom_data.RomData) with dex(nr) and dex_error(nr)."""

    def __init__(self, dir: Path, player: list[int], codes: dict[int, str | None], sav_path, read_catches,
                 rom=None, read_catches_ram=None):
        """Loads the dead state and creates the data for the players."""
        self.dir = Path(dir)
        self.player = list(player)
        self.codes = codes
        self._sav_path = sav_path
        self._read_catches = read_catches
        self._read_catches_ram = read_catches_ram
        self._from_ram: set[int] = set()
        self.rom = rom if rom is not None else RomData(self.player)
        self._catches: dict[int, list] = {}
        self.dead, self.encounters = self._load()
        self.version = 0

    def dex_load_start(self) -> None:
        """Requests the ROM data of all players (loaded in the background, one after the other)."""
        for nr in self.player:
            self.rom.dex(nr)

    def dex(self, nr: int):
        """Dex of a player; None while it loads."""
        return self.rom.dex(nr)

    def dex_error(self, nr: int) -> str | None:
        """Why the ROM data of a player could not be loaded, else None."""
        return self.rom.dex_error(nr)

    def location_name(self, location: int) -> str:
        """Location name from the ROM of the first player or the first loaded one; ids are equal per generation."""
        return self.rom.location_name(self.player[0] if self.player else None, location)

    def location_key(self, location: int) -> int:
        """Same-named locations count as one (FireRed has "Route 4" twice): the smallest id with that name."""
        return self.rom.location_key(self.player[0] if self.player else None, location)

    def _first_dex(self):
        """The first loaded dex of any player; None if none is loaded."""
        return next((d for d in (self.rom.dex(nr) for nr in self.player) if d is not None), None)

    def location_names_there(self) -> bool:
        """True once location names are available."""
        return self._first_dex() is not None

    def free_locations(self, nr: int) -> list[tuple[int, str]]:
        """Locations where player `nr` has neither caught anything nor entered a missed Pokemon (exactly one Pokemon per
        player and location): every name once, in the ROM's order."""
        dex = self._first_dex()
        if dex is None:
            return []
        bound = {z.location for z in self.rows() if nr in z.catches or nr in z.missed}
        return [(o, name) for o, name in sorted(dex.locations.items())
                if name and self.location_key(o) == o and o not in bound]

    def catches_new(self, nr: int) -> None:
        """Re-reads the save of player `nr` (after saving in the game), only while no RAM state exists."""
        if nr in self._from_ram:
            return
        try:
            data = Path(self._sav_path(nr)).read_bytes()
            self._catches[nr] = self._read_catches(data, self.codes.get(nr) or "")
        except Exception:
            self._catches[nr] = []
        self.version += 1

    def catches_from_ram(self, nr: int, blocks: dict) -> None:
        """Live state from main memory; if empty (e.g. an unknown game) the save stays in use."""
        if self._read_catches_ram is None:
            return
        try:
            catches = self._read_catches_ram(blocks, self.codes.get(nr) or "")
        except Exception:  # noqa: BLE001
            catches = []
        if catches:
            self._catches[nr] = catches
            self._from_ram.add(nr)
            self.version += 1

    def all_new(self) -> None:
        """Re-reads the saves of all players."""
        for nr in self.player:
            self.catches_new(nr)

    def rows(self) -> list[Row]:
        """The list rows for display."""
        return link(self._catches, self.player, self.dead, self.location_name, self.location_key, self.encounters)

    def _load(self) -> tuple[set[int], dict[int, dict[int, int]]]:
        """Reads the dead locations and the entered misses from soullink.json."""
        try:
            data = json.loads((self.dir / FILE).read_text(encoding="utf-8"))
            dead = {int(o) for o in data.get("dead", [])}
        except (OSError, ValueError, TypeError, AttributeError):
            return set(), {}
        try:
            encounters = {int(o): {int(nr): int(kind) for nr, kind in e.items()}
                           for o, e in data.get("encounters", {}).items()}
        except (ValueError, TypeError, AttributeError):
            encounters = {}
        return dead, encounters

    def _save(self) -> None:
        """Writes soullink.json."""
        data = {"dead": sorted(self.dead),
                 "encounters": {str(o): {str(nr): kind for nr, kind in sorted(e.items())}
                                 for o, e in sorted(self.encounters.items()) if e}}
        atomic_write(self.dir / FILE, json.dumps(data, indent=2).encode("utf-8"))
        self.version += 1

    def _is_dead(self, location: int) -> bool:
        """True if the location (or one with the same name) is marked dead."""
        return any(self.location_key(o) == self.location_key(location) for o in self.dead)

    def toggle(self, location: int) -> None:
        """Toggles the dead state of a location for all locations with its name."""
        equal = {o for o in self.dead if self.location_key(o) == self.location_key(location)}
        self.dead = self.dead - equal if equal else self.dead | {location}
        self._save()

    def encounter_set(self, location: int, nr: int, kind: int | None) -> None:
        """Records that player `nr` did not catch Pokemon `kind` at the location (None removes the entry); an entry makes
        the location dead as the Soullink rule demands, and "alive" again goes through the dead toggle."""
        key = self.location_key(location)
        for o in [o for o in self.encounters if self.location_key(o) == key]:
            self.encounters[o].pop(nr, None)
            if not self.encounters[o]:
                del self.encounters[o]
        if kind is not None:
            self.encounters.setdefault(key, {})[nr] = kind
            if not self._is_dead(key):
                self.dead.add(key)
        self._save()
