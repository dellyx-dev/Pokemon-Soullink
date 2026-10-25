"""Tests of the portable build folder and the release archive (without running PyInstaller)."""

import importlib.util
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def build():
    """The build.py module from the project folder."""
    spec = importlib.util.spec_from_file_location("soullink_build_script", ROOT / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dist(dir: Path, exe: bytes = b"new") -> Path:
    """A fake PyInstaller dist folder with the program entries."""
    (dir / "_internal").mkdir(parents=True)
    (dir / "_internal" / "python313.dll").write_bytes(b"dll")
    (dir / "language").mkdir()
    (dir / "language" / "de.txt").write_text("a = b\n", encoding="utf-8")
    (dir / "Pokemon-Soullink.exe").write_bytes(exe)
    return dir


def test_install_replaces_program_and_keeps_user_data(build, tmp_path):
    """Program files and bundled plugins are replaced; sessions, presets, own plugins and settings stay."""
    target = tmp_path / "build"
    (target / "_internal").mkdir(parents=True)
    (target / "_internal" / "stale.dll").write_bytes(b"old")
    (target / "Pokemon-Soullink.exe").write_bytes(b"old")
    (target / "sessions" / "S").mkdir(parents=True)
    (target / "sessions" / "S" / "session.json").write_text("{}", encoding="utf-8")
    (target / "presets").mkdir()
    (target / "presets" / "Pokemon Standard.rnqs").write_bytes(b"own")
    (target / "plugins" / "soullink").mkdir(parents=True)
    (target / "plugins" / "soullink" / "old.py").write_text("", encoding="utf-8")
    (target / "plugins" / "mine").mkdir()
    (target / "plugins" / "mine" / "plugin.json").write_text("{}", encoding="utf-8")
    (target / "settings.json").write_text("{}", encoding="utf-8")

    build.install(_dist(tmp_path / "dist"), target)

    assert (target / "Pokemon-Soullink.exe").read_bytes() == b"new"
    assert not (target / "_internal" / "stale.dll").exists()
    assert (target / "sessions" / "S" / "session.json").exists()
    assert (target / "presets" / "Pokemon Standard.rnqs").read_bytes() == b"own"
    assert (target / "settings.json").exists()
    assert (target / "plugins" / "mine" / "plugin.json").exists()
    assert not (target / "plugins" / "soullink" / "old.py").exists()
    assert (target / "plugins" / "soullink" / "plugin.json").exists()
    assert not list((target / "plugins").rglob("tests"))
    assert all((target / dir).is_dir() for dir in ("roms/gba", "roms/nds", "sound", "language"))


def test_release_zip_contains_only_program_and_empty_folders(build, tmp_path, monkeypatch):
    """The archive has one top folder with program, plugins without tests and the empty user folders."""
    monkeypatch.setattr(build, "RELEASE", tmp_path / "release")
    archive = build.release_zip(_dist(tmp_path / "dist"), "test")
    names = zipfile.ZipFile(archive).namelist()
    assert all(n.startswith("Pokemon-Soullink/") for n in names)
    inner = {n.removeprefix("Pokemon-Soullink/") for n in names}
    assert {"Pokemon-Soullink.exe", "roms/gba/README.txt", "roms/nds/README.txt", "sessions/README.txt",
            "sound/README.txt", "presets/Pokemon Standard.rnqs", "plugins/soullink/plugin.json"} <= inner
    assert not [n for n in inner if "/tests/" in n or n.endswith("conftest.py") or "__pycache__" in n]
    assert not [n for n in inner if n.endswith((".gba", ".nds", ".sav", ".state")) or n == "settings.json"]


def test_assemble_adds_the_readme(build, tmp_path):
    """The program folder gets the project README next to cores, randomizer and licences."""
    (tmp_path / "dist").mkdir()
    dist = build.assemble(tmp_path / "dist")
    assert (dist / "README.md").read_bytes() == (ROOT / "README.md").read_bytes()
    assert (dist / "core" / "mgba_libretro.dll").is_file() and (dist / "licenses" / "GPL-3.0.txt").is_file()
