"""Test helpers for plugins/<id>/tests/: German language (autouse), plugin_app, ROM copies and worker parts with a fake
core. Fixture names are unique across all plugins; a plugin's own fixtures are prefixed with its id."""
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BUNDLED
from conftest import english  # noqa: F401
from conftest import plugin_create as _plugin_create

DEV = BUNDLED.parent


@pytest.fixture
def plugin_create():
    """Creates a test plugin: plugin_create(dir, id, code=…, data=…, texts=…) → folder of the plugin."""
    return _plugin_create


@pytest.fixture
def plugin_app(monkeypatch, tmp_path):
    """plugin_app(*ids) → dummy app with copies of these bundled plugins under <base>/plugins, switched on."""
    from ui_helpers import dummy_app

    apps = []

    def create(*ids):
        """Creates an app with the given bundled plugins enabled."""
        app = dummy_app(monkeypatch, tmp_path)
        apps.append(app)
        for pid in ids:
            shutil.copytree(BUNDLED / pid, tmp_path / "plugins" / pid,
                            ignore=shutil.ignore_patterns("tests", "__pycache__"))
        app.plugins.new_read()
        for pid in ids:
            app.plugins.set_(pid, True)
        assert [i.id for i, _ in app.plugins.active()] == sorted(ids)
        return app

    yield create
    for app in apps:
        app.close()


def _rom_from(variable: str) -> Path:
    """ROM path from an environment variable; the test is skipped if it is not set."""
    path = os.environ.get(variable)
    if not path or not Path(path).exists():
        pytest.skip(f"{variable} not set")
    return Path(path)


@pytest.fixture
def gba_rom() -> Path:
    """Real GBA ROM from SOULLINK_TEST_ROM (e.g. a copy of Emerald)."""
    return _rom_from("SOULLINK_TEST_ROM")


@pytest.fixture
def nds_rom() -> Path:
    """Real NDS ROM from SOULLINK_TEST_NDS (e.g. a copy of SoulSilver or Platinum)."""
    return _rom_from("SOULLINK_TEST_NDS")


@pytest.fixture
def gba_endless_rom() -> bytes:
    """The smallest runnable GBA ROM: ARM `b .` at the entry point, the rest zeros (for real cores without a real game)."""
    rom = bytearray(0x8000)
    rom[0:4] = struct.pack("<I", 0xEAFFFFFE)
    rom[0xAC:0xB0] = b"TEST"
    return bytes(rom)


class Events(list):
    """Stands in for the event queue of the worker: collects what the parts report."""

    def put(self, e):
        """Appends an event."""
        self.append(e)


def bundled_entry(plugin_id: str, slot=None) -> dict:
    """Entry for job["plugins"]: the worker part of a bundled plugin (from /plugins)."""
    return {"id": plugin_id, "dir": str(BUNDLED / plugin_id), "module": "worker", "slot": slot}


@pytest.fixture
def worker_parts():
    """worker_parts(core, plugin_id, nr=1, shared=None, **job) → (PluginParts, events): the worker part of a bundled
    plugin, loaded as in the player process (without __init__.py)."""
    from soullink.plugin.worker import PluginParts

    def build(core, plugin_id, nr=1, shared=None, **job):
        """Creates the worker parts for a core and returns them with the events list."""
        events = Events()
        parts = PluginParts(core, {"nr": nr, "plugins": [bundled_entry(plugin_id)], **job}, events,
                            shared)
        return parts, events

    return build


@pytest.fixture
def worker_without_pygame():
    """Runs worker_without_pygame(plugin_id, core_fields, job) in an own Python process and returns its output: the active
    parts, the keys of the ready info and whether pygame was loaded; core_fields are the attributes of the fake core."""
    def check(plugin_id: str, core_fields: dict, job: dict) -> str:
        """Runs the check for one plugin in an own Python process."""
        code = (
            "import sys\n"
            "from soullink.plugin.worker import PluginParts\n"
            f"K = type('K', (), {core_fields!r})\n"
            "class Q:\n"
            "    def put(self, x): print(x)\n"
            f"t = PluginParts(K(), {{**{job!r}, 'plugins': [{bundled_entry(plugin_id)!r}]}}, Q())\n"
            "b = t.ready()\n"
            "print(t.active(), {k: sorted(v) for k, v in b.items()}, 'pygame' in sys.modules)\n"
            "t.end()\n"
        )
        output = subprocess.run([sys.executable, "-c", code], cwd=DEV, capture_output=True, text=True,
                                 timeout=60, env={**os.environ, "PYTHONPATH": str(DEV)})
        assert output.returncode == 0, output.stderr
        return output.stdout.strip()

    return check
