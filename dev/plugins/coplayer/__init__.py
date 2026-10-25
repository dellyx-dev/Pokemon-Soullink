"""Coplayer plugin: the other players in the own world, drawn as their first Pokemon or a stylus in the player color."""
from __future__ import annotations

import time

import pygame

from soullink.plugin.api import Setting, MenuEntry, Plugin
from soullink.roms import code_from_file, family
from soullink.ui import graphics

from soullink.world import FIGURE_TILE, WORLDS, Movement, NdsIcons, PokemonIcons, unpack, shared, icons_load, projection

DISPLAY, POKEMON, STYLUS = "display", "pokemon", "stylus"


def _world(family_: str | None) -> str | None:
    """World (map numbering) of a game family; None for unknown games."""
    return WORLDS.get(family_) if family_ else None


class CoplayerPlugin(Plugin):
    """The worker part (worker.py) sends the position of its player every frame; here it is smoothed (movement) and drawn
    over the other players' game frames."""

    def __init__(self, api):
        """Creates the plugin without game data."""
        super().__init__(api)
        self.game = None
        self.families: dict[int, str | None] = {}
        self.movement: dict[int, Movement] = {}
        self.show: dict[int, bool] = {}
        self.icons: dict[int, PokemonIcons | NdsIcons] = {}
        self.display = POKEMON

    def settings(self) -> list[Setting]:
        """The display setting (Pokemon or stylus)."""
        return [Setting(DISPLAY, self.api.t("display"), "selection", POKEMON, (POKEMON, STYLUS),
                            lambda value: self.api.t(f"display_{value}"))]

    def fits(self, session) -> bool | str:
        """Only if at least two players play the same world, since otherwise there would be nobody to see."""
        worlds = [_world(family(code_from_file(session.rom(s.nr)) or "")) for s in session.player]
        return True if any(w and worlds.count(w) >= 2 for w in worlds) else self.api.t("no_partner")

    def session_start(self, game) -> None:
        """Resets everything for a new game, because the plugin object survives across games."""
        self.game = game
        numbers = game.player_numbers()
        self.families = {nr: game.player_info(nr)["family"] for nr in numbers}
        self.movement = {nr: Movement() for nr in numbers}
        self.show = dict.fromkeys(numbers, True)
        self.display = game.setting(DISPLAY)
        self.icons = {}
        if self.display == POKEMON:
            for nr in numbers:
                if self._possible(nr) and (icons := icons_load(game.player_info(nr)["rom"],
                                                                 self.families[nr])) is not None:
                    self.icons[nr] = icons

    def session_end(self) -> None:
        """Releases memory (generation 3 icons hold the whole ROM); the core always ends a game before the next one starts."""
        self.game, self.icons, self.movement, self.families, self.show = None, {}, {}, {}, {}

    def update(self, dt: float) -> None:
        """Per frame: feeds the positions delivered by the workers into the movements."""
        if self.game is None:
            return
        now = time.monotonic()
        for nr, movement in self.movement.items():
            if self.families.get(nr) is not None:
                movement.new(unpack(self.game.worker_data(nr)), now)

    def _possible(self, nr: int) -> bool:
        """True if at least one other player has a world that matches the own one (gen 3, gen 4, gen 5)."""
        own = _world(self.families.get(nr))
        return own is not None and any(o != nr and _world(f) == own for o, f in self.families.items())

    def player_menu(self, nr: int) -> list[MenuEntry]:
        """Switch "show coplayers"; greyed out with a reason without a partner in the own world, and nothing without a
        Pokemon game."""
        if self.families.get(nr) is None:
            return []
        if not self._possible(nr):
            return [MenuEntry("show", self.api.t("show"), lambda: None, reason=self.api.t("no_partner"))]
        return [MenuEntry("show", self.api.t("show"), lambda: self._toggle(nr),
                             switch=lambda: self.show.get(nr, True))]

    def _toggle(self, nr: int) -> None:
        """Switches the display of coplayers on or off for a player."""
        self.show[nr] = not self.show.get(nr, True)

    def draw_game_frame(self, area, nr: int, target, source) -> None:
        """Draws the coplayers over the game frame of a player (GBA or the DS top screen)."""
        if source in ("gba", "top") and self.show.get(nr, False):
            self.draw(area, nr, target, time.monotonic())

    def _world_pos(self, nr: int, now: float) -> tuple[tuple, float, float] | None:
        """(map key, x, y) smoothed in the shared numbering."""
        movement, family_ = self.movement.get(nr), self.families.get(nr)
        if movement is None or movement.location is None or family_ is None:
            return None
        map_ = shared(family_, movement.location.group, movement.location.number)
        if map_ is None:
            return None
        x, y = movement.position(now)
        return map_[0], x + map_[1], y + map_[2]

    def draw(self, area, nr: int, target: pygame.Rect, now: float) -> None:
        """Draws the others on the same map relative to the own figure into the game frame `target` (GBA or upper DS
        screen), only while the own world is visible."""
        my = self._world_pos(nr, now)
        if my is None or not self.movement[nr].in_overworld:
            return
        camera = self.movement[nr].location.camera
        for other in self.movement:
            pos = self._world_pos(other, now) if other != nr else None
            if pos is None or pos[0] != my[0]:
                continue
            dx, dy = pos[1] - my[1], pos[2] - my[2]
            if abs(dx) > 12 or abs(dy) > 10:
                continue
            if camera is None:
                tile = target.width / 15
                foot = (target.x + (FIGURE_TILE[0] + 0.5 + dx) * tile, target.y + (FIGURE_TILE[1] + 0.5 + dy) * tile)
            else:
                point = projection(camera, pos[1], self.movement[other].location.height, pos[2])
                if point is None:
                    continue
                scale = target.width / 256
                tile = point[2] * scale
                foot = (target.x + point[0] * scale, target.y + point[1] * scale - tile * 0.35)
            half = abs(dx) < 0.5 and abs(dy) < 0.5
            if self.display == STYLUS or not self._draw_pokemon(area, other, foot, tile, half, now):
                graphics.coplayer_figure(area, foot, tile, other, half=half)

    def _draw_pokemon(self, area, other: int, foot, tile: float, half: bool, now: float) -> bool:
        """The first Pokemon of the other player's team walks in their place (party icon with two alternating frames,
        faster while walking, mirrored to the right) with their small badge above; False means there is no icon and the
        stylus is drawn instead."""
        icons, movement = self.icons.get(other), self.movement[other]
        clock = 0.14 if movement.runs(now) else 0.35
        image = icons.image(movement.location.kind, int(now / clock)) if icons and movement.location else None
        if image is None:
            return False
        size = round(tile * 2)
        image = pygame.transform.scale(image, (size, size))
        if movement.after_right:
            image = pygame.transform.flip(image, True, False)
        x, y = foot
        shadow = pygame.Surface((round(tile * 0.9), round(tile * 0.35)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 50 if half else 90), shadow.get_rect())
        area.blit(shadow, shadow.get_rect(center=(round(x), round(y + tile * 0.3))))
        if half:
            image.set_alpha(130)
        rect = image.get_rect(midbottom=(round(x), round(y + tile * 0.45)))
        area.blit(image, rect)
        graphics.badge(area, (rect.centerx, rect.y + round(tile * 0.35)), other, max(6, round(tile * 0.3)),
                         anchor="midbottom")
        return True


def create(api):
    """Creates the plugin object."""
    return CoplayerPlugin(api)
