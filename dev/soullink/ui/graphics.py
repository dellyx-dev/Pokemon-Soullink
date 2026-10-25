""""Night glass" design: colors, font (Poppins), glass cards, gradients and button symbols. All sizes are meant for 1080
lines and scaled with size()."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pygame

FONTS = Path(__file__).resolve().parent / "fonts"

BG_TOP, BG_BOTTOM = (12, 15, 34), (36, 20, 72)
BACKGROUND = BG_TOP
ACCENT1, ACCENT2 = (124, 92, 255), (255, 92, 138)
ACCENT = ACCENT2
TEXT = (240, 242, 255)
DIMMED = (150, 158, 196)
ERROR = (255, 107, 107)
OK = (92, 224, 150)
WARNING = (255, 196, 61)
MAP = (255, 255, 255, 16)
MAP_RAND = (255, 255, 255, 30)
VEIL = (8, 10, 24)
PLAYER_COLORS = [(255, 92, 102), (64, 168, 255), (76, 214, 120), (255, 196, 61)]

_fonts: dict[tuple[int, str], pygame.font.Font] = {}
_areas: dict[tuple, pygame.Surface] = {}


def player_color(nr: int) -> tuple[int, int, int]:
    """Badge color of a player."""
    return PLAYER_COLORS[(nr - 1) % len(PLAYER_COLORS)]


def size(area: pygame.Surface, base: float) -> int:
    """Scales a base size relative to 1080 lines of screen height."""
    return max(1, round(base * area.get_height() / 1080))


def fonts_clear() -> None:
    """Drops cached fonts, since old font objects are invalid after pygame.quit()."""
    _fonts.clear()


def load_font(pixel: int, weight: str = "SemiBold") -> pygame.font.Font:
    """Poppins font in the given pixel size and weight, cached."""
    key = (max(8, int(pixel)), weight)
    font = _fonts.get(key)
    if font is None:
        if not pygame.font.get_init():
            pygame.font.init()
        file = FONTS / f"Poppins-{weight}.ttf"
        font = pygame.font.Font(str(file) if file.exists() else None, key[0])
        _fonts[key] = font
    return font


def text(area: pygame.Surface, content: str, pos, pixel: int, color=TEXT, anchor: str = "topleft",
         rotate: bool = False, weight: str = "SemiBold", alpha: int = 255) -> pygame.Rect:
    """Draws text at a position with an anchor and returns its rectangle; optionally rotated or transparent."""
    image = load_font(pixel, weight).render(content, True, color)
    if rotate:
        image = pygame.transform.rotate(image, 90)
    if alpha < 255:
        image.set_alpha(alpha)
    rect = image.get_rect(**{anchor: pos})
    area.blit(image, rect)
    return rect


def shorten(content: str, pixel: int, width: int, weight: str = "SemiBold") -> str:
    """Text shortened with an ellipsis to fit the width."""
    font = load_font(pixel, weight)
    if font.size(content)[0] <= width:
        return content
    while content and font.size(content + "…")[0] > width:
        content = content[:-1]
    return content + "…"


def _cache(key: tuple, create) -> pygame.Surface:
    """Returns the cached surface for the key, creating it on first use."""
    area = _areas.get(key)
    if area is None:
        if len(_areas) > 400:
            _areas.clear()
        area = _areas[key] = create()
    return area


def rounded_rect(size_: tuple[int, int], radius: int, color, border_width: int = 0, border_color=None) -> pygame.Surface:
    """Rounded rectangle with smooth edges (supersampled threefold) and an optional border."""
    b, h = max(1, int(size_[0])), max(1, int(size_[1]))

    def create():
        """Renders the rounded rectangle."""
        ss = 3
        large = pygame.Surface((b * ss, h * ss), pygame.SRCALPHA)
        r = min(radius, b // 2, h // 2) * ss
        pygame.draw.rect(large, color, large.get_rect(), border_radius=r)
        if border_width:
            pygame.draw.rect(large, border_color, large.get_rect(), width=border_width * ss, border_radius=r)
        return pygame.transform.smoothscale(large, (b, h))

    return _cache(("round", b, h, radius, tuple(color), border_width, tuple(border_color or ())), create)


def gradient_rect(size_: tuple[int, int], radius: int, left=ACCENT1, right=ACCENT2) -> pygame.Surface:
    """Rounded rectangle with a horizontal gradient from left to right."""
    b, h = max(1, int(size_[0])), max(1, int(size_[1]))

    def create():
        """Renders the gradient rectangle."""
        mask = rounded_rect((b, h), radius, (255, 255, 255, 255))
        x = np.linspace(0, 1, b)[:, None]
        color = np.empty((b, h, 3), np.uint8)
        for i in range(3):
            color[..., i] = (left[i] + (right[i] - left[i]) * x).astype(np.uint8)
        area = pygame.Surface((b, h), pygame.SRCALPHA)
        pygame.surfarray.blit_array(area, color)
        pygame.surfarray.pixels_alpha(area)[...] = pygame.surfarray.array_alpha(mask)
        return area

    return _cache(("gradient", b, h, radius, tuple(left), tuple(right)), create)


def glow(radius: int, color, strength: float = 0.5) -> pygame.Surface:
    """Soft round glow of the given color."""
    radius = max(2, int(radius))

    def create():
        """Renders the glow."""
        d = radius * 2
        yy, xx = np.mgrid[0:d, 0:d]
        r = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / radius
        alpha = (np.clip(1 - r, 0, 1) ** 2.2 * 255 * strength).astype(np.uint8)
        area = pygame.Surface((d, d), pygame.SRCALPHA)
        area.fill((*color[:3], 0))
        pygame.surfarray.pixels_alpha(area)[...] = alpha.T
        return area

    return _cache(("glow", radius, tuple(color), strength), create)


def shadow(size_: tuple[int, int], radius: int, blur: int = 20, alpha: int = 130):
    """Soft shadow of a rectangle; returns the image and its bleed."""
    b, h = int(size_[0]), int(size_[1])
    bleed = blur * 2

    def create():
        """Renders the shadow."""
        area = pygame.Surface((b + bleed * 2, h + bleed * 2), pygame.SRCALPHA)
        pygame.draw.rect(area, (0, 0, 0, alpha), (bleed, bleed, b, h), border_radius=radius)
        small = pygame.transform.smoothscale(area, (max(1, area.get_width() // blur),
                                                       max(1, area.get_height() // blur)))
        return pygame.transform.smoothscale(small, area.get_size())

    return _cache(("shadow", b, h, radius, blur, alpha), create), bleed


def pokeball(area: pygame.Surface, middle, radius: int, top=(255, 92, 102), bottom=TEXT, line=(20, 20, 34)) -> None:
    """Draws the Pokeball logo."""
    radius = max(2, int(radius))

    def create():
        """Renders the Pokeball."""
        ss, d = 3, radius * 6
        c = d // 2
        ball = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(ball, bottom, (c, c), c)
        upper = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(upper, top, (c, c), c)
        ball.blit(upper, (0, 0), (0, 0, d, c))
        pygame.draw.circle(ball, line, (c, c), c, width=max(2, d // 14))
        pygame.draw.rect(ball, line, (0, c - d // 28, d, d // 14))
        pygame.draw.circle(ball, line, (c, c), d // 6)
        pygame.draw.circle(ball, bottom, (c, c), d // 10)
        return pygame.transform.smoothscale(ball, (radius * 2, radius * 2))

    image = _cache(("pokeball", radius, tuple(top), tuple(bottom), tuple(line)), create)
    area.blit(image, (middle[0] - radius, middle[1] - radius))


def pokeball_symbol(edge: int) -> pygame.Surface:
    """The Pokeball of the main menu as a square image (window and exe icon)."""
    image = pygame.Surface((edge, edge), pygame.SRCALPHA)
    pokeball(image, (edge // 2, edge // 2), edge // 2 - max(1, edge // 32))
    return image


def ico_data(edges=(16, 24, 32, 48, 64, 128, 256)) -> bytes:
    """Windows .ico with the Pokeball in all common sizes (PNG images in an ICO container)."""
    import io
    import struct

    images = []
    for edge in edges:
        buffer = io.BytesIO()
        pygame.image.save(pokeball_symbol(edge), buffer, "symbol.png")
        images.append((edge, buffer.getvalue()))
    entries, data, offset = b"", b"", 6 + 16 * len(images)
    for edge, png in images:
        entries += struct.pack("<BBBBHHII", edge % 256, edge % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return struct.pack("<HHH", 0, 1, len(images)) + entries + data


def background(size_: tuple[int, int], quiet: bool = False) -> pygame.Surface:
    """Diagonal night gradient; unless quiet it has glows and a Pokeball watermark."""
    b, h = int(size_[0]), int(size_[1])

    def create():
        """Renders the background."""
        y = np.linspace(0, 1, h)[None, :]
        x = np.linspace(0, 1, b)[:, None]
        t = 0.65 * y + 0.35 * x
        arr = np.empty((b, h, 3), np.uint8)
        for i in range(3):
            arr[..., i] = (BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t).astype(np.uint8)
        area = pygame.surfarray.make_surface(arr)
        if not quiet:
            s = h / 1080
            area.blit(glow(round(520 * s), ACCENT1, 0.35), (round(-260 * s), round(-300 * s)))
            area.blit(glow(round(560 * s), ACCENT2, 0.25), (b - round(700 * s), h - round(600 * s)))
            pokeball(area, (b - round(260 * s), round(300 * s)), round(420 * s),
                     (255, 255, 255, 10), (255, 255, 255, 6), (255, 255, 255, 14))
        return area.convert() if pygame.display.get_surface() else area

    return _cache(("background", b, h, quiet), create)


def card(area: pygame.Surface, rect, chosen: bool = False, radius: int | None = None,
          glowing: bool = True) -> None:
    """Glass card; when chosen with a purple-to-pink gradient, shadow and glow."""
    rect = pygame.Rect(rect)
    radius = radius if radius is not None else max(8, rect.height * 22 // 92)
    if chosen:
        if glowing:
            r = rect.width // 2
            area.blit(glow(r, ACCENT2, 0.18), (rect.centerx - r, rect.centery - r))
        blur = max(4, rect.height // 5)
        image, bleed = shadow(rect.size, radius, blur, 140)
        area.blit(image, (rect.x - bleed, rect.y - bleed + blur // 2))
        area.blit(gradient_rect(rect.size, radius), rect)
    else:
        area.blit(rounded_rect(rect.size, radius, MAP, 2, MAP_RAND), rect)


def panel(area: pygame.Surface, rect, radius: int | None = None, opaque: bool = True, opacity: int = 235) -> None:
    """Larger glass area for menus and messages over the game."""
    rect = pygame.Rect(rect)
    radius = radius if radius is not None else max(10, min(rect.width, rect.height) // 12)
    blur = max(6, min(rect.width, rect.height) // 14)
    image, margin = shadow(rect.size, radius, blur, 160 * opacity // 235)
    area.blit(image, (rect.x - margin, rect.y - margin + blur // 2))
    area.blit(rounded_rect(rect.size, radius, (22, 20, 48, opacity) if opaque else MAP, 2, (255, 255, 255, 40)), rect)


def outlined(area: pygame.Surface, rect, content: str, pixel: int, chosen: bool) -> None:
    """Primary button: pink outline, a gradient when chosen."""
    rect = pygame.Rect(rect)
    radius = max(8, rect.height * 22 // 78)
    if chosen:
        card(area, rect, True, radius)
        text(area, content, rect.center, pixel, (255, 255, 255), "center", weight="Bold")
    else:
        area.blit(rounded_rect(rect.size, radius, (255, 255, 255, 0), 3, (*ACCENT2, 200)), rect)
        text(area, content, rect.center, pixel, ACCENT2, "center", weight="Bold")


def badge(area: pygame.Surface, pos, nr: int, pixel: int, inverted: bool = False,
              anchor: str = "midleft") -> pygame.Rect:
    """Player badge "P1" in the player's color."""
    color = player_color(nr)
    b, h = round(pixel * 2.4), round(pixel * 1.75)
    image = rounded_rect((b, h), h * 3 // 10, (255, 255, 255, 255) if inverted else (*color, 255))
    rect = image.get_rect(**{anchor: pos})
    area.blit(image, rect)
    text(area, f"P{nr}", (rect.centerx, rect.centery + max(1, pixel // 16)), pixel,
         color if inverted else (20, 20, 30), "center", weight="Bold")
    return rect


def coplayer_figure(area: pygame.Surface, foot, tile: float, nr: int, half: bool = False) -> None:
    """A coplayer in the player's own world: shadow under the feet and a pen above it in the player color; half means it
    stands on the own tile (overlapping) and is drawn see-through."""
    x, y = foot
    opacity = 120 if half else 235
    shadow = pygame.Rect(0, 0, round(tile * 0.8), round(tile * 0.35))
    shadow.center = (round(x), round(y + tile * 0.3))
    level = pygame.Surface(shadow.size, pygame.SRCALPHA)
    pygame.draw.ellipse(level, (0, 0, 0, opacity // 2), level.get_rect())
    area.blit(level, shadow)
    pixel = max(6, round(tile * 0.42))
    b, h = max(round(pixel * 2.6), round(tile)), round(tile * 0.25 + tile * 0.9 + pixel * 1.9)
    level = pygame.Surface((b, h), pygame.SRCALPHA)
    header_y = h - round(tile * 1.15)
    width = max(3, round(tile * 0.18))
    pygame.draw.polygon(level, (*player_color(nr), 255), [(b / 2 - width, header_y), (b / 2 + width, header_y),
                                                           (b / 2, h - 1)])
    badge(level, (b // 2, header_y + round(tile * 0.1)), nr, pixel, anchor="midbottom")
    level.set_alpha(opacity)
    area.blit(level, (round(x - b / 2), round(y + tile * 0.25) - h + 1))


def button(area: pygame.Surface, pos, label: str, pixel: int, anchor: str = "midleft") -> pygame.Rect:
    """Button symbol for hints: circle with letter, pill with word or a pair of arrows; "L/R" means two buttons."""
    if "/" in label.strip("/"):
        parts = label.split("/")
        gap = max(2, pixel // 6)
        probe = pygame.Surface((1, 1), pygame.SRCALPHA)
        width = sum(button(probe, (0, 0), t, pixel).width for t in parts) + gap * (len(parts) - 1)
        rect = pygame.Rect(0, 0, width, pixel)
        setattr(rect, anchor, pos)
        x = rect.x
        for part in parts:
            x = button(area, (x, rect.centery), part, pixel).right + gap
        return rect
    h = pixel
    if len(label) == 1 or label in ("<>", "^v"):
        b = h
    else:
        b = load_font(round(h * 0.42), "Bold").size(label)[0] + h * 2 // 3
    image = rounded_rect((b, h), h // 2, (255, 255, 255, 46))
    rect = image.get_rect(**{anchor: pos})
    area.blit(image, rect)
    if label == "<>":
        s = h // 5
        cx, cy = rect.center
        pygame.draw.polygon(area, TEXT, [(cx - s // 3, cy - s), (cx - s // 3, cy + s), (cx - s - s // 3, cy)])
        pygame.draw.polygon(area, TEXT, [(cx + s // 3, cy - s), (cx + s // 3, cy + s), (cx + s + s // 3, cy)])
    elif label == "^v":
        s = h // 5
        cx, cy = rect.center
        pygame.draw.polygon(area, TEXT, [(cx - s, cy - s // 3), (cx + s, cy - s // 3), (cx, cy - s - s // 3)])
        pygame.draw.polygon(area, TEXT, [(cx - s, cy + s // 3), (cx + s, cy + s // 3), (cx, cy + s + s // 3)])
    else:
        single = len(label) == 1
        text(area, label, (rect.centerx, rect.centery + 1), round(h * (0.52 if single else 0.4)), TEXT,
             "center", weight="Bold")
    return rect


def button_row(area: pygame.Surface, middle, entries: list[tuple[str, str]], k: int, pixel: int, padding: int,
               max_width: int | None = None) -> None:
    """Button hints centered around middle; whatever does not fit is dropped from the end."""
    if not entries:
        return
    max_width = max_width or area.get_width()
    height = k + 4
    buffer = pygame.Surface((max_width + 4 * k, height), pygame.SRCALPHA)
    x = width = 0
    for symbol, label in entries:
        r = button(buffer, (x, height // 2), symbol, k)
        r2 = text(buffer, label, (r.right + pixel // 2, height // 2 + 1), pixel, DIMMED, "midleft",
                  weight="Medium")
        if r2.right > max_width and width:
            break
        width, x = r2.right, r2.right + padding
    area.blit(buffer, (middle[0] - width // 2, middle[1] - height // 2), (0, 0, width, height))


def footer(area: pygame.Surface, entries: list[tuple[str, str]], y: int | None = None) -> None:
    """Button hints at the bottom center of the whole screen."""
    y = y if y is not None else area.get_height() - size(area, 56)
    button_row(area, (area.get_width() // 2, y), entries, size(area, 34), size(area, 26),
               size(area, 44))


def title(area: pygame.Surface, content: str, subtitle: str | None = None, x: int | None = None) -> None:
    """Screen title with optional subtitle."""
    x = x if x is not None else size(area, 200)
    text(area, content, (x, size(area, 110)), size(area, 72), TEXT, "midleft", weight="ExtraBold")
    if subtitle:
        text(area, subtitle, (x + size(area, 4), size(area, 172)), size(area, 28), DIMMED,
             "midleft", weight="Medium")


def hint(area: pygame.Surface, content: str) -> None:
    """Hint text at the bottom center."""
    text(area, content, (area.get_width() // 2, area.get_height() - size(area, 40)),
         size(area, 26), DIMMED, "midbottom", weight="Medium")


def draw_menu(area: pygame.Surface, menu, rect, pixel: int, map_height: int | None = None,
                  gap: int | None = None, middle: bool = False) -> None:
    """Draws the entries as stacked cards."""
    rect = pygame.Rect(rect)
    map_height = map_height or round(pixel * 2.5)
    gap = gap if gap is not None else round(pixel * 0.75)
    height = len(menu.entries) * map_height + max(0, len(menu.entries) - 1) * gap
    y = rect.top + max(0, (rect.height - height) // 2)
    for i, entry in enumerate(menu.entries):
        card_rect = pygame.Rect(rect.x, y, rect.width, map_height)
        chosen = i == menu.selection
        card(area, card_rect, chosen)
        content = shorten(entry, pixel, card_rect.width - pixel * 2)
        color = (255, 255, 255) if chosen else TEXT
        if middle:
            text(area, content, (card_rect.centerx, card_rect.centery + 1), pixel, color, "center")
        else:
            text(area, content, (card_rect.x + round(pixel * 0.95), card_rect.centery + 1), pixel, color, "midleft")
        y += map_height + gap


ON_WHITE = (70, 40, 120)


def slider(area: pygame.Surface, rect, percent: int, chosen: bool) -> None:
    """Volume bar: track with a filled part, purple to pink and white in the chosen row."""
    rect = pygame.Rect(rect)
    radius = rect.height // 2
    area.blit(rounded_rect(rect.size, radius, (255, 255, 255, 70 if chosen else 34)), rect)
    width = round(rect.width * max(0, min(100, percent)) / 100)
    if width >= rect.height:
        size_ = (width, rect.height)
        area.blit(rounded_rect(size_, radius, (255, 255, 255, 255)) if chosen else gradient_rect(size_, radius),
                     rect.topleft)


def toggle(area: pygame.Surface, right_middle, options: list[str], active: int, pixel: int,
               chosen: bool) -> pygame.Rect:
    """Pills side by side, right-aligned at right_middle; the active one is highlighted."""
    height, padding = round(pixel * 1.55), max(2, pixel // 4)
    widths = [load_font(pixel, "SemiBold").size(o)[0] + pixel for o in options]
    total = pygame.Rect(0, 0, sum(widths) + padding * (len(options) - 1), height)
    total.midright = right_middle
    x = total.x
    for i, (option, width) in enumerate(zip(options, widths)):
        pill = pygame.Rect(x, total.y, width, height)
        if i == active:
            image = rounded_rect(pill.size, height // 2, (255, 255, 255, 245)) if chosen else gradient_rect(pill.size,
                                                                                                         height // 2)
            color = ON_WHITE if chosen else (255, 255, 255)
        else:
            image = rounded_rect(pill.size, height // 2, (255, 255, 255, 0), 2, (255, 255, 255, 110 if chosen else 50))
            color = (235, 235, 255) if chosen else DIMMED
        area.blit(image, pill)
        text(area, option, (pill.centerx, pill.centery + 1), pixel, color, "center")
        x += width + padding
    return total


def switch(area: pygame.Surface, right_middle, on: bool, pixel: int, chosen: bool) -> pygame.Rect:
    """On/off switch: a pill with a round knob, right-aligned at right_middle."""
    height = round(pixel * 1.35)
    rect = pygame.Rect(0, 0, round(height * 1.9), height)
    rect.midright = right_middle
    if on:
        image = rounded_rect(rect.size, height // 2, (255, 255, 255, 245)) if chosen else gradient_rect(rect.size, height // 2)
    else:
        image = rounded_rect(rect.size, height // 2, (255, 255, 255, 70 if chosen else 34))
    area.blit(image, rect)
    button_r = height // 2 - max(2, height // 8)
    middle = (rect.right - height // 2 if on else rect.x + height // 2, rect.centery)
    color = ON_WHITE if on and chosen else (255, 255, 255) if on or chosen else DIMMED
    pygame.draw.aacircle(area, color, middle, button_r, 0)
    return rect


def dim(area: pygame.Surface, rect, alpha: int = 190) -> None:
    """Darkens a rectangle."""
    rect = pygame.Rect(rect)
    veil = pygame.Surface(rect.size, pygame.SRCALPHA)
    veil.fill((*VEIL, alpha))
    area.blit(veil, rect.topleft)


def spinner(area: pygame.Surface, middle, radius: int, time: float, color=ACCENT2) -> None:
    """Rotating loading arc."""
    rect = pygame.Rect(0, 0, radius * 2, radius * 2)
    rect.center = middle
    start = -time * 6.0
    pygame.draw.arc(area, (255, 255, 255, 40), rect, 0, 6.283, max(2, radius // 4))
    pygame.draw.arc(area, color, rect, start, start + 1.9, max(2, radius // 4))
