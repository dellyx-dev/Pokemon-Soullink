"""Tests of the player process with real cores (need test ROMs)."""

import os
import shutil
import time
from pathlib import Path

import pytest

from soullink.core.libretro import pointer_value
from soullink.player import PlayerProcess


@pytest.fixture
def dir(tmp_path, test_rom):
    """Player folder with the test ROM."""
    p = tmp_path / "p1"
    p.mkdir()
    shutil.copyfile(test_rom, p / "rom.gba")
    return p


def _wait(sp, condition, timeout=20):
    """Polls until the condition holds or the timeout expires."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        sp.fetch()
        if condition():
            return True
        if not sp.alive and sp.ready_info is None:
            break
        time.sleep(0.02)
    return condition()


def _run_with_save(dir):
    """Runs a player until a save state exists and ends it."""
    sp = PlayerProcess(1, dir, audio=False)
    sp.start()
    try:
        assert _wait(sp, lambda: sp.ready_info is not None), sp.error
        nr = sp.save()
        assert _wait(sp, lambda: nr in sp.saved_ids), sp.error
        return sp.ready_info
    finally:
        sp.end()


def test_run(dir):
    """A player process runs and delivers frames."""
    sp = PlayerProcess(1, dir, audio=True)
    sp.start()
    try:
        assert _wait(sp, lambda: sp.ready_info is not None), sp.error
        assert sp.ready_info["samplerate"] == 65536
        assert sp.ready_info["source"] is None
        assert sp.ready_info["version"].startswith("0.11")
        time.sleep(1.0)
        area = sp.image()
        assert area is not None and area.get_size() == (240, 160)
        assert sum(map(len, sp.audio_fetch())) > 0
        nr = sp.save()
        assert _wait(sp, lambda: nr in sp.saved_ids)
        assert (dir / "state.state").stat().st_size > 100_000
    finally:
        sp.end()
    assert not sp.alive
    assert sp.exitcode == 0


def test_clock_matches_the_gba(dir):
    """The process runs at the GBA's frame rate."""
    sp = PlayerProcess(1, dir, audio=False)
    sp.start()
    try:
        assert _wait(sp, lambda: sp.ready_info is not None), sp.error
        time.sleep(0.5)
        start = sp._memory.image_read()[0]
        time.sleep(2.0)
        images = sp._memory.image_read()[0] - start
        assert 110 <= images <= 125, images
    finally:
        sp.end()


def test_second_start_loads_the_state(dir):
    """A second start loads the saved state."""
    _run_with_save(dir)
    info = _run_with_save(dir)
    assert info["source"].endswith("state.state")


def test_broken_state_falls_back_to_bak(dir):
    """A broken state file falls back to the backup."""
    _run_with_save(dir)
    _run_with_save(dir)
    (dir / "state.state").write_bytes(b"\x00" * 100)
    info = _run_with_save(dir)
    assert info["source"].endswith("state.state.bak")


@pytest.fixture
def ds_dir(tmp_path):
    """Player folder with the DS test ROM."""
    path = os.environ.get("SOULLINK_TEST_NDS")
    if not path or not Path(path).exists():
        pytest.skip("SOULLINK_TEST_NDS not set")
    p = tmp_path / "p1"
    p.mkdir()
    try:
        os.link(path, p / "rom.nds")
    except OSError:
        shutil.copyfile(path, p / "rom.nds")
    return p


def _cursor_at(area, x: int, y: int) -> bool:
    """melonDS DS draws the cursor as 4×4 inverted pixels from (x-2, y-2) to (x+1, y+1)."""
    square = {tuple(area.get_at((x + dx, y + dy))) for dx in range(-2, 2) for dy in range(-2, 2)}
    margin = {tuple(area.get_at(p)) for p in ((x - 4, y), (x + 3, y), (x, y - 4), (x, y + 3))}
    return len(square) == 1 and len(margin) == 1 and square != margin


def _wait_image(sp, condition, timeout=10):
    """Polls frames until the condition holds or the timeout expires."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        area = sp.image()
        if area is not None and condition(area):
            return area
        time.sleep(0.01)
    return None


def test_nds_without_rom_reports_the_missing_rom(tmp_path):
    """An NDS player without ROM reports the missing rom.nds."""
    sp = PlayerProcess(1, tmp_path, audio=False, system="nds")
    sp.start()
    try:
        assert _wait(sp, lambda: sp.error is not None)
        assert "rom.nds" in sp.error
    finally:
        sp.end()


def test_nds_run_and_pointer(ds_dir):
    """An NDS player runs and accepts the touch pointer."""
    sp = PlayerProcess(1, ds_dir, audio=False, system="nds", core_options={})
    sp.start()
    try:
        assert _wait(sp, lambda: sp.ready_info is not None, timeout=60), sp.error
        assert sp.ready_info["samplerate"] == 32728
        assert sp.ready_info["version"].startswith("1.4")
        for (x, y), (old_x, old_y) in (((80, 350), (170, 330)), ((170, 330), (80, 350))):
            sp.pointer(pointer_value(x + 0.5, 256), pointer_value(y + 0.5, 384), False)
            area = _wait_image(sp, lambda f: _cursor_at(f, x, y) and not _cursor_at(f, old_x, old_y))
            assert area is not None, (x, y)
            assert area.get_size() == (256, 384)
        nr = sp.save()
        assert _wait(sp, lambda: nr in sp.saved_ids), sp.error
        assert (ds_dir / "state.state").stat().st_size > 1_000_000
    finally:
        sp.end()
    assert sp.exitcode == 0


def test_nds_second_start_loads_the_state(ds_dir):
    """A second NDS start loads the saved state."""
    for _ in range(2):
        sp = PlayerProcess(1, ds_dir, audio=False, system="nds")
        sp.start()
        try:
            assert _wait(sp, lambda: sp.ready_info is not None, timeout=60), sp.error
            nr = sp.save()
            assert _wait(sp, lambda: nr in sp.saved_ids), sp.error
        finally:
            sp.end()
    assert sp.ready_info["source"].endswith("state.state")


def test_nds_melonds_cursor_is_off(ds_dir):
    """The melonDS cursor is switched off."""
    sp = PlayerProcess(1, ds_dir, audio=False, system="nds")
    sp.start()
    try:
        assert _wait(sp, lambda: sp.ready_info is not None, timeout=60), sp.error
        sp.pointer(pointer_value(80.5, 256), pointer_value(350.5, 384), False)
        assert _wait_image(sp, lambda f: _cursor_at(f, 80, 350), timeout=3) is None
    finally:
        sp.end()
