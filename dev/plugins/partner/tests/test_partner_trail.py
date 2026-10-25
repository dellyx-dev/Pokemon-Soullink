"""Trail of the player: the partner walks one tile behind, also around corners, and does not jump along at warps."""
import importlib.util
import math
from pathlib import Path

_spec = importlib.util.spec_from_file_location("partner_trail", Path(__file__).resolve().parents[1] / "trail.py")
trail = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(trail)


def _is(point, x, y):
    """Asserts that the point equals (x, y)."""
    assert math.dist(point, (x, y)) < 1e-6, point


def test_start_partner_stands_one_tile_below_the_player():
    """At the start the partner stands one tile below the player."""
    t = trail.Trail()
    t.new("k", 5.0, 5.0, 0.0)
    _is(t.partner(), 5.0, 6.0)


def test_partner_follows_straight_one_tile_behind():
    """Walking straight, the partner stays exactly one tile behind and faces the walking direction."""
    t = trail.Trail()
    t.new("k", 5.0, 5.0, 0.0)
    for i in range(1, 21):
        t.new("k", 5.0 + i * 0.1, 5.0, i * 0.01)
    _is(t.partner(), 6.0, 5.0)
    assert t.facing_right is True and t.walking(0.1) and not t.walking(5.0)


def test_partner_takes_the_corner():
    """The partner follows the path around a corner."""
    t = trail.Trail()
    t.new("k", 0.0, 0.0, 0.0)
    for i in range(1, 6):
        t.new("k", i * 0.1, 0.0, 0.0)
    for i in range(1, 11):
        t.new("k", 0.5, i * 0.1, 0.0)
    _is(t.partner(), 0.5, 0.0)


def test_map_change_and_warp_carry_the_trail_along():
    """A map change or warp moves the trail with the player, so the partner stays behind."""
    t = trail.Trail()
    t.new("a", 5.0, 5.0, 0.0)
    for i in range(1, 21):
        t.new("a", 5.0, 5.0 - i * 0.1, 0.0)
    _is(t.partner(), 5.0, 4.0)
    t.new("b", 5.0, 40.0, 0.1)
    _is(t.partner(), 5.0, 41.0)
    t.new("b", 30.0, 10.0, 0.2)
    _is(t.partner(), 30.0, 11.0)


def test_trail_stays_short():
    """The recorded trail is trimmed to a few points."""
    t = trail.Trail()
    t.new("k", 0.0, 0.0, 0.0)
    for i in range(1, 500):
        t.new("k", i * 0.1, 0.0, 0.0)
    assert len(t.points) < 40
