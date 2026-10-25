"""Tests of the audio mixer and output."""

import os
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np

from soullink import audio


def constant(frames: int, value: int) -> bytes:
    """Stereo samples of one constant value."""
    return np.full(frames * 2, value, np.int16).tobytes()


def fill(mixer: audio.Mixer, frames: int) -> np.ndarray:
    """Fills the mixer into a buffer and returns it as int16 samples."""
    output = memoryview(bytearray(frames * 4))
    mixer.fill(output)
    return np.frombuffer(output, np.int16)


def test_single_player_is_unchanged():
    """A single player's samples pass through unchanged."""
    m = audio.Mixer(65536)
    m.feed(1, constant(100, 1000))
    assert (fill(m, 100) == 1000).all()


def test_two_players_are_attenuated_by_square_root():
    """Two players are mixed and attenuated by 1/sqrt(2)."""
    m = audio.Mixer(65536)
    m.feed(1, constant(100, 1000))
    m.feed(2, constant(100, 1000))
    assert (np.abs(fill(m, 100).astype(int) - 1414) <= 1).all()


def test_output_is_clipped_to_int16():
    """The mix is clipped to the int16 range."""
    m = audio.Mixer(65536)
    m.feed(1, constant(100, 30000))
    m.feed(2, constant(100, 30000))
    assert (fill(m, 100) == 32767).all()
    m.feed(1, constant(100, -30000))
    m.feed(2, constant(100, -30000))
    assert (fill(m, 100) == -32768).all()


def test_no_data_silence():
    """Without data the output is silence."""
    m = audio.Mixer(65536)
    assert (fill(m, 100) == 0).all()


def test_partial_data_is_padded_with_silence():
    """Partial data is followed by silence."""
    m = audio.Mixer(65536)
    m.feed(1, constant(40, 1000))
    out = fill(m, 100)
    assert (out[:80] == 1000).all()
    assert (out[80:] == 0).all()
    assert m.buffer_frames(1) == 0


def test_fill_consumes_only_what_it_outputs():
    """Filling consumes only the samples that were output."""
    m = audio.Mixer(65536)
    m.feed(1, constant(100, 1000))
    fill(m, 30)
    assert m.buffer_frames(1) == 70


def test_clear():
    """Clearing a player empties its buffer."""
    m = audio.Mixer(65536)
    m.feed(1, constant(100, 1000))
    m.clear(1)
    assert m.buffer_frames(1) == 0
    assert (fill(m, 100) == 0).all()


def test_clearing_an_unknown_player_is_harmless():
    """Clearing an unknown player does nothing."""
    assert audio.Mixer(65536).buffer_frames(3) == 0


def test_overflow_discards_oldest_until_target():
    """Overflow discards the oldest samples down to the target size."""
    m = audio.Mixer(65536)
    frames = 65536 * 200 // 1000
    ramp = np.repeat(np.arange(frames, dtype=np.int16), 2)
    m.feed(1, ramp.tobytes())
    rest = m.buffer_frames(1)
    assert 0 < rest <= 3932
    out = fill(m, rest)
    assert out[0] == frames - rest
    assert out[-1] == frames - 1


def test_below_the_maximum_nothing_is_discarded():
    """Below the maximum nothing is discarded."""
    m = audio.Mixer(65536)
    m.feed(1, constant(65536 * 100 // 1000, 1))
    assert m.buffer_frames(1) == 6553


def test_audio_output_queues_data(monkeypatch):
    """The audio output queues mixed data on the device."""
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    m = audio.Mixer(65536)
    m.feed(1, constant(9000, 1000))
    output = audio.AudioOutput(m, 65536)
    try:
        pushed = output.refill()
        assert pushed > 0 and m.buffer_frames(1) == 9000 - pushed
        assert output.refill() == 0
        time.sleep(0.1)
        assert output.refill() > 0
    finally:
        output.close()


def test_close_does_not_hang():
    """Closing the audio output never hangs, even under load."""
    import subprocess
    import sys

    script = (
        "import os, time, random\n"
        "os.environ['SDL_AUDIODRIVER'] = 'dummy'\n"
        "from soullink.audio import Mixer, AudioOutput\n"
        "for i in range(300):\n"
        "    m = Mixer(65536); m.feed(1, b'\\x10\\x00' * 4096)\n"
        "    t = AudioOutput(m, 65536); t.refill()\n"
        "    time.sleep(random.uniform(0, 0.03)); t.refill(); t.close()\n"
        "print('OK')\n"
    )
    run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=90,
                          env={**os.environ, "PYGAME_HIDE_SUPPORT_PROMPT": "1"})
    assert run.returncode == 0 and "OK" in run.stdout, run.stderr[-2000:]


def test_mixer_volume_per_player():
    """The mixer applies a volume per player."""
    m = audio.Mixer(65536)
    m.feed(1, constant(100, 1000))
    m.feed(2, constant(100, 1000))
    m.volume(1, 50)
    m.volume(2, 0)
    values = fill(m, 100)
    assert abs(int(values[0]) - round(500 / 2 ** 0.5)) <= 1
