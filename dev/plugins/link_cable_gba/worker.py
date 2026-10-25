"""Worker part of the GBA link cable: plugs the core into mGBA's lockstep coordinator of the process group and out again."""
from __future__ import annotations

import threading


class LinkCoordinator:
    """Shared lockstep coordinator of the GBA players of a group process (the first core creates it)."""

    def __init__(self):
        """Creates the coordinator holder with its lock."""
        self._lock = threading.Lock()
        self._pointer = 0

    def fetch(self, core) -> int:
        """Returns the coordinator, creating it for the first core."""
        with self._lock:
            if not self._pointer:
                self._pointer = core.link_coordinator_new()
            return self._pointer


class CablePart:
    """Command True/False plugs the cable in or out; the answer says whether the core is connected now."""

    def __init__(self, core, nr: int, coordinator: LinkCoordinator):
        """Creates the part for one core and the shared coordinator."""
        self.core, self.nr, self.coordinator = core, nr, coordinator
        self.connected = False

    def ready(self) -> dict:
        """Reports whether the core supports the link cable."""
        return {"link": bool(self.core.can_link)}

    def command(self, on) -> bool:
        """Plugs the cable in or out through the link coordinator and returns whether the core is connected."""
        if not self.core.can_link:
            return False
        if on and not self.connected:
            self.connected = self.core.link_connect(self.coordinator.fetch(self.core), self.nr - 1)
        elif not on and self.connected:
            self.core.link_disconnect()
            self.connected = False
        return self.connected

    def end(self) -> None:
        """Game over or plugin switched off: pulls the cable so the partners do not wait for this core."""
        if self.connected:
            self.core.link_disconnect()
            self.connected = False


def create(core, job: dict, shared: dict) -> CablePart | None:
    """Creates the part only in a process group (job["group"]); a single player in an own process (restart after a crash)
    has no partner to connect with."""
    if not job.get("group"):
        return None
    coordinator = shared.setdefault("coordinator", LinkCoordinator())
    return CablePart(core, int(job["nr"]), coordinator)
