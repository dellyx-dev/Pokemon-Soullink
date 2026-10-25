"""Tests of the dex loading and the Java helper call."""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from soullink import dex as D
from soullink import paths

DATA = {
    "format": 2, "rom_code": "BPRD", "generation": 3,
    "pokemon": [
        {"nr": 1, "name": "Bulbasaur", "types": ["GRASS", "POISON"], "values": [45, 49, 49, 65, 65, 45],
         "evolutions": [{"target": 2, "kind": "LEVEL", "value": 16}], "learnset": [[1, 33], [4, 45]]},
        {"nr": 2, "name": "Ivysaur", "types": ["GRASS", "POISON"], "values": [60, 62, 63, 80, 80, 60],
         "evolutions": [], "learnset": []},
        {"nr": 95, "name": "Onix", "types": ["ROCK", "GROUND"], "values": [35, 45, 160, 30, 45, 70],
         "evolutions": [{"target": 208, "kind": "TRADE_ITEM", "value": 199}], "learnset": [[1, 33]]},
    ],
    "moves": [
        {"nr": 33, "name": "Tackle", "type": "NORMAL", "strength": 35, "accuracy": 95, "ap": 35,
         "category": "PHYSICAL"},
        {"nr": 174, "name": "Curse", "type": None, "strength": 0, "accuracy": 0, "ap": 10, "category": "STATUS"},
    ],
    "items": {"94": "Moon Stone", "199": "Metal Coat"},
    "locations": {"88": "Pallet Town", "101": "Route 1"},
    "trainer": [
        {"tag": "GYM2-LEADER", "index": 415, "name": "Misty", "max_level": 21, "team": [[95, 18], [1, 21]]},
        {"tag": "GYM1-LEADER", "index": 414, "name": "Rocko", "max_level": 14, "team": [[95, 14]]},
        {"tag": "GYM9-LEADER", "index": 500, "name": "Extra", "max_level": 70, "team": [[95, 70]]},
        {"tag": "ELITE1-2", "index": 735, "name": "Lorelei", "max_level": 66, "team": [[1, 66]]},
        {"tag": "ELITE1-1", "index": 410, "name": "Lorelei", "max_level": 54, "team": [[1, 54]]},
        {"tag": "RIVAL8-0", "index": 438, "name": "Blue", "max_level": 63, "team": [[2, 63]]},
        {"tag": "RIVAL9-1", "index": 739, "name": "Blue", "max_level": 75, "team": [[2, 75]]},
        {"tag": "RIVAL3-0", "index": 332, "name": "Blue", "max_level": 18, "team": [[2, 18]]},
    ],
}


@pytest.fixture
def dex(tmp_path) -> D.Dex:
    """Loads a small dex from a generated dex.json."""
    path = tmp_path / "dex.json"
    path.write_text(json.dumps(DATA, ensure_ascii=False), encoding="utf-8")
    return D.load(path)


def test_load(dex):
    """A dex.json file is loaded completely."""
    assert dex.rom_code == "BPRD" and dex.generation == 3
    bulbasaur = dex.pokemon_after_nr[1]
    assert bulbasaur.name == "Bulbasaur"
    assert bulbasaur.types == ["GRASS", "POISON"]
    assert bulbasaur.values == [45, 49, 49, 65, 65, 45]
    assert bulbasaur.evolutions == [D.Evolution(2, "LEVEL", 16)]
    assert bulbasaur.learnset == [(1, 33), (4, 45)]
    assert dex.moves[33].name == "Tackle" and dex.moves[174].type_ is None
    assert dex.items == {94: "Moon Stone", 199: "Metal Coat"}


def test_load_wrong_format(tmp_path):
    """A dex.json of the wrong format is rejected."""
    path = tmp_path / "dex.json"
    path.write_text(json.dumps({**DATA, "format": 99}), encoding="utf-8")
    with pytest.raises(ValueError):
        D.load(path)


def test_location(dex):
    """Location names are looked up with a placeholder fallback."""
    assert dex.location(88) == "Pallet Town"
    assert dex.location(101) == "Route 1"
    assert dex.location(7) == "Location #7"


def test_type_name():
    """ZX type names map to the program's type names."""
    assert D.type_name("GRASS") == "Grass"
    assert D.type_name("DARK") == "Dark"
    assert D.type_name("STEEL") == "Steel"
    assert D.type_name("FAIRY") == "???"
    assert D.type_name(None) == "???"


