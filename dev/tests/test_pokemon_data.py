"""Tests of the Pokemon record decoding."""

import os
import struct
import tempfile
import zipfile
from pathlib import Path

import pytest

from pokemon_helpers import G3_ROWS, NDS_ROWS, crc, pk3, pk45, prng
from soullink import pokemon_data as pd
from soullink.pokemon_data import Catch

SESSIONS = Path(os.environ.get("SOULLINK_TEST_SESSIONS", Path(tempfile.gettempdir()) / "soullink-sessions"))
JAR = Path(__file__).parent.parent / "vendor" / "randomizer" / "PokeRandoZX.jar"


def test_g3_dex_numbers():
    """Generation 3 internal numbers map to national dex numbers."""
    assert [pd.g3_national(n) for n in (1, 151, 251, 277, 280, 303, 359, 411)] == \
           [1, 151, 251, 252, 255, 292, 334, 358]
    assert pd.g3_national(0) == pd.g3_national(260) == pd.g3_national(412) == 0
    assert sorted(pd.G3_HOENN) == list(range(252, 387))


def test_pk3_decrypt_and_checksum():
    """PK3 records are decrypted and checksummed."""
    mon = pk3(280, "Äffchen", location=101, catch_level=3, level=7)
    assert pd.pk3(mon, True, None, 0, mon[0x54]) == Catch(255, "Äffchen", 101, False, False, True, None, 0, None, 7)
    assert pd.pk3(pk3(1, "BISA", catch_level=0), False, 2, 4).hatched
    broken = bytearray(mon)
    broken[0x30] ^= 0xFF
    assert pd.pk3(bytes(broken), True, None, 0) is None
    assert pd.pk3(pk3(260, "SLOT"), False, 0, 0) is None


def test_g5_nickname_special_chars():
    """Generation 5 nicknames with special characters decode."""
    assert pd.g5_text(struct.pack("<6H", 0x41, 0x246D, 0x246E, 0x2479, 0x1F, 0xFFFF)) == "A♂♀"


def test_nds_all_block_orders():
    """All block orders of NDS records decode."""
    for nr in range(24):
        pid = nr << 13 | 0x1234
        catch = pd.pk45(pk45(nr + 1, 5, "X", pid=pid, level=3), 5, True, None, 0)
        assert (catch.kind, catch.level, catch.nickname) == (nr + 1, 3, "X")


def test_orders_match_pkhex():
    """The block orders match PKHeX."""
    assert pd.G3_ROWS == G3_ROWS
    assert pd.NDS_ROWS == NDS_ROWS
    assert crc(b"123456789") == pd.crc16(b"123456789") == 0x29B1


def test_g4_half_decrypted_records_in_ram():
    """Half-decrypted generation 4 records in RAM are read."""
    mon = bytearray(pk45(6, 4, "Charizard", level=13, kp=44))
    pid, check = struct.unpack_from("<I2xH", mon)
    raw = struct.unpack_from("<64H", mon, 8)
    clear = prng(check, raw)
    for k in (0, 6, 17, 64):
        partial = bytes(mon[:8]) + struct.pack("<64H", *(clear[:k] + list(raw[k:]))) + bytes(mon[0x88:])
        assert (pd.pk45(partial, 4, True, None, 0).kind, pd.pk45(partial, 4, True, None, 0).level) == (6, 13)
    extra = struct.unpack_from("<5H", mon, 0x88)
    clear_extra = bytes(mon[:0x88]) + struct.pack("<5H", *prng(pid, extra)) + bytes(mon[0x92:])
    assert pd.pk45(clear_extra, 4, True, None, 0).level == 13
    broken = bytes(mon[:8]) + bytes(64 * 2) + bytes(mon[0x88:])
    assert pd.pk45(broken, 4, True, None, 0) is None


def test_nds_buffer_without_hit():
    """Without a hit the NDS buffer search returns nothing."""
    gen, team, slots = pd.NDS_BUFFER["CPU"]
    assert pd.nds_buffer(bytes(0x80000), gen, team, slots) == (0, [])
    assert pd.box_slots(4, 0xFF0, 2)[29:31] == [4 + 29 * 136, 4 + 0xFF0]


def _zx_table(name):
    """A table from the randomizer jar for comparison; the test is skipped without the jar."""
    if not JAR.exists():
        pytest.skip("PokeRandoZX.jar missing")
    char = {}
    with zipfile.ZipFile(JAR) as z:
        for row in z.read(f"com/dabomstew/pkrandom/config/{name}").decode("utf-8").splitlines():
            nr, _, value = row.partition("=")
            char.setdefault(int(nr, 16), set()).add(value)
    return char


def test_charsets_match_zx():
    """The character sets match ZX."""
    for name, own in (("gba_english.tbl", pd.G3_CHAR), ("Generation4.tbl", pd.G4_CHAR),
                         ("Generation5.tbl", pd.G5_CHAR)):
        zx = _zx_table(name)
        assert all(z in zx[nr] for nr, z in own.items()), name


def test_dex_table_matches_the_rom():
    """The dex table matches the ROM."""
    rom_paths = sorted(SESSIONS.glob("*/p*/rom.gba")) if SESSIONS.is_dir() else []
    if not rom_paths:
        pytest.skip("no GBA ROM in SOULLINK_TEST_SESSIONS")
    rom = rom_paths[0].read_bytes()
    start = rom.find(struct.pack("<251H", *range(1, 252)))
    assert start > 0
    table = struct.unpack_from("<411H", rom, start)
    assert list(table[276:]) == list(pd.G3_HOENN)
    assert all(pd.g3_national(n) in (table[n - 1], 0) for n in range(1, 412))
