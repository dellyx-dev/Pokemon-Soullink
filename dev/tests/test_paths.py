"""Tests of the path helpers."""

import sys
from pathlib import Path

from soullink import paths


def test_base_from_environment(monkeypatch, tmp_path):
    """The data directory can come from the environment."""
    monkeypatch.setenv("SOULLINK_BASE", str(tmp_path))
    assert paths.base_dir() == tmp_path


def test_base_is_the_dev_folder(monkeypatch):
    """From source the data directory is dev/, where plugins, language files and licences live too."""
    monkeypatch.delenv("SOULLINK_BASE", raising=False)
    base = paths.base_dir()
    assert (base / "soullink").is_dir() and (base / "plugins").is_dir()


def test_core_file_fits_the_platform():
    """The core file name fits the platform."""
    core = paths.core_file()
    assert core.suffix == ".dll"
    assert core.exists() and core.stem == "mgba_libretro"


def test_core_file_per_system():
    """Each system has its own core file."""
    assert paths.core_file("gba").stem == "mgba_libretro"
    nds = paths.core_file("nds")
    assert nds.stem == "melondsds_libretro" and nds.exists()


def test_randomizer_jar_present():
    """The randomizer jar is present."""
    assert paths.randomizer_jar().exists()


def _java(home: Path) -> Path:
    """Creates an empty java.exe below home/bin and returns it."""
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "java.exe").write_bytes(b"")
    return home / "bin" / "java.exe"


def _no_java(monkeypatch, tmp_path):
    """Removes every way to find Java: JAVA_HOME, PATH and Program Files."""
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr(paths.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramW6432", str(tmp_path / "pf"))


def test_java_from_java_home(monkeypatch, tmp_path):
    """JAVA_HOME wins over everything else."""
    _no_java(monkeypatch, tmp_path)
    java = _java(tmp_path / "jdk")
    monkeypatch.setenv("JAVA_HOME", str(tmp_path / "jdk"))
    assert paths.java_program() == java


def test_java_from_path(monkeypatch, tmp_path):
    """Without JAVA_HOME the java on PATH is used."""
    _no_java(monkeypatch, tmp_path)
    found = tmp_path / "x" / "java.exe"
    monkeypatch.setattr(paths.shutil, "which", lambda name: str(found))
    assert paths.java_program() == found


def test_java_from_program_files(monkeypatch, tmp_path):
    """Without JAVA_HOME and PATH the newest Java in Program Files is found."""
    _no_java(monkeypatch, tmp_path)
    _java(tmp_path / "pf" / "Java" / "jre1.8.0_351")
    newest = _java(tmp_path / "pf" / "Java" / "jre1.8.0_401")
    assert paths.java_program() == newest


def test_java_missing(monkeypatch, tmp_path):
    """Without an installed Java there is none; nothing bundled is used."""
    _no_java(monkeypatch, tmp_path)
    assert paths.java_program() is None


def _built(monkeypatch, exe):
    """Pretends to run as a built program with the given exe path."""
    monkeypatch.delenv("SOULLINK_BASE", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))


def test_built_without_reference_uses_the_exe_dir(monkeypatch, tmp_path):
    """A built program without reference file keeps its data next to the exe (portable folder)."""
    _built(monkeypatch, tmp_path / "Pokemon-Soullink.exe")
    assert paths.base_dir() == tmp_path.resolve()


def test_reference_file_next_to_the_exe(monkeypatch, tmp_path):
    """A reference file next to the exe redirects the data directory."""
    game = tmp_path / "common" / "SomeGame"
    data = tmp_path / "Pokemon-Soullink"
    game.mkdir(parents=True)
    data.mkdir()
    (game / paths.REFERENCE).write_text(f"\ufeff{data}\r\n", encoding="utf-8")
    _built(monkeypatch, game / "SomeGame.exe")
    assert paths.base_dir() == data
    (game / paths.REFERENCE).write_text("../../Pokemon-Soullink", encoding="utf-8")
    assert paths.base_dir().resolve() == data.resolve()


def test_reference_to_a_missing_dir_is_ignored(monkeypatch, tmp_path):
    """A reference to a missing folder is ignored."""
    game = tmp_path / "common" / "SomeGame"
    game.mkdir(parents=True)
    (game / paths.REFERENCE).write_text(str(tmp_path / "missing"), encoding="utf-8")
    _built(monkeypatch, game / "SomeGame.exe")
    assert paths.base_dir() == game.resolve()
