"""Tests of the worker parts of plugins in the player process."""
import queue
import threading

import pytest

from conftest import plugin_create
from soullink.core.memory import SLOT_SIZE, SharedMemory
from soullink.plugin.worker import PluginParts

WORKER = '''
class Part:
    def __init__(self, core, job, shared):
        self.core, self.shared = core, shared
        shared.setdefault("player", []).append(job["nr"])
        self.images = 0
        shared.setdefault("calls", [])

    def ready(self):
        return {"can": self.core.can_link, "player": list(self.shared["player"])}

    def before_image(self):
        self.shared["calls"].append("before")

    def after_image(self):
        self.images += 1
        self.shared["calls"].append("after")
        return self.core.read(0x02000000, 4) + bytes([self.images])

    def command(self, data):
        if data == "still":
            return None
        if data == "broken":
            raise RuntimeError("broken in Command")
        if data == "large":
            self.after_image = lambda: bytes(1025)
            return None
        return {"echo": data}

    def end(self):
        self.shared["ended"] = True


def create(core, job, shared):
    return Part(core, job, shared)
'''

EVIL = '''
class Part:
    def after_image(self):
        raise ValueError("broken in Image")


def create(core, job, shared):
    return Part()
'''


class FakeCore:
    """Minimal core for worker part tests."""
    can_link = True

    @staticmethod
    def read(address, length):
        """Bytes of the core's memory."""
        return bytes(range(length))


class Events(list):
    """List that acts as the event queue."""

    def put(self, e):
        """Appends an event."""
        self.append(e)


def _plugin(dir, pid, worker=WORKER, module="worker"):
    """Creates a test plugin with a worker module."""
    path = plugin_create(dir, pid, data={"worker": module})
    (path / f"{module}.py").write_text(worker, encoding="utf-8")
    return path


def _entry(path, slot=0, module="worker"):
    """Job entry for the worker part of a plugin folder."""
    return {"id": path.name, "dir": str(path), "module": module, "slot": slot}


@pytest.fixture
def memory():
    """Shared memory for the tests."""
    s = SharedMemory()
    yield s
    s.close()
    s.release()


def test_part_ready_per_image_and_slot(tmp_path, memory):
    """Parts report ready, run per image and write their slot."""
    path = _plugin(tmp_path / "plugins", "one")
    events = Events()
    parts = PluginParts(FakeCore(), {"nr": 1, "plugins": [_entry(path, slot=3)]}, events)
    assert parts.ready() == {"one": {"can": True, "player": [1]}}
    for _ in range(2):
        parts.before_image()
        parts.after_image(memory)
    shared = parts.shared["one"]
    assert shared["calls"] == ["before", "after", "before", "after"]
    assert memory.slot_read(3) == (4, b"\x00\x01\x02\x03\x02")
    assert memory.slot_read(0) is None and events == []


def test_command_replies_as_event(tmp_path):
    """A command reply arrives as an event."""
    path = _plugin(tmp_path / "plugins", "one")
    events = Events()
    parts = PluginParts(FakeCore(), {"nr": 1, "plugins": [_entry(path)]}, events)
    parts.command("one", 5)
    parts.command("one", "still")
    parts.command("exists_not", 1)
    assert events == [("plugin", "one", {"echo": 5})]


def test_error_switches_only_the_part_off(tmp_path, memory):
    """An error switches off only the failing part."""
    dir = tmp_path / "plugins"
    good, evil = _plugin(dir, "good"), _plugin(dir, "evil", EVIL)
    events = Events()
    parts = PluginParts(FakeCore(), {"nr": 2, "plugins": [_entry(evil, 0), _entry(good, 1)]}, events)
    parts.after_image(memory)
    parts.after_image(memory)
    (kind, pid, text), = events
    assert (kind, pid) == ("plugin_error", "evil") and "ValueError: broken in Image" in text
    assert parts.active() == ["good"] and memory.slot_read(1)[0] == 4
    parts.command("good", "broken")
    assert events[-1][:2] == ("plugin_error", "good") and "RuntimeError: broken in Command" in events[-1][2]
    assert parts.active() == [] and parts.shared["good"]["ended"]
    parts.after_image(memory)
    parts.before_image()
    assert len(events) == 2


