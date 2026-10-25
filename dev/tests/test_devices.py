"""Tests of device handling with fake controller and joystick modules."""

import pygame
import pytest

from soullink.input.bindings import Bindings
from soullink.input.devices import DeviceEvent, Devices, RawEvent, KeysEvent
from soullink.input.keys import Key

RAW_GUID = "03000000raw"


class FakeJoystick:
    """Fake pygame joystick."""

    def __init__(self, instance_id: int, name: str, guid: str):
        """Creates the fake with instance id, name and GUID."""
        self.instance_id, self.name, self.guid = instance_id, name, guid

    def get_instance_id(self) -> int:
        """The instance id."""
        return self.instance_id

    def get_name(self) -> str:
        """The joystick name."""
        return self.name

    def get_guid(self) -> str:
        """The GUID."""
        return self.guid


class FakeJoystickModule:
    """Fake pygame.joystick module."""

    def __init__(self, devices: dict[int, FakeJoystick]):
        """Creates the module with its devices."""
        self.devices = devices

    def Joystick(self, index: int) -> FakeJoystick:
        """The fake joystick for an index."""
        return self.devices[index]


class FakeController:
    """Fake SDL controller."""

    def __init__(self, index: int):
        """Creates the fake for an index."""
        self.id = index
        self.name = "Fake-Controller"


class FakeControllerModule:
    """Fake pygame._sdl2.controller module."""

    def __init__(self, controller_indices: set[int]):
        """Creates the module with the indices that count as controllers."""
        self.controller_indices = controller_indices

    def is_controller(self, index: int) -> bool:
        """True if the index is a controller."""
        return index in self.controller_indices

    def Controller(self, index: int) -> FakeController:
        """The fake controller for an index."""
        return FakeController(index)


def ev(type_: int, **attribute) -> pygame.event.Event:
    """Builds a pygame event."""
    return pygame.event.Event(type_, attribute)


@pytest.fixture
def path(tmp_path):
    """Path of the bindings file."""
    return tmp_path / "controller-bindings.json"


@pytest.fixture
def devices(path):
    """Devices with a keyboard, a controller and a raw joystick available."""
    joysticks = FakeJoystickModule({
        0: FakeJoystick(7, "Xbox-Pad", "030000xbox"),
        1: FakeJoystick(12, "Cheap-Pad", RAW_GUID),
        2: FakeJoystick(13, "Cheap-Pad", RAW_GUID),
    })
    return Devices(Bindings(path), FakeControllerModule({0}), joysticks)


@pytest.fixture
def controller(devices):
    """Devices with a connected controller."""
    assert devices.process(ev(pygame.CONTROLLERDEVICEADDED, device_index=0)) == [
        DeviceEvent("c7", "new")
    ]
    return devices


@pytest.fixture
def raw(devices):
    """Devices with a connected raw joystick."""
    assert devices.process(ev(pygame.JOYDEVICEADDED, device_index=1)) == [
        DeviceEvent("j12", "new")
    ]
    return devices


def button(devices, button, down=True):
    """Presses or releases a controller button and returns the resulting events."""
    type_ = pygame.CONTROLLERBUTTONDOWN if down else pygame.CONTROLLERBUTTONUP
    return devices.process(ev(type_, instance_id=7, button=button))


def stick(devices, axis, value):
    """Moves a controller axis and returns the resulting events."""
    return devices.process(ev(pygame.CONTROLLERAXISMOTION, instance_id=7, axis=axis, value=value))


def test_only_the_keyboard_exists_at_start(devices):
    """At start only the keyboard device exists."""
    assert devices.devices() == ["keyboard"]
    assert devices.name("keyboard") == "Keyboard"
    assert devices.guid("keyboard") is None
    assert not devices.unknown("keyboard")


def test_keyboard_x_down_and_up(devices):
    """Keyboard key X press and release produce events."""
    assert devices.process(ev(pygame.KEYDOWN, key=pygame.K_x)) == [
        KeysEvent("keyboard", Key.SOUTH, True)
    ]
    assert devices.pressed("keyboard") == {Key.SOUTH}
    assert devices.process(ev(pygame.KEYUP, key=pygame.K_x)) == [
        KeysEvent("keyboard", Key.SOUTH, False)
    ]
    assert devices.pressed("keyboard") == set()


