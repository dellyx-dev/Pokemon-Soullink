"""Tests of the ROM discovery."""

import zipfile

from conftest import fake_gba
from soullink import roms


def _zip(path, entry, data):
    """Creates a ZIP file with one entry."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(entry, data)


def test_name_fits():
    """File names are recognized as Pokemon ROMs."""
    assert roms.name_fits("Pokémon Emerald Version.zip")
    assert roms.name_fits("POKEMON x.gba")
    assert not roms.name_fits("Texas Hold 'em Poker.zip")


def test_read_code():
    """The game code is read from the header."""
    assert roms.read_code(fake_gba("BPED")) == "BPED"
    assert roms.read_code(b"\x00" * 10) is None


def test_find_base_roms(tmp_path):
    """Base ROMs are found in the folder."""
    _zip(tmp_path / "Pokémon Emerald Version.zip", "Pokemon - Emerald.gba", fake_gba("BPED"))
    (tmp_path / "Pokemon FireRed.gba").write_bytes(fake_gba("BPRD"))
    _zip(tmp_path / "Pokemon Pinball - Ruby & Sapphire.zip", "pinball.gba", fake_gba("BPPE"))
    _zip(tmp_path / "Poker.zip", "poker.gba", fake_gba("BPED"))
    _zip(tmp_path / "Pokemon empty.zip", "readme.txt", b"x")
    found = roms.find_base_roms(tmp_path)
    assert [r.game for r in found] == ["Emerald", "FireRed"]
    assert found[0].entry == "Pokemon - Emerald.gba"
    assert found[1].entry is None


def test_unpack(tmp_path):
    """ROMs are unpacked from ZIP files."""
    data = fake_gba("BPED") + b"rest"
    _zip(tmp_path / "Pokemon Emerald.zip", "e.gba", data)
    (tmp_path / "Pokemon Ruby.gba").write_bytes(fake_gba("AXVD"))
    ruby, emerald = sorted(roms.find_base_roms(tmp_path), key=lambda r: r.game, reverse=True)
    assert roms.unpack(emerald, tmp_path / "out" / "a.gba").read_bytes() == data
    assert roms.unpack(ruby, tmp_path / "out" / "b.gba").read_bytes() == fake_gba("AXVD")


def test_game_name_from_file(tmp_path):
    """The game name is read from a ROM file."""
    file = tmp_path / "rom.gba"
    file.write_bytes(fake_gba("AXVD"))
    assert roms.game_name_from_file(file) == "Ruby"
    assert roms.game_name_from_file(tmp_path / "missing.gba") is None


def test_nds_detection(tmp_path):
    """NDS ROMs are detected."""
    from conftest import fake_nds

    _zip(tmp_path / "Pokémon Platinum Version.zip", "Pokemon - Platinum.nds", fake_nds("CPUD"))
    (tmp_path / "Pokemon Black Version 2.nds").write_bytes(fake_nds("IRED"))
    (tmp_path / "Pokemon Emerald.gba").write_bytes(fake_gba("BPED"))
    _zip(tmp_path / "Pokemon Mystery Dungeon.zip", "pmd.nds", fake_nds("YFTD"))
    found = roms.find_base_roms(tmp_path)
    assert [(r.system, r.game) for r in found] == [("gba", "Emerald"), ("nds", "Black 2"), ("nds", "Platinum")]
    platinum = found[2]
    assert platinum.suffix == ".nds" and platinum.entry == "Pokemon - Platinum.nds"
    assert roms.unpack(platinum, tmp_path / "x" / "base.nds").read_bytes() == fake_nds("CPUD")


def test_nds_game_name_from_file(tmp_path):
    """The game name of an NDS ROM is read."""
    from conftest import fake_nds

    (tmp_path / "rom.nds").write_bytes(fake_nds("IPKD"))
    assert roms.game_name_from_file(tmp_path / "rom.nds") == "HeartGold"
    assert roms.read_code(fake_nds("IRAD"), "nds") == "IRAD"
