"""Opponents in a running battle, live from RAM: the opposing teams and who is fighting (with HP and types)."""
from __future__ import annotations

import struct

from soullink.pokemon_data import (G3_RAM_TEAM, NDS_MAX_KIND, NDS_BUFFER, NDS_TEAM_HEADER, Opponent, g3_battle_flag,
                                    g3_gmain, g3_ram_slots, g3_ram_team, nds_battle_stats, nds_buffer, pk3, pk45)


def read_battle_ram(blocks: dict[int, bytes], game_code: str) -> list[list[Opponent]] | None:
    """Opposing teams if a battle is running (else None), one list per team; generation 3 uses the "inBattle" bit in gMain
    (IWRAM, found structurally)."""
    game = game_code[:3]
    try:
        if game in G3_RAM_TEAM:
            return _g3_battle(blocks, game)
        if game in NDS_BUFFER:
            return _nds_battle(bytes(blocks.get(0x02000000, b"")), *NDS_BUFFER[game])
    except (struct.error, IndexError, ValueError):
        pass
    return None


_G3_BATTLE_MON = 0x58
_G3_BATTLE_TYPES = ["Normal", "Battle", "Flying", "Poison", "Ground", "Rock", "Bug", "Ghost", "Steel", None, "Fire",
                  "Water", "Grass", "Electric", "Psychic", "Ice", "Dragon", "Dark"]


def _g3_in_battle(blocks: dict[int, bytes], own: set[int], opponent: list[int]) -> dict[int, tuple]:
    """Opponents that are fighting right now: {personality: (level, HP, types)} from gBattleMons."""
    active = {}
    for data in (bytes(b) for b in blocks.values()):
        for pid in opponent:
            place = data.find(struct.pack("<I", pid))
            while place >= 0:
                base = place - 0x48
                for slot in (1, 3):
                    first = base - slot * _G3_BATTLE_MON
                    if place % 4 or first < 0 or struct.unpack_from("<I", data, first + 0x48)[0] not in own:
                        continue
                    kind = struct.unpack_from("<H", data, base)[0]
                    kp, level, max_kp = struct.unpack_from("<HBxH", data, base + 0x28)
                    if kind and 1 <= level <= 100 and kp <= max_kp:
                        types = (_G3_BATTLE_TYPES[n] if n < len(_G3_BATTLE_TYPES) else None
                                 for n in data[base + 0x21:base + 0x23])
                        active[pid] = (level, kp, tuple(dict.fromkeys(t for t in types if t)))
                place = data.find(struct.pack("<I", pid), place + 1)
    return active


def _g3_battle(blocks: dict[int, bytes], game: str) -> list[list[Opponent]] | None:
    """Reads the opposing teams of a generation 3 game."""
    iw = bytes(blocks.get(0x03000000, b""))
    gmain = g3_gmain(iw)
    if gmain is None or not iw[gmain + g3_battle_flag(game)] & 0x02:
        return None
    opponent_gap = G3_RAM_TEAM[game][0]
    for data in (bytes(b) for b in blocks.values()):
        valid, empty = g3_ram_slots(data)
        start = g3_ram_team(data, valid, empty, game)
        if start is None:
            continue
        own = {struct.unpack_from("<I", data, start + slot * 100)[0] for slot in range(6)} - {0}
        team = []
        for slot in range(6):
            mon = data[start + opponent_gap + slot * 100:start + opponent_gap + (slot + 1) * 100]
            catch = pk3(mon, True, None, slot) if any(mon[:80]) else None
            if catch is not None:
                team.append((struct.unpack_from("<I", mon)[0], Opponent(catch.kind, mon[0x54],
                                                                      struct.unpack_from("<H", mon, 0x56)[0])))
        in_battle = _g3_in_battle(blocks, own, [pid for pid, _ in team])
        opponent = [Opponent(g.kind, *in_battle[pid][:2], True, in_battle[pid][2]) if pid in in_battle else g
                  for pid, g in team]
        return [opponent] if opponent else None
    return None


def _nds_opponent(mon: bytes, gen: int) -> Opponent | None:
    """Opponent record from a decrypted team Pokemon of generation 4/5."""
    catch = pk45(mon, gen, True, None, 0)
    values = nds_battle_stats(mon)
    if catch is None or values is None:
        return None
    return Opponent(catch.kind, *values)


