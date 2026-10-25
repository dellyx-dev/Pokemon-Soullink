"""Player position in the world (gen 3, 4, 5), shared by plugins: read from RAM in the worker, packed for the slot,
smoothed and projected in the main process, plus party icons from the ROM. Gen 3 finds SaveBlock1 and gMain once and
reads position, map and callbacks every frame; gen 4 and 5 find the field camera or map data and also deliver the
camera, so the main process can draw at a position like the game graphics. Used in worker parts too, so no pygame here."""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np

from . import pokemon_data as pd
from .maps_rs import RS_TO_EMERALD
from .nds_file import NdsRom, narc, ncgr_pixel, nclr_palettes
from .roms import family

EWRAM, IWRAM = 0x02000000, 0x03000000
NDS_RAM = 0x02000000
WORLDS = {"rs": "hoenn", "emerald": "hoenn", "frlg": "kanto", "dp": "sinnoh", "pt": "sinnoh", "hgss": "johto",
          "bw": "unova", "bw2": "unova2"}
GEN4, GEN5 = ("dp", "pt", "hgss"), ("bw", "bw2")
SEARCH_ALL = 120
FIGURE_TILE = (7, 5)


@dataclass(frozen=True)
class Location:
    """A player in the world, raw from RAM: map group and number, x/y, callback (gMain.callback2 XOR vblankCallback:
    overworld, bag, Pokedex, help menu), battle and vblank flags, kind of the first team Pokemon (gen 3 internal number,
    412 = egg; NDS national dex number, 0 = none), and for the NDS the height and the camera (eye x/y/z, target x/y/z,
    tan of half the opening)."""
    group: int
    number: int
    x: int
    y: int
    callback: int
    battle: bool
    vblank: bool = True
    kind: int = 0
    height: float = 0.0
    camera: tuple[float, ...] | None = None


_SLOT = struct.Struct("<BBHHHIfff7f")
_SLOT_VERSION = 1


def pack(location: Location | None) -> bytes:
    """Location as bytes for the plugin slot (52 bytes: version, flags, group, number, kind, callbacks, x, y, height,
    camera); b"" means no position (title screen, values out of range)."""
    if location is None:
        return b""
    marker = (1 if location.battle else 0) | (2 if location.vblank else 0) | (4 if location.camera is not None else 0)
    try:
        return _SLOT.pack(_SLOT_VERSION, marker, location.group, location.number, location.kind, location.callback, location.x, location.y, location.height,
                          *(location.camera or (0.0,) * 7))
    except struct.error:
        return b""


def unpack(data: bytes | None) -> Location | None:
    """Counterpart of pack; None means no position (empty, too short, other version, negative x or a NaN or infinite
    number)."""
    if not data or len(data) < _SLOT.size or data[0] != _SLOT_VERSION:
        return None
    _, marker, group, number, kind, callback, x, y, height, *camera = _SLOT.unpack_from(data)
    if not all(math.isfinite(v) for v in (x, y, height, *camera)) or x < 0:
        return None
    battle, vblank = bool(marker & 1), bool(marker & 2)
    if not marker & 4:
        return Location(group, number, round(x), round(y), callback, battle, vblank, kind)
    return Location(group, number, x, y, callback, battle, vblank, kind, height, tuple(camera))


def shared(family_: str, group: int, number: int) -> tuple[tuple, int, int] | None:
    """(map key, dx, dy) in the shared numbering: coordinates plus (dx, dy) match for all players with the same key; maps
    without counterpart (RS-only) stay among themselves."""
    if family_ == "rs":
        target = RS_TO_EMERALD.get((group, number))
        if target is None:
            return ("rs", group, number), 0, 0
        return ("hoenn", target[0], target[1]), target[2], target[3]
    if family_ == "emerald":
        return ("hoenn", group, number), 0, 0
    if family_ == "frlg":
        return ("kanto", group, number), 0, 0
    if family_ in GEN4:
        return ((WORLDS[family_], 0) if group == 0 else (family_, 1, number)), 0, 0
    if family_ in GEN5:
        return (family_, number), 0, 0
    return None


