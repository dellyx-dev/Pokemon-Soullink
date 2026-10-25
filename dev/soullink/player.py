"""Main-process side of a player: starts the worker and fetches image, audio and events."""
from __future__ import annotations

import multiprocessing as mp
import os
import queue
import shutil
import tempfile
import time
from pathlib import Path

import pygame

from . import paths
from .core.memory import SharedMemory
from .core.worker import group_main, worker_main
from .session import candidates

_CTX = mp.get_context("spawn")
DEFAULT_OPTIONS = {"nds": {"melonds_show_cursor": "disabled"}}


class ProcessGroup:
    """GBA players of a session in one shared process (one thread and one core DLL copy each), needed when a plugin such as
    the GBA link cable requires cores in the same process."""

    def __init__(self, count: int):
        """Creates the group for the given number of players."""
        self.count = count
        self._jobs: list[tuple] = []
        self._process = None
        self._copies = Path(tempfile.gettempdir()) / "soullink-cores"

    @property
    def started(self) -> bool:
        """True once the shared process has been started."""
        return self._process is not None

    def core_copy(self, core: Path, nr: int) -> Path:
        """Own DLL copy per player, because a DLL keeps its state globally and only copies can run side by side."""
        self._copies.mkdir(parents=True, exist_ok=True)
        if not self._jobs:
            for old in self._copies.glob(f"*{core.suffix}"):
                try:
                    old.unlink()
                except OSError:
                    pass
        target = self._copies / f"{core.stem}-{os.getpid()}-{nr}{core.suffix}"
        shutil.copy2(core, target)
        return target

    def register(self, job: dict, commands, events, audio) -> None:
        """Registers one player's job; the process starts when all players are registered."""
        self._jobs.append((job, commands, events, audio))
        if len(self._jobs) == self.count:
            self._process = _CTX.Process(target=group_main, args=(self._jobs,), name="player-group",
                                         daemon=True)
            self._process.start()

    @property
    def alive(self) -> bool:
        """True while the shared process runs."""
        return self._process is not None and self._process.is_alive()

    @property
    def exitcode(self) -> int | None:
        """Exit code of the shared process, None while running."""
        return self._process.exitcode if self._process is not None else None

    def cancel(self) -> None:
        """Terminates the shared process."""
        if self.alive:
            self._process.terminate()
            self._process.join(1.0)


