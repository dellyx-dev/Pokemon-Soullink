"""Tests of soullink.world: position reading, movement and party icons."""
import io
import math
import struct

import pytest

from pokemon_helpers import G3_PC, g3_pc_set, g4_write, gmain_set, pk3, pk45
from soullink import world
from world_helpers import gen5_icon_rom, icon_rom, nds_icon_rom  # noqa: F401

EI, ICON_COUNT, NDS_EI, NDS_RAM, SEARCH_MENU = world.EI, world.ICON_COUNT, world.NDS_EI, world.NDS_RAM, world.SEARCH_MENU
Movement, Gen4Reader, Gen5Reader, NdsIcons, Location = world.Movement, world.Gen4Reader, world.Gen5Reader, world.NdsIcons, world.Location
PokemonIcons, WorldReader, _first_kind, family = world.PokemonIcons, world.WorldReader, world._first_kind, world.family
shared, projection, world_reader, pack, unpack = world.shared, world.projection, world.world_reader, world.pack, \
    world.unpack


def _read(blocks):
    """Memory reader over RAM blocks."""
    def read(address, length):
        """Bytes at an address."""
        for start, data in blocks.items():
            if start <= address and address + length <= start + len(data):
                return bytes(data[address - start:address - start + length])
        return b""
    return read


def test_firered_position_through_the_block_pointer():
    """FireRed's position is found through the block pointer."""
    ewram, iwram = bytearray(0x40000), bytearray(0x8000)
    g3_pc_set(ewram, 0x29384, G3_PC)
    struct.pack_into("<III", iwram, 0x5008, 0x02025590, 0x020245EC, 0x02029384)
    gmain_set(iwram, 0x3040, False)
    struct.pack_into("<hhbb", ewram, 0x25590, 12, 7, 3, 19)
    blocks = {0x02000000: ewram, 0x03000000: iwram}
    reader = WorldReader("BPRD")
    assert reader.step(lambda: blocks, _read(blocks)) == Location(3, 19, 12, 7, 0x08011085 ^ 0x08011679, False)
    struct.pack_into("<I", iwram, 0x5008, 0x025600 + 0x02000000)
    struct.pack_into("<hhbb", ewram, 0x25600, 4, 9, 3, 0)
    iwram[0x3040 + 0x439] = 0x02
    assert reader.read(_read(blocks)) == Location(3, 0, 4, 9, 0x08011085 ^ 0x08011679, True)


def test_ruby_fixed_block_and_title_screen():
    """Ruby uses a fixed block and the title screen yields no position."""
    ewram, iwram = bytearray(0x40000), bytearray(0x8000)
    gmain_set(iwram, 0x3040, False)
    blocks = {0x02000000: ewram, 0x03000000: iwram}
    reader = WorldReader("AXVD")
    assert reader.step(lambda: blocks, _read(blocks)) is None
    struct.pack_into("<hhbb", ewram, 0x25734, 5, 6, 0, 9)
    assert reader.read(_read(blocks)).x == 5


def test_sapphire_battle_flag_four_bytes_later():
    """Ruby/Sapphire keep inBattle at gMain+0x43D; the byte at +0x439 (0x0C in the real game) does not count."""
    ewram, iwram = bytearray(0x40000), bytearray(0x8000)
    gmain_set(iwram, 0x3040, False, "AXP")
    iwram[0x3040 + 0x439] = 0x0C | 0x02
    struct.pack_into("<hhbb", ewram, 0x25734, 4, 16, 0, 16)
    blocks = {0x02000000: ewram, 0x03000000: iwram}
    reader = WorldReader("AXPD")
    assert reader.step(lambda: blocks, _read(blocks)).battle is False
    gmain_set(iwram, 0x3040, True, "AXP")
    assert reader.read(_read(blocks)).battle is True


def test_without_gmain_the_search_is_repeated_later():
    """Without gMain the search is repeated later."""
    reader = WorldReader("BPED")
    calls = []

    def dump():
        """Returns an empty dump and counts the calls."""
        calls.append(1)
        return {0x02000000: bytes(0x40000), 0x03000000: bytes(0x8000)}

    for _ in range(130):
        assert reader.step(dump, _read({})) is None
    assert len(calls) == 2


