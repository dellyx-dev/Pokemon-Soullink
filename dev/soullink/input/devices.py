"""Turns pygame events of the keyboard, SDL controllers and raw joysticks into the program's own events."""
from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from .bindings import Bindings, RawState
from .keys import CONTROLLER, STICK_THRESHOLD, KEYBOARD, Key

KEYBOARD_ID = "keyboard"

_STICK = {
    "LEFT": {"type": "axis", "index": pygame.CONTROLLER_AXIS_LEFTX, "direction": -1},
    "RIGHT": {"type": "axis", "index": pygame.CONTROLLER_AXIS_LEFTX, "direction": 1},
    "UP": {"type": "axis", "index": pygame.CONTROLLER_AXIS_LEFTY, "direction": -1},
    "DOWN": {"type": "axis", "index": pygame.CONTROLLER_AXIS_LEFTY, "direction": 1},
    "L2": {"type": "axis", "index": pygame.CONTROLLER_AXIS_TRIGGERLEFT, "direction": 1},
    "R2": {"type": "axis", "index": pygame.CONTROLLER_AXIS_TRIGGERRIGHT, "direction": 1},
}
_CONTROLLER_INPUT = (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP, pygame.CONTROLLERAXISMOTION)
_JOYSTICK_INPUT = (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP, pygame.JOYHATMOTION, pygame.JOYAXISMOTION)


@dataclass(frozen=True)
class KeysEvent:
    """The set of position keys pressed on a device changed."""
    device: str
    key: Key
    pressed: bool
    repeats: bool = False


@dataclass(frozen=True)
class DeviceEvent:
    """A device was plugged in or removed."""
    device: str
    kind: str


@dataclass(frozen=True)
class RawEvent:
    """Raw input of a joystick without a known binding, used by the setup wizard."""
    device: str
    source: dict


@dataclass
class _Device:
    """State of one connected input device."""
    kind: str
    name: str
    guid: str | None
    objects: tuple = ()
    raw: RawState = field(default_factory=RawState)
    pressed: set[Key] = field(default_factory=set)


