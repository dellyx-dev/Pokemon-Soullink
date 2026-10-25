"""Shared fixtures: language, test ROM paths and helpers to create test plugins."""

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
BUNDLED = Path(__file__).resolve().parents[1] / "plugins"

EMPTY_PLUGIN = """from soullink.plugin.api import Plugin


def create(api):
    return Plugin(api)
"""


def plugin_create(dir: Path, pid: str, code: str = EMPTY_PLUGIN, data: dict | None = None,
                   texts: dict[str, str] | None = None) -> Path:
    """Creates a test plugin folder <dir>/<pid>/ with plugin.json, __init__.py and language files (texts: abbreviation to
    content)."""
    path = Path(dir) / pid
    (path / "language").mkdir(parents=True)
    (path / "plugin.json").write_text(json.dumps({"version": "1.0.0", "author": "Test", "api": 1, **(data or {})}),
                                      encoding="utf-8")
    (path / "__init__.py").write_text(code, encoding="utf-8")
    if texts is None:
        texts = {"us": f"_name = {pid.title()}\n_description = Test plugin {pid}\n"}
    for abbreviation, content in texts.items():
        (path / "language" / f"{abbreviation}.txt").write_text(content, encoding="utf-8")
    return path


def plugin_module(pid: str, module: str | None = None):
    """Module of a bundled plugin, soullink_plugins.<pid>[.<module>] from /plugins, imported the way the loader does it."""
    from soullink.plugin.loader import import_

    return import_(BUNDLED, pid if module is None else f"{pid}.{module}")


def fake_gba(code: str) -> bytes:
    """Minimal GBA header: 0xC0 bytes, game code at 0xAC."""
    data = bytearray(0xC0)
    data[0xAC:0xB0] = code.encode("ascii")
    return bytes(data)


def fake_nds(code: str) -> bytes:
    """Minimal NDS header: title, game code at 0x0C."""
    data = bytearray(0x200)
    data[0:10] = b"POKEMON PL"
    data[0x0C:0x10] = code.encode("ascii")
    return bytes(data)


@pytest.fixture(autouse=True)
def english(monkeypatch):
    """Makes the tests run in English, independent of the system language of the machine."""
    from soullink import language

    monkeypatch.setattr(language, "system_language", lambda: "us")
    language.set_("us")
    yield
    for pid in list(language._plugin_dir):
        language.plugin_texts(pid, None)
    for name in [n for n in sys.modules if n == "soullink_plugins" or n.startswith("soullink_plugins.")]:
        del sys.modules[name]
    language.set_("us")


@pytest.fixture
def test_rom() -> Path:
    """Path of the GBA test ROM from SOULLINK_TEST_ROM; the test is skipped without it."""
    path = os.environ.get("SOULLINK_TEST_ROM")
    if not path or not Path(path).exists():
        pytest.skip("SOULLINK_TEST_ROM not set")
    return Path(path)


@pytest.fixture
def test_preset() -> Path:
    """Path of the randomizer preset from SOULLINK_TEST_PRESET; the test is skipped without it."""
    path = os.environ.get("SOULLINK_TEST_PRESET")
    if not path or not Path(path).exists():
        pytest.skip("SOULLINK_TEST_PRESET not set")
    return Path(path)