def _nds_battle(ram: bytes, gen: int, team: int, slots: list[int]) -> list[list[Opponent]] | None:
    """Reads the opposing teams of an NDS game."""
    size = 236 if gen == 4 else 220
    teams: dict[tuple[int, ...], list[int]] = {}
    for hit in NDS_TEAM_HEADER.finditer(ram):
        start, count = hit.end(), ram[hit.start() + 4]
        mons = [ram[start + i * size:start + (i + 1) * size] for i in range(count)]
        if len(mons[-1]) == size and all(pk45(m, gen, True, None, 0) for m in mons):
            teams.setdefault(tuple(struct.unpack_from("<I", m)[0] for m in mons), []).append(start)
    own = _nds_own_pids(ram, gen, team, slots)
    if not own:
        return None
    live = _nds_battle_slots(ram, own, {pid for pids in teams for pid in pids} - own) if gen == 4 else {}
    in_battle = set(live) or _nds_in_battle(ram, teams, size, own)
    opponent = []
    for pids, place in teams.items():
        if len(place) >= 2 and not set(pids) & own:
            mons = [(pid, _nds_opponent(ram[place[0] + i * size:place[0] + (i + 1) * size], gen))
                    for i, pid in enumerate(pids)]
            opponent.append([Opponent(g.kind, *live[pid][:2], True, live[pid][2]) if pid in live
                           else Opponent(g.kind, g.level, g.kp, pid in in_battle) for pid, g in mons if g])
    return opponent or None


_NDS_BATTLE_MON = 0xC0
_NDS_BATTLE_MON_PID = 0x68


def _nds_battle_slots(ram: bytes, own: set[int], opponent: set[int]) -> dict[int, tuple]:
    """Opponents that are fighting right now: {personality: (level, HP, types)}, found via slot 0; slot 3 only counts if
    slot 2 also holds an opponent."""
    def word(place: int) -> int:
        """Reads a 32-bit word from RAM."""
        return struct.unpack_from("<I", ram, place)[0]

    active = {}
    for pid in own:
        place = ram.find(struct.pack("<I", pid))
        while place >= 0:
            base = place - _NDS_BATTLE_MON_PID
            if place % 4 == 0 and base >= 0 and base + 4 * _NDS_BATTLE_MON <= len(ram):
                for slot in (1, 3):
                    s = base + slot * _NDS_BATTLE_MON
                    if word(s + _NDS_BATTLE_MON_PID) not in opponent or \
                            slot == 3 and word(base + 2 * _NDS_BATTLE_MON + _NDS_BATTLE_MON_PID) not in own:
                        continue
                    kind, level = struct.unpack_from("<H", ram, s)[0], ram[s + 0x34]
                    kp, max_kp = struct.unpack_from("<iI", ram, s + 0x4C)
                    if 0 < kind <= NDS_MAX_KIND[4] and 1 <= level <= 100 and 0 <= kp <= max_kp < 1000:
                        types = (_G3_BATTLE_TYPES[n] if n < len(_G3_BATTLE_TYPES) else None for n in ram[s + 0x24:s + 0x26])
                        active[word(s + _NDS_BATTLE_MON_PID)] = (level, kp, tuple(dict.fromkeys(t for t in types if t)))
            place = ram.find(struct.pack("<I", pid), place + 1)
    return active


def _nds_in_battle(ram: bytes, teams: dict, size: int, own: set[int]) -> set[int]:
    """Personalities of the opponents fighting right now: outside the team copies the battle Pokemon sit right behind the
    active own Pokemon."""
    ranges = [(s, s + size * len(pids)) for pids, place in teams.items() for s in place]

    def outside(pid: int) -> list[int]:
        """Finds occurrences of a personality value outside the team copies."""
        finds, place = [], ram.find(struct.pack("<I", pid))
        while place >= 0:
            if place % 4 == 0 and not any(a <= place < e for a, e in ranges):
                finds.append(place)
            place = ram.find(struct.pack("<I", pid), place + 1)
        return finds

    slots = [s for pid in own for s in outside(pid)]
    opponent = {pid for pids in teams for pid in pids} - own
    return {pid for pid in opponent if any(abs(s - p) <= 0x400 for s in outside(pid) for p in slots)}


def _nds_own_pids(ram: bytes, gen: int, team: int, slots: list[int]) -> set[int]:
    """PIDs of the own team: the team in the save buffer (the same hit as for the catches)."""
    start, catches = nds_buffer(ram, gen, team, slots)
    size = 236 if gen == 4 else 220
    return {struct.unpack_from("<I", ram, start + i * size)[0] for i, f in enumerate(catches) if f and f.box is None}