def projection(camera: tuple[float, ...], x: float, y: float, z: float) -> tuple[float, float, float] | None:
    """NDS: screen point on the upper screen (256x192) and pixels per tile for the world point x/y/z (tiles; y is the
    height, +z is down in the image), in perspective like the game: camera at the eye, looking at the target in the
    image center; None means behind the camera."""
    ex, ey, ez, zx, zy, zz, tan_half = camera
    fx, fy, fz = zx - ex, zy - ey, zz - ez
    length = math.sqrt(fx * fx + fy * fy + fz * fz)
    right = math.hypot(fx, fz)
    if length < 1e-6 or right < 1e-6 or tan_half <= 0:
        return None
    fx, fy, fz = fx / length, fy / length, fz / length
    rx, rz = -fz / math.hypot(fx, fz), fx / math.hypot(fx, fz)
    ux, uy, uz = -rz * fy, rz * fx - rx * fz, rx * fy
    vx, vy, vz = x - ex, y - ey, z - ez
    depth = vx * fx + vy * fy + vz * fz
    if depth < 0.5:
        return None
    focal_length = 96 / tan_half
    return (128 + focal_length * (vx * rx + vz * rz) / depth, 96 - focal_length * (vx * ux + vy * uy + vz * uz) / depth,
            focal_length / depth)


class Movement:
    """Smooth display from the tile jumps in RAM: a step of one tile takes as long as the gap to the previous step (walking
    16 frames, running 8, cycling 4, from standing 16), and another place or a jump goes there at once. It also learns
    which callbacks are the overworld, namely those while walking."""

    STEP_MIN, STEP_MAX = 4 / 59.73, 16 / 59.73

    def __init__(self):
        """Starts without a position."""
        self.location: Location | None = None
        self.overworld: int | None = None
        self._start = (0.0, 0.0)
        self._target = (0, 0)
        self._started_at = 0.0
        self._duration = self.STEP_MAX
        self._last_step = -1.0
        self.after_right = False

    def runs(self, now: float) -> bool:
        """True while the player is on the move (the last step was not long ago)."""
        return self._last_step >= 0 and now - self._last_step < self._duration + 0.15

    def new(self, location: Location | None, now: float) -> None:
        """Feeds in a newly read location at time now."""
        old = self.location
        self.location = location
        if location is None:
            return
        if location.camera is not None:
            self._fine(old, location, now)
            return
        target = (location.x, location.y)
        if old is None or (old.group, old.number) != (location.group, location.number) or \
                abs(target[0] - self._target[0]) + abs(target[1] - self._target[1]) > 1:
            self._start, self._target, self._started_at = (float(location.x), float(location.y)), target, now
            return
        if target == self._target:
            return
        if not location.battle:
            self.overworld = location.callback
        if target[0] != self._target[0]:
            self.after_right = target[0] > self._target[0]
        gap = now - self._last_step
        self._duration = min(self.STEP_MAX, max(self.STEP_MIN, gap)) if gap < 0.5 else self.STEP_MAX
        self._start, self._target, self._started_at, self._last_step = self.position(now), target, now, now

    def _fine(self, old: Location | None, location: Location, now: float) -> None:
        """HGSS: the position already arrives smooth from the game; only whether and where the player walks is derived
        here."""
        step = (location.x - old.x, location.y - old.y) if old is not None and old.camera is not None else (0, 0)
        if 0 < abs(step[0]) + abs(step[1]) < 1:
            self._last_step, self._duration = now, 0.1
            if location.vblank:
                self.overworld = location.callback
            if step[0]:
                self.after_right = step[0] > 0
        self._start = self._target = (location.x, location.y)
        self._started_at = now

    def position(self, now: float) -> tuple[float, float]:
        """Smoothed (x, y) at time now."""
        share = min(1.0, max(0.0, (now - self._started_at) / self._duration)) if self._duration > 0 else 1.0
        return (self._start[0] + (self._target[0] - self._start[0]) * share,
                self._start[1] + (self._target[1] - self._start[1]) * share)

    @property
    def in_overworld(self) -> bool:
        """True while the world is visible: not in battle, not in bag, Pokedex or help (other callbacks)."""
        return self.location is not None and self.location.vblank and not self.location.battle and \
            (self.overworld is None or self.location.callback == self.overworld)


