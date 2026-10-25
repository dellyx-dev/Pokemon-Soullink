"""Worker part of Link cable NDS: UDP between the players, netpacket of the core, real melonDS processes."""
import os
import shutil
import time
from pathlib import Path

import pytest

from conftest import plugin_module
from soullink import paths
from soullink.core.libretro import NETWORK_ALL

PLUGIN = Path(__file__).resolve().parents[1]
ID = "link_cable_nds"
ENTRY = {"id": ID, "dir": str(PLUGIN), "module": "worker", "slot": None}


class FakeCore:
    """Netpacket part of core.libretro.Core: remembers what the part starts, sends and receives."""

    def __init__(self, can=True):
        """Creates the fake core with or without netpacket support."""
        self.can_network, self.log, self.receive = can, [], []
        self.send = self.query = None

    def network_start(self, own_id, send, query):
        """Logs the start of the network."""
        self.log.append(("start", own_id))
        self.send, self.query = send, query

    def network_receive(self, data, sender):
        """Remembers a received packet."""
        self.receive.append((sender, data))

    def network_stop(self):
        """Logs the stop of the network."""
        self.log.append(("stop",))


def _wait(condition, seconds=2.0):
    """Polls until the condition holds or the time is over."""
    end = time.monotonic() + seconds
    while time.monotonic() < end and not condition():
        time.sleep(0.01)
    return condition()


def test_network_packets_between_two_players():
    """Packets travel between two players' networks."""
    network = plugin_module(ID, "network")
    a, b, foreign = network.Network(), network.Network(), network.Network()
    try:
        a.own_id, a.targets = 0, {1: b.port}
        b.own_id, b.targets = 1, {0: a.port}
        foreign.own_id, foreign.targets = 5, {1: b.port}
        a.send(b"hello", NETWORK_ALL)
        foreign.send(b"not connected", NETWORK_ALL)
        b.send(b"reply", 0)
        receive_b, receive_a = [], []
        end = time.monotonic() + 2
        while time.monotonic() < end and not (receive_b and receive_a):
            receive_b += b.fetch()
            receive_a += a.fetch()
            time.sleep(0.01)
        assert receive_b == [(0, b"hello")]
        assert receive_a == [(1, b"reply")]
    finally:
        for n in (a, b, foreign):
            n.close()


def test_part_connects_sends_and_fetches(worker_parts):
    """The part connects, sends and fetches packets."""
    ka, kb = FakeCore(), FakeCore()
    (ta, ea), (tb, eb) = worker_parts(ka, ID, nr=1), worker_parts(kb, ID, nr=2)
    port_a, port_b = ta.ready()[ID]["network_port"], tb.ready()[ID]["network_port"]
    assert port_a and port_b and port_a != port_b
    try:
        ta.before_image()
        ta.command(ID, {"id": 0, "targets": {1: port_b}})
        tb.command(ID, {"id": 1, "targets": {0: port_a}})
        ta.command(ID, {"id": 0, "targets": {1: port_b}})
        assert ka.log == [("start", 0)] and kb.log == [("start", 1)]
        assert ea == [("plugin", ID, True)] * 2 and eb == [("plugin", ID, True)]
        ka.send(b"from core a", NETWORK_ALL)
        assert _wait(lambda: tb.before_image() or kb.receive)
        assert kb.receive == [(0, b"from core a")]
        kb.send(b"from core b", 0)
        assert _wait(lambda: ka.query() or ka.receive)
        assert ka.receive == [(1, b"from core b")]
        ta.command(ID, None)
        assert ka.log[-1] == ("stop",) and ea[-1] == ("plugin", ID, False)
        kb.send(b"too late", 0)
        time.sleep(0.1)
        ta.before_image()
        assert ka.receive == [(1, b"from core b")]
    finally:
        ta.end()
        tb.end()
    assert ka.log.count(("stop",)) == 1 and kb.log[-1] == ("stop",)


def test_without_netpacket_no_part(worker_parts):
    """Without netpacket there is no part."""
    parts, events = worker_parts(FakeCore(can=False), ID)
    assert parts.active() == [] and parts.ready() == {} and events == []


def test_in_worker_no_pygame(worker_without_pygame):
    """The worker part does not import pygame."""
    assert worker_without_pygame(ID, {"can_network": True}, {"nr": 1}) == \
        "['link_cable_nds'] {'link_cable_nds': ['network_port']} False"


def test_real_nds_cores_connect_through_the_plugin(nds_rom, tmp_path):
    """Real DS cores connect through the plugin (needs a test ROM)."""
    from soullink.player import PlayerProcess

    if not paths.core_file("nds").exists():
        pytest.skip("melonDS DS core missing")
    player = []
    for nr in (1, 2):
        dir = tmp_path / f"p{nr}"
        dir.mkdir()
        try:
            os.link(nds_rom, dir / "rom.nds")
        except OSError:
            shutil.copyfile(nds_rom, dir / "rom.nds")
        player.append(PlayerProcess(nr, dir, False, system="nds", plugins=[ENTRY], base=tmp_path))
    events = []

    def wait(condition, seconds=60):
        """Polls until the condition holds or the time is over."""
        end = time.monotonic() + seconds
        while time.monotonic() < end and not condition():
            for sp in player:
                events.extend((sp.nr, e) for e in sp.fetch())
                sp.audio_fetch()
            time.sleep(0.005)
        return condition()

    def images():
        """Frame counters in shared memory."""
        return {sp.nr: (sp._memory.image_read() or (0,))[0] for sp in player}

    def reply(nr):
        """Replies of the worker part of a player."""
        return [e[2] for n, e in events if n == nr and e[:2] == ("plugin", ID)]

    try:
        for sp in player:
            sp.start()
        assert wait(lambda: all(sp.ready_info for sp in player)), [sp.error for sp in player]
        ports = {sp.nr - 1: sp.ready_info["plugins"][ID]["network_port"] for sp in player}
        assert all(ports.values()) and ports[0] != ports[1]
        assert not {"link", "network_port"} & set(player[0].ready_info)
        for sp in player:
            own = sp.nr - 1
            sp.plugin_command(ID, {"id": own, "targets": {k: v for k, v in ports.items() if k != own}})
        assert wait(lambda: reply(1) == [True] and reply(2) == [True], 10)
        before = images()
        wait(lambda: False, 2.0)
        after = images()
        assert all(after[nr] - before[nr] > 90 for nr in after), (before, after)
        for sp in player:
            sp.plugin_command(ID, None)
        assert wait(lambda: reply(1)[-1:] == [False] and reply(2)[-1:] == [False], 10)
        assert not [e for _, e in events if e[0] in ("plugin_error", "error")]
    finally:
        for sp in player:
            sp.end()
        for sp in player:
            (sp.dir / "rom.nds").unlink(missing_ok=True)
    assert all(sp.ended and not sp.error for sp in player)
