"""Catches from the save (raw battery SRAM) or live from RAM (team and boxes), plus the badges. The records themselves are
read by soullink/pokemon_data.py."""
from __future__ import annotations

import struct

import numpy as np

from soullink.pokemon_data import (G3_DATA, G3_RAM_TEAM, G4_BOXES, G4_GAMES, G5_BOXES, G5_COPY, G5_TEAM, NDS_BUFFER,
                                    Catch, crc16, g3_block1, g3_checksum, g3_ram_slots, g3_ram_team, nds_buffer, pk3,
                                    pk45)


def read_catches(sav: bytes, game_code: str) -> list[Catch]:
    """Team first, then the boxes; empty or invalid slots are left out and a broken save yields []."""
    reader = _READER.get(game_code[:3])
    if reader is None:
        return []
    try:
        return [f for f in reader(bytes(sav), game_code[:3]) if f is not None]
    except (struct.error, IndexError, ValueError):
        return []


G3_TEAM_SIZE = {"AXV": 0x234, "AXP": 0x234, "BPE": 0x234, "BPR": 0x34, "BPG": 0x34}
_G3_SECTORS = 14
_G3_SIGNATURE = 0x08012025
G3_BOXES = 14


def g3_sections(sav: bytes) -> list[bytes] | None:
    """Sections 0-13 from the slot with the highest save counter in which all 14 are valid (as the game does)."""
    best, best_number = None, -1
    for slot in range(2):
        sections, number = [None] * _G3_SECTORS, -1
        for i in range(_G3_SECTORS):
            start = (slot * _G3_SECTORS + i) * 0x1000
            sector = sav[start:start + 0x1000]
            nr, check, signature, counter = struct.unpack_from("<HHII", sector, 0xFF4)
            if signature == _G3_SIGNATURE and nr < _G3_SECTORS and g3_checksum(sector) == check:
                sections[nr], number = sector[:G3_DATA], counter
        if None not in sections and number > best_number:
            best, best_number = sections, number
    return best


def _g3_read(sav: bytes, game: str) -> list[Catch | None]:
    """Reads the catches of a generation 3 save."""
    sections = g3_sections(sav)
    if sections is None:
        return []
    team, number = sections[1], G3_TEAM_SIZE[game]
    catches = []
    for slot in range(min(team[number], 6)):
        mon = team[number + 4 + slot * 100:number + 4 + (slot + 1) * 100]
        catches.append(pk3(mon, True, None, slot, mon[0x54]))
    pc = b"".join(sections[5:])
    for box in range(G3_BOXES):
        for slot in range(30):
            start = 4 + (box * 30 + slot) * 80
            catches.append(pk3(pc[start:start + 80], False, box, slot))
    return catches


_G4_HALF = 0x40000


def g4_block(sav: bytes, start: int, size: int, foot: int) -> bytes | None:
    """Valid copy of the block, the one with the higher counters of both halves."""
    best, best_counter = None, None
    for half in (0, _G4_HALF):
        block = sav[half + start:half + start + size]
        if len(block) < size or crc16(block[:-foot]) != struct.unpack_from("<H", block, size - 2)[0]:
            continue
        counter = struct.unpack_from("<II", block, size - foot)
        if best_counter is None or counter > best_counter:
            best, best_counter = block, counter
    return best


def _g4_read(sav: bytes, game: str) -> list[Catch | None]:
    """Reads the catches of a generation 4 save."""
    general_size, storage_start, storage_size, foot, team, box_start, box_gap = G4_GAMES[game]
    general = g4_block(sav, 0, general_size, foot)
    storage = g4_block(sav, storage_start, storage_size, foot)
    catches = []
    if general is not None:
        for slot in range(min(general[team - 4], 6)):
            catches.append(pk45(general[team + slot * 236:team + (slot + 1) * 236], 4, True, None, slot))
    if storage is not None:
        for box in range(G4_BOXES):
            for slot in range(30):
                start = box_start + box * box_gap + slot * 136
                catches.append(pk45(storage[start:start + 136], 4, False, box, slot))
    return catches


def g5_block(sav: bytes, start: int, length: int, copy: int) -> bytes | None:
    """Block with a valid checksum: the original or the backup copy."""
    for start in (start, start + copy):
        block = sav[start:start + length + 4]
        if len(block) == length + 4 and crc16(block[:length]) == struct.unpack_from("<H", block, length + 2)[0]:
            return block[:length]
    return None


def _g5_read(sav: bytes, game: str) -> list[Catch | None]:
    """Reads the catches of a generation 5 save."""
    copy = G5_COPY[game]
    catches = []
    team = g5_block(sav, *G5_TEAM, copy)
    if team is not None:
        for slot in range(min(team[4], 6)):
            catches.append(pk45(team[8 + slot * 220:8 + (slot + 1) * 220], 5, True, None, slot))
    for box in range(G5_BOXES):
        data = g5_block(sav, 0x400 + box * 0x1000, 30 * 136, copy)
        if data is None:
            continue
        for slot in range(30):
            catches.append(pk45(data[slot * 136:(slot + 1) * 136], 5, False, box, slot))
    return catches


