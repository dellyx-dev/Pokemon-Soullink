"""Overlay per player: tabs side by side with L/R to page through them; the core only has the "Types" tab (table). Plugins
add more tabs, ordered by their own position."""
from __future__ import annotations

import pygame

from .. import types
from ..input.keys import BACK_KEYS, Key
from ..plugin.api import Tab
from ..language import t
from . import graphics

DIM = 45
OPACITY = 160
LEVELS = {
    4: ((46, 204, 113), "4×"),
    2: ((120, 224, 143), "2×"),
    0.5: ((255, 170, 90), "½×"),
    0.25: ((255, 107, 107), "¼×"),
    0: ((130, 130, 150), "0×"),
}
TABLE_RESULT = {1: "table.1", 2: "table.2", 0.5: "table.05", 0: "table.0"}
CELLS = {2: ((120, 224, 143), "2", (20, 40, 25)), 0.5: ((255, 120, 110), "½", (60, 15, 15)),
          0: ((105, 105, 128), "0", (20, 20, 28))}
DARKER_TEXT = (24, 24, 30)


def _is_bright(color) -> bool:
    """True for a color that needs dark text."""
    return 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2] > 160


def draw_type(area: pygame.Surface, type_: str, rect: pygame.Rect, pixel: int, short: bool = False) -> None:
    """Draws a type chip in the official type color."""
    color = types.COLORS[type_]
    rect = pygame.Rect(rect)
    area.blit(graphics.rounded_rect(rect.size, max(3, rect.height // 3), (*color, 255)), rect)
    content = types.short(type_) if short else types.display(type_)
    graphics.text(area, graphics.shorten(content, pixel, rect.width - 4, "Bold"), (rect.centerx, rect.centery + 1),
                pixel, DARKER_TEXT if _is_bright(color) else (255, 255, 255), "center", weight="Bold")


def chip_size(u: int, width: int) -> tuple[int, int, int]:
    """Width, height and font size of a type chip: as wide as the longest type name, at most a third of the width."""
    pixel = max(9, round(u * 0.56))
    b = max(graphics.load_font(pixel, "Bold").size(types.display(type_))[0] for type_ in types.TYPES) + u // 2
    return min(b, width // 3), round(u * 1.25), pixel


def tab_order(tab: list, discarded=None) -> list:
    """Orders tabs by their own position (ties keep the given order); a tab with `replaced` removes the tab with that id,
    also among tabs of other plugins."""
    discarded = discarded or (lambda tab, reason: None)
    targets: dict[str, object] = {}
    keep = []
    for r in tab:
        target = getattr(r, "replaced", None)
        if target:
            if target in targets:
                discarded(r, f'replaces "{target}", which another tab already replaces')
                continue
            targets[target] = r
        keep.append(r)
    result, ids = [], set()
    for r in keep:
        if r.id in targets and targets[r.id] is not r:
            continue
        if r.id in ids:
            discarded(r, f'the tab id "{r.id}" already exists')
            continue
        ids.add(r.id)
        result.append(r)
    return sorted(result, key=lambda r: r.position)


class TypesTab(Tab):
    """Core tab "Types": the whole type table with attackers in rows and defenders in columns."""
    id, position = "types", 40

    def __init__(self):
        """Starts with the cursor at the first attacker and defender."""
        self.row = 0
        self.column = 0

    def title(self, short: bool = False) -> str:
        """Tab title, abbreviated if short."""
        return t("tab_short.types") if short else t("tab.types")

    def event(self, key: Key) -> bool:
        """Moves the cursor in the table."""
        count = len(types.TYPES)
        step = {Key.RIGHT: 1, Key.LEFT: -1}.get(key, 0)
        up_down = {Key.DOWN: 1, Key.UP: -1}.get(key, 0)
        if not (step or up_down):
            return False
        self.row = (self.row + up_down) % count
        self.column = (self.column + step) % count
        return True

    def hints(self) -> list[tuple[str, str]]:
        """Button hints of the tab."""
        return [("<>", t("overlay.column")), ("L/R", t("hint.page")), ("B", t("hint.close"))]

    def draw(self, area, rect: pygame.Rect, u: int, time: float = 0.0) -> None:
        """Draws the tab."""
        self._draw_table(area, rect, u)

    def _draw_table(self, area, rect: pygame.Rect, u: int) -> None:
        """Draws the type table."""
        count = len(types.TYPES)
        info_h = round(u * 1.3)
        s = max(8, min(rect.width * 10 // (count * 10 + 24), (rect.height - info_h - u // 2) * 10 // (count * 10 + 12)))
        header_b, header_h = round(s * 2.4), round(s * 1.2)
        with_text = s >= 20
        grid = pygame.Rect(0, 0, header_b + s * count, header_h + s * count)
        grid.midtop = (rect.centerx, rect.y)
        x0, y0 = grid.x + header_b, grid.y + header_h
        pixel = max(8, round(s * 0.42))
        for i, type_ in enumerate(types.TYPES):
            draw_type(area, type_, pygame.Rect(grid.x, y0 + i * s + 1, header_b - 3, s - 2), pixel, short=True)
            column = pygame.Rect(x0 + i * s + 1, grid.y, s - 2, header_h - 3)
            if s >= 22:
                draw_type(area, type_, column, max(7, round(s * 0.34)), short=True)
            else:
                area.blit(graphics.rounded_rect(column.size, max(2, s // 5), (*types.COLORS[type_], 255)), column)
        marker = pygame.Surface((s * count, s), pygame.SRCALPHA)
        marker.fill((255, 255, 255, 28))
        area.blit(marker, (x0, y0 + self.row * s))
        marker = pygame.Surface((s, s * count), pygame.SRCALPHA)
        marker.fill((255, 255, 255, 28))
        area.blit(marker, (x0 + self.column * s, y0))
        for z, attacker in enumerate(types.TYPES):
            for sp, defender in enumerate(types.TYPES):
                cell = pygame.Rect(x0 + sp * s, y0 + z * s, s, s)
                value = types.factor(attacker, defender)
                if value == 1:
                    pygame.draw.rect(area, (255, 255, 255, 18), cell, 1)
                    continue
                color, content, load_font_color = CELLS[value]
                pygame.draw.rect(area, color, cell.inflate(-2, -2), border_radius=max(2, s // 6))
                if with_text:
                    graphics.text(area, content, (cell.centerx, cell.centery + 1), round(s * 0.6), load_font_color,
                                "center", weight="Bold")
        active = pygame.Rect(x0 + self.column * s, y0 + self.row * s, s, s)
        pygame.draw.rect(area, (255, 255, 255), active.inflate(4, 4), 2, border_radius=max(2, s // 5))
        attacker, defender = types.TYPES[self.row], types.TYPES[self.column]
        value = types.factor(attacker, defender)
        chip_w, chip_h, chip_font = chip_size(u, rect.width)
        y = grid.bottom + u // 2
        x = rect.centerx - (2 * chip_w + u * 9) // 2
        draw_type(area, attacker, pygame.Rect(x, y, chip_w, chip_h), chip_font)
        r = graphics.text(area, t("overlay.against"), (x + chip_w + u // 3, y + chip_h // 2), max(9, round(u * 0.55)),
                        graphics.DIMMED,
                        "midleft", weight="Medium")
        draw_type(area, defender, pygame.Rect(r.right + u // 3, y, chip_w, chip_h), chip_font)
        result = t(TABLE_RESULT[value]) if value == 1 else f"{LEVELS[value][1]} {t(TABLE_RESULT[value])}"
        color = graphics.TEXT if value == 1 else LEVELS[value][0]
        graphics.text(area, result, (r.right + u // 3 + chip_w + u // 2, y + chip_h // 2), max(10, round(u * 0.62)), color,
                    "midleft", weight="Bold")
        if not with_text:
            lx, ly = grid.right + u // 2, grid.y + header_h
            for value_, (color, content, _) in CELLS.items():
                pygame.draw.rect(area, color, (lx, ly, s, s), border_radius=max(2, s // 6))
                graphics.text(area, f"{content}×", (lx + s + 4, ly + s // 2), max(9, round(u * 0.5)), graphics.TEXT,
                            "midleft", weight="SemiBold")
                ly += s + 6


class TypesOverlay:
    """Frame with a header (tabs), the content of the open tab and a button row; L/R pages, B/Y/Select closes."""

    def __init__(self, tab: list | None = None, discarded=None):
        """Creates the overlay with an optional tab list."""
        self.tab: list = []
        self.page = 0
        self.tab_set([TypesTab()] if tab is None else tab, discarded)

    def tab_set(self, tab: list, discarded=None) -> None:
        """Sets a new tab list (ordered by tab_order); the open tab stays open if it still exists."""
        open_ = self.active.id if self.tab else None
        self.tab = tab_order(tab, discarded)
        if not self.show(open_):
            self.page = min(self.page, max(0, len(self.tab) - 1))

    @property
    def active(self):
        """The open tab; None if there are none."""
        return self.tab[self.page] if self.tab else None

    def find(self, tab_id: str):
        """The tab with this id; None if there is none."""
        return next((r for r in self.tab if r.id == tab_id), None)

    def show(self, tab_id: str | None) -> bool:
        """Opens the tab with this id; False if there is none."""
        for i, r in enumerate(self.tab):
            if r.id == tab_id:
                self.page = i
                return True
        return False

    def close(self) -> None:
        """The overlay closes: closes the on-screen keyboards of the tabs."""
        for tab in self.tab:
            if hasattr(tab, "keyboard_close"):
                tab.keyboard_close()

    def event(self, key: Key) -> str | None:
        """Returns "close" for the north key, B or Select (unless the tab needs the key itself), else None."""
        if key in (Key.L, Key.R) and self.tab:
            self.page = (self.page + (1 if key == Key.R else -1)) % len(self.tab)
            return None
        if self.active is not None and self.active.event(key):
            return None
        if key == Key.NORTH or key in BACK_KEYS:
            return "close"
        return None

    def draw(self, area: pygame.Surface, range_: pygame.Rect, pixel: int, time: float = 0.0) -> None:
        """Draws the overlay into the range."""
        range_ = pygame.Rect(range_)
        graphics.dim(area, range_, DIM)
        margin = max(6, pixel // 3)
        panel = range_.inflate(-2 * margin, -2 * margin)
        graphics.panel(area, panel, opacity=OPACITY)
        u = max(11, min(44, panel.height // 15, panel.width // 20))
        inside = panel.inflate(-u, -u)
        header = self._draw_header(area, inside, u)
        foot_height = round(u * 1.3)
        content = pygame.Rect(inside.x, header.bottom + u // 2, inside.width, inside.bottom - header.bottom - u // 2 - foot_height)
        if self.active is not None:
            self.active.draw(area, content, u, time)
        self._draw_foot(area, pygame.Rect(inside.x, inside.bottom - foot_height, inside.width, foot_height), u)

    def _draw_header(self, area, inside: pygame.Rect, u: int) -> pygame.Rect:
        """Draws the tab header and returns the remaining area."""
        height = round(u * 1.5)
        header = pygame.Rect(inside.x, inside.y, inside.width, height)
        pixel = max(10, round(u * 0.62))
        k = round(u * 1.1)
        if len(self.tab) > 1:
            start = graphics.button(area, (header.x, header.centery), "L", k).right + u // 2
            end = graphics.button(area, (header.right, header.centery), "R", k, anchor="midright").left - u // 2
        else:
            start, end = header.x, header.right + u // 4
        width = (end - start) // max(1, len(self.tab))
        slot = width - u // 4 - 10
        names, p = [r.title() for r in self.tab], pixel
        while p > pixel * 85 // 100 and any(graphics.load_font(p, "Bold").size(n)[0] > slot for n in names):
            p -= 1
        if any(graphics.load_font(p, "Bold").size(n)[0] > slot for n in names):
            names, p = [r.title(short=True) for r in self.tab], pixel
        for i, name in enumerate(names):
            rect = pygame.Rect(start + i * width, header.y, width - u // 4, height)
            if i == self.page:
                area.blit(graphics.gradient_rect(rect.size, height // 2), rect)
                color = (255, 255, 255)
            else:
                area.blit(graphics.rounded_rect(rect.size, height // 2, (255, 255, 255, 0), 2, (255, 255, 255, 50)), rect)
                color = graphics.DIMMED
            graphics.text(area, graphics.shorten(name, p, rect.width - 8, "Bold"), (rect.centerx, rect.centery + 1),
                        p, color, "center", weight="Bold")
        return header

    def _draw_foot(self, area, rect: pygame.Rect, u: int) -> None:
        """Draws the button row at the bottom."""
        k, pixel = round(u * 0.95), max(9, round(u * 0.5))
        entries = self.active.hints() if self.active is not None else []
        if len(self.tab) <= 1:
            entries = [(symbol, text) for symbol, text in entries if symbol != "L/R"]
        entries = [(t("button.top") if symbol == "^" else symbol, text) for symbol, text in entries]
        graphics.button_row(area, rect.center, entries, k, pixel, u, rect.width)
