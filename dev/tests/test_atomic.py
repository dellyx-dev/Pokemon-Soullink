"""Tests of atomic file writing."""

from soullink.atomic import atomic_write


def test_first_write_without_bak(tmp_path):
    """The first write creates no backup file."""
    target = tmp_path / "a.sav"
    atomic_write(target, b"one")
    assert target.read_bytes() == b"one"
    assert not (tmp_path / "a.sav.bak").exists()


def test_second_write_keeps_a_backup(tmp_path):
    """The second write keeps the previous content as a .bak file."""
    target = tmp_path / "a.sav"
    atomic_write(target, b"one")
    atomic_write(target, b"two")
    assert target.read_bytes() == b"two"
    assert (tmp_path / "a.sav.bak").read_bytes() == b"one"
    assert not (tmp_path / "a.sav.tmp").exists()
