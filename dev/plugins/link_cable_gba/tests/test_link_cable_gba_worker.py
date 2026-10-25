"""Worker part of Link cable GBA: coordinator in "shared", commands on/off, a real process group with mGBA."""
import queue
import shutil
import threading
import time
from pathlib import Path

import pytest

from soullink import paths

PLUGIN = Path(__file__).resolve().parents[1]
ID = "link_cable_gba"
ENTRY = {"id": ID, "dir": str(PLUGIN), "module": "worker", "slot": None}


class FakeCore:
    """Link cable part of core.libretro.Core; all cores of a group write into the same log."""

    def __init__(self, log, can=True, slow=0.0):
        """Creates the fake core with a log, link support and an optional delay."""
        self.log, self.can_link, self.slow = log, can, slow

    def link_coordinator_new(self):
        """Creates a coordinator after the delay."""
        time.sleep(self.slow)
        self.log.append(("new",))
        return 4711 + len(self.log)

    def link_connect(self, coordinator, wish_id):
        """Logs the connection."""
        self.log.append(("connect", coordinator, wish_id))
        return True

    def link_disconnect(self):
        """Logs the disconnection."""
        self.log.append(("disconnect",))


def test_commands_plug_in_and_out_with_a_coordinator(worker_parts):
    """Plug commands connect and disconnect through the coordinator."""
    log, shared = [], {}
    one, e1 = worker_parts(FakeCore(log), ID, nr=1, shared=shared, group=True)
    two, e2 = worker_parts(FakeCore(log), ID, nr=2, shared=shared, group=True)
    assert one.ready() == two.ready() == {ID: {"link": True}}
    one.command(ID, True)
    two.command(ID, True)
    one.command(ID, True)
    assert log == [("new",), ("connect", 4712, 0), ("connect", 4712, 1)]
    assert e1 == [("plugin", ID, True)] * 2 and e2 == [("plugin", ID, True)]
    one.command(ID, False)
    one.command(ID, False)
    assert log[3:] == [("disconnect",)] and e1[-1] == ("plugin", ID, False)
    two.end()
    assert log[4:] == [("disconnect",)]
    one.end()
    assert len(log) == 5


