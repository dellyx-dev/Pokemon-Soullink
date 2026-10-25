"""Overlay tab "Pokedex": all Pokemon of the player's own ROM with types, values, evolutions and level-up moves. A shows
the details, X sorts by number or A-Z, and Y searches."""
from __future__ import annotations

import unicodedata

import pygame

from soullink.input.keys import CONFIRM, BACK_KEYS, Key
from soullink.plugin.api import Tab
from soullink.language import t
from soullink.ui import graphics
from soullink.ui.pokemon_components import displayable, hint, list_draw, pokemon_types, draw_details
from soullink.ui.keyboard import Search
from soullink.ui.types_overlay import draw_type


def _sort_name(name: str) -> str:
    """Sort key A-Z without umlaut special cases: "Aequitox" is filed under A."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()


class PokedexTab(Tab):
    """Overlay tab with the Pokedex list, the detail view and the search."""
    id, position = "pokedex", 50

    def __init__(self, api, nr: int):
        """Creates the tab for a player; api is the GameApi for texts and the player's ROM data."""
        self.api = api
        self.nr = nr
        self.selection = 0
        self.open_ = False
        self.scroll = 0
        self.after_name = False
        self.search = Search()

    def title(self, short: bool = False) -> str:
        """Tab title, abbreviated if short."""
        return self.api.t("tab_short") if short else self.api.t("tab")

    def keyboard_close(self) -> None:
        """The overlay closes: closes the on-screen keyboard."""
        self.search.close()

    def _list(self):
        """The Pokemon filtered by the search in the chosen sorting (number or A-Z), hits at the start of the name first;
        empty while there is no ROM data."""
        dex = self.api.dex(self.nr)
        list_ = [p for p in dex.pokemon if p is not None and p.nr > 0 and self.search.fits(p.name)] \
            if dex is not None else []
        if self.after_name:
            list_ = sorted(list_, key=lambda p: (_sort_name(p.name), p.nr))
        return sorted(list_, key=lambda p: self.search.rank(p.name))

    def _letter_jump(self, list_, direction: int) -> None:
        """A-Z: left/right jumps to the next or previous initial letter."""
        def start(i):
            """Initial letter of the entry at index i."""
            return _sort_name(list_[i].name)[:1]

        i = self.selection
        if direction > 0:
            now = start(i)
            while i < len(list_) - 1 and start(i) == now:
                i += 1
        else:
            if i > 0 and start(i - 1) != start(i):
                i -= 1
            now = start(i)
            while i > 0 and start(i - 1) == now:
                i -= 1
        self.selection = i

    def event(self, key: Key) -> bool:
        """Handles a key."""
        if self.search.is_open:
            before = self.search.text
            self.search.event(key)
            if self.search.text != before:
                self.selection = 0
            return True
        list_ = self._list()
        if not self.open_ and self.api.dex(self.nr) is not None:
            if key == Key.NORTH:
                self.search.open()
                return True
            if key in BACK_KEYS and self.search.active:
                self.search.clear()
                self.selection = 0
                return True
        if not list_:
            return False
        if self.open_:
            if key in BACK_KEYS:
                self.open_ = False
            elif key in (Key.UP, Key.DOWN):
                self.scroll = max(0, self.scroll + (2 if key == Key.DOWN else -2))
            elif key in (Key.LEFT, Key.RIGHT):
                self.selection = (self.selection + (1 if key == Key.RIGHT else -1)) % len(list_)
                self.scroll = 0
            return True
        if key == Key.WEST:
            self.after_name = not self.after_name
            self.selection = 0
            return True
        if self.after_name and key in (Key.LEFT, Key.RIGHT):
            self._letter_jump(list_, 1 if key == Key.RIGHT else -1)
            return True
        step = {Key.UP: -1, Key.DOWN: 1, Key.LEFT: -10, Key.RIGHT: 10}.get(key)
        if step is not None:
            self.selection = (self.selection + step) % len(list_)
            return True
        if key in CONFIRM or key == Key.START:
            self.open_, self.scroll = True, 0
            return True
        return False

    def hints(self) -> list[tuple[str, str]]:
        """Button hints for the current state."""
        if self.search.is_open:
            return self.search.hints()
        if self.open_:
            return [("<>", self.api.t("before_back")), ("B", t("hint.back"))]
        if self.after_name:
            return [("A", self.api.t("details")), ("Y", t("osk.search")), ("<>", self.api.t("letter")),
                    ("X", self.api.t("after_nr")), ("B", t("hint.close"))]
        return [("A", self.api.t("details")), ("Y", t("osk.search")), ("<>", t("hint.ten_next")),
                ("X", self.api.t("a_z")), ("B", t("hint.close"))]

    def draw(self, area, rect: pygame.Rect, u: int, time: float = 0.0) -> None:
        """Draws the list, the details or the search."""
        dex = self.api.dex(self.nr)
        if dex is None:
            error = self.api.dex_error(self.nr)
            hint(area, rect, u, [t("dex.missing", error=error)] if error else
                    [self.api.t("loads")], loads=error is None, time=time)
            return
        list_ = self._list()
        self.selection = min(self.selection, max(0, len(list_) - 1))
        if self.open_ and list_:
            draw_details(area, rect, u, dex, list_[self.selection].nr, scroll=self.scroll)
            return
        rect = self.search.draw(area, rect, u, time, len(list_))
        if not list_:
            hint(area, rect, u, [t("osk.no_hit")])
            return
        pixel = max(9, round(u * 0.58))
        cb, ch = round(u * 3.0), round(u * 0.95)

        def row_draw(i, row_rect, chosen):
            """Draws one list row."""
            p = list_[i]
            color = (255, 255, 255) if chosen else graphics.TEXT
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

        list_draw(area, rect, len(list_), self.selection, round(u * 1.3), row_draw)
