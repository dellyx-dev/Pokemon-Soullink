""""About": who made Pokemon-Soullink, which third-party software and which active plugins it contains (with licenses), and
the Pokemon trademark notice."""
from __future__ import annotations

import sys
from pathlib import Path

import pygame

from .. import AUTHOR, PROJECT_URL, paths
from ..input.devices import KeysEvent
from ..input.keys import CONFIRM, BACK_KEYS, Key
from ..language import t
from . import graphics
from .app import Screen
from .start import TITLE, trademark_notice

THIRD = [
    ("mGBA", "about.purpose_gba", "MPL-2.0", "mgba.io", ["MPL-2.0.txt"]),
    ("melonDS DS", "about.purpose_nds", "GPL-3.0", "github.com/JesseTG/melonds-ds", ["GPL-3.0.txt"]),
    ("Universal Pokemon Randomizer ZX", "about.purpose_randomizer", "GPL-3.0",
     "github.com/Ajarmar/universal-pokemon-randomizer-zx", ["GPL-3.0.txt"]),
    ("Python", "about.purpose_python", "PSF License", "python.org", ["Python-LICENSE.txt"]),
    ("pygame-ce · SDL2", "about.purpose_pygame", "LGPL-2.1 · zlib", "pyga.me", ["LGPL-2.1.txt", "SDL2-zlib.txt"]),
    ("NumPy", "about.purpose_numpy", "BSD-3-Clause", "numpy.org", ["NumPy-LICENSE.txt"]),
    ("Poppins", "about.purpose_load_font", "SIL OFL 1.1", "Indian Type Foundry", ["Poppins-OFL.txt"]),
]


def _source_license(name: str) -> Path | None:
    """Licence texts when started from source, which build.py would otherwise copy into licenses/ beside the exe."""
    if name == "Python-LICENSE.txt":
        return Path(sys.base_prefix) / "LICENSE.txt"
    if name == "NumPy-LICENSE.txt":
        import numpy

        return next(Path(numpy.__file__).parent.parent.glob("numpy-*.dist-info/licenses/LICENSE.txt"), None)
    if name == "Poppins-OFL.txt":
        return Path(__file__).resolve().parent / "fonts" / "OFL.txt"
    return None


def license_file(name: str | Path) -> Path | None:
    """Licence text file for a name from THIRD; a Path (the licence of a plugin) stands for itself."""
    if isinstance(name, Path):
        return name if name.is_file() else None
    path = paths.license_dir() / name
    return path if path.is_file() else _source_license(name)


def license_text(files: list[str | Path]) -> list[str]:
    """Lines of all licence texts of an entry (several separated by a blank line)."""
    rows: list[str] = []
    for name in files:
        path = license_file(name)
        try:
            text = path.read_text(encoding="utf-8", errors="replace") if path else None
        except OSError:
            text = None
        if rows:
            rows += ["", "—" * 12, ""]
        if text is None:
            rows.append(t("about.license_missing", file=Path(name).name))
        else:
            rows += text.replace("\t", "    ").replace("\f", "").splitlines()
    return rows


def wrap(rows: list[str], pixel: int, width: int) -> list[str]:
    """Wraps long lines at word boundaries to the width; blank lines stay as paragraph breaks."""
    load_font = graphics.load_font(pixel, "Medium")
    out: list[str] = []
    for row in rows:
        if load_font.size(row)[0] <= width:
            out.append(row)
            continue
        indent = row[:len(row) - len(row.lstrip())]
        current = ""
        for word in row.split():
            probe = f"{current} {word}" if current else indent + word
            if current and load_font.size(probe)[0] > width:
                out.append(current)
                current = indent + word
            else:
                current = probe
        out.append(current)
    return out


