"""Worker part of the coplayer plugin: reads the player's position from RAM for every displayed frame."""
from __future__ import annotations

from pathlib import Path

from soullink.roms import code_from_file

from soullink.world import pack, world_reader


class WorldPart:
    """One reader from soullink.world per player; after_image() delivers the position as bytes (world.pack) for the slot."""

    def __init__(self, core, reader):
        """Creates the part for a core and a reader."""
        self.core = core
        self.reader = reader

    def ready(self) -> dict:
        """Reports which reader runs."""
        return {"reader": type(self.reader).__name__}

    def after_image(self) -> bytes | None:
        """The player's position as bytes after each displayed frame; None if there is none."""
        if not getattr(self.core, "image_active", True):
            return None
        return pack(self.reader.step(self.core.ram_blocks, self.core.read))


def create(core, job: dict, shared: dict) -> WorldPart | None:
    """Creates the part only for games with a reader; None for games roms.family does not know (not a Pokemon game)."""
    reader = world_reader(code_from_file(Path(job["rom"])) or "")
    return WorldPart(core, reader) if reader is not None else None
