"""Tests of reading catches and badges from saves and RAM."""
import hashlib
import os
import random
import struct
import tempfile
import time
from datetime import date
from pathlib import Path

import pytest

from conftest import plugin_module
from pokemon_helpers import (G3_OPPONENT, G3_PC, G3_TEAM, G4, flags_set, g3_pc_set, g3_sav, g3_slot,
                            g3_team_set, g4_write, g5_sav, empty_slot, pk3, pk45)
from soullink import pokemon_data, roms
from soullink.pokemon_data import Catch

reader = plugin_module("soullink", "catches")
read_catches, read_catches_ram, read_badge_ram = reader.read_catches, reader.read_catches_ram, reader.read_badge_ram

SESSIONS = Path(os.environ.get("SOULLINK_TEST_SESSIONS", Path(tempfile.gettempdir()) / "soullink-sessions"))
RAM_DUMPS = Path(os.environ.get("SOULLINK_TEST_RAM", Path(tempfile.gettempdir()) / "soullink-ram"))


def test_g3_firered_team_and_boxes():
    """Generation 3 FireRed team and boxes are read."""
    sav = g3_sav(team=[pk3(280, "Äffchen", location=101, catch_level=3, level=7), pk3(25, "PIKA", location=88, level=12)],
                 boxes={(0, 0): pk3(395, "SÄLAMÖ", location=122, pid=7),
                        (13, 29): pk3(175, "EI", location=0, catch_level=0, ei=True, pid=5),
                        (2, 4): pk3(1, "BISA", location=97, catch_level=0, pid=99)})
    assert read_catches(bytes(sav), "BPRD") == [
        Catch(255, "Äffchen", 101, False, False, True, None, 0, None, 7),
        Catch(25, "PIKA", 88, False, False, True, None, 1, None, 12),
        Catch(371, "SÄLAMÖ", 122, False, False, False, 0, 0),
        Catch(1, "BISA", 97, False, True, False, 2, 4),
        Catch(175, "EI", 0, True, False, False, 13, 29),
    ]
    assert read_catches(bytes(sav), "BPGD") == read_catches(bytes(sav), "BPRD")


def test_g3_ruby_sapphire_emerald_team_at_another_place():
    """Ruby, Sapphire and Emerald keep the team at another place."""
    sav = bytes(g3_sav(team=[pk3(315, "SKITTY", level=9)], team_size=0x234))
    for code in ("AXVD", "AXPD", "BPED"):
        assert [(f.kind, f.level) for f in read_catches(sav, code)] == [(300, 9)]
    assert read_catches(sav, "BPRD") == []


def test_g3_newer_slot_wins_broken_falls_back():
    """The newer valid slot wins and a broken one falls back."""
    sav = g3_slot(bytearray(b"\xff" * 0x20000), 7, team=[pk3(4, "OLD", level=5)])
    g3_slot(sav, 8, team=[pk3(7, "NEW", level=6)])
    assert [f.nickname for f in read_catches(bytes(sav), "BPRD")] == ["NEW"]
    sav[0x1000 + 5] ^= 1
    assert [f.nickname for f in read_catches(bytes(sav), "BPRD")] == ["OLD"]


def test_g3_invalid_slots_missing():
    """Invalid generation 3 slots are left out."""
    broken = bytearray(pk3(10, "CATERPIE"))
    broken[0x30] ^= 0xFF
    sav = g3_sav(boxes={(0, 0): bytes(broken), (0, 1): pk3(260, "SLOT"), (0, 2): pk3(10, "CATERPIE")})
    assert [(f.kind, f.slot) for f in read_catches(bytes(sav), "BPRD")] == [(10, 2)]


