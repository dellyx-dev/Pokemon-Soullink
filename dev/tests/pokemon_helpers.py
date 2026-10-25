"""Builders for synthetic Pokemon records, saves and RAM dumps of generations 3-5."""
from __future__ import annotations

import binascii
import itertools
import struct

from soullink import pokemon_data


def prng(seed, words):
    """Encrypts or decrypts words with the NDS random number generator."""
    out = []
    for w in words:
        seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        out.append(w ^ (seed >> 16))
    return out


def crc(data):
    """CRC-16/CCITT-FALSE of the data."""
    return binascii.crc_hqx(bytes(data), 0xFFFF)


G3_ROWS = ["".join(p) for p in itertools.permutations("GAEM")]
G3_TEXT = {v: k for k, v in pokemon_data.G3_CHAR.items()}


def pk3(kind, name="", location=0, catch_level=5, ei=False, pid=0x12345678, otid=0x0BADF00D, level=None):
    """Builds an encrypted PK3 record."""
    parts = {"G": struct.pack("<HHIBBH", kind, 0, 0, 0, 0, 0), "A": bytes(12), "E": bytes(12),
             "M": struct.pack("<BBHII", 0, location, catch_level, (1 << 30) if ei else 0, 0)}
    raw = b"".join(parts[k] for k in G3_ROWS[pid % 24])
    check = sum(struct.unpack("<24H", raw)) & 0xFFFF
    encoded = bytes(G3_TEXT[z] for z in name).ljust(10, b"\xff")
    mon = (struct.pack("<II", pid, otid) + encoded + bytes([5, 2]) + b"\xff" * 7 + b"\x00"
           + struct.pack("<HH", check, 0) + struct.pack("<12I", *(w ^ pid ^ otid for w in struct.unpack("<12I", raw))))
    return mon if level is None else mon + bytes(4) + bytes([level]) + bytes(15)


def g3_checksum(data):
    """Checksum of a generation 3 save sector."""
    sum_ = sum(struct.unpack("<992I", data)) & 0xFFFFFFFF
    return ((sum_ >> 16) + sum_) & 0xFFFF


def g3_slot(sav, counter, team=(), boxes=None, team_size=0x34):
    """Writes a save slot as the game does: slot = counter % 2, sections rotated by the counter."""
    section1 = bytearray(0xF80)
    section1[team_size] = len(team)
    for i, mon in enumerate(team):
        section1[team_size + 4 + i * 100:team_size + 4 + (i + 1) * 100] = mon
    pc = bytearray(9 * 0xF80)
    for (box, slot), mon in (boxes or {}).items():
        pc[4 + (box * 30 + slot) * 80:4 + (box * 30 + slot + 1) * 80] = mon
    sections = [bytes(0xF80)] * 14
    sections[1] = bytes(section1)
    sections[5:] = [bytes(pc[i * 0xF80:(i + 1) * 0xF80]) for i in range(9)]
    for nr, data in enumerate(sections):
        sector = bytearray(0x1000)
        sector[:0xF80] = data
        struct.pack_into("<HHII", sector, 0xFF4, nr, g3_checksum(data), 0x08012025, counter)
        pos = (counter % 2) * 14 + (nr + counter) % 14
        sav[pos * 0x1000:(pos + 1) * 0x1000] = sector
    return sav


def g3_sav(**slot):
    """Builds a generation 3 save with one valid slot."""
    return g3_slot(bytearray(b"\xff" * 0x20000), 1, **slot)


def g3_team_set(ram, start, mons, number_place=None):
    """Writes team records into a RAM dump."""
    for i, mon in enumerate(mons):
        ram[start + i * 100:start + (i + 1) * 100] = mon
    for i in range(len(mons), 6):
        ram[start + i * 100 + 0x55] = 0xFF
    if number_place is not None:
        ram[number_place] = len(mons)


def g3_pc_set(ram, base, boxes):
    """Writes box records into a RAM dump."""
    for (box, slot), mon in boxes.items():
        start = base + 4 + (box * 30 + slot) * 80
        ram[start:start + 80] = mon
    for i in range(14):
        name = bytes(G3_TEXT[z] for z in f"BOX {i + 1}") + b"\xff"
        ram[base + 4 + 420 * 80 + i * 9:base + 4 + 420 * 80 + i * 9 + len(name)] = name


def gmain_set(iwram, place, in_battle, game="BPR"):
    """Writes gMain as in FireRed: seven callbacks, intrCheck, keys; bit 1 of +0x439 (Ruby/Sapphire +0x43D) is
    inBattle."""
    struct.pack_into("<7I", iwram, place, 0x08012369, 0x08011085, 0x0807FAA5, 0x08011679, 0, 0, 0x0800B719)
    struct.pack_into("<HH", iwram, place + 0x1C, 6, 0)
    iwram[place + pokemon_data.g3_battle_flag(game)] = 0x02 if in_battle else 0x00