def test_shared_maps():
    """Maps are mapped to a shared numbering."""
    assert family("AXVD") == "rs" and family("BPED") == "emerald" and family("BPGD") == "frlg"
    assert family("AMKE") is None and family("") is None
    assert shared("emerald", 0, 3) == (("hoenn", 0, 3), 0, 0)
    assert shared("rs", 0, 3) == (("hoenn", 0, 3), 0, 0)
    assert shared("rs", 5, 3)[0] == ("hoenn", 5, 4)
    assert shared("rs", 13, 4) == (("hoenn", 13, 4), 8, 0)
    assert shared("rs", 5, 1)[0] == ("rs", 5, 1)
    assert shared("frlg", 3, 19) == (("kanto", 3, 19), 0, 0)


def test_movement_smooths_steps_and_learns_overworld():
    """Movement smooths steps and learns the overworld callbacks."""
    b = Movement()
    b.new(Location(0, 3, 10, 10, 0x0800A, False), 0.0)
    assert b.position(0.0) == (10.0, 10.0) and b.overworld is None
    b.new(Location(0, 3, 11, 10, 0x0800A, False), 1.0)
    assert b.overworld == 0x0800A and b.in_overworld
    assert b.position(1.0) == (10.0, 10.0)
    assert b.position(1.0 + Movement.STEP_MAX / 2) == pytest.approx((10.5, 10.0))
    assert b.position(2.0) == (11.0, 10.0)
    b.new(Location(0, 3, 12, 10, 0x0800A, False), 2.0 + 8 / 59.73)
    b.new(Location(0, 3, 13, 10, 0x0800A, False), 2.0 + 16 / 59.73)
    assert b._duration == pytest.approx(8 / 59.73)
    b.new(Location(1, 0, 4, 4, 0x0800A, False), 3.0)
    assert b.position(3.0) == (4.0, 4.0)
    b.new(Location(1, 0, 4, 4, 0x0800B, False), 3.5)
    assert not b.in_overworld
    b.new(Location(1, 0, 4, 4, 0x0800A, True), 4.0)
    assert not b.in_overworld
    new = Movement()
    new.new(Location(3, 0, 10, 7, 0x0800A, False, vblank=False), 0.0)
    assert not new.in_overworld


def test_first_kind_from_the_team():
    """The first Pokemon of the team is determined."""
    assert _first_kind(pk3(25, "PIKA", level=5)) == 25
    assert _first_kind(pk3(25, ei=True)) == EI
    assert _first_kind(bytes(100)) == 0


def test_party_icons_from_the_rom(icon_rom):
    """Party icons are read from the ROM."""
    icons = PokemonIcons(icon_rom)
    assert icons.there
    assert icons.image(25, 0).get_at((5, 5)) == (255, 0, 0, 255)
    assert icons.image(25, 3).get_at((31, 31)) == (0, 0, 255, 255)
    assert icons.image(0, 0) is None and icons.image(ICON_COUNT, 0) is None
    assert not PokemonIcons(bytes(0x4000)).there


def test_icons_load_gba_nds_and_read_error(tmp_path, icon_rom, nds_icon_rom, gen5_icon_rom):
    """Icons load for GBA and NDS and read errors are handled."""
    for name, data in (("rom.gba", icon_rom), ("hgss.nds", nds_icon_rom), ("bw2.nds", gen5_icon_rom)):
        (tmp_path / name).write_bytes(data)
    gba = world.icons_load(tmp_path / "rom.gba", "emerald")
    assert isinstance(gba, PokemonIcons) and gba.image(25, 0).get_at((5, 5)) == (255, 0, 0, 255)
    hgss = world.icons_load(str(tmp_path / "hgss.nds"), "hgss")
    assert isinstance(hgss, NdsIcons) and hgss.image(25, 0).get_at((3, 3)) == (0, 0, 255, 255)
    bw2 = world.icons_load(tmp_path / "bw2.nds", "bw2")
    assert isinstance(bw2, NdsIcons) and bw2.image(1, 0).get_at((3, 3)) == (0, 255, 0, 255)
    assert world.icons_load(tmp_path / "missing.gba", "frlg") is None
    assert world.icons_load(tmp_path / "missing.nds", "pt") is None
    assert not world.icons_load(tmp_path / "rom.gba", "hgss").there


