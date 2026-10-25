"""Locations of the data directory, bundled resources and the installed Java."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


REFERENCE = "soullink-base.txt"


def is_built() -> bool:
    """True when running as the PyInstaller executable."""
    return bool(getattr(sys, "frozen", False))


def base_dir() -> Path:
    """Data directory holding sessions, presets and settings.json."""
    env = os.environ.get("SOULLINK_BASE")
    if env:
        return Path(env)
    if is_built():
        exe_dir = Path(sys.executable).resolve().parent
        return _reference(exe_dir / REFERENCE) or exe_dir
    return Path(__file__).resolve().parents[1]


def _reference(file: Path) -> Path | None:
    """Folder named in the reference file (relative to its folder); None if the file or folder is missing."""
    try:
        rows = file.read_text(encoding="utf-8-sig").strip().splitlines()
    except OSError:
        return None
    if not rows:
        return None
    target = file.parent / rows[0].strip().strip('"')
    return target if target.is_dir() else None


PLUGINS = "plugins"
ERROR_LOG = "error.log"


def plugin_dir(base: Path | None = None) -> Path:
    """The plugins folder inside the data directory, one subfolder per plugin."""
    return Path(base if base is not None else base_dir()) / PLUGINS


DEFAULT_KEYS = "default-keys.json"


def default_keys_files() -> list[Path]:
    """Candidates for default-keys.json: a custom one in the data directory first, then the bundled one."""
    bundled = Path(sys.executable).resolve().parent if is_built() else Path(__file__).resolve().parents[1]
    return list(dict.fromkeys([base_dir() / DEFAULT_KEYS, bundled / DEFAULT_KEYS]))


def license_dir() -> Path:
    """The licenses folder with the texts of third-party software."""
    if is_built():
        return Path(sys.executable).resolve().parent / "licenses"
    return Path(__file__).resolve().parents[1] / "licenses"


def language_dir() -> Path:
    """The language folder with the translation files."""
    if is_built():
        return Path(sys.executable).resolve().parent / "language"
    return Path(__file__).resolve().parents[1] / "language"


def resources_dir() -> Path:
    """Folder containing the cores and the randomizer."""
    if is_built():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1] / "vendor"


CORES = {"gba": "mgba_libretro", "nds": "melondsds_libretro"}


def core_file(system: str = "gba") -> Path:
    """Path of the libretro core DLL for the given system."""
    return resources_dir() / "core" / (CORES[system] + ".dll")


def randomizer_jar() -> Path:
    """Path of the Universal Pokemon Randomizer ZX jar."""
    return resources_dir() / "randomizer" / "PokeRandoZX.jar"


def dex_jar() -> Path:
    """Path of the SoullinkDex helper jar that reads Pokedex data from a ROM."""
    return resources_dir() / "randomizer" / "soullink-dex.jar"


JAVA_VENDORS = ("Java", "Eclipse Adoptium", "Amazon Corretto", "Microsoft", "Zulu", "BellSoft", "Semeru")


def java_program() -> Path | None:
    """The installed java.exe from JAVA_HOME, PATH or the usual install folders; None if no Java is installed."""
    exe = "java.exe"
    home = os.environ.get("JAVA_HOME")
    if home and (Path(home) / "bin" / exe).exists():
        return Path(home) / "bin" / exe
    found = shutil.which("java")
    if found:
        return Path(found)
    return _installed_java(exe)


def _installed_java(exe: str) -> Path | None:
    """Newest java.exe below the vendor folders in Program Files (64-bit)."""
    root = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles")
    if not root:
        return None
    for vendor in JAVA_VENDORS:
        for home in sorted((Path(root) / vendor).glob("*"), key=lambda p: p.name, reverse=True):
            if (home / "bin" / exe).exists():
                return home / "bin" / exe
    return None
