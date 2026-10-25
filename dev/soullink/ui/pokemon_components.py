"""Building blocks for Pokemon tabs of plugins: detail view, scrolling list, notice ("loading"), types and names."""
from __future__ import annotations

import pygame

from .. import types
from ..dex import evolution_text, type_name
from ..language import t
from . import graphics
from .types_overlay import draw_type

VALUES = ("kp", "ang", "vertical", "spang", "spvert", "init")


def displayable(text: str) -> str:
    """Replaces the male and female signs, which Poppins lacks (Nidoran), with words."""
    return text.replace(chr(0x2642), " " + t("gender.m")).replace(chr(0x2640), " " + t("gender.w"))


def pokemon_types(dex, pokemon) -> list[str]:
    """Types of the Pokemon as names from types.TYPES (without Fairy and unknown ones)."""
    return [t for t in dict.fromkeys(type_name(z) for z in pokemon.types if z) if t in types.COLORS]


def draw_details(area, rect: pygame.Rect, u: int, dex, nr: int, subtitle: str = "", title: str | None = None,
                    scroll: int = 0) -> int:
    """Draws name, types, base values, evolutions and learnset of a Pokemon; returns the scroll limit."""
    pokemon = dex.pokemon_after_nr.get(nr) if dex is not None else None
    if pokemon is None:
        graphics.text(area, t("dex.no_data"), (rect.x, rect.y), max(10, round(u * 0.55)),
                    graphics.DIMMED, "topleft", weight="Medium")
        return 0
    large, small = max(12, round(u * 0.85)), max(9, round(u * 0.5))
    name = displayable(title or pokemon.name)
    r = graphics.text(area, graphics.shorten(name, large, rect.width * 3 // 5, "Bold"), (rect.x, rect.y), large,
                    graphics.TEXT, "topleft", weight="Bold")
    cb, ch = round(u * 3.4), round(u * 1.05)
    x = rect.right
    for type_ in reversed(pokemon_types(dex, pokemon)):
        x -= cb
        draw_type(area, type_, pygame.Rect(x, r.centery - ch // 2, cb, ch), max(9, round(u * 0.5)))
        x -= u // 3
    y = r.bottom + u // 4
    rows = [subtitle or f"#{pokemon.nr:03d}"]
    if pokemon.values:
        values = "  ".join(f"{t('value.' + k)} {w}" for k, w in zip(VALUES, pokemon.values)) + \
            "  " + t("dex.sum", sum=sum(pokemon.values))
        single_line = f"{rows[0]}   ·   {values}"
        fits = graphics.load_font(small, "Medium").size(single_line)[0] <= rect.width
        rows = [single_line] if fits else [rows[0], values]
    for row in rows:
        graphics.text(area, graphics.shorten(row, small, rect.width, "Medium"), (rect.x, y), small, graphics.DIMMED,
                    "topleft", weight="Medium")
        y += round(small * 1.6)
    if pokemon.evolutions:
        parts = [f"{displayable(dex.name(e.target))} ({displayable(evolution_text(e, dex))})" for e in pokemon.evolutions]
        text = t("dex.evolved_to", targets=", ".join(parts))
    else:
        text = t("dex.evolved_not")
    y = _wrap(area, text, rect.x, y, rect.width, max(10, round(u * 0.55)), graphics.ACCENT2) + u // 3
    return _draw_moves(area, pygame.Rect(rect.x, y, rect.width, rect.bottom - y), u, dex, pokemon, scroll)


def _wrap(area, text: str, x: int, y: int, width: int, pixel: int, color) -> int:
    """Draws text over several lines and returns the bottom edge."""
    load_font = graphics.load_font(pixel, "SemiBold")
    row = ""
    for word in text.split(" "):
        probe = f"{row} {word}".strip()
        if row and load_font.size(probe)[0] > width:
            graphics.text(area, row, (x, y), pixel, color, "topleft", weight="SemiBold")
            y += round(pixel * 1.35)
            row = word
        else:
            row = probe
    if row:
        graphics.text(area, row, (x, y), pixel, color, "topleft", weight="SemiBold")
        y += round(pixel * 1.35)
    return y


def _draw_moves(area, rect: pygame.Rect, u: int, dex, pokemon, scroll: int) -> int:
    """Draws the learnset of a Pokemon with its moves."""
    learnset = sorted(pokemon.learnset)
    if not learnset or rect.height < u:
        return len(learnset)
    pixel = max(9, round(u * 0.52))
    zh = round(pixel * 1.75)
    columns = 2 if rect.width >= u * 22 else 1
    width = (rect.width - (columns - 1) * u) // columns
    pro_column = max(1, rect.height // zh)
    visible = pro_column * columns
    start = max(0, min(scroll, len(learnset) - visible)) // columns * columns if len(learnset) > visible else 0
    cb = round(u * 2.2)
    for i, (level, nr) in enumerate(learnset[start:start + visible]):
        x = rect.x + (i // pro_column) * (width + u)
        y = rect.y + (i % pro_column) * zh
        graphics.text(area, t("dex.lv", level=level) if level > 0 else t("dex.start"), (x, y + zh // 2), pixel,
                    graphics.DIMMED,
                    "midleft", weight="Medium")
        move = dex.moves.get(nr)
        x_name = x + round(pixel * 3.6)
        type_ = type_name(move.type_) if move else "???"
        rest = width - (x_name - x) - (cb + u // 3 if type_ in types.COLORS else 0)
        if move and move.strength > 1:
            rest -= round(pixel * 2.2)
            graphics.text(area, str(move.strength), (x + width - cb - u // 2, y + zh // 2), pixel, graphics.DIMMED,
                        "midright", weight="Medium")
        graphics.text(area, graphics.shorten(dex.move(nr), pixel, rest, "SemiBold"), (x_name, y + zh // 2), pixel,
                    graphics.TEXT, "midleft", weight="SemiBold")
        if type_ in types.COLORS:
            draw_type(area, type_, pygame.Rect(x + width - cb, y + 3, cb, zh - 6), max(8, round(pixel * 0.85)),
                        short=True)
    if len(learnset) > visible:
        graphics.text(area, f"{start + 1}–{min(len(learnset), start + visible)} / {len(learnset)}",
                    (rect.right, rect.y - u // 3), max(8, round(u * 0.45)), graphics.DIMMED, "bottomright",
                    weight="Medium")
    return len(learnset)


def list_draw(area, rect: pygame.Rect, count: int, selection: int, row_height: int, draw_row,
                   offset: int | None = None) -> None:
    """Scrolling list that keeps the selection as visible as possible and draws the rows through draw_row."""
    visible = max(1, rect.height // row_height)
    until = visible + 2
    if offset is None:
        offset, until = min(max(0, selection - visible // 2), max(0, count - visible)) * row_height, visible
    old_clip = area.get_clip()
    area.set_clip(rect.clip(old_clip))
    first = offset // row_height
    for i in range(first, min(count, first + until)):
        row = pygame.Rect(rect.x, rect.y + i * row_height - offset, rect.width, row_height - 3)
        if i == selection:
            area.blit(graphics.gradient_rect(row.size, row.height // 3), row)
        draw_row(i, row, i == selection)
    area.set_clip(old_clip)


def hint(area, rect: pygame.Rect, u: int, rows: list[str], loads: bool = False, time: float = 0.0) -> None:
    """Rows centered in the upper third (e.g. "loading ...", with a spinner)."""
    y = rect.y + rect.height // 3
    if loads:
        graphics.spinner(area, (rect.centerx, y - u), max(8, u // 2), time)
    for row in rows:
        graphics.text(area, row, (rect.centerx, y), max(10, round(u * 0.6)), graphics.DIMMED, "midtop",
                    weight="Medium")
        y += round(u * 1.1)