class AboutScreen(Screen):
    """Screen listing software and plugins with their licenses."""

    def __init__(self, app):
        """Creates the screen."""
        super().__init__(app)
        self.plugins = [info for info, _ in app.plugins.active()]
        self._licenses = [info.dir / info.license if info.license and (info.dir / info.license).is_file() else None
                          for info in self.plugins]
        self.selection = 0
        self.open_: int | None = None
        self.scroll = 0
        self._wrap: tuple | None = None
        self._rows: list[str] = []
        self._page = 10

    def _entry(self, nr: int) -> tuple[str, str, list]:
        """(title, subtitle, licence files) of a row: first the third-party software, then the active plugins."""
        if nr < len(THIRD):
            name, _, license, _, files = THIRD[nr]
            return name, license, files
        info, license = self.plugins[nr - len(THIRD)], self._licenses[nr - len(THIRD)]
        return info.name, t("about.plugin_header", version=info.version, author=info.author), [license] if license else []

    def event(self, e) -> None:
        """Handles a key."""
        if not isinstance(e, KeysEvent) or not e.pressed:
            return
        if self.open_ is not None:
            if e.key in BACK_KEYS or e.key in CONFIRM:
                self.open_ = None
            elif e.key in (Key.UP, Key.DOWN, Key.LEFT, Key.RIGHT):
                step = 1 if e.key in (Key.UP, Key.DOWN) else self._page - 1
                direction = -1 if e.key in (Key.UP, Key.LEFT) else 1
                self.scroll = max(0, min(self.scroll + direction * step, len(self._rows) - self._page))
            return
        if e.key in BACK_KEYS:
            self._back()
        elif e.key in (Key.UP, Key.DOWN):
            self.selection = (self.selection + (1 if e.key == Key.DOWN else -1)) % (len(THIRD) + len(self.plugins))
        elif (e.key in CONFIRM or e.key == Key.START) and self._entry(self.selection)[2]:
            self.open_, self.scroll = self.selection, 0

    def raw(self, ev) -> None:
        """Handles Escape."""
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if self.open_ is not None:
                self.open_ = None
            else:
                self._back()

    def _back(self) -> None:
        """Returns to the start screen."""
        from .start import StartScreen

        self.app.switch(StartScreen(self.app))

    def draw(self, area) -> None:
        """Draws the list or the open licence text."""
        def g(n):
            """Scales a base size to the screen."""
            return graphics.size(area, n)

        width = min(area.get_width() - g(100), g(1720))
        x = (area.get_width() - width) // 2
        if self.open_ is not None:
            self._draw_license(area, x, width, g)
            return
        graphics.text(area, t("about.title", name=TITLE), (x, g(100)), g(56), graphics.TEXT, "midleft",
                    weight="ExtraBold")
        row = t("about.author", author=AUTHOR) + (f"  ·  {PROJECT_URL}" if PROJECT_URL else "")
        graphics.text(area, row, (x + g(4), g(152)), g(26), graphics.ACCENT2, "midleft", weight="SemiBold")
        graphics.text(area, t("about.software"), (x, g(222)), g(28), graphics.TEXT, "midleft", weight="Bold")
        height, header = g(56), g(58)
        range_ = pygame.Rect(x, g(262), width, area.get_height() - g(208) - g(262))
        layout = [("row", nr) for nr in range(len(THIRD))]
        if self.plugins:
            layout += [("header", None)] + [("row", len(THIRD) + i) for i in range(len(self.plugins))]
        positions, y = [], 0
        for kind, _ in layout:
            positions.append(y)
            y += height if kind == "row" else header
        y -= g(8)
        middle = positions[layout.index(("row", self.selection))]
        offset = max(0, min(middle + height // 2 - range_.height // 2, y - range_.height))
        if y > range_.height:
            graphics.text(area, f"{self.selection + 1} / {len(THIRD) + len(self.plugins)}", (range_.right, g(222)),
                        g(22), graphics.DIMMED, "midright", weight="Medium")
        limits = [x + g(20), x + width * 30 // 100, x + width * 52 // 100, x + width * 70 // 100, x + width - g(20)]
        old_clip = area.get_clip()
        area.set_clip(range_.clip(old_clip))
        for (kind, nr), pos in zip(layout, positions):
            top = range_.y + pos - offset
            if top + header < range_.y or top > range_.bottom:
                continue
            if kind == "header":
                graphics.text(area, t("about.plugins"), (x, top + g(26)), g(28), graphics.TEXT, "midleft", weight="Bold")
            else:
                self._draw_entry(area, pygame.Rect(x, top, width, height - g(8)), nr, limits, g)
        area.set_clip(old_clip)
        graphics.text(area, t("about.license_texts"), (x, range_.y + min(y, range_.height) + g(32)), g(22),
                    graphics.DIMMED, "midleft", weight="Medium")
        trademark_notice(area, area.get_height() - g(140))
        hints = [("A", t("about.license_show"))] if self._entry(self.selection)[2] else []
        graphics.footer(area, hints + [("B", t("hint.back"))])

    def _draw_entry(self, area, rect: pygame.Rect, nr: int, limits: list[int], g) -> None:
        """Draws one row of the list."""
        if nr < len(THIRD):
            name, purpose, license, source, _ = THIRD[nr]
            columns = ((name, g(24), graphics.TEXT, "SemiBold"), (t(purpose), g(22), graphics.DIMMED, "Medium"),
                       (license, g(22), graphics.ACCENT2, "SemiBold"), (source, g(20), graphics.DIMMED, "Medium"))
        else:
            info = self.plugins[nr - len(THIRD)]
            columns = ((info.name, g(24), graphics.TEXT, "SemiBold"),
                       (t("about.plugin_version", version=info.version) if info.version else "", g(22), graphics.DIMMED,
                        "Medium"),
                       (t("about.plugin_author", author=info.author) if info.author else "", g(22), graphics.ACCENT2,
                        "SemiBold"),
                       (info.license if self._entry(nr)[2] else "", g(20), graphics.DIMMED, "Medium"))
        chosen = nr == self.selection
        graphics.card(area, rect, chosen, radius=rect.height // 3, glowing=False)
        for i, (content, pixel, color, weight) in enumerate(columns):
            if content:
                slot = limits[i + 1] - limits[i] - g(16)
                graphics.text(area, graphics.shorten(content, pixel, slot, weight), (limits[i], rect.centery + 1), pixel,
                            (255, 255, 255) if chosen else color, "midleft", weight=weight)

    def _draw_license(self, area, x: int, width: int, g) -> None:
        """Draws the licence text of the open entry."""
        name, license, files = self._entry(self.open_)
        graphics.text(area, name, (x, g(100)), g(48), graphics.TEXT, "midleft", weight="ExtraBold")
        graphics.text(area, license, (x + g(4), g(148)), g(26), graphics.ACCENT2, "midleft", weight="SemiBold")
        rect = pygame.Rect(x, g(185), width, area.get_height() - g(185) - g(110))
        graphics.panel(area, rect, opacity=200)
        pixel, zh = g(22), round(g(22) * 1.45)
        inside = rect.inflate(-g(80), -g(48))
        key = (self.open_, inside.width, pixel)
        if self._wrap != key:
            self._rows = wrap(license_text(files), pixel, inside.width - g(24))
            self._wrap = key
        self._page = max(1, inside.height // zh)
        self.scroll = max(0, min(self.scroll, len(self._rows) - self._page))
        for i, row in enumerate(self._rows[self.scroll:self.scroll + self._page]):
            if row:
                graphics.text(area, row, (inside.x, inside.y + i * zh), pixel, graphics.TEXT, "topleft",
                            weight="Medium")
        if len(self._rows) > self._page:
            away = len(self._rows) - self._page
            track = pygame.Rect(inside.right + g(20), inside.y, g(6), inside.height)
            bar_h = max(g(40), track.height * self._page // len(self._rows))
            bar = pygame.Rect(track.x, track.y + (track.height - bar_h) * self.scroll // away, track.width, bar_h)
            area.blit(graphics.rounded_rect(track.size, track.width // 2, (255, 255, 255, 25)), track)
            area.blit(graphics.rounded_rect(bar.size, bar.width // 2, (255, 255, 255, 110)), bar)
            end = min(len(self._rows), self.scroll + self._page)
            graphics.text(area, f"{self.scroll + 1}–{end} / {len(self._rows)}", (rect.right, g(148)), g(22),
                        graphics.DIMMED, "midright", weight="Medium")
        page = f"{t('button.up')}/{t('button.down')}"
        graphics.footer(area, [(page, t("about.page")), ("<>", t("hint.page")),
                                   ("B", t("hint.back"))])
