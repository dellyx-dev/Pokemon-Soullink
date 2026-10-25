"""Trail of the player on the map: the partner Pokemon walks one step behind along exactly this path."""
from __future__ import annotations

import math

DISTANCE = 1.0
JUMP = 3.0
MIN_STEP = 0.02


class Trail:
    """Polyline of the player's last positions (map key, x, y in the shared numbering); tiles are the unit and DISTANCE is the gap behind the player, JUMP a move that counts as a warp and MIN_STEP the smallest recorded movement."""

    def __init__(self):
        """Starts with an empty trail."""
        self.map = None
        self.points: list[tuple[float, float]] = []
        self.facing_right = False
        self.last_change = -1.0

    def new(self, map_key, x: float, y: float, now: float) -> None:
        """Records the player's position; a map change or warp carries the trail along so the partner stays behind the player."""
        if not self.points:
            self.map, self.points = map_key, [(x, y + DISTANCE), (x, y)]
            return
        if map_key != self.map or math.dist(self.points[-1], (x, y)) > JUMP:
            vx, vy = x - self.points[-1][0], y - self.points[-1][1]
            self.map, self.points = map_key, [(px + vx, py + vy) for px, py in self.points]
            return
        last = self.points[-1]
        if math.dist(last, (x, y)) < MIN_STEP:
            return
        old = self.partner()
        self.points.append((x, y))
        self.last_change = now
        self._trim()
        new = self.partner()
        if abs(new[0] - old[0]) > 0.01:
            self.facing_right = new[0] > old[0]

    def _trim(self) -> None:
        """Cuts off the part of the trail that lies further back than DISTANCE + 1."""
        length = 0.0
        for i in range(len(self.points) - 1, 0, -1):
            length += math.dist(self.points[i], self.points[i - 1])
            if length > DISTANCE + 1:
                del self.points[:i - 1]
                return

    def partner(self) -> tuple[float, float] | None:
        """The point DISTANCE tiles (arc length) before the end of the trail."""
        if not self.points:
            return None
        rest = DISTANCE
        for i in range(len(self.points) - 1, 0, -1):
            a, b = self.points[i], self.points[i - 1]
            part = math.dist(a, b)
            if part >= rest:
                f = rest / part
                return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
            rest -= part
        return self.points[0]

    def walking(self, now: float) -> bool:
        """True while the player moved a moment ago."""
        return self.last_change >= 0 and now - self.last_change < 0.25
