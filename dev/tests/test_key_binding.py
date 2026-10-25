"""Tests of key bindings."""

import itertools

from soullink.input.control import PlayerControl
from soullink.input.keys import Key
from soullink.input.key_binding import ONLY_DS, Function, KeyBinding, function_name


def test_default_gba():
    """The GBA default binding is as configured."""
    b = KeyBinding()
    assert b.function(Key.SOUTH) == Function.A and b.function(Key.EAST) == Function.B
    assert b.function(Key.L2) == Function.MENU and b.function(Key.STICK_R) == Function.FAST_FORWARD
    assert all(b.function(t) is None for t in (Key.WEST, Key.NORTH, Key.R2, Key.STICK_L))
    assert b.is_default


def test_default_ds_has_x_and_y_and_each_function_exactly_one_key():
    """The DS default has X and Y and gives each function exactly one key."""
    b = KeyBinding(ds=True)
    assert b.function(Key.SOUTH) == Function.A and b.function(Key.EAST) == Function.B
    assert b.function(Key.WEST) == Function.X and b.function(Key.NORTH) == Function.Y
    assert b.function(Key.L2) == Function.MENU and b.function(Key.R2) == Function.TOUCH
    assert b.function(Key.STICK_L) == Function.SWAP and b.function(Key.STICK_R) == Function.FAST_FORWARD
    assert all(len(b.keys_for(f)) == 1 for f in Function)
    assert b.is_default


def test_ds_functions_are_never_left_unbound():
    """DS functions are never left without a key."""
    b = KeyBinding(ds=True)
    for function, key in itertools.islice(itertools.product(Function, Key), 0, None, 7):
        b.bind(function, key)
        assert all(b.keys_for(f) for f in Function)


def test_names_per_system():
    """Function names differ per system."""
    assert function_name(Function.A, ds=False) == "GBA-A"
    assert function_name(Function.X, ds=True) == "DS-X"
    assert function_name(Function.FAST_FORWARD, ds=True) == "Fast-forward on/off"
    assert Function.X in ONLY_DS and Function.Y in ONLY_DS


def test_bind_swaps_on_conflict():
    """Binding a used key swaps the two functions."""
    b = KeyBinding()
    b.bind(Function.A, Key.EAST)
    assert b.function(Key.EAST) == Function.A
    assert b.function(Key.SOUTH) == Function.B
    assert b.keys_for(Function.A) == [Key.EAST]
    assert not b.is_default


def test_bind_on_free_key():
    """Binding a free key just moves the function."""
    b = KeyBinding()
    b.bind(Function.FAST_FORWARD, Key.WEST)
    assert b.function(Key.WEST) == Function.FAST_FORWARD
    assert b.function(Key.STICK_R) is None
    assert b.keys_for(Function.FAST_FORWARD) == [Key.WEST]


def test_save_and_load():
    """A binding survives serialization."""
    for ds in (False, True):
        b = KeyBinding(ds=ds)
        b.bind(Function.MENU, Key.SELECT)
        d = b.to_dict()
        assert KeyBinding.from_dict(d, ds).to_dict() == d
        assert KeyBinding.from_dict(None, ds).is_default
    assert KeyBinding.from_dict({"MISSING": "A", "L": "NONSENSE"}).is_default


def test_legacy_bindings_equal_the_default():
    """Bindings from the first sessions equal the default."""
    gba = {"SOUTH": "A", "L": "L", "R": "R", "START": "START", "SELECT": "SELECT", "UP": "UP", "DOWN": "DOWN",
           "LEFT": "LEFT", "RIGHT": "RIGHT", "EAST": "B", "STICK_R": "FAST_FORWARD", "L2": "MENU"}
    ds = {**gba, "WEST": "X", "R2": "TOUCH", "STICK_L": "SWAP", "NORTH": "Y"}
    assert KeyBinding.from_dict(gba).is_default
    assert KeyBinding.from_dict(ds, ds=True).is_default


def test_legacy_names_and_legacy_ds_binding():
    """Legacy function names and DS bindings still load."""
    old = {"SOUTH": "GBA_A", "EAST": "GBA_W", "WEST": "FAST_FORWARD", "NORTH": "MENU"}
    b = KeyBinding.from_dict(old)
    assert b.function(Key.SOUTH) == Function.A and b.function(Key.EAST) == Function.B
    assert KeyBinding.from_dict(old, ds=True).is_default


def test_control_uses_binding():
    """The player control uses the binding."""
    b = KeyBinding(ds=True)
    s = PlayerControl(b)
    s.event(Key.NORTH, True)
    s.event(Key.WEST, True)
    assert s.mask == (1 << 9) | (1 << 1)
    s.event(Key.STICK_R, True)
    assert s.fast_forward and s.mask == (1 << 9) | (1 << 1)


def test_custom_default_file_takes_priority(monkeypatch, tmp_path):
    """A custom default file takes priority over the bundled one."""
    import json

    import pygame

    from soullink.input.key_binding import KeyboardBinding, default_binding

    monkeypatch.setenv("SOULLINK_BASE", str(tmp_path))
    default_binding.cache_clear()
    try:
        assert KeyboardBinding().function(pygame.K_y) == Function.B
        assert KeyboardBinding().function(pygame.K_z) == Function.B
        own = {"controller": {"gba": {"A": "EAST", "B": ["SOUTH", "WEST"], "MENU": "R3?", "NONSENSE": "L"}}}
        (tmp_path / "default-keys.json").write_text(json.dumps(own), encoding="utf-8")
        default_binding.cache_clear()
        b = KeyBinding()
        assert b.function(Key.EAST) == Function.A and b.function(Key.WEST) == Function.B
        assert b.keys_for(Function.MENU) == [] and b.is_default
        assert KeyBinding(ds=True).function(Key.SOUTH) == Function.A
        (tmp_path / "default-keys.json").write_text("{broken", encoding="utf-8")
        default_binding.cache_clear()
        assert KeyBinding().function(Key.SOUTH) == Function.A
    finally:
        default_binding.cache_clear()
