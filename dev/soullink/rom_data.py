"""ROM data of the players during the game: loads the dex of each player in the background and resolves location names. The
Java helper starts only when somebody asks for a player's dex, one player after the other, so no more than one Java
process runs next to the emulators."""
from __future__ import annotations

import threading

from .language import t


class RomData:
    """Dex of each player (Pokemon, moves, items, locations, trainers) from their own randomized ROM. A player is loaded
    exactly once after the first request; the result comes from dex(nr) and a failure from dex_error(nr)."""

    def __init__(self, player: list[int], load_dex=None):
        """Creates the store for the given players; load_dex(nr) loads blocking in a background thread, None disables
        loading."""
        self.player = list(player)
        self._load_dex = load_dex
        self._dex: dict[int, object] = {}
        self._error: dict[int, str] = {}
        self._requested: list[int] = []
        self._wait: list[int] = []
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.version = 0
        self._equal: dict[int, tuple[object, dict[int, int]]] = {}

    @property
    def requested(self) -> list[int]:
        """Players whose data somebody has requested (empty means Java was never started)."""
        return list(self._requested)

    def request(self, nr: int) -> None:
        """Starts loading the dex of player nr, only the first time; unknown players and a missing loader do nothing."""
        if self._load_dex is None or nr not in self.player or nr in self._requested:
            return
        with self._lock:
            if nr in self._requested:
                return
            self._requested.append(nr)
            self._wait.append(nr)
            if self._thread is None:
                self._thread = threading.Thread(target=self._load, daemon=True, name="dex-load")
                self._thread.start()

    def _load(self) -> None:
        """Thread body: loads the requested players one after the other."""
        while True:
            with self._lock:
                if not self._wait:
                    self._thread = None
                    return
                nr = self._wait.pop(0)
            try:
                self._dex[nr] = self._load_dex(nr)
            except Exception as error:  
                self._error[nr] = str(error) or type(error).__name__
            self.version += 1

    def dex(self, nr: int):
        """The dex of the player, or None while it loads (the first call starts loading) or if it failed."""
        self.request(nr)
        return self._dex.get(nr)

    def dex_error(self, nr: int) -> str | None:
        """Why the data of the player could not be loaded, else None."""
        return self._error.get(nr)

    def _row(self, nr: int | None) -> list:
        """Loaded dex objects, the one of player nr first and the others in player order."""
        if nr is not None:
            self.request(nr)
        numbers = ([nr] if nr is not None else []) + [n for n in self.player if n != nr]
        return [self._dex[n] for n in numbers if n in self._dex]

    def location_name(self, nr: int | None, location: int) -> str:
        """Name of a location id from the ROM of player nr (or any loaded one); "Location #<id>" without data."""
        for dex in self._row(nr):
            if location in dex.locations:
                return dex.locations[location]
        return t("dex.location", id=location)

    def location_key(self, nr: int | None, location: int) -> int:
        """Smallest id sharing the location's name, so same-named locations count as one; the id itself without data."""
        row = self._row(nr)
        if not row:
            return location
        dex = row[0]
        remembered = self._equal.get(id(dex))
        if remembered is None or remembered[0] is not dex:
            first: dict[str, int] = {}
            equal = {o: first.setdefault(name, o) for o, name in sorted(dex.locations.items())}
            remembered = self._equal[id(dex)] = (dex, equal)
        return remembered[1].get(location, location)
