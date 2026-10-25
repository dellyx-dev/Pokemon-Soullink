"""Overlay tab "Opponent": the opponent in a running battle (from RAM) or one or two types entered by hand. During a battle
the opposing Pokemon is shown with the effect of all attack types."""
from __future__ import annotations

from typing import NamedTuple

import pygame

from soullink import types
from soullink.dex import type_name
from soullink.input.keys import Key
from soullink.plugin.api import Tab
from soullink.language import t
from soullink.ui import graphics
from soullink.ui.types_overlay import DARKER_TEXT, LEVELS, chip_size, draw_type

LEVELS_TEXT = {4: "level_4", 2: "level_2", 0.5: "level_05", 0.25: "level_025", 0: "level_0"}
ORDER = (4, 2, 0.5, 0.25, 0)
OMIT = (0.25, 0.5)


class Metrics(NamedTuple):
    """Layout metrics: chip width, height, font and abbreviation, whether labels ("super effective", headings) have room,
    and whether the effects are stacked (1 column) or in two columns (2)."""
    chip_w: int
    chip_h: int
    chip_font: int
    short: bool
    text: bool
    header: bool
    columns: int = 1


def _card_width(pixel: int, short: bool, margin: int, at_most: int) -> int:
    """Width of a card: as wide as the longest type name plus margin, at most at_most."""
    names = (types.short(type_) if short else types.display(type_) for type_ in types.TYPES)
    return min(max(graphics.load_font(pixel, "Bold").size(n)[0] for n in names) + margin, at_most)