class WorldReader:
    """Gen 3 reader in the worker: finds the addresses once (read(address, length) delivers bytes from the core) and then
    reads the position every frame."""

    def __init__(self, game_code: str):
        """Creates the reader for a game code."""
        self.game = game_code[:3]
        self._block1_pointer: int | None = None
        self._block1_fixed = pd.G3_RS_BLOCK1 if self.game in ("AXV", "AXP") else None
        self._gmain: int | None = None
        self._team: int | None = None
        self._wait = 0
        self._team_wait = 0

    @property
    def found(self) -> bool:
        """True once all addresses are known."""
        return self._gmain is not None and (self._block1_pointer is not None or self._block1_fixed is not None)

    def search(self, blocks: dict[int, bytes]) -> bool:
        """Determines the addresses from a RAM dump ({start address: bytes}); False means not yet (e.g. title screen)."""
        iw = bytes(blocks.get(IWRAM, b""))
        gmain = pd.g3_gmain(iw)
        if gmain is None:
            return False
        if self._block1_fixed is None:
            place = pd.g3_block_pointer(iw)
            if place is None:
                return False
            self._block1_pointer = IWRAM + place
        self._gmain = IWRAM + gmain
        return True

    def read(self, read) -> Location | None:
        """Position in the running game; None while addresses are missing or the values are implausible."""
        if not self.found:
            return None
        if self._block1_fixed is not None:
            block1 = self._block1_fixed
        else:
            raw = read(self._block1_pointer, 4)
            if len(raw) < 4:
                return None
            block1 = struct.unpack("<I", raw)[0]
        header, main = read(block1, 6), read(self._gmain + 4, 12)
        battle = read(self._gmain + pd.g3_battle_flag(self.game), 1)
        if len(header) < 6 or len(main) < 12 or len(battle) < 1:
            return None
        x, y, group, number = struct.unpack("<hhBB", header)
        if not (0 <= x < 1024 and 0 <= y < 1024 and group < 64 and number < 128) or (x, y, group, number) == (0,) * 4:
            return None
        callback2, _, vblank = struct.unpack("<III", main)
        kind = _first_kind(read(self._team, 0x50)) if self._team is not None else 0
        return Location(group, number, x, y, callback2 ^ vblank, bool(battle[0] & 0x02), vblank != 0, kind)

    def team_search(self, blocks: dict[int, bytes]) -> bool:
        """Finds gPlayerParty (RS in IWRAM, otherwise EWRAM) as when reading catches; needs a Pokemon in the team."""
        for start, data in blocks.items():
            data = bytes(data)
            place = pd.g3_ram_team(data, *pd.g3_ram_slots(data), self.game)
            if place is not None:
                self._team = start + place
                return True
        return False

    def step(self, ram_blocks, read) -> Location | None:
        """Per frame: search first (rarely), then read; ram_blocks() delivers a whole dump for searching."""
        if self.found and self._team is None:
            self._team_wait -= 1
            if self._team_wait <= 0:
                self._team_wait = SEARCH_ALL
                try:
                    self.team_search(ram_blocks())
                except (struct.error, IndexError, ValueError):
                    pass
        if not self.found:
            self._wait -= 1
            if self._wait > 0:
                return None
            self._wait = SEARCH_ALL
            try:
                if not self.search(ram_blocks()):
                    return None
            except (struct.error, IndexError, ValueError):
                return None
        return self.read(read)


def _first_kind(mon: bytes) -> int:
    """Internal species of the first Pokemon (PK3, only the growth block is decrypted); egg gives 412, empty or broken
    gives 0."""
    if len(mon) < 0x50:
        return 0
    pid, otid = struct.unpack_from("<II", mon)
    if not pid and not otid:
        return 0
    words = [w ^ pid ^ otid for w in struct.unpack_from("<12I", mon, 0x20)]
    row = pd.G3_ROWS[pid % 24]
    kind = words[row.index("G") * 3] & 0xFFFF
    ei = words[row.index("M") * 3 + 1] >> 30 & 1
    if not 0 < kind < ICON_COUNT:
        return 0
    return EI if ei else kind


ICON_COUNT = 440
EI = 412
_PALETTES_TAG = 0xDAC0


