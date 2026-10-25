"""Small ROMs with party icon tables for tests of soullink.world and the plugins that draw with it."""
import struct

import pytest

from soullink.world import ICON_COUNT
from test_nds_file import narc_build, ncgr_build, nclr_build, nds_rom

PALETTES = [[0, 0x001F, 0x001F] + [0] * 13, [0, 0x03E0, 0x03E0] + [0] * 13, [0, 0x7C00, 0x7C00] + [0] * 13]


@pytest.fixture
def icon_rom() -> bytes:
    """Small GBA ROM with icon tables: every species shows frame 0 fully in color 1 (red), frame 1 in color 2 (blue)."""
    rom = bytearray(0x4000)
    table, data, palette = 0x100, 0x2000, 0x3000
    struct.pack_into(f"<{ICON_COUNT}I", rom, table, *[0x08000000 + data] * ICON_COUNT)
    palettes = table + 5 * ICON_COUNT
    for i in range(3):
        struct.pack_into("<IHH", rom, palettes + 8 * i, 0x08000000 + palette, 0xDAC0 + i, 0)
    struct.pack_into("<3H", rom, palette, 0, 0x001F, 0x7C00)
    rom[data:data + 0x200] = b"\x11" * 0x200
    rom[data + 0x200:data + 0x400] = b"\x22" * 0x200
    return bytes(rom)


@pytest.fixture
def nds_icon_rom() -> bytes:
    """HGSS-like ROM: palettes (0 red, 1 green, 2 blue), 30 icons with frame 0 in color 1 and frame 1 in color 2, and a
    palette table in the ARM9 starting with Pikachu (25)."""
    icon = ncgr_build(b"\x11" * 512 + b"\x22" * 512)
    table = bytearray([0, 1, 1, 1, 0, 0, 0, 0, 2, 2] + [0] * 20)
    table[25] = 2
    return nds_rom({"a/0/2/0": narc_build([nclr_build(PALETTES)] + [b"-"] * 6 + [icon] * 30)},
                   arm9=b"CODE" + bytes(table) + bytes(8))


@pytest.fixture
def gen5_icon_rom() -> bytes:
    """Like Black 2: a/0/0/7 with two palette files first, then per species an icon and an (empty) female icon; a table
    with one byte per species (low nibble), Pikachu on palette 2."""
    icon = ncgr_build(b"\x11" * 512 + b"\x22" * 512)
    table = bytearray([0, 0x11, 0x11, 0x11, 0, 0, 0, 0, 0x22, 0x22] + [0] * 20)
    table[25] = 0x12
    files = [nclr_build(PALETTES), nclr_build(PALETTES)] + [b"-"] * 6
    for _ in range(30):
        files += [icon, b""]
    return nds_rom({"a/0/0/7": narc_build(files)}, arm9=b"CODE" + bytes(table) + bytes(8))