def test_keyboard_esc_and_unbound_keys(devices):
    """Escape and unbound keyboard keys produce no key event."""
    assert devices.process(ev(pygame.KEYDOWN, key=pygame.K_ESCAPE)) == []
    assert devices.process(ev(pygame.KEYDOWN, key=pygame.K_w)) == []


def test_keyboard_q_is_the_left_stick_click(devices):
    """Keyboard Q acts as the left stick click."""
    assert devices.process(ev(pygame.KEYDOWN, key=pygame.K_q)) == [
        KeysEvent("keyboard", Key.STICK_L, True)
    ]


def test_keyboard_y_and_z_are_the_same_key(devices):
    """Y and Z are the same key on both keyboard layouts."""
    assert len(devices.process(ev(pygame.KEYDOWN, key=pygame.K_y))) == 1
    assert devices.process(ev(pygame.KEYDOWN, key=pygame.K_z)) == []
    assert devices.process(ev(pygame.KEYUP, key=pygame.K_y)) == []
    assert devices.process(ev(pygame.KEYUP, key=pygame.K_z)) == [
        KeysEvent("keyboard", Key.EAST, False)
    ]


def test_controller_add(controller):
    """A plugged-in controller is registered."""
    assert controller.devices() == ["keyboard", "c7"]
    assert controller.name("c7") == "Fake-Controller"
    assert controller.guid("c7") == "030000xbox"
    assert not controller.unknown("c7")


def test_controller_button_a(controller):
    """A controller button press produces its position key."""
    assert button(controller, pygame.CONTROLLER_BUTTON_A) == [KeysEvent("c7", Key.SOUTH, True)]
    assert button(controller, pygame.CONTROLLER_BUTTON_A, False) == [
        KeysEvent("c7", Key.SOUTH, False)
    ]


def test_stick_and_dpad(controller):
    """Stick and d-pad both produce direction keys."""
    left_x = pygame.CONTROLLER_AXIS_LEFTX
    assert stick(controller, left_x, -10000) == []
    assert stick(controller, left_x, -20000) == [KeysEvent("c7", Key.LEFT, True)]
    assert stick(controller, left_x, -30000) == []
    assert button(controller, pygame.CONTROLLER_BUTTON_DPAD_LEFT) == []
    assert stick(controller, left_x, 0) == []
    assert controller.pressed("c7") == {Key.LEFT}
    assert button(controller, pygame.CONTROLLER_BUTTON_DPAD_LEFT, False) == [
        KeysEvent("c7", Key.LEFT, False)
    ]


def test_stick_all_directions(controller):
    """The stick produces all four directions."""
    assert stick(controller, pygame.CONTROLLER_AXIS_LEFTX, 20000) == [
        KeysEvent("c7", Key.RIGHT, True)
    ]
    assert stick(controller, pygame.CONTROLLER_AXIS_LEFTY, -20000) == [
        KeysEvent("c7", Key.UP, True)
    ]
    assert stick(controller, pygame.CONTROLLER_AXIS_LEFTY, 20000) == [
        KeysEvent("c7", Key.UP, False), KeysEvent("c7", Key.DOWN, True)
    ]


def test_right_stick_is_no_direction(controller):
    """The right stick does not count as direction keys."""
    assert stick(controller, pygame.CONTROLLER_AXIS_RIGHTX, -30000) == []


def test_stick_clicks(controller):
    """Stick clicks produce their keys."""
    assert button(controller, pygame.CONTROLLER_BUTTON_LEFTSTICK) == [KeysEvent("c7", Key.STICK_L, True)]
    assert button(controller, pygame.CONTROLLER_BUTTON_RIGHTSTICK) == [KeysEvent("c7", Key.STICK_R, True)]
    assert button(controller, pygame.CONTROLLER_BUTTON_LEFTSTICK, False) == [
        KeysEvent("c7", Key.STICK_L, False)
    ]


