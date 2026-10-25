"""Background music: plays the files of the sound folder one after another in random order through pygame.mixer."""
from __future__ import annotations

import random
from pathlib import Path

import pygame

SUFFIXES = {".mp3", ".ogg", ".wav", ".flac", ".opus"}


class Music:
    """Plays the files of the sound folder in random order; the mixer is opened only if files exist."""

    def __init__(self, dir: Path, volume: int = 50):
        """Creates the player for a folder and a volume in percent."""
        self.dir = Path(dir)
        self.volume = max(0, min(100, int(volume)))
        self._queue: list[Path] = []
        self.runs = False
        self.title: str | None = None

    def files(self) -> list[Path]:
        """Playable files of the sound folder, sorted by name."""
        if not self.dir.is_dir():
            return []
        return sorted(p for p in self.dir.iterdir() if p.suffix.lower() in SUFFIXES and p.is_file())

    def start(self) -> None:
        """Opens the mixer if files exist and starts the first track; safe to call repeatedly."""
        if self.runs or not self.files():
            return
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        except pygame.error:
            return
        self.runs = True
        self._next()

    def _next(self) -> None:
        """Starts the next playable track and closes the mixer if nothing can be played."""
        for _ in range(len(self.files()) + 1):
            if not self._queue:
                self._queue = self.files()
                random.shuffle(self._queue)
                if not self._queue:
                    break
            file = self._queue.pop()
            try:
                pygame.mixer.music.load(str(file))
                pygame.mixer.music.set_volume(self.volume / 100)
                pygame.mixer.music.play()
            except pygame.error:
                continue
            self.title = file.stem
            return
        self.close()

    def update(self) -> None:
        """Call once per frame; starts the next track when the current one has ended."""
        if self.runs and not pygame.mixer.music.get_busy():
            self._next()

    def volume_set(self, value: int) -> None:
        """Sets the volume in percent (0-100), also for the running track."""
        self.volume = max(0, min(100, int(value)))
        if self.runs:
            pygame.mixer.music.set_volume(self.volume / 100)

    def close(self) -> None:
        """Stops playback and closes the mixer."""
        if self.runs:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        self.runs = False
        self.title = None
