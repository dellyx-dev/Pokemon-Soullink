"""Tests of the battle reading from RAM."""
import struct

from conftest import plugin_module
from pokemon_helpers import G3_TEAM, G4, g3_team_set, g4_write, gmain_set, pk3, pk45
from soullink.pokemon_data import Opponent

read_battle_ram = plugin_module("opponent", "battle").read_battle_ram


def test_g3_battle_from_ram():
    """A generation 3 battle is read from RAM."""
    ewram, iwram = bytearray(0x40000), bytearray(0x8000)
    g3_team_set(ewram, 0x24284, G3_TEAM, 0x24029)
    opponent = [bytearray(pk3(232, "DONPHAN", level=2, pid=21)), bytearray(pk3(41, "ZUBAT", level=3, pid=22))]
    struct.pack_into("<H", opponent[1], 0x56, 12)
    g3_team_set(ewram, 0x2402C, [bytes(g) for g in opponent])
    gmain_set(iwram, 0x3040, True)
    blocks = {0x02000000: bytes(ewram), 0x03000000: bytes(iwram)}
    assert read_battle_ram(blocks, "BPRD") == [[Opponent(232, 2, 0), Opponent(41, 3, 12)]]
    gmain_set(iwram, 0x3040, False)
    assert read_battle_ram({0x02000000: bytes(ewram), 0x03000000: bytes(iwram)}, "BPRD") is None


def test_g3_sapphire_battle_flag_four_bytes_later():
    """Ruby/Sapphire read inBattle at gMain+0x43D, so the overworld value 0x0C at +0x439 is no battle."""
    iwram = bytearray(0x8000)
    gmain_set(iwram, 0x3040, False, "AXP")
    iwram[0x3040 + 0x439] = 0x0C | 0x02
    assert read_battle_ram({0x02000000: bytes(0x40000), 0x03000000: bytes(iwram)}, "AXPD") is None


def test_g3_active_opponent_from_battle_data():
    """The active generation 3 opponent comes from the battle data."""
    ewram, iwram = bytearray(0x40000), bytearray(0x8000)
    g3_team_set(ewram, 0x24284, G3_TEAM, 0x24029)
    opponent = [bytearray(pk3(232, "DONPHAN", level=2, pid=21)), bytearray(pk3(41, "ZUBAT", level=3, pid=22))]
    struct.pack_into("<H", opponent[0], 0x56, 16)
    struct.pack_into("<H", opponent[1], 0x56, 20)
    g3_team_set(ewram, 0x2402C, [bytes(g) for g in opponent])
    gmain_set(iwram, 0x3040, True)
    blocks = {0x02000000: bytes(ewram), 0x03000000: bytes(iwram)}
    assert read_battle_ram(blocks, "BPRD") == [[Opponent(232, 2, 16), Opponent(41, 3, 20)]]
    battle = 0x23BE4
    struct.pack_into("<I", ewram, battle + 0x48, 0x12345678)
    opponent_slot = battle + 0x58
    struct.pack_into("<H", ewram, opponent_slot, 41)
    ewram[opponent_slot + 0x21:opponent_slot + 0x23] = bytes([3, 2])
    struct.pack_into("<HBxH", ewram, opponent_slot + 0x28, 9, 3, 20)
    struct.pack_into("<I", ewram, opponent_slot + 0x48, 22)
    blocks = {0x02000000: bytes(ewram), 0x03000000: bytes(iwram)}
    assert read_battle_ram(blocks, "BPRD") == [[Opponent(232, 2, 16), Opponent(41, 3, 9, True, ("Poison", "Flying"))]]


def test_g4_active_opponent_next_to_own_battle_slot():
    """The active generation 4 opponent is found next to the own battle slot."""
    code = "CPUD"
    team = [pk45(38, 4, "Ninetales", location=16, level=7, kp=27)]
    buffer = g4_write(bytearray(0x40000), code, 0, team=team, boxes={})
    ram = bytearray(0x80000)
    ram[0x30000:0x70000] = buffer
    opponent = (struct.pack("<II", 6, 2) + pk45(231, 4, "Phanpy", pid=0x77, level=2, kp=16)
              + pk45(41, 4, "Zubat", pid=0x78, level=3, kp=11))
    ram[0x1000:0x1000 + len(opponent)] = opponent
    ram[0x2000:0x2000 + len(opponent)] = opponent
    assert read_battle_ram({0x02000000: bytes(ram)}, code) == [[Opponent(231, 2, 16), Opponent(41, 3, 11)]]
    struct.pack_into("<I", ram, 0x5000, 0x2A6F1C35)
    struct.pack_into("<I", ram, 0x50C0, 0x78)
    assert read_battle_ram({0x02000000: bytes(ram)}, code) == [[Opponent(231, 2, 16), Opponent(41, 3, 11, True)]]