def test_axis_values_of_right_stick_and_trigger(controller):
    """Axis values of the right stick and triggers are readable."""
    right_x, right_y = pygame.CONTROLLER_AXIS_RIGHTX, pygame.CONTROLLER_AXIS_RIGHTY
    trigger = pygame.CONTROLLER_AXIS_TRIGGERRIGHT
    assert controller.axis("c7", right_x) == 0
    assert stick(controller, right_x, -30000) == []
    assert stick(controller, right_y, 12345) == []
    assert stick(controller, trigger, 32767) == [KeysEvent("c7", Key.R2, True)]
    assert controller.axis("c7", right_x) == -30000
    assert controller.axis("c7", right_y) == 12345
    assert controller.axis("c7", trigger) == 32767
    stick(controller, right_x, 5)
    assert controller.axis("c7", right_x) == 5


def test_unknown_axis_is_zero(controller):
    """An unknown axis reads zero."""
    assert controller.axis("c99", pygame.CONTROLLER_AXIS_RIGHTX) == 0
    assert controller.axis("keyboard", pygame.CONTROLLER_AXIS_RIGHTX) == 0


def test_raw_joystick_axis_is_in_the_sdl_range(raw):
    """A raw joystick axis is reported in the SDL range."""
    raw.process(ev(pygame.JOYAXISMOTION, instance_id=12, axis=3, value=0.5))
    assert raw.axis("j12", 3) == 16384
    assert raw.axis("j12", 4) == 0


def test_controller_remove_releases_all_keys(controller):
    """Removing a controller releases all its keys."""
    button(controller, pygame.CONTROLLER_BUTTON_A)
    stick(controller, pygame.CONTROLLER_AXIS_LEFTX, -20000)
    events = controller.process(ev(pygame.CONTROLLERDEVICEREMOVED, instance_id=7))
    assert events[-1] == DeviceEvent("c7", "away")
    assert set(events[:-1]) == {
        KeysEvent("c7", Key.SOUTH, False), KeysEvent("c7", Key.LEFT, False)
    }
    assert controller.devices() == ["keyboard"]
    assert controller.pressed("c7") == set()


def test_joystick_events_of_controllers_are_ignored(controller):
    """Joystick events of devices known as controllers are ignored."""
    assert controller.process(ev(pygame.JOYDEVICEADDED, device_index=0)) == []
    assert controller.process(ev(pygame.JOYBUTTONDOWN, instance_id=7, button=0)) == []
    assert controller.process(ev(pygame.JOYDEVICEREMOVED, instance_id=7)) == []
    assert controller.devices() == ["keyboard", "c7"]


def test_unknown_device_events_ignored(devices):
    """Events of unknown devices are ignored."""
    assert button(devices, pygame.CONTROLLER_BUTTON_A) == []
    assert devices.process(ev(pygame.JOYBUTTONDOWN, instance_id=99, button=0)) == []
    assert devices.process(ev(pygame.CONTROLLERDEVICEREMOVED, instance_id=99)) == []


def test_raw_joystick_without_binding(raw):
    """A raw joystick without binding reports raw events."""
    assert raw.devices() == ["keyboard", "j12"]
    assert raw.name("j12") == "Cheap-Pad"
    assert raw.guid("j12") == RAW_GUID
    assert raw.unknown("j12")
    assert raw.process(ev(pygame.JOYBUTTONDOWN, instance_id=12, button=3)) == [
        RawEvent("j12", {"type": "button", "index": 3})
    ]
    assert raw.process(ev(pygame.JOYBUTTONUP, instance_id=12, button=3)) == []
    assert raw.pressed("j12") == set()


def test_raw_hat_and_axis(raw):
    """Raw hat and axis events are reported."""
    def joy(type_, **attribute):
        """Feeds a joystick event of the raw device."""
        return raw.process(ev(type_, instance_id=12, **attribute))

    assert joy(pygame.JOYHATMOTION, hat=0, value=(0, 1)) == [
        RawEvent("j12", {"type": "hat", "index": 0, "value": [0, 1]})
    ]
    assert joy(pygame.JOYHATMOTION, hat=0, value=(0, 0)) == []
    assert joy(pygame.JOYAXISMOTION, axis=1, value=-0.3) == []
    assert joy(pygame.JOYAXISMOTION, axis=1, value=-1.0) == [
        RawEvent("j12", {"type": "axis", "index": 1, "direction": -1})
    ]
    assert joy(pygame.JOYAXISMOTION, axis=1, value=-0.9) == []
    assert joy(pygame.JOYAXISMOTION, axis=1, value=0.0) == []
    assert joy(pygame.JOYAXISMOTION, axis=1, value=1.0) == [
        RawEvent("j12", {"type": "axis", "index": 1, "direction": 1})
    ]


