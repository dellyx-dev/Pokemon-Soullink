"""Worker parts of the plugins in the player process: load, call per core step, pass on commands and report errors."""
from __future__ import annotations

import pickle
import threading
import traceback
from pathlib import Path

from .. import paths
from .api import error_log
from .loader import import_without_init

_IMPORT = threading.Lock()


class PluginParts:
    """The parts of the plugins from job["plugins"] ({"id", "dir", "module", "slot"}) for one player; job["base"] is the
    data directory (for error.log), and further parts of a process group share one dict per plugin."""

    def __init__(self, core, job: dict, events, shared: dict | None = None):
        """Loads the worker part of every plugin in the job; a failing part is switched off and reported."""
        self._core, self._job, self._events = core, job, events
        self.shared = {} if shared is None else shared
        self._parts: dict[str, object] = {}
        self._slots: dict[str, int | None] = {}
        self._base = Path(job["base"]) if job.get("base") else paths.base_dir()
        for entry in job.get("plugins") or []:
            self.load(entry)

    def load(self, entry: dict) -> None:
        """Loads the worker part of one plugin ({"id", "dir", "module", "slot"}); a failing part is reported. A part that
        still runs is ended first (restart)."""
        pid, dir = entry["id"], Path(entry["dir"])
        self._disable(pid)
        try:
            with _IMPORT:
                module = import_without_init(dir.parent, pid, entry["module"])
            part = module.create(self._core, self._job, self.shared.setdefault(pid, {}))
        except Exception:
            self._events.put(("plugin_error", pid, traceback.format_exc()))
            return
        if part is not None:
            self._parts[pid] = part
            self._slots[pid] = entry.get("slot")

    def active(self) -> list[str]:
        """Ids of the parts that still run."""
        return list(self._parts)

    def _safe(self, pid: str, call, default=None):
        """Calls call(part); an exception switches the part off and reports the traceback."""
        part = self._parts.get(pid)
        if part is None:
            return default
        try:
            return call(part)
        except Exception:
            self._events.put(("plugin_error", pid, traceback.format_exc()))
            self._disable(pid)
            return default

    def _disable(self, pid: str, to_end: bool = False) -> None:
        """Removes the part and ends it; its errors go as an event to the main process, at the very end (worker ends)
        directly to error.log."""
        part = self._parts.pop(pid, None)
        end = getattr(part, "end", None)
        if end is None:
            return
        try:
            end()
        except Exception:
            text = traceback.format_exc()
            if to_end:
                error_log(self._base, pid, f"Worker part, at shutdown:\n{text}")
            else:
                self._events.put(("plugin_error", pid, text))

    def ready(self) -> dict:
        """ready() of all parts for the ready info of the worker (under "plugins")."""
        def fetch(part) -> dict:
            """Reads the ready info of one part."""
            info = dict(getattr(part, "ready", dict)() or {})
            pickle.dumps(info)
            return info

        return {pid: info for pid in list(self._parts) if (info := self._safe(pid, fetch)) is not None}

    def before_image(self) -> None:
        """Called before every core step."""
        for pid in list(self._parts):
            self._safe(pid, lambda part: getattr(part, "before_image", _nothing)())

    def after_image(self, memory) -> None:
        """Called after every core step; returned bytes go into the plugin's shared memory slot."""
        def write(part, pid):
            """Writes the bytes of one part into its slot."""
            data = getattr(part, "after_image", _nothing)()
            if data is not None and self._slots.get(pid) is not None:
                memory.slot_write(self._slots[pid], bytes(data))

        for pid in list(self._parts):
            self._safe(pid, lambda part: write(part, pid))

    def command(self, pid: str, data) -> None:
        """Passes the command ("plugin", id, data) to the part; a reply goes back as ("plugin", id, reply)."""
        def run(part):
            """Runs the command on one part."""
            reply = getattr(part, "command", _nothing)(data)
            if reply is not None:
                pickle.dumps(reply)
                self._events.put(("plugin", pid, reply))

        self._safe(pid, run)

    def disable(self, pid: str) -> None:
        """The main process switched the plugin off (until load() restarts it)."""
        self._disable(pid)

    def end(self) -> None:
        """The worker ends: ends all parts."""
        for pid in list(self._parts):
            self._disable(pid, to_end=True)


def _nothing(*_):
    """Placeholder hook that does nothing."""
    return None
