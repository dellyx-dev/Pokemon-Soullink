"""Choose a saved session and resume it, or delete it (X, confirm by typing "DELETE")."""
from __future__ import annotations

import pygame

from ..input.devices import KeysEvent
from ..roms import game_name_from_file
from ..language import t
from ..input.keys import Key
from ..session import Session, all_sessions, missing_roms, session_delete
from . import graphics
from .app import Screen
from .menu import BACK, Menu
from .keyboard import VirtualKeyboard, hints, draw_field

VISIBLE = 6
CONFIRMATION = "DELETE"


def playtime(seconds: int) -> str:
    """Formatted playtime for a number of seconds."""
    return t("resume.playtime", hours=seconds // 3600, minutes=f"{seconds // 60 % 60:02d}")


def details(s: Session) -> str:
    """One-line description of a session: games and player count."""
    games = sorted({game_name_from_file(s.rom(sp.nr)) or "?" for sp in s.player})
    year, month, tag = s.last_played[:10].split("-") if len(s.last_played) >= 10 else ("", "", "")
    day = f"{tag}.{month}.{year}" if year else "?"
    return t("resume.details", games=" / ".join(games), count=len(s.player),
             playtime=playtime(s.playtime_seconds), day=day)


class ResumeScreen(Screen):
    """List of saved sessions to resume or delete."""

    def __init__(self, app):
        """Creates the screen and loads the sessions."""
        super().__init__(app)
        self.message: str | None = None
        self.delete: VirtualKeyboard | None = None
        self.wrong = False
        self.time = 0.0
        self._load()

    def _load(self, selection: int = 0) -> None:
        """Reads the session list and selects an entry."""
        self.sessions = all_sessions(self.app.sessions_dir)
        self.details = [details(s) for s in self.sessions]
        self.menu = Menu([s.name for s in self.sessions])
        self.menu.selection = max(0, min(selection, len(self.sessions) - 1))

    def raw(self, ev) -> None:
        """Handles Escape."""
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if self.delete is not None:
                self.delete = None
            else:
                self._back()

    def update(self, dt: float) -> None:
        """Advances the animation time."""
        self.time += dt

    def _back(self) -> None:
        """Returns to the start screen."""
        from .start import StartScreen

        self.app.switch(StartScreen(self.app))

    def event(self, e) -> None:
        """Handles a key: choose, resume or ask for deletion."""
        if not isinstance(e, KeysEvent) or not e.pressed:
            return
        self.message = None
        if self.delete is not None:
            self._delete_event(e.key)
            return
        if e.key == Key.WEST and self.sessions:
            self.delete, self.wrong = VirtualKeyboard("", len(CONFIRMATION) + 4), False
            return
        choice = self.menu.event(e.key)
        if choice == BACK:
            self._back()
        elif isinstance(choice, int):
            session = self.sessions[choice]
            missing = missing_roms(session)
            if missing:
                self.message = t("resume.rom_missing", file=missing[0])
                return
            from .assignment import AssignmentScreen

            self.app.switch(AssignmentScreen(self.app, session))

    def _delete_event(self, key: Key) -> None:
        """Handles a key during the delete confirmation."""
        result = self.delete.event(key)
        if result == "cancel":
            self.delete = None
        elif result == "done" and self.delete.text.strip() != CONFIRMATION:
            self.wrong = True
        elif result == "done":
            self.delete = None
            session = self.sessions[self.menu.selection]
            try:
                session_delete(session, self.app.sessions_dir)
            except (OSError, ValueError) as error:
                self.message = t("resume.delete_error", error=error)
            self._load(self.menu.selection)
        else:
            self.wrong = False

    def draw(self, area) -> None:
        """Draws the session list."""
        def g(n):
            """Scales a base size to the screen."""
            return graphics.size(area, n)

        count = len(self.sessions)
        graphics.title(area, t("resume.title"),
                     t("resume.count_one" if count == 1 else "resume.count", count=count) if count else None)
        x, width = g(200), area.get_width() - g(400)
        if not self.sessions:
            rect = pygame.Rect(x, g(260), width, g(180))
            graphics.panel(area, rect, opaque=False)
            graphics.text(area, t("resume.no"), (rect.x + g(40), rect.centery), g(34),
                        graphics.DIMMED, "midleft")
        else:
            first = min(max(0, self.menu.selection - VISIBLE + 1), max(0, count - VISIBLE))
            y = g(240)
            for i in range(first, min(count, first + VISIBLE)):
                chosen = i == self.menu.selection
                rect = pygame.Rect(x, y, width, g(104))
                graphics.card(area, rect, chosen)
                s = self.sessions[i]
                graphics.text(area, graphics.shorten(s.name, g(34), width - g(300)), (rect.x + g(32), rect.y + g(38)),
                            g(34), (255, 255, 255) if chosen else graphics.TEXT, "midleft")
                graphics.text(area, graphics.shorten(self.details[i], g(24), width - g(300), "Medium"),
                            (rect.x + g(32), rect.y + g(76)), g(24), (235, 235, 255) if chosen else graphics.DIMMED,
                            "midleft", weight="Medium")
                right = rect.right - g(32)
                for sp in reversed(s.player):
                    right = graphics.badge(area, (right, rect.centery), sp.nr, g(18), inverted=chosen,
                                              anchor="midright").left - g(10)
                y += g(122)
        if self.message:
            rect = pygame.Rect(x, area.get_height() - g(200), width, g(70))
            graphics.panel(area, rect)
            graphics.text(area, graphics.shorten(self.message, g(26), width - g(64), "Medium"),
                        (rect.x + g(32), rect.centery), g(26), graphics.ERROR, "midleft", weight="Medium")
        if self.delete is not None:
            self._draw_delete(area, g)
            return
        legend = [("A", t("resume.resume")), ("B", t("hint.back"))]
        if self.sessions:
            legend.insert(1, ("X", t("resume.delete")))
        graphics.footer(area, legend)

    def _draw_delete(self, area, g) -> None:
        """Draws the confirmation: session name, field for DELETE and on-screen keyboard."""
        graphics.dim(area, area.get_rect(), 150)
        u = g(44)
        width = min(area.get_width() - g(120), g(1000))
        height = g(170) + round(u * 1.4) + VirtualKeyboard.height(u) + g(80)
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (area.get_width() // 2, (area.get_height() - g(80)) // 2)
        graphics.panel(area, rect)
        inside = rect.inflate(-g(80), -g(70))
        name = self.sessions[self.menu.selection].name
        graphics.text(area, graphics.shorten(t("resume.delete_title", name=name), g(38), inside.width, "Bold"),
                    (inside.x, inside.y + g(18)), g(38), graphics.ERROR, "midleft", weight="Bold")
        hint = t("resume.delete_wrong" if self.wrong else "resume.delete_text", word=CONFIRMATION)
        graphics.text(area, graphics.shorten(hint, g(26), inside.width, "Medium"), (inside.x, inside.y + g(70)), g(26),
                    graphics.ERROR if self.wrong else graphics.DIMMED, "midleft", weight="Medium")
        field = pygame.Rect(inside.x, inside.y + g(110), inside.width, round(u * 1.4))
        draw_field(area, field, u, self.delete.text, True, self.time, placeholder=CONFIRMATION)
        self.delete.draw(area, pygame.Rect(inside.x, field.bottom + g(30), inside.width,
                                                    inside.bottom - field.bottom - g(30)), u)
        graphics.footer(area, hints())