def test_raw_joystick_after_binding(raw, path):
    """After a binding is stored a raw joystick yields keys."""
    binding = {"SOUTH": {"type": "button", "index": 3}}
    raw.binding_set(RAW_GUID, binding)
    assert not raw.unknown("j12")
    assert Bindings(path).for_(RAW_GUID) == binding
    assert raw.process(ev(pygame.JOYBUTTONDOWN, instance_id=12, button=3)) == [
        KeysEvent("j12", Key.SOUTH, True)
    ]
    assert raw.process(ev(pygame.JOYBUTTONUP, instance_id=12, button=3)) == [
        KeysEvent("j12", Key.SOUTH, False)
    ]


def test_raw_axis_with_binding(raw):
    """A raw axis with a binding yields keys."""
    raw.binding_set(RAW_GUID, {"LEFT": {"type": "axis", "index": 0, "direction": -1}})
    assert raw.process(ev(pygame.JOYAXISMOTION, instance_id=12, axis=0, value=-1.0)) == [
        KeysEvent("j12", Key.LEFT, True)
    ]
    assert raw.process(ev(pygame.JOYAXISMOTION, instance_id=12, axis=0, value=0.0)) == [
        KeysEvent("j12", Key.LEFT, False)
    ]


def test_hat_binding(raw):
    """A hat can be bound to keys."""
    raw.binding_set(RAW_GUID, {
        "UP": {"type": "hat", "index": 0, "value": [0, 1]},
        "RIGHT": {"type": "hat", "index": 0, "value": [1, 0]},
    })

    def hat(value):
        """Feeds a hat motion of the raw device."""
        return raw.process(ev(pygame.JOYHATMOTION, instance_id=12, hat=0, value=value))

    assert hat((0, 1)) == [KeysEvent("j12", Key.UP, True)]
    assert hat((1, 1)) == [KeysEvent("j12", Key.RIGHT, True)]
    assert set(hat((0, 0))) == {
        KeysEvent("j12", Key.UP, False), KeysEvent("j12", Key.RIGHT, False)
    }


def test_identical_controllers_share_a_binding(raw):
    """Identical controllers share one binding."""
    assert raw.process(ev(pygame.JOYDEVICEADDED, device_index=2)) == [DeviceEvent("j13", "new")]
    assert raw.unknown("j13")
    raw.binding_set(RAW_GUID, {"START": {"type": "button", "index": 9}})
    assert not raw.unknown("j12") and not raw.unknown("j13")
    assert raw.process(ev(pygame.JOYBUTTONDOWN, instance_id=13, button=9)) == [
        KeysEvent("j13", Key.START, True)
    ]


def test_binding_survives_a_restart(path, raw):
    """A stored binding survives a restart."""
    raw.binding_set(RAW_GUID, {"START": {"type": "button", "index": 9}})
    new = Devices(Bindings(path), FakeControllerModule(set()),
                  FakeJoystickModule({0: FakeJoystick(4, "Cheap-Pad", RAW_GUID)}))
    new.process(ev(pygame.JOYDEVICEADDED, device_index=0))
    assert not new.unknown("j4")


def test_raw_joystick_remove(raw):
    """Removing a raw joystick releases its keys."""
    raw.binding_set(RAW_GUID, {"SOUTH": {"type": "button", "index": 3}})
    raw.process(ev(pygame.JOYBUTTONDOWN, instance_id=12, button=3))
    assert raw.process(ev(pygame.JOYDEVICEREMOVED, instance_id=12)) == [
        KeysEvent("j12", Key.SOUTH, False), DeviceEvent("j12", "away")
    ]
    assert raw.devices() == ["keyboard"]


def test_triggers_are_keys(controller):
    """Triggers act as the keys L2 and R2."""
    right = pygame.CONTROLLER_AXIS_TRIGGERRIGHT
    assert stick(controller, right, 10000) == []
    assert stick(controller, right, 30000) == [KeysEvent("c7", Key.R2, True)]
    assert stick(controller, right, 0) == [KeysEvent("c7", Key.R2, False)]
    assert stick(controller, pygame.CONTROLLER_AXIS_TRIGGERLEFT, 32767) == [KeysEvent("c7", Key.L2, True)]
