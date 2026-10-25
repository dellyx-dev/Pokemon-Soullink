"""ctypes binding for libretro cores (mGBA, melonDS DS). Only one instance per loaded DLL file, because libretro cores keep
global state."""
from __future__ import annotations

import ctypes as C
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

EXPERIMENTAL = 0x10000
ENV_GET_CAN_DUPE = 3
ENV_SET_MESSAGE = 6
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_SET_INPUT_DESCRIPTORS = 11
ENV_GET_VARIABLE = 15
ENV_SET_VARIABLES = 16
ENV_GET_SAVE_DIRECTORY = 31
ENV_SET_SYSTEM_AV_INFO = 32
ENV_SET_CONTROLLER_INFO = 35
ENV_SET_MEMORY_MAPS = 36 | EXPERIMENTAL
ENV_SET_GEOMETRY = 37
ENV_SET_SUPPORT_ACHIEVEMENTS = 42 | EXPERIMENTAL
ENV_GET_INPUT_BITMASKS = 51 | EXPERIMENTAL
ENV_SET_NETPACKET_INTERFACE = 78
_ONLY_CONFIRM = {ENV_SET_MESSAGE, ENV_SET_INPUT_DESCRIPTORS, ENV_SET_VARIABLES, ENV_SET_CONTROLLER_INFO,
                    ENV_SET_MEMORY_MAPS, ENV_SET_GEOMETRY, ENV_SET_SUPPORT_ACHIEVEMENTS, ENV_GET_INPUT_BITMASKS}

PIXEL_0RGB1555, PIXEL_XRGB8888, PIXEL_RGB565 = 0, 1, 2
SAVE_RAM = 0
SYSTEM_RAM = 2
JOYPAD = 1
JOYPAD_MASK = 256
POINTER = 6
POINTER_X, POINTER_Y, POINTER_PRESSED = 0, 1, 2
POINTER_MAX = 0x7FFF


class CoreError(Exception):
    """Raised when a core cannot be loaded or used."""
    pass


@dataclass
class AvInfo:
    """Video and audio properties reported by the core."""
    width: int
    height: int
    fps: float
    samplerate: int


class _SystemInfo(C.Structure):
    """ctypes mirror of retro_system_info."""
    _fields_ = [("library_name", C.c_char_p), ("library_version", C.c_char_p),
                ("valid_extensions", C.c_char_p), ("need_fullpath", C.c_bool), ("block_extract", C.c_bool)]


class _Geometry(C.Structure):
    """ctypes mirror of retro_game_geometry."""
    _fields_ = [("base_width", C.c_uint), ("base_height", C.c_uint), ("max_width", C.c_uint),
                ("max_height", C.c_uint), ("aspect_ratio", C.c_float)]


class _Clock(C.Structure):
    """ctypes mirror of retro_system_timing."""
    _fields_ = [("fps", C.c_double), ("sample_rate", C.c_double)]


class _AvInfo(C.Structure):
    """ctypes mirror of retro_system_av_info."""
    _fields_ = [("geometry", _Geometry), ("timing", _Clock)]


class _Variable(C.Structure):
    """ctypes mirror of retro_variable."""
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class _MemoryDescription(C.Structure):
    """ctypes mirror of retro_memory_descriptor."""
    _fields_ = [("flags", C.c_uint64), ("ptr", C.c_void_p), ("offset", C.c_size_t), ("start", C.c_size_t),
                ("select", C.c_size_t), ("disconnect", C.c_size_t), ("len", C.c_size_t), ("addrspace", C.c_char_p)]


class _MemoryMap(C.Structure):
    """ctypes mirror of retro_memory_map."""
    _fields_ = [("descriptors", C.POINTER(_MemoryDescription)), ("num_descriptors", C.c_uint)]


class _GameInfo(C.Structure):
    """ctypes mirror of retro_game_info."""
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]


_ENVIRONMENT = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
_IMAGE = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
_SAMPLE = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
_SAMPLE_BATCH = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
_POLL = C.CFUNCTYPE(None)
_STATUS = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
_NETWORK_SEND = C.CFUNCTYPE(None, C.c_int, C.c_void_p, C.c_size_t, C.c_uint16)
_NETWORK_QUERY = C.CFUNCTYPE(None)
_NETWORK_START = C.CFUNCTYPE(None, C.c_uint16, _NETWORK_SEND, _NETWORK_QUERY)
_NETWORK_RECEIVE = C.CFUNCTYPE(None, C.c_void_p, C.c_size_t, C.c_uint16)
_NETWORK_STOP = C.CFUNCTYPE(None)
NETWORK_ALL = 0xFFFF