@pytest.mark.parametrize("code", ["ADAD", "APAD", "CPUD", "IPKD", "IPGD"])
def test_g4_team_and_boxes(code):
    """Generation 4 team and boxes are read."""
    sav = g4_write(bytearray(0x80000), code, 0,
                       team=[pk45(393, 4, "Piplup", location=16, location_dp=16, level=8),
                             pk45(175, 4, "Ei", ei=True, ei_location=2011, ei_location_dp=2011, day=(0, 0, 0), level=1)],
                       boxes={(0, 3): pk45(399, 4, "Bidoof", location=17, location_dp=17, day=(26, 10, 18), pid=77),
                              (17, 29): pk45(447, 4, "Riolü", location=31, location_dp=31, ei_location=2000, ei_location_dp=2000, pid=9)})
    assert read_catches(bytes(sav), code) == [
        Catch(393, "Piplup", 16, False, False, True, None, 0, date(2026, 10, 19), 8),
        Catch(175, "Ei", 0, True, False, True, None, 1, None, 1),
        Catch(399, "Bidoof", 17, False, False, False, 0, 3, date(2026, 10, 18)),
        Catch(447, "Riolü", 31, False, True, False, 17, 29, date(2026, 10, 19)),
    ]


def test_g4_extended_place_comes_before_the_dp_place():
    """The extended place is used before the Diamond/Pearl place."""
    sav = g4_write(bytearray(0x80000), "CPUD", 0, team=[pk45(442, 4, "Spiritomb", location=2500, location_dp=3002, level=25),
                                                            pk45(1, 4, "Bulbasaur", location=0, location_dp=12, level=5)])
    assert [f.location for f in read_catches(bytes(sav), "CPUD")] == [2500, 12]


def test_g4_newer_copy_per_block():
    """Per block the newer generation 4 copy wins."""
    sav = bytearray(0x80000)
    g4_write(sav, "CPUD", 0, team=[pk45(1, 4, "OLD", level=5)], boxes={(0, 0): pk45(2, 4, "NEW")},
                 counter=(4, 9))
    g4_write(sav, "CPUD", 1, team=[pk45(3, 4, "NEW", level=5)], boxes={(0, 0): pk45(4, 4, "OLD")},
                 counter=(4, 8))
    g4_write(sav, "CPUD", 1, team=[pk45(3, 4, "NEW", level=5)], counter=(5, 1))
    assert [f.kind for f in read_catches(bytes(sav), "CPUD")] == [3, 2]
    sav[0x40000 + 0x200] ^= 1
    assert [f.kind for f in read_catches(bytes(sav), "CPUD")] == [1, 2]


def test_g5_team_and_boxes():
    """Generation 5 team and boxes are read."""
    sav = g5_sav(team=[pk45(495, 5, "Snivy", location=117, level=5)],
                 boxes={(0, 0): pk45(224, 5, "Octillery", location=124, day=(26, 10, 19), pid=3),
                        (23, 29): pk45(587, 5, "Emolga♀", location=19, ei_location=60002, pid=0xFFFFFFFF)})
    assert read_catches(bytes(sav), "IRED") == [
        Catch(495, "Snivy", 117, False, False, True, None, 0, date(2026, 10, 19), 5),
        Catch(224, "Octillery", 124, False, False, False, 0, 0, date(2026, 10, 19)),
        Catch(587, "Emolga♀", 19, False, True, False, 23, 29, date(2026, 10, 19)),
    ]
    assert read_catches(bytes(sav), "IRDD") == read_catches(bytes(sav), "IRED")


def test_g5_black_white_backup_at_0x24000():
    """Black/White use the backup at 0x24000."""
    sav = g5_sav(team=[pk45(501, 5, "Oshawott", location=4, level=5)], copy=0x24000)
    assert [f.kind for f in read_catches(bytes(sav), "IRBD")] == [501]
    sav[0x18E00 + 20] ^= 1
    assert [f.kind for f in read_catches(bytes(sav), "IRAD")] == [501]
    sav[0x24000 + 0x18E00 + 20] ^= 1
    assert read_catches(bytes(sav), "IRBD") == []


@pytest.mark.parametrize("code", ["BPRD", "BPED", "ADAD", "CPUD", "IPKD", "IRBD", "IRED"])
def test_broken_saves_yield_empty_list(code):
    """Broken saves yield an empty list."""
    rng = random.Random(code)
    for sav in (b"", b"\x00" * 100, b"\xff" * 0x80000, bytes(0x80000), rng.randbytes(0x80000)):
        assert read_catches(sav, code) == []