def test_coordinator_is_created_once_even_when_plugging_simultaneously(worker_parts):
    """The coordinator is created once even with simultaneous plug-ins."""
    log, shared, parts = [], {}, {}
    start = threading.Barrier(4)

    def player(nr):
        """Thread body of one player plugging in."""
        part, _ = worker_parts(FakeCore(log, slow=0.05), ID, nr=nr, shared=shared, group=True)
        parts[nr] = part
        start.wait()
        part.command(ID, True)

    threads = [threading.Thread(target=player, args=(nr,)) for nr in (1, 2, 3, 4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    connected = [p for p in log if p[0] == "connect"]
    assert log.count(("new",)) == 1 and len(shared[ID]) == 1
    assert len({p[1] for p in connected}) == 1
    assert sorted(p[2] for p in connected) == [0, 1, 2, 3]


def test_without_group_no_part_and_core_without_link(worker_parts):
    """Without a group or link support there is no part."""
    parts, events = worker_parts(FakeCore([]), ID, group=False)
    assert parts.active() == [] and parts.ready() == {} and events == []
    log = []
    parts, events = worker_parts(FakeCore(log, can=False), ID, group=True)
    assert parts.ready() == {ID: {"link": False}}
    parts.command(ID, True)
    assert events == [("plugin", ID, False)] and log == []


def test_in_worker_no_pygame(worker_without_pygame):
    """The worker part does not import pygame."""
    assert worker_without_pygame(ID, {"can_link": False}, {"nr": 1, "group": True}) == \
        "['link_cable_gba'] {'link_cable_gba': ['link']} False"


def test_core_crash_pulls_the_cable(tmp_path, monkeypatch):
    """A core crash pulls the cable."""
    from soullink.core import worker
    from soullink.core.memory import SharedMemory

    log = []

    class BrokenCore(FakeCore):
        """Fake core that crashes in step()."""
        version, image_active = "fake", True

        def __init__(self, *args, **kwargs):
            """Creates the core with the shared log."""
            super().__init__(log)
            self.av = type("Av", (), {"fps": 2000.0, "samplerate": 32768})()
            self.images = 0

        def load_game(self, rom):
            """Does nothing."""
            pass

        def sram(self):
            """Empty save RAM."""
            return b""

        def step(self):
            """Counts the frames and crashes after the cable was plugged in."""
            self.images += 1
            if self.images == 3:
                self.log.append(("plug_in",))
            if self.images >= 10:
                raise RuntimeError("core broken")

    class Events(list):
        """List that acts as the event queue."""
        put = list.append

    class Commands:
        """Command source that plugs the cable in once."""

        def __init__(self):
            """Starts with nothing given."""
            self.given = False

        def get_nowait(self):
            """Gives the plug-in command once."""
            if not self.given and ("plug_in",) in log:
                self.given = True
                return ("plugin", ID, True)
            raise queue.Empty

    monkeypatch.setattr(worker, "Core", BrokenCore)
    memory = SharedMemory()
    try:
        job = {"nr": 1, "core": "x.dll", "rom": str(tmp_path / "rom.gba"), "system_dir": str(tmp_path),
                   "sav": str(tmp_path / "game.sav"), "state": str(tmp_path / "state.state"),
                   "state_candidates": [], "sram_candidates": [], "shm": memory.name, "audio": False,
                   "options": {}, "plugins": [ENTRY], "group": True, "base": str(tmp_path)}
        with pytest.raises(RuntimeError, match="core broken"):
            worker._run(job, Commands(), Events(), queue.Queue(), {})
    finally:
        memory.close()
        memory.release()
    assert [p[0] for p in log] == ["plug_in", "new", "connect", "disconnect"]


def _group(tmp_path, rom: bytes | Path):
    """Process group of two players with the ROM."""
    from soullink.player import ProcessGroup, PlayerProcess

    if not paths.core_file("gba").exists():
        pytest.skip("mGBA core missing")
    group = ProcessGroup(2)
    player = []
    for nr in (1, 2):
        dir = tmp_path / f"p{nr}"
        dir.mkdir()
        if isinstance(rom, Path):
            shutil.copyfile(rom, dir / "rom.gba")
        else:
            (dir / "rom.gba").write_bytes(rom)
        player.append(PlayerProcess(nr, dir, False, group=group, plugins=[ENTRY], base=tmp_path))
    return group, player


class _Observer:
    """Fetches events and audio, remembers the replies of the worker part and counts the cores' frames."""

    def __init__(self, player):
        """Creates the observer for the players."""
        self.player, self.events = player, []
        self.connected = {sp.nr: None for sp in player}

    def round_(self):
        """Fetches events and audio of all players once."""
        for sp in self.player:
            for e in sp.fetch():
                self.events.append((sp.nr, e))
                if e[:2] == ("plugin", ID):
                    self.connected[sp.nr] = e[2]
            sp.audio_fetch()

    def wait(self, condition, seconds=30):
        """Polls until the condition holds or the time is over."""
        end = time.monotonic() + seconds
        while time.monotonic() < end and not condition():
            self.round_()
            time.sleep(0.005)
        return condition()

    def images(self) -> dict[int, int]:
        """Frame counters in shared memory (exact, since polling misses frames that come in quick succession)."""
        return {sp.nr: (sp._memory.image_read() or (0,))[0] for sp in self.player}

    def images_in(self, seconds):
        """Frames produced during the given seconds."""
        self.wait(lambda: False, 0.2)
        before = self.images()
        self.wait(lambda: False, seconds)
        return {nr: n - before[nr] for nr, n in self.images().items()}

    def error(self):
        """Plugin error events seen so far."""
        return [e for _, e in self.events if e[0] in ("plugin_error", "error")]


def test_real_group_connects_through_the_plugin(tmp_path, gba_endless_rom):
    """A real group connects through the plugin (needs a test ROM)."""
    group, player = _group(tmp_path, gba_endless_rom)
    b = _Observer(player)
    try:
        for sp in player:
            sp.start()
        assert b.wait(lambda: all(sp.ready_info for sp in player)), [sp.error for sp in player]
        assert [sp.ready_info["plugins"] for sp in player] == [{ID: {"link": True}}] * 2
        assert not {"link", "network_port"} & set(player[0].ready_info)
        for sp in player:
            sp.plugin_command(ID, True)
        assert b.wait(lambda: all(b.connected.values()), 5)
        for sp in player:
            sp.plugin_command(ID, False)
        assert b.wait(lambda: b.connected == {1: False, 2: False}, 5)
        assert not b.error()
    finally:
        for sp in player:
            sp.end()
    assert all(sp.ended and not sp.error for sp in player)
    assert b.wait(lambda: not group.alive, 5)


def test_real_rom_in_sync(gba_rom, tmp_path):
    """Two real cores run in sync (needs a test ROM)."""
    group, player = _group(tmp_path, gba_rom)
    b = _Observer(player)
    try:
        for sp in player:
            sp.start()
        assert b.wait(lambda: all(sp.ready_info for sp in player)), [sp.error for sp in player]
        free = b.images_in(1.0)
        for sp in player:
            sp.plugin_command(ID, True)
        assert b.wait(lambda: all(b.connected.values()), 5)
        connected = b.images_in(2.0)
        player[0].pause(True)
        paired = b.images_in(1.0)
        for sp in player:
            sp.plugin_command(ID, False)
        assert b.wait(lambda: b.connected == {1: False, 2: False}, 5)
        separated = b.images_in(1.0)
        player[0].pause(False)
        print("frames free/s", free, "connected/2 s", connected, "partner waits/s", paired, "separated/s", separated)
        assert min(free.values()) > 50 and min(connected.values()) > 100
        assert paired[2] < 25
        assert separated[2] > 50
        assert not b.error(), b.error()
    finally:
        for sp in player:
            sp.end()
        for sp in player:
            (sp.dir / "rom.gba").unlink(missing_ok=True)
    assert all(sp.ended and not sp.error for sp in player)
