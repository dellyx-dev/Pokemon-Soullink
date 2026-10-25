"""Assigning controllers: press A one after another. Then everybody picks a key profile of the game system in their
card: default, a created one or a new one to name and bind; created ones can be deleted after a confirmation."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import pygame

from .. import layout
from ..input.wizard import STEPS, BindingWizard
from ..input.devices import KEYBOARD_ID, DeviceEvent, RawEvent, KeysEvent
from ..input.keys import CONFIRM, BACK_KEYS, Key
from ..input.key_binding import KeyboardBinding, KeyBinding
from ..input.assignment import Assignment
from ..profile import MAX_NAME, kind_of
from ..roms import game_name_from_file
from ..session import with_name
from ..language import t
from . import graphics
from .app import Screen
from .keyboard import VirtualKeyboard, draw_name_input
from .keys_menu import KeysMenu

NEW = "+"


def description(key: Key) -> str:
    """What the setup wizard asks to press (language key wizard.<key>)."""
    return t(f"wizard.{key.name.lower()}")


@dataclass
class Choice:
    """Profile choice of a joined player; phases are profile (list), name (name a new profile), bind (key menu), delete
(confirmation) and ready."""
    kind: str
    system: str
    phase: str = "profile"
    profile: str | None = None
    keyboard: VirtualKeyboard | None = None
    menu: KeysMenu | None = None


class AssignmentScreen(Screen):
    """Screen in which devices are assigned to players and key profiles chosen."""

    def __init__(self, app, session):
        """Creates the screen for a session."""
        super().__init__(app)
        self.session = session
        self.assignment = Assignment(len(session.player))
        self.cells = layout.compute(len(session.player), *app.size)
        self.game_names = [with_name(game_name_from_file(session.rom(sp.nr)) or "?", sp.name) for sp in session.player]
        self.wizard: tuple[str, BindingWizard] | None = None
        self.choice: dict[int, Choice] = {}
        self._raw_consumed = False
        self.time = 0.0

    def _options(self, choice: Choice) -> list:
        """Profile options of a choice: default, existing profiles and "new"."""
        return [None, *self.app.profile.names(choice.kind, choice.system), NEW]

    def _join(self, position: int, device: str) -> None:
        """A device joins as the next player."""
        info = self.session.player[position]
        choice = Choice(kind_of(device), info.system)
        old = info.keyboard if choice.kind == "keyboard" else info.keys
        if self.app.profile.exists(choice.kind, info.profile, info.system):
            choice.profile = info.profile
        elif old:
            choice.profile = self.app.profile.create(choice.kind, info.system,
                                                   info.name or t("new.player_nr", nr=info.nr), old)
            if choice.kind == "keyboard":
                info.keyboard = None
            else:
                info.keys = None
        self.choice[position] = choice

    def _bind(self, position: int, choice: Choice) -> None:
        """Starts binding keys for the player's profile."""
        info = self.session.player[position]
        ds = info.system == "nds"
        kind = KeyboardBinding if choice.kind == "keyboard" else KeyBinding
        binding = kind.from_dict(self.app.profile.binding(choice.kind, choice.profile, info.system), ds)
        choice.menu = KeysMenu(binding, ds, t("keys.title_profile", name=choice.profile),
                                 only_raw=choice.kind == "keyboard", nr=position + 1)
        choice.phase = "bind"

    def _binding_done(self, position: int, choice: Choice) -> None:
        """Finishes binding and marks the player ready."""
        info = self.session.player[position]
        self.app.profile.set_(choice.kind, choice.profile, info.system, choice.menu.binding.to_dict())
        choice.menu, choice.phase = None, "profile"

    def _delete(self, choice: Choice) -> None:
        """Deletes the chosen profile: its player moves to the next list entry, other players who had it fall back to the
        default."""
        name = choice.profile
        options = self._options(choice)
        following = options[options.index(name) + 1] if name in options else None
        self.app.profile.delete(choice.kind, name, choice.system)
        for other in self.choice.values():
            if other.kind == choice.kind and other.system == choice.system and other.profile == name:
                other.profile = following if other is choice else None
                if other.phase in ("ready", "delete"):
                    other.phase = "profile"
        choice.phase = "profile"

    def _choice_event(self, position: int, device: str, key: Key) -> None:
        """Handles a key in a player's profile choice."""
        choice = self.choice[position]
        if choice.phase == "ready":
            if key in BACK_KEYS:
                choice.phase = "profile"
        elif choice.phase == "name":
            result = choice.keyboard.event(key)
            name = choice.keyboard.text.strip()
            if result == "cancel" or (result == "done" and not name):
                choice.phase, choice.keyboard = "profile", None
            elif result == "done":
                choice.profile, choice.keyboard = self.app.profile.create(choice.kind, choice.system, name), None
                self._bind(position, choice)
        elif choice.phase == "bind":
            if choice.menu.event(key, time.monotonic()) == "done":
                self._binding_done(position, choice)
        elif choice.phase == "delete":
            if key in CONFIRM:
                self._delete(choice)
            elif key in BACK_KEYS:
                choice.phase = "profile"
        else:
            options = self._options(choice)
            i = options.index(choice.profile) if choice.profile in options else 0
            if key in (Key.LEFT, Key.UP, Key.RIGHT, Key.DOWN):
                choice.profile = options[(i + (1 if key in (Key.RIGHT, Key.DOWN) else -1)) % len(options)]
            elif key in CONFIRM or key == Key.START:
                if choice.profile == NEW:
                    choice.phase, choice.keyboard = "name", VirtualKeyboard("", MAX_NAME)
                else:
                    choice.phase = "ready"
            elif key == Key.NORTH and choice.profile not in (None, NEW):
                self._bind(position, choice)
            elif key == Key.WEST and choice.profile not in (None, NEW):
                choice.phase = "delete"
            elif key in BACK_KEYS:
                self.assignment.device_away(device)
                del self.choice[position]

    def _start_if_ready(self) -> None:
        """Starts the game when all players are assigned and ready."""
        if not self.assignment.done or any(self.choice.get(i) is None or self.choice[i].phase != "ready"
                                            for i in range(len(self.session.player))):
            return
        for i, info in enumerate(self.session.player):
            info.profile = self.choice[i].profile
        if self.session.dir is not None:
            self.session.save()
        from .game import GameScreen

        self.app.switch(GameScreen(self.app, self.session, list(self.assignment.player)))

    def raw(self, ev) -> None:
        """Handles raw pygame events (keyboard text)."""
        self._raw_consumed = False
        if ev.type != pygame.KEYDOWN:
            return
        position = self.assignment.player.index(KEYBOARD_ID) if KEYBOARD_ID in self.assignment.player else None
        choice = self.choice.get(position)
        if choice is not None and choice.phase == "bind" and choice.menu.waits is not None:
            if ev.key == pygame.K_ESCAPE:
                choice.menu.waits = None
            else:
                choice.menu.bind_with(ev.key)
            self._raw_consumed = True
        elif ev.key == pygame.K_ESCAPE:
            if self.wizard is not None:
                self.wizard = None
            elif choice is not None and choice.phase == "name":
                choice.phase, choice.keyboard = "profile", None
                self._raw_consumed = True
            elif choice is not None and choice.phase == "bind":
                self._raw_consumed = True
            else:
                self._back()

    def event(self, e) -> None:
        """Handles device and key events."""
        if self.wizard is not None:
            device, wizard = self.wizard
            if isinstance(e, RawEvent) and e.device == device and wizard.event(e.source):
                self.app.devices.binding_set(self.app.devices.guid(device), wizard.result)
                self.wizard = None
            return
        if isinstance(e, RawEvent) and self.app.devices.unknown(e.device):
            self.wizard = (e.device, BindingWizard())
        elif isinstance(e, DeviceEvent) and e.kind == "away":
            if e.device in self.assignment.player:
                self.choice.pop(self.assignment.player.index(e.device), None)
            self.assignment.device_away(e.device)
        elif isinstance(e, KeysEvent) and e.pressed:
            if e.device == KEYBOARD_ID and self._raw_consumed:
                self._raw_consumed = False
                return
            if e.device in self.assignment.player:
                self._choice_event(self.assignment.player.index(e.device), e.device, e.key)
            elif e.key in BACK_KEYS and not any(self.assignment.player):
                self._back()
                return
            elif self.assignment.event(e.device, e.key) == "joined":
                self._join(self.assignment.player.index(e.device), e.device)
            self._start_if_ready()

    def _back(self) -> None:
        """Returns to the start screen."""
        from .start import StartScreen

        self.app.switch(StartScreen(self.app))

    def update(self, dt: float) -> None:
        """Advances the animation time."""
        self.time += dt
        now = time.monotonic()
        for choice in self.choice.values():
            if choice.menu is not None:
                choice.menu.update(now)

    def draw(self, area) -> None:
        """Draws the assignment screen."""
        def g(n):
            """Scales a base size to the screen."""
            return graphics.size(area, n)

        next_ = self.assignment.player.index(None) if not self.assignment.done else None
        foot = g(110)
        cells = layout.compute(len(self.session.player), area.get_width(), area.get_height() - foot)
        for i, cell in enumerate(cells):
            rect = pygame.Rect(cell.cell.x, cell.cell.y, cell.cell.w, cell.cell.h).inflate(-g(36), -g(36))
            if i >= len(self.session.player):
                graphics.card(area, rect, radius=g(28))
                graphics.text(area, self.session.name, (rect.centerx, rect.centery), g(30), graphics.DIMMED, "center")
                continue
            nr = i + 1
            color = graphics.player_color(nr)
            device = self.assignment.player[i]
            choice = self.choice.get(i)
            is_next = i == next_
            graphics.card(area, rect, radius=g(28))
            if device is not None or is_next:
                margin = graphics.rounded_rect(rect.size, g(28), (0, 0, 0, 0), 3, (*color, 255 if device else 150))
                area.blit(margin, rect)
            pixel = max(g(18), min(g(40), rect.height // 10))
            if choice is not None and choice.phase == "bind":
                choice.menu.draw(area, rect, pixel, time.monotonic())
                continue
            if choice is not None and choice.phase == "name":
                self._draw_name(area, rect, nr, choice, pixel)
                continue
            if choice is not None:
                self._draw_choice(area, rect, nr, device, choice, pixel)
                continue
            top = rect.y + rect.height * 22 // 100
            badge_rect = graphics.badge(area, (rect.centerx, top), nr, round(pixel * 0.8), anchor="midbottom")
            graphics.text(area, graphics.shorten(self.game_names[i], pixel, rect.width - g(40)),
                        (rect.centerx, badge_rect.bottom + pixel // 2), pixel, graphics.TEXT, "midtop")
            middle_bottom = rect.y + rect.height * 62 // 100
            if is_next:
                pulse = 0.5 + 0.5 * math.sin(self.time * 5)
                large = round(pixel * (1.25 + 0.1 * pulse))
                k = round(large * 1.15)
                width = graphics.load_font(large, "Bold").size(t("assignment.press"))[0] + large // 3 + k
                r = graphics.text(area, t("assignment.press"), (rect.centerx - width // 2, middle_bottom), large,
                                graphics.TEXT, "midleft",
                                weight="Bold")
                graphics.button(area, (r.right + large // 3, middle_bottom - 2), "A", k)
            else:
                graphics.text(area, t("assignment.waits"), (rect.centerx, middle_bottom), round(pixel * 0.8),
                            graphics.DIMMED, "center",
                            weight="Medium")
        if self.wizard is not None:
            self._draw_wizard(area)
        elif self.assignment.done:
            graphics.footer(area, [("A", t("assignment.ready")), ("B", t("hint.back"))])
        else:
            graphics.footer(area, [("A", t("assignment.join")), ("B", t("hint.back"))])

    @staticmethod
    def _profile_name(profile: str | None) -> str:
        """Display name of a profile, "Default" for none."""
        if profile is None:
            return t("assignment.default")
        return t("assignment.new_profile") if profile == NEW else profile

    def _draw_choice(self, area, rect: pygame.Rect, nr: int, device: str, choice: Choice, pixel: int) -> None:
        """Joined card: compact header (badge and game in one line), below it the small profile list or the chosen one and
        "Ready", and hints at the bottom."""
        small = round(pixel * 0.62)
        large = round(pixel * 0.85)
        header_y = rect.y + round(pixel * 1.4)
        name = graphics.shorten(self.game_names[nr - 1], large, rect.width - 5 * pixel)
        badge_rect_w = round(pixel * 0.6 * 2.4)
        left = rect.centerx - (badge_rect_w + pixel // 3 + graphics.load_font(large).size(name)[0]) // 2
        badge_rect = graphics.badge(area, (left, header_y), nr, round(pixel * 0.6))
        graphics.text(area, name, (badge_rect.right + pixel // 3, header_y + 1), large, graphics.TEXT, "midleft")
        graphics.text(area, graphics.shorten(self.app.devices.name(device), small, rect.width - 2 * pixel, "Medium"),
                    (rect.centerx, header_y + round(pixel * 1.05)), small, graphics.DIMMED, "center", weight="Medium")
        if choice.phase == "delete":
            y = rect.y + rect.height * 50 // 100
            graphics.text(area, graphics.shorten(t("assignment.delete_question", name=choice.profile), large,
                                                rect.width - 2 * pixel, "Bold"),
                        (rect.centerx, y), large, graphics.TEXT, "center", weight="Bold")
            graphics.text(area, graphics.shorten(t("assignment.delete_sure"), small, rect.width - 2 * pixel, "Medium"),
                        (rect.centerx, y + round(pixel * 1.1)), small, graphics.DIMMED, "center", weight="Medium")
            buttons = [("A", t("assignment.delete")), ("B", t("hint.cancel"))]
        elif choice.phase == "ready":
            y = rect.y + rect.height * 55 // 100
            graphics.text(area, graphics.shorten(f"{t('assignment.profile')}: {self._profile_name(choice.profile)}", small,
                                                rect.width - 2 * pixel, "Medium"),
                        (rect.centerx, y), small, graphics.TEXT, "center", weight="Medium")
            y += round(pixel * 1.3)
            hook = pygame.Rect(0, 0, pixel, pixel)
            width = hook.width + pixel // 3 + graphics.load_font(pixel, "Bold").size(t("assignment.ready"))[0]
            hook.midleft = (rect.centerx - width // 2, y)
            pygame.draw.circle(area, graphics.player_color(nr), hook.center, pixel // 2)
            pygame.draw.lines(area, (20, 20, 30), False,
                              [(hook.x + pixel * 0.27, hook.centery),
                               (hook.x + pixel * 0.45, hook.centery + pixel * 0.18),
                               (hook.x + pixel * 0.75, hook.centery - pixel * 0.2)], max(2, pixel // 8))
            graphics.text(area, t("assignment.ready"), (hook.right + pixel // 3, y), pixel, graphics.OK, "midleft",
                        weight="Bold")
            buttons = [("B", t("assignment.not_ready"))]
        else:
            self._draw_profile_list(area, rect, nr, choice, pixel)
            buttons = [("A", t("assignment.create") if choice.profile == NEW else t("assignment.ready")),
                       ("^v", t("assignment.profile"))]
            if choice.profile not in (None, NEW):
                buttons += [("Y", t("assignment.bind")), ("X", t("assignment.delete"))]
            buttons.append(("B", t("hint.back")))
        graphics.button_row(area, (rect.centerx, rect.bottom - round(pixel * 1.1)), buttons, round(pixel * 0.8),
                          round(pixel * 0.55), pixel, rect.width - pixel)

    def _draw_profile_list(self, area, rect: pygame.Rect, nr: int, choice: Choice, pixel: int) -> None:
        """Small list under "Profile": default, created ones and "+ New profile"; with many profiles it scrolls."""
        small = round(pixel * 0.62)
        width = min(rect.width - 2 * pixel, round(pixel * 11))
        top = rect.y + round(pixel * 3.6)
        graphics.text(area, t("assignment.profile").upper(), (rect.centerx - width // 2 + pixel // 2, top),
                    max(9, round(pixel * 0.45)), graphics.DIMMED, "midleft", weight="SemiBold")
        height = round(pixel * 1.05)
        list_ = pygame.Rect(rect.centerx - width // 2, top + round(pixel * 0.55), width,
                            rect.bottom - round(pixel * 2.3) - top - round(pixel * 0.55))
        options = self._options(choice)
        selection = options.index(choice.profile) if choice.profile in options else 0
        visible = max(1, list_.height // height)
        first = max(0, min(selection - visible // 2, len(options) - visible))
        for k, profile in enumerate(options[first:first + visible], start=first):
            row = pygame.Rect(list_.x, list_.y + (k - first) * height, list_.width, height - max(2, pixel // 8))
            chosen = k == selection
            if chosen:
                graphics.card(area, row, True, radius=row.height // 3, glowing=False)
            color = (255, 255, 255) if chosen else graphics.ACCENT2 if profile == NEW else graphics.TEXT
            graphics.text(area, graphics.shorten(self._profile_name(profile), small, row.width - pixel, "SemiBold"),
                        (row.x + pixel // 2, row.centery + 1), small, color, "midleft", weight="SemiBold")
            if profile not in (None, NEW) and profile == self.session.player[nr - 1].profile:
                graphics.text(area, t("assignment.last"), (row.right - pixel // 2, row.centery + 1),
                            max(9, round(pixel * 0.45)), (235, 235, 255) if chosen else graphics.DIMMED, "midright",
                            weight="Medium")
        for top_rand, arrow in ((first > 0, -1), (first + visible < len(options), 1)):
            if top_rand:
                y = list_.y - pixel // 4 if arrow < 0 else list_.y + visible * height + pixel // 6
                s = max(3, pixel // 6)
                pygame.draw.polygon(area, graphics.DIMMED, [(list_.centerx - s, y), (list_.centerx + s, y),
                                                             (list_.centerx, y + arrow * s)])

    def _draw_name(self, area, rect: pygame.Rect, nr: int, choice: Choice, pixel: int) -> None:
        """New profile: name entry with the on-screen keyboard in the player's own card."""
        draw_name_input(area, rect, pixel, nr, t("assignment.profile_name"), choice.keyboard, self.time,
                              t("assignment.profile_example"))

    def _draw_wizard(self, area) -> None:
        """Draws the setup wizard for an unknown controller."""
        def g(n):
            """Scales a base size to the screen."""
            return graphics.size(area, n)

        device, wizard = self.wizard
        graphics.dim(area, area.get_rect(), 200)
        rect = pygame.Rect(0, 0, g(960), g(440))
        rect.center = area.get_rect().center
        graphics.panel(area, rect)
        graphics.text(area, t("wizard.title"), (rect.x + g(48), rect.y + g(64)), g(44), graphics.TEXT, "midleft",
                    weight="Bold")
        graphics.text(area, graphics.shorten(self.app.devices.name(device), g(26), rect.width - g(96), "Medium"),
                    (rect.x + g(48), rect.y + g(112)), g(26), graphics.DIMMED, "midleft", weight="Medium")
        key = wizard.current
        if key is not None:
            step = STEPS.index(key)
            graphics.text(area, t("wizard.press"), (rect.x + g(48), rect.y + g(200)), g(30), graphics.DIMMED,
                        "midleft",
                        weight="Medium")
            graphics.text(area, description(key), (rect.x + g(48), rect.y + g(252)), g(48), graphics.ACCENT2, "midleft",
                        weight="Bold")
            bar = pygame.Rect(rect.x + g(48), rect.y + g(330), rect.width - g(96), g(14))
            area.blit(graphics.rounded_rect(bar.size, g(7), (255, 255, 255, 30)), bar)
            filled = max(g(14), bar.width * step // len(STEPS))
            area.blit(graphics.gradient_rect((filled, bar.height), g(7)), bar)
            graphics.text(area, f"{step + 1} / {len(STEPS)}", (rect.right - g(48), rect.y + g(64)), g(28),
                        graphics.DIMMED, "midright", weight="Medium")
        graphics.text(area, t("wizard.applies_for_all"), (rect.x + g(48), rect.bottom - g(48)), g(24),
                    graphics.DIMMED, "midleft", weight="Medium")
        graphics.footer(area, [("ESC", t("hint.cancel"))])
