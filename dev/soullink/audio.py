"""Mixes the audio of all players and plays it through an SDL audio device."""
from __future__ import annotations

import ctypes
import threading
from pathlib import Path

import numpy as np


class Mixer:
    """Buffers int16 stereo per player and mixes the buffers when the output asks for samples."""

    def __init__(self, samplerate: int, target_ms: int = 60, max_ms: int = 150):
        """Creates the mixer with the sample rate and the target and maximum buffer fill in milliseconds."""
        self._target_bytes = samplerate * target_ms // 1000 * 4
        self._max_bytes = samplerate * max_ms // 1000 * 4
        self._buffer: dict[int, bytearray] = {}
        self._volume: dict[int, float] = {}
        self._lock = threading.Lock()

    def volume(self, nr: int, percent: int) -> None:
        """Sets the volume of one player in percent."""
        with self._lock:
            self._volume[nr] = max(0, min(100, percent)) / 100

    def feed(self, nr: int, data: bytes) -> None:
        """Appends samples of one player, trimming the buffer to the target size when it grows too large."""
        with self._lock:
            buffer = self._buffer.setdefault(nr, bytearray())
            buffer += data
            if len(buffer) > self._max_bytes:
                del buffer[: len(buffer) - self._target_bytes]

    def clear(self, nr: int) -> None:
        """Discards the buffered samples of one player."""
        with self._lock:
            self._buffer.pop(nr, None)

    def buffer_frames(self, nr: int) -> int:
        """Number of buffered stereo frames of one player."""
        with self._lock:
            return len(self._buffer.get(nr, b"")) // 4

    def fill(self, output) -> None:
        """Mixes the buffers into the output buffer, attenuating by 1/sqrt(n) when several players sound at once."""
        target = memoryview(output).cast("B")
        frames = target.nbytes // 4
        sum_ = np.zeros(frames * 2, np.int32)
        k = 0
        with self._lock:
            for nr, buffer in self._buffer.items():
                n = min(frames, len(buffer) // 4)
                if n:
                    part = np.frombuffer(buffer, np.int16, n * 2).astype(np.int32)
                    factor = self._volume.get(nr, 1.0)
                    sum_[: n * 2] += part if factor == 1.0 else np.rint(part * factor).astype(np.int32)
                    del buffer[: n * 4]
                    k += 1
        if k > 1:
            sum_ = np.rint(sum_ / np.sqrt(k))
        target[:] = np.clip(sum_, -32768, 32767).astype(np.int16).tobytes()


class _AudioSpec(ctypes.Structure):
    """ctypes mirror of SDL_AudioSpec."""
    _fields_ = [("freq", ctypes.c_int), ("format", ctypes.c_uint16), ("channels", ctypes.c_uint8),
                ("silence", ctypes.c_uint8), ("samples", ctypes.c_uint16), ("padding", ctypes.c_uint16),
                ("size", ctypes.c_uint32), ("callback", ctypes.c_void_p), ("userdata", ctypes.c_void_p)]


_SDL_INIT_AUDIO = 0x10
_AUDIO_S16LSB = 0x8010
_sdl = None


def _sdl_library():
    """The SDL2 library already loaded by pygame, because SDL keeps its state per library instance."""
    global _sdl
    if _sdl is None:
        import pygame

        lib = ctypes.CDLL(str(Path(pygame.__file__).parent / "SDL2.dll"))
        lib.SDL_OpenAudioDevice.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(_AudioSpec),
                                            ctypes.POINTER(_AudioSpec), ctypes.c_int]
        lib.SDL_OpenAudioDevice.restype = ctypes.c_uint32
        lib.SDL_QueueAudio.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
        lib.SDL_GetQueuedAudioSize.argtypes = [ctypes.c_uint32]
        lib.SDL_GetQueuedAudioSize.restype = ctypes.c_uint32
        lib.SDL_PauseAudioDevice.argtypes = [ctypes.c_uint32, ctypes.c_int]
        lib.SDL_CloseAudioDevice.argtypes = [ctypes.c_uint32]
        lib.SDL_GetError.restype = ctypes.c_char_p
        _sdl = lib
    return _sdl


class AudioOutput:
    """Queues mixed audio via SDL_QueueAudio; refill() is called once per frame from the main loop. No Python callback runs
    on the SDL audio thread, because the pygame AudioDevice deadlocked on close."""

    def __init__(self, mixer: Mixer, samplerate: int, target_ms: int = 80):
        """Opens the SDL audio device for the mixer and starts playback."""
        self._sdl = _sdl_library()
        self._mixer = mixer
        self._target_bytes = samplerate * target_ms // 1000 * 4
        if self._sdl.SDL_InitSubSystem(_SDL_INIT_AUDIO) != 0:
            raise RuntimeError(self._sdl.SDL_GetError().decode("utf-8", "replace"))
        wish = _AudioSpec(freq=samplerate, format=_AUDIO_S16LSB, channels=2, samples=1024)
        receive = _AudioSpec()
        self._device = self._sdl.SDL_OpenAudioDevice(None, 0, ctypes.byref(wish), ctypes.byref(receive), 0)
        if not self._device:
            raise RuntimeError(self._sdl.SDL_GetError().decode("utf-8", "replace"))
        self._sdl.SDL_PauseAudioDevice(self._device, 0)

    def refill(self) -> int:
        """Tops up the SDL queue to the target size and returns the number of frames queued."""
        if not self._device:
            return 0
        missing = self._target_bytes - self._sdl.SDL_GetQueuedAudioSize(self._device)
        frames = missing // 4
        if frames <= 0:
            return 0
        buffer = bytearray(frames * 4)
        self._mixer.fill(memoryview(buffer))
        data = (ctypes.c_char * len(buffer)).from_buffer(buffer)
        self._sdl.SDL_QueueAudio(self._device, data, len(buffer))
        return frames

    def close(self) -> None:
        """Closes the audio device."""
        if self._device:
            self._sdl.SDL_CloseAudioDevice(self._device)
            self._device = 0
