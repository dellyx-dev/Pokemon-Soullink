"""Builds the mGBA libretro core with link cable support (tools/mgba/soullink-link.c) into vendor/core/mgba_libretro.dll.
The source is mGBA at the version of the previously bundled core; the rest of the core stays as in the buildbot, and
retro_run runs the frame through soullinkLinkFrame."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEV = HERE.parent
SOURCE = DEV / "build" / "mgba-source"
BUILD = DEV / "build" / "mgba-build"
TARGET = DEV / "vendor" / "core" / "mgba_libretro.dll"
REPO = "https://github.com/mgba-emu/mgba.git"
STATE = "7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6"
WINGET = [Path(os.environ[v]) / sub for v, sub in (("ProgramFiles", "WinGet"), ("LOCALAPPDATA", "Microsoft/WinGet"))
          if os.environ.get(v)]
COMPILER = os.environ.get("SOULLINK_CLANG", "x86_64-w64-mingw32-clang")

CHANGES = {
    "CMakeLists.txt": [
        ('''	set(LIBRETRO_CORE_SRC ${CORE_SRC})
	list(APPEND LIBRETRO_CORE_SRC ${VFS_SRC})''',
         '''	set(LIBRETRO_CORE_SRC ${CORE_SRC})
	list(APPEND LIBRETRO_CORE_SRC ${VFS_SRC})
	list(APPEND LIBRETRO_CORE_SRC ${CMAKE_CURRENT_SOURCE_DIR}/src/gba/sio/lockstep.c)
	set_source_files_properties(${CMAKE_CURRENT_SOURCE_DIR}/src/gba/sio/lockstep.c
		${CMAKE_CURRENT_SOURCE_DIR}/src/platform/libretro/soullink-link.c PROPERTIES COMPILE_OPTIONS "-UDISABLE_THREADING")'''),
    ],
    "src/platform/libretro/libretro.c": [
        ('''#include "libretro_core_options.h"''', '''#include "libretro_core_options.h"
#include "soullink-link.h"'''),
        ('''static struct mCore* core;
''', '''static struct mCore* core;

struct mCore* soullinkCore(void) {
	return core;
}
'''),
        ('''	core->runFrame(core);
	unsigned width, height;''', '''	if (!soullinkLinkFrame(core)) {
		core->runFrame(core);
	}
	unsigned width, height;'''),
        ('''void retro_unload_game(void) {
	if (!core) {
		return;
	}
''', '''void retro_unload_game(void) {
	if (!core) {
		return;
	}
	soullinkLinkUnload(core);
'''),
    ],
}


def _path() -> dict:
    """PATH with LLVM-MinGW and CMake (winget packages; CMake via the link does not find its share folder) and Ninja
    (winget link), for machine and user installs; tools already on the PATH work too."""
    environment = dict(os.environ)
    extra = []
    for winget in WINGET:
        packets = winget / "Packages"
        llvm = next(packets.glob("MartinStorsjo.LLVM-MinGW.UCRT_*/llvm-mingw-*/bin"), None)
        cmake = next(packets.glob("Kitware.CMake_*/cmake-*/bin"), None)
        extra += [str(p) for p in (llvm, cmake, winget / "Links") if p is not None and p.is_dir()]
    environment["PATH"] = os.pathsep.join(extra + [environment.get("PATH", "")])
    return environment


def source_fetch() -> None:
    """Clones the mGBA source if it is not there yet."""
    if not (SOURCE / ".git").exists():
        SOURCE.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=SOURCE, check=True)
        subprocess.run(["git", "remote", "add", "origin", REPO], cwd=SOURCE, check=True)
    subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", STATE], cwd=SOURCE, check=True)
    subprocess.run(["git", "checkout", "-q", "-f", STATE], cwd=SOURCE, check=True)
    subprocess.run(["git", "clean", "-q", "-fdx"], cwd=SOURCE, check=True)


def change() -> None:
    """Copies the link cable sources into the mGBA tree and patches its CMake and libretro files."""
    for file in ("soullink-link.c", "soullink-link.h"):
        shutil.copy2(HERE / "mgba" / file, SOURCE / "src" / "platform" / "libretro" / file)
    for name, pairs in CHANGES.items():
        path = SOURCE / name
        text = path.read_text(encoding="utf-8")
        for old, new in pairs:
            if text.count(old) != 1:
                raise SystemExit(f"{name}: location not found uniquely: {old[:60]!r}")
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8", newline="\n")


def build() -> Path:
    """Builds the core and returns the DLL path."""
    source_fetch()
    change()
    environment = _path()
    options = ["BUILD_LIBRETRO=ON", "SKIP_LIBRARY=ON", "BUILD_QT=OFF", "BUILD_SDL=OFF", "BUILD_GL=OFF",
                "BUILD_GLES2=OFF", "BUILD_GLES3=OFF", "BUILD_UPDATER=OFF", "USE_FFMPEG=OFF", "USE_ZLIB=OFF",
                "USE_PNG=OFF", "USE_LIBZIP=OFF", "USE_MINIZIP=OFF", "USE_SQLITE3=OFF", "USE_ELF=OFF", "USE_LZMA=OFF",
                "USE_DISCORD_RPC=OFF", "USE_EDITLINE=OFF", "USE_EPOXY=OFF", "USE_LUA=OFF", "ENABLE_SCRIPTING=OFF"]
    def program(name: str) -> str:
        """Finds a program in the PATH of the build environment, since Windows searches the caller's PATH."""
        return shutil.which(name, path=environment["PATH"]) or name

    subprocess.run([program("cmake"), "-G", "Ninja", "-S", str(SOURCE), "-B", str(BUILD), "-DCMAKE_BUILD_TYPE=Release",
                    f"-DCMAKE_C_COMPILER={COMPILER}", "-DCMAKE_RC_COMPILER=x86_64-w64-mingw32-windres"]
                   + [f"-D{o}" for o in options], env=environment, check=True)
    subprocess.run([program("ninja"), "-C", str(BUILD), "mgba_libretro"], env=environment, check=True)
    shutil.copy2(BUILD / "mgba_libretro.dll", TARGET)
    return TARGET


if __name__ == "__main__":
    print(f"Done: {build()}")
