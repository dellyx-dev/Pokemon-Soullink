"""Tests of the libretro binding with real cores (need test ROMs)."""

import os
import shutil
from pathlib import Path

import numpy as np
import pytest

from soullink import paths
from soullink.core.libretro import Core, pointer_value


@pytest.fixture
def core(tmp_path, test_rom):
    """A GBA core with the test ROM loaded."""
    rom = tmp_path / "rom.gba"
    shutil.copyfile(test_rom, rom)
    k = Core(paths.core_file(), tmp_path)
    k.load_game(rom)
    yield k
    k.end()


def test_av_info_and_version(core):
    """The core reports its video/audio info and version."""
    assert (core.av.width, core.av.height) == (240, 160)
    assert 59 < core.av.fps < 60
    assert core.av.samplerate == 65536
    assert core.version.startswith("0.11")


def test_image_and_audio(core):
    """Image and audio callbacks deliver data."""
    images, audio = [], []
    core.at_image = lambda a: images.append(a.copy())
    core.at_audio = audio.append
    core.input_mask = 1 << 3
    for _ in range(120):
        core.step()
    assert len(images) == 120
    assert images[-1].shape == (160, 240) and images[-1].dtype == np.uint32
    assert (images[-1] >> 24 == 0xFF).all()
    expected = 120 * 1097 * 4
    assert abs(sum(map(len, audio)) - expected) < expected * 0.05


def test_without_image_and_audio(core):
    """Without image and audio the core still runs."""
    images, audio = [], []
    core.at_image = images.append
    core.at_audio = audio.append
    core.image_active = core.audio_active = False
    for _ in range(10):
        core.step()
    assert images == [] and audio == []


def test_sram_and_state(core):
    """SRAM and state can be read and restored."""
    for _ in range(30):
        core.step()
    state = core.state()
    assert len(state) > 100_000
    assert core.state_load(state)
    assert not core.state_load(b"\x00" * 100)
    assert len(core.sram()) == 131072
    core.sram_set(b"\x00" * 10)
    assert core.sram()[:10] == b"\x00" * 10


@pytest.mark.parametrize("pixel, size, value", [
    (0, 256, -32767), (256, 256, 32767), (128, 256, 0), (192, 384, 0),
    (-5, 256, -32767), (300, 256, 32767), (-1e9, 384, -32767), (1e9, 384, 32767),
])
def test_pointer_value(pixel, size, value):
    """The pointer value is computed from the pixel."""
    assert pointer_value(pixel, size) == value


@pytest.mark.parametrize("size", [192, 256, 384])
def test_pointer_value_hits_the_pixel_center(size):
    """The pointer value hits the pixel center."""
    for p in range(size):
        assert (pointer_value(p + 0.5, size) + 32767) * size // 65534 == p


def test_pointer_status_without_core():
    """The pointer state is stored without a core."""
    k = Core.__new__(Core)
    k.input_mask, k.pointer_x, k.pointer_y, k.pointer_pressed = 0b1001, -100, 200, True
    pointer = 6
    assert [k._status(0, pointer, 0, i) for i in range(4)] == [-100, 200, 1, 0]
    assert k._status(1, pointer, 0, 0) == 0
    assert k._status(0, pointer, 1, 0) == 0
    k.pointer_pressed = False
    assert k._status(0, pointer, 0, 2) == 0
    assert k._status(0, 1, 0, 256) == 0b1001


A = 1 << 8
YES = (128.5, 275.5)


class _Ds:
    """Helper that runs a DS core and collects its frames."""

    def __init__(self, core: Core, system: Path):
        """Creates the helper for a core and system folder."""
        self.core, self.system, self.image = core, system, None
        core.at_image = self._image
        core.at_audio = lambda data: None

    def _image(self, rgbx):
        """Stores a copy of the latest frame."""
        self.image = rgbx.copy()

    def run(self, images: int) -> np.ndarray:
        """Runs the core for some frames and returns the last frame."""
        for _ in range(images):
            self.core.step()
        return self.image

    def tap(self, x: float, y: float, images: int = 10) -> None:
        """Taps the touch screen at a position for some frames."""
        self.core.pointer_x, self.core.pointer_y = pointer_value(x, 256), pointer_value(y, 384)
        self.core.pointer_pressed = True
        self.run(images)
        self.core.pointer_pressed = False


