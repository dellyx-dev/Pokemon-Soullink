"""Tests of the background music."""

import subprocess
import sys
import wave

import pygame

from soullink.music import Music


def _wav(path, seconds=0.2):
    """Writes a short silent WAV file."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\0\0\0\0" * int(44100 * seconds))


def test_empty_folder_opens_no_mixer(tmp_path):
    """An empty music folder does not open the mixer."""
    m = Music(tmp_path / "Sound", 50)
    m.start()
    assert not m.runs and pygame.mixer.get_init() is None
    m.update()
    m.close()


def test_only_music_files(tmp_path):
    """Only music files are picked up."""
    for name in ("b.mp3", "a.OGG", "readme.txt", "c.wav"):
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in Music(tmp_path).files()] == ["a.OGG", "b.mp3", "c.wav"]


def test_plays_in_sequence_and_adjusts_volume(tmp_path):
    """Tracks play one after another and the volume can be adjusted."""
    for name in ("one", "two"):
        _wav(tmp_path / f"{name}.wav")
    (tmp_path / "broken.mp3").write_bytes(b"no music")
    script = (
        "import os, sys, time\n"
        "os.environ['SDL_AUDIODRIVER'] = 'dummy'\n"
        "import pygame\n"
        "from soullink.music import Music\n"
        f"m = Music(r'{tmp_path}', 30)\n"
        "m.start()\n"
        "assert m.runs and m.title in ('one', 'two'), m.title\n"
        "title = set()\n"
        "end = time.monotonic() + 3\n"
        "while time.monotonic() < end and len(title) < 2:\n"
        "    title.add(m.title); m.update(); time.sleep(0.02)\n"
        "assert {'one', 'two'} <= title | {m.title}, title\n"
        "m.volume_set(150); assert m.volume == 100\n"
        "assert abs(pygame.mixer.music.get_volume() - 1.0) < 0.01\n"
        "m.close(); assert not m.runs and pygame.mixer.get_init() is None\n"
        "print('ok')\n"
    )
    run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60,
                          cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    assert run.returncode == 0 and "ok" in run.stdout, run.stderr
