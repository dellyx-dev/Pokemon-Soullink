"""Tests of the device-to-player assignment state machine."""

from soullink.input.keys import Key
from soullink.input.assignment import Assignment


def test_flow_three_players():
    """Three players join one after another and start together."""
    z = Assignment(3)
    assert z.player == [None, None, None]
    assert not z.done
    assert z.event("c1", Key.SOUTH) == "joined"
    assert z.player == ["c1", None, None]
    assert z.event("c1", Key.SOUTH) is None
    assert z.event("c2", Key.SOUTH) == "joined"
    assert z.player == ["c1", "c2", None]
    assert z.event("c2", Key.EAST) == "undo"
    assert z.player == ["c1", None, None]
    assert z.event("keyboard", Key.START) == "joined"
    assert z.player == ["c1", "keyboard", None]
    assert z.event("c3", Key.SOUTH) == "joined"
    assert z.player == ["c1", "keyboard", "c3"]
    assert z.done
    assert z.event("c1", Key.START) == "start"
    assert z.event("c9", Key.START) is None
    z.device_away("c1")
    assert z.player == [None, "keyboard", "c3"]
    assert not z.done
    assert z.event("c4", Key.SOUTH) == "joined"
    assert z.player == ["c4", "keyboard", "c3"]


def test_back_frees_the_last_joined_position():
    """Backing out frees the position that joined last."""
    z = Assignment(2)
    z.event("c1", Key.SOUTH)
    z.event("c2", Key.SOUTH)
    assert z.event("c1", Key.SELECT) == "undo"
    assert z.player == ["c1", None]


def test_undo_after_device_removed():
    """Undo still works after a device was removed."""
    z = Assignment(3)
    for g in ("c1", "c2", "c3"):
        z.event(g, Key.SOUTH)
    z.device_away("c1")
    z.event("c4", Key.SOUTH)
    assert z.player == ["c4", "c2", "c3"]
    assert z.event("c2", Key.SELECT) == "undo"
    assert z.player == [None, "c2", "c3"]


def test_start_before_done_does_nothing():
    """Start does nothing before all players are assigned."""
    z = Assignment(2)
    z.event("c1", Key.SOUTH)
    assert z.event("c1", Key.START) is None
    assert z.event("c2", Key.START) is None
    assert z.player == ["c1", None]


def test_other_keys_do_not_join():
    """Keys other than confirm do not make a device join."""
    z = Assignment(2)
    for key in (Key.UP, Key.EAST, Key.WEST, Key.NORTH, Key.L, Key.SELECT):
        assert z.event("c1", key) is None
    assert z.event("keyboard", Key.SELECT) is None
    assert z.player == [None, None]


def test_no_join_if_full():
    """Nobody joins once every position is taken."""
    z = Assignment(1)
    z.event("c1", Key.SOUTH)
    assert z.event("c2", Key.SOUTH) is None
    assert z.player == ["c1"]


def test_removing_an_unknown_device_is_harmless():
    """Removing a device that never joined changes nothing."""
    z = Assignment(2)
    z.device_away("c5")
    assert z.player == [None, None]
