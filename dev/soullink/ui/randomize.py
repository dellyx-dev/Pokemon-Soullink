"""Randomizing: creates the ROMs per player and creates the session only if everything succeeded."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pygame

from .. import paths
from ..input.devices import KeysEvent
from ..randomizer import Result, without_randomizer, randomize
from ..roms import unpack
from ..session import Session, Player, nds_mac, staging_finish, staging_create, staging_discard
from ..language import t
from . import graphics
from .app import Screen
from .menu import Menu


class RandomizeScreen(Screen):
    """Shows the progress of randomizing all players' ROMs and then starts the game."""

    def __init__(self, app, model):
        """Creates the screen for the new-session model and starts working."""
        super().__init__(app)
        self.model = model
        self.results: dict[int, Result] = {}
        self.menu: Menu | None = None
        self.error: str | None = None
        self._staging = None
        self._thread: threading.Thread | None = None
        self.time = 0.0
        self._start()

    def _start(self) -> None:
        """Resets the results and starts the background work."""
        self.results, self.menu, self.error = {}, None, None
        java, jar = paths.java_program(), paths.randomizer_jar()
        if self.model.preset is not None and (java is None or not jar.exists()):
            self.error = t("randomize.java_missing") if java is None else t("randomize.missing", jar=jar)
            self.actions = ["different"]
            self.menu = Menu([t("randomize.other_game")])
            return
        self._staging = staging_create(self.app.sessions_dir)
        self._thread = threading.Thread(target=self._flow, args=(java, jar), daemon=True)
        self._thread.start()

    def _flow(self, java, jar) -> None:
        """Randomizes (or copies) the ROM of every player in parallel threads and assembles the session."""
        roms = self.model.player_roms()
        try:
            base = {}
            for rom in dict.fromkeys(roms):
                base[rom] = unpack(rom, self._staging / f"base-{len(base) + 1}{rom.suffix}")
            preset = self.model.preset

            def a_player(nr: int) -> Result:
                """Randomizes the ROM of one player."""
                dir = self._staging / f"p{nr}"
                if preset is None:
                    return without_randomizer(nr, base[roms[nr - 1]], dir)
                return randomize(nr, java, jar, preset, base[roms[nr - 1]], dir)

            parallel = 2 if roms[0].system == "nds" else len(roms)
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                for result in pool.map(a_player, range(1, len(roms) + 1)):
                    self.results[result.nr] = result
            for file in base.values():
                file.unlink(missing_ok=True)
        except Exception as error:
            for nr in range(1, len(roms) + 1):
                self.results.setdefault(nr, Result(nr, False, None, str(error)))

    @property
    def done(self) -> bool:
        """True when the background work has finished."""
        return self._thread is not None and not self._thread.is_alive()

    def update(self, dt: float) -> None:
        """Advances the animation and starts the game when everything is done."""
        self.time += dt
        if self.menu is not None or not self.done:
            return
        if all(e.ok for e in self.results.values()):
            session = self._session()
            staging_finish(self._staging, session, self.app.sessions_dir)
            self._staging = None
            from .assignment import AssignmentScreen

            self.app.switch(AssignmentScreen(self.app, session))
        else:
            self.actions = ["again", "different"]
            self.menu = Menu([t("randomize.again"), t("randomize.other_game")])

    def _session(self) -> Session:
        """Builds the session object from the results."""
        now = datetime.now().isoformat(timespec="seconds")
        preset = self.model.preset
        player = [Player(nr, rom.file.name, self.results[nr].seed, False, rom.system, volume=0,
                           name=self.model.names.get(nr), mac=nds_mac(nr) if rom.system == "nds" else None)
                   for nr, rom in enumerate(self.model.player_roms(), start=1)]
        return Session(self.model.name, now, now, 0, preset.name if preset else None, "", player)

    def raw(self, ev) -> None:
        """Handles Escape in the error menu."""
        if self.menu is not None and ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self._selection("different")

    def event(self, e) -> None:
        """Handles a key in the error menu."""
        if self.menu is None or not isinstance(e, KeysEvent) or not e.pressed:
            return
        choice = self.menu.event(e.key)
        if choice is not None:
            self._selection(self.actions[choice] if isinstance(choice, int) else "different")

    def _selection(self, action: str) -> None:
        """Runs the chosen action of the error menu."""
        self._discard()
        if action == "again":
            self._start()
        else:
            from .new_session import NewSessionScreen

            self.app.switch(NewSessionScreen(self.app, self.model))

    def _discard(self) -> None:
        """Stops the background work and deletes the staging folder."""
        if self._thread is not None:
            self._thread.join()
        if self._staging is not None:
            staging_discard(self._staging)
            self._staging = None

    def leave(self) -> None:
        """Cleans up when another screen takes over."""
        self._discard()

    def draw(self, area) -> None:
        """Draws the progress or the error menu."""
        def g(n):
            """Scales a base size to the screen."""
            return graphics.size(area, n)

        graphics.title(area, t("randomize.title" if self.model.preset else "randomize.title_without"), self.model.name)
        x, width, height, y = g(200), g(1100), g(84), g(240)
        if self.error:
            rect = pygame.Rect(x, y, width, height)
            graphics.card(area, rect)
            graphics.text(area, graphics.shorten(self.error, g(26), width - g(64), "Medium"),
                        (rect.x + g(32), rect.centery), g(26), graphics.ERROR, "midleft", weight="Medium")
            y += height + g(16)
        for nr, rom in enumerate(self.model.player_roms(), start=1):
            rect = pygame.Rect(x, y, width, height)
            graphics.card(area, rect)
            left = graphics.badge(area, (rect.x + g(32), rect.centery), nr, g(22)).right + g(20)
            graphics.text(area, t("randomize.player", nr=nr, game=rom.game), (left, rect.centery + 2), g(32), graphics.TEXT,
                        "midleft")
            e = self.results.get(nr)
            right = (rect.right - g(32), rect.centery + 2)
            if e is None:
                r = graphics.text(area, t("randomize.runs"), right, g(28), graphics.DIMMED, "midright", weight="Medium")
                graphics.spinner(area, (r.left - g(30), rect.centery), g(14), self.time)
            elif e.ok:
                content = t("randomize.done_seed", seed=e.seed) if e.seed else t("randomize.done")
                graphics.text(area, content, right, g(28), graphics.OK, "midright", weight="Medium")
            else:
                content = graphics.shorten(t("randomize.error", message=e.message), g(26), width // 2, "Medium")
                graphics.text(area, content, right, g(26), graphics.ERROR, "midright", weight="Medium")
            y += height + g(16)
        if self.menu is not None:
            rect = pygame.Rect(x, y + g(30), g(520), 2 * g(80) + g(20))
            graphics.draw_menu(area, self.menu, rect, g(30), map_height=g(80), gap=g(20))
            graphics.footer(area, [("A", t("hint.select")), ("B", t("randomize.other_game"))])
