"""Example plugin "Hello": a Hello tab with a greet counter, a setting, a menu entry and a clock display in the free field.
Copy the folder into <data directory>/plugins/ to try it; details are in docs/plugins.md."""
from __future__ import annotations

from soullink.plugin.api import Display, Setting, MenuEntry, Plugin, Tab
from soullink.ui import graphics


class HelloTab(Tab):
    """Overlay tab that shows how often the player greeted."""
    id = "hello"
    position = 45

    def __init__(self, plugin: "HelloPlugin", nr: int):
        """Creates the tab for a player."""
        self.plugin, self.nr = plugin, nr

    def title(self, short: bool = False) -> str:
        """Tab title, abbreviated if short."""
        return self.plugin.api.t("tab_short" if short else "tab")

    def draw(self, area, rect, u: int, time: float) -> None:
        """Draws the greeting counter."""
        text = self.plugin.api.t("greeted", count=self.plugin.greetings.get(self.nr, 0))
        graphics.text(area, text, (rect.x, rect.y + u), max(10, round(u * 0.7)), graphics.TEXT, "midleft")


class HelloDisplay(Display):
    """Free-field display that shows the playtime in minutes."""

    def __init__(self, plugin: "HelloPlugin"):
        """Creates the display."""
        self.plugin = plugin

    def draw(self, area, rect, u: int, time: float) -> None:
        """Draws the playtime."""
        minutes = int(self.plugin.game.playtime) // 60 if self.plugin.game else 0
        graphics.text(area, self.plugin.api.t("minutes", minutes=minutes), rect.center, u, graphics.TEXT, "center")


class HelloPlugin(Plugin):
    """The example plugin object."""

    def __init__(self, api):
        """Creates the plugin with empty greeting counters."""
        super().__init__(api)
        self.game = None
        self.greetings: dict[int, int] = {}

    def settings(self) -> list[Setting]:
        """A "loud" switch in the main menu."""
        return [Setting("loud", self.api.t("loud"), "switch", False)]

    def display_names(self) -> list[tuple[str, str]]:
        """The clock display for the free field."""
        return [("clock", self.api.t("display"))]

    def fits(self, session) -> bool | str:
        """Active in every session."""
        return True

    def session_start(self, game) -> None:
        """Remembers the game; the plugin object lives across several games."""
        self.game = game
        self.greetings = {nr: 0 for nr in game.player_numbers()}

    def session_end(self) -> None:
        """Forgets the game."""
        self.game = None

    def player_menu(self, nr: int) -> list[MenuEntry]:
        """A "Greet" entry in the "Plugins" submenu."""
        return [MenuEntry("greet", self.api.t("greet"), lambda: self._greet(nr))]

    def _greet(self, nr: int) -> None:
        """Counts one more greeting of a player."""
        self.greetings[nr] += 1
        text = self.api.t("hello_loud" if self.api.setting("loud") else "hello")
        self.game.report(nr, text)

    def overlay_tab(self, nr: int) -> list:
        """The Hello tab of a player."""
        return [HelloTab(self, nr)]

    def display(self, display_id: str):
        """The clock display for its id."""
        return HelloDisplay(self) if display_id == "clock" else None


def create(api):
    """Creates the plugin object."""
    return HelloPlugin(api)
