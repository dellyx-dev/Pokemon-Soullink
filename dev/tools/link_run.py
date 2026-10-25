"""Shared code of the link cable runs (gba_kabelclub.py, nds_packets.py): paths, key scripts and frame-exact playback. The
runs start real game processes."""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEV = HERE.parent
PROJECT = DEV.parent
PLUGINS = DEV / "plugins"
KEYS = {"B": 0, "Y": 1, "SELECT": 2, "START": 3, "UP": 4, "DOWN": 5, "LEFT": 6, "RIGHT": 7, "A": 8, "X": 9, "L": 10,
          "R": 11}
LEGACY_COMMANDS = {"LINK", "INFO", "DISCONNECT"}


def in_project(path: Path) -> bool:
    """True if the path lies inside the project, where no ROMs or saves belong."""
    path = Path(path).resolve()
    return path == PROJECT or PROJECT in path.parents


def path(value: str | None, variable: str, name: str, must_there_be: bool = True) -> Path:
    """Path from the argument or the environment variable; never inside the project (test data belongs in %TEMP%)."""
    value = value or os.environ.get(variable)
    if not value:
        raise SystemExit(f"{name} missing: argument or environment variable {variable}")
    result = Path(value)
    if in_project(result):
        raise SystemExit(f"{name} is inside the project ({result}) - test data belongs in %TEMP%")
    if must_there_be and not result.exists():
        raise SystemExit(f"{name} does not exist: {result}")
    return result


def arguments(description: str, suffix: str, argv: list[str] | None = None) -> argparse.Namespace:
    """Parses --rom, --state, --output and --work; the scripts (one per player) follow after "--"."""
    divider = argparse.ArgumentParser(description=description)
    divider.add_argument("--rom", help=f"ROM copy ({suffix}); otherwise SOULLINK_LINK_ROM")
    divider.add_argument("--state", help="Save state copy (state.state) for all; otherwise SOULLINK_LINK_STATE")
    divider.add_argument("--output", dest="output_dir", help="Folder for the screenshots; otherwise SOULLINK_LINK_OUTPUT")
    divider.add_argument("--work", help="Work folder of the players (default: new under %%TEMP%%, removed afterwards)")
    divider.add_argument("scripts", nargs="*", help="one key script per player (after --)")
    a = divider.parse_args(argv)
    a.rom = path(a.rom, "SOULLINK_LINK_ROM", "ROM")
    a.state = path(a.state, "SOULLINK_LINK_STATE", "Save state")
    a.output_dir = path(a.output_dir, "SOULLINK_LINK_OUTPUT", "Output folder", must_there_be=False)
    a.own_work = a.work is None
    a.work = Path(tempfile.mkdtemp(prefix="soullink-link-")) if a.work is None else \
        path(a.work, "", "Work folder", must_there_be=False)
    return a


def plan(script: str) -> list[tuple]:
    """Parses a key script like "A:5 -:70 IMAGE:x" into steps [("keys", mask, 5), ("keys", 0, 70), ("image", "x")]."""
    steps = []
    for command in script.split():
        kind, _, value = command.partition(":")
        if kind in LEGACY_COMMANDS:
            continue
        if kind == "IMAGE":
            steps.append(("image", value))
            continue
        mask = 0
        if kind != "-":
            for key in kind.split("+"):
                mask |= 1 << KEYS[key]
        steps.append(("keys", mask, int(value)))
    return steps


def repeats(count: int, part: str) -> str:
    """The part repeated count times, separated by spaces."""
    return " ".join([part] * count)


def entry(plugin_id: str) -> dict:
    """Worker part entry of a bundled plugin for PlayerProcess(plugins=[...])."""
    return {"id": plugin_id, "dir": str(PLUGINS / plugin_id), "module": "worker", "slot": None}


def player_dir(work: Path, nr: int, rom: Path, state: Path, suffix: str) -> Path:
    """Creates p<nr>/ with the ROM (linked if possible) and a copy of the save state."""
    dir = Path(work) / f"p{nr}"
    if dir.exists():
        shutil.rmtree(dir)
    dir.mkdir(parents=True)
    try:
        os.link(rom, dir / f"rom.{suffix}")
    except OSError:
        shutil.copyfile(rom, dir / f"rom.{suffix}")
    shutil.copyfile(state, dir / "state.state")
    return dir


class Observer:
    """Fetches events and audio of the players and remembers the replies of the worker part `plugin_id`."""

    def __init__(self, player, plugin_id: str):
        """Creates the observer for the players and the plugin id."""
        self.player, self.plugin_id = player, plugin_id
        self.reply = {sp.nr: [] for sp in player}
        self.error: list = []

    def round_(self) -> None:
        """Fetches events and audio of all players once."""
        for sp in self.player:
            for e in sp.fetch():
                if e[:2] == ("plugin", self.plugin_id):
                    self.reply[sp.nr].append(e[2])
                elif e[0] in ("plugin_error", "error"):
                    self.error.append((sp.nr, e))
                    print("ERROR", sp.nr, e)
            sp.audio_fetch()

    def wait(self, condition, seconds: float) -> bool:
        """Polls until the condition holds or the seconds are over."""
        end = time.monotonic() + seconds
        while time.monotonic() < end and not condition():
            self.round_()
            time.sleep(0.005)
        return condition()


def frame_number(sp) -> int:
    """Sequence number of the player's latest frame."""
    read = sp._memory.image_read()
    return read[0] if read else 0


def play(observer: Observer, plans: list[list[tuple]], output_dir: Path, at_most: float = 600.0,
              log=None) -> float:
    """Plays all scripts frame-exactly and saves screenshots as <output>/p<n>-<name>.png; returns the duration in seconds."""
    import pygame

    output_dir.mkdir(parents=True, exist_ok=True)
    player = observer.player
    pointer = [0] * len(player)
    start = [frame_number(sp) for sp in player]
    start = time.monotonic()
    while any(z < len(p) for z, p in zip(pointer, plans)) and time.monotonic() - start < at_most:
        observer.round_()
        for i, sp in enumerate(player):
            now = frame_number(sp)
            while pointer[i] < len(plans[i]):
                step = plans[i][pointer[i]]
                if step[0] == "image":
                    _, width, height, data = sp._memory.image_read()
                    pygame.image.save(pygame.image.frombuffer(data, (width, height), "RGBX"),
                                      str(output_dir / f"p{sp.nr}-{step[1]}.png"))
                    if log is not None:
                        log(sp.nr, step[1])
                    pointer[i] += 1
                    start[i] = now
                    continue
                sp.input(step[1])
                if now - start[i] >= step[2]:
                    pointer[i] += 1
                    start[i] = now
                    continue
                break
            else:
                sp.input(0)
        time.sleep(0.003)
    return time.monotonic() - start