def test_fresh_save_without_boxes_and_the_help_menu():
    """A fresh save without boxes and the help menu are handled."""
    ewram, iwram = bytearray(0x40000), bytearray(0x8000)
    struct.pack_into("<III", iwram, 0x4F58, 0x02025590, 0x020245EC, 0x02029384)
    struct.pack_into("<7I", iwram, 0x3040, 0x08056555, 0x080565D5, 0x0805676D, 0, 0, 0, 0x0800B719)
    struct.pack_into("<HH", iwram, 0x3040 + 0x1C, 4, 0)
    struct.pack_into("<hhbb", ewram, 0x25590, 10, 7, 3, 0)
    blocks = {0x02000000: ewram, 0x03000000: iwram}
    reader = WorldReader("BPGD")
    assert reader.step(lambda: blocks, _read(blocks)) == Location(3, 0, 10, 7, 0x080565D5, False, False)
    struct.pack_into("<I", iwram, 0x3040 + 12, 0x08056A35)
    assert reader.read(_read(blocks)).callback == 0x080565D5 ^ 0x08056A35


def test_position_as_bytes_in_the_plugin_slot():
    """The position travels as bytes in the plugin slot."""
    from soullink.core.memory import SLOT_SIZE, SharedMemory

    owner = SharedMemory()
    worker = SharedMemory(owner.name)
    camera = (466.25, 34.5, 286.0, 466.25, 3.0, 258.5, 0.125)
    locations = [Location(0, 9, 11, 14, 0x0800A, False, False), Location(3, 0, 4, 9, 0x08011085 ^ 0x08011679, True, True, 412),
            Location(73, 401, 466.25, 258.5, 0, False, True, 25, 3.0, camera),
            Location(0, 445, 46.5, 45.5, 0, False, False, NDS_EI, 2.0, camera)]
    try:
        for location in locations:
            data = pack(location)
            assert len(data) <= SLOT_SIZE
            worker.slot_write(0, data)
            assert unpack(owner.slot_read(0)[1]) == location
        assert pack(None) == b"" and unpack(b"") is None and unpack(None) is None
        assert unpack(b"\x09" + pack(locations[0])[1:]) is None
        assert pack(Location(0, 70000, 1, 1, 0, False)) == b""
        nan = float("nan")
        for broken in (Location(0, 9, -1, 14, 0, False), Location(0, 9, nan, 14, 0, False), Location(0, 9, 3, nan, 0, False),
                       Location(0, 445, 46.5, 45.5, 0, False, True, 25, nan, camera),
                       Location(0, 445, 46.5, 45.5, 0, False, True, 25, 2.0, (nan,) + camera[1:])):
            assert unpack(pack(broken)) is None, broken
    finally:
        worker.close()
        owner.close()
        owner.release()


FIELD, PROCESSES, CAMERA_PLACE, HEADERS, BUFFER = 0x2A0208, 0x2A0350, 0x348384, 0x0F6B94, 0x27C000
_TILT, _OPENING = (0x10000 - 0xDD62) * 2 * math.pi / 0x10000, 0x05C1 * 2 * math.pi / 0x10000


def _camera(x, y, z):
    """The usual HGSS camera above (x, y, z): (eye, target, tan of half the opening) in tiles."""
    gap = 0x29AEC1 / 65536
    return (x, y + gap * math.sin(_TILT), z + gap * math.cos(_TILT), x, y, z, math.tan(_OPENING))


CAMERA = _camera(466.5, 3.0, 258.5)