def test_g4_active_opponent_from_battle_slots():
    """The active generation 4 opponent comes from the battle slots."""
    code = "IPGD"
    team = [pk45(426, 4, "Drifblim", level=8, kp=43)]
    buffer = g4_write(bytearray(0x40000), code, 0, team=team, boxes={})
    ram = bytearray(0x80000)
    ram[0x30000:0x70000] = buffer
    opponent = (struct.pack("<II", 6, 2) + pk45(325, 4, "Spoink", pid=0x77, level=2, kp=14)
              + pk45(82, 4, "Magneton", pid=0x78, level=4, kp=18))
    ram[0x1000:0x1000 + len(opponent)] = opponent
    ram[0x2000:0x2000 + len(opponent)] = opponent
    battle = 0x4000
    struct.pack_into("<H", ram, battle, 426)
    struct.pack_into("<I", ram, battle + 0x68, 0x2A6F1C35)
    struct.pack_into("<H", ram, battle + 0xC0, 82)
    ram[battle + 0xC0 + 0x24:battle + 0xC0 + 0x26] = bytes([13, 8])
    ram[battle + 0xC0 + 0x34] = 4
    struct.pack_into("<iI", ram, battle + 0xC0 + 0x4C, 0, 18)
    struct.pack_into("<I", ram, battle + 0xC0 + 0x68, 0x78)
    struct.pack_into("<I", ram, battle + 0x200, 0x2A6F1C35)
    struct.pack_into("<I", ram, battle + 0x240, 0x77)
    assert read_battle_ram({0x02000000: bytes(ram)}, code) == [
        [Opponent(325, 2, 14), Opponent(82, 4, 0, True, ("Electric", "Steel"))]]


def test_g4_fighting_type_from_battle_slots():
    """Type id 1 in the battle slot is Fighting (Croagunk in SoulSilver: Poison/Fighting)."""
    code = "IPGD"
    buffer = g4_write(bytearray(0x40000), code, 0, team=[pk45(426, 4, "Drifblim", level=8, kp=43)], boxes={})
    ram = bytearray(0x80000)
    ram[0x30000:0x70000] = buffer
    opponent = struct.pack("<II", 6, 1) + pk45(453, 4, "Croagunk", pid=0x77, level=5, kp=20)
    ram[0x1000:0x1000 + len(opponent)] = opponent
    ram[0x2000:0x2000 + len(opponent)] = opponent
    battle = 0x4000
    struct.pack_into("<I", ram, battle + 0x68, 0x2A6F1C35)
    struct.pack_into("<H", ram, battle + 0xC0, 453)
    ram[battle + 0xC0 + 0x24:battle + 0xC0 + 0x26] = bytes([3, 1])
    ram[battle + 0xC0 + 0x34] = 5
    struct.pack_into("<iI", ram, battle + 0xC0 + 0x4C, 20, 20)
    struct.pack_into("<I", ram, battle + 0xC0 + 0x68, 0x77)
    assert read_battle_ram({0x02000000: bytes(ram)}, code) == [[Opponent(453, 5, 20, True, ("Poison", "Fighting"))]]


def test_g4_double_battle_opponents_in_ram():
    """Both opponents of a generation 4 double battle are found in RAM."""
    code = "CPUD"
    team = [pk45(38, 4, "Ninetales", location=16, level=7, kp=27)]
    buffer = g4_write(bytearray(0x40000), code, 0, team=team, boxes={})
    ram = bytearray(0x80000)
    ram[0x30000:0x70000] = buffer
    opponent = struct.pack("<II", 6, 1) + pk45(231, 4, "Phanpy", pid=0x77, level=2, kp=16)
    ram[0x1000:0x1000 + len(opponent)] = opponent
    assert read_battle_ram({0x02000000: bytes(ram)}, code) is None
    ram[0x2000:0x2000 + len(opponent)] = opponent
    own_copy = buffer[G4[code][4] - 8:G4[code][4] + 236]
    ram[0x3000:0x3000 + len(own_copy)] = own_copy
    assert read_battle_ram({0x02000000: bytes(ram)}, code) == [[Opponent(231, 2, 16)]]


def test_battle_without_data():
    """Without battle data nothing is reported."""
    assert read_battle_ram({}, "BPRD") is None
    assert read_battle_ram({0x02000000: bytes(0x1000)}, "CPUD") is None
    assert read_battle_ram({}, "XXXX") is None
