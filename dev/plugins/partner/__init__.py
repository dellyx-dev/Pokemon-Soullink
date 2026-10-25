"""Partner plugin: the first Pokemon of the own team follows the player around (except in HeartGold/SoulSilver)."""
from __future__ import annotations

import time

import pygame

from soullink import world
from soullink.plugin.api import MenuEntry, Plugin
from soullink.roms import code_from_file, family

from .trail import Trail

Movement, FIGURE_TILE, WORLDS = world.Movement, world.FIGURE_TILE, world.WORLDS


def _possible_for(family_: str | None) -> bool:
    """True for a Pokemon world with an overworld reader; HeartGold/SoulSilver already has the partner."""
    return family_ in WORLDS and family_ != "hgss"


class PartnerPlugin(Plugin):
    """The worker part sends the own location with the first team Pokemon every frame; it is smoothed, the trail recorded and the party icon drawn one step behind in the game's pixel size with its feet on the player's ground line (gen 3 on the tile grid, NDS projected through the game camera)."""

    def __init__(self, api):
        """Creates the plugin without game data."""
        super().__init__(api)
        self.game = None
        self.families: dict[int, str | None] = {}
        self.movement: dict[int, Movement] = {}
        self.trails: dict[int, Trail] = {}
        self.show: dict[int, bool] = {}
        self.icons: dict = {}

    def fits(self, session) -> bool | str:
        """Only if at least one player plays a game with an overworld reader (not HeartGold/SoulSilver)."""
        if any(_possible_for(family(code_from_file(session.rom(s.nr)) or "")) for s in session.player):
            return True
        return self.api.t("no_game")

    def session_start(self, game) -> None:
        """Resets everything for a new game and loads the party icons of the possible players."""
        self.game = game
        numbers = game.player_numbers()
        self.families = {nr: game.player_info(nr)["family"] for nr in numbers}
        self.movement = {nr: Movement() for nr in numbers}
        self.trails = {nr: Trail() for nr in numbers}
        self.show = dict.fromkeys(numbers, True)
        self.icons = {}
        for nr in numbers:
            if self._possible(nr) and (icons := world.icons_load(game.player_info(nr)["rom"],
                                                                 self.families[nr])) is not None:
                self.icons[nr] = icons

    def session_end(self) -> None:
        """Releases the game and all per-player data."""
        self.game, self.icons, self.movement, self.trails, self.families, self.show = None, {}, {}, {}, {}, {}

    def _possible(self, nr: int) -> bool:
        """True if the player's game can show a partner."""
        return _possible_for(self.families.get(nr))

    def update(self, dt: float) -> None:
        """Per frame: feeds the worker locations into the movements and the trails."""
        if self.game is None:
            return
        now = time.monotonic()
        for nr, movement in self.movement.items():
            if self._possible(nr):
                movement.new(world.unpack(self.game.worker_data(nr)), now)
                pos = self._world_pos(nr, now)
                if pos is not None:
                    self.trails[nr].new(pos[0], pos[1], pos[2], now)

    def player_menu(self, nr: int) -> list[MenuEntry]:
        """The switch "Show partner" for players whose game can show one."""
        if not self._possible(nr):
            return []
        return [MenuEntry("show", self.api.t("show"), lambda: self._toggle(nr),
                          switch=lambda: self.show.get(nr, True))]

    def _toggle(self, nr: int) -> None:
        """Switches the partner display of a player on or off."""
        self.show[nr] = not self.show.get(nr, True)

    def _world_pos(self, nr: int, now: float) -> tuple[tuple, float, float] | None:
        """(map key, x, y) of the player, smoothed, in the shared numbering."""
        movement, family_ = self.movement.get(nr), self.families.get(nr)
        if movement is None or movement.location is None or family_ is None:
            return None
        key = world.shared(family_, movement.location.group, movement.location.number)
        if key is None:
            return None
        x, y = movement.position(now)
        return key[0], x + key[1], y + key[2]

    def draw_game_frame(self, area, nr: int, target, source) -> None:
        """Draws the partner over the game frame (GBA or the DS top screen) if it is switched on."""
        if source in ("gba", "top") and self.show.get(nr, False) and self._possible(nr):
            self.draw(area, nr, target, time.monotonic())

    def draw(self, area, nr: int, target: pygame.Rect, now: float) -> None:
        """Draws the partner into the game frame one step behind the player, only while the world is visible."""
        movement, trail, icons = self.movement.get(nr), self.trails.get(nr), self.icons.get(nr)
        mine = self._world_pos(nr, now)
        if mine is None or trail is None or icons is None or not movement.in_overworld or trail.map != mine[0]:
            return
        location = movement.location
        if location.kind in (0, world.EI, world.NDS_EI) or (partner := trail.partner()) is None:
            return
        dx, dy = partner[0] - mine[1], partner[1] - mine[2]
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return
        if location.camera is None:
            tile = target.width / 15
            ground = (target.x + (FIGURE_TILE[0] + 0.5 + dx) * tile,
                      target.y + (FIGURE_TILE[1] + 0.5 + dy) * tile - tile / 16)
        else:
            point = world.projection(location.camera, mine[1] + dx, location.height, mine[2] + dy)
            if point is None:
                return
            scale = target.width / 256
            tile = point[2] * scale
            ground = (target.x + point[0] * scale, target.y + point[1] * scale)
        beat = 0.14 if trail.walking(now) else 0.35
        image, resting = icons.image(location.kind, int(now / beat)), icons.image(location.kind, 0)
        if image is None or resting is None:
            return
        size = round(tile * 2)
        image = pygame.transform.scale(image, (size, size))
        feet = pygame.transform.scale(resting, (size, size)).get_bounding_rect().bottom
        if trail.facing_right:
            image = pygame.transform.flip(image, True, False)
        x, y = ground
        shadow = pygame.Surface((round(tile * 0.9), round(tile * 0.35)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 90), shadow.get_rect())
        area.blit(shadow, shadow.get_rect(center=(round(x), round(y - tile * 0.05))))
        area.blit(image, (round(x - size / 2), round(y - feet)))


def create(api):
    """Creates the plugin object."""
    return PartnerPlugin(api)
