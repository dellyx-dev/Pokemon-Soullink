"""Worker part of the Other players plugin: position per shown frame into the slot, without __init__ and pygame."""
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import fake_gba
from pokemon_helpers import G3_PC, g3_pc_set, gmain_set

PLUGIN = Path(__file__).resolve().parents[1]
DEV = Path(__file__).resolve().parents[3]
ENTRY = {"id": "coplayer", "dir": str(PLUGIN), "module": "worker", "slot": 3}


class Events(list):
    """List that acts as the event queue."""

    def put(self, e):
        """Appends an event."""
        self.append(e)


class FireRedCore:
    """Enough of a core for the worker part: RAM as in German FireRed with the player on Route 1 (12, 7)."""

    def __init__(self):
        """Builds the fake RAM."""
        ewram, iwram = bytearray(0x40000), bytearray(0x8000)
        g3_pc_set(ewram, 0x29384, G3_PC)
        struct.pack_into("<III", iwram, 0x5008, 0x02025590, 0x020245EC, 0x02029384)
        gmain_set(iwram, 0x3040, False)
        struct.pack_into("<hhbb", ewram, 0x25590, 12, 7, 3, 19)
        self.blocks = {0x02000000: ewram, 0x03000000: iwram}
        self.image_active = True
        self.dumps = 0

    def ram_blocks(self):
        """The RAM blocks, counting the dumps."""
        self.dumps += 1
        return {k: bytes(v) for k, v in self.blocks.items()}

    def read(self, address, length):
        """Bytes from the fake RAM."""
        for start, data in self.blocks.items():
            if start <= address and address + length <= start + len(data):
                return bytes(data[address - start:address - start + length])
        return b""


def _job(tmp_path, code="BPRD"):
    """Job for the coplayer worker part with a ROM in the folder."""
    rom = tmp_path / "rom.gba"
    rom.write_bytes(fake_gba(code))
    return {"nr": 1, "rom": str(rom), "plugins": [ENTRY], "base": str(tmp_path)}


def test_part_loads_without_init_and_writes_the_position(tmp_path):
    """The worker part loads without the plugin __init__ and writes the position."""
    from soullink import world
    from soullink.core.memory import SharedMemory
    from soullink.plugin.worker import PluginParts

    core, events, memory = FireRedCore(), Events(), SharedMemory()
    try:
        parts = PluginParts(core, _job(tmp_path), events)
        assert parts.active() == ["coplayer"] and not events
        assert not hasattr(sys.modules["soullink_plugins.coplayer"], "CoplayerPlugin")
        assert parts.ready() == {"coplayer": {"reader": "WorldReader"}}
        parts.before_image()
        parts.after_image(memory)
        seq, data = memory.slot_read(3)
        assert world.unpack(data) == world.Location(3, 19, 12, 7, 0x08011085 ^ 0x08011679, False)
        core.image_active = False
        parts.after_image(memory)
        assert memory.slot_read(3)[0] == seq and core.dumps == 1
        core.image_active = True
        struct.pack_into("<hhbb", core.blocks[0x02000000], 0x25590, 0, 0, 0, 0)
        parts.after_image(memory)
        assert memory.slot_read(3) == (seq + 2, b"")
        assert not events
        parts.end()
    finally:
        memory.close()
        memory.release()


def test_without_pokemon_game_no_part(tmp_path):
    """Without a Pokemon game there is no part."""
    from soullink.plugin.worker import PluginParts

    events = Events()
    parts = PluginParts(FireRedCore(), _job(tmp_path, "AMKE"), events)
    assert parts.active() == [] and not events


def test_in_worker_no_pygame(tmp_path):
    """The worker part does not import pygame."""
    without_slot = {**ENTRY, "slot": None}
    code = (
        "import sys\n"
        "from soullink.plugin.worker import PluginParts\n"
        "class K:\n"
        "    image_active = True\n"
        "    def ram_blocks(self): return {}\n"
        "    def read(self, a, n): return b''\n"
        f"job = {{'rom': {str(_job(tmp_path)['rom'])!r}, 'plugins': [{without_slot!r}]}}\n"
        "e = []\n"
        "class Q:\n"
        "    def put(self, x): e.append(x)\n"
        "t = PluginParts(K(), job, Q())\n"
        "t.after_image(None)\n"
        "print(t.active(), e, 'pygame' in sys.modules)\n"
    )
    output = subprocess.run([sys.executable, "-c", code], cwd=DEV, capture_output=True, text=True,
                             timeout=60, env={**os.environ, "PYTHONPATH": str(DEV)})
    assert output.stdout.strip() == "['coplayer'] [] False", output.stderr


def test_real_worker_with_rom_sends_position_data(test_rom, tmp_path):
    """A real worker with a ROM sends position data (needs a test ROM)."""
    from soullink import paths, world
    from soullink.player import PlayerProcess

    if not paths.core_file("gba").exists():
        pytest.skip("mGBA core missing")
    dir = tmp_path / "p1"
    dir.mkdir()
    rom = dir / "rom.gba"
    shutil.copyfile(test_rom, rom)
    sp = PlayerProcess(1, dir, False, plugins=[{**ENTRY, "slot": 0}], base=tmp_path)
    events = []

    def wait(condition, seconds=30):
        """Polls until the condition holds or the time is over."""
        end = time.monotonic() + seconds
        while time.monotonic() < end and not condition():
            events.extend(sp.fetch())
            sp.audio_fetch()
            time.sleep(0.02)
        return condition()

    def seq():
        """Sequence number of the slot."""
        read = sp._memory.slot_read(0)
        return read[0] if read else 0

    try:
        sp.start()
        assert wait(lambda: sp.ready_info is not None), sp.error
        assert sp.ready_info["plugins"] == {"coplayer": {"reader": "WorldReader"}}
        assert wait(lambda: seq() > 0)
        first = seq()
        assert wait(lambda: seq() >= first + 2 * 30)
        assert sp.plugin_data(0) == b""
        sp.tempo(8)
        press = iter(range(10 ** 9))

        def position():
            """Next position delivered through the slot."""
            n = next(press)
            sp.input(((1 << 8) if (n // 40) % 3 else (1 << 3)) if n % 2 else 0)
            return world.unpack(sp.plugin_data(0))

        assert wait(lambda: position() is not None, 120)
        location = world.unpack(sp.plugin_data(0))
        assert location.camera is None and not location.battle and (location.group, location.number) != (0, 0)
        assert not any(e[0] in ("plugin_error", "error") for e in events), events
    finally:
        sp.end()
        rom.unlink(missing_ok=True)
    assert sp.ended and not sp.error
