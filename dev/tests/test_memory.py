"""Tests of the shared memory and the player process handle."""

import numpy as np
import pytest

from soullink.core.memory import SharedMemory


def test_input_and_image():
    """Input and image pass through shared memory."""
    main = SharedMemory()
    kind = SharedMemory(main.name)
    try:
        assert kind.image_read() is None
        main.input = 0b1001
        assert kind.input == 0b1001
        red = np.full((160, 240), 0xFF0000FF, np.uint32)
        green = np.full((160, 240), 0xFF00FF00, np.uint32)
        kind.image_write(red)
        kind.image_write(green)
        seq, width, height, data = main.image_read()
        assert (seq, width, height) == (2, 240, 160)
        assert data == green.tobytes()
    finally:
        kind.close()
        main.close()
        main.release()


def test_nds_image_256x384():
    """A DS frame of 256x384 passes through shared memory."""
    main = SharedMemory()
    kind = SharedMemory(main.name)
    try:
        image = np.arange(256 * 384, dtype=np.uint32).reshape(384, 256) | np.uint32(0xFF000000)
        kind.image_write(image)
        kind.image_write(image[::-1])
        seq, width, height, data = main.image_read()
        assert (seq, width, height) == (2, 256, 384)
        assert data == np.ascontiguousarray(image[::-1]).tobytes()
    finally:
        kind.close()
        main.close()
        main.release()


def test_pointer_round_trip():
    """The touch pointer survives a round trip."""
    main = SharedMemory()
    kind = SharedMemory(main.name)
    try:
        assert kind.pointer == (0, 0, False)
        main.input = 0xFFFF
        main.pointer = (-32767, 14165, True)
        assert kind.pointer == (-32767, 14165, True)
        assert kind.input == 0xFFFF
        kind.image_write(np.full((160, 240), 0xFF0000FF, np.uint32))
        assert kind.pointer == (-32767, 14165, True)
        main.pointer = (32767, -1, False)
        assert kind.pointer == (32767, -1, False)
    finally:
        kind.close()
        main.close()
        main.release()


def test_pointer_is_clamped():
    """The touch pointer is clamped to the valid range."""
    s = SharedMemory()
    try:
        s.pointer = (40000, -40000, 1)
        assert s.pointer == (32767, -32767, True)
    finally:
        s.close()
        s.release()


def test_player_process_ignores_a_frame_without_size():
    """The player process ignores a frame without size."""
    from soullink.player import PlayerProcess

    sp = PlayerProcess(1, ".", audio=False)
    sp._memory = SharedMemory()
    try:
        sp._memory.image_write(np.zeros((0, 0), np.uint32))
        assert sp.image() is None
    finally:
        sp._memory.close()
        sp._memory.release()


def test_plugin_slots():
    """Plugin slots store and return data."""
    from soullink.core.memory import SLOT_COUNT, SLOT_SIZE

    main = SharedMemory()
    kind = SharedMemory(main.name)
    try:
        assert SLOT_COUNT == 8 and SLOT_SIZE == 1024
        assert all(main.slot_read(i) is None for i in range(SLOT_COUNT))
        kind.slot_write(0, b"first")
        kind.slot_write(7, bytes(range(256)) * 4)
        kind.slot_write(0, b"second")
        assert main.slot_read(0) == (4, b"second")
        assert main.slot_read(7) == (2, bytes(range(256)) * 4)
        kind.slot_write(0, b"")
        assert main.slot_read(0) == (6, b"")
        with pytest.raises(ValueError):
            kind.slot_write(1, bytes(SLOT_SIZE + 1))
        with pytest.raises(IndexError):
            kind.slot_write(SLOT_COUNT, b"x")
        assert main.slot_read(1) is None
        kind.image_write(np.full((384, 256), 0xFFFFFFFF, np.uint32))
        assert main.slot_read(7) == (2, bytes(range(256)) * 4)
    finally:
        kind.close()
        main.close()
        main.release()


def test_plugin_slot_during_a_write():
    """A plugin slot read during a write returns nothing."""
    import struct

    from soullink.core.memory import SLOTS

    s = SharedMemory()
    try:
        s.slot_write(2, b"old")
        start = SLOTS + 2 * (8 + 1024)
        struct.pack_into("<I", s._buf, start, 3)
        assert s.slot_read(2) is None
    finally:
        s.close()
        s.release()


def test_player_process_plugins_in_job_command_and_slot(monkeypatch, tmp_path):
    """The player process passes plugins, commands and slots on."""
    import queue

    from soullink import player as player_module
    from soullink.player import PlayerProcess

    started = []

    class FakeCtx:
        """Fake multiprocessing context."""
        Queue = queue.Queue

        class Process:
            """Fake process that only records its arguments."""

            def __init__(self, target, args, name, daemon):
                """Records the arguments."""
                started.append(args[0])

            def start(self):
                """Does nothing."""
                pass

    monkeypatch.setattr(player_module, "_CTX", FakeCtx)
    plugins = [{"id": "one", "dir": str(tmp_path / "one"), "module": "worker", "slot": 1}]
    sp = PlayerProcess(1, tmp_path, audio=False, plugins=plugins, base=tmp_path / "data")
    sp.start()
    try:
        assert started[0]["plugins"] == plugins and started[0]["base"] == str(tmp_path / "data")
        assert PlayerProcess(2, tmp_path, audio=False).plugins == []
        sp.plugin_command("one", {"on": True})
        sp.plugin_disable("one")
        assert sp._commands.get_nowait() == ("plugin", "one", {"on": True})
        assert sp._commands.get_nowait() == ("plugin_disable", "one")
        assert sp.plugin_data(1) is None
        kind = SharedMemory(sp._memory.name)
        kind.slot_write(1, b"data")
        kind.close()
        assert sp.plugin_data(1) == b"data" and sp.plugin_data(None) is None
    finally:
        sp._memory.close()
        sp._memory.release()
