"""Entry point: `python -m soullink` starts the program, `--selftest <rom> [<report>]` checks the installation."""
from __future__ import annotations

import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

ENVIRONMENT = {
    "PYGAME_HIDE_SUPPORT_PROMPT": "1",
    "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS": "1",
    "SDL_GAMECONTROLLER_USE_BUTTON_LABELS": "0",
}


def _wait(sp, condition, timeout: float) -> bool:
    """Polls the player process until the condition holds or the timeout expires."""
    end = time.monotonic() + timeout
    while time.monotonic() < end and not condition():
        sp.fetch()
        sp.audio_fetch()
        time.sleep(0.02)
    return condition()


def _plugins_check(check) -> None:
    """Reports how many plugins exist and are enabled and trial-imports the enabled ones, which verifies that the build
    bundles everything they need."""
    import json

    from . import paths
    from .config import FILE
    from .plugin import loader

    dir = paths.plugin_dir()
    infos = loader.find(dir)
    try:
        saved = json.loads((paths.base_dir() / FILE).read_text(encoding="utf-8")).get("plugins", {})
    except (OSError, ValueError, AttributeError):
        saved = {}
    on = {k for k, v in saved.items() if v is True} if isinstance(saved, dict) else set()
    error = []
    for info in infos:
        if info.id not in on or info.status != "ok":
            continue
        try:
            loader.import_(dir, info.id)
        except Exception as error_:
            error.append(f"{info.id}: {type(error_).__name__}: {error_}")
    active = sum(1 for i in infos if i.id in on)
    check("Plugins", not error, "; ".join(error) or f"{len(infos)} found, {active} enabled, {dir}")


def selftest(rom: Path, output: Path) -> int:
    """Checks core, randomizer, Java, plugins and a short game run with the given ROM and writes a report; returns 0 on
    success."""
    from . import paths
    from .randomizer import _FLAGS
    from .player import PlayerProcess

    rows: list[str] = []
    ok = True

    def check(name: str, passed: bool, info: str = "") -> None:
        """Records one check result in the report."""
        nonlocal ok
        ok = ok and passed
        rows.append(f"{'OK  ' if passed else 'FAIL'} {name} {info}".rstrip())

    check("Core", paths.core_file().exists(), str(paths.core_file()))
    check("Randomizer", paths.randomizer_jar().exists(), str(paths.randomizer_jar()))
    java = paths.java_program()
    try:
        runs = java is not None and subprocess.run([str(java), "-version"], capture_output=True,
                                                     timeout=30, creationflags=_FLAGS).returncode == 0
    except (OSError, subprocess.SubprocessError):
        runs = False
    check("Java", runs, str(java))
    _plugins_check(check)

    with tempfile.TemporaryDirectory() as tmp:
        dir = Path(tmp) / "p1"
        dir.mkdir()
        shutil.copyfile(rom, dir / "rom.gba")
        sp = PlayerProcess(1, dir, audio=False)
        sp.start()
        try:
            started = _wait(sp, lambda: sp.ready_info is not None or not sp.alive, 30) and sp.ready_info
            check("Core starts", bool(started), (sp.ready_info or {}).get("version", sp.error or ""))
            if started:
                time.sleep(1.0)
                check("Image", sp.image() is not None)
                nr = sp.save()
                check("Save state", _wait(sp, lambda: nr in sp.saved_ids, 10))
        finally:
            sp.end()
        check("Shutdown", sp.exitcode == 0, f"Exit-Code {sp.exitcode}")

    rows.append(f"INFO  Base folder {paths.base_dir()}")
    rows.append("RESULT: OK" if ok else "RESULT: FAILED")
    Path(output).write_text("\n".join(rows) + "\n", encoding="utf-8")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    """Program entry point; returns the process exit code."""
    multiprocessing.freeze_support()
    argv = sys.argv[1:] if argv is None else argv
    for key, value in ENVIRONMENT.items():
        os.environ.setdefault(key, value)
    from . import paths

    if argv[:1] == ["--selftest"] and len(argv) >= 2:
        output = Path(argv[2]) if len(argv) > 2 else paths.base_dir() / "selftest.txt"
        return selftest(Path(argv[1]), output)
    try:
        from .ui.app import App

        App(paths.base_dir()).run()
    except Exception:
        with open(paths.base_dir() / paths.ERROR_LOG, "a", encoding="utf-8") as log:
            log.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')}\n{traceback.format_exc()}\n")
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