class _NetworkCallbacks(C.Structure):
    """ctypes mirror of retro_netpacket_callback."""
    _fields_ = [("start", C.c_void_p), ("receive", C.c_void_p), ("stop", C.c_void_p), ("poll", C.c_void_p),
                ("connected", C.c_void_p), ("disconnected", C.c_void_p), ("protocol_version", C.c_char_p)]


def pointer_value(pixel: float, size: int) -> int:
    """Converts a position in the whole video frame (0 to size, pixel center = p + 0.5) into a clamped libretro pointer
    value."""
    return max(-POINTER_MAX, min(POINTER_MAX, round(pixel * 2 * POINTER_MAX / size) - POINTER_MAX))


def _five_on_eight(v):
    """Expands a 5-bit color channel to 8 bits."""
    return (v << 3) | (v >> 2)


def _table(pixelformat: int) -> np.ndarray:
    """Lookup table converting 16-bit pixels to uint32 with the bytes R, G, B, 0xFF."""
    v = np.arange(65536, dtype=np.uint32)
    if pixelformat == PIXEL_RGB565:
        r, g, b = _five_on_eight((v >> 11) & 0x1F), (v >> 5) & 0x3F, _five_on_eight(v & 0x1F)
        g = (g << 2) | (g >> 4)
    else:
        r, g, b = (_five_on_eight((v >> s) & 0x1F) for s in (10, 5, 0))
    return r | (g << 8) | (b << 16) | np.uint32(0xFF000000)


