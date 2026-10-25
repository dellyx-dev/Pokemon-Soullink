"""Runs the Universal Pokemon Randomizer ZX from the command line."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .language import t

_SEED = re.compile(r"^Random Seed:\s*(-?\d+)", re.MULTILINE)
_FLAGS = subprocess.CREATE_NO_WINDOW


@dataclass
class Result:
    """Outcome of randomizing one player's ROM."""
    nr: int
    ok: bool
    seed: str | None
    message: str


def find_presets(dir: Path) -> list[Path]:
    """Randomizer settings files (.rnqs) in the folder, sorted by name."""
    dir = Path(dir)
    if not dir.is_dir():
        return []
    return sorted((p for p in dir.iterdir() if p.suffix.lower() == ".rnqs"), key=lambda p: p.name.lower())


def command(java: Path, jar: Path, preset: Path, source: Path, target: Path) -> list[str]:
    """Command line that randomizes source into target with the given preset."""
    return [str(java), "-jar", str(jar), "cli", "-s", str(preset), "-i", str(source), "-o", str(target), "-l"]


def read_seed(log: str) -> str | None:
    """Seed number from the randomizer log text; None if absent."""
    hit = _SEED.search(log)
    return hit.group(1) if hit else None


def error_text(output: str) -> str:
    """Most informative error line of the randomizer output."""
    rows = [z.strip() for z in output.splitlines() if z.strip()]
    error = [z[len("ERROR:"):].strip() for z in rows if z.startswith("ERROR:")]
    if error:
        return "; ".join(error)
    exception = next((z for z in rows if "Exception" in z and not z.startswith("at ")), None)
    if exception:
        return exception
    rest = [z for z in rows if not z.startswith(("Usage:", "-d:"))]
    return rest[-1] if rest else t("randomizer.unknown")


def randomize(nr: int, java: Path, jar: Path, preset: Path, source: Path, player_dir: Path,
                 run=subprocess.run) -> Result:
    """Randomizes the source ROM into the player's folder; ZX unpacks NDS ROMs next to its jar, so every player gets an own
    input file name to keep parallel runs apart."""
    player_dir = Path(player_dir)
    player_dir.mkdir(parents=True, exist_ok=True)
    target = player_dir / f"rom{Path(source).suffix.lower()}"
    input = player_dir / f"input-p{nr}{Path(source).suffix.lower()}"
    try:
        _link(Path(source), input)
        run = run(command(java, jar, preset, input, target), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300, creationflags=_FLAGS)
    except (OSError, subprocess.SubprocessError) as error:
        return Result(nr, False, None, t("randomizer.not_startable", java=java, error=error))
    finally:
        input.unlink(missing_ok=True)
    if run.returncode != 0 or not target.exists():
        return Result(nr, False, None, error_text((run.stdout or "") + "\n" + (run.stderr or "")))
    log = target.with_name(target.name + ".log")
    seed = None
    if log.exists():
        seed = read_seed(log.read_text(encoding="utf-8-sig", errors="replace"))
        log.replace(player_dir / "randomizer.log")
    return Result(nr, True, seed, "")


def _link(source: Path, target: Path) -> None:
    """Hard-links the source (no copy of up to 512 MB), copying if that is not possible."""
    target.unlink(missing_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def without_randomizer(nr: int, source: Path, player_dir: Path) -> Result:
    """Copies the source ROM unchanged into the player's folder."""
    player_dir = Path(player_dir)
    player_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, player_dir / f"rom{Path(source).suffix.lower()}")
    return Result(nr, True, None, "")
