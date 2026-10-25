"""Free screen field in the game (e.g. with 3 GBA players): a header with title, session and playtime and a display below."""
from __future__ import annotations

import pygame

from ..plugin.api import Display
from ..plugin.loader import ALTERNATING, CORE_DISPLAY, field_display
from ..language import t
from . import graphics

SWITCH = 15.0


class SessionDisplay(Display):
    """Core display "Session": badge and game name of each player."""

    def __init__(self, player: list[tuple[int, str]]):
        """Creates the display for the (number, game name) pairs of the players."""
        self.player = player

    def draw(self, area, rect, u: int, time: float) -> None:
        """Draws badge and game name per player."""
        height, gap = round(u * 1.7), max(4, u // 3)
        pixel = max(10, round(u * 0.62))
        for i, (nr, name) in enumerate(self.player):
            row = pygame.Rect(rect.x, rect.y + i * (height + gap), rect.width, height)
            if row.bottom > rect.bottom:
                break
            graphics.card(area, row, radius=height // 3)
            badge_rect = graphics.badge(area, (row.x + u // 2, row.centery), nr, max(9, round(u * 0.6)))
            graphics.text(area, graphics.shorten(name, pixel, row.right - badge_rect.right - u, "SemiBold"),
                        (badge_rect.right + u // 2, row.centery + 1), pixel, graphics.TEXT, "midleft", weight="SemiBold")


class FreeField:
    """Chooses which display the free field shows according to the "Free field" setting: empty is the first one,
    "alternating" cycles through all, and the core display "Session" comes after the plugin displays."""

    def __init__(self, show: list[tuple[str, str, object]], core):
        """Creates the field from the plugin displays (id, title, display) and the core display."""
        self.show = list(show)
        self.core = core

    def current(self, setting: str, time: float) -> tuple[str, str, object]:
        """The (id, title, display) shown for the setting at the given time."""
        all_ = [*self.show, (CORE_DISPLAY, t("once.field_session"), self.core)]
        choice = field_display(setting, [a[0] for a in self.show])
        if choice == ALTERNATING:
            return all_[int(time // SWITCH) % len(all_)]
        return next(a for a in all_ if a[0] == choice)

    def draw(self, area, cell: pygame.Rect, setting: str, time: float, session: str,
                 playtime: float) -> None:
        """Draws the header and the current display into the cell."""
        _, title_text, display = self.current(setting, time)
        rect = pygame.Rect(cell).inflate(-graphics.size(area, 32), -graphics.size(area, 32))
        graphics.card(area, rect, radius=graphics.size(area, 28))
        u = max(11, min(40, rect.height // 15, rect.width // 20))
        inside = rect.inflate(-u, -u)
        seconds = int(playtime)
        title = graphics.text(area, graphics.shorten(title_text, round(u * 0.8), inside.width // 2, "Bold"),
                            (inside.x, inside.y + u // 2), round(u * 0.8), graphics.TEXT, "midleft", weight="Bold")
        duration = t("game.playtime", hours=seconds // 3600, minutes=f"{seconds // 60 % 60:02d}")
        right = graphics.text(area, duration, (inside.right, inside.y + u // 2), round(u * 0.55), graphics.DIMMED,
                             "midright", weight="Medium")
        graphics.text(area, graphics.shorten(session, round(u * 0.55), right.left - title.right - u, "Medium"),
                    (title.right + u // 2, inside.y + u // 2 + 1), round(u * 0.55), graphics.DIMMED, "midleft",
                    weight="Medium")
        content = pygame.Rect(inside.x, inside.y + round(u * 1.4), inside.width, inside.height - round(u * 1.4))
        display.draw(area, content, u, time)