def metric_levels(u: int, width: int) -> list[Metrics]:
    """From large to compact: effects stacked with spelled-out types (with labels, without, smaller chips), only then
    abbreviations and very last two columns."""
    chip_w, chip_h, chip_font = chip_size(u, width)
    levels = [Metrics(chip_w, chip_h, chip_font, False, True, True), Metrics(chip_w, chip_h, chip_font, False, False, True),
              Metrics(chip_w, chip_h, chip_font, False, False, False)]
    for factor in (0.85, 0.72, 0.62):
        p = max(8, round(chip_font * factor))
        levels.append(Metrics(_card_width(p, False, max(6, u // 4), width // 3), round(chip_h * factor), p, False,
                            False, False))
    kp = max(8, round(chip_font * 0.72))
    short = Metrics(_card_width(kp, True, max(4, u // 4), width // 4), round(chip_h * 0.72), kp, True, False, False)
    return levels + [short, short._replace(columns=2)]


class OpponentTab(Tab):
    """Overlay tab showing the opponent of the running battle; the plugin sets `battle` with every RAM dump
    (battle.read_battle_ram: opposing teams or None)."""
    id, position, ram_interval = "opponent", 20, 1.5

    def __init__(self, api, nr: int):
        """Creates the tab for a player; api is the GameApi for texts and the player's ROM data."""
        self.api = api
        self.nr = nr
        self.type1 = 0
        self.type2 = -1
        self.focus = 0
        self.battle = None

    def title(self, short: bool = False) -> str:
        """Tab title, abbreviated if short."""
        return self.api.t("tab_short") if short else self.api.t("tab")

    @property
    def defender(self) -> list[str]:
        """The defending types: the chosen ones, entered by hand."""
        chosen = [types.TYPES[self.type1]] + ([types.TYPES[self.type2]] if self.type2 >= 0 else [])
        return list(dict.fromkeys(chosen))

    def active_opponent(self) -> list:
        """The opponents fighting right now (from the battle data); without that information the first Pokemon with HP per
        team (the last at the end of the battle), at most two (double battle)."""
        active = []
        for team in self.battle or []:
            in_battle = [g for g in team if g.active]
            if in_battle:
                active.extend(in_battle)
            elif team:
                active.append(next((g for g in team if g.kp > 0), team[-1]))
        return active[:2]

    def _dex(self):
        """Dex of the player's own ROM (names and types of the opponents), only requested while a battle is running."""
        return self.api.dex(self.nr) if self.active_opponent() else None

    def _in_battle(self) -> bool:
        """True if a battle is running and the ROM data is loaded."""
        return self._dex() is not None

    def event(self, key: Key) -> bool:
        """Handles a key."""
        if self._in_battle():
            return False
        count = len(types.TYPES)
        step = {Key.RIGHT: 1, Key.LEFT: -1}.get(key, 0)
        if key in (Key.UP, Key.DOWN):
            self.focus = 1 - self.focus
        elif step and self.focus == 0:
            self.type1 = (self.type1 + step) % count
        elif step:
            self.type2 = (self.type2 + 1 + step) % (count + 1) - 1
        else:
            return False
        return True

    def hints(self) -> list[tuple[str, str]]:
        """Button hints for the current state."""
        if self._in_battle():
            return [("L/R", t("hint.page")), ("B", t("hint.close"))]
        return [("<>", self.api.t("type")), ("^", self.api.t("first_second")), ("L/R", t("hint.page")),
                ("B", t("hint.close"))]

    def draw(self, area, rect: pygame.Rect, u: int, time: float = 0.0) -> None:
        """Draws the tab."""
        opponent = self.active_opponent()
        dex = self._dex()
        if opponent and dex is not None:
            self._draw_battle(area, rect, u, opponent, dex)
        else:
            self._draw_manual(area, rect, u, time, bool(opponent))

    def _draw_selection(self, area, rect: pygame.Rect, u: int, title: str, selection: list[str | None],
                         focus: int) -> int:
        """Row "Types by hand: [type] [type]"; returns the bottom edge."""
        chip_w, chip_h, chip_font = chip_size(u, rect.width)
        chip_w = round(chip_w * 1.25)
        r = graphics.text(area, title, (rect.x, rect.y + chip_h // 2), max(10, round(u * 0.62)), graphics.DIMMED,
                        "midleft", weight="SemiBold")
        x = r.right + u // 2
        for i, type_ in enumerate(selection):
            chip = pygame.Rect(x + u // 2, rect.y, chip_w, chip_h)
            if type_ is None:
                area.blit(graphics.rounded_rect(chip.size, chip_h // 3, (255, 255, 255, 18), 2, (255, 255, 255, 60)), chip)
                graphics.text(area, "—", chip.center, chip_font, graphics.DIMMED, "center", weight="Bold")
            else:
                draw_type(area, type_, chip, round(chip_font * 1.1))
            if i == focus:
                pygame.draw.rect(area, (255, 255, 255), chip.inflate(6, 6), 2, border_radius=chip_h // 3 + 3)
                graphics.text(area, "‹", (chip.left - 4, chip.centery), round(u * 0.9), (255, 255, 255), "midright")
                graphics.text(area, "›", (chip.right + 4, chip.centery), round(u * 0.9), (255, 255, 255), "midleft")
            x = chip.right + u
        return rect.y + chip_h

    @staticmethod
    def _card(area, list_: list[str], x0: int, y0: int, per_row: int, m: Metrics, gap: int,
                   bottom: int) -> None:
        """Type chips in a grid from (x0, y0); chips that would reach below `bottom` are left out."""
        for i, type_ in enumerate(list_):
            row, column = divmod(i, per_row)
            chip = pygame.Rect(x0 + column * (m.chip_w + gap), y0 + row * (m.chip_h + gap), m.chip_w, m.chip_h)
            if chip.bottom <= bottom:
                draw_type(area, type_, chip, m.chip_font, short=m.short)

    def _groups(self, area, rect: pygame.Rect, u: int, groups: dict, m: Metrics, away=(),
                 draw: bool = True) -> int:
        """One row per effect: badge (4x, 2x ...), with room the types wrapped; in two columns (emergency) 4x/2x on the
        left and 1/2x/1/4x/0x on the right."""
        if m.columns == 2:
            half, a = (rect.width - u) // 2, m._replace(columns=1)
            strong = {value: list_ for value, list_ in groups.items() if value > 1}
            weak = {value: list_ for value, list_ in groups.items() if value < 1}
            return max(self._groups(area, pygame.Rect(rect.x, rect.y, half, rect.height), u, strong, a, away,
                                     draw),
                       self._groups(area, pygame.Rect(rect.x + half + u, rect.y, half, rect.height), u, weak,
                                     a, away, draw))
        gap = max(3, m.chip_h // 5)
        badge_rect_w = round(m.chip_h * 1.7)
        pixel = max(9, round(u * 0.5))
        label = {value: self.api.t(key) for value, key in LEVELS_TEXT.items()}
        x0 = rect.x + badge_rect_w + 2 * gap
        text_b = max(graphics.load_font(pixel, "SemiBold").size(b)[0] for b in label.values()) + 2 * gap \
            if m.text else 0
        if text_b and (rect.right - x0 - text_b + gap) // (m.chip_w + gap) < 3:
            text_b = 0
        per_row = max(1, (rect.right - x0 - text_b + gap) // (m.chip_w + gap))
        y = rect.y
        for value in ORDER:
            list_ = groups.get(value)
            if not list_ or value in away:
                continue
            if y > rect.y:
                y += round(gap * 1.6)
            if draw and y + m.chip_h <= rect.bottom:
                color, badge = LEVELS[value]
                badge_rect = pygame.Rect(rect.x, y, badge_rect_w, m.chip_h)
                area.blit(graphics.rounded_rect(badge_rect.size, m.chip_h // 3, (*color, 255)), badge_rect)
                graphics.text(area, badge, badge_rect.center, max(9, round(m.chip_h * 0.53)), DARKER_TEXT, "center",
                            weight="ExtraBold")
                if text_b:
                    graphics.text(area, label[value], (x0, y + m.chip_h // 2), pixel, color, "midleft",
                                weight="SemiBold")
                self._card(area, list_, x0 + text_b, y, per_row, m, gap, rect.bottom)
            rows = -(-len(list_) // per_row)
            y += rows * m.chip_h + (rows - 1) * gap
        return y - rect.y

    def _not_send(self, area, rect: pygame.Rect, u: int, list_: list[str], name: str, m: Metrics,
                        draw: bool = True) -> int:
        """Red-bordered box "Do not send": the types the opponent hits super effectively; with room a heading with the
        reason above the chips."""
        if not list_:
            return 0
        margin, gap = max(4, m.chip_h // 4), max(3, m.chip_h // 5)
        pixel = max(9, round(u * 0.6)) if m.header else max(8, round(m.chip_h * 0.5))
        header = self.api.t("not_send")
        header_b, header_h = graphics.load_font(pixel, "Bold").size(header)
        x0, y0 = rect.x + margin, rect.y + margin
        if m.header:
            y0 += header_h + gap
        else:
            x0 += header_b + 2 * gap
        per_row = max(1, (rect.right - margin - x0 + gap) // (m.chip_w + gap))
        rows = -(-len(list_) // per_row)
        height = y0 - rect.y + rows * m.chip_h + (rows - 1) * gap + margin
        if draw:
            box = pygame.Rect(rect.x, rect.y, rect.width, height)
            area.blit(graphics.rounded_rect(box.size, max(6, m.chip_h // 2), (*graphics.ERROR, 40), 2,
                                         (*graphics.ERROR, 210)), box)
            middle = box.y + margin + (header_h // 2 if m.header else m.chip_h // 2)
            r = graphics.text(area, header, (box.x + margin, middle), pixel, graphics.ERROR, "midleft", weight="Bold")
            reason, small = self.api.t("not_send_reason", name=name), max(8, round(u * 0.45))
            if m.header and graphics.load_font(small, "Medium").size(reason)[0] <= box.right - margin - r.right - u // 2:
                graphics.text(area, reason, (r.right + u // 2, r.centery + 1), small, graphics.DIMMED, "midleft",
                            weight="Medium")
            self._card(area, list_, x0, y0, per_row, m, gap, box.bottom)
        return height

    def _matching_metrics(self, u: int, width: int, height: int, send: list[str], groups: dict,
                        name: str = "") -> tuple[Metrics, tuple]:
        """(metrics, omitted effects): the first level at which "Do not send", heading and effects fit into the height (two
        columns only if three chips fit side by side)."""
        levels = self._levels(u, width)
        for m in levels:
            if self._need(u, width, send, groups, name, m) <= height:
                return m, ()
        m, away = levels[-1], ()
        for value in OMIT:
            away += (value,)
            if self._need(u, width, send, groups, name, m, away) <= height:
                break
        return m, away

    @staticmethod
    def _levels(u: int, width: int) -> list[Metrics]:
        """The metric levels without two columns in which no three chips fit side by side."""
        def possible(m: Metrics) -> bool:
            """True if the level is usable at the width."""
            gap = max(3, m.chip_h // 5)
            half = (width - u) // 2 - round(m.chip_h * 1.7) - 2 * gap
            return m.columns == 1 or (half + gap) // (m.chip_w + gap) >= 3

        return [m for m in metric_levels(u, width) if possible(m)]

    def _need(self, u: int, width: int, send: list[str], groups: dict, name: str, m: Metrics, away=()) -> int:
        """Height of "Do not send", heading and effects in the given metrics."""
        mass = pygame.Rect(0, 0, width, 0)
        box = self._not_send(None, mass, u, send, name, m, draw=False)
        return (box + u // 3 if box else 0) + (round(u * 1.1) if m.header else 0) + \
            self._groups(None, mass, u, groups, m, away, draw=False)

    def _effect(self, area, rect: pygame.Rect, u: int, defender: list[str], send: list[str],
                 name: str = "", choice: tuple | None = None) -> None:
        """Below the opponent: "Do not send" and the effects of all attack types on the defender, with the metrics and
        omissions that fit the rect."""
        groups = types.defense(defender)
        m, away = choice or self._matching_metrics(u, rect.width, rect.height, send, groups, name)
        y = rect.y
        box = self._not_send(area, pygame.Rect(rect.x, y, rect.width, 0), u, send, name, m)
        if box:
            y += box + u // 3
        if m.header:
            graphics.text(area, self.api.t("attacken_are"), (rect.x, y), max(9, round(u * 0.5)), graphics.DIMMED,
                        "topleft", weight="Medium")
            y += round(u * 1.1)
        self._groups(area, pygame.Rect(rect.x, y, rect.width, rect.bottom - y), u, groups, m, away)

    def _draw_battle(self, area, rect: pygame.Rect, u: int, opponent: list, dex) -> None:
        """Draws the opposing Pokemon side by side: name, level, types and below them the effect of attacks."""
        width = (rect.width - u * (len(opponent) - 1)) // len(opponent)
        columns = []
        for i, g in enumerate(opponent):
            pokemon = dex.pokemon_after_nr.get(g.kind)
            name = dex.name(g.kind).replace(chr(0x2642), " (m)").replace(chr(0x2640), " (w)")
            extra = self.api.t("lv", level=g.level) + ("" if g.kp else f"  ·  {self.api.t('defeated')}")
            defender = list(g.types) or [z for z in dict.fromkeys(type_name(x) for x in (pokemon.types if pokemon
                                                                                              else []) if x)
                                            if z in types.COLORS]
            columns.append((pygame.Rect(rect.x + i * (width + u), rect.y, width, rect.height), name, extra,
                            graphics.TEXT if g.kp else graphics.DIMMED, defender))
        levels = self._levels(u, width)
        header = 2 * chip_size(u, width)[1] + round(u * 0.7)
        choices = [self._matching_metrics(u, width, s.height - header, types.strong_against(v), types.defense(v), n)
                  for s, n, _, _, v in columns if v]
        choice = max(choices, key=lambda w: (levels.index(w[0]), len(w[1])), default=None)
        a_row = None
        if choice is not None and not choice[0].header:
            for m in levels[:levels.index(choice[0])]:
                heights = [self._header(None, s, u, n, z, f, v, m, draw=False) for s, n, z, f, v in columns]
                if m.header or m.short or None in heights:
                    continue
                if all(self._need(u, width, types.strong_against(v), types.defense(v), n, m) <= s.height - h
                       for (s, n, _, _, v), h in zip(columns, heights) if v):
                    choice, a_row = (m, ()), m
                    break
        for column, name, extra, color, defender in columns:
            top = column.y + self._header(area, column, u, name, extra, color, defender, a_row)
            if defender:
                self._effect(area, pygame.Rect(column.x, top, column.width, column.bottom - top), u,
                              defender, types.strong_against(defender), name, choice)

    @staticmethod
    def _header(area, column: pygame.Rect, u: int, name: str, extra: str, color, defender: list[str],
              m: Metrics | None = None, draw: bool = True) -> int | None:
        """Name, level and types with the chips of the level m; returns the height, None if not drawn."""
        chip_w, chip_h, chip_font = chip_size(u, column.width)
        large, small = round(u * 0.75), max(9, round(u * 0.5))
        name = graphics.shorten(name, large, column.width * 2 // 3, "Bold")
        if m is None:
            row, height, gap = chip_h, 2 * chip_h + round(u * 0.7), u // 3
            x, y, kb, kh, kp = column.x, column.y + chip_h + u // 3, chip_w, chip_h, round(chip_font * 1.1)
        else:
            row, gap = max(m.chip_h, round(u * 0.9)), max(3, m.chip_h // 5)
            x = column.x + graphics.load_font(large, "Bold").size(name)[0] + graphics.load_font(small, "Medium").size(extra)[0] \
                + u
            if x + len(defender) * (m.chip_w + gap) - gap > column.right:
                return None
            height, y, kb, kh, kp = row + round(u * 0.5), column.y + (row - m.chip_h) // 2, m.chip_w, m.chip_h, m.chip_font
        if draw:
            r = graphics.text(area, name, (column.x, column.y + row // 2), large, color, "midleft", weight="Bold")
            graphics.text(area, extra, (r.right + u // 2, r.centery + 1), small, graphics.DIMMED, "midleft",
                        weight="Medium")
            for type_ in defender:
                draw_type(area, type_, pygame.Rect(x, y, kb, kh), kp)
                x += kb + gap
        return height

    def _draw_manual(self, area, rect: pygame.Rect, u: int, time: float, in_battle: bool) -> None:
        """Header line ("no battle" or "battle running, loading") and the type selection by hand."""
        header, x, middle = self.api.t("no_battle"), rect.x, rect.y + round(u * 0.4)
        if in_battle:
            error = self.api.dex_error(self.nr)
            if error:
                header = self.api.t("battle_error", error=error)
            else:
                header = self.api.t("battle_loads")
                radius = max(6, u // 3)
                graphics.spinner(area, (x + radius, middle), radius, time)
                x += 2 * radius + u // 3
        pixel = max(10, round(u * 0.62))
        graphics.text(area, graphics.shorten(header, pixel, rect.right - x, "Bold"), (x, middle), pixel, graphics.TEXT,
                    "midleft", weight="Bold")
        rect = pygame.Rect(rect.x, rect.y + round(u * 1.3), rect.width, rect.height - round(u * 1.3))
        type2 = types.TYPES[self.type2] if self.type2 >= 0 else None
        bottom = self._draw_selection(area, rect, u, self.api.t("of_hand"), [types.TYPES[self.type1], type2],
                                      self.focus)
        self._effect(area, pygame.Rect(rect.x, bottom + u, rect.width, rect.bottom - bottom - u), u, self.defender,
                      [])
