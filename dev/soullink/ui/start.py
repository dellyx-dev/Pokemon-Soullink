"""Start screen: new session, resume session, quit."""
from __future__ import annotations

import time

import pygame

from .. import AUTHOR
from ..input.devices import KeysEvent
from ..input.keys import Key
from ..language import t
from . import graphics
from .app import Screen
from .menu import BACK, Menu

ENTRIES = ["start.new_session", "start.resume", "start.settings", "start.about", "start.end"]
SETTINGS, ABOUT, END = 2, 3, 4
TITLE = "Pokémon Soullink"
AFTER_GAME_LOCK = 0.3
VOLUME_STEP = 1


def trademark_notice(area, y: int) -> None:
    """Small centered Pokemon trademark notice (main menu and "About")."""
    pixel = graphics.size(area, 19)
    for i, row in enumerate((t("mark.row1"), t("mark.row2"))):
        graphics.text(area, row, (area.get_width() // 2, y + i * round(pixel * 1.45)), pixel, graphics.DIMMED,
                    "center", weight="Medium")


class StartScreen(Screen):
    """The main menu."""

    def __init__(self, app, lock: float = 0.0):
        """Creates the main menu; lock blocks input for that many seconds."""
        super().__init__(app)
        self.menu = Menu([t(k) for k in ENTRIES])
        self.question: Menu | None = None
        self.locked_until = time.monotonic() + lock
        app.music.start()

    def event(self, e) -> None:
        """Handles a menu key."""
        if not isinstance(e, KeysEvent) or not e.pressed or time.monotonic() < self.locked_until:
            return
        if self.question is not None:
            choice = self.question.event(e.key)
            if choice == 1:
                self.app.end()
            elif choice == 0 or choice == BACK:
                self.question = None
            return
        choice = self.menu.event(e.key)
        if choice == 0:
            from .new_session import NewSessionScreen

            self.app.switch(NewSessionScreen(self.app))
        elif choice == 1:
            from .resume import ResumeScreen

            self.app.switch(ResumeScreen(self.app))
        elif choice == SETTINGS:
            from .settings import SettingsScreen

            self.app.switch(SettingsScreen(self.app))
        elif choice == ABOUT:
            from .about import AboutScreen

            self.app.switch(AboutScreen(self.app))
        elif choice == END:
            self.question = Menu([t("general.no"), t("start.yes_end")])

    def draw(self, area) -> None:
        """Draws the main menu."""
        def g(n):
            """Scales a base size to the screen."""
            return graphics.size(area, n)

        middle = area.get_width() // 2
        radius, gap = g(46), g(26)
        width = graphics.load_font(g(92), "ExtraBold").size(TITLE)[0]
        x = middle - (2 * radius + gap + width) // 2
        graphics.pokeball(area, (x + radius, g(250)), radius)
        x += 2 * radius + gap
        graphics.text(area, TITLE, (x, g(254)), g(92), graphics.TEXT, "midleft", weight="ExtraBold")
        under = graphics.text(area, t("start.subtitle") + "  ·  ", (x + g(4), g(330)), g(32), graphics.DIMMED,
                            "midleft", weight="Medium")
        graphics.text(area, t("start.of", author=AUTHOR), (under.right, g(330)), g(32), graphics.ACCENT2, "midleft",
                    weight="SemiBold")
        rect = pygame.Rect(middle - g(330), g(410), g(660), g(5 * 82 + 4 * 18))
        if self.question is not None:
            graphics.text(area, t("start.question_end"), (middle, rect.y + g(40)), g(44), graphics.TEXT, "center",
                        weight="Bold")
            rect = pygame.Rect(rect.x, rect.y + g(118), rect.width, g(2 * 92 + 26))
            graphics.draw_menu(area, self.question, rect, g(34), map_height=g(92), gap=g(26))
            graphics.footer(area, [("A", t("hint.select")), ("B", t("hint.back"))])
            return
        self.menu.entries = [t(k) for k in ENTRIES]
        graphics.draw_menu(area, self.menu, rect, g(34), map_height=g(82), gap=g(18))
        graphics.footer(area, [("A", t("hint.select"))])
        trademark_notice(area, area.get_height() - g(140))