class PokemonIcons:
    """The small party icons of a gen 3 ROM: in the ROM code gMonIconTable (440 pointers), gMonIconPaletteIndices (440
    bytes, 0-2) and gMonIconPaletteTable (pointer plus tag 56000, 56001, 56002) follow one another, found via the tags;
    verified on Ruby, Emerald, FireRed and LeafGreen (German)."""

    def __init__(self, rom: bytes):
        """Creates the icon source for a ROM and finds the tables."""
        self.rom = rom
        self._images: dict[tuple[int, int], object] = {}
        self._table = self._indices = None
        self._palettes: list[list[tuple[int, int, int]]] = []
        place = rom.find(struct.pack("<HH", _PALETTES_TAG, 0))
        while place >= 4:
            pointer = struct.unpack_from("<I", rom, place - 4)[0]
            if _rom(pointer) and rom[place + 8:place + 10] == struct.pack("<H", _PALETTES_TAG + 1):
                break
            place = rom.find(struct.pack("<HH", _PALETTES_TAG, 0), place + 1)
        if place < 4:
            return
        palettes = place - 4
        indices = palettes - ICON_COUNT
        table = indices - 4 * ICON_COUNT
        if table < 0 or max(rom[indices:palettes]) > 2 or \
                not all(_rom(z) for z in struct.unpack_from(f"<{ICON_COUNT}I", rom, table)):
            return
        for i in range(3):
            data = struct.unpack_from("<I", rom, palettes + 8 * i)[0] - 0x08000000
            colors = struct.unpack_from("<16H", rom, data)
            self._palettes.append([((f & 31) * 255 // 31, (f >> 5 & 31) * 255 // 31, (f >> 10 & 31) * 255 // 31)
                                   for f in colors])
        self._table, self._indices = table, indices

    @property
    def there(self) -> bool:
        """True if the tables were found."""
        return self._table is not None

    def image(self, kind: int, number: int):
        """pygame surface 32x32 (color 0 transparent) for frame 0 or 1; None if unknown."""
        import pygame

        if not self.there or not 0 < kind < ICON_COUNT:
            return None
        key = (kind, number % 2)
        if key not in self._images:
            pointer = struct.unpack_from("<I", self.rom, self._table + 4 * kind)[0] - 0x08000000
            palette = self._palettes[min(self.rom[self._indices + kind], 2)]
            image = pygame.Surface((32, 32), pygame.SRCALPHA)
            start = pointer + key[1] * 0x200
            for tile in range(16):
                kx, ky = tile % 4 * 8, tile // 4 * 8
                for i, byte in enumerate(self.rom[start + tile * 32:start + tile * 32 + 32]):
                    for half, index in enumerate((byte & 15, byte >> 4)):
                        if index:
                            image.set_at((kx + i % 4 * 2 + half, ky + i // 4), (*palette[index], 255))
            self._images[key] = image
        return self._images[key]


def _rom(pointer: int) -> bool:
    """True for an address in the ROM area."""
    return 0x08000000 <= pointer < 0x0A000000


def icons_load(rom, family_: str | None):
    """Party icons from a player's ROM (PokemonIcons or NdsIcons); None if unreadable, in which case the stylus is used."""
    try:
        if family_ in GEN4 + GEN5:
            with open(rom, "rb") as file:
                return NdsIcons(file, family_)
        return PokemonIcons(Path(rom).read_bytes())
    except (OSError, ValueError, struct.error):
        return None


_FX = 4096 * 16
_ANGLE = 2 * math.pi / 0x10000
NDS_EI = 0xFFFF
SEARCH_MENU = 30


def _default_camera(x: float, y: float, z: float) -> tuple[float, ...]:
    """Camera as in the gen 4 overworld above (x, y, z), as long as a player has not yet seen the overworld."""
    gap, tilt = 0x29AEC1 / _FX, (0x10000 - 0xDD62) * _ANGLE
    return (x, y + gap * math.sin(tilt), z + gap * math.cos(tilt), x, y, z, math.tan(0x05C1 * _ANGLE))

_G4_HEADERS = {"hgss": (0x0C, 4), "dp": (0x0A, 2), "pt": (0x0A, 2)}
_G4_CAMERA_FIELD = {"hgss": 0x24, "dp": 0x20, "pt": 0x24}
_G4_HEADER = 24


def _g4_map_headers(ram: bytes, music: int) -> int | None:
    """Position of the map header table in RAM: the first run of at least 500 headers with plausible music."""
    range_ = ram[:0x200000]
    for offset in range(0, _G4_HEADER, 4):
        n = (len(range_) - offset) // _G4_HEADER
        if n <= 0:
            continue
        a = np.frombuffer(range_, "<u2", n * _G4_HEADER // 2, offset).reshape(n, _G4_HEADER // 2)
        tag, night = a[:, music // 2], a[:, music // 2 + 1]
        good = ((tag >= 1000) & (tag <= 1300) & (night >= 1000) & (night <= 1300)).astype(np.int8)
        edges = np.diff(np.concatenate(([0], good, [0])))
        starts, end = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
        lang = np.flatnonzero(end - starts >= 500)
        if len(lang):
            return offset + int(starts[lang[0]]) * _G4_HEADER
    return None


def _g4_cameras(ram: bytes) -> list[int]:
    """Positions of possible field cameras: distance 1-128 tiles, the eye exactly that far from the target, half opening
    1-45 degrees."""
    w = np.frombuffer(ram, "<i4", len(ram) // 4)
    if len(w) < 32:
        return []
    gap = w[14:len(w) - 18 + 14]
    candidates = np.flatnonzero((gap >= 0x10000) & (gap <= 0x800000))
    if not len(candidates):
        return []
    a = w.astype(np.float64)
    k = candidates
    eye, target = [a[k + 5 + i] for i in range(3)], [a[k + 8 + i] for i in range(3)]
    width = np.sqrt(sum((eye[i] - target[i]) ** 2 for i in range(3)))
    opening = (w[k + 17].astype(np.int64) >> 16) & 0xFFFF
    good = (np.abs(width - a[k + 14]) <= a[k + 14] * 0.02) & (opening >= 0xB6) & (opening <= 0x2000)
    return [int(i) * 4 for i in k[good]]


def _nds_first_kind(mon: bytes, gen: int = 4) -> int | None:
    """National dex number of the first team Pokemon (PK4/PK5 in the save buffer); egg gives NDS_EGG, empty 0 and None
    means currently unreadable."""
    if len(mon) < 136 or not any(mon[:8]):
        return 0
    catch_ = pd.pk45(mon, gen, True, None, 0)
    if catch_ is None:
        return None
    return NDS_EI if catch_.ei else catch_.kind


class _NdsReader:
    """Shared base for gen 4 and 5: search (rarely), read (every frame) and the first team Pokemon."""

    def __init__(self, game_code: str):
        """Creates the reader for a game code."""
        self.game = game_code[:3]
        self.family = family(game_code)
        self.gen = 4 if self.family in GEN4 else 5
        self._team: int | None = None
        self._first = (b"", 0)
        self._wait = 0
        self._failures = 0
        self._team_wait = 0

    found = False

    def search(self, blocks: dict[int, bytes]) -> bool:
        """Finds the addresses in a RAM dump; implemented by the subclasses."""
        raise NotImplementedError

    def read(self, read) -> Location | None:
        """Reads the position; implemented by the subclasses."""
        raise NotImplementedError

    def team_search(self, blocks: dict[int, bytes]) -> bool:
        """Finds the team in the save buffer of main memory."""
        ram = bytes(blocks.get(NDS_RAM, b""))
        start, catches = pd.nds_buffer(ram, *pd.NDS_BUFFER[self.game])
        if not catches:
            return False
        self._team = NDS_RAM + start
        return True

    def _kind(self, read) -> int:
        """Species number of the first team Pokemon; 0 if unknown."""
        if self._team is None:
            return 0
        header = read(self._team, 8)
        if header != self._first[0]:
            kind = _nds_first_kind(read(self._team, 236 if self.gen == 4 else 220), self.gen)
            if kind is None:
                return self._first[1]
            self._first = (header, kind)
        return self._first[1]

    def step(self, ram_blocks, read) -> Location | None:
        """Per frame: search first (rarely), then read; ram_blocks() delivers a whole dump for searching."""
        if self.found and self._team is None:
            self._team_wait -= 1
            if self._team_wait <= 0:
                self._team_wait = SEARCH_ALL
                try:
                    self.team_search(ram_blocks())
                except (struct.error, IndexError, ValueError):
                    pass
        if not self.found:
            self._wait -= 1
            if self._wait > 0:
                return None
            self._failures += 1
            self._wait = 1 if self._failures % 8 else SEARCH_ALL
            try:
                if not self.search(ram_blocks()):
                    return None
            except (struct.error, IndexError, ValueError):
                return None
            self._failures = 0
        return self.read(read)


class Gen4Reader(_NdsReader):
    """Diamond/Pearl/Platinum and HeartGold/SoulSilver: finds the field camera and the FieldSystem pointing at it (Diamond/
    Pearl at +0x20, the others at +0x24), and from that the location."""

    def __init__(self, game_code: str):
        """Creates the reader for a game code."""
        super().__init__(game_code)
        self._field: int | None = None
        self._location_field = 0x20
        self._location: int | None = None
        self._headers: int | None = None
        self._last: tuple | None = None

    @property
    def found(self) -> bool:
        """True once the FieldSystem is known."""
        return self._field is not None

    def search(self, blocks: dict[int, bytes]) -> bool:
        """Finds the FieldSystem via the map header table and the camera."""
        ram = bytes(blocks.get(NDS_RAM, b""))
        music, _ = _G4_HEADERS[self.family]
        headers = _g4_map_headers(ram, music)
        if headers is None:
            return False
        for camera in _g4_cameras(ram):
            zx, _, zz = (v / _FX for v in struct.unpack_from("<3i", ram, camera + 0x20))
            holder = ram.find(struct.pack("<I", NDS_RAM + camera))
            while holder >= 0:
                field = holder - _G4_CAMERA_FIELD[self.family]
                if holder % 4 == 0 and field >= 0:
                    for location_field in (0x1C, 0x20):
                        location = struct.unpack_from("<I", ram, field + location_field)[0] - NDS_RAM
                        if 0 <= location <= len(ram) - 20 and location % 4 == 0:
                            map_, _, x, z, direction = struct.unpack_from("<5i", ram, location)
                            if 0 <= map_ < 1000 and 0 <= direction < 4 and abs(x + 0.5 - zx) <= 2 \
                                    and abs(z + 0.5 - zz) <= 2:
                                self._field, self._location_field, self._location = NDS_RAM + field, location_field, NDS_RAM + location
                                self._headers = NDS_RAM + headers
                                self.team_search(blocks)
                                return True
                holder = ram.find(struct.pack("<I", NDS_RAM + camera), holder + 1)
        return False

    def read(self, read) -> Location | None:
        """Reads map, position with height and camera."""
        if not self.found:
            return None
        field, location = read(self._field, 0x28), read(self._location, 16)
        if len(field) < 0x28 or len(location) < 16:
            return None
        processes = struct.unpack_from("<I", field)[0]
        camera_pointer = struct.unpack_from("<I", field, _G4_CAMERA_FIELD[self.family])[0]
        if struct.unpack_from("<I", field, self._location_field)[0] != self._location:
            self._field = None
            return None
        map_, _, x, z = struct.unpack("<iiii", location)
        _, matrix_place = _G4_HEADERS[self.family]
        matrix = read(self._headers + map_ * _G4_HEADER + matrix_place, 2) if 0 <= map_ < 1000 else b""
        if len(matrix) < 2:
            return None
        main_kind = read(processes, 8) if processes else b""
        overworld = len(main_kind) == 8 and struct.unpack("<II", main_kind)[0] != 0 and \
            struct.unpack("<II", main_kind)[1] == 0
        position = None
        if overworld and camera_pointer:
            k = read(camera_pointer, 0x48)
            if len(k) == 0x48:
                eye = tuple(v / _FX for v in struct.unpack_from("<3i", k, 0x14))
                target = tuple(v / _FX for v in struct.unpack_from("<3i", k, 0x20))
                opening = struct.unpack_from("<H", k, 0x46)[0] * _ANGLE
                if abs(target[0] - x - 0.5) <= 2 and abs(target[2] - z - 0.5) <= 2 and 0 < opening < math.pi / 4:
                    position = (target[0], target[2], target[1], (*eye, *target, math.tan(opening)))
                    self._last = position
        real = position is not None
        if not real:
            height = self._last[2] if self._last else 0.0
            camera = self._last[3] if self._last else _default_camera(x + 0.5, height, z + 0.5)
            position = (x + 0.5, z + 0.5, height, camera)
        return Location(struct.unpack("<H", matrix)[0], map_, position[0], position[1], 0, False, overworld and real,
                   self._kind(read), position[2], position[3])


_HEAP_MAGIC, _HEAP_HEADER = 0x5544, 0x2C


def _heap_blocks(ram: bytes, name: str) -> list[tuple[int, int]]:
    """(position of the content, size) of all heap blocks with this source file name."""
    pattern, blocks = name.encode("ascii") + b"\0", []
    place = ram.find(pattern)
    while place >= 0:
        header = place - 0x14
        if header >= 0 and header % 4 == 0 and struct.unpack_from("<I", ram, header)[0] == _HEAP_MAGIC:
            blocks.append((header + _HEAP_HEADER, struct.unpack_from("<I", ram, header + 4)[0]))
        place = ram.find(pattern, place + 1)
    return blocks


def _heap_name(header: bytes) -> str | None:
    """Source file name from a heap block header; None if the header is invalid."""
    if len(header) < 0x24 or struct.unpack_from("<I", header)[0] != _HEAP_MAGIC:
        return None
    return header[0x14:0x24].split(b"\0")[0].decode("latin-1")


class Gen5Reader(_NdsReader):
    """Black/White and Black 2/White 2: finds game data, field map and camera through the source file names in the heap
    headers."""

    def __init__(self, game_code: str):
        """Creates the reader for a game code."""
        super().__init__(game_code)
        self._data: int | None = None
        self._map: int | None = None
        self._camera: int | None = None
        self._last: tuple | None = None
        self._menu_wait = 0

    @property
    def found(self) -> bool:
        """True once the game data are known."""
        return self._data is not None

    def search(self, blocks: dict[int, bytes]) -> bool:
        """Game data and the position within them: zone plus fx32 position whose x/z fit the target of a camera (the field
        camera's target lies on the player, other cameras do not)."""
        ram = bytes(blocks.get(NDS_RAM, b""))
        game_data = _heap_blocks(ram, "game_data.c")
        maps = _heap_blocks(ram, "fieldmap.c")
        if not game_data or not maps:
            return False
        content, size = game_data[0]
        for camera, _ in _heap_blocks(ram, "g3d_camera.c"):
            sine, cosine = struct.unpack_from("<ii", ram, camera + 4)
            zx, zy, zz = (v / _FX for v in struct.unpack_from("<3i", ram, camera + 0x38))
            if not (0 < sine < cosine <= 4096) or abs(zx) + abs(zz) < 2:
                continue
            for place in range(content + 4, content + min(size, 0x1000) - 12, 4):
                zone, x, y, z = struct.unpack_from("<I3i", ram, place - 4)
                if zone < 2000 and abs(x / _FX - zx) <= 0.5 and abs(z / _FX - zz) <= 0.5 and abs(y / _FX - zy) <= 2:
                    self._data = NDS_RAM + place - 4
                    self._map, self._camera = NDS_RAM + maps[0][0], NDS_RAM + camera
                    self.team_search(blocks)
                    return True
        return False

    def _field_search(self, ram: bytes, position: tuple[float, float]) -> bool:
        """After a battle or menu: is fieldmap.c back, and the camera whose target lies at the player."""
        maps = _heap_blocks(ram, "fieldmap.c")
        if not maps:
            return False
        for content, _ in _heap_blocks(ram, "g3d_camera.c"):
            sine, cosine = struct.unpack_from("<ii", ram, content + 4)
            zx, _, zz = (v / _FX for v in struct.unpack_from("<3i", ram, content + 0x38))
            if 0 < sine < cosine <= 4096 and abs(zx - position[0]) <= 2 and abs(zz - position[1]) <= 2:
                self._map, self._camera = NDS_RAM + maps[0][0], NDS_RAM + content
                return True
        return False

    def read(self, read) -> Location | None:
        """Reads map, position with height and camera."""
        if not self.found:
            return None
        raw = read(self._data, 16)
        if len(raw) < 16:
            return None
        zone, x, y, z = struct.unpack("<I3i", raw)
        x, y, z = x / _FX, y / _FX, z / _FX
        overworld = self._map is not None and _heap_name(read(self._map - _HEAP_HEADER, 0x24)) == "fieldmap.c"
        camera = None
        if overworld and self._camera is not None and \
                _heap_name(read(self._camera - _HEAP_HEADER, 0x24)) == "g3d_camera.c":
            k = read(self._camera, 0x44)
            if len(k) == 0x44:
                sine, cosine = struct.unpack_from("<ii", k, 4)
                eye = tuple(v / _FX for v in struct.unpack_from("<3i", k, 0x20))
                target = tuple(v / _FX for v in struct.unpack_from("<3i", k, 0x38))
                if 0 < sine < cosine and abs(target[0] - x) <= 2 and abs(target[2] - z) <= 2:
                    camera = (*eye, *target, sine / cosine)
                    self._last = (y, camera)
        if camera is None:
            overworld = False
            camera = self._last[1] if self._last else _default_camera(x, y, z)
        return Location(0, zone, x, z, 0, False, overworld, self._kind(read), y, camera)

    def step(self, ram_blocks, read) -> Location | None:
        """Per frame like the base class; searches again now and then when the field map or camera was recreated (after a
        battle or menu)."""
        location = super().step(ram_blocks, read)
        if location is not None and not location.vblank:
            self._menu_wait -= 1
            if self._menu_wait <= 0:
                self._menu_wait = SEARCH_MENU
                try:
                    if self._field_search(bytes(ram_blocks().get(NDS_RAM, b"")), (location.x, location.y)):
                        location = self.read(read)
                except (struct.error, IndexError, ValueError):
                    pass
        return location


def world_reader(game_code: str) -> WorldReader | Gen4Reader | Gen5Reader | None:
    """The reader fitting the coplayer display for a game; None for games without one."""
    kind = family(game_code)
    if kind is None:
        return None
    if kind in GEN4:
        return Gen4Reader(game_code)
    return Gen5Reader(game_code) if kind in GEN5 else WorldReader(game_code)


class NdsIcons:
    """Party icons from an NDS ROM. Gen 4 reads a NARC (HGSS a/0/2/0, Platinum pl_poke_icon, Diamond/Pearl poke_icon) where
    file 0 holds the palettes and from the first NCGR each species has a 32x64 image with two frames stacked (494 is the
    egg), with the palette number from a table in the ARM9. Gen 5 reads NARC a/0/0/7 with two files per species, whose
    table has one byte per species with the low nibble counting, and the egg is 650 (Black/White) or 683 (Black 2/White
    2); same interface as PokemonIcons."""

    _PATHS = {"hgss": "a/0/2/0", "pt": "poketool/icongra/pl_poke_icon.narc", "dp": "poketool/icongra/poke_icon.narc",
              "bw": "a/0/0/7", "bw2": "a/0/0/7"}
    _EI = {"hgss": 494, "pt": 494, "dp": 494, "bw": 650, "bw2": 683}

    def __init__(self, file: BinaryIO, family_: str):
        """Creates the icon source for a ROM file and a game family."""
        self._images: dict[tuple[int, int], object] = {}
        self._files: list[bytes] = []
        self._palettes: list = []
        self._numbers: list[int] = []
        self._ei = self._EI.get(family_, 0)
        gen5 = family_ in GEN5
        try:
            rom = NdsRom(file)
            data = rom.file(self._PATHS.get(family_, ""))
            arm9 = rom.arm9()
            if gen5:
                place = arm9.find(bytes([0x11, 0x11, 0x11, 0, 0, 0, 0, 0x22, 0x22])) - 1
            else:
                place = arm9.find(bytes([0, 1, 1, 1, 0, 0, 0, 0, 2, 2]))
            if data is None or place < 0:
                return
            files = narc(data)
            self._palettes = nclr_palettes(files[0])
        except (struct.error, IndexError, ValueError):
            return
        first = next((i for i, d in enumerate(files) if d[:4] == b"RGCN"), len(files))
        self._files = files[first::2] if gen5 else files[first:]
        self._numbers = [b & 15 if gen5 else b for b in arm9[place:place + len(self._files)]]

    @property
    def there(self) -> bool:
        """True if files and palettes were found."""
        return bool(self._files) and bool(self._palettes)

    def image(self, kind: int, number: int):
        """pygame surface 32x32 (color 0 transparent) for frame 0 or 1; None if unknown."""
        import pygame

        if kind == NDS_EI:
            kind = self._ei
        if not self.there or not 0 < kind < min(len(self._files), len(self._numbers)) or not self._files[kind]:
            return None
        key = (kind, number % 2)
        if key not in self._images:
            pixel = ncgr_pixel(self._files[kind])
            palette = self._palettes[min(self._numbers[kind], len(self._palettes) - 1)]
            image = pygame.Surface((32, 32), pygame.SRCALPHA)
            start = key[1] * 16 * 32
            for tile in range(16):
                kx, ky = tile % 4 * 8, tile // 4 * 8
                for i, byte in enumerate(pixel[start + tile * 32:start + tile * 32 + 32]):
                    for half, index in enumerate((byte & 15, byte >> 4)):
                        if index:
                            image.set_at((kx + i % 4 * 2 + half, ky + i // 4), (*palette[index], 255))
            self._images[key] = image
        return self._images[key]
