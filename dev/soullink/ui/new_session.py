"""New session: choose the number of players, the game and name per player, the randomizer preset and the session name."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pygame

from ..input.devices import KeysEvent
from ..input.keys import CONFIRM, BACK_KEYS, Key
from ..randomizer import find_presets
from ..roms import BaseRom, find_base_roms
from ..session import with_name, default_name
from ..language import t
from .. import layout
from . import graphics
from .app import Screen
from .keyboard import VirtualKeyboard, hints, draw_field

MAX_PLAYER = 4
MAX_NAME = 40
MAX_PLAYER_NAME = 12


class NewSessionModel:
    """State of the new-session form: ROMs, presets, player count, chosen games, preset and names."""

    def __init__(self, roms: list[BaseRom], presets: list[Path], today: date):
        """Creates the model from the available ROMs and presets."""
        self.roms = roms
        self.presets = presets
        self.today = today
        self.count = MAX_PLAYER
        self.game_index = [0] * MAX_PLAYER
        self.own: set[int] = set()
        self.preset_index = 0 if presets else len(presets)
        self.own_name: str | None = None
        self.names: dict[int, str] = {}

    def count_change(self, delta: int) -> None:
        """Changes the player count within 1 to MAX_PLAYER."""
        self.count = min(MAX_PLAYER, max(1, self.count + delta))

    @property
    def system(self) -> str:
        """Game system of the session, taken from the first player's game."""
        return self.roms[self.game_index[0]].system if self.roms else "gba"

    def game_change(self, nr: int, delta: int) -> None:
        """Changes the game of a player; player 1 chooses freely, all others only games of the same system (one session has
        one system)."""
        if not self.roms:
            return
        if nr == 1:
            index = (self.game_index[0] + delta) % len(self.roms)
            self.game_index[0] = index
            for other in range(2, MAX_PLAYER + 1):
                if other not in self.own or self.roms[self.game_index[other - 1]].system != self.system:
                    self.game_index[other - 1] = index
                    self.own.discard(other)
            return
        matching = [i for i, r in enumerate(self.roms) if r.system == self.system]
        position = matching.index(self.game_index[nr - 1]) if self.game_index[nr - 1] in matching else 0
        self.game_index[nr - 1] = matching[(position + delta) % len(matching)]
        self.own.add(nr)

    def player_name(self, nr: int) -> str:
        """Display name of a player, "Player <nr>" without an own name."""
        return self.names.get(nr) or t("new.player_nr", nr=nr)

    def preset_change(self, delta: int) -> None:
        """Cycles through the presets, with "without randomizer" as the last option."""
        self.preset_index = (self.preset_index + delta) % (len(self.presets) + 1)

    @property
    def preset(self) -> Path | None:
        """The chosen preset file; None for "without randomizer"."""
        return self.presets[self.preset_index] if self.preset_index < len(self.presets) else None

    @property
    def preset_name(self) -> str:
        """Display name of the chosen preset."""
        return self.preset.stem if self.preset else t("new.without_randomizer")

    def player_roms(self) -> list[BaseRom]:
        """The chosen base ROM of every player."""
        return [self.roms[self.game_index[i]] for i in range(self.count)]

    @property
    def name(self) -> str:
        """Session name: the entered one or the suggested default."""
        return self.own_name or default_name(self.today, [r.game for r in self.player_roms()])