def _g4_ram(x=466, z=258, map_=73, overworld=True, location_field=0x20, music=0x0C, matrix=4, code="IPGD",
            camera_field=0x24):
    """RAM as in German SoulSilver (location field 0x1C, music 0x0A, matrix 2 as in Platinum; camera field 0x20 as in
    Diamond): save buffer with team (Pikachu) and location, and a FieldSystem."""
    ram = bytearray(0x400000)
    buffer = g4_write(bytearray(0x40000), code, 0, team=[pk45(25, 4, "Pikachu", level=5)], boxes={})
    ram[BUFFER:BUFFER + 0x40000] = buffer
    location = BUFFER + 0x1234
    struct.pack_into("<5i", ram, location, map_, -1, x, z, 0)
    struct.pack_into("<I", ram, FIELD, NDS_RAM + PROCESSES)
    struct.pack_into("<I", ram, FIELD + location_field, NDS_RAM + location)
    struct.pack_into("<I", ram, FIELD + camera_field, NDS_RAM + CAMERA_PLACE)
    struct.pack_into("<II", ram, PROCESSES, 0x022A6B20 if overworld else 0, 0 if overworld else 0x022A6AC8)
    eye = _camera(x + 0.5, 3.0, z + 0.5)[:3]
    struct.pack_into("<3i", ram, CAMERA_PLACE + 0x14, *(round(v * 65536) for v in eye))
    struct.pack_into("<3i", ram, CAMERA_PLACE + 0x20, (2 * x + 1) * 32768, 3 * 65536, (2 * z + 1) * 32768)
    struct.pack_into("<i", ram, CAMERA_PLACE + 0x38, 0x29AEC1)
    struct.pack_into("<H", ram, CAMERA_PLACE + 0x3C, 0xDD62)
    struct.pack_into("<H", ram, CAMERA_PLACE + 0x46, 0x05C1)
    for k in range(540):
        struct.pack_into("<HH", ram, HEADERS + k * 24 + music, 1000 + k % 50, 1000 + k % 50)
    struct.pack_into("<H", ram, HEADERS + 69 * 24 + matrix, 73)
    return ram


def _read_from(ram):
    """Memory reader over a RAM image."""
    def read(address, length):
        """Bytes at an address."""
        o = address - NDS_RAM
        return bytes(ram[o:o + length]) if 0 <= o and o + length <= len(ram) else b""
    return read


def test_families_and_reader():
    """Game families select the matching reader."""
    assert family("IPGD") == family("IPKF") == "hgss" and family("CPUD") == "pt" and family("ADAD") == "dp"
    assert family("IRBD") == "bw" and family("IREO") == "bw2"
    assert isinstance(world_reader("IPKD"), Gen4Reader) and isinstance(world_reader("APAE"), Gen4Reader)
    assert isinstance(world_reader("IRAD"), Gen5Reader) and isinstance(world_reader("BPRD"), WorldReader)


def test_gen4_position_camera_and_overworld():
    """Generation 4 yields position, camera and overworld state."""
    ram = _g4_ram()
    reader = Gen4Reader("IPGD")
    assert reader.search({NDS_RAM: bytes(ram)})
    location = reader.read(_read_from(ram))
    assert (location.group, location.number, location.x, location.y, location.height, location.vblank, location.kind) == (0, 73, 466.5, 258.5, 3.0, True, 25)
    assert location.camera == pytest.approx(CAMERA, abs=1e-3)
    struct.pack_into("<II", ram, PROCESSES, 0, 0x022A6AC8)
    struct.pack_into("<i", ram, BUFFER + 0x1234 + 8, 470)
    location = reader.read(_read_from(ram))
    assert (location.x, location.y, location.height, location.vblank) == (470.5, 258.5, 3.0, False)
    assert location.camera == pytest.approx(CAMERA, abs=1e-3)
    struct.pack_into("<i", ram, BUFFER + 0x1234, 69)
    assert reader.read(_read_from(ram)).group == 73
    struct.pack_into("<I", ram, FIELD + 0x20, 0)
    assert reader.read(_read_from(ram)) is None and not reader.found


def test_gen4_platinum_location_at_another_place():
    """Platinum's location is found at another place."""
    ram = _g4_ram(x=126, z=849, map_=342, location_field=0x1C, music=0x0A, matrix=2, code="CPUD")
    reader = Gen4Reader("CPUD")
    assert reader.search({NDS_RAM: bytes(ram)})
    location = reader.read(_read_from(ram))
    assert (location.group, location.number, location.x, location.y, location.vblank, location.kind) == (0, 342, 126.5, 849.5, True, 25)


