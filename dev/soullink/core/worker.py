"""Player process: runs the core at the pace of the system and saves SRAM and state. Normally every player has an own
process (worker_main); when a plugin demands it (GBA link cable: mGBA lockstep only links cores of the same process) the
GBA players of a session share one process with a thread each (group_main)."""
from __future__ import annotations

import multiprocessing
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

from ..atomic import atomic_write
from ..plugin.worker import PluginParts
from .libretro import Core
from .memory import SharedMemory

SRAM_INTERVAL = 1.0
MAX_BACKLOG = 0.25


def worker_main(job: dict, commands, events, audio) -> None:
    """Entry point of a player's own process."""
    try:
        _run(job, commands, events, audio)
    except Exception:
        events.put(("error", traceback.format_exc()))
        audio.cancel_join_thread()
        sys.exit(1)


def group_main(jobs: list[tuple]) -> None:
    """Entry point of a process shared by several players (job, commands, events, audio), one thread each; the worker parts
    of a plugin share one dict per plugin."""
    shared: dict[str, dict] = {}
    threads = [threading.Thread(target=_thread_main, args=(*job, shared),
                                name=f"player-{job[0]['nr']}") for job in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def _thread_main(job: dict, commands, events, audio, shared: dict) -> None:
    """Thread body of one player inside a group process."""
    try:
        _run(job, commands, events, audio, shared)
    except Exception:
        events.put(("error", traceback.format_exc()))
        audio.cancel_join_thread()


def _load(core: Core, job: dict) -> str | None:
    """Loads the save RAM and, if present, the state; returns the source of the loaded save."""
    for candidate in job["sram_candidates"]:
        try:
            core.sram_set(Path(candidate).read_bytes())
            break
        except OSError:
            continue
    for candidate in job["state_candidates"]:
        try:
            data = Path(candidate).read_bytes()
        except OSError:
            continue
        if core.state_load(data):
            return candidate
    return None


def _run(job: dict, commands, events, audio, shared: dict | None = None) -> None:
    """Starts the core and the plugin parts of one player and runs the main loop."""
    memory = SharedMemory(job["shm"])
    core = Core(Path(job["core"]), Path(job["system_dir"]), job.get("options"))
    core.load_game(Path(job["rom"]))
    source = _load(core, job)
    parts = PluginParts(core, job, events, shared)
    try:
        _loop(core, memory, parts, job, commands, events, audio, source)
    finally:
        parts.end()


def _loop(core: Core, memory: SharedMemory, parts: PluginParts, job: dict, commands, events, audio,
              source: str | None) -> None:
    """Accepts commands, runs at the pace of the system and backs up the SRAM until the player ends."""
    sav, state = Path(job["sav"]), Path(job["state"])
    last_sram = core.sram()

    def sram_back_up() -> None:
        """Writes the SRAM to disk when it changed."""
        nonlocal last_sram
        current = core.sram()
        if current and current != last_sram:
            atomic_write(sav, current)
            last_sram = current
            events.put(("sram",))

    core.at_image = memory.image_write
    core.at_audio = audio.put
    audio_an, tempo, paused = bool(job["audio"]), 1, False
    events.put(("ready", {"fps": core.av.fps, "samplerate": core.av.samplerate, "version": core.version,
                               "source": source, "plugins": parts.ready()}))
    parent = multiprocessing.parent_process()
    clock = 1.0 / core.av.fps
    next_ = time.perf_counter()
    next_check = next_ + SRAM_INTERVAL

    while True:
        while True:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                break
            kind = command[0]
            if kind == "pause":
                paused = bool(command[1])
            elif kind == "tempo":
                tempo = max(1, int(command[1]))
            elif kind == "audio":
                audio_an = bool(command[1])
            elif kind == "save":
                atomic_write(state, core.state())
                sram_back_up()
                events.put(("saved", command[1]))
            elif kind == "ram":
                events.put(("ram", core.ram_blocks()))
            elif kind == "plugin":
                parts.command(command[1], command[2])
            elif kind == "plugin_disable":
                parts.disable(command[1])
            elif kind == "end":
                sram_back_up()
                parts.end()
                core.end()
                audio.cancel_join_thread()
                events.put(("ended",))
                return

        if paused:
            time.sleep(0.01)
            next_ = time.perf_counter()
        else:
            core.input_mask = memory.input
            core.pointer_x, core.pointer_y, core.pointer_pressed = memory.pointer
            for i in range(tempo):
                core.image_active = i == tempo - 1
                core.audio_active = audio_an and tempo == 1
                parts.before_image()
                core.step()
                parts.after_image(memory)
            next_ += clock
            rest = next_ - time.perf_counter()
            if rest > 0:
                time.sleep(rest)
            elif rest < -MAX_BACKLOG:
                next_ = time.perf_counter()

        now = time.perf_counter()
        if now >= next_check:
            sram_back_up()
            next_check = now + SRAM_INTERVAL
            if parent is not None and not parent.is_alive():
                parts.end()
                core.end()
                audio.cancel_join_thread()
                return
