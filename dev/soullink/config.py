"""Program settings stored in settings.json next to the program."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .atomic import atomic_write

FILE = "settings.json"


@dataclass
class Settings:
    """All user settings of the program, persisted as JSON."""
    rom_dir: str
    rom_dir_nds: str = ""
    sessions_dir: str = "sessions"
    presets_dir: str = "presets"
    fast_forward_factor: int = 3
    autosave_minutes: float = 5
    ds_view: str = "hybrid"
    sound_dir: str = "sound"
    music_volume: int = 50
    language: str = ""
    plugins: dict = field(default_factory=dict)
    plugin_values: dict = field(default_factory=dict)
    free_field: str = ""


def default_rom_dir(system: str = "gba") -> str:
    """Default ROM folder for the given system ("gba" or "nds")."""
    return str(Path("roms") / system)


def resolve(base: Path, value: str) -> Path:
    """Resolves a possibly relative folder setting against the data directory."""
    path = Path(value)
    return path if path.is_absolute() else base / path


def folders_create(base: Path, settings: Settings) -> list[Path]:
    """Creates the missing session, preset, sound and ROM folders inside the data directory and returns them."""
    created = []
    for value in (settings.sessions_dir, settings.presets_dir, settings.sound_dir, settings.rom_dir,
                  settings.rom_dir_nds):
        if not value or Path(value).is_absolute():
            continue
        path = resolve(base, value)
        if path.is_dir():
            continue
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        created.append(path)
    return created


def _default() -> dict:
    """Settings as a dict with the built-in default values."""
    return asdict(Settings(rom_dir=default_rom_dir("gba"), rom_dir_nds=default_rom_dir("nds")))


def save_settings(base: Path, settings: Settings) -> None:
    """Writes the settings atomically to settings.json."""
    path = Path(base) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(asdict(settings), indent=2, ensure_ascii=False).encode("utf-8"))


def load_settings(base: Path) -> Settings:
    """Loads the settings, creating the file or missing keys; a corrupt file is left untouched."""
    path = Path(base) / FILE
    default = _default()
    read: dict = {}
    if path.exists():
        try:
            read = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(read, dict):
                raise ValueError("not an object")
        except (ValueError, OSError):
            return Settings(**default)
    known = {f.name for f in fields(Settings)}
    values = {**default, **{k: v for k, v in read.items()
                            if k in known and (not isinstance(default[k], dict) or isinstance(v, dict))}}
    settings = Settings(**values)
    if not path.exists() or not known <= set(read):
        save_settings(base, settings)
    return settings