def test_gen4_diamond_camera_four_bytes_earlier():
    """Diamond's FieldSystem holds the camera at +0x20, so the process pointer at +0 is found and the overworld shown;
    the junk word 4 bytes before the FieldSystem is never taken as the start."""
    ram = _g4_ram(x=90, z=853, map_=334, location_field=0x1C, music=0x0A, matrix=2, code="ADAD", camera_field=0x20)
    struct.pack_into("<I", ram, FIELD - 4, 0x0B)
    reader = Gen4Reader("ADAD")
    assert reader.search({NDS_RAM: bytes(ram)})
    location = reader.read(_read_from(ram))
    assert (location.number, location.x, location.y, location.height, location.vblank) == (334, 90.5, 853.5, 3.0, True)
    struct.pack_into("<II", ram, PROCESSES, 0, 0x022A6AC8)
    assert reader.read(_read_from(ram)).vblank is False


def test_gen4_without_team_and_before_the_overworld():
    """Generation 4 without a team or before the overworld yields nothing."""
    ram = _g4_ram()
    struct.pack_into("<II", ram, BUFFER + 0x98 - 8, 6, 0)
    ram[BUFFER + 0x98:BUFFER + 0x98 + 236] = bytes(236)
    reader = Gen4Reader("IPGD")
    assert reader.search({NDS_RAM: bytes(ram)}) and reader.read(_read_from(ram)).kind == 0
    empty = {NDS_RAM: bytes(0x400000)}
    reader = Gen4Reader("IPGD")
    dumps = iter([empty, empty, {NDS_RAM: bytes(ram)}])
    results = [reader.step(lambda: next(dumps), _read_from(ram)) for _ in range(3)]
    assert results[:2] == [None, None] and results[2].number == 73


def _heap_block(ram, place, name, size):
    """Gen 5 heap block: header with the source file name, content from place + 0x2C."""
    struct.pack_into("<IIIII", ram, place, 0x5544, size, 0, 0, 0x194E0015)
    ram[place + 0x14:place + 0x14 + len(name)] = name.encode()
    return place + 0x2C


def _gen5_camera(ram, content, x, y, z):
    """Writes a camera into the fake generation 5 RAM."""
    struct.pack_into("<ii", ram, content + 4, 0x576, 0xF0A)
    struct.pack_into("<3i", ram, content + 0x20, round(x * 65536), round((y + 11.86) * 65536), round((z + 8.88) * 65536))
    struct.pack_into("<3i", ram, content + 0x38, round(x * 65536), round((y + 0.25) * 65536), round(z * 65536))


def _gen5_ram():
    """RAM as in Black 2: game data (zone 445 with position at +0x114), field map, a camera at the origin (as for menu
    graphics) and the field camera."""
    ram = bytearray(0x400000)
    data = _heap_block(ram, 0x23B244, "game_data.c", 0x334)
    struct.pack_into("<I3i", ram, data + 0x114, 445, 46 * 65536 + 0x8000, 2 * 65536, 45 * 65536 + 0x8000)
    _heap_block(ram, 0x2631F4, "fieldmap.c", 0x184)
    _gen5_camera(ram, _heap_block(ram, 0x25BF74, "g3d_camera.c", 0x60), 0, 0, 0)
    _gen5_camera(ram, _heap_block(ram, 0x26FD58, "g3d_camera.c", 0x60), 46.5, 2.0, 45.5)
    return ram


def test_gen5_position_camera_and_overworld():
    """Generation 5 yields position, camera and overworld state."""
    ram = _gen5_ram()
    reader = Gen5Reader("IRED")
    assert reader.search({NDS_RAM: bytes(ram)})
    read = _read_from(ram)
    location = reader.read(read)
    assert (location.number, location.x, location.y, location.height, location.vblank) == (445, 46.5, 45.5, 2.0, True)
    camera = location.camera
    assert camera[3:6] == pytest.approx((46.5, 2.25, 45.5)) and camera[6] == pytest.approx(0x576 / 0xF0A)
    assert projection(camera, 46.5, 2.0, 45.5)[:2] == pytest.approx((128, 98.7), abs=0.5)
    ram[0x2631F4:0x2631F4 + 0x2C] = bytes(0x2C)
    ram[0x26FD58:0x26FD58 + 0x2C] = bytes(0x2C)
    location = reader.step(lambda: {NDS_RAM: bytes(ram)}, read)
    assert not location.vblank and location.camera == camera
    _heap_block(ram, 0x300000, "fieldmap.c", 0x184)
    _gen5_camera(ram, _heap_block(ram, 0x310000, "g3d_camera.c", 0x60), 46.5, 2.0, 45.5)
    locations = [reader.step(lambda: {NDS_RAM: bytes(ram)}, read) for _ in range(SEARCH_MENU + 1)]
    assert locations[-1].vblank