_READER = {**dict.fromkeys(G3_TEAM_SIZE, _g3_read), **dict.fromkeys(G4_GAMES, _g4_read),
          **dict.fromkeys(G5_COPY, _g5_read)}


def read_catches_ram(blocks: dict[int, bytes], game_code: str) -> list[Catch]:
    """Like read_catches but from the running game; blocks = {start address: bytes}: GBA 0x02000000 (EWRAM) and 0x03000000
    (IWRAM), NDS 0x02000000 (main memory)."""
    game = game_code[:3]
    try:
        if game in G3_RAM_TEAM:
            catches = _g3_ram([bytes(b) for b in blocks.values()], game)
        elif game in NDS_BUFFER:
            catches = nds_buffer(bytes(blocks.get(0x02000000, b"")), *NDS_BUFFER[game])[1]
        else:
            return []
        return [f for f in catches if f is not None]
    except (struct.error, IndexError, ValueError):
        return []


_G3_PC_SLOTS = G3_BOXES * 30


def _g3_ram_pc(data: bytes, valid: np.ndarray, empty: np.ndarray) -> int | None:
    """Finds PokemonStorage in RAM: 1 byte current box (+3), 420 slots of 80 bytes (valid or empty), then 14 box names."""
    ok = valid | empty
    for rest in range(20):
        chain = np.concatenate(([0], ok[rest::20].astype(np.int8), [0]))
        switch = np.diff(chain)
        for start, end in zip(np.flatnonzero(switch == 1), np.flatnonzero(switch == -1)):
            if end - start < _G3_PC_SLOTS or not valid[rest::20][end - _G3_PC_SLOTS:end].any():
                continue
            names = (rest + int(end) * 20) * 4
            base = names - 4 - _G3_PC_SLOTS * 80
            names_ok = all(0xFF in data[names + i * 9:names + (i + 1) * 9] for i in range(G3_BOXES))
            if base >= 0 and data[base] < G3_BOXES and names_ok:
                return base
    return None


def _g3_ram(blocks: list[bytes], game: str) -> list[Catch | None]:
    """Reads team and boxes of a generation 3 game from RAM."""
    team, pc = [], []
    for data in blocks:
        valid, empty = g3_ram_slots(data)
        start = g3_ram_team(data, valid, empty, game)
        if start is not None and not team:
            for slot in range(6):
                mon = data[start + slot * 100:start + (slot + 1) * 100]
                team.append(pk3(mon, True, None, slot, mon[0x54]) if any(mon[:80]) else None)
        base = _g3_ram_pc(data, valid, empty)
        if base is not None and not pc:
            pc = [pk3(data[base + 4 + i * 80:base + 4 + (i + 1) * 80], False, i // 30, i % 30)
                  for i in range(_G3_PC_SLOTS)]
    return team + pc


_G3_BADGE = {"BPR": (0xEE0, 0x820, 0x828), "BPG": (0xEE0, 0x820, 0x828), "BPE": (0x1270, 0x867, 0x860),
             "AXV": (0x1220, 0x807, 0x800), "AXP": (0x1220, 0x807, 0x800)}
_NDS_BADGE = {"ADA": [0x7E], "APA": [0x7E], "CPU": [0x82], "IPK": [0x7E, 0x83], "IPG": [0x7E, 0x83],
              "IRB": [0x21204], "IRA": [0x21204], "IRE": [0x21104], "IRD": [0x21104]}


def read_badge_ram(blocks: dict[int, bytes], game_code: str) -> int | None:
    """Number of badges of the player from the running game (HGSS: Johto and Kanto together); None if not found."""
    game = game_code[:3]
    try:
        if game in _G3_BADGE:
            return _g3_badge(blocks, game)
        if game in _NDS_BADGE:
            ram = bytes(blocks.get(0x02000000, b""))
            gen, team, slots = NDS_BUFFER[game]
            start, catches = nds_buffer(ram, gen, team, slots)
            if not catches:
                return None
            return sum(ram[start - team + place].bit_count() for place in _NDS_BADGE[game])
    except (struct.error, IndexError, ValueError):
        pass
    return None


def _g3_badge(blocks: dict[int, bytes], game: str) -> int | None:
    """Badge count of a generation 3 game from RAM."""
    ew = bytes(blocks.get(0x02000000, b""))
    block1 = g3_block1(blocks, game)
    if block1 is None:
        return None
    flags, badge, pokemon = _G3_BADGE[game]
    flags += block1 - 0x02000000
    if not 0 <= flags < len(ew) - 0x120:
        return None
    bit = lambda n: ew[flags + n // 8] >> (n % 8) & 1  # noqa: E731
    if not bit(pokemon):
        return None
    return sum(bit(badge + k) for k in range(8))
