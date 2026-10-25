"""Tests of the binding wizard."""

from soullink.input.wizard import STEPS, BindingWizard
from soullink.input.keys import Key


def test_steps_in_the_specified_order():
    """The wizard asks for the keys in the specified order."""
    assert list(STEPS) == [
        Key.UP, Key.DOWN, Key.LEFT, Key.RIGHT, Key.SOUTH, Key.EAST,
        Key.WEST, Key.NORTH, Key.L, Key.R, Key.START, Key.SELECT,
    ]


def test_twelve_sources_yield_a_binding():
    """Twelve distinct sources yield a binding."""
    a = BindingWizard()
    for i, key in enumerate(STEPS):
        assert a.current is key
        done = a.event({"type": "button", "index": i})
        assert done is (i == 11)
    assert a.current is None
    assert len(a.result) == 12
    assert a.result["UP"] == {"type": "button", "index": 0}
    assert a.result["SELECT"] == {"type": "button", "index": 11}
    assert set(a.result) == {t.name for t in STEPS}


def test_same_source_twice_stays_on_the_step():
    """The same source twice does not advance the step."""
    a = BindingWizard()
    assert a.event({"type": "hat", "index": 0, "value": [0, 1]}) is False
    assert a.current is Key.DOWN
    assert a.event({"type": "hat", "index": 0, "value": [0, 1]}) is False
    assert a.current is Key.DOWN
    assert a.event({"type": "hat", "index": 0, "value": [0, -1]}) is False
    assert a.current is Key.LEFT


def test_axis_directions_are_different_sources():
    """The two directions of an axis are different sources."""
    a = BindingWizard()
    a.event({"type": "axis", "index": 1, "direction": -1})
    a.event({"type": "axis", "index": 1, "direction": 1})
    assert a.current is Key.LEFT
    assert a.result == {
        "UP": {"type": "axis", "index": 1, "direction": -1},
        "DOWN": {"type": "axis", "index": 1, "direction": 1},
    }
