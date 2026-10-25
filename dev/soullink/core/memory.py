"""Shared memory between main and player process: input, touch pointer, double-buffered image and plugin slots."""
from __future__ import annotations

import struct
from multiprocessing import shared_memory

import numpy as np

MAX_B, MAX_H = 256, 384
HEADER = 24
POINTER_MAX = 0x7FFF
BUFFER = MAX_B * MAX_H * 4
SLOTS = HEADER + 2 * BUFFER
SLOT_COUNT, SLOT_SIZE = 8, 1024
_SLOT_HEADER = struct.Struct("<II")
_SLOT = _SLOT_HEADER.size + SLOT_SIZE
SIZE = SLOTS + SLOT_COUNT * _SLOT


class SharedMemory:
    """Shared memory block with the input mask, touch pointer, double-buffered image and plugin slots."""

    def __init__(self, name: str | None = None):
        """Creates a new block, or attaches to an existing one when a name is given."""
        self._owner = name is None
        if self._owner:
            self._shm = shared_memory.SharedMemory(create=True, size=SIZE)
        else:
            try:
                self._shm = shared_memory.SharedMemory(name=name, track=False)
            except TypeError:
                self._shm = shared_memory.SharedMemory(name=name)
        self._buf = self._shm.buf

    @property
    def name(self) -> str:
        """Name under which another process can attach."""
        return self._shm.name

    @property
    def input(self) -> int:
        """Pressed-button mask."""
        return struct.unpack_from("<I", self._buf, 0)[0]

    @input.setter
    def input(self, mask: int) -> None:
        """Pressed-button mask."""
        struct.pack_into("<I", self._buf, 0, mask & 0xFFFFFFFF)

    @property
    def pointer(self) -> tuple[int, int, bool]:
        """Touch pointer position in the libretro range of +-32767 relative to the whole frame, and whether it is pressed."""
        x, y, pressed = struct.unpack_from("<hhI", self._buf, 16)
        return x, y, bool(pressed)

    @pointer.setter
    def pointer(self, value: tuple[int, int, bool]) -> None:
        """Touch pointer position in the libretro range of +-32767 relative to the whole frame, and whether it is pressed."""
        x, y, pressed = value
        x, y = (max(-POINTER_MAX, min(POINTER_MAX, int(v))) for v in (x, y))
        struct.pack_into("<hhI", self._buf, 16, x, y, 1 if pressed else 0)

    def image_write(self, rgbx: np.ndarray) -> None:
        """Writes a frame into the inactive buffer and makes it the active one."""
        height, width = rgbx.shape
        seq, active = struct.unpack_from("<II", self._buf, 4)
        target = active ^ 1
        start = HEADER + target * BUFFER
        data = np.ascontiguousarray(rgbx, dtype=np.uint32).view(np.uint8).reshape(-1)
        self._buf[start:start + data.size] = data
        struct.pack_into("<HH", self._buf, 12, width, height)
        struct.pack_into("<I", self._buf, 8, target)
        struct.pack_into("<I", self._buf, 4, seq + 1)

    def image_read(self) -> tuple[int, int, int, bytes] | None:
        """Latest frame as (sequence, width, height, bytes); None if none was written yet."""
        seq, active, width, height = struct.unpack_from("<IIHH", self._buf, 4)
        if seq == 0:
            return None
        start = HEADER + active * BUFFER
        return seq, width, height, bytes(self._buf[start:start + width * height * 4])

    @staticmethod
    def _slot_start(slot: int) -> int:
        """Offset of a plugin slot; raises IndexError for an invalid slot number."""
        if not 0 <= slot < SLOT_COUNT:
            raise IndexError(f"Plugin slot {slot} does not exist (0-{SLOT_COUNT - 1})")
        return SLOTS + slot * _SLOT

    def slot_write(self, slot: int, data: bytes) -> None:
        """Writes the data of a plugin part into its slot (at most SLOT_SIZE bytes); readers discard half-written data."""
        start = self._slot_start(slot)
        if len(data) > SLOT_SIZE:
            raise ValueError(f"At most {SLOT_SIZE} bytes per plugin slot, got {len(data)}")
        seq = struct.unpack_from("<I", self._buf, start)[0]
        seq += seq % 2
        struct.pack_into("<II", self._buf, start, (seq + 1) & 0xFFFFFFFF, len(data))
        self._buf[start + _SLOT_HEADER.size:start + _SLOT_HEADER.size + len(data)] = data
        struct.pack_into("<I", self._buf, start, (seq + 2) & 0xFFFFFFFF or 2)

    def slot_read(self, slot: int) -> tuple[int, bytes] | None:
        """(sequence, data) of a slot, or None if nothing was written yet or a write is in progress."""
        start = self._slot_start(slot)
        for _ in range(3):
            seq, length = _SLOT_HEADER.unpack_from(self._buf, start)
            if seq == 0:
                return None
            if seq % 2:
                continue
            data = bytes(self._buf[start + _SLOT_HEADER.size:start + _SLOT_HEADER.size + min(length, SLOT_SIZE)])
            if struct.unpack_from("<I", self._buf, start)[0] == seq:
                return seq, data
        return None

    def close(self) -> None:
        """Detaches from the block."""
        self._buf = None
        self._shm.close()

    def release(self) -> None:
        """Deletes the block; only the creating process does this."""
        if self._owner:
            self._shm.unlink()