def test_unknown_game():
    """An unknown game yields an empty list."""
    assert read_catches(bytes(g3_sav(team=[pk3(1, "A", level=5)])), "AXXD") == []
    assert read_catches(b"", "") == []


G3_EXPECTED = [Catch(83, "FARFETCHD", 101, False, False, True, None, 0, None, 4),
               Catch(10, "CATERPIE", 102, False, False, True, None, 1, None, 2),
               Catch(371, "BAGON", 88, False, False, False, 0, 0),
               Catch(25, "PIKA", 89, False, False, False, 1, 5)]


def test_g3_ram_firered_without_opponent_and_battle_copy():
    """FireRed RAM ignores opponents and battle copies."""
    ewram = bytearray(0x40000)
    g3_team_set(ewram, 0x151BC, G3_TEAM)
    g3_team_set(ewram, 0x2402C, G3_OPPONENT)
    g3_team_set(ewram, 0x24284, G3_TEAM, 0x24029)
    g3_pc_set(ewram, 0x29384, G3_PC)
    assert read_catches_ram({0x02000000: bytes(ewram), 0x03000000: bytes(0x8000)}, "BPRD") == G3_EXPECTED


def test_g3_ram_emerald_opponent_behind_the_team():
    """Emerald RAM has the opponent behind the team."""
    ewram = bytearray(0x40000)
    g3_team_set(ewram, 0x244EC, G3_TEAM, 0x244E9)
    g3_team_set(ewram, 0x24744, G3_OPPONENT)
    g3_pc_set(ewram, 0x2B000, G3_PC)
    assert read_catches_ram({0x02000000: bytes(ewram), 0x03000000: bytes(0x8000)}, "BPED") == G3_EXPECTED


def test_g3_ram_ruby_team_in_iwram():
    """Ruby RAM has the team in IWRAM."""
    ewram, iwram = bytearray(0x40000), bytearray(0x8000)
    g3_team_set(iwram, 0x4370, G3_TEAM, 0x4360)
    g3_team_set(iwram, 0x45D0, G3_OPPONENT)
    g3_pc_set(ewram, 0x300A0, G3_PC)
    assert read_catches_ram({0x02000000: bytes(ewram), 0x03000000: bytes(iwram)}, "AXVD") == G3_EXPECTED


@pytest.mark.parametrize("code", ["ADAD", "CPUD", "IPGD"])
def test_g4_ram_save_buffer_instead_of_battle_copy(code):
    """Generation 4 RAM uses the save buffer instead of the battle copy."""
    team = [pk45(38, 4, "Ninetales", location=16, location_dp=16, level=7), pk45(246, 4, "Larvitar", location=16, pid=5, level=3)]
    buffer = g4_write(bytearray(0x40000), code, 0, team=team, boxes={(17, 29): pk45(92, 4, "Gastly", location=178)})
    ram = bytearray(0x80000)
    team_place = G4[code][4]
    ram[0x1000:0x1000 + 8 + 2 * 236] = buffer[team_place - 8:team_place + 2 * 236]
    ram[0x30000:0x70000] = buffer
    assert [(f.kind, f.team, f.box, f.slot, f.level) for f in read_catches_ram({0x02000000: bytes(ram)}, code)] == \
           [(38, True, None, 0, 7), (246, True, None, 1, 3), (92, False, 17, 29, None)]


