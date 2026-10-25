"""Tests of controller bindings and raw joystick evaluation."""

import json

from soullink.input.bindings import Bindings, RawState
from soullink.input.keys import Key

BINDING = {
    "UP": {"type": "hat", "index": 0, "value": [0, 1]},
    "RIGHT": {"type": "hat", "index": 0, "value": [1, 0]},
    "SOUTH": {"type": "button", "index": 1},
    "LEFT": {"type": "axis", "index": 0, "direction": -1},
    "DOWN": {"type": "axis", "index": 1, "direction": 1},
}


def test_unknown_guid(tmp_path):
    """An unknown GUID has no binding."""
    assert Bindings(tmp_path / "controller-bindings.json").for_("abc") is None


def test_set_and_reload(tmp_path):
    """A stored binding survives reloading."""
    path = tmp_path / "controller-bindings.json"
    Bindings(path).set_("abc", BINDING)
    assert Bindings(path).for_("abc") == BINDING
    assert json.loads(path.read_text(encoding="utf-8")) == {"abc": BINDING}


def test_set_is_atomic(tmp_path):
    """Storing a binding is written atomically."""
    path = tmp_path / "controller-bindings.json"
    bindings = Bindings(path)
    bindings.set_("abc", BINDING)
    bindings.set_("def", BINDING)
    assert path.with_name(path.name + ".bak").exists()
    assert not path.with_name(path.name + ".tmp").exists()
    assert Bindings(path).for_("abc") == BINDING


def test_broken_file_falls_back_to_bak(tmp_path):
    """A broken file falls back to the .bak copy."""
    path = tmp_path / "controller-bindings.json"
    bindings = Bindings(path)
    bindings.set_("abc", BINDING)
    bindings.set_("def", BINDING)
    path.write_text("{broken", encoding="utf-8")
    assert Bindings(path).for_("abc") == BINDING


def test_broken_file_without_bak(tmp_path):
    """A broken file without a backup yields no bindings."""
    path = tmp_path / "controller-bindings.json"
    path.write_text("{broken", encoding="utf-8")
    assert Bindings(path).for_("abc") is None


def test_raw_button():
    """A raw button maps to its bound key."""
    raw = RawState()
    assert raw.keys(BINDING) == set()
    raw.button(1, True)
    assert raw.keys(BINDING) == {Key.SOUTH}
    raw.button(1, False)
    assert raw.keys(BINDING) == set()


def test_raw_hat():
    """A raw hat direction maps to its bound key."""
    raw = RawState()
    raw.hat(0, (0, 1))
    assert raw.keys(BINDING) == {Key.UP}
    raw.hat(0, (1, 1))
    assert raw.keys(BINDING) == {Key.UP, Key.RIGHT}
    raw.hat(0, (0, 0))
    assert raw.keys(BINDING) == set()


def test_raw_axis_threshold():
    """A raw axis counts as pressed above the threshold."""
    raw = RawState()
    raw.axis(0, -10000)
    assert raw.keys(BINDING) == set()
    raw.axis(0, -20000)
    assert raw.keys(BINDING) == {Key.LEFT}
    raw.axis(0, 20000)
    assert raw.keys(BINDING) == set()
    raw.axis(1, 20000)
    assert raw.keys(BINDING) == {Key.DOWN}


def test_unknown_key_names_are_ignored():
    """Unknown key names in a binding are ignored."""
    raw = RawState()
    raw.button(1, True)
    assert raw.keys({"NONSENSE": {"type": "button", "index": 1}}) == set()