class Core:
    """A loaded libretro core with video, audio, save RAM, states, memory access, DS wireless and GBA link cable support."""

    def __init__(self, path: Path, system_dir: Path, options: dict[str, str] | None = None):
        """Loads the core DLL; options are core variables such as melonds_show_cursor=disabled, everything else keeps its
        default."""
        self._options = {k.encode(): v.encode() for k, v in (options or {}).items()}
        self._lib = lib = C.CDLL(str(path))
        lib.retro_load_game.argtypes = [C.POINTER(_GameInfo)]
        lib.retro_load_game.restype = C.c_bool
        lib.retro_get_memory_data.argtypes = [C.c_uint]
        lib.retro_get_memory_data.restype = C.c_void_p
        lib.retro_get_memory_size.argtypes = [C.c_uint]
        lib.retro_get_memory_size.restype = C.c_size_t
        lib.retro_serialize_size.restype = C.c_size_t
        lib.retro_serialize.argtypes = [C.c_void_p, C.c_size_t]
        lib.retro_serialize.restype = C.c_bool
        lib.retro_unserialize.argtypes = [C.c_void_p, C.c_size_t]
        lib.retro_unserialize.restype = C.c_bool

        self._system = str(system_dir).encode("utf-8")
        self._pixelformat = PIXEL_0RGB1555
        self._tables: dict[int, np.ndarray] = {}
        self._single_tone = bytearray()
        self._rom_buffer = None
        self._rom_path = b""
        self._loaded = False
        self._active = True
        self.input_mask = 0
        self.pointer_x = 0
        self.pointer_y = 0
        self.pointer_pressed = False
        self.image_active = True
        self.audio_active = True
        self.at_image = None
        self.at_audio = None
        self.av: AvInfo | None = None
        self._network = None
        self._network_callbacks = None
        self._network_send_py = self._network_query_py = None

        self._callbacks = (_ENVIRONMENT(self._environment), _IMAGE(self._image), _SAMPLE(self._sample),
                           _SAMPLE_BATCH(self._sample_batch), _POLL(lambda: None), _STATUS(self._status))
        lib.retro_set_environment(self._callbacks[0])
        lib.retro_set_video_refresh(self._callbacks[1])
        lib.retro_set_audio_sample(self._callbacks[2])
        lib.retro_set_audio_sample_batch(self._callbacks[3])
        lib.retro_set_input_poll(self._callbacks[4])
        lib.retro_set_input_state(self._callbacks[5])
        lib.retro_init()
        info = _SystemInfo()
        lib.retro_get_system_info(C.byref(info))
        self.version = (info.library_version or b"").decode("utf-8", "replace")

    def _environment(self, command, data):
        """libretro environment callback: answers the core's queries and settings."""
        try:
            if command == ENV_SET_PIXEL_FORMAT:
                format_ = C.cast(data, C.POINTER(C.c_int))[0]
                if format_ not in (PIXEL_0RGB1555, PIXEL_XRGB8888, PIXEL_RGB565):
                    return False
                self._pixelformat = format_
                return True
            if command in (ENV_GET_SYSTEM_DIRECTORY, ENV_GET_SAVE_DIRECTORY):
                C.cast(data, C.POINTER(C.c_char_p))[0] = self._system
                return True
            if command == ENV_GET_CAN_DUPE:
                C.cast(data, C.POINTER(C.c_bool))[0] = True
                return True
            if command == ENV_SET_SYSTEM_AV_INFO:
                self._av_apply(C.cast(data, C.POINTER(_AvInfo))[0])
                return True
            if command == ENV_SET_MEMORY_MAPS:
                self._memory_card_remember(C.cast(data, C.POINTER(_MemoryMap))[0])
                return True
            if command == ENV_SET_NETPACKET_INTERFACE:
                r = C.cast(data, C.POINTER(_NetworkCallbacks))[0]
                if not r.start or not r.receive:
                    return False
                self._network = (_NETWORK_START(r.start), _NETWORK_RECEIVE(r.receive), _NETWORK_STOP(r.stop) if r.stop else None)
                return True
            if command == ENV_GET_VARIABLE:
                variable = C.cast(data, C.POINTER(_Variable))[0]
                value = self._options.get(variable.key)
                if value is None:
                    return False
                variable.value = value
                return True
            return command in _ONLY_CONFIRM
        except Exception:
            return False

    def _memory_card_remember(self, map_) -> None:
        """Remembers the core's address ranges (e.g. GBA EWRAM from 0x02000000, IWRAM from 0x03000000) for reading RAM."""
        self._memory_card = []
        for i in range(map_.num_descriptors):
            d = map_.descriptors[i]
            if d.ptr and d.len:
                self._memory_card.append((d.start, d.ptr + d.offset, d.len))

    def _image(self, data, width, height, pitch):
        """Video callback: converts the frame and hands it on."""
        if not data or not self.image_active or self.at_image is None or not width or not height:
            return
        if self._pixelformat == PIXEL_XRGB8888:
            v = np.ctypeslib.as_array(C.cast(data, C.POINTER(C.c_uint32)), shape=(height, pitch // 4))[:, :width]
            rgbx = ((v >> 16) & 0xFF) | (v & 0xFF00) | ((v & 0xFF) << 16) | np.uint32(0xFF000000)
        else:
            table = self._tables.get(self._pixelformat)
            if table is None:
                table = self._tables[self._pixelformat] = _table(self._pixelformat)
            raw = np.ctypeslib.as_array(C.cast(data, C.POINTER(C.c_uint16)), shape=(height, pitch // 2))
            rgbx = table[raw[:, :width]]
        self.at_image(rgbx)

    def _sample(self, left, right):
        """Audio callback for a single sample."""
        if self.audio_active:
            self._single_tone += struct.pack("<hh", left, right)

    def _sample_batch(self, data, frames):
        """Audio callback for a batch of samples."""
        if self.audio_active and self.at_audio is not None and frames:
            self.at_audio(C.string_at(data, frames * 4))
        return frames

    def _status(self, port, device, index, key):
        """Input callback: reports button, axis and touch pointer state to the core."""
        if port == 0 and device == POINTER and index == 0:
            if key == POINTER_X:
                return self.pointer_x
            if key == POINTER_Y:
                return self.pointer_y
            return int(self.pointer_pressed) if key == POINTER_PRESSED else 0
        if port != 0 or device != JOYPAD:
            return 0
        if key == JOYPAD_MASK:
            return self.input_mask & 0x7FFF
        return (self.input_mask >> key) & 1 if key < 16 else 0

    def _av_apply(self, av: _AvInfo):
        """Takes over the video and audio properties from the core."""
        self.av = AvInfo(av.geometry.base_width, av.geometry.base_height, av.timing.fps,
                         int(round(av.timing.sample_rate)))

    def load_game(self, rom: Path) -> None:
        """Loads the ROM file into the core."""
        data = Path(rom).read_bytes()
        self._rom_buffer = C.create_string_buffer(data, len(data))
        self._rom_path = str(rom).encode("utf-8")
        info = _GameInfo(self._rom_path, C.cast(self._rom_buffer, C.c_void_p), len(data), None)
        if not self._lib.retro_load_game(C.byref(info)):
            raise CoreError(f"Core could not load {rom}")
        self._loaded = True
        av = _AvInfo()
        self._lib.retro_get_system_av_info(C.byref(av))
        self._av_apply(av)

    def step(self) -> None:
        """Runs the core for one frame."""
        self._lib.retro_run()
        if self._single_tone:
            if self.at_audio is not None:
                self.at_audio(bytes(self._single_tone))
            self._single_tone.clear()

    def ram_blocks(self) -> dict[int, bytes]:
        """Memory as {start address: bytes}: GBA EWRAM and IWRAM, NDS main memory (used for the catches in the game)."""
        blocks = {}
        for start, pointer, length in getattr(self, "_memory_card", []):
            if start in (0x02000000, 0x03000000) and length <= 16 * 1024 * 1024 and start not in blocks:
                blocks[start] = C.string_at(pointer, length)
        if 0x02000000 not in blocks:
            pointer, size = self._lib.retro_get_memory_data(SYSTEM_RAM), self._lib.retro_get_memory_size(SYSTEM_RAM)
            if pointer and size:
                blocks[0x02000000] = C.string_at(pointer, size)
        return blocks

    def read(self, address: int, length: int) -> bytes:
        """A few bytes from the core's address space, e.g. the player position every frame."""
        for start, pointer, size in getattr(self, "_memory_card", []):
            if start <= address and address + length <= start + size:
                return C.string_at(pointer + address - start, length)
        return b""

    def sram(self) -> bytes:
        """The battery-backed save RAM."""
        pointer = self._lib.retro_get_memory_data(SAVE_RAM)
        size = self._lib.retro_get_memory_size(SAVE_RAM)
        return C.string_at(pointer, size) if pointer and size else b""

    def sram_set(self, data: bytes) -> None:
        """Copies at most as many bytes as the core's SRAM holds; the rest stays unchanged."""
        pointer = self._lib.retro_get_memory_data(SAVE_RAM)
        size = self._lib.retro_get_memory_size(SAVE_RAM)
        if pointer and size and data:
            data = bytes(data[:size])
            C.memmove(pointer, data, len(data))

    def state(self) -> bytes:
        """Serializes the core state."""
        size = self._lib.retro_serialize_size()
        buffer = C.create_string_buffer(size)
        if not self._lib.retro_serialize(buffer, size):
            raise CoreError("State could not be saved")
        return buffer.raw

    def state_load(self, data: bytes) -> bool:
        """Restores a serialized state; returns False if it was rejected."""
        if not data:
            return False
        buffer = C.create_string_buffer(bytes(data), len(data))
        return bool(self._lib.retro_unserialize(buffer, len(data)))

    @property
    def can_network(self) -> bool:
        """True if the core supports DS wireless via netpacket (melonDS DS)."""
        return self._network is not None

    def network_start(self, own_id: int, send, query) -> None:
        """Starts DS wireless: send(data, target) transmits a packet (target all = broadcast) and query() hands in arrived
        packets via network_receive; the core calls both."""
        self._network_send_py, self._network_query_py = send, query
        self._network_callbacks = (_NETWORK_SEND(self._network_send), _NETWORK_QUERY(self._network_query))
        self._network[0](own_id, *self._network_callbacks)

    def _network_send(self, flags, data, length, target):
        """Core callback: forwards an outgoing packet to the Python send function."""
        if data and length and self._network_send_py is not None:
            self._network_send_py(C.string_at(data, length), target)

    def _network_query(self):
        """Core callback: asks the Python side for arrived packets."""
        if self._network_query_py is not None:
            self._network_query_py()

    def network_receive(self, data: bytes, sender: int) -> None:
        """Hands an arrived packet to the core."""
        if self._network_callbacks is not None:
            buffer = C.create_string_buffer(data, len(data))
            self._network[1](buffer, len(data), sender)

    def network_stop(self) -> None:
        """Stops DS wireless."""
        if self._network_callbacks is not None:
            if self._network[2] is not None:
                self._network[2]()
            self._network_callbacks = None

    @property
    def can_link(self) -> bool:
        """True if the custom mGBA build with GBA link cable support is loaded (tools/mgba_build.py)."""
        try:
            self._lib.soullink_link_connect
        except AttributeError:
            return False
        return True

    def link_coordinator_new(self) -> int:
        """Creates a link cable coordinator shared by the cores of one process."""
        self._lib.soullink_link_new.restype = C.c_void_p
        return self._lib.soullink_link_new() or 0

    def link_coordinator_free(self, coordinator: int) -> None:
        """Frees a link cable coordinator."""
        self._lib.soullink_link_free.argtypes = [C.c_void_p]
        self._lib.soullink_link_free(coordinator)

    def link_connect(self, coordinator: int, wish_id: int) -> bool:
        """Connects this core to the coordinator with the wished player id."""
        self._lib.soullink_link_connect.argtypes = [C.c_void_p, C.c_int]
        self._lib.soullink_link_connect.restype = C.c_bool
        return bool(self._lib.soullink_link_connect(coordinator, wish_id))

    def link_disconnect(self) -> None:
        """Pulls the link cable of this core."""
        if self.can_link:
            self._lib.soullink_link_disconnect()

    def end(self) -> None:
        """Unloads the game and releases the core."""
        if not self._active:
            return
        self.network_stop()
        if self._loaded:
            self._lib.retro_unload_game()
            self._loaded = False
        self._lib.retro_deinit()
        self._active = False
