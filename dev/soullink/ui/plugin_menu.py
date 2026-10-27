"""Plugins in the player menu: the "Plugins" submenu (rows, drawing, A/B, restarting a plugin switched off by an error)
and clean-up when a plugin drops out or comes back."""
from __future__ import annotations

import pygame

from ..plugin.api import MenuEntry
from ..language import t
from . import graphics
from .menu import BACK, Menu

RESTART = "_restart"


def _nothing() -> None:
    """Placeholder action that does nothing."""
    return None


class PluginMenu:
    """Part of the game screen (ui/game.py) for the "Plugins" submenu, offered in a player's menu when an active plugin
    gives that player entries."""

    def __init__(self, game):
        """Creates the submenu handler for the game screen."""
        self.game = game

    def visible(self, nr: int) -> bool:
        """True if the player has anything to show in the submenu."""
        return bool(self._rows(nr))

    def _rows(self, nr: int) -> list[tuple]:
        """(PluginInfo, MenuEntry, group header) rows; empty if there is nothing for this player."""
        plugins = self.game.plugins
        rows = [(info, entry, info.name) for info, list_ in plugins.menu(nr) for entry in list_]
        rows += [(info, MenuEntry("_inactive", info.name, _nothing, reason=reason), t("menu.plugins_inactive"))
                 for info, reason in plugins.not_matching]
        rows += [(info, MenuEntry(RESTART, info.name, lambda info=info: plugins.restart(info),
                                  reason=t("plugin.error_reason")), t("menu.plugins_inactive"))
                 for info in plugins.disabled]
        return rows

    def open_(self, sp, selection: int = 0) -> None:
        """Opens or relabels the submenu; if nothing is left to show it returns to the player menu."""
        rows = self._rows(sp.nr)
        if not rows:
            self.game._menu_open(sp, self.game._menu_index(sp, "overlay"))
            return
        sp.plugin_rows = rows
        sp.menu_actions = ["plugin"] * len(sp.plugin_rows)
        sp.menu = Menu([entry.text for _, entry, _ in sp.plugin_rows])
        sp.menu.selection = min(selection, len(sp.plugin_rows) - 1)
        sp.menu_question, sp.submenu = False, "plugins"

    def key(self, sp, choice, back: bool) -> None:
        """A triggers the entry (greyed-out ones do nothing, a plugin switched off by an error is restarted); B or the menu
        key goes back to "Plugins"."""
        if choice == BACK or back:
            self.game._menu_open(sp, self.game._menu_index(sp, "plugins"))
        elif isinstance(choice, int):
            info, entry, _ = sp.plugin_rows[choice]
            if entry.id == RESTART and info in self.game.plugins.disabled:
                entry.trigger()
            elif entry.reason:
                return
            else:
                self.game.plugins.trigger(info, entry)
            if sp.submenu == "plugins" and sp.menu is not None:
                self.open_(sp, choice)

    @staticmethod
    def layout(sp) -> list[tuple[str, int | str]]:
        """Group header per plugin (or "Inactive") with its rows below."""
        layout, header = [], None
        for i, (_, _, group) in enumerate(sp.plugin_rows):
            if group != header:
                layout.append(("group", group))
            header = group
            layout.append(("row", i))
        return layout

    @staticmethod
    def extra_width(sp, i: int, p: int) -> int:
        """Space next to the text of row i for the reason (small) or the switch."""
        entry, width = sp.plugin_rows[i][1], 0
        if entry.reason:
            width += graphics.load_font(round(p * 0.62), "Medium").size(entry.reason)[0] + p // 2
        if entry.switch is not None:
            width += round(p * 3.6)
        return width

    def draw_row(self, area, row: pygame.Rect, sp, i: int, p: int, chosen: bool) -> None:
        """Draws the text, a greyed-out row with its reason, or a switch on the right (card and selection are drawn by the
        player menu)."""
        info, entry, _ = sp.plugin_rows[i]
        right = row.right - round(p * 0.8)
        if entry.switch is not None:
            on = self.game.plugins.switch(info, entry)
            right = graphics.switch(area, (right, row.centery), on, p, chosen).x - p // 2
        gray = bool(entry.reason)
        color = ((235, 235, 255) if gray else (255, 255, 255)) if chosen else graphics.DIMMED if gray else graphics.TEXT
        x = row.x + round(p * 0.8)
        left = graphics.text(area, graphics.shorten(entry.text, p, right - x), (x, row.centery + 1), p, color,
                            "midleft")
        if gray:
            small, color = round(p * 0.62), (235, 235, 255) if chosen else graphics.DIMMED
            graphics.text(area, graphics.shorten(entry.reason, small, max(0, right - left.right - p // 2), "Medium"),
                        (left.right + p // 2, row.centery + 1), small, color, "midleft", weight="Medium")

    def new_order(self) -> None:
        """A plugin is off or restarted: its tabs, displays and menu entries disappear or come back with the next frame, not
        in the middle of drawing a menu."""
        game = self.game
        plugins = game.plugins
        restarted, plugins.restarted, plugins.changed = plugins.restarted, [], False
        again = {info.id for info in restarted}
        for sp in game.player:
            sp.plugin_tab = [r for r in sp.plugin_tab if r.active and r.plugin_id not in again] + \
                plugins.tab(sp.nr, restarted)
            sp.types.tab_set(sp.core_tab + sp.plugin_tab)
            if sp.submenu == "plugins":
                self.open_(sp, sp.menu.selection)
            elif sp.menu is not None and not sp.menu_question and not sp.submenu:
                game._menu_open(sp)
        game.field.show = [a for a in game.field.show if getattr(a[2], "active", True)
                           and getattr(a[2], "plugin_id", None) not in again] + plugins.show(restarted)
