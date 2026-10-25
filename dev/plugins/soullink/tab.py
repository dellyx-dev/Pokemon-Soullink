"""Overlay tabs "Soullink" and "Level" and the display "Soullink list" for the free field. Soullink shows one row per catch
location with the catches of all players."""
from __future__ import annotations

import pygame

from soullink.input.keys import CONFIRM, BACK_KEYS, Key
from soullink.plugin.api import Display, Tab
from soullink.language import t
from soullink.ui import graphics
from soullink.ui.pokemon_components import displayable, hint, list_draw, pokemon_types, draw_details
from soullink.ui.keyboard import Search
from soullink.ui.types_overlay import draw_type

from .level import Battle, battles
from .link_list import natural

DEAD_COLOR = graphics.ERROR
DEAD_TEXT = (110, 112, 135)
MISSED = "× "
DISPLAY_PAUSE = 3.0
DISPLAY_TEMPO = 0.7


def nickname(catch, dex) -> str:
    """Only a real nickname: generation 3 otherwise stores the species name in capitals."""
    name = (catch.nickname or "").strip()
    kind = dex.name(catch.kind) if dex is not None else ""
    return "" if not name or name.casefold() == kind.casefold() else name


def _dead_mark(area, rect: pygame.Rect) -> None:
    """Dead row: grey veil with fine diagonal hatching."""
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    layer.fill((20, 20, 30, 110))
    gap = max(6, rect.height // 4)
    for x in range(-rect.height, rect.width, gap):
        pygame.draw.line(layer, (200, 200, 220, 45), (x, rect.height), (x + rect.height, 0), 2)
    area.blit(layer, rect)


def pendulum(time: float, away: int, tempo: float, pause: float = DISPLAY_PAUSE) -> int:
    """Offset in pixels for automatic scrolling up and down: wait at the top, scroll down, wait at the bottom, scroll up."""
    if away <= 0 or tempo <= 0:
        return 0
    ride = away / tempo
    p = time % (2 * (pause + ride))
    if p < pause:
        return 0
    if p < pause + ride:
        return round((p - pause) * tempo)
    if p < 2 * pause + ride:
        return away
    return round(away - (p - 2 * pause - ride) * tempo)


class SoullinkTab(Tab):
    """Overlay tab listing the locations with catches, dead marks and the dialogs to enter missed encounters."""
    id, position = "soullink", 10
    ram_interval = 5.0

    def __init__(self, api, data, nr: int):
        """Creates the tab for a player."""
        self.api = api
        self.data = data
        self.nr = nr
        self.selection = 0
        self.open_ = False
        self.column = nr
        self.scroll = 0
        self._rows = []
        self.location_choice = False
        self.location_selection = 0
        self.location_search = Search()
        self.poke_choice: tuple[int, int] | None = None
        self.poke_search = Search()
        self.poke_selection = 0
        self.of_location_choice = False

    def title(self, short: bool = False) -> str:
        """Tab title, abbreviated if short."""
        return self.api.t("tab_short") if short else self.api.t("tab")

    def keyboard_close(self) -> None:
        """The overlay closes: closes the on-screen keyboards (the search term stays)."""
        self.location_search.close()
        self.poke_search.close()

    def _current_rows(self):
        """Refreshes the cached rows from the data."""
        self._rows = self.data.rows()
        self.selection = min(self.selection, max(0, len(self._rows) - 1))
        return self._rows

    def event(self, key: Key) -> bool:
        """Handles a key in the list or in one of the choice dialogs."""
        if self.location_choice:
            return self._location_choice_event(key)
        if self.poke_choice is not None:
            return self._poke_event(key)
        rows = self._current_rows()
        if not self.open_:
            if key == Key.WEST:
                self.location_choice, self.location_selection, self.location_search = True, 0, Search()
                return True
            if not rows:
                return False
            if key in (Key.UP, Key.DOWN):
                self.selection = (self.selection + (1 if key == Key.DOWN else -1)) % len(rows)
                return True
            if key in CONFIRM or key == Key.START:
                self.open_, self.scroll = True, 0
                present = sorted(rows[self.selection].catches)
                self.column = self.nr if self.nr in present or not present else present[0]
                return True
            return False
        row = rows[self.selection] if rows else None
        if row is None or key in BACK_KEYS:
            self.open_ = False
            return True
        if key in (Key.LEFT, Key.RIGHT):
            player = self.data.player
            i = player.index(self.column) if self.column in player else 0
            self.column = player[(i + (1 if key == Key.RIGHT else -1)) % len(player)]
            self.scroll = 0
        elif key in (Key.UP, Key.DOWN):
            self.scroll = max(0, self.scroll + (2 if key == Key.DOWN else -2))
        elif key == Key.WEST and self.column not in row.catches:
            self.poke_choice, self.poke_search, self.poke_selection = (row.location, self.column), Search(), 0
            self.of_location_choice = False
        elif key in CONFIRM or key == Key.START:
            self.data.toggle(row.location)
            if all(z.location != row.location for z in self._current_rows()):
                self.open_ = False
        return True

    def _free_locations(self) -> list[tuple[int, str]]:
        """Locations without an entry of this player, A-Z, filtered by the search term."""
        locations = [o for o in self.data.free_locations(self.nr) if self.location_search.fits(o[1])]
        return sorted(locations, key=lambda o: (self.location_search.rank(o[1]), natural(o[1]), o[0]))

    def _location_choice_event(self, key: Key) -> bool:
        """Handles a key while choosing a location."""
        if self.location_search.is_open:
            before = self.location_search.text
            self.location_search.event(key)
            if self.location_search.text != before:
                self.location_selection = 0
            return True
        locations = self._free_locations()
        if key == Key.NORTH:
            self.location_search.open()
        elif key in BACK_KEYS and self.location_search.active:
            self.location_search.clear()
            self.location_selection = 0
        elif key in BACK_KEYS:
            self.location_choice = False
        elif locations and key in (Key.UP, Key.DOWN):
            self.location_selection = (self.location_selection + (1 if key == Key.DOWN else -1)) % len(locations)
        elif locations and key in (Key.LEFT, Key.RIGHT):
            self.location_selection = max(0, min(len(locations) - 1, self.location_selection + (10 if key == Key.RIGHT else -10)))
        elif locations and (key in CONFIRM or key == Key.START):
            location = locations[min(self.location_selection, len(locations) - 1)][0]
            self.poke_choice, self.poke_search, self.poke_selection = (location, self.nr), Search(), 0
            self.location_choice, self.of_location_choice = False, True
        return True

    def _poke_list(self) -> list:
        """All Pokemon of the player's ROM, A-Z, filtered by the search term, with "remove entry" (None) first."""
        location, nr = self.poke_choice
        dex = self.data.dex(nr)
        list_ = sorted((p for p in (dex.pokemon if dex else []) if p is not None and p.nr > 0
                        and self.poke_search.fits(p.name)),
                       key=lambda p: (self.poke_search.rank(p.name), natural(p.name), p.nr))
        row = next((z for z in self.data.rows() if z.location == location), None)
        if row is not None and nr in row.missed and not self.poke_search.active:
            list_.insert(0, None)
        return list_

    def _poke_event(self, key: Key) -> bool:
        """Handles a key while choosing a Pokemon."""
        if self.poke_search.is_open:
            before = self.poke_search.text
            self.poke_search.event(key)
            if self.poke_search.text != before:
                self.poke_selection = 0
            return True
        list_ = self._poke_list()
        if key == Key.NORTH:
            self.poke_search.open()
        elif key in BACK_KEYS and self.poke_search.active:
            self.poke_search.clear()
            self.poke_selection = 0
        elif key in BACK_KEYS:
            self.poke_choice, self.location_choice = None, self.of_location_choice
        elif list_ and key in (Key.UP, Key.DOWN):
            self.poke_selection = (self.poke_selection + (1 if key == Key.DOWN else -1)) % len(list_)
        elif list_ and key in (Key.LEFT, Key.RIGHT):
            self.poke_selection = max(0, min(len(list_) - 1, self.poke_selection + (10 if key == Key.RIGHT else -10)))
        elif list_ and (key in CONFIRM or key == Key.START):
            location, nr = self.poke_choice
            chosen = list_[min(self.poke_selection, len(list_) - 1)]
            self.data.encounter_set(location, nr, chosen.nr if chosen is not None else None)
            self.poke_choice, self.of_location_choice = None, False
            rows = self._current_rows()
            if all(z.location != location for z in rows):
                self.open_ = False
            else:
                self.selection = next(i for i, z in enumerate(rows) if z.location == location)
        return True

    def _draw_poke_choice(self, area, rect: pygame.Rect, u: int, time: float) -> None:
        """Draws the Pokemon choice."""
        location, nr = self.poke_choice
        list_rect = rect
        if not self.poke_search.is_open:
            badge_rect = graphics.badge(area, (rect.x, rect.y + u // 2), nr, max(9, round(u * 0.6)))
            title = self.api.t("encounter_title", location=self.data.location_name(location))
            graphics.text(area, graphics.shorten(title, max(10, round(u * 0.62)), rect.right - badge_rect.right - u // 2, "Bold"),
                        (badge_rect.right + u // 3, badge_rect.centery + 1), max(10, round(u * 0.62)), graphics.TEXT, "midleft",
                        weight="Bold")
            list_rect = pygame.Rect(rect.x, badge_rect.bottom + u // 2, rect.width, rect.bottom - badge_rect.bottom - u // 2)
        dex = self.data.dex(nr)
        if dex is None:
            hint(area, list_rect, u, [t("dex.loads")], loads=True, time=time)
            return
        list_ = self._poke_list()
        list_rect = self.poke_search.draw(area, list_rect, u, time, sum(p is not None for p in list_))
        if not list_:
            hint(area, list_rect, u, [t("osk.no_hit")])
            return
        self.poke_selection = min(self.poke_selection, len(list_) - 1)
        pixel = max(9, round(u * 0.58))
        cb, ch = round(u * 3.0), round(u * 0.95)

        def row_draw(i, row_rect, chosen):
            """Draws one row of the Pokemon choice."""
            p = list_[i]
            color = (255, 255, 255) if chosen else graphics.TEXT
            if p is None:
                graphics.text(area, self.api.t("entry_remove"), (row_rect.x + u // 2, row_rect.centery + 1), pixel,
                            color if chosen else graphics.ERROR, "midleft", weight="SemiBold")
                return
            graphics.text(area, f"#{p.nr:03d}", (row_rect.x + u // 2, row_rect.centery + 1), pixel,
                        (235, 235, 255) if chosen else graphics.DIMMED, "midleft", weight="Medium")
            x = row_rect.right - u // 2
            for type_ in reversed(pokemon_types(dex, p)):
                x -= cb
                draw_type(area, type_, pygame.Rect(x, row_rect.centery - ch // 2, cb, ch), max(8, round(u * 0.46)))
                x -= u // 4
            name_x = row_rect.x + u // 2 + round(pixel * 3.2)
            graphics.text(area, graphics.shorten(displayable(p.name), pixel, x - name_x - u // 2, "SemiBold"),
                        (name_x, row_rect.centery + 1), pixel, color, "midleft", weight="SemiBold")

        list_draw(area, list_rect, len(list_), self.poke_selection, round(u * 1.3), row_draw)

    def hints(self) -> list[tuple[str, str]]:
        """Button hints for the current state."""
        if self.poke_choice is not None:
            if self.poke_search.is_open:
                return self.poke_search.hints()
            return [("A", t("hint.select")), ("Y", t("osk.search")), ("<>", t("hint.ten_next")),
                    ("B", t("hint.cancel"))]
        if self.location_choice:
            if self.location_search.is_open:
                return self.location_search.hints()
            return [("A", t("hint.next")), ("Y", t("osk.search")), ("<>", t("hint.ten_next")),
                    ("B", t("hint.cancel"))]
        if self.open_:
            hints = [("<>", self.api.t("pokemon")), ("A", self.api.t("dead_alive")), ("B", t("hint.back"))]
            row = next((z for z in self._rows if z.location == self._open_location()), None)
            if row is not None and self.column not in row.catches:
                hints.insert(2, ("X", self.api.t("encounter")))
            return hints
        return [("A", self.api.t("open")), ("X", self.api.t("encounter")), ("L/R", t("hint.page")),
                ("B", t("hint.close"))]

    def _open_location(self) -> int | None:
        """Location id of the open row; None if no row is open."""
        return self._rows[self.selection].location if self.open_ and self._rows else None

    def draw(self, area, rect: pygame.Rect, u: int, time: float = 0.0) -> None:
        """Draws the tab."""
        if self.location_choice:
            self._draw_location_choice(area, rect, u, time)
            return
        if self.poke_choice is not None:
            self._draw_poke_choice(area, rect, u, time)
            return
        rows = self._current_rows()
        if not rows:
            hint(area, rect, u, [self.api.t("no_catches"), self.api.t("no_catches_2")])
            return
        if self.open_:
            self._draw_open(area, rect, u, rows[self.selection])
        else:
            self._draw_list(area, rect, u, rows)

    def _draw_location_choice(self, area, rect: pygame.Rect, u: int, time: float) -> None:
        """All locations of the game without an entry of this player; A continues to the choice of the Pokemon."""
        list_ = rect
        if not self.location_search.is_open:
            badge_rect = graphics.badge(area, (rect.x, rect.y + u // 2), self.nr, max(9, round(u * 0.6)))
            title = graphics.shorten(self.api.t("location_choose"), max(10, round(u * 0.62)),
                                   rect.right - badge_rect.right - u // 2, "Bold")
            graphics.text(area, title, (badge_rect.right + u // 3, badge_rect.centery + 1), max(10, round(u * 0.62)), graphics.TEXT,
                        "midleft", weight="Bold")
            list_ = pygame.Rect(rect.x, badge_rect.bottom + u // 2, rect.width, rect.bottom - badge_rect.bottom - u // 2)
        locations = self._free_locations()
        list_ = self.location_search.draw(area, list_, u, time, len(locations))
        if not locations:
            if self.location_search.active:
                hint(area, list_, u, [t("osk.no_hit")])
            elif self.data.location_names_there():
                hint(area, list_, u, [self.api.t("all_locations")])
            else:
                error = [f for f in map(self.data.dex_error, self.data.player) if f]
                all_broken = len(error) >= len(self.data.player)
                hint(area, list_, u, [t("dex.missing", error=error[0])] if all_broken else [t("dex.loads")],
                        loads=not all_broken, time=time)
            return
        self.location_selection = min(self.location_selection, len(locations) - 1)
        pixel = max(9, round(u * 0.58))

        def row_draw(i, row_rect, chosen):
            """Draws one row of the location choice."""
            graphics.text(area, graphics.shorten(locations[i][1], pixel, row_rect.width - u, "SemiBold"),
                        (row_rect.x + u // 2, row_rect.centery + 1), pixel, (255, 255, 255) if chosen else graphics.TEXT,
                        "midleft", weight="SemiBold")

        list_draw(area, list_, len(locations), self.location_selection, round(u * 1.3), row_draw)

    def _columns(self, rect: pygame.Rect, u: int) -> tuple[int, int]:
        """Widths of the location column and the player columns."""
        location_width = max(u * 5, rect.width * 3 // 10)
        return location_width, (rect.width - location_width) // max(1, len(self.data.player))

    def draw_display(self, area, rect: pygame.Rect, u: int, time: float) -> None:
        """View only (free screen space): no selection, and with many locations it scrolls up and down."""
        rows = self.data.rows()
        if not rows:
            hint(area, rect, u, [self.api.t("no_catches"), self.api.t("no_catches_2")])
            return
        self._draw_list(area, rect, u, rows, time)

    def _draw_list(self, area, rect: pygame.Rect, u: int, rows, display_time: float | None = None) -> None:
        """Draws the list rows."""
        pixel = max(9, round(u * 0.55))
        location_width, sp_b = self._columns(rect, u)
        header = round(u * 1.2)
        graphics.text(area, self.api.t("catch_location"), (rect.x + u // 2, rect.y + header // 2), pixel, graphics.DIMMED,
                    "midleft", weight="SemiBold")
        for j, nr in enumerate(self.data.player):
            x = rect.x + location_width + j * sp_b
            graphics.badge(area, (x + u // 3, rect.y + header // 2), nr, max(9, round(u * 0.6)))
        list_ = pygame.Rect(rect.x, rect.y + header, rect.width, rect.height - header)
        height = round(u * 1.35)
        offset = bar = None
        if display_time is not None:
            away = len(rows) * height - list_.height
            offset = pendulum(display_time, away, DISPLAY_TEMPO * height)
            if away > 0:
                bar_h = max(u, list_.height * list_.height // (away + list_.height))
                bar = pygame.Rect(list_.right - u // 5, list_.y + (list_.height - bar_h) * offset // away,
                                     max(3, u // 6), bar_h)

        def row_draw(i, row_rect, chosen):
            """Draws one list row."""
            z = rows[i]
            if z.dead:
                color = (205, 205, 220) if chosen else DEAD_TEXT
            else:
                color = (255, 255, 255) if chosen else graphics.TEXT
            x = row_rect.x + u // 2
            graphics.text(area, graphics.shorten(z.name, pixel, rect.x + location_width - x - u // 3, "SemiBold"),
                        (x, row_rect.centery + 1), pixel, color, "midleft", weight="SemiBold")
            for j, nr in enumerate(self.data.player):
                catch = z.catches.get(nr)
                sx = row_rect.x + location_width + j * sp_b
                dex = self.data.dex(nr)
                if catch is None and nr in z.missed:
                    name = MISSED + displayable(dex.name(z.missed[nr]) if dex is not None else f"#{z.missed[nr]}")
                    graphics.text(area, graphics.shorten(name, pixel, sp_b - u // 2, "Medium"),
                                (sx + u // 3, row_rect.centery + 1), pixel,
                                (255, 200, 200) if chosen else (200, 120, 125) if z.dead else graphics.ERROR,
                                "midleft", weight="Medium")
                    continue
                if catch is None:
                    graphics.text(area, "–", (sx + u // 3, row_rect.centery + 1), pixel, graphics.DIMMED, "midleft")
                    continue
                name = displayable(dex.name(catch.kind) if dex is not None else f"#{catch.kind}")
                other = DEAD_TEXT if z.dead else graphics.DIMMED
                bright = nr == self.nr or chosen or display_time is not None
                graphics.text(area, graphics.shorten(name, pixel, sp_b - u // 2, "Medium"), (sx + u // 3, row_rect.centery + 1),
                            pixel, color if bright else other, "midleft",
                            weight="SemiBold" if nr == self.nr else "Medium")
            if z.dead:
                _dead_mark(area, row_rect)

        selection = -1 if display_time is not None else self.selection
        list_draw(area, list_, len(rows), selection, height, row_draw, offset)
        if bar is not None:
            area.blit(graphics.rounded_rect(bar.size, bar.width // 2, (255, 255, 255, 70)), bar)

    def _draw_open(self, area, rect: pygame.Rect, u: int, row) -> None:
        """Draws the opened row with the details of each player."""
        pixel = max(10, round(u * 0.62))
        r = graphics.text(area, graphics.shorten(row.name, pixel, rect.width * 2 // 3, "Bold"), (rect.x, rect.y),
                        pixel, graphics.TEXT, "topleft", weight="Bold")
        status = pygame.Rect(0, 0, round(u * 3.4), round(u * 0.95))
        status.midright = (rect.right, r.centery)
        area.blit(graphics.rounded_rect(status.size, status.height // 3, (*(DEAD_COLOR if row.dead else graphics.OK), 255)),
                     status)
        graphics.text(area, self.api.t("dead" if row.dead else "alive"), status.center, max(8, round(u * 0.48)),
                    (255, 255, 255), "center", weight="Bold")
        y = r.bottom + u // 3
        kh = round(u * 1.5)
        kb = rect.width // max(1, len(self.data.player))
        for j, nr in enumerate(self.data.player):
            map_ = pygame.Rect(rect.x + j * kb, y, kb - u // 4, kh)
            chosen = nr == self.column
            graphics.card(area, map_, chosen, radius=kh // 3, glowing=False)
            badge_rect = graphics.badge(area, (map_.x + u // 3, map_.centery), nr, max(8, round(u * 0.5)))
            catch = row.catches.get(nr)
            dex = self.data.dex(nr)
            if catch is None and nr in row.missed:
                name = MISSED + displayable(dex.name(row.missed[nr]) if dex else f"#{row.missed[nr]}")
            else:
                name = "–" if catch is None else displayable(nickname(catch, dex) or (dex.name(catch.kind) if dex else
                                                                                      f"#{catch.kind}"))
            graphics.text(area, graphics.shorten(name, max(9, round(u * 0.52)), map_.right - badge_rect.right - u // 2, "SemiBold"),
                        (badge_rect.right + u // 4, map_.centery + 1), max(9, round(u * 0.52)),
                        (255, 255, 255) if chosen else graphics.TEXT, "midleft", weight="SemiBold")
        details = pygame.Rect(rect.x, y + kh + u // 2, rect.width, rect.bottom - y - kh - u // 2)
        catch = row.catches.get(self.column)
        missed = row.missed.get(self.column)
        if catch is None and missed is not None and self.data.dex(self.column) is not None:
            dex = self.data.dex(self.column)
            draw_details(area, details, u, dex, missed, self.api.t("not_caught_info", nr=self.column),
                            MISSED + dex.name(missed), self.scroll)
            return
        if catch is None:
            hint(area, details, u, [self.api.t("nothing_caught", nr=self.column), self.api.t("x_enter")])
            return
        dex = self.data.dex(self.column)
        if dex is None:
            error = self.data.dex_error(self.column)
            hint(area, details, u, [t("dex.missing", error=error)] if error else [t("dex.loads")],
                    loads=error is None)
            return
        kind = dex.name(catch.kind)
        own = nickname(catch, dex)
        title = f"{own} ({kind})" if own else kind
        parts = [self.api.t("player", nr=self.column)]
        if catch.level:
            parts.append(self.api.t("level", level=catch.level))
        if catch.team or catch.box is not None:
            parts.append(self.api.t("in_team") if catch.team else self.api.t("box", box=catch.box + 1))
        under = " · ".join(parts)
        draw_details(area, details, u, dex, catch.kind, under, title, self.scroll)


class SoullinkList(Display):
    """Display "Soullink list" in the free field: the live list without selection."""
    ram_interval = 10.0

    def __init__(self, api, data):
        """Creates the display on top of a read-only tab."""
        self._tab = SoullinkTab(api, data, 0)

    def draw(self, area, rect, u: int, time: float) -> None:
        """Draws the list."""
        self._tab.draw_display(area, rect, u, time)


class LevelTab(Tab):
    """Overlay tab "Level": the level cap from gym leaders, Elite Four and champion by badges."""
    id, position = "level", 30
    ram_interval = 5.0

    def __init__(self, api, data, nr: int, badge=None):
        """Creates the tab for a player; badge() returns the player's badge count."""
        self.api = api
        self.data = data
        self.nr = nr
        self.badge = badge or (lambda: None)
        self.selection = 0
        self._battles: list[Battle] = []

    def title(self, short: bool = False) -> str:
        """Tab title, abbreviated if short."""
        return self.api.t("tab_level_short") if short else self.api.t("tab_level")

    def group(self, k: Battle, sixteen: bool) -> str:
        """Heading of the group; with 16 gyms (HGSS) it is split into 1-8 and 9-16."""
        if k.kind == "arena":
            if not sixteen:
                return self.api.t("level_gyms")
            of, until = (1, 8) if k.number <= 8 else (9, 16)
            return self.api.t("level_gyms_range", of=of, until=until)
        return self.api.t("level_top4") if k.round_ == 1 else self.api.t("level_rematch")

    def label(self, k: Battle) -> str:
        """Row label of a battle."""
        if k.kind == "arena":
            return self.api.t("level_arena", nr=k.number)
        return self.api.t("level_champ") if k.kind == "champ" else self.api.t("level_top4_slot", nr=k.number)

    def _list(self) -> list[Battle]:
        """The battles of the player's ROM; empty while it loads."""
        dex = self.data.dex(self.nr)
        self._battles = battles(dex) if dex is not None else []
        return self._battles

    def cap(self, list_: list[Battle]) -> int | None:
        """Index of the next battle by badge count: gyms 1-8, then the Elite Four; in HGSS afterwards gyms 9-16 and the
        second Elite Four."""
        badge = self.badge()
        if badge is None:
            return None
        gyms = {k.number: i for i, k in enumerate(list_) if k.kind == "arena"}
        top4 = {r: next((i for i, k in enumerate(list_) if k.kind == "top4" and k.round_ == r), None) for r in (1, 2)}
        if badge < 8 or 8 < badge < max(gyms, default=0):
            return gyms.get(badge + 1)
        if badge == 8 or top4[2] is None:
            return top4[1]
        return top4[2]

    def event(self, key: Key) -> bool:
        """Scrolls through the battles."""
        list_ = self._list()
        if list_ and key in (Key.UP, Key.DOWN):
            self.selection = (self.selection + (1 if key == Key.DOWN else -1)) % len(list_)
            return True
        return False

    def hints(self) -> list[tuple[str, str]]:
        """Button hints of the tab."""
        return [(f"{t('button.up')}/{t('button.down')}", t("about.page")), ("L/R", t("hint.page")),
                ("B", t("hint.close"))]

    def draw(self, area, rect: pygame.Rect, u: int, time: float = 0.0) -> None:
        """Draws the tab."""
        dex = self.data.dex(self.nr)
        if dex is None:
            error = self.data.dex_error(self.nr)
            hint(area, rect, u, [t("dex.missing", error=error)] if error else [t("dex.loads")],
                    loads=error is None, time=time)
            return
        list_ = self._list()
        if not list_:
            hint(area, rect, u, [self.api.t("level_no")])
            return
        self.selection = min(self.selection, len(list_) - 1)
        cap = self.cap(list_)
        badge = self.badge()
        height, gap, header = round(u * 1.2), max(3, u // 6), round(u * 1.0)
        sixteen = any(k.kind == "arena" and k.number > 8 for k in list_)
        layout, last = [], None
        for i, k in enumerate(list_):
            new = self.group(k, sixteen)
            if new != last:
                if k.kind == "arena" and k.number in (1, 9) and badge is not None:
                    new_text = f"{new}  ·  {self.api.t('level_badge', count=badge)}" if k.number == 1 else new
                else:
                    new_text = new
                layout.append(("group", new_text))
            last = new
            layout.append(("row", i))
        positions, y = [], 0
        for kind, _ in layout:
            positions.append(y)
            y += height + gap if kind == "row" else header
        middle = next(pos for (kind, value), pos in zip(layout, positions) if kind == "row" and value == self.selection)
        offset = max(0, min(middle + height // 2 - rect.height // 2, y - rect.height))
        pixel = max(9, round(u * 0.55))
        old_clip = area.get_clip()
        area.set_clip(rect.clip(old_clip))
        for (kind, value), pos in zip(layout, positions):
            top = rect.y + pos - offset
            if top + height < rect.y or top > rect.bottom:
                continue
            if kind == "group":
                graphics.text(area, value, (rect.x + u // 4, top + header * 3 // 5), max(9, round(u * 0.45)),
                            graphics.DIMMED, "midleft", weight="SemiBold")
                continue
            k = list_[value]
            row = pygame.Rect(rect.x, top, rect.width, height)
            chosen = value == self.selection
            defeated = badge is not None and k.kind == "arena" and k.number <= badge
            graphics.card(area, row, chosen, radius=height // 3, glowing=False)
            if value == cap and not chosen:
                area.blit(graphics.rounded_rect(row.size, height // 3, (255, 255, 255, 0), 2, (*graphics.ACCENT2, 220)),
                             row)
            color = (255, 255, 255) if chosen else graphics.DIMMED if defeated else graphics.TEXT
            left = graphics.text(area, self.label(k), (row.x + u // 2, row.centery + 1), pixel,
                                (235, 235, 255) if chosen else graphics.DIMMED, "midleft", weight="Medium")
            right_x = row.right - u // 2
            lv = graphics.text(area, self.api.t("level_lv", level=k.level), (right_x, row.centery + 1), pixel,
                             color, "midright", weight="Bold")
            right_x = lv.x - u // 3
            if defeated:
                s = round(pixel * 0.8)
                x0, y0 = right_x - s, row.centery
                pygame.draw.lines(area, graphics.OK if not chosen else (255, 255, 255), False,
                                  [(x0, y0), (x0 + s // 3, y0 + s // 3), (x0 + s, y0 - s // 2)], max(2, s // 5))
                right_x = x0 - u // 3
            elif value == cap:
                cap_text = self.api.t("level_cap")
                badge_rect = pygame.Rect(0, 0, graphics.load_font(round(u * 0.42), "Bold").size(cap_text)[0] + u // 2,
                                  round(u * 0.7))
                badge_rect.midright = (right_x, row.centery)
                area.blit(graphics.rounded_rect(badge_rect.size, badge_rect.height // 2, (*graphics.ACCENT2, 255)), badge_rect)
                graphics.text(area, cap_text, (badge_rect.centerx, badge_rect.centery + 1), round(u * 0.42), (255, 255, 255),
                            "center", weight="Bold")
                right_x = badge_rect.x - u // 3
            graphics.text(area, graphics.shorten(k.name, pixel, right_x - left.right - u // 2, "SemiBold"),
                        (left.right + u // 2, row.centery + 1), pixel, color, "midleft", weight="SemiBold")
        area.set_clip(old_clip)