def test_g5_ram_save_buffer_instead_of_battle_copy():
    """Generation 5 RAM uses the save buffer instead of the battle copy."""
    ram = bytearray(0x80000)
    team = struct.pack("<II", 6, 1) + pk45(541, 5, "Leavanny", location=117, level=6)
    ram[0x20000:0x20000 + len(team)] = team
    base = 0x40000
    ram[base + 0x18E00:base + 0x18E00 + len(team)] = team
    boxes = {(0, 0): pk45(224, 5, "Octillery", location=124, pid=3)}
    for box in range(24):
        for slot in range(30):
            start = base + 0x400 + box * 0x1000 + slot * 136
            ram[start:start + 136] = boxes.get((box, slot), empty_slot())
    assert read_catches_ram({0x02000000: bytes(ram)}, "IRED") == [
        Catch(541, "Leavanny", 117, False, False, True, None, 0, date(2026, 10, 19), 6),
        Catch(224, "Octillery", 124, False, False, False, 0, 0, date(2026, 10, 19)),
    ]


def test_ram_without_hit():
    """RAM without a hit yields no catches."""
    rng = random.Random(1)
    for code in ("BPRD", "BPED", "AXVD", "IRED", "IRBD"):
        assert read_catches_ram({}, code) == []
        assert read_catches_ram({0x02000000: rng.randbytes(0x40000), 0x03000000: bytes(0x8000)}, code) == []
    assert read_catches_ram({0x02000000: bytes(0x400000)}, "CPUD") == []


def _roms(suffix):
    """Test ROMs of the local test sessions."""
    return sorted(SESSIONS.glob(f"*/p*/rom.{suffix}")) if SESSIONS.is_dir() else []


def _saves():
    """Test saves of the local test sessions."""
    finds = []
    for system in ("gba", "nds"):
        for rom in _roms(system):
            sav = rom.with_name("game.sav")
            if sav.exists():
                with open(rom, "rb") as f:
                    code = roms.read_code(f.read(roms.HEADER_LENGTH), system)
                finds.append(pytest.param(sav, code, id=f"{rom.parent.parent.name}-{rom.parent.name}"))
    return finds or [pytest.param(None, None, marks=pytest.mark.skip(reason="no real save games"))]


def _gen(code):
    """Generation of a game code."""
    return 3 if code[:3] in reader.G3_TEAM_SIZE else 4 if code[:3] in pokemon_data.G4_GAMES else 5


def _plausible(catches, code):
    """Checks that the catches of a real save look plausible."""
    gen = _gen(code)
    team = [f for f in catches if f.team]
    assert team or not catches
    assert catches[:len(team)] == team and [f.slot for f in team] == list(range(len(team)))
    assert len({(f.box, f.slot) for f in catches}) == len(catches)
    for f in catches:
        assert 1 <= f.kind <= {3: 386, 4: 493, 5: 649}[gen]
        assert f.nickname
        assert (1 <= f.level <= 100) if f.team else f.level is None and 0 <= f.box < 24
        assert f.day is None if gen == 3 else (f.ei or date(2000, 1, 1) <= f.day <= date.today())


@pytest.mark.parametrize("sav, code", _saves())
def test_real_saves(sav, code):
    """Real saves are read (needs test data)."""
    data = sav.read_bytes()
    if _gen(code) == 3:
        assert reader.g3_sections(data) is not None
    elif _gen(code) == 4:
        general_size, _, _, foot = pokemon_data.G4_GAMES[code[:3]][:4]
        assert reader.g4_block(data, 0, general_size, foot) is not None
    elif _gen(code) == 5:
        assert reader.g5_block(data, *pokemon_data.G5_TEAM, pokemon_data.G5_COPY[code[:3]]) is not None
    _plausible(read_catches(data, code), code)


def _ram_dumps():
    """RAM dumps <session>/pN-<address>.bin with the game code from the session's ROM."""
    finds = []
    for dump in sorted(RAM_DUMPS.glob("*/p*-02000000.bin")) if RAM_DUMPS.is_dir() else []:
        player = dump.name.split("-")[0]
        for system in ("gba", "nds"):
            rom = SESSIONS / dump.parent.name / player / f"rom.{system}"
            if rom.exists():
                with open(rom, "rb") as f:
                    code = roms.read_code(f.read(roms.HEADER_LENGTH), system)
                finds.append(pytest.param(dump, code, id=f"{dump.parent.name}-{player}"))
    return finds or [pytest.param(None, None, marks=pytest.mark.skip(reason="no RAM dumps"))]


