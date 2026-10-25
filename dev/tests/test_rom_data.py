"""Tests of the per-player ROM data loading."""
import threading
import time

from soullink.dex import Dex
from soullink.rom_data import RomData


def _dex(locations):
    """A small dex with the given locations."""
    return Dex("BPRD", 3, [], {}, {}, locations)


def _wait(condition, seconds=5.0):
    """Polls until the condition holds or the time is over."""
    end = time.monotonic() + seconds
    while not condition() and time.monotonic() < end:
        time.sleep(0.005)
    return condition()


def test_loads_at_the_first_dex_call_and_only_once():
    """The dex loads at the first request and only once."""
    loaded = []
    rom = RomData([1, 2], lambda nr: loaded.append(nr) or _dex({nr: f"Ort von {nr}"}))
    rom.location_name(None, 5), rom.location_key(None, 5), rom.dex_error(1)
    time.sleep(0.05)
    assert loaded == [] and rom.requested == []
    assert rom.dex(2) is None
    assert _wait(lambda: rom.version == 1)
    assert loaded == [2] and rom.requested == [2] and rom.dex(2).locations == {2: "Ort von 2"}
    assert rom.dex(1) is None and _wait(lambda: rom.version == 2)
    rom.dex(1), rom.dex(2)
    time.sleep(0.05)
    assert loaded == [2, 1] and rom.version == 2
    assert rom.dex(7) is None and rom.requested == [2, 1]


def test_without_loader_nothing_loads():
    """Without a loader nothing is ever loaded."""
    rom = RomData([1])
    assert rom.dex(1) is None and rom.dex_error(1) is None and rom.requested == []
    assert rom.location_name(1, 5) == "Location #5" and rom.location_key(1, 5) == 5


def test_in_sequence_never_simultaneous():
    """Players load one after the other, never simultaneously."""
    simultaneous, now, lock = [], [0], threading.Lock()

    def load(nr):
        """Loader that fails if two run at the same time."""
        with lock:
            now[0] += 1
            simultaneous.append(now[0])
        time.sleep(0.02)
        with lock:
            now[0] -= 1
        return _dex({})

    rom = RomData([1, 2, 3], load)
    for nr in (3, 1, 2):
        rom.dex(nr)
    assert _wait(lambda: all(rom.dex(nr) is not None for nr in (1, 2, 3)))
    assert max(simultaneous) == 1 and rom.requested == [3, 1, 2]


def test_error_per_player():
    """An error is stored per player."""
    def load(nr):
        """Loader that fails for player 1."""
        if nr == 1:
            raise FileNotFoundError("java missing")
        if nr == 2:
            raise RuntimeError()
        return _dex({})

    rom = RomData([1, 2, 3], load)
    for nr in (1, 2, 3):
        rom.dex(nr)
    assert _wait(lambda: rom.version == 3)
    assert (rom.dex_error(1), rom.dex_error(2), rom.dex_error(3)) == ("java missing", "RuntimeError", None)
    assert rom.dex(1) is None and rom.dex(3) is not None


def test_location_name_and_same_locations_from_the_matching_rom():
    """Location names and same-named locations come from the matching ROM."""
    rom = RomData([1, 2])
    rom._dex = {2: _dex({99: "Route 4", 101: "Route 1", 103: "Route 4"})}
    assert rom.location_name(1, 103) == "Route 4"
    assert rom.location_name(None, 7) == "Location #7"
    assert [rom.location_key(1, o) for o in (99, 101, 103, 7)] == [99, 101, 99, 7]
    rom._dex[1] = _dex({103: "Route 4b", 5: "Pallet Town"})
    assert rom.location_name(1, 103) == "Route 4b" and rom.location_name(2, 103) == "Route 4" and rom.location_name(1, 99) == "Route 4"
    assert rom.location_key(1, 103) == 103 and rom.location_key(2, 103) == 99
