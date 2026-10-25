"""Helpers for screen tests: dummy app, fake session, fake player process and key events."""
from __future__ import annotations

import pygame

from conftest import fake_gba
from soullink.session import Session, Player


def dummy_app(monkeypatch, base):
    """App with a headless pygame window and test settings."""
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    monkeypatch.setenv("SOULLINK_BASE", str(base))
    from soullink.ui.app import App

    return App(base, window=True)


def fake_session(dir, count=2, codes=None, system="gba") -> Session:
    """A session with fake ROM files for the given player count."""
    from conftest import fake_nds

    codes = codes or (("CPUD", "IPKD", "IRBD", "IRAD") if system == "nds" else ("BPED", "BPRD", "AXVD", "AXPD"))
    dir.mkdir(parents=True, exist_ok=True)
    s = Session("Test ×2", "2026-10-19T19:00:00", "2026-10-19T19:00:00", 0, None, "",
                [Player(nr, "x.zip", None, nr == 1, system) for nr in range(1, count + 1)], dir)
    for nr in range(1, count + 1):
        s.player_dir(nr).mkdir(exist_ok=True)
        s.rom(nr).write_bytes((fake_nds if system == "nds" else fake_gba)(codes[nr - 1]))
    s.save()
    return s


def key(key):
    """Posts a key press event to pygame."""
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, mod=0, unicode="", scancode=0))


class FakeProcess:
    """Stand-in for PlayerProcess that only records commands."""
    instances: list["FakeProcess"] = []

    def __init__(self, nr, dir, audio, core=None, system="gba", plugins=None, group=None, **_):
        """Creates the fake like PlayerProcess."""
        self.nr, self.dir, self.audio_an, self.system = nr, dir, audio, system
        self.plugins, self.group = list(plugins or []), group
        self.slots: dict[int, bytes] = {}
        self.commands: list[tuple] = []
        self.pointer_values: tuple | None = None
        self.mask = 0
        self.alive = True
        self.ready_info = {"fps": 59.7275, "samplerate": 65536, "version": "0.11-test", "source": None,
                            "plugins": {p["id"]: {} for p in self.plugins}}
        self.saved_ids: set[int] = set()
        self._new = [("ready", self.ready_info)]
        FakeProcess.instances.append(self)

    def start(self):
        """Records the start."""
        self.commands.append(("start",))

    def input(self, mask):
        """Remembers the button mask."""
        self.mask = mask

    def pointer(self, x, y, pressed):
        """Remembers the touch pointer."""
        self.pointer_values = (x, y, pressed)

    def pause(self, on):
        """Records pause or resume."""
        self.commands.append(("pause", on))

    def tempo(self, factor):
        """Records a speed change."""
        self.commands.append(("tempo", factor))

    def ram_request(self):
        """Records a RAM request."""
        self.commands.append(("ram",))

    def plugin_command(self, plugin_id, data):
        """Records a command for a plugin worker part."""
        self.commands.append(("plugin", plugin_id, data))

    def plugin_disable(self, plugin_id):
        """Records that a plugin worker part is switched off."""
        self.commands.append(("plugin_disable", plugin_id))

    def plugin_data(self, slot):
        """Data of a plugin slot."""
        return self.slots.get(slot)

    def audio(self, on):
        """Records an audio switch."""
        self.commands.append(("audio", on))

    def save(self):
        """Records a save request and returns its id."""
        nr = sum(1 for b in self.commands if b[0] == "save") + 1
        self.commands.append(("save", nr))
        self.saved_ids.add(nr)
        return nr

    def fetch(self):
        """Returns and clears the prepared events."""
        new, self._new = self._new, []
        return new

    def audio_fetch(self):
        """No audio chunks."""
        return []

    def image(self):
        """No frame."""
        return None

    def end(self, timeout=5.0):
        """Records the end."""
        self.commands.append(("end",))
        self.alive = False

    def hat(self, kind):
        """Recorded commands of a kind."""
        return [b for b in self.commands if b[0] == kind]


def input(bs, device, key, pressed=True):
    """Like the app: keyboard first raw (real key code), then as a position key; controllers only as a position key."""
    from soullink.input.devices import KeysEvent
    from soullink.input.keys import KEYBOARD

    if device == "keyboard":
        code = next(k for k, t in KEYBOARD.items() if t == key)
        kind = pygame.KEYDOWN if pressed else pygame.KEYUP
        bs.raw(pygame.event.Event(kind, key=code, mod=0, unicode="", scancode=0))
    bs.event(KeysEvent(device, key, pressed))


DEVICES = ("keyboard", "c1", "c2", "c3")


def game_start(app, dir, count=2, system="gba", codes=None):
    """Game screen with fake processes (FakeProcess.instances reset), switched active and updated once."""
    from soullink.ui.game import GameScreen

    FakeProcess.instances = []
    bs = GameScreen(app, fake_session(dir, count, codes=codes, system=system), list(DEVICES[:count]),
                         process_factory=FakeProcess)
    app.switch(bs)
    bs.update(0.016)
    return bs


def active_plugin(app, plugin_id):
    """The loaded plugin object, the same across all games of the app."""
    return dict((i.id, p) for i, p in app.plugins.active())[plugin_id]


def press(bs, device, key, pressed=True):
    """Sends a key press or release of a device to the screen."""
    input(bs, device, key, pressed)
    bs.update(0.016)


def a_press(bs, device):
    """Presses and releases the A key (south)."""
    from soullink.input.keys import Key

    press(bs, device, Key.SOUTH)
    press(bs, device, Key.SOUTH, False)


def player_menu(bs, device):
    """Short press of the menu key (L2): opens the player menu of the player with this device and returns the player."""
    from soullink.input.keys import Key

    press(bs, device, Key.L2)
    press(bs, device, Key.L2, False)
    return next(s for s in bs.player if s.device == device)


def plugins_submenu(bs, device):
    """Player menu to "Plugins"; returns the player."""
    sp = player_menu(bs, device)
    sp.menu.selection = sp.menu_actions.index("plugins")
    a_press(bs, device)
    assert sp.submenu == "plugins"
    return sp
