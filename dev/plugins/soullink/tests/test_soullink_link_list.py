"""Tests of the Soullink list."""
from dataclasses import dataclass
from datetime import date

from conftest import plugin_module

link_list = plugin_module("soullink", "link_list")
LinkData, link = link_list.LinkData, link_list.link


@dataclass
class F:
    """Minimal catch for the tests."""
    kind: int
    location: int
    team: bool = False
    box: int | None = 0
    slot: int = 0
    day: date | None = None
    ei: bool = False
    hatched: bool = False
    nickname: str = ""
    level: int | None = None


def test_first_catch_per_location_and_player():
    """Per location and player the first catch counts."""
    catches = {
        1: [F(16, 5, box=0, slot=3), F(19, 5, team=True, slot=1), F(10, 7, box=1)],
        2: [F(41, 5, box=0, slot=0), F(25, 9, ei=True), F(50, 9, hatched=True)],
    }
    rows = link(catches, [1, 2], {7}, lambda o: f"Route {o}")
    assert [(z.location, z.name, z.dead) for z in rows] == [(5, "Route 5", False), (7, "Route 7", True)]
    assert rows[0].catches[1].kind == 19
    assert rows[0].catches[2].kind == 41
    assert 2 not in rows[1].catches


def test_day_decides_before_team():
    """The catch date decides before team membership."""
    catches = {1: [F(1, 3, team=True, day=date(2026, 10, 2)), F(4, 3, box=2, day=date(2026, 10, 1))]}
    assert link(catches, [1], set(), str)[0].catches[1].kind == 4


def test_dead_status_is_saved(tmp_path):
    """The dead status is saved."""
    sav = tmp_path / "p1.sav"
    sav.write_bytes(b"x")
    data = LinkData(tmp_path, [1], {1: "BPRD"}, lambda nr: sav, lambda b, code: [F(16, 5)])
    data.all_new()
    assert data.rows()[0].name == "Location #5" and not data.rows()[0].dead
    data.toggle(5)
    assert LinkData(tmp_path, [1], {}, lambda nr: sav, lambda b, c: []).dead == {5}
    data.toggle(5)
    assert data.dead == set()


def test_broken_save_and_dex_error(tmp_path):
    """A broken save or a dex error is tolerated."""
    import time

    from soullink.rom_data import RomData

    def broken(b, code):
        """Reader that always fails."""
        raise ValueError("broken")

    def dex_missing(nr):
        """Dex loader that fails because Java is missing."""
        raise FileNotFoundError("java missing")

    data = LinkData(tmp_path, [1, 2], {}, lambda nr: tmp_path / "missing.sav", broken, RomData([1, 2], dex_missing))
    data.all_new()
    assert data.rows() == []
    data.dex_load_start()
    end = time.monotonic() + 5
    while data.rom.version < 2 and time.monotonic() < end:
        time.sleep(0.01)
    assert [data.dex_error(nr) for nr in (1, 2)] == ["java missing", "java missing"] and data.dex(1) is None


def test_same_named_locations_form_one_row():
    """Same-named locations form one row."""
    names = {99: "Route 4", 101: "Route 1", 103: "Route 4"}
    catches = {1: [F(16, 103)], 2: [F(41, 99)]}
    rows = link(catches, [1, 2], {103}, names.get, {99: 99, 101: 101, 103: 99}.get)
    assert [(z.location, z.name, z.dead, sorted(z.catches)) for z in rows] == [(99, "Route 4", True, [1, 2])]


def test_free_locations_per_player(tmp_path):
    """Free locations are listed per player."""
    from soullink.dex import Dex

    data = LinkData(tmp_path, [1, 2], {}, lambda nr: tmp_path / "x.sav", lambda b, c: [])
    data._catches = {1: [F(16, 101)]}
    assert data.free_locations(1) == [] and not data.location_names_there()
    data.rom._dex = {1: Dex("BPRE", 3, [], {}, {}, {88: "Pallet Town", 99: "Route 4", 101: "Route 1", 103: "Route 4",
                                                      104: ""})}
    assert data.free_locations(1) == [(88, "Pallet Town"), (99, "Route 4")]
    assert data.free_locations(2) == [(88, "Pallet Town"), (99, "Route 4"), (101, "Route 1")]
    data.encounter_set(103, 2, 41)
    assert data.free_locations(2) == [(88, "Pallet Town"), (101, "Route 1")]
    assert data.free_locations(1) == [(88, "Pallet Town"), (99, "Route 4")]


def test_dead_row_without_entry_from_older_session(tmp_path):
    """A dead row without an entry from an older session is handled."""
    from soullink.dex import Dex

    data = LinkData(tmp_path, [1, 2], {}, lambda nr: tmp_path / "x.sav", lambda b, c: [])
    data._catches = {1: [F(16, 101)]}
    data.rom._dex = {1: Dex("BPRE", 3, [], {}, {}, {99: "Route 4", 101: "Route 1", 103: "Route 4"})}
    data.toggle(99)
    empty = next(z for z in data.rows() if z.location == 99)
    assert empty.dead and empty.catches == {} and empty.name == "Route 4"
    data.dead.add(103)
    data.toggle(99)
    assert data.dead == set() and [z.location for z in data.rows()] == [101]


def test_catch_locations_a_to_z_with_numbers():
    """Locations sort A-Z with natural number order."""
    names = {1: "Route 10", 2: "Route 2", 3: "Ödwald", 4: "Pallet Town", 5: "route 1", 6: "Cinnabar Island"}
    catches = {1: [F(10 + o, o) for o in names]}
    rows = link(catches, [1], set(), names.get)
    assert [z.name for z in rows] == ["Cinnabar Island", "Ödwald", "Pallet Town", "route 1", "Route 2", "Route 10"]


def test_entering_a_miss_makes_the_location_dead_and_is_saved(tmp_path):
    """Entering a miss kills the location and is saved."""
    data = LinkData(tmp_path, [1, 2], {}, lambda nr: tmp_path / "x.sav", lambda b, c: [])
    data._catches = {1: [F(16, 5)]}
    data.encounter_set(5, 2, 41)
    row = data.rows()[0]
    assert row.dead and row.missed == {2: 41} and 1 in row.catches
    data.encounter_set(7, 1, 19)
    assert [z.location for z in data.rows()] == [5, 7]
    new = LinkData(tmp_path, [1, 2], {}, lambda nr: tmp_path / "x.sav", lambda b, c: [])
    assert new.encounters == {5: {2: 41}, 7: {1: 19}} and new.dead == {5, 7}
    data.encounter_set(7, 1, None)
    data.toggle(7)
    assert [z.location for z in data.rows()] == [5]
    data._catches[2] = [F(10, 5)]
    assert data.rows()[0].missed == {}