def test_too_many_bytes_are_an_error(tmp_path, memory):
    """Too many bytes for a slot are an error."""
    path = _plugin(tmp_path / "plugins", "one")
    events = Events()
    parts = PluginParts(FakeCore(), {"nr": 1, "plugins": [_entry(path)]}, events)
    parts.command("one", "large")
    parts.after_image(memory)
    assert events[0][:2] == ("plugin_error", "one") and str(SLOT_SIZE) in events[0][2]
    assert memory.slot_read(0) is None


def test_load_with_errors(tmp_path):
    """Loading with errors switches off only the failing parts."""
    dir = tmp_path / "plugins"
    _plugin(dir, "import_throws", "raise ImportError('gone')\n")
    _plugin(dir, "without_part", "def create(core, job, shared):\n    return None\n")
    _plugin(dir, "create_throws", "def create(core, job, shared):\n    raise KeyError('x')\n")
    plugin_create(dir, "without_file", data={"worker": "worker"})
    _plugin(dir, "ready_broken", "class T:\n    def ready(self):\n        return {'f': lambda: 1}\n\n\n"
                                     "def create(core, job, shared):\n    return T()\n")
    _plugin(dir, "good")
    entries = [_entry(dir / pid, i) for i, pid in enumerate(
        ("import_throws", "without_part", "create_throws", "without_file", "ready_broken", "good"))]
    events = Events()
    parts = PluginParts(FakeCore(), {"nr": 1, "plugins": entries}, events)
    assert {pid for _, pid, _ in events} == {"import_throws", "create_throws", "without_file"}
    assert parts.active() == ["ready_broken", "good"]
    assert parts.ready() == {"good": {"can": True, "player": [1]}}
    assert events[-1][:2] == ("plugin_error", "ready_broken") and parts.active() == ["good"]


