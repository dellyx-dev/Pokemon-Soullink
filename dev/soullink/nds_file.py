"""Reads files from an NDS ROM without loading it completely: ARM9 (BLZ-packed), file system (FNT/FAT), NARC archives and
the NCLR (palette) and NCGR (4-bit tile) graphics formats."""
from __future__ import annotations

import struct
from typing import BinaryIO


def blz_unpack(data: bytes) -> bytes:
    """Decompresses backwards LZ data as used for the ARM9 of Platinum and HGSS; data that is not packed is returned
    unchanged."""
    if len(data) < 8:
        return data
    header_end, extra = struct.unpack_from("<II", data, len(data) - 8)
    header, packed = header_end >> 24, header_end & 0xFFFFFF
    if not 8 <= header <= 0x20 or packed > len(data) or extra > 0x400000:
        return data
    output = bytearray(data) + bytearray(extra)
    a, write, end = len(data) - header, len(data) + extra, len(data) - packed
    while a > end:
        a -= 1
        flags = data[a]
        for _ in range(8):
            if a <= end:
                break
            if flags & 0x80:
                a -= 2
                info = data[a + 1] << 8 | data[a]
                gap = (info & 0xFFF) + 3
                for _ in range((info >> 12) + 3):
                    write -= 1
                    output[write] = output[write + gap]
            else:
                a -= 1
                write -= 1
                output[write] = data[a]
            flags = flags << 1 & 0xFF
    return bytes(output)


class NdsRom:
    """Reads the header, the ARM9 and single files (path like "a/0/2/0") from an open ROM file."""

    def __init__(self, file: BinaryIO):
        """Reads the header and the file name and allocation tables of the ROM."""
        self._file = file
        header = self._read(0, 0x50)
        self.arm9_start, _, self.arm9_ram, self.arm9_size = struct.unpack_from("<IIII", header, 0x20)
        fnt, fnt_size, fat, fat_size = struct.unpack_from("<IIII", header, 0x40)
        self._fnt = self._read(fnt, fnt_size)
        self._fat = self._read(fat, fat_size)

    def _read(self, place: int, length: int) -> bytes:
        """Reads length bytes at the given offset of the ROM file."""
        self._file.seek(place)
        return self._file.read(length)

    def arm9(self) -> bytes:
        """The unpacked ARM9 code as it sits in RAM from arm9_ram on."""
        return blz_unpack(self._read(self.arm9_start, self.arm9_size))

    def file_number(self, path: str) -> int | None:
        """File id for a path in the file name table; None if the path does not exist."""
        dir, parts = 0, path.split("/")
        for k, part in enumerate(parts):
            under, number = struct.unpack_from("<IH", self._fnt, dir * 8)
            place = under
            while True:
                length = self._fnt[place]
                if length == 0:
                    return None
                name = self._fnt[place + 1:place + 1 + (length & 0x7F)].decode("latin-1")
                place += 1 + (length & 0x7F)
                if length & 0x80:
                    kind = struct.unpack_from("<H", self._fnt, place)[0] & 0xFFF
                    place += 2
                    if name == part and k < len(parts) - 1:
                        dir = kind
                        break
                elif name == part and k == len(parts) - 1:
                    return number
                else:
                    number += 1
        return None

    def file(self, path: str) -> bytes | None:
        """Content of the file at the path; None if it does not exist."""
        number = self.file_number(path)
        if number is None or (number + 1) * 8 > len(self._fat):
            return None
        start, end = struct.unpack_from("<II", self._fat, number * 8)
        return self._read(start, end - start)


def narc(data: bytes) -> list[bytes]:
    """Splits a NARC archive (BTAF, BTNF, GMIF blocks) into its files."""
    place = struct.unpack_from("<H", data, 0x0C)[0]
    if data[:4] != b"NARC" or data[place:place + 4] != b"BTAF":
        raise ValueError("not a NARC archive")
    count = struct.unpack_from("<H", data, place + 8)[0]
    limits = [struct.unpack_from("<II", data, place + 12 + 8 * i) for i in range(count)]
    place += struct.unpack_from("<I", data, place + 4)[0]
    place += struct.unpack_from("<I", data, place + 4)[0]
    return [data[place + 8 + a:place + 8 + e] for a, e in limits]


def _section(data: bytes, name: bytes) -> int:
    """Offset of the named section in an NCLR/NCGR file."""
    place = struct.unpack_from("<H", data, 0x0C)[0]
    while place + 8 <= len(data):
        if data[place:place + 4] == name:
            return place
        place += max(8, struct.unpack_from("<I", data, place + 4)[0])
    raise ValueError(f"{name!r} missing")


def nclr_palettes(data: bytes) -> list[list[tuple[int, int, int]]]:
    """Palettes of 16 colors each (BGR555 converted to RGB)."""
    place = _section(data, b"TTLP")
    size, offset = struct.unpack_from("<II", data, place + 16)
    colors = struct.unpack_from(f"<{size // 2}H", data, place + 8 + offset)
    rgb = [((f & 31) * 255 // 31, (f >> 5 & 31) * 255 // 31, (f >> 10 & 31) * 255 // 31) for f in colors]
    return [rgb[i:i + 16] for i in range(0, len(rgb) - 15, 16)]


def ncgr_pixel(data: bytes) -> bytes:
    """Raw 4-bit tile data (8x8 pixels, 32 bytes per tile) of an NCGR file."""
    place = _section(data, b"RAHC")
    size, offset = struct.unpack_from("<II", data, place + 8 + 0x10)
    return data[place + 8 + offset:place + 8 + offset + size]
