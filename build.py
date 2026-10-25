"""Builds the portable program folder build/ (program files replaced, user folders only created when missing) and with
`--zip` a release archive in release/. Run on Windows from the project folder with `dev\\.venv\\Scripts\\python build.py`."""
from __future__ import annotations

import datetime
import importlib.util
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEV = ROOT / "dev"
TARGET = ROOT / "build"
RELEASE = ROOT / "release"
SKELETON = DEV / "release"
NAME = "Pokemon-Soullink"
DIST = DEV / "build" / "dist" / NAME
PLUGIN_IGNORE = shutil.ignore_patterns("tests", "__pycache__", "conftest.py", "test_*.py", "*.pyc")
WITHOUT_STDLIB = {"tkinter", "turtle", "turtledemo", "idlelib", "test", "ensurepip", "lib2to3", "pydoc_data", "venv",
               "this", "antigravity", "curses", "readline", "tty", "pty", "termios", "fcntl", "grp", "pwd", "resource",
               "posix", "syslog", "crypt", "nis", "spwd", "ossaudiodev", "msilib", "xxlimited"}

sys.path.insert(0, str(DEV))


def symbol_build(target: Path) -> Path:
    """Creates the exe icon: the same Pokeball as in the main menu."""
    from soullink.ui import graphics

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(graphics.ico_data())
    return target


def stdlib_module() -> list[str]:
    """The whole standard library for plugins (plugins/ is not inside the exe, so PyInstaller does not see their imports)."""
    away = WITHOUT_STDLIB | set(sys.builtin_module_names)
    return sorted(m for m in sys.stdlib_module_names if not m.startswith("_") and m not in away)


def pyinstaller() -> Path:
    """Runs PyInstaller in dev/build and returns the dist folder."""
    work = DEV / "build"
    fonts = DEV / "soullink" / "ui" / "fonts"
    symbol = symbol_build(work / "pokeball.ico")
    imports = ["--collect-submodules", "soullink"]
    for m in stdlib_module():
        spec = importlib.util.find_spec(m)
        packet = spec is not None and spec.submodule_search_locations is not None
        imports += ["--collect-submodules" if packet else "--hidden-import", m]
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed", "--name", NAME,
                    "--icon", str(symbol),
                    "--distpath", str(DIST.parent), "--workpath", str(work / "work"),
                    "--specpath", str(work), "--paths", str(DEV), *imports,
                    "--add-data", f"{fonts}{os.pathsep}soullink/ui/fonts", str(DEV / "start.py")], check=True, cwd=DEV)
    return DIST


def licenses_collect(target: Path) -> None:
    """Collects the licence texts of the bundled software: licenses/ from the project plus Python, NumPy and Poppins."""
    import numpy

    shutil.copytree(DEV / "licenses", target, dirs_exist_ok=True)
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", target / "Python-LICENSE.txt")
    numpy_info = next(Path(numpy.__file__).parent.parent.glob("numpy-*.dist-info"))
    shutil.copy2(numpy_info / "licenses" / "LICENSE.txt", target / "NumPy-LICENSE.txt")
    shutil.copy2(DEV / "soullink" / "ui" / "fonts" / "OFL.txt", target / "Poppins-OFL.txt")


def assemble(dist: Path) -> Path:
    """Adds cores, randomizer, licences, language files, default keys and the README to the dist folder and returns it."""
    (dist / "core").mkdir(exist_ok=True)
    for core in (DEV / "vendor" / "core").glob("*.dll"):
        shutil.copy2(core, dist / "core" / core.name)
    (dist / "randomizer").mkdir(exist_ok=True)
    for jar in ("PokeRandoZX.jar", "soullink-dex.jar"):
        shutil.copy2(DEV / "vendor" / "randomizer" / jar, dist / "randomizer" / jar)
    shutil.copytree(DEV / "language", dist / "language", dirs_exist_ok=True)
    shutil.copy2(DEV / "default-keys.json", dist / "default-keys.json")
    shutil.copy2(ROOT / "README.md", dist / "README.md")
    licenses_collect(dist / "licenses")
    return dist


def plugins() -> list[Path]:
    """The bundled plugin folders of the project (those with a plugin.json)."""
    return sorted(p for p in (DEV / "plugins").iterdir() if (p / "plugin.json").is_file())


def replace(source: Path, target: Path, ignore=None) -> None:
    """Replaces the file or folder at target with a copy of source."""
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()
    if source.is_dir():
        shutil.copytree(source, target, ignore=ignore)
    else:
        shutil.copy2(source, target)


def install(dist: Path, target: Path = TARGET) -> Path:
    """Fills the portable folder: program files and bundled plugins are replaced, the skeleton only where missing."""
    target.mkdir(parents=True, exist_ok=True)
    for entry in dist.iterdir():
        replace(entry, target / entry.name)
    (target / "plugins").mkdir(exist_ok=True)
    for plugin in plugins():
        replace(plugin, target / "plugins" / plugin.name, PLUGIN_IGNORE)
    for file in SKELETON.rglob("*"):
        goal = target / file.relative_to(SKELETON)
        if file.is_dir():
            goal.mkdir(parents=True, exist_ok=True)
        elif not goal.exists():
            goal.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, goal)
    return target


def _files(folder: Path, ignore=None):
    """All files below folder, skipping what the ignore function of shutil would skip."""
    for dir, subdirs, names in os.walk(folder):
        skip = ignore(dir, subdirs + names) if ignore else set()
        subdirs[:] = [d for d in subdirs if d not in skip]
        for name in names:
            if name not in skip:
                yield Path(dir) / name


def release_zip(dist: Path, name: str | None = None) -> Path:
    """Packs program files, bundled plugins and the empty skeleton into release/<name>.zip, never the build/ folder."""
    name = name or f"{NAME}-{datetime.date.today().isoformat()}"
    RELEASE.mkdir(exist_ok=True)
    archive = RELEASE / f"{name}.zip"
    sources = [(dist, dist, None), (DEV / "plugins", DEV, PLUGIN_IGNORE), (SKELETON, SKELETON, None)]
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for folder, base, ignore in sources:
            for file in _files(folder, ignore):
                part = file.relative_to(base)
                if part.parts[0] == "plugins" and not (DEV / "plugins" / part.parts[1] / "plugin.json").is_file():
                    continue
                z.write(file, f"{NAME}/{part.as_posix()}")
    return archive


if __name__ == "__main__":
    dist = assemble(pyinstaller())
    print(f"Done: {install(dist)}")
    if "--zip" in sys.argv[1:]:
        print(f"Release: {release_zip(dist)}")
