"""Screen layout: cells per player, 3:2 game rectangles and margins for labels."""
from __future__ import annotations

from dataclasses import dataclass

GBA_W, GBA_H = 240, 160
MARGIN_MIN = 24
MAX_LOGICAL = (1920, 1080)


@dataclass(frozen=True)
class Rect:
    """Integer rectangle with position and size."""
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Cell:
    """One player's cell with its game rectangle and the free margin for the label."""
    cell: Rect
    game: Rect
    margin: Rect | None
    vertical: bool


def grid(count: int) -> tuple[int, int]:
    """Column and row count of the cell grid for the given player count."""
    return {1: (1, 1), 2: (2, 1)}.get(count, (2, 2))


def _game_in(cell: Rect) -> Rect:
    """Largest 3:2 rectangle centered in the cell."""
    if cell.w * GBA_H >= cell.h * GBA_W:
        h = cell.h
        w = min(cell.w, round(h * GBA_W / GBA_H))
    else:
        w = cell.w
        h = min(cell.h, round(w * GBA_H / GBA_W))
    return Rect(cell.x + (cell.w - w) // 2, cell.y + (cell.h - h) // 2, w, h)


def _margin(cell: Rect, game: Rect) -> tuple[Rect | None, bool]:
    """Free margin left of or above the game rectangle and whether it is a side margin."""
    sideways = game.x - cell.x
    top = game.y - cell.y
    if sideways >= top:
        if sideways >= MARGIN_MIN:
            return Rect(cell.x, cell.y, sideways, cell.h), True
        return None, True
    if top >= MARGIN_MIN:
        return Rect(cell.x, cell.y, cell.w, top), False
    return None, False


def compute(count: int, width: int, height: int) -> list[Cell]:
    """Cells for a GBA session on the given screen size."""
    columns, rows = grid(count)
    cw, ch = width // columns, height // rows
    result = []
    for row in range(rows):
        for column in range(columns):
            cell = Rect(column * cw, row * ch, cw, ch)
            game = _game_in(cell)
            margin, vertical = _margin(cell, game)
            result.append(Cell(cell, game, margin, vertical))
    return result


DS_W, DS_H = 256, 192
VIEWS = ("hybrid", "columns")


@dataclass(frozen=True)
class DsCell:
    """One player's cell for DS games with a large and a small screen."""
    cell: Rect
    large: Rect
    small: Rect
    free: Rect | None
    vertical: bool


def _ds_column(cell: Rect) -> DsCell:
    """Column layout with both DS screens stacked."""
    s = min(cell.w / DS_W, cell.h / (2 * DS_H))
    w, h = round(DS_W * s), round(DS_H * s)
    x, y = cell.x + (cell.w - w) // 2, cell.y + (cell.h - 2 * h) // 2
    free, vertical = None, False
    if y - cell.y >= MARGIN_MIN:
        free = Rect(cell.x, cell.y, cell.w, y - cell.y)
    elif x - cell.x >= MARGIN_MIN:
        free, vertical = Rect(cell.x, cell.y, x - cell.x, cell.h), True
    return DsCell(cell, Rect(x, y, w, h), Rect(x, y + h, w, h), free, vertical)


def _ds_hybrid(cell: Rect) -> DsCell:
    """Hybrid layout with one large screen and a half-size screen beside or below it."""
    s_next_to = min(cell.w / (1.5 * DS_W), cell.h / DS_H)
    s_under = min(cell.w / DS_W, cell.h / (1.5 * DS_H))
    s = max(s_next_to, s_under)
    gb, gh = round(DS_W * s), round(DS_H * s)
    kb, kh = gb // 2, gh // 2
    if s_next_to >= s_under:
        x, y = cell.x + (cell.w - gb - kb) // 2, cell.y + (cell.h - gh) // 2
        return DsCell(cell, Rect(x, y, gb, gh), Rect(x + gb, y + gh - kh, kb, kh),
                       Rect(x + gb, y, kb, gh - kh), False)
    x, y = cell.x + (cell.w - gb) // 2, cell.y + (cell.h - gh - kh) // 2
    return DsCell(cell, Rect(x, y, gb, gh), Rect(x + gb - kb, y + gh, kb, kh),
                   Rect(x, y + gh, gb - kb, kh), False)


def compute_ds(count: int, width: int, height: int, view: str) -> list[DsCell]:
    """DS cells for the "columns" view (one column per player) or the "hybrid" view (grid like GBA)."""
    if view == "columns":
        w = width // count
        return [_ds_column(Rect(i * w, 0, w, height)) for i in range(count)]
    columns, rows = grid(count)
    cw, ch = width // columns, height // rows
    return [_ds_hybrid(Rect(s * cw, z * ch, cw, ch)) for z in range(rows) for s in range(columns)]


def logical_resolution(width: int, height: int) -> tuple[int, int]:
    """Screen size scaled down to at most the maximum logical resolution."""
    mb, mh = MAX_LOGICAL
    if width <= mb and height <= mh:
        return width, height
    factor = min(mb / width, mh / height)
    return round(width * factor), round(height * factor)