class Devices:
    """Tracks all input devices with ids "keyboard", "c<instance_id>" (SDL controller) and "j<instance_id>" (raw joystick)."""

    def __init__(self, bindings: Bindings, controller_module=None, joystick_module=None):
        """Creates the tracker; the controller and joystick modules can be replaced for tests."""
        if controller_module is None:
            from pygame._sdl2 import controller as controller_module
        self._bindings = bindings
        self._controller = controller_module
        self._joystick = joystick_module or pygame.joystick
        self._devices: dict[str, _Device] = {KEYBOARD_ID: _Device("keyboard", "Keyboard", None)}

    def process(self, ev: pygame.event.Event) -> list:
        """Translates one pygame event into zero or more own events."""
        type_ = ev.type
        if type_ == pygame.CONTROLLERDEVICEADDED:
            return self._controller_new(ev.device_index)
        if type_ == pygame.JOYDEVICEADDED:
            return self._joystick_new(ev.device_index)
        if type_ == pygame.CONTROLLERDEVICEREMOVED:
            return self._away(f"c{ev.instance_id}")
        if type_ == pygame.JOYDEVICEREMOVED:
            return self._away(f"j{ev.instance_id}")
        if type_ in (pygame.KEYDOWN, pygame.KEYUP):
            if ev.key not in KEYBOARD:
                return []
            self._devices[KEYBOARD_ID].raw.button(ev.key, type_ == pygame.KEYDOWN)
            return self._difference(KEYBOARD_ID)
        if type_ in _CONTROLLER_INPUT:
            g = self._devices.get(f"c{ev.instance_id}")
            if g is None:
                return []
            if type_ == pygame.CONTROLLERAXISMOTION:
                g.raw.axis(ev.axis, ev.value)
            else:
                g.raw.button(ev.button, type_ == pygame.CONTROLLERBUTTONDOWN)
            return self._difference(f"c{ev.instance_id}")
        if type_ in _JOYSTICK_INPUT:
            gid = f"j{ev.instance_id}"
            g = self._devices.get(gid)
            if g is None:
                return []
            source = _raw_change(g.raw, ev)
            if self.unknown(gid):
                return [RawEvent(gid, source)] if source else []
            return self._difference(gid)
        return []

    def name(self, g: str) -> str:
        """Display name of a device, the id itself if unknown."""
        return self._devices[g].name if g in self._devices else g

    def guid(self, g: str) -> str | None:
        """SDL GUID of a device; None if unknown."""
        return self._devices[g].guid if g in self._devices else None

    def unknown(self, g: str) -> bool:
        """True for a raw joystick without any binding."""
        device = self._devices.get(g)
        return device is not None and device.kind == "joystick" and self._bindings.for_(device.guid) is None

    def pressed(self, g: str) -> set[Key]:
        """Position keys currently pressed on a device."""
        return set(self._devices[g].pressed) if g in self._devices else set()

    def axis(self, g: str, index: int) -> int:
        """Last value of the axis in the SDL range of +-32767, 0 if unknown."""
        return self._devices[g].raw.axes.get(index, 0) if g in self._devices else 0

    def binding_set(self, guid: str, binding: dict) -> None:
        """Stores the key binding for all devices with this GUID."""
        self._bindings.set_(guid, binding)

    def devices(self) -> list[str]:
        """Ids of all connected devices."""
        return list(self._devices)

    def _controller_new(self, index: int) -> list:
        """Registers a newly connected SDL controller."""
        controller = self._controller.Controller(index)
        joystick = self._joystick.Joystick(index)
        gid = f"c{joystick.get_instance_id()}"
        if gid in self._devices:
            return []
        self._devices[gid] = _Device("controller", controller.name, joystick.get_guid(), (controller, joystick))
        return [DeviceEvent(gid, "new")]

    def _joystick_new(self, index: int) -> list:
        """Registers a newly connected joystick that SDL does not know as controller."""
        if self._controller.is_controller(index):
            return []
        joystick = self._joystick.Joystick(index)
        gid = f"j{joystick.get_instance_id()}"
        if gid in self._devices:
            return []
        self._devices[gid] = _Device("joystick", joystick.get_name(), joystick.get_guid(), (joystick,))
        return [DeviceEvent(gid, "new")]

    def _away(self, gid: str) -> list:
        """Removes a disconnected device and reports its pressed keys as released."""
        g = self._devices.get(gid)
        if g is None or g.kind == "keyboard":
            return []
        del self._devices[gid]
        return [KeysEvent(gid, t, False) for t in Key if t in g.pressed] + [DeviceEvent(gid, "away")]

    def _keys(self, g: _Device) -> set[Key]:
        """Position keys currently pressed on a device."""
        if g.kind == "keyboard":
            return {KEYBOARD[k] for k in g.raw.buttons}
        if g.kind == "controller":
            return {CONTROLLER[k] for k in g.raw.buttons if k in CONTROLLER} | g.raw.keys(_STICK)
        binding = self._bindings.for_(g.guid)
        return g.raw.keys(binding) if binding else set()

    def _difference(self, gid: str) -> list:
        """Reports a change of the pressed keys of a device as an event, if there is one."""
        g = self._devices[gid]
        old, new = g.pressed, self._keys(g)
        g.pressed = new
        return [KeysEvent(gid, t, False) for t in Key if t in old - new] + [
            KeysEvent(gid, t, True) for t in Key if t in new - old
        ]


def _raw_change(raw: RawState, ev: pygame.event.Event) -> dict | None:
    """Applies a joystick event to the raw state and returns its source if it was a press."""
    if ev.type == pygame.JOYBUTTONDOWN:
        raw.button(ev.button, True)
        return {"type": "button", "index": ev.button}
    if ev.type == pygame.JOYBUTTONUP:
        raw.button(ev.button, False)
        return None
    if ev.type == pygame.JOYHATMOTION:
        old = raw.hats.get(ev.hat, (0, 0))
        raw.hat(ev.hat, ev.value)
        new = raw.hats[ev.hat]
        return {"type": "hat", "index": ev.hat, "value": list(new)} if new not in ((0, 0), old) else None
    old = raw.axes.get(ev.axis, 0)
    new = round(ev.value * 32768)
    raw.axis(ev.axis, new)
    for direction in (-1, 1):
        if new * direction > STICK_THRESHOLD >= old * direction:
            return {"type": "axis", "index": ev.axis, "direction": direction}
    return None
