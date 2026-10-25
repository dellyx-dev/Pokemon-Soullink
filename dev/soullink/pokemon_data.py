"""Pokemon records of generations 3-5: decrypting, texts, checksums, and finding the team and save data in RAM. Core
service for everything that reads Pokemon from saves or RAM dumps; formats as in PKHeX, verified against real saves and
RAM dumps (FireRed, Platinum, SoulSilver, Black 2), the first three characters of the ROM code identify the game (e.g.
"BPR" for FireRed)."""
from __future__ import annotations

import binascii
import re
import struct
from dataclasses import dataclass
from datetime import date

import numpy as np


@dataclass(frozen=True)
class Catch:
    """One Pokemon from the team or a box."""
    kind: int
    nickname: str
    location: int
    ei: bool
    hatched: bool
    team: bool
    box: int | None
    slot: int
    day: date | None = None
    level: int | None = None


@dataclass(frozen=True)
class Opponent:
    """The opponent's Pokemon in a running battle."""
    kind: int
    level: int
    kp: int
    active: bool = False
    types: tuple[str, ...] = ()


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE as used in the NDS saves (generation 4/5 blocks)."""
    return binascii.crc_hqx(bytes(data), 0xFFFF)


G3_ROWS = ["GAEM", "GAME", "GEAM", "GEMA", "GMAE", "GMEA", "AGEM", "AGME", "AEGM", "AEMG", "AMGE", "AMEG",
             "EGAM", "EGMA", "EAGM", "EAMG", "EMGA", "EMAG", "MGAE", "MGEA", "MAGE", "MAEG", "MEGA", "MEAG"]
G3_HOENN = (252, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270, 271,
            272, 273, 274, 275, 290, 291, 292, 276, 277, 285, 286, 327, 278, 279, 283, 284, 320, 321, 300, 301,
            352, 343, 344, 299, 324, 302, 339, 340, 370, 341, 342, 349, 350, 318, 319, 328, 329, 330, 296, 297,
            309, 310, 322, 323, 363, 364, 365, 331, 332, 361, 362, 337, 338, 298, 325, 326, 311, 312, 303, 307,
            308, 333, 334, 360, 355, 356, 315, 287, 288, 289, 316, 317, 357, 293, 294, 295, 366, 367, 368, 359,
            353, 354, 336, 335, 369, 304, 305, 306, 351, 313, 314, 345, 346, 347, 348, 280, 281, 282, 371, 372,
            373, 374, 375, 376, 377, 378, 379, 382, 383, 384, 380, 381, 385, 386, 358)
G3_CHAR = {0x00: " ", 0x15: "ß", 0x5C: "(", 0x5D: ")", 0xAB: "!", 0xAC: "?", 0xAD: ".", 0xAE: "-", 0xB0: "…",
              0xB5: "♂", 0xB6: "♀", 0xB8: ",", 0xBA: "/", 0xF0: ":", 0xF1: "Ä", 0xF2: "Ö", 0xF3: "Ü", 0xF4: "ä",
              0xF5: "ö", 0xF6: "ü",
              **{0xA1 + i: str(i) for i in range(10)},
              **{0xBB + i: chr(ord("A") + i) for i in range(26)},
              **{0xD5 + i: chr(ord("a") + i) for i in range(26)}}
G3_DATA = 0xF80


def g3_checksum(sector: bytes) -> int:
    """Checksum of a generation 3 save sector (over G3_DATA bytes)."""
    sum_ = sum(struct.unpack_from(f"<{G3_DATA // 4}I", sector)) & 0xFFFFFFFF
    return ((sum_ >> 16) + sum_) & 0xFFFF


def g3_national(internal: int) -> int:
    """Internal species number (generation 3) to national dex number; 0 means no species."""
    if 1 <= internal <= 251:
        return internal
    if 277 <= internal <= 411:
        return G3_HOENN[internal - 277]
    return 0


def g3_text(data: bytes) -> str:
    """Decodes generation 3 text."""
    text = []
    for char in data:
        if char == 0xFF:
            break
        text.append(G3_CHAR.get(char, ""))
    return "".join(text).strip()


def pk3(data: bytes, team: bool, box: int | None, slot: int, level: int | None = None) -> Catch | None:
    """Decrypts a PK3; None if the checksum does not match or there is no species."""
    pid, otid = struct.unpack_from("<II", data)
    raw = struct.pack("<12I", *(w ^ pid ^ otid for w in struct.unpack_from("<12I", data, 0x20)))
    if sum(struct.unpack("<24H", raw)) & 0xFFFF != struct.unpack_from("<H", data, 0x1C)[0]:
        return None
    part = {k: raw[i * 12:(i + 1) * 12] for i, k in enumerate(G3_ROWS[pid % 24])}
    kind = g3_national(struct.unpack_from("<H", part["G"])[0])
    if not kind:
        return None
    location, origin, values = struct.unpack_from("<xBHI", part["M"])
    ei = bool(values >> 30 & 1)
    return Catch(kind, g3_text(data[8:18]), location, ei, not ei and origin & 0x7F == 0, team, box, slot, None, level)


G3_RAM_TEAM = {"BPR": (-600, -603), "BPG": (-600, -603), "BPE": (600, -3), "AXV": (608, -16), "AXP": (608, -16)}
G3_RS_BLOCK1 = 0x02025734


def g3_battle_flag(game: str) -> int:
    """Offset of the gMain byte whose bit 1 is inBattle: Ruby/Sapphire keep objCount before the OAM buffer, so it sits
    4 bytes later than in FireRed/LeafGreen/Emerald."""
    return 0x43D if game[:3] in ("AXV", "AXP") else 0x439


def g3_ram_slots(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    """For every 4-byte position: does a PK3 with a valid checksum start there, or an empty slot (80 zero bytes)?"""
    w = np.frombuffer(data, "<u4", len(data) // 4)
    n = max(len(w) - 20, 0)
    key = w[:n] ^ w[1:n + 1]
    sum_ = np.zeros(n, np.uint32)
    for k in range(8, 20):
        part = w[k:n + k] ^ key
        sum_ += (part & 0xFFFF) + (part >> 16)
    not_null = np.concatenate(([0], np.cumsum(w != 0)))
    empty = not_null[20:n + 20] == not_null[:n]
    return ((sum_ & 0xFFFF) == (w[7:n + 7] & 0xFFFF)) & ~empty, empty


def g3_ram_team(data: bytes, valid: np.ndarray, empty: np.ndarray, game: str) -> int | None:
    """Position of gPlayerParty in the block `data` (valid/empty from g3_ram_slots); None if not found."""
    opponent, number = G3_RAM_TEAM[game]

    def slots(start: int) -> list[str] | None:
        """Slot pattern at a start position: "x" (Pokemon), "-" (empty) or None per slot."""
        if start < 0 or start % 4 or start // 4 + 125 >= len(valid):
            return None
        binding = ["x" if valid[start // 4 + 25 * i] and 1 <= data[start + 100 * i + 0x54] <= 100
                    else "-" if empty[start // 4 + 25 * i] else "?" for i in range(6)]
        return None if "?" in binding else binding

    for word in np.flatnonzero(valid):
        start = int(word) * 4
        team = slots(start)
        if team is None or slots(start + opponent) is None:
            continue
        count = "".join(team).rstrip("-")
        if count and "-" not in count and start + number >= 0 and data[start + number] == len(count):
            return start
    return None


def g3_gmain(iw: bytes) -> int | None:
    """Finds gMain in IWRAM: seven callback pointers (each into the ROM or 0; callback2 and serialCallback are always set,
    vblankCallback is missing e.g. in the FRLG help menu), followed by the interrupt state."""
    def rom(x: int) -> bool:
        """True for an address in the ROM area."""
        return 0x08000000 <= x < 0x0A000000

    for o in range(0, len(iw) - 0x440, 4):
        cb1, cb2, saved, vblank, hblank, vcount, serial = struct.unpack_from("<7I", iw, o)
        if not (rom(cb2) and rom(serial) and all(x == 0 or rom(x) for x in (cb1, saved, vblank, hblank, vcount))):
            continue
        intr, rest = struct.unpack_from("<HH", iw, o + 0x1C)
        if intr <= 0x3FFF and rest == 0 and all(t <= 0x3FF for t in struct.unpack_from("<5H", iw, o + 0x28)):
            return o
    return None


def g3_block_pointer(iw: bytes) -> int | None:
    """Position of gSaveBlock1Ptr in IWRAM (FRLG/Emerald), followed by gSaveBlock2Ptr and gPokemonStoragePtr, all pointing
    into EWRAM with the same random offset."""
    w = np.frombuffer(iw, "<u4", len(iw) // 4).astype(np.int64)
    if len(w) < 3:
        return None
    b1, b2, pc = w[:-2], w[1:-1], w[2:]

    def ewram(v):
        """Mask of the values that point into EWRAM."""
        return (v >= 0x02000000) & (v < 0x02040000)

    hit = np.flatnonzero(ewram(b1) & ewram(b2) & ewram(pc) & (b1 - b2 >= 0xF00) & (b1 - b2 <= 0x1000)
                             & (pc - b1 >= 0x3D00) & (pc - b1 <= 0x3F00))
    return int(hit[0]) * 4 if len(hit) else None


def g3_block1(blocks: dict[int, bytes], game: str) -> int | None:
    """Address of SaveBlock1 (flags, position): fixed for RS, via gSaveBlock1Ptr for FRLG/Emerald."""
    if game in ("AXV", "AXP"):
        return G3_RS_BLOCK1
    iw = bytes(blocks.get(0x03000000, b""))
    place = g3_block_pointer(iw)
    return struct.unpack_from("<I", iw, place)[0] if place is not None else None


NDS_ROWS = ["ABCD", "ABDC", "ACBD", "ACDB", "ADBC", "ADCB", "BACD", "BADC", "BCAD", "BCDA", "BDAC", "BDCA",
              "CABD", "CADB", "CBAD", "CBDA", "CDAB", "CDBA", "DABC", "DACB", "DBAC", "DBCA", "DCAB", "DCBA"]
NDS_MAX_KIND = {4: 493, 5: 649}
G4_CHAR = {0x01DE: " ", 0x017E: "ß", 0x0163: "Ä", 0x0175: "Ö", 0x017B: "Ü", 0x0183: "ä", 0x0195: "ö",
              0x019B: "ü", 0x0188: "é", 0x01AB: "!", 0x01AC: "?", 0x01AD: ",", 0x01AE: ".", 0x01AF: "…",
              0x01B1: "/", 0x01B3: "'", 0x01B9: "(", 0x01BA: ")", 0x01BB: "♂", 0x01BC: "♀", 0x01BE: "-",
              0x01C4: ":",
              **{0x0121 + i: str(i) for i in range(10)},
              **{0x012B + i: chr(ord("A") + i) for i in range(26)},
              **{0x0145 + i: chr(ord("a") + i) for i in range(26)}}
G5_CHAR = {0x2467: "×", 0x2468: "÷", 0x246C: "…", 0x246D: "♂", 0x246E: "♀"}


def prng(seed: int, words) -> list[int]:
    """Encrypts or decrypts words with the random number generator of the NDS games (the same operation)."""
    out = []
    for word in words:
        seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        out.append(word ^ seed >> 16)
    return out


def day(jmt: bytes) -> date | None:
    """Date from year (since 2000), month and day bytes; None if invalid."""
    try:
        return date(2000 + jmt[0], jmt[1], jmt[2])
    except ValueError:
        return None


def g4_text(data: bytes) -> str:
    """Decodes generation 4 text."""
    text = []
    for (char,) in struct.iter_unpack("<H", data):
        if char == 0xFFFF:
            break
        text.append(G4_CHAR.get(char, ""))
    return "".join(text).strip()


def g5_text(data: bytes) -> str:
    """Decodes generation 5 text."""
    text = []
    for (char,) in struct.iter_unpack("<H", data):
        if char == 0xFFFF:
            break
        z = G5_CHAR.get(char, "") if 0x2460 <= char < 0x2500 else chr(char)
        if z.isprintable():
            text.append(z)
    return "".join(text).strip()


def readings(raw, clear) -> list[list[int]]:
    """Candidate decodings of a record: while running, the game decrypts a Pokemon it is working with in place, word by
    word from the start (seen on SoulSilver: one team Pokemon every other frame, sometimes midway), so raw and cleartext
    words can mix."""
    raw, clear = list(raw), list(clear)
    kinds = [clear, raw]
    for k in range(1, len(raw)):
        kinds += [raw[:k] + clear[k:], clear[:k] + raw[k:]]
    return kinds


def nds_words(data: bytes, check: int) -> list[int] | None:
    """The 64 decrypted words from 0x08 using the reading whose checksum matches."""
    raw = struct.unpack_from("<64H", data, 8)
    clear = prng(check, raw)
    if sum(clear) & 0xFFFF == check:
        return clear
    s_raw, s_clear = [0], [0]
    for a, b in zip(raw, clear):
        s_raw.append(s_raw[-1] + a)
        s_clear.append(s_clear[-1] + b)
    for k in range(65):
        if (s_raw[k] + s_clear[64] - s_clear[k]) & 0xFFFF == check:
            return list(raw[:k]) + clear[k:]
        if (s_clear[k] + s_raw[64] - s_raw[k]) & 0xFFFF == check:
            return clear[:k] + list(raw[k:])
    return None


def nds_battle_stats(mon: bytes) -> tuple[int, int] | None:
    """(level, HP) from the team extra at 0x88 (PRNG with the PID: 0x8C level, 0x8E HP, 0x90 max HP); without a checksum
    the first plausible reading applies."""
    pid = struct.unpack_from("<I", mon)[0]
    raw = struct.unpack_from("<5H", mon, 0x88)
    for words in readings(raw, prng(pid, raw)):
        level, kp, max_kp = words[2] & 0xFF, words[3], words[4]
        if 1 <= level <= 100 and 0 < max_kp < 1000 and kp <= max_kp:
            return level, kp
    return None


def pk45(data: bytes, gen: int, team: bool, box: int | None, slot: int) -> Catch | None:
    """Decrypts a PK4/PK5 (also in cleartext or half decrypted); level only in the team; None if invalid."""
    pid, check = struct.unpack_from("<I2xH", data)
    words = nds_words(data, check)
    if words is None:
        return None
    raw = struct.pack("<64H", *words)
    block = {k: raw[i * 32:(i + 1) * 32] for i, k in enumerate(NDS_ROWS[(pid >> 13 & 31) % 24])}
    a, b, c, d = block["A"], block["B"], block["C"], block["D"]
    kind = struct.unpack_from("<H", a)[0]
    if not 0 < kind <= NDS_MAX_KIND[gen]:
        return None
    ei = bool(struct.unpack_from("<I", b, 0x10)[0] >> 30 & 1)
    ei_location, location = struct.unpack_from("<HH", d, 0x16)
    if gen == 4:
        ei_location_new, location_new = struct.unpack_from("<HH", b, 0x1C)
        ei_location, location = ei_location_new or ei_location, location_new or location
    name = (g4_text if gen == 4 else g5_text)(c[:22])
    values = nds_battle_stats(data) if team else None
    level = values[0] if values else None
    return Catch(kind, name, location, ei, not ei and ei_location != 0, team, box, slot, day(d[0x13:0x16]), level)


G4_GAMES = {
    "ADA": (0xC100, 0xC100, 0x121E0, 0x14, 0x98, 4, 0xFF0),
    "APA": (0xC100, 0xC100, 0x121E0, 0x14, 0x98, 4, 0xFF0),
    "CPU": (0xCF2C, 0xCF2C, 0x121E4, 0x14, 0xA0, 4, 0xFF0),
    "IPK": (0xF628, 0xF700, 0x12310, 0x10, 0x98, 0, 0x1000),
    "IPG": (0xF628, 0xF700, 0x12310, 0x10, 0x98, 0, 0x1000),
}
G4_BOXES = 18
G5_COPY = {"IRB": 0x24000, "IRA": 0x24000, "IRE": 0x26000, "IRD": 0x26000}
G5_TEAM = (0x18E00, 0x534)
G5_BOXES = 24


def box_slots(start: int, gap: int, boxes: int) -> list[int]:
    """Positions of all box slots (30 per box, 136 bytes each)."""
    return [start + box * gap + slot * 136 for box in range(boxes) for slot in range(30)]


NDS_EMPTY = bytes(8) + struct.pack("<64H", *prng(0, [0] * 64))
NDS_TEAM_HEADER = re.compile(rb"\x06\x00\x00\x00[\x01-\x06]\x00\x00\x00")
NDS_FOREIGN = 10
NDS_BUFFER = {
    **{game: (4, team, box_slots(storage + box_start, gap, G4_BOXES))
       for game, (_, storage, _, _, team, box_start, gap) in G4_GAMES.items()},
    **{game: (5, G5_TEAM[0] + 8, box_slots(0x400, 0x1000, G5_BOXES)) for game in G5_COPY},
}


def nds_buffer(ram: bytes, gen: int, team: int, slots: list[int]) -> tuple[int, list[Catch | None]]:
    """Save buffer in main memory (arguments from NDS_BUFFER[game]): position of the team and catches of the boxes (invalid
    box slots as None); otherwise (0, [])."""
    size = 236 if gen == 4 else 220
    for hit in NDS_TEAM_HEADER.finditer(ram):
        start = hit.end()
        base = start - team
        if base < 0 or len(ram) < base + slots[-1] + 136:
            continue
        catches = [pk45(ram[start + i * size:start + (i + 1) * size], gen, True, None, i)
                  for i in range(ram[hit.start() + 4])]
        if None in catches:
            continue
        foreign = 0
        for i, gap in enumerate(slots):
            mon = ram[base + gap:base + gap + 136]
            if mon != NDS_EMPTY:
                catches.append(pk45(mon, gen, False, i // 30, i % 30))
                foreign += catches[-1] is None
                if foreign > NDS_FOREIGN:
                    break
        else:
            return start, catches
    return 0, []
