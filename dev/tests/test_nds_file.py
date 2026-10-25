"""Tests of reading NDS ROM files."""
import io
import struct

import pytest

from soullink.nds_file import NdsRom, blz_unpack, narc, ncgr_pixel, nclr_palettes


def nds_rom(files: dict[str, bytes], arm9: bytes = b"") -> bytes:
    """ROM with header, ARM9 and file system (folders as path parts, e.g. "a/0/2/0")."""
    tree: dict = {}
    for path in files:
        node, parts = tree, path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = path
    dir: list[dict] = []

    def collect(node):
        """Collects the directory entries of a node."""
        dir.append(node)
        for kind in node.values():
            if isinstance(kind, dict):
                collect(kind)

    collect(tree)
    number_of = {id(k): i for i, k in enumerate(dir)}
    row, first, under = [], [], []
    for k in dir:
        first.append(len(row))
        table = bytearray()
        for name, kind in k.items():
            raw = name.encode()
            if isinstance(kind, dict):
                table += bytes([0x80 | len(raw)]) + raw + struct.pack("<H", 0xF000 | number_of[id(kind)])
            else:
                table += bytes([len(raw)]) + raw
                row.append(kind)
        under.append(bytes(table) + b"\0")
    fnt, offset = bytearray(), 8 * len(dir)
    for i in range(len(dir)):
        fnt += struct.pack("<IHH", offset, first[i], len(dir) if i == 0 else 0xF000)
        offset += len(under[i])
    fnt += b"".join(under)
    rom = bytearray(0x200)
    arm9_start = len(rom)
    rom += arm9
    fnt_start = len(rom)
    rom += fnt
    fat_start = len(rom)
    rom += bytes(8 * len(row))
    for i, path in enumerate(row):
        start = len(rom)
        rom += files[path]
        struct.pack_into("<II", rom, fat_start + 8 * i, start, len(rom))
    struct.pack_into("<IIII", rom, 0x20, arm9_start, 0, 0x02000000, len(arm9))
    struct.pack_into("<IIII", rom, 0x40, fnt_start, len(fnt), fat_start, 8 * len(row))
    return bytes(rom)


def narc_build(files: list[bytes]) -> bytes:
    """Builds a NARC archive from files."""
    limits, data = [], b""
    for d in files:
        limits.append((len(data), len(data) + len(d)))
        data += d
    btaf = b"BTAF" + struct.pack("<IHH", 12 + 8 * len(files), len(files), 0) + \
        b"".join(struct.pack("<II", a, e) for a, e in limits)
    btnf = b"BTNF" + struct.pack("<IIHH", 16, 4, 0, 1)
    gmif = b"GMIF" + struct.pack("<I", 8 + len(data)) + data
    body = btaf + btnf + gmif
    return b"NARC" + struct.pack("<HHIHH", 0xFFFE, 0x0100, 16 + len(body), 16, 3) + body


def nclr_build(palettes: list[list[int]]) -> bytes:
    """Palettes as lists of 16 BGR555 colours."""
    colors = b"".join(struct.pack("<16H", *p) for p in palettes)
    ttlp = b"TTLP" + struct.pack("<IIIII", 0x18 + len(colors), 3, 0, len(colors), 0x10) + colors
    return b"RLCN" + struct.pack("<HHIHH", 0xFEFF, 0x0100, 16 + len(ttlp), 16, 1) + ttlp


def ncgr_build(pixel: bytes) -> bytes:
    """Builds an NCGR file from pixel data."""
    rahc = b"RAHC" + struct.pack("<IHHIIBBHII", 0x20 + len(pixel), 0xFFFF, 0xFFFF, 3, 0, 0, 0, 0, len(pixel), 0x18) + pixel
    return b"RGCN" + struct.pack("<HHIHH", 0xFEFF, 0x0101, 16 + len(rahc), 16, 1) + rahc


def test_blz_unpack():
    """Backwards LZ data is unpacked."""
    packed = bytes([0x00, 0xF0]) + b"XYZ" + bytes([0x10])
    foot = struct.pack("<II", 8 << 24 | len(packed) + 8, 21 - len(packed) - 8)
    assert blz_unpack(b"HEADER" + packed + foot) == b"HEADER" + b"XYZ" * 7
    assert blz_unpack(b"unpacked" + bytes(8)) == b"unpacked" + bytes(8)


def test_filesystem_narc_and_graphics():
    """File system, NARC and graphics formats are read."""
    pixel = bytes(range(32)) * 2
    archive = narc_build([nclr_build([[0, 0x001F] + [0] * 14, [0, 0x7C00] + [0] * 14]), b"x", ncgr_build(pixel)])
    rom = NdsRom(io.BytesIO(nds_rom({"a/0/2/0": archive, "a/0/2/1": b"different", "b/c": b"deep"}, arm9=b"ARM9" + bytes(8))))
    assert rom.file("a/0/2/1") == b"different" and rom.file("b/c") == b"deep"
    assert rom.file("a/0/2/9") is None and rom.file("x/y") is None
    assert rom.arm9() == b"ARM9" + bytes(8)
    files = narc(rom.file("a/0/2/0"))
    assert len(files) == 3 and files[1] == b"x"
    assert nclr_palettes(files[0])[1][1] == (0, 0, 255)
    assert ncgr_pixel(files[2]) == pixel
    with pytest.raises(ValueError):
        narc(b"NOT NARC!" + bytes(16))