KNOWN_DUMPS = {
    "c3d17bb71ceb5102": [(83, None, 0), (371, 0, 0), (184, 0, 1)],
    "4589c7ef6cae9476": [(370, None, 0), (59, 0, 0), (163, 0, 1)],
    "eac82d88a83e6afa": [(327, None, 0), (359, 0, 0), (345, 0, 1)],
    "befcdc6c210af149": [(541, None, 0), (224, 0, 0)],
    "6ea554602e400a85": [(67, None, 0)],
    "21587d1f76d24ac3": [(38, None, 0), (246, None, 1)],
    "8f2d5e53e9716236": [(330, None, 0), (92, None, 1)],
}


@pytest.mark.parametrize("dump, code", _ram_dumps())
def test_real_ram_dumps(dump, code):
    """Real RAM dumps are read (needs test data)."""
    player = dump.name.split("-")[0]
    blocks = {int(d.stem.split("-")[1], 16): d.read_bytes() for d in dump.parent.glob(f"{player}-*.bin")}
    start = time.perf_counter()
    catches = read_catches_ram(blocks, code)
    assert time.perf_counter() - start < 0.5
    assert catches
    _plausible(catches, code)
    expected = KNOWN_DUMPS.get(hashlib.sha256(blocks[0x02000000]).hexdigest()[:16])
    if expected is not None:
        assert [(f.kind, f.box, f.slot) for f in catches] == expected


def test_g3_badge_firered_through_the_block_pointer():
    """FireRed badges are read through the block pointer."""
    ewram, iwram = bytearray(0x40000), bytearray(0x8000)
    g3_team_set(ewram, 0x24284, G3_TEAM, 0x24029)
    g3_pc_set(ewram, 0x29384, G3_PC)
    struct.pack_into("<III", iwram, 0x5008, 0x02025590, 0x020245EC, 0x02029384)
    blocks = {0x02000000: ewram, 0x03000000: iwram}
    assert read_badge_ram(blocks, "BPRD") is None
    flags_set(ewram, 0x25590 + 0xEE0, [0x828, 0x820, 0x821, 0x822])
    assert read_badge_ram(blocks, "BPRD") == 3


def test_g3_badge_ruby_fixed_block():
    """Ruby badges are read from the fixed block."""
    ewram = bytearray(0x40000)
    flags_set(ewram, 0x25734 + 0x1220, [0x800] + list(range(0x807, 0x80F)))
    assert read_badge_ram({0x02000000: ewram, 0x03000000: bytes(0x8000)}, "AXVD") == 8


@pytest.mark.parametrize("code, place, expected", [("CPUD", {0x82: 0b111}, 3),
                                                     ("IPGD", {0x7E: 0xFF, 0x83: 0b11}, 10)])
def test_g4_badge_from_trainer_data(code, place, expected):
    """Generation 4 badges come from the trainer data."""
    team = [pk45(38, 4, "Ninetales", location=16, level=7)]
    buffer = g4_write(bytearray(0x40000), code, 0, team=team, boxes={})
    for place, value in place.items():
        buffer[place] = value
    ram = bytearray(0x80000)
    ram[0x30000:0x70000] = buffer
    assert read_badge_ram({0x02000000: bytes(ram)}, code) == expected
    assert read_badge_ram({0x02000000: bytes(0x80000)}, code) is None


def test_g5_badge_from_misc_block():
    """Generation 5 badges come from the misc block."""
    ram = bytearray(0x80000)
    base = 0x40000
    team = struct.pack("<II", 6, 1) + pk45(541, 5, "Leavanny", location=117, level=6)
    ram[base + 0x18E00:base + 0x18E00 + len(team)] = team
    for box in range(24):
        for slot in range(30):
            start = base + 0x400 + box * 0x1000 + slot * 136
            ram[start:start + 136] = empty_slot()
    ram[base + 0x21104] = 0b1011
    assert read_badge_ram({0x02000000: bytes(ram)}, "IRED") == 3