@pytest.mark.parametrize("kind, value, text", [
    ("LEVEL", 16, "Lv. 16"),
    ("STONE", 94, "Moon Stone"),
    ("STONE", 5, "Item #5"),
    ("TRADE", 0, "Trade"),
    ("TRADE_ITEM", 199, "Trade holding Metal Coat"),
    ("HAPPINESS", 0, "Friendship"),
    ("HAPPINESS_DAY", 0, "Friendship (day)"),
    ("HAPPINESS_NIGHT", 0, "Friendship (night)"),
    ("LEVEL_ATTACK_HIGHER", 20, "Lv. 20, Atk > Def"),
    ("LEVEL_LOW_PV", 7, "Lv. 7 (random)"),
    ("LEVEL_IS_EXTRA", 20, "Lv. 20, free party slot"),
    ("LEVEL_FEMALE_ONLY", 21, "Lv. 21 (female)"),
    ("STONE_MALE_ONLY", 94, "Moon Stone (male)"),
    ("LEVEL_ITEM_NIGHT", 199, "Level up holding Metal Coat (night)"),
    ("LEVEL_WITH_MOVE", 33, "Level up knowing Tackle"),
    ("LEVEL_WITH_OTHER", 95, "Level up with Onix in the party"),
    ("LEVEL_MOSS_ROCK", 0, "Level up at the Moss Rock"),
    ("LEVEL_HIGH_BEAUTY", 0, "High Beauty"),
    ("FAIRY_AFFECTION", 0, "Special evolution"),
])
def test_evolution_text(dex, kind, value, text):
    """Evolution conditions are described in text."""
    assert D.evolution_text(D.Evolution(2, kind, value), dex) == text


def test_each_kind_has_a_text(dex):
    """Every evolution kind has a text."""
    gen3_5 = ["LEVEL", "STONE", "TRADE", "TRADE_ITEM", "HAPPINESS", "HAPPINESS_DAY", "HAPPINESS_NIGHT",
              "LEVEL_ATTACK_HIGHER", "LEVEL_DEFENSE_HIGHER", "LEVEL_ATK_DEF_SAME", "LEVEL_LOW_PV", "LEVEL_HIGH_PV",
              "LEVEL_CREATE_EXTRA", "LEVEL_IS_EXTRA", "LEVEL_HIGH_BEAUTY", "STONE_MALE_ONLY", "STONE_FEMALE_ONLY",
              "LEVEL_ITEM_DAY", "LEVEL_ITEM_NIGHT", "LEVEL_WITH_MOVE", "LEVEL_WITH_OTHER", "LEVEL_MALE_ONLY",
              "LEVEL_FEMALE_ONLY", "LEVEL_ELECTRIFIED_AREA", "LEVEL_MOSS_ROCK", "LEVEL_ICY_ROCK", "TRADE_SPECIAL"]
    for kind in gen3_5:
        assert D.evolution_text(D.Evolution(2, kind, 30), dex) != "Special evolution", kind


def test_command():
    """The helper command line is built correctly."""
    jar = Path("r") / "soullink-dex.jar"
    cmd = D.command(Path("java"), jar, Path("rom.gba"), Path("p1") / "dex.json")
    assert cmd == ["java", "-cp", f"{Path('r') / 'PokeRandoZX.jar'}{os.pathsep}{jar}", "SoullinkDex", "rom.gba",
                   str(Path("p1") / "dex.json")]


def test_dex_jar_next_to_randomizer():
    """The dex helper jar lies next to the randomizer jar."""
    assert paths.dex_jar().parent == paths.randomizer_jar().parent
    assert paths.dex_jar().name == "soullink-dex.jar"