def flags_set(ram, flags, numbers):
    """Sets flag bits in a RAM dump."""
    for n in numbers:
        ram[flags + n // 8] |= 1 << (n % 8)


G3_TEAM = [pk3(83, "FARFETCHD", location=101, level=4), pk3(10, "CATERPIE", location=102, level=2, pid=3)]
G3_OPPONENT = [pk3(374, "AALABYSS", location=101, catch_level=3, level=3, pid=11)]
G3_PC = {(0, 0): pk3(395, "BAGON", location=88), (1, 5): pk3(25, "PIKA", location=89, pid=8)}


NDS_ROWS = ["".join(p) for p in itertools.permutations("ABCD")]
G4_TEXT = {v: k for k, v in pokemon_data.G4_CHAR.items()}
G5_TEXT = {"♂": 0x246D, "♀": 0x246E}


def _name(text, gen):
    """Encodes a name in the text format of the generation."""
    char = [G4_TEXT[z] if gen == 4 else G5_TEXT.get(z, ord(z)) for z in text]
    return struct.pack(f"<{len(char) + 1}H", *char, 0xFFFF)


def pk45(kind, gen, name="", location=0, location_dp=0, ei_location=0, ei_location_dp=0, ei=False, day=(26, 10, 19), pid=0x2A6F1C35,
         level=None, kp=0):
    """Builds an encrypted PK4/PK5 record."""
    raw = bytearray(0x88)
    struct.pack_into("<I", raw, 0, pid)
    struct.pack_into("<H", raw, 0x08, kind)
    struct.pack_into("<I", raw, 0x38, (1 << 30) if ei else 0)
    if gen == 4:
        struct.pack_into("<HH", raw, 0x44, ei_location, location)
        struct.pack_into("<HH", raw, 0x7E, ei_location_dp, location_dp)
    else:
        struct.pack_into("<HH", raw, 0x7E, ei_location, location)
    encoded = _name(name, gen)
    raw[0x48:0x48 + len(encoded)] = encoded
    raw[0x7B:0x7E] = bytes(day)
    check = sum(struct.unpack_from("<64H", raw, 8)) & 0xFFFF
    struct.pack_into("<H", raw, 6, check)
    blocks = {k: raw[8 + i * 32:8 + (i + 1) * 32] for i, k in enumerate("ABCD")}
    mixed = b"".join(blocks[k] for k in NDS_ROWS[((pid >> 13) & 31) % 24])
    mon = bytes(raw[:8]) + struct.pack("<64H", *prng(check, struct.unpack("<64H", mixed)))
    if level is None:
        return mon
    extra = bytearray(0x64 if gen == 4 else 0x54)
    extra[4] = level
    struct.pack_into("<HH", extra, 6, kp, max(kp, 10))
    words = len(extra) // 2
    return mon + struct.pack(f"<{words}H", *prng(pid, struct.unpack(f"<{words}H", extra)))


def empty_slot():
    """Empty slots in a save are encrypted zeros with PID 0 and checksum 0."""
    return bytes(8) + struct.pack("<64H", *prng(0, [0] * 64))


G4 = {"ADAD": (0xC100, 0xC100, 0x121E0, 0x14, 0x98, 4, 0xFF0),
      "CPUD": (0xCF2C, 0xCF2C, 0x121E4, 0x14, 0xA0, 4, 0xFF0),
      "IPKD": (0xF628, 0xF700, 0x12310, 0x10, 0x98, 0, 0x1000)}
G4["APAD"], G4["IPGD"] = G4["ADAD"], G4["IPKD"]


def _g4_block(sav, half, start, size, foot, content, counter):
    """Builds a generation 4 save block with footer and counter."""
    block = bytearray(size)
    block[:len(content)] = content
    struct.pack_into("<II", block, size - foot, *counter)
    struct.pack_into("<H", block, size - 2, crc(block[:-foot]))
    sav[half * 0x40000 + start:half * 0x40000 + start + size] = block


def g4_write(sav, code, half, team=None, boxes=None, counter=(1, 1)):
    """Writes team and boxes into a generation 4 save half."""
    general, storage_start, storage, foot, team_place, box_start, gap = G4[code]
    if team is not None:
        content = bytearray(team_place + 6 * 236)
        struct.pack_into("<II", content, team_place - 8, 6, len(team))
        for i, mon in enumerate(team):
            content[team_place + i * 236:team_place + (i + 1) * 236] = mon
        _g4_block(sav, half, 0, general, foot, content, counter)
    if boxes is not None:
        content = bytearray(box_start + 18 * gap)
        for box in range(18):
            for slot in range(30):
                start = box_start + box * gap + slot * 136
                content[start:start + 136] = boxes.get((box, slot), empty_slot())
        _g4_block(sav, half, storage_start, storage, foot, content, counter)
    return sav


def _g5_block(sav, start, length, content, counter=1):
    """Builds a generation 5 save block with checksum."""
    block = bytearray(length)
    block[:len(content)] = content
    sav[start:start + length] = block
    struct.pack_into("<HH", sav, start + length, counter, crc(block))


def g5_sav(team=(), boxes=None, copy=0x26000):
    """Builds a generation 5 save with team, boxes and backup copy."""
    sav = bytearray(0x80000)
    for base in (0, copy):
        content = bytearray(8)
        struct.pack_into("<II", content, 0, 6, len(team))
        _g5_block(sav, base + 0x18E00, 0x534, content + b"".join(team))
        for box in range(24):
            content = b"".join((boxes or {}).get((box, slot), empty_slot()) for slot in range(30))
            _g5_block(sav, base + 0x400 + box * 0x1000, 0xFF0, content)
    return sav