def _share_different(a: np.ndarray, b: np.ndarray) -> float:
    """Share of differing pixels in the bottom screen of two frames."""
    bottom_a, bottom_b = a[192:], b[192:]
    return float((bottom_a != bottom_b).mean())


@pytest.fixture(scope="module")
def ds(tmp_path_factory):
    """A DS core with the test ROM loaded."""
    path = os.environ.get("SOULLINK_TEST_NDS")
    if not path or not Path(path).exists():
        pytest.skip("SOULLINK_TEST_NDS not set")
    system = tmp_path_factory.mktemp("ds-system")
    core = Core(paths.core_file("nds"), system)
    d = _Ds(core, system)
    d.pointer_start = (core.pointer_x, core.pointer_y, core.pointer_pressed)
    core.load_game(Path(path))
    for i in range(4000):
        core.input_mask = A if 1200 <= i < 3700 and i % 50 < 4 else 0
        core.step()
    core.input_mask = 0
    d.question = core.state()
    yield d
    core.end()


def test_ds_av_info(ds):
    """The DS core reports its video info."""
    assert (ds.core.av.width, ds.core.av.height) == (256, 384)
    assert 59 < ds.core.av.fps < 60
    assert ds.core.av.samplerate == 32728
    assert ds.core.version.startswith("1.4")
    assert ds.pointer_start == (0, 0, False)


def test_ds_tap_on_yes(ds):
    """A DS tap on a dialog answer is recognized."""
    assert ds.core.state_load(ds.question)
    before = ds.run(10)
    assert _share_different(before, ds.run(310)) < 0.05

    assert ds.core.state_load(ds.question)
    before = ds.run(10)
    ds.tap(*YES)
    assert _share_different(before, ds.run(300)) > 0.5


def test_ds_tap_beside_a_button_does_nothing(ds):
    """A DS tap beside a button does nothing."""
    assert ds.core.state_load(ds.question)
    before = ds.run(10)
    ds.tap(128.5, 100.5)
    assert _share_different(before, ds.run(300)) < 0.05


def test_ds_state_save_and_load(ds):
    """A DS state can be saved and loaded."""
    assert ds.core.state_load(ds.question)
    ds.run(5)
    state = ds.core.state()
    assert len(state) > 1_000_000
    expected = ds.run(30).copy()
    ds.tap(*YES)
    ds.run(100)
    assert ds.core.state_load(state)
    assert _share_different(expected, ds.run(30)) < 0.01
    assert not ds.core.state_load(b"\x00" * 100)


def test_ds_save_through_save_ram(ds):
    """A DS game is saved through the save RAM."""
    assert len(ds.core.sram()) == 512 * 1024
    files = [p.relative_to(ds.system).as_posix() for p in ds.system.rglob("*") if p.is_file()]
    assert set(files) <= {"melonDS DS/wfcsettings.bin"}
    old = ds.core.sram()[:16]
    ds.core.sram_set(b"\x12" * 16)
    assert ds.core.sram()[:16] == b"\x12" * 16
    ds.core.sram_set(old)


def test_core_options_through_get_variable():
    """Core options are delivered through GET_VARIABLE."""
    import ctypes as C
    from soullink.core import libretro

    k = Core.__new__(Core)
    k._options = {b"melonds_show_cursor": b"disabled"}
    var = libretro._Variable(b"melonds_show_cursor", None)
    assert k._environment(libretro.ENV_GET_VARIABLE, C.addressof(var))
    assert var.value == b"disabled"
    other = libretro._Variable(b"mgba_skip_bios", None)
    assert not k._environment(libretro.ENV_GET_VARIABLE, C.addressof(other))
    assert other.value is None


def test_image_without_size_is_discarded():
    """A frame without size is discarded."""
    k = Core.__new__(Core)
    arrived = []
    k.image_active, k.at_image = True, arrived.append
    k._pixelformat = 1
    k._image(12345, 0, 0, 0)
    k._image(12345, 256, 0, 1024)
    assert arrived == []


def test_ram_blocks_gba(core):
    """GBA RAM blocks are readable."""
    core.step()
    blocks = core.ram_blocks()
    assert len(blocks[0x02000000]) == 256 * 1024 and len(blocks[0x03000000]) == 32 * 1024


def test_ram_blocks_ds(ds):
    """DS RAM blocks are readable."""
    assert len(ds.core.ram_blocks()[0x02000000]) == 4 * 1024 * 1024