def _fake_tools(calls):
    """Fake subprocess.run that records its calls and writes a dex file."""
    def run(cmd, **kw):
        """Records the call and creates the dex file."""
        calls.append((cmd, kw))
        Path(cmd[-1]).write_text(json.dumps(DATA), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return run


def test_ensure_creates_and_remembers(tmp_path):
    """ensure() creates dex.json once and reuses it afterwards."""
    rom = tmp_path / "rom.gba"
    rom.write_bytes(b"rom")
    calls = []
    target = D.ensure(tmp_path, rom, Path("java"), Path("soullink-dex.jar"), run=_fake_tools(calls))
    assert target == tmp_path / "dex.json" and target.exists()
    assert len(calls) == 1
    assert calls[0][1]["creationflags"] == D._FLAGS
    D.ensure(tmp_path, rom, Path("java"), Path("soullink-dex.jar"), run=_fake_tools(calls))
    assert len(calls) == 1


def test_ensure_recreates_for_a_newer_rom(tmp_path):
    """ensure() recreates dex.json when the ROM is newer."""
    rom = tmp_path / "rom.gba"
    rom.write_bytes(b"rom")
    (tmp_path / "dex.json").write_text(json.dumps(DATA), encoding="utf-8")
    old = time.time() - 100
    os.utime(tmp_path / "dex.json", (old, old))
    calls = []
    D.ensure(tmp_path, rom, Path("java"), Path("soullink-dex.jar"), run=_fake_tools(calls))
    assert len(calls) == 1


def test_ensure_recreates_for_an_old_format(tmp_path):
    """ensure() recreates dex.json when its format is old."""
    rom = tmp_path / "rom.gba"
    rom.write_bytes(b"rom")
    (tmp_path / "dex.json").write_text(json.dumps({"format": 0}), encoding="utf-8")
    calls = []
    D.ensure(tmp_path, rom, Path("java"), Path("soullink-dex.jar"), run=_fake_tools(calls))
    assert len(calls) == 1


def test_ensure_error(tmp_path):
    """ensure() reports a failing helper as an error."""
    rom = tmp_path / "rom.gba"
    rom.write_bytes(b"rom")

    def broken(cmd, **kw):
        """Fake run that fails with a Java exception."""
        return subprocess.CompletedProcess(cmd, 1, "", "ERROR: java.lang.IllegalArgumentException: ROM not "
                                                       "supported\n\tat SoullinkDex.write\n")
    with pytest.raises(RuntimeError, match="ROM not supported"):
        D.ensure(tmp_path, rom, Path("java"), Path("soullink-dex.jar"), run=broken)
    with pytest.raises(RuntimeError, match="Java"):
        D.ensure(tmp_path, rom, None, Path("soullink-dex.jar"))


def test_ensure_not_startable(tmp_path):
    """ensure() reports a helper that cannot start."""
    rom = tmp_path / "rom.gba"
    rom.write_bytes(b"rom")

    def missing(cmd, **kw):
        """Fake run that raises because Java cannot be started."""
        raise FileNotFoundError(cmd[0])
    with pytest.raises(RuntimeError, match="Could not start"):
        D.ensure(tmp_path, rom, Path("java"), Path("soullink-dex.jar"), run=missing)



def _real_dex(rom: Path, dir: Path) -> D.Dex:
    """Loads the dex of a real ROM through Java."""
    java = paths.java_program()
    if java is None or not paths.dex_jar().exists():
        pytest.skip("Java or soullink-dex.jar missing")
    return D.load(D.ensure(dir, rom, java, paths.dex_jar()))


@pytest.fixture
def test_nds() -> Path:
    """The dex of a real NDS ROM is readable (needs a test ROM)."""
    path = os.environ.get("SOULLINK_TEST_NDS")
    if not path or not Path(path).exists():
        pytest.skip("SOULLINK_TEST_NDS not set")
    return Path(path)


def _basics(dex: D.Dex, count: int):
    """Checks basic properties of a loaded real dex."""
    assert len(dex.pokemon) == count
    bulbasaur = dex.pokemon_after_nr[1]
    assert bulbasaur.name == "Bisasam"
    assert bulbasaur.types == ["GRASS", "POISON"]
    assert bulbasaur.values == [45, 49, 49, 65, 65, 45]
    assert bulbasaur.learnset and all(dex.moves.get(nr) for _, nr in bulbasaur.learnset)
    assert bulbasaur.evolutions[0] == D.Evolution(2, "LEVEL", 16)
    assert D.evolution_text(bulbasaur.evolutions[0], dex) == "Lv. 16"
    assert dex.moves[1].name == "Pfund"
    assert dex.pokemon_after_nr[29].name == "Nidoran♀"
    evoli = dex.pokemon_after_nr[133]
    assert {D.evolution_text(e, dex) for e in evoli.evolutions} >= {"Feuerstein", "Wasserstein", "Donnerstein"}
    assert any(name.startswith("Route ") for name in dex.locations.values())


def test_emerald(test_rom, tmp_path):
    """The dex of a real Emerald ROM is readable (needs a test ROM)."""
    dex = _real_dex(test_rom, tmp_path)
    assert dex.generation == 3 and dex.rom_code == "BPED"
    _basics(dex, 386)
    assert dex.location(0) == "Wurzelheim"
    assert dex.location(16) == "Route 101"
    assert dex.location(73) == "Insel im Süden"
    assert dex.location(88) == "Alabastia"


def test_platinum(test_nds, tmp_path):
    """The dex of a real Platinum ROM is readable (needs a test ROM)."""
    dex = _real_dex(test_nds, tmp_path)
    assert dex.generation == 4 and dex.rom_code == "CPUD"
    _basics(dex, 493)
    assert dex.location(1) == "Zweiblattdorf"
    assert dex.location(16) == "Route 201"
    assert not list(tmp_path.glob("*.nds"))
