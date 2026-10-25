"""Tests of the GBA link cable build and the netpacket interface."""
import ctypes as C
import shutil
import struct
import threading
import time

import pytest

from soullink import paths
from soullink.core.libretro import ENV_SET_NETPACKET_INTERFACE, NETWORK_ALL, Core, _NetworkCallbacks


def _endless_loop() -> bytes:
    """The smallest runnable GBA ROM: ARM `b .` at the entry point, the rest zeros."""
    rom = bytearray(0x8000)
    rom[0:4] = struct.pack("<I", 0xEAFFFFFE)
    rom[0xAC:0xB0] = b"TEST"
    return bytes(rom)


def _core_copy(tmp_path, nr: int) -> Core:
    """Core loaded from an own DLL copy for a player."""
    dir = tmp_path / f"p{nr}"
    dir.mkdir()
    dll = dir / f"mgba_libretro_{nr}.dll"
    shutil.copy2(paths.core_file("gba"), dll)
    rom = dir / "rom.gba"
    rom.write_bytes(_endless_loop())
    core = Core(dll, dir)
    core.load_game(rom)
    return core


def test_gba_two_cores_in_lockstep(tmp_path):
    """Two GBA cores run in lockstep with the link cable build."""
    cores = [_core_copy(tmp_path, nr) for nr in (1, 2)]
    assert all(k.can_link for k in cores)
    coordinator = cores[0].link_coordinator_new()
    assert coordinator
    images = [0, 0]
    results = [None, None]

    def run(i):
        """Runs one core in a thread."""
        core = cores[i]
        core.at_image = lambda rgbx: images.__setitem__(i, images[i] + 1)
        results[i] = core.link_connect(coordinator, i)
        for _ in range(120):
            core.step()
        core.link_disconnect()

    threads = [threading.Thread(target=run, args=(i,)) for i in (0, 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads)
    assert results == [True, True]
    assert min(images) >= 100
    for k in cores:
        k.end()
    cores[0].link_coordinator_free(coordinator)


def test_gba_paused_partner_does_not_block_permanently(tmp_path):
    """A paused partner does not hold the other core forever."""
    cores = [_core_copy(tmp_path, nr) for nr in (1, 2)]
    coordinator = cores[0].link_coordinator_new()
    for i, k in enumerate(cores):
        assert k.link_connect(coordinator, i)
    start = time.perf_counter()
    for _ in range(10):
        cores[0].step()
    assert time.perf_counter() - start < 5
    for k in cores:
        k.link_disconnect()
        k.end()


def test_netpacket_interface_is_in_the_binding(tmp_path):
    """The netpacket interface is part of the core binding."""
    core = _core_copy(tmp_path, 1)
    log = []

    @C.CFUNCTYPE(None, C.c_uint16, C.c_void_p, C.c_void_p)
    def start(own_id, send, query):
        """Records the start of the network."""
        log.append(("start", own_id))
        send = C.CFUNCTYPE(None, C.c_int, C.c_void_p, C.c_size_t, C.c_uint16)(send)
        data = C.create_string_buffer(b"core out")
        send(0, data, 8, NETWORK_ALL)
        C.CFUNCTYPE(None)(query)()

    @C.CFUNCTYPE(None, C.c_void_p, C.c_size_t, C.c_uint16)
    def receive(data, length, sender):
        """Records a received packet."""
        log.append(("receive", C.string_at(data, length), sender))

    @C.CFUNCTYPE(None)
    def stop():
        """Records the stop of the network."""
        log.append(("stop",))

    callbacks = _NetworkCallbacks(C.cast(start, C.c_void_p), C.cast(receive, C.c_void_p), C.cast(stop, C.c_void_p))
    assert core._environment(ENV_SET_NETPACKET_INTERFACE, C.addressof(callbacks))
    assert core.can_network
    sent, queried = [], []
    core.network_start(2, lambda data, target: sent.append((data, target)), lambda: queried.append(1))
    core.network_receive(b"from partner", 1)
    core.network_stop()
    assert log == [("start", 2), ("receive", b"from partner", 1), ("stop",)]
    assert sent == [(b"core out", NETWORK_ALL)] and queried == [1]
    core.end()


@pytest.mark.parametrize("nr, expected", [(1, "00:09:BF:53:4C:01"), (4, "00:09:BF:53:4C:04")])
def test_nds_mac_per_player(nr, expected):
    """Each player gets an own DS hardware address."""
    from soullink.session import nds_mac

    assert nds_mac(nr) == expected