class NewSessionScreen(Screen):
    """Screen for creating a new session."""

    def __init__(self, app, model: NewSessionModel | None = None):
        """Creates the screen, optionally with a prepared model."""
        super().__init__(app)
        if model is None:
            roms = find_base_roms(app.rom_dir) + find_base_roms(app.rom_dir_nds)
            model = NewSessionModel(roms, find_presets(app.presets_dir), date.today())
        self.model = model
        self.row = 0
        self.keyboard: VirtualKeyboard | None = None
        self.keyboard_for: int | None = None
        self.time = 0.0

    def rows(self) -> list[tuple[str, str, str | None, int | None]]:
        """(kind, label, value, player number) for every row."""
        m = self.model
        rows = [("count", t("new.player"), str(m.count), None)]
        for nr, rom in enumerate(m.player_roms(), start=1):
            rows.append(("game", m.player_name(nr), rom.game, nr))
        rows += [("preset", t("new.randomizer"), m.preset_name, None), ("name", t("new.name"), m.name, None),
                   ("los", t("new.los"), None, None)]
        return rows

    def _kind(self, row: int) -> str:
        """Kind of the row with the given index."""
        count = self.model.count
        if row == 0:
            return "count"
        if row <= count:
            return "game"
        return ("preset", "name", "los")[row - count - 1]

    def raw(self, ev) -> None:
        """Handles Escape."""
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if self.keyboard is not None:
                self.keyboard = None
            else:
                self._back()

    def event(self, e) -> None:
        """Handles a key."""
        if not isinstance(e, KeysEvent) or not e.pressed:
            return
        if self.keyboard is not None:
            result = self.keyboard.event(e.key)
            if result == "done" and self.keyboard_for is not None:
                text = self.keyboard.text.strip()
                if text:
                    self.model.names[self.keyboard_for] = text
                else:
                    self.model.names.pop(self.keyboard_for, None)
            elif result == "done":
                self.model.own_name = self.keyboard.text.strip() or None
            if result is not None:
                self.keyboard = None
            return
        if not self.model.roms:
            if e.key in BACK_KEYS:
                self._back()
            return
        count_rows = len(self.rows())
        kind = self._kind(self.row)
        if e.key in BACK_KEYS:
            self._back()
        elif e.key == Key.UP:
            self.row = (self.row - 1) % count_rows
        elif e.key == Key.DOWN:
            self.row = (self.row + 1) % count_rows
        elif e.key in (Key.LEFT, Key.RIGHT):
            delta = -1 if e.key == Key.LEFT else 1
            if kind == "count":
                self.model.count_change(delta)
            elif kind == "game":
                self.model.game_change(self.row, delta)
            elif kind == "preset":
                self.model.preset_change(delta)
        elif e.key in CONFIRM or e.key == Key.START:
            if kind == "name" and e.key != Key.START:
                self.keyboard, self.keyboard_for = VirtualKeyboard(self.model.own_name or "", MAX_NAME), None
            elif kind == "game" and e.key != Key.START:
                self.keyboard = VirtualKeyboard(self.model.names.get(self.row, ""), MAX_PLAYER_NAME)
                self.keyboard_for = self.row
            elif kind == "los" or e.key == Key.START:
                from .randomize import RandomizeScreen

                self.app.switch(RandomizeScreen(self.app, self.model))

    def _back(self) -> None:
        """Returns to the start screen."""
        from .start import StartScreen

        self.app.switch(StartScreen(self.app))

    def update(self, dt: float) -> None:
        """Advances the animation time."""
        self.time += dt

    def draw(self, area) -> None:
        """Draws the form."""
        def g(n):
            """Scales a base size to the screen."""
            return graphics.size(area, n)

        graphics.title(area, t("new.title"), t("new.subtitle"))
        if not self.model.roms:
            rect = pygame.Rect(g(200), g(260), area.get_width() - g(400), g(220))
            graphics.panel(area, rect, opaque=False)
            graphics.text(area, t("new.no_roms"), (rect.x + g(40), rect.y + g(60)), g(36),
                        graphics.ERROR, "midleft")
            for i, dir in enumerate((self.app.rom_dir, self.app.rom_dir_nds)):
                graphics.text(area, graphics.shorten(str(dir), g(28), rect.width - g(80), "Medium"),
                            (rect.x + g(40), rect.y + g(122) + i * g(46)), g(28), graphics.TEXT, "midleft",
                            weight="Medium")
            graphics.footer(area, [("B", t("hint.back"))])
            return

        x, width, height, step, y = g(200), g(1100), g(72), g(88), g(230)
        pixel, value_pixel = g(32), g(30)
        ambiguous = {r.game for r in self.model.roms if sum(o.game == r.game for o in self.model.roms) > 1}
        for i, (kind, label, value, nr) in enumerate(self.rows()):
            chosen = i == self.row
            if kind == "los":
                y += g(20) - step + height
                rect = pygame.Rect(x, y, width, g(78))
                graphics.outlined(area, rect, label, g(34), chosen)
                rows_bottom = rect.bottom
                continue
            rect = pygame.Rect(x, y, width, height)
            graphics.card(area, rect, chosen)
            color = (255, 255, 255) if chosen else graphics.TEXT
            left = rect.x + g(32)
            if nr:
                left = graphics.badge(area, (left, rect.centery), nr, g(22), inverted=chosen).right + g(20)
            graphics.text(area, label, (left, rect.centery + 2), pixel, color, "midleft")
            if chosen and kind in ("count", "game", "preset"):
                value = f"‹  {value}  ›"
            value_rect = graphics.text(area, graphics.shorten(value, value_pixel, width // 2, "Medium"),
                                    (rect.right - g(32), rect.centery + 2), value_pixel,
                                    (255, 255, 255) if chosen else graphics.DIMMED, "midright", weight="Medium")
            if kind == "game" and value and self.model.player_roms()[nr - 1].game in ambiguous:
                file = self.model.player_roms()[nr - 1].file.stem
                graphics.text(area, graphics.shorten(file, g(22), width // 3, "Medium"),
                            (value_rect.left - g(20), rect.centery + 2), g(22),
                            (230, 230, 255) if chosen else graphics.DIMMED, "midright", weight="Medium",
                            alpha=200)
            y += step
        self._draw_preview(area, pygame.Rect(x + width + g(80), g(230), g(320), rows_bottom - g(230)))
        if self.keyboard is not None:
            self._draw_keyboard(area, g)
        else:
            graphics.footer(area, [("A", t("new.edit_los")), ("<>", t("hint.change")),
                                       ("B", t("hint.back"))])

    def _draw_keyboard(self, area, g) -> None:
        """Player or session name through the on-screen keyboard; empty means the suggested name."""
        graphics.dim(area, area.get_rect(), 150)
        u = g(44)
        width = min(area.get_width() - g(120), g(1000))
        height = g(110) + round(u * 1.4) + VirtualKeyboard.height(u) + g(80)
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (area.get_width() // 2, (area.get_height() - g(80)) // 2)
        graphics.panel(area, rect)
        inside = rect.inflate(-g(80), -g(70))
        nr = self.keyboard_for
        if nr is None:
            title = t("new.name")
            suggestion = default_name(self.model.today, [r.game for r in self.model.player_roms()])
            left = inside.x
        else:
            title = t("new.player_name")
            suggestion = t("new.player_nr", nr=nr)
            left = graphics.badge(area, (inside.x, inside.y + g(18)), nr, g(22)).right + g(20)
        graphics.text(area, title, (left, inside.y + g(18)), g(38), graphics.TEXT, "midleft", weight="Bold")
        field = pygame.Rect(inside.x, inside.y + g(60), inside.width, round(u * 1.4))
        draw_field(area, field, u, self.keyboard.text, True, self.time, placeholder=suggestion)
        self.keyboard.draw(area, pygame.Rect(inside.x, field.bottom + g(30), inside.width,
                                                    inside.bottom - field.bottom - g(30)), u)
        graphics.footer(area, hints())

    def _draw_preview(self, area, rect) -> None:
        """Mini screen with the later layout in the player colors."""
        if rect.right > area.get_width():
            return
        margin = graphics.size(area, 24)
        inside = rect.width - 2 * margin
        rect.height = (graphics.size(area, 76) + inside * 9 // 16 + graphics.size(area, 16)
                       + len(self.model.player_roms()) * graphics.size(area, 40) + margin)
        graphics.card(area, rect, radius=graphics.size(area, 26))
        graphics.text(area, t("new.preview"), (rect.x + margin, rect.y + graphics.size(area, 40)), graphics.size(area, 26),
                    graphics.DIMMED, "midleft")
        width = rect.width - 2 * margin
        image = pygame.Rect(rect.x + margin, rect.y + graphics.size(area, 76), width, width * 9 // 16)
        area.blit(graphics.rounded_rect(image.size, graphics.size(area, 10), (0, 0, 0, 120)), image)
        roms = self.model.player_roms()
        if self.model.system == "nds":
            cells = layout.compute_ds(len(roms), image.width, image.height, self.app.settings.ds_view)
            fields = [(nr, [z.large, z.small]) for nr, z in enumerate(cells[:len(roms)], start=1)]
        else:
            fields = [(nr, [z.game]) for nr, z in enumerate(layout.compute(len(roms), image.width, image.height)[:len(roms)],
                                                             start=1)]
        for nr, rects in fields:
            color = graphics.player_color(nr)
            for j, z in enumerate(rects):
                r = pygame.Rect(image.x + z.x, image.y + z.y, z.w, z.h).inflate(-2, -2)
                area.blit(graphics.rounded_rect(r.size, graphics.size(area, 6), (*color, 90 if j == 0 else 60), 2,
                                             (*color, 255)), r)
                if j == 0:
                    graphics.text(area, f"P{nr}", r.center, graphics.size(area, 20), (255, 255, 255), "center",
                                weight="Bold")
        y = image.bottom + graphics.size(area, 36)
        for nr, rom in enumerate(roms, start=1):
            graphics.badge(area, (image.x, y), nr, graphics.size(area, 16))
            graphics.text(area, graphics.shorten(with_name(rom.game, self.model.names.get(nr)), graphics.size(area, 22),
                                                width - graphics.size(area, 52), "Medium"),
                        (image.x + graphics.size(area, 52), y + 1), graphics.size(area, 22),
                        graphics.TEXT, "midleft", weight="Medium")
            y += graphics.size(area, 40)
