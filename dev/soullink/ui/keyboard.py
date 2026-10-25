"""On-screen keyboard for controllers (A-Z as in the name entry of the Pokemon games) and search in lists. Text comes in
through the keyboard only; the real keyboard is not needed."""
from __future__ import annotations

import unicodedata

import pygame

from ..input.keys import CONFIRM, Key
from ..language import t
from . import graphics

CHAR = ["ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZÄÖÜß", "0123456789", "-.'&:!?()_"]
COLUMNS = 10
SPECIAL_KEYS = [("empty", 4), ("delete", 2), ("large", 2), ("done", 2)]
REASON, REASON_OPACITY = (16, 14, 36), 150


def simplified(text: str) -> str:
    """Text for searching: without accents and umlaut dots and case-folded ("Affchen" matches "affchen")."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()


class VirtualKeyboard:
    """On-screen keyboard with a cursor, upper/lower case and a maximum text length."""

    def __init__(self, text: str = "", max_length: int = 40):
        """Creates the keyboard with a start text."""
        self.text = text
        self.max_length = max_length
        self.row = 0
        self.column = 0
        self.large = True

    def _rows(self) -> list[list[tuple[str, int, int]]]:
        """Per row: (character or action, first column, width)."""
        rows = [[(z if self.large else z.lower(), i, 1) for i, z in enumerate(row)] for row in CHAR]
        special, x = [], 0
        for action, width in SPECIAL_KEYS:
            special.append((action, x, width))
            x += width
        return rows + [special]

    def _index(self, row: list) -> int:
        """Index of the key under the cursor in a row."""
        return next(i for i, (_, x, b) in enumerate(row) if x <= self.column < x + b)

    def chosen(self) -> str:
        """The character or action under the cursor."""
        row = self._rows()[self.row]
        return row[self._index(row)][0]

    def _tap(self, char: str) -> None:
        """Appends a character if the maximum length allows it."""
        if len(self.text) < self.max_length:
            self.text += char

    def event(self, key: Key) -> str | None:
        """Returns "done", "cancel" or None (text changed or selection moved)."""
        rows = self._rows()
        if key in (Key.UP, Key.DOWN):
            self.row = (self.row + (1 if key == Key.DOWN else -1)) % len(rows)
        elif key in (Key.LEFT, Key.RIGHT):
            row = rows[self.row]
            i = (self._index(row) + (1 if key == Key.RIGHT else -1)) % len(row)
            self.column = row[i][1]
        elif key in CONFIRM:
            value = self.chosen()
            if value == "done":
                return "done"
            if value == "delete":
                self.text = self.text[:-1]
            elif value == "large":
                self.large = not self.large
            else:
                self._tap(" " if value == "empty" else value)
        elif key in (Key.EAST, Key.SELECT):
            if not self.text:
                return "cancel"
            self.text = self.text[:-1]
        elif key == Key.NORTH:
            self._tap(" ")
        elif key == Key.WEST:
            self.large = not self.large
        elif key == Key.START:
            return "done"
        return None

    @staticmethod
    def height(u: int) -> int:
        """Height of the keyboard for a base unit."""
        return len(CHAR) * (round(u * 1.05) + max(2, u // 6)) + round(u * 1.05)

    def draw(self, area: pygame.Surface, rect: pygame.Rect, u: int) -> None:
        """Draws the key grid at the bottom of the rectangle on a slightly denser surface than the overlay below."""
        h, gap = round(u * 1.05), max(2, u // 6)
        b = (rect.width - (COLUMNS - 1) * gap) / COLUMNS
        y = rect.bottom - self.height(u)
        margin = max(3, u // 4)
        reason = pygame.Rect(rect.x - margin, y - margin, rect.width + 2 * margin, self.height(u) + 2 * margin)
        area.blit(graphics.rounded_rect(reason.size, h // 3 + margin, (*REASON, REASON_OPACITY)), reason)
        pixel = max(9, round(u * 0.52))
        label = {"empty": t("osk.empty"), "delete": t("osk.delete"), "large": "abc" if self.large else "ABC",
                        "done": t("hint.done")}
        for z, row in enumerate(self._rows()):
            for i, (value, x, width) in enumerate(row):
                key = pygame.Rect(round(rect.x + x * (b + gap)), y, round(width * b + (width - 1) * gap), h)
                chosen = z == self.row and i == self._index(row)
                if chosen:
                    area.blit(graphics.gradient_rect(key.size, h // 3), key)
                elif value == "done":
                    area.blit(graphics.rounded_rect(key.size, h // 3, (*graphics.ACCENT2, 40), 2, (*graphics.ACCENT2, 160)),
                                 key)
                else:
                    area.blit(graphics.rounded_rect(key.size, h // 3, (255, 255, 255, 20), 1, (255, 255, 255, 45)), key)
                graphics.text(area, graphics.shorten(label.get(value, value), pixel, key.width - 4, "Bold"),
                            (key.centerx, key.centery + 1), pixel, (255, 255, 255) if chosen else graphics.TEXT,
                            "center", weight="Bold")
            y += h + gap


def hints() -> list[tuple[str, str]]:
    """Legend shown while the on-screen keyboard is open."""
    return [("A", t("osk.tap")), ("B", t("osk.delete")), ("Y", t("osk.empty")), ("X", t("osk.large")),
            ("START", t("hint.done"))]


def draw_name_input(area: pygame.Surface, rect: pygame.Rect, pixel: int, nr: int | None, title: str,
                          keyboard: VirtualKeyboard, time: float, placeholder: str = "") -> None:
    """Draws a name entry for a player: title, text field and keyboard."""
    inside = rect.inflate(-pixel, -pixel)
    hints_h = round(pixel * 1.6)
    u = max(11, min(round(pixel * 1.1), (inside.height - hints_h) // 11, inside.width // 12))
    x, header = inside.x, inside.y + u // 2 + 2
    if nr is not None:
        x = graphics.badge(area, (inside.x, header), nr, round(u * 0.6)).right + u // 3
    graphics.text(area, graphics.shorten(title, round(u * 0.75), inside.right - x, "Bold"), (x, header + 1),
                round(u * 0.75), graphics.TEXT, "midleft", weight="Bold")
    field = pygame.Rect(inside.x, header + round(u * 0.6) + u // 2, inside.width, round(u * 1.3))
    draw_field(area, field, u, keyboard.text, True, time, placeholder=placeholder)
    keyboard.draw(area, pygame.Rect(inside.x, field.bottom + u // 2, inside.width,
                                           inside.bottom - hints_h - field.bottom - u // 2), u)
    graphics.button_row(area, (rect.centerx, inside.bottom - hints_h // 2), hints(), round(pixel * 0.7),
                      round(pixel * 0.5), pixel, rect.width - pixel)


def draw_field(area: pygame.Surface, rect: pygame.Rect, u: int, text: str, active: bool, time: float,
                 label: str = "", placeholder: str = "", right: str = "") -> None:
    """Draws a text field with label, cursor and placeholder."""
    area.blit(graphics.rounded_rect(rect.size, rect.height // 3, (255, 255, 255, 18), 2,
                                 (*graphics.ACCENT2, 200) if active else (255, 255, 255, 60)), rect)
    pixel = max(9, round(rect.height * 0.45))
    x = rect.x + rect.height // 2
    if label:
        x = graphics.text(area, label, (x, rect.centery + 1), round(pixel * 0.85), graphics.DIMMED, "midleft",
                        weight="SemiBold").right + pixel // 2
    right_x = rect.right - rect.height // 2
    if right:
        right_x = graphics.text(area, right, (right_x, rect.centery + 1), round(pixel * 0.8), graphics.DIMMED,
                               "midright", weight="Medium").x - pixel
    slot = right_x - x
    if text or not placeholder:
        stroke = "|" if active and int(time * 2) % 2 == 0 else ""
        content = text + stroke
        load_font = graphics.load_font(pixel, "SemiBold")
        while content and load_font.size(content)[0] > slot:
            content = content[1:]
        graphics.text(area, content, (x, rect.centery + 1), pixel, graphics.TEXT, "midleft")
    else:
        graphics.text(area, graphics.shorten(placeholder, pixel, slot, "Medium"), (x, rect.centery + 1), pixel,
                    graphics.DIMMED, "midleft", weight="Medium")


class Search:
    """Search term with an on-screen keyboard for a list; it filters while typing."""

    def __init__(self):
        """Starts with an empty term and no keyboard."""
        self.text = ""
        self.keyboard: VirtualKeyboard | None = None

    @property
    def is_open(self) -> bool:
        """True while the on-screen keyboard is open."""
        return self.keyboard is not None

    @property
    def active(self) -> bool:
        """True while filtering (keyboard open or a term in the field)."""
        return self.is_open or bool(self.text.strip())

    def open(self) -> None:
        """Opens the on-screen keyboard."""
        self.keyboard = VirtualKeyboard(self.text, max_length=24)

    def clear(self) -> None:
        """Clears the term and closes the keyboard."""
        self.text, self.keyboard = "", None

    def close(self) -> None:
        """Closes the keyboard but keeps the term (e.g. when the overlay is closed)."""
        self.keyboard = None

    def event(self, key: Key) -> str | None:
        """Call only with the keyboard open; "done" and "cancel" close it and the term stays."""
        result = self.keyboard.event(key)
        self.text = self.keyboard.text
        if result is not None:
            self.keyboard = None
        return result

    def fits(self, name: str) -> bool:
        """True if the name matches the term."""
        term = simplified(self.text.strip())
        return not term or term in simplified(name)

    def rank(self, name: str) -> int:
        """For sorting hits: 0 if the name starts with the term (first), 1 if it only contains it."""
        term = simplified(self.text.strip())
        return 0 if not term or simplified(name).startswith(term) else 1

    def hints(self) -> list[tuple[str, str]]:
        """Legend for the search."""
        return hints()

    def draw(self, area: pygame.Surface, rect: pygame.Rect, u: int, time: float, hit: int) -> pygame.Rect:
        """Search field on top and the keyboard below when open; returns the space left for the list."""
        if not self.active:
            return rect
        field = pygame.Rect(rect.x, rect.y, rect.width, round(u * 1.3))
        draw_field(area, field, u, self.text, self.is_open, time, t("osk.search_placeholder"),
                     right=t("osk.hit", count=hit))
        top = field.bottom + u // 3
        bottom = rect.bottom
        if self.is_open:
            gap = round(u * 0.6)
            self.keyboard.draw(area, pygame.Rect(rect.x, rect.y, rect.width, rect.height - gap), u)
            bottom = rect.bottom - gap - VirtualKeyboard.height(u) - u // 3
        return pygame.Rect(rect.x, top, rect.width, max(0, bottom - top))