class PlayerProcess:
    """Handle of one player's worker: starts it, sends commands and fetches image, audio and events."""

    def __init__(self, nr: int, player_dir: Path, audio: bool, core: Path | None = None, system: str = "gba",
                 core_options: dict[str, str] | None = None, group: ProcessGroup | None = None,
                 plugins: list[dict] | None = None, base: Path | None = None):
        """Prepares a player process for the player folder; nothing is started yet."""
        self.nr = nr
        self.base = Path(base) if base is not None else paths.base_dir()
        self.core_options = DEFAULT_OPTIONS.get(system, {}) if core_options is None else core_options
        self.dir = Path(player_dir)
        self.system = system
        self._audio_on = bool(audio)
        self._core = Path(core) if core else paths.core_file(system)
        self._memory: SharedMemory | None = None
        self._process = None
        self._commands = self._events = self._audio = None
        self._last_seq = 0
        self._next_id = 0
        self.ready_info: dict | None = None
        self.saved_ids: set[int] = set()
        self.error: str | None = None
        self.ended = False
        self.group = group
        self._thread_end = False
        self.plugins = list(plugins or [])
        self._slot_data: dict[int, bytes] = {}

    def start(self) -> None:
        """Starts the worker process (or registers with the process group) and its shared memory."""
        sav, state = self.dir / "game.sav", self.dir / "state.state"
        self._memory = SharedMemory()
        self._commands, self._events, self._audio = _CTX.Queue(), _CTX.Queue(), _CTX.Queue()
        job = {
            "nr": self.nr,
            "core": str(self._core),
            "rom": str(self.dir / f"rom.{self.system}"),
            "system_dir": str(self.dir),
            "sav": str(sav),
            "state": str(state),
            "state_candidates": [str(p) for p in candidates(state)],
            "sram_candidates": [str(p) for p in candidates(sav)],
            "shm": self._memory.name,
            "audio": self._audio_on,
            "options": self.core_options,
            "plugins": self.plugins,
            "base": str(self.base),
            "group": self.group is not None,
        }
        if self.group is not None:
            job["core"] = str(self.group.core_copy(self._core, self.nr))
            self.group.register(job, self._commands, self._events, self._audio)
            return
        self._process = _CTX.Process(target=worker_main, args=(job, self._commands, self._events, self._audio),
                                     name=f"player-{self.nr}", daemon=True)
        self._process.start()

    def _command(self, *command) -> None:
        """Sends a command to the worker unless it has ended."""
        if self._commands is not None and not self.ended:
            self._commands.put(command)

    def input(self, mask: int) -> None:
        """Sets the pressed-button mask."""
        if self._memory is not None:
            self._memory.input = mask

    def pointer(self, x: int, y: int, pressed: bool) -> None:
        """Touch pointer position in the libretro range of +-32767 relative to the whole frame."""
        if self._memory is not None:
            self._memory.pointer = (x, y, pressed)

    def pause(self, on: bool) -> None:
        """Pauses or resumes the game."""
        self._command("pause", bool(on))

    def tempo(self, factor: int) -> None:
        """Sets the speed factor (fast forward)."""
        self._command("tempo", int(factor))

    def audio(self, on: bool) -> None:
        """Switches the game audio on or off."""
        self._audio_on = bool(on)
        self._command("audio", self._audio_on)

    def save(self) -> int:
        """Asks the worker to save the state; returns an id that later appears in saved_ids."""
        self._next_id += 1
        self._command("save", self._next_id)
        return self._next_id

    def ram_request(self) -> None:
        """Asks the worker for its memory, delivered as an event ("ram", {start address: bytes})."""
        self._command("ram")

    def plugin_command(self, plugin_id: str, data) -> None:
        """Sends data to the worker part of a plugin; its reply arrives as an event ("plugin", id, reply)."""
        self._command("plugin", plugin_id, data)

    def plugin_disable(self, plugin_id: str) -> None:
        """Switches the worker part of a plugin off for the rest of the session."""
        self._command("plugin_disable", plugin_id)

    def plugin_data(self, slot: int | None) -> bytes | None:
        """What the worker part last wrote into its shared memory slot; None if nothing yet."""
        if slot is None or self._memory is None:
            return None
        read = self._memory.slot_read(slot)
        if read is not None:
            self._slot_data[slot] = read[1]
        return self._slot_data.get(slot)

    def fetch(self) -> list[tuple]:
        """Collects pending events of the worker and updates the state from them."""
        events = []
        while self._events is not None:
            try:
                e = self._events.get_nowait()
            except (queue.Empty, OSError, ValueError):
                break
            if e[0] == "ready":
                self.ready_info = e[1]
            elif e[0] == "saved":
                self.saved_ids.add(e[1])
            elif e[0] == "error":
                self.error = e[1]
                self._thread_end = True
            elif e[0] == "ended":
                self._thread_end = True
            events.append(e)
        return events

    def audio_fetch(self) -> list[bytes]:
        """Collects pending audio chunks."""
        data = []
        while self._audio is not None:
            try:
                data.append(self._audio.get_nowait())
            except (queue.Empty, OSError, ValueError):
                break
        return data

    def image(self) -> pygame.Surface | None:
        """The latest frame as a pygame surface; None if there is none yet."""
        if self._memory is None:
            return None
        read = self._memory.image_read()
        if read is None or read[0] == self._last_seq:
            return None
        self._last_seq, width, height, data = read
        if not width or not height:
            return None
        return pygame.image.frombuffer(data, (width, height), "RGBX")

    @property
    def alive(self) -> bool:
        """True while the worker (or the player's thread) runs."""
        if self.group is not None:
            return self.group.alive and not self._thread_end
        return self._process is not None and self._process.is_alive()

    @property
    def exitcode(self) -> int | None:
        """Exit code of the worker, None while it runs."""
        if self.group is not None:
            return (1 if self.error else 0) if self._thread_end else self.group.exitcode
        return self._process.exitcode if self._process is not None else None

    def end(self, timeout: float = 5.0) -> None:
        """Ends the worker, waiting up to the timeout before terminating it."""
        if self.group is not None:
            self._group_end(timeout)
            return
        if self._process is None or self.ended:
            return
        if self._process.is_alive():
            self._command("end")
            end = time.monotonic() + timeout
            while self._process.is_alive() and time.monotonic() < end:
                self._process.join(0.05)
                self.fetch()
                self.audio_fetch()
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(1.0)
        self.fetch()
        self.ended = True
        for q in (self._commands, self._events, self._audio):
            q.close()
        self._clean_up()

    def _group_end(self, timeout: float) -> None:
        """Ends only the own thread; the process ends with the last player."""
        if self.ended or self._memory is None:
            return
        if self.group.alive and not self._thread_end:
            self._command("end")
            end = time.monotonic() + timeout
            while self.group.alive and not self._thread_end and time.monotonic() < end:
                self.fetch()
                self.audio_fetch()
                time.sleep(0.02)
            if not self._thread_end:
                self.group.cancel()
        self.fetch()
        self.ended = True
        for q in (self._commands, self._events, self._audio):
            q.close()
        self._clean_up()

    def _clean_up(self) -> None:
        """Releases queues and shared memory."""
        self._commands.join_thread()
        self._memory.close()
        self._memory.release()
        self._memory = None
