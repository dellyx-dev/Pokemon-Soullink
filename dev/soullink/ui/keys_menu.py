"""Rebinding keys in the player's own screen area: choose a function, then press the new key."""
from __future__ import annotations

import pygame

from ..input.keys import CONFIRM, Key
from ..input.key_binding import ONLY_DS, Function, KeyBinding, function_name
from ..language import t
from . import graphics

WAIT_TIME = 5.0
SPECIAL_ROWS = {"default": "keys.default"}
GROUPS = {"keys.group_game": {Function.A, Function.B, Function.X, Function.Y, Function.L, Function.R,
                                   Function.START, Function.SELECT},
           "keys.group_cross": {Function.UP, Function.DOWN, Function.LEFT, Function.RIGHT},
           "keys.group_extra": {Function.FAST_FORWARD, Function.MENU, Function.SWAP, Function.TOUCH}}


class KeysMenu:
    """List of the functions of a binding in which a function is chosen and its new key pressed."""

    def __init__(self, binding: KeyBinding, ds: bool, title: str = "", only_raw: bool = False,
                 nr: int | None = None):
        """Creates the menu for a binding, optionally restricted to raw input."""
        self.binding = binding
        self.title = title or t("keys.title")
        self.nr = nr
        self.ds = ds
        self.only_raw = only_raw
        self.rows: list = [f for f in Function if ds or f not in ONLY_DS] + list(SPECIAL_ROWS)
        self.selection = 0
        self.waits: Function | None = None
        self.wait_since = 0.0

    def event(self, key: Key, now: float) -> str | None:
        """Returns "done" to close (Start; B does nothing here); while waiting for a key every key is bound."""
        if self.waits is not None:
            if not self.only_raw:
                self.bind_with(key)
            return None
        if key in (Key.UP, Key.DOWN):
            self.selection = (self.selection + (1 if key == Key.DOWN else -1)) % len(self.rows)
        elif key == Key.START:
            return "done"
        elif key in CONFIRM:
            row = self.rows[self.selection]
            if row == "default":
                self.binding.default()
            else:
                self.waits, self.wait_since = row, now
        return None

    def bind_with(self, input) -> None:
        """Binds the chosen function to the input (position key or keyboard code)."""
        if self.waits is not None:
            self.binding.bind(self.waits, input)
            self.waits = None

    def update(self, now: float) -> None:
        """Cancels the wait for a key after the wait time."""
        if self.waits is not None and now - self.wait_since > WAIT_TIME:
            self.waits = None

    def _keys_text(self, function: Function) -> str:
        """Names of the keys bound to a function."""
        keys = self.binding.keys_for(function)
        return " / ".join(self.binding.name(key) for key in keys) if keys else t("keys.free")

    def _layout(self) -> list[tuple[str, object]]:
        """Rows from top to bottom as ("group", language key), ("row", index) or ("gap", "")."""
        layout, group = [], None
        for i, row in enumerate(self.rows):
            new = next((k for k, functions in GROUPS.items() if row in functions), None)
            if row == "default":
                layout.append(("gap", ""))
            elif new is not None and new != group:
                layout.append(("group", new))
            group = new
            layout.append(("row", i))
        return layout

    def draw(self, area: pygame.Surface, range_: pygame.Rect, pixel: int, now: float) -> None:
        """Draws the menu into the range."""
        range_ = pygame.Rect(range_)
        graphics.dim(area, range_, 205)
        margin = max(6, pixel // 3)
        panel = range_.inflate(-2 * margin, -2 * margin)
        graphics.panel(area, panel)
        u = max(11, min(40, panel.height // 16, panel.width // 20))
        corner = max(10, min(panel.width, panel.height) // 12)
        inside = panel.inflate(-2 * max(u, round(corner * 0.85)), -2 * max(u * 3 // 4, round(corner * 0.6)))
        header = inside.y + u // 2
        x = inside.x
        if self.nr is not None:
            x = graphics.badge(area, (inside.x, header), self.nr, round(u * 0.75)).right + u // 3
        height, gap = round(u * 1.2), max(3, u // 6)
        mass = {"row": height + gap, "group": round(u * 0.95), "gap": round(u * 0.4)}
        layout, positions, y = self._layout(), [], 0
        for kind, _ in layout:
            positions.append(y)
            y += mass[kind]
        foot = round(u * 1.2)
        list_ = pygame.Rect(inside.x, inside.y + round(u * 1.4), inside.width, inside.height - round(u * 1.4) - foot)
        counter = ""
        if y > list_.height:
            counter = f"{self.selection + 1} / {len(self.rows)}"
            graphics.text(area, counter, (inside.right, header), max(9, round(u * 0.5)), graphics.DIMMED, "midright",
                        weight="Medium")
        slot = inside.right - x - (graphics.load_font(max(9, round(u * 0.5)), "Medium").size(counter)[0] + u if counter else 0)
        graphics.text(area, graphics.shorten(self.title, round(u * 0.8), slot, "Bold"), (x, header), round(u * 0.8),
                    graphics.TEXT, "midleft", weight="Bold")
        middle = next(pos for (kind, value), pos in zip(layout, positions) if kind == "row" and value == self.selection)
        offset = max(0, min(middle + height // 2 - list_.height // 2, y - list_.height))
        old_clip = area.get_clip()
        area.set_clip(list_.clip(old_clip))
        for (kind, value), pos in zip(layout, positions):
            top = list_.y + pos - offset
            if top + mass[kind] < list_.y or top > list_.bottom:
                continue
            if kind == "group":
                graphics.text(area, t(value), (list_.x + u // 4, top + mass[kind] * 3 // 5), max(9, round(u * 0.45)),
                            graphics.DIMMED, "midleft", weight="SemiBold")
            elif kind == "row":
                self._draw_row(area, pygame.Rect(list_.x, top, list_.width, height), value, u)
        area.set_clip(old_clip)
        self._draw_foot(area, pygame.Rect(inside.x, inside.bottom - foot, inside.width, foot), u)
        if self.waits is not None:
            self._draw_wait(area, panel, u, now)

    def _draw_row(self, area, rect: pygame.Rect, i: int, u: int) -> None:
        """Draws one function row."""
        row = self.rows[i]
        chosen = i == self.selection
        load_font = max(9, round(u * 0.52))
        graphics.card(area, rect, chosen, radius=rect.height // 3, glowing=False)
        color = (255, 255, 255) if chosen else graphics.TEXT
        if row in SPECIAL_ROWS:
            graphics.text(area, t(SPECIAL_ROWS[row]), (rect.x + u // 2, rect.centery + 1), load_font, color,
                        "midleft", weight="Bold")
            return
        left = graphics.text(area, function_name(row, self.ds), (rect.x + u // 2, rect.centery + 1), load_font, color,
                            "midleft", weight="SemiBold")
        slot = rect.right - u // 2 - left.right - u
        graphics.text(area, graphics.shorten(self._keys_text(row), load_font, slot, "Medium"),
                    (rect.right - u // 2, rect.centery + 1), load_font, (235, 235, 255) if chosen else graphics.DIMMED,
                    "midright", weight="Medium")

    def _draw_foot(self, area, rect: pygame.Rect, u: int) -> None:
        """Draws the hint row at the bottom."""
        k, pixel = round(u * 0.95), max(9, round(u * 0.5))
        graphics.button_row(area, rect.center, [("A", t("hint.change")), ("START", t("hint.done"))], k,
                          pixel, u, rect.width)

    def _draw_wait(self, area, panel: pygame.Rect, u: int, now: float) -> None:
        """Draws the prompt that waits for a key."""
        graphics.dim(area, panel, 150)
        box = pygame.Rect(0, 0, min(panel.width - u, u * 18), u * 6)
        box.center = panel.center
        graphics.panel(area, box)
        graphics.text(area, t("keys.press_now"), (box.centerx, box.y + u * 1.2), max(9, round(u * 0.55)),
                    graphics.DIMMED, "center", weight="Medium")
        graphics.text(area, function_name(self.waits, self.ds), (box.centerx, box.y + u * 2.7), round(u * 1.05),
                    graphics.ACCENT2, "center", weight="Bold")
        rest = max(0.0, 1 - (now - self.wait_since) / WAIT_TIME)
        bar = pygame.Rect(box.x + u, box.bottom - round(u * 1.6), box.width - 2 * u, max(6, u // 3))
        area.blit(graphics.rounded_rect(bar.size, bar.height // 2, (255, 255, 255, 30)), bar)
        if rest > 0:
            area.blit(graphics.gradient_rect((max(bar.height, round(bar.width * rest)), bar.height),
                                             bar.height // 2), bar)
        graphics.text(area, t("keys.without_press"), (box.centerx, bar.bottom + u // 2),
                    max(8, round(u * 0.42)), graphics.DIMMED, "midtop", weight="Medium")
