"""Compiles SoullinkDex.java into vendor/randomizer/soullink-dex.jar. Run with `.venv/Scripts/python.exe
tools/dex_build.py` (JDK from SOULLINK_JDK, JAVA_HOME or the PATH)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RANDOMIZER = HERE.parent / "vendor" / "randomizer"


def jdk_tool(name: str) -> str:
    """Path of a JDK program (javac, jar) from SOULLINK_JDK or JAVA_HOME, otherwise from the PATH."""
    for home in (os.environ.get("SOULLINK_JDK"), os.environ.get("JAVA_HOME")):
        if home and (Path(home) / "bin" / f"{name}.exe").is_file():
            return str(Path(home) / "bin" / f"{name}.exe")
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"{name} not found: install a JDK 17+ or set SOULLINK_JDK")
    return found


def build() -> Path:
    """Compiles and packs the helper jar and returns its path."""
    target = RANDOMIZER / "soullink-dex.jar"
    with tempfile.TemporaryDirectory() as classes:
        subprocess.run([jdk_tool("javac"), "--release", "17", "-encoding", "UTF-8",
                        "-cp", str(RANDOMIZER / "PokeRandoZX.jar"), "-d", classes, str(HERE / "SoullinkDex.java")],
                       check=True)
        subprocess.run([jdk_tool("jar"), "--create", "--file", str(target), "-C", classes, "."],
                       check=True)
    return target


if __name__ == "__main__":
    print(f"Done: {build()}")