def test_shared_dict_per_plugin_across_threads(tmp_path):
    """Threads of a process group share one dict per plugin."""
    path = _plugin(tmp_path / "plugins", "one")
    shared = {}
    parts = []

    def load(nr):
        """Loads the parts of one thread."""
        parts.append(PluginParts(FakeCore(), {"nr": nr, "plugins": [_entry(path)]}, Events(), shared))

    threads = [threading.Thread(target=load, args=(nr,)) for nr in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(shared["one"]["player"]) == [1, 2]
    assert all(t.shared is shared for t in parts)
    alone = PluginParts(FakeCore(), {"nr": 3, "plugins": [_entry(path)]}, Events())
    assert alone.shared["one"]["player"] == [3]


def test_disable_and_end(tmp_path, memory):
    """Parts can be disabled and ended."""
    dir = tmp_path / "plugins"
    one, two = _plugin(dir, "one"), _plugin(dir, "two")
    parts = PluginParts(FakeCore(), {"nr": 1, "plugins": [_entry(one, 0), _entry(two, 1)]}, Events())
    parts.disable("one")
    assert parts.active() == ["two"] and parts.shared["one"]["ended"]
    parts.after_image(memory)
    assert memory.slot_read(0) is None and memory.slot_read(1) is not None
    parts.end()
    assert parts.active() == [] and parts.shared["two"]["ended"]


def test_worker_loads_without_the_plugin_init(tmp_path):
    """The worker loads a part without running the plugin's __init__."""
    dir = tmp_path / "plugins"
    code = ("from pathlib import Path\nPath(__file__).with_name('init_ran.txt').write_text('yes')\n"
            "raise RuntimeError('no')\n")
    path = plugin_create(dir, "slim", code=code, data={"worker": "worker"})
    (path / "values.py").write_text("VALUE = 7\n", encoding="utf-8")
    (path / "worker.py").write_text("from .values import VALUE\n\n\nclass Part:\n    def ready(self):\n"
                                    "        return {'value': VALUE}\n\n\n"
                                    "def create(core, job, shared):\n    return Part()\n", encoding="utf-8")
    events = Events()
    parts = PluginParts(FakeCore(), {"nr": 1, "plugins": [_entry(path)]}, events)
    assert parts.ready() == {"slim": {"value": 7}} and events == []
    assert not (path / "init_ran.txt").exists()


def test_error_at_end_is_reported(tmp_path):
    """An error at shutdown is reported to the log."""
    dir = tmp_path / "plugins"
    code = ("class Part:\n    def end(self):\n        raise OSError('socket stuck')\n\n\n"
            "def create(core, job, shared):\n    return Part()\n")
    one, two = _plugin(dir, "one", code), _plugin(dir, "two", code)
    events = Events()
    data = tmp_path / "data"
    job = {"nr": 1, "base": str(data), "plugins": [_entry(one, 0), _entry(two, 1)]}
    parts = PluginParts(FakeCore(), job, events)
    parts.disable("one")
    (kind, pid, text), = events
    assert (kind, pid) == ("plugin_error", "one") and "OSError: socket stuck" in text
    data.mkdir()
    parts.end()
    assert len(events) == 1
    log = (data / "error.log").read_text(encoding="utf-8")
    assert "Plugin two" in log and "OSError: socket stuck" in log and "Plugin one" not in log
    assert not (tmp_path / "error.log").exists()


def test_without_plugins_in_job():
    """A job without plugins works."""
    parts = PluginParts(FakeCore(), {"nr": 1}, Events())
    assert parts.ready() == {} and parts.active() == []
    parts.before_image()
    parts.after_image(None)
    parts.end()


class RunCore:
    """Enough of libretro.Core for the worker loop: runs, delivers RAM and saves nothing; it claims netpacket support,
    which the worker must not open without a plugin."""
    can_network, can_link = True, False

    def network_start(self, *args):
        """Fails, since without a plugin the worker must not start a network."""
        raise AssertionError("no netpacket without the plugin")
    version = "fake"

    def __init__(self, dll, dir, options=None):
        """Creates the fake core with a fast clock."""
        self.av = type("Av", (), {"fps": 2000.0, "samplerate": 32768})()
        self.images = 0
        self.at_image = self.at_audio = None

    def load_game(self, rom):
        """Does nothing."""
        pass

    def sram_set(self, data):
        """Does nothing."""
        pass

    def state_load(self, data):
        """Never loads a state."""
        return False

    def sram(self):
        """Empty save RAM."""
        return b""

    def step(self):
        """Counts the frames."""
        self.images += 1

    def ram_blocks(self):
        """No RAM blocks."""
        return {}

    def read(self, address, length):
        """Bytes derived from the frame counter."""
        return bytes([self.images % 256]) * length

    def end(self):
        """Does nothing."""
        pass


class Commands:
    """Hands out the commands only after a few frames (otherwise not a single frame would run)."""

    def __init__(self, core_ref, plan):
        """Creates the command source with a plan of commands."""
        self.core_ref, self.plan = core_ref, list(plan)

    def get_nowait(self):
        """Gives the next planned command once the core exists."""
        core = self.core_ref.get("core")
        if self.plan and core is not None and core.images >= self.plan[0][0]:
            return self.plan.pop(0)[1]
        raise queue.Empty


def test_plugins_in_worker_flow(tmp_path, monkeypatch, memory):
    """Plugins run in the worker flow."""
    from soullink.core import worker

    path = _plugin(tmp_path / "plugins", "one")
    ref = {}

    def core_factory(*args, **kwargs):
        """Creates the fake core and remembers it."""
        ref["core"] = RunCore(*args, **kwargs)
        return ref["core"]

    monkeypatch.setattr(worker, "Core", core_factory)
    (tmp_path / "rom.gba").write_bytes(bytes(0xC0))
    job = {"nr": 1, "core": "x.dll", "rom": str(tmp_path / "rom.gba"), "system_dir": str(tmp_path),
               "sav": str(tmp_path / "game.sav"), "state": str(tmp_path / "state.state"),
               "state_candidates": [], "sram_candidates": [], "shm": memory.name, "audio": False,
               "options": {}, "plugins": [_entry(path, slot=2)]}
    commands = Commands(ref, [(0, ("tempo", 3)), (3, ("plugin", "one", "hello")), (9, ("end",))])
    events, audio = Events(), queue.Queue()
    audio.cancel_join_thread = lambda: None
    shared = {}
    worker._run(job, commands, events, audio, shared)
    ready = next(e[1] for e in events if e[0] == "ready")
    assert ready["plugins"] == {"one": {"can": False, "player": [1]}}
    assert set(ready) == {"fps", "samplerate", "version", "source", "plugins"}
    assert ("plugin", "one", {"echo": "hello"}) in events and events[-1] == ("ended",)
    seq, data = memory.slot_read(2)
    images = ref["core"].images
    assert images >= 9 and data[:4] == bytes([images % 256]) * 4
    calls = shared["one"]["calls"]
    assert calls.count("before") == calls.count("after") == images
    assert seq == 2 * images
    assert not any(e[0] == "plugin_error" for e in events)


def test_exception_in_the_core_still_ends_the_parts(tmp_path, monkeypatch, memory):
    """An exception in the core still ends the parts."""
    from soullink.core import worker

    class BrokenCore(RunCore):
        """Core whose step raises an exception."""

        def step(self):
            """Raises after the first frame."""
            super().step()
            if self.images >= 3:
                raise RuntimeError("core broken")

    path = _plugin(tmp_path / "plugins", "one")
    monkeypatch.setattr(worker, "Core", BrokenCore)
    (tmp_path / "rom.gba").write_bytes(bytes(0xC0))
    job = {"nr": 1, "core": "x.dll", "rom": str(tmp_path / "rom.gba"), "system_dir": str(tmp_path),
               "sav": str(tmp_path / "game.sav"), "state": str(tmp_path / "state.state"),
               "state_candidates": [], "sram_candidates": [], "shm": memory.name, "audio": False,
               "options": {}, "plugins": [_entry(path, slot=2)]}
    shared = {}
    with pytest.raises(RuntimeError, match="core broken"):
        worker._run(job, Commands({}, []), Events(), queue.Queue(), shared)
    assert shared["one"]["ended"]


REAL = '''
class Part:
    def __init__(self, core, job, shared):
        self.core, self.nr, self.shared, self.images = core, job["nr"], shared, 0
        shared.setdefault("player", []).append(self.nr)

    def ready(self):
        return {"nr": self.nr, "can_link": bool(self.core.can_link)}

    def after_image(self):
        self.images += 1
        return self.images.to_bytes(4, "little")

    def command(self, data):
        return {"echo": data, "all": sorted(self.shared["player"])}


def create(core, job, shared):
    return Part(core, job, shared)
'''


def test_real_process_group_with_plugin_part(tmp_path):
    """A real process group runs a plugin part."""
    import time

    from soullink import paths
    from soullink.player import ProcessGroup, PlayerProcess
    from test_link import _endless_loop

    if not paths.core_file("gba").exists():
        pytest.skip("mGBA core missing")
    path = _plugin(tmp_path / "plugins", "real", REAL)
    group = ProcessGroup(2)
    player = []
    for nr in (1, 2):
        dir = tmp_path / f"p{nr}"
        dir.mkdir()
        (dir / "rom.gba").write_bytes(_endless_loop())
        player.append(PlayerProcess(nr, dir, False, group=group, plugins=[_entry(path, slot=nr - 1)]))
    for sp in player:
        sp.start()
    events = []

    def wait(condition, seconds=30):
        """Polls until the condition holds or the time is over."""
        end = time.monotonic() + seconds
        while time.monotonic() < end and not condition():
            for sp in player:
                events.extend((sp.nr, e) for e in sp.fetch())
                sp.audio_fetch()
            time.sleep(0.02)
        return condition()

    try:
        assert wait(lambda: all(sp.ready_info for sp in player)), [sp.error for sp in player]
        assert [sp.ready_info["plugins"] for sp in player] == [{"real": {"nr": 1, "can_link": True}},
                                                                 {"real": {"nr": 2, "can_link": True}}]
        assert wait(lambda: all(sp.plugin_data(sp.nr - 1) for sp in player))
        first = int.from_bytes(player[0].plugin_data(0), "little")
        assert wait(lambda: int.from_bytes(player[0].plugin_data(0), "little") > first + 5)
        player[1].plugin_command("real", "hello")
        assert wait(lambda: (2, ("plugin", "real", {"echo": "hello", "all": [1, 2]})) in events, 5)
        assert not any(e[0] == "plugin_error" for _, e in events)
    finally:
        for sp in player:
            sp.end()
    assert all(sp.ended and not sp.error for sp in player)
