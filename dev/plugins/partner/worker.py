"""Worker part of the partner plugin: reads the player's position and the first team Pokemon for every displayed frame."""
from __future__ import annotations

from pathlib import Path

from soullink import world
from soullink.roms import code_from_file


class PartnerPart:
    """One reader from soullink.world; after_image() delivers the location as bytes (world.pack) for the slot."""

    def __init__(self, core, reader):
        """Creates the part for a core and a reader."""
        self.core = core
        self.reader = reader

    def ready(self) -> dict:
        """Reports which reader runs."""
        return {"reader": type(self.reader).__name__}

    def after_image(self) -> bytes | None:
        """The packed location after each displayed frame; None while fast-forwarding."""
        if not getattr(self.core, "image_active", True):
            return None
        return world.pack(self.reader.step(self.core.ram_blocks, self.core.read))


def create(core, job: dict, shared: dict) -> PartnerPart | None:
    """Creates the part only for games with a reader, except HeartGold/SoulSilver where the Pokemon walks by itself."""
    code = code_from_file(Path(job["rom"])) or ""
    reader = world.world_reader(code)
    return PartnerPart(core, reader) if reader is not None and world.family(code) != "hgss" else None
