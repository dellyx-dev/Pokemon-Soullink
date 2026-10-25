"""Sharp scaling of game frames and simple status symbols."""
from __future__ import annotations

import pygame

SYMBOLS = ("mute", "fast_forward", "link", "pause", "controller")


def between_factor(source: tuple[int, int], target: tuple[int, int]) -> int:
    """Nearest integer factor for the intermediate size, so 1.875x (DS) goes 2x first and then slightly down."""
    return max(1, round(min(target[0] / source[0], target[1] / source[1])))


class Scaler:
    """Scales with nearest neighbor to an integer multiple, then smoothly to the target size."""

    def __init__(self):
        """Creates the intermediate and target surface caches."""
        self._between: dict[tuple[int, int], pygame.Surface] = {}
        self._target: dict[tuple[int, int], pygame.Surface] = {}

    def scale(self, source: pygame.Surface, target: tuple[int, int]) -> pygame.Surface:
        """Returns the source scaled to the target size, reusing cached surfaces."""
        target = (int(target[0]), int(target[1]))
        sw, sh = source.get_size()
        k = between_factor((sw, sh), target)
        size = (sw * k, sh * k)
        between = self._between.get(size)
        if between is None:
            between = self._between[size] = pygame.Surface(size, 0, source)
        pygame.transform.scale(source, size, between)
        if size == target:
            return between
        area = self._target.get(target)
        if area is None:
            area = self._target[target] = pygame.Surface(target, 0, between)
        pygame.transform.smoothscale(between, target, area)
        return area


def draw_symbol(area: pygame.Surface, kind: str, rect: pygame.Rect, color=(235, 235, 235)) -> None:
    """Draws a status symbol (pause, fast_forward, mute, link, controller) into the rectangle."""
    r = pygame.Rect(rect)
    x, y, b, h = r
    if kind == "pause":
        width = max(2, b // 4)
        pygame.draw.rect(area, color, (x + b // 6, y, width, h))
        pygame.draw.rect(area, color, (x + b - b // 6 - width, y, width, h))
    elif kind == "fast_forward":
        half = b // 2
        for start in (x, x + half):
            pygame.draw.polygon(area, color, [(start, y), (start + half, y + h // 2), (start, y + h)])
    elif kind == "mute":
        pygame.draw.polygon(area, color, [(x, y + h // 3), (x + b // 4, y + h // 3), (x + b // 2, y),
                                             (x + b // 2, y + h), (x + b // 4, y + 2 * h // 3), (x, y + 2 * h // 3)])
        thickness = max(2, b // 10)
        pygame.draw.line(area, color, (x + 3 * b // 5, y + h // 4), (x + b, y + 3 * h // 4), thickness)
        pygame.draw.line(area, color, (x + 3 * b // 5, y + 3 * h // 4), (x + b, y + h // 4), thickness)
    elif kind == "link":
        thickness = max(2, b // 9)
        link = (round(b * 0.62), round(h * 0.4))
        pygame.draw.rect(area, color, (x, y + h // 6, *link), thickness, border_radius=link[1] // 2)
        pygame.draw.rect(area, color, (x + b - link[0], y + h - h // 6 - link[1], *link), thickness,
                         border_radius=link[1] // 2)
        pygame.draw.line(area, color, (x + b // 3, y + h * 2 // 3), (x + b * 2 // 3, y + h // 3), thickness)
    elif kind == "controller":
        thickness = max(2, b // 10)
        pygame.draw.rect(area, color, (x, y + h // 4, b, h // 2), thickness, border_radius=max(2, h // 6))
        pygame.draw.line(area, (220, 60, 60), (x, y), (x + b, y + h), thickness)
    else:
        raise ValueError(f"Unknown symbol: {kind}")
