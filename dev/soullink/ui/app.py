"""Window, main loop and switching between screens."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pygame

from ..config import folders_create, resolve, load_settings, save_settings
from ..input.bindings import Bindings
from ..input.devices import Devices, KeysEvent
from ..input.keys import Key
from ..layout import logical_resolution
from .. import language
from ..music import Music
from ..plugin.loader import Plugins
from ..profile import Profile
from . import graphics
from .menu import Repeater

WINDOW_SIZE = (1280, 720)
DIRECTIONS = (Key.UP, Key.DOWN, Key.LEFT, Key.RIGHT)


class Screen:
    """Base class of all screens; the App forwards events, updates and drawing to the current one."""
    quieter_background = False

    def __init__(self, app: "App"):
        """Creates the screen for the app."""
        self.app = app

    def raw(self, ev: pygame.event.Event) -> None:
        """Unmodified pygame events (Escape, text input)."""

    def event(self, e) -> None:
        """Own event: KeysEvent, DeviceEvent or RawEvent."""

    def update(self, dt: float) -> None:
        """Advances the screen by dt seconds."""
        pass

    def repeat_kind(self, key) -> str | None:
        """How a held direction key repeats: "list", "slider" (faster) or None (not at all)."""
        return "list"

    def draw(self, area: pygame.Surface) -> None:
        """Draws the screen into the area."""
        pass

    def close_requested(self) -> None:
        """The window is being closed."""
        self.app.end()

    def leave(self) -> None:
        """Cleans up before another screen takes over."""


class App:
    """The program: window, devices, settings, plugins, music and the main loop."""

    def __init__(self, base: Path, window: bool = False, devices: Devices | None = None):
        """Creates the app for the data directory; window=True forces a window instead of full screen."""
        self.base = Path(base)
        self.settings = load_settings(self.base)
        language.set_(self.settings.language or language.system_language())
        pygame.display.init()
        pygame.font.init()
        graphics.fonts_clear()
        pygame.joystick.init()
        from pygame._sdl2 import controller

        controller.init()
        self.window = window or os.environ.get("SOULLINK_WINDOW") == "1"
        pygame.display.set_icon(graphics.pokeball_symbol(64))
        if self.window:
            self.area = pygame.display.set_mode(WINDOW_SIZE)
        else:
            size = logical_resolution(*pygame.display.get_desktop_sizes()[0])
            try:
                self.area = pygame.display.set_mode(size, pygame.FULLSCREEN | pygame.SCALED, vsync=1)
            except pygame.error:
                self.area = pygame.display.set_mode(size, pygame.FULLSCREEN | pygame.SCALED)
            pygame.mouse.set_visible(False)
        pygame.display.set_caption("Pokemon-Soullink")
        self.size = self.area.get_size()
        self.devices = devices or Devices(Bindings(self.base / "controller-bindings.json"))
        self.profile = Profile(self.base)
        self.plugins = Plugins(self.base, self.settings)
        folders_create(self.base, self.settings)
        self.music = Music(resolve(self.base, self.settings.sound_dir), self.settings.music_volume)
        self.music.start()
        self.runs = True
        self._screen: Screen | None = None
        self.hold = Repeater()
        self._hold_device: str | None = None
        from .start import StartScreen

        self.switch(StartScreen(self))

    @property
    def screen(self) -> Screen:
        """The current screen."""
        return self._screen

    @property
    def sessions_dir(self) -> Path:
        """Absolute sessions folder."""
        return resolve(self.base, self.settings.sessions_dir)

    @property
    def presets_dir(self) -> Path:
        """Absolute randomizer presets folder."""
        return resolve(self.base, self.settings.presets_dir)

    @property
    def rom_dir(self) -> Path:
        """Absolute GBA ROM folder."""
        return resolve(self.base, self.settings.rom_dir)

    @property
    def rom_dir_nds(self) -> Path:
        """Absolute NDS ROM folder."""
        return resolve(self.base, self.settings.rom_dir_nds)

    def switch(self, new: Screen) -> None:
        """Makes another screen the current one after the old one has cleaned up."""
        self.hold.stop()
        if self._screen is not None:
            self._screen.leave()
        self._screen = new

    def end(self) -> None:
        """Ends the main loop."""
        self.runs = False

    def music_new(self) -> None:
        """Restarts the music with the files of a newly chosen folder."""
        self.music.close()
        self.music = Music(resolve(self.base, self.settings.sound_dir), self.settings.music_volume)
        self.music.start()

    def volume_change(self, step: int, save: bool = True) -> None:
        """Changes the music volume in percent and stores it; while a key is held it saves only at the end (step 0)."""
        self.music.volume_set(self.music.volume + step)
        if save and self.music.volume != self.settings.music_volume:
            self.settings.music_volume = self.music.volume
            save_settings(self.base, self.settings)

    def run(self, max_images: int | None = None) -> None:
        """Main loop; with max_images (tests) it ends after that many frames without cleaning up."""
        clock = pygame.time.Clock()
        images = 0
        while self.runs:
            dt = clock.tick(60) / 1000
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self._screen.close_requested()
                    continue
                self._screen.raw(ev)
                for e in self.devices.process(ev):
                    self.input(e)
            self.repeat()
            self._screen.update(dt)
            self.music.update()
            self.area.blit(graphics.background(self.size, self._screen.quieter_background), (0, 0))
            self._screen.draw(self.area)
            pygame.display.flip()
            images += 1
            if max_images is not None and images >= max_images:
                return
        self.close()

    def input(self, e) -> None:
        """Forwards an event to the screen; held direction keys repeat (see Screen.repeat_kind)."""
        if isinstance(e, KeysEvent) and not e.pressed:
            if e.device == self._hold_device:
                self.hold.stop(e.key)
        elif isinstance(e, KeysEvent):
            kind = self._screen.repeat_kind(e.key) if e.key in DIRECTIONS else None
            if kind is None:
                self.hold.stop()
            else:
                self.hold.start(e.key, time.monotonic(), kind)
                self._hold_device = e.device
        self._screen.event(e)

    def repeat(self) -> None:
        """Sends the repeat event of a held key when it is due."""
        key = self.hold.due(time.monotonic())
        if key is not None:
            self._screen.event(KeysEvent(self._hold_device, key, True, repeats=True))

    def close(self) -> None:
        """Cleans up and shuts pygame down."""
        if self._screen is not None:
            self._screen.leave()
            self._screen = None
        graphics.fonts_clear()
        self.music.close()
        pygame.quit()