def test_nds_shared_maps():
    """NDS maps are mapped to a shared numbering."""
    assert shared("hgss", 0, 73) == shared("hgss", 0, 34)
    assert shared("dp", 0, 3) == shared("pt", 0, 342)
    assert shared("dp", 7, 69) != shared("pt", 7, 69)
    assert shared("hgss", 73, 69) != shared("hgss", 73, 70)
    assert shared("bw2", 0, 445) != shared("bw2", 0, 446) and shared("bw", 0, 1) != shared("bw2", 0, 1)


def test_projection_matches_the_game():
    """The projection matches the game's perspective."""
    x, y, scale = projection(CAMERA, 466.5, 3.0, 258.5)
    assert (x, y) == pytest.approx((128, 96)) and scale == pytest.approx(16.2, abs=0.1)
    x, y, _ = projection(CAMERA, 474.5, 3.0, 252.5)
    assert x == pytest.approx(246, abs=2) and y == pytest.approx(29, abs=2)
    bottom, top = projection(CAMERA, 466.5, 3.0, 261.5), projection(CAMERA, 466.5, 3.0, 255.5)
    assert bottom[2] > top[2] and 96 - top[1] < bottom[1] - 96
    assert projection(CAMERA, 466.5, 4.0, 258.5)[1] < 96 and projection(CAMERA, 466.5, 3.0, 340) is None


def test_movement_with_smoother_position():
    """Movement with an already smooth position."""
    b = Movement()
    b.new(Location(0, 73, 466.5, 258.5, 0, False, True, 25, 3.0, CAMERA), 0.0)
    b.new(Location(0, 73, 466.75, 258.5, 0, False, True, 25, 3.0, CAMERA), 0.02)
    assert b.position(0.02) == (466.75, 258.5) and b.runs(0.05) and b.after_right and b.in_overworld
    b.new(Location(0, 73, 466.5, 258.5, 0, False, True, 25, 3.0, CAMERA), 0.04)
    assert not b.after_right and not b.runs(1.0)
    b.new(Location(0, 73, 100.5, 20.5, 0, False, True, 25, 3.0, CAMERA), 2.0)
    assert b.position(2.0) == (100.5, 20.5) and not b.runs(2.0)


def test_nds_icons_from_the_rom(nds_icon_rom, gen5_icon_rom):
    """NDS icons are read from the ROM."""
    icons = NdsIcons(io.BytesIO(nds_icon_rom), "hgss")
    assert icons.there
    assert icons.image(25, 0).get_at((3, 3)) == (0, 0, 255, 255)
    assert icons.image(1, 1).get_at((30, 30)) == (0, 255, 0, 255)
    assert icons.image(0, 0) is None and icons.image(30, 0) is None and icons.image(NDS_EI, 0) is None
    assert not NdsIcons(io.BytesIO(bytes(0x200)), "hgss").there
    gen5 = NdsIcons(io.BytesIO(gen5_icon_rom), "bw2")
    assert gen5.image(25, 0).get_at((3, 3)) == (0, 0, 255, 255) and gen5.image(1, 0).get_at((3, 3)) == (0, 255, 0, 255)


def test_nds_first_pokemon_and_egg():
    """The first NDS Pokemon and the egg are determined."""
    _nds_first_kind = world._nds_first_kind

    assert _nds_first_kind(pk45(25, 4, "Pikachu", level=5)) == 25
    assert _nds_first_kind(pk45(175, 4, "Ei", ei=True, level=1)) == NDS_EI
    assert _nds_first_kind(bytes(236)) == 0
    broken = bytearray(pk45(25, 4, "Pikachu", level=5))
    broken[0x20] ^= 0xFF
    assert _nds_first_kind(bytes(broken)) is None
    assert _nds_first_kind(pk45(495, 5, "Snivy", level=5), 5) == 495


