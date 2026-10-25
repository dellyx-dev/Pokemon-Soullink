"""Session folder: session.json plus one folder per player."""
from __future__ import annotations

import json
import os
import re
import shutil
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from .atomic import atomic_write
from .language import t

VERSION = 1
FILE = "session.json"
STAGING_PREFIX = ".new-"
_REPLACEMENT = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss", "×": "x"}


class SessionError(Exception):
    """Raised when a session cannot be read."""
    pass


@dataclass
class Player:
    """Settings of one player of a session."""
    nr: int
    base_rom: str
    seed: str | None
    audio: bool
    system: str = "gba"
    keys: dict | None = None
    keyboard: dict | None = None
    volume: int | None = None
    name: str | None = None
    mac: str | None = None
    profile: str | None = None

    @property
    def audio_percent(self) -> int:
        """Game volume in percent, derived from the legacy on/off flag if no volume is stored."""
        return self.volume if self.volume is not None else (100 if self.audio else 0)


@dataclass
class Session:
    """Metadata of a session and the paths of its players' files."""
    name: str
    created: str
    last_played: str
    playtime_seconds: int
    randomizer_preset: str | None
    core_version: str
    player: list[Player]
    dir: Path | None = field(default=None, compare=False)

    def player_dir(self, nr: int) -> Path:
        """Folder of one player (p<nr>)."""
        return self.dir / f"p{nr}"

    @property
    def system(self) -> str:
        """Game system ("gba" or "nds") of the session."""
        return self.player[0].system if self.player else "gba"

    def rom(self, nr: int) -> Path:
        """Path of the player's randomized ROM."""
        system = next((sp.system for sp in self.player if sp.nr == nr), "gba")
        return self.player_dir(nr) / f"rom.{system}"

    def sav(self, nr: int) -> Path:
        """Path of the player's battery save."""
        return self.player_dir(nr) / "game.sav"

    def state(self, nr: int) -> Path:
        """Path of the player's save state."""
        return self.player_dir(nr) / "state.state"

    def to_dict(self) -> dict:
        """Serializable dict including the format version."""
        data = asdict(self)
        data.pop("dir")
        return {"version": VERSION, **data}

    @classmethod
    def from_dict(cls, data: dict, dir: Path | None) -> "Session":
        """Builds a session from the dict of session.json."""
        return cls(
            name=data["name"],
            created=data["created"],
            last_played=data["last_played"],
            playtime_seconds=int(data["playtime_seconds"]),
            randomizer_preset=data["randomizer_preset"],
            core_version=data["core_version"],
            player=[Player(**s) for s in data["player"]],
            dir=dir,
        )

    def save(self) -> None:
        """Writes session.json atomically."""
        text = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self.dir / FILE, text.encode("utf-8"))


def dir_name(name: str) -> str:
    """File system safe folder name derived from a session name."""
    for old, new in _REPLACEMENT.items():
        name = name.replace(old, new)
    name = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    name = re.sub(r"[^A-Za-z0-9-]", "", name.replace(" ", "-"))
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name or "Session"


def free_dir(sessions: Path, name: str) -> Path:
    """A folder path for the session name that does not exist yet, numbered if necessary."""
    base = dir_name(name)
    candidate, n = Path(sessions) / base, 2
    while candidate.exists():
        candidate, n = Path(sessions) / f"{base}-{n}", n + 1
    return candidate


def nds_mac(nr: int) -> str:
    """Own DS hardware address per player (Nintendo prefix 00:09:BF, then "SL" and the number); with three or more linked
    DS every address must differ, and Pokemon stores it in the save, so only new sessions use it."""
    return f"00:09:BF:53:4C:{nr:02X}"


def with_name(game_name: str, name: str | None) -> str:
    """Player label shown in the game: "Name · Game", or just the game without a name."""
    return f"{name} · {game_name}" if name else game_name


def default_name(day: date, games: list[str]) -> str:
    """Default session name: date, game (or "mixed") and player count."""
    game = games[0] if len(set(games)) == 1 else t("session.mixed")
    return f"{day.isoformat()} {game} ×{len(games)}"


def load_session(dir: Path) -> Session:
    """Reads session.json, falling back to the .bak file; raises SessionError if neither can be read."""
    dir = Path(dir)
    for file in (dir / FILE, dir / (FILE + ".bak")):
        if not file.exists():
            continue
        try:
            return Session.from_dict(json.loads(file.read_text(encoding="utf-8")), dir)
        except (ValueError, KeyError, TypeError, OSError):
            continue
    raise SessionError(t("session.unreadable", file=FILE, dir=dir))


def all_sessions(sessions: Path) -> list[Session]:
    """All readable sessions of the folder, most recently played first."""
    sessions = Path(sessions)
    if not sessions.is_dir():
        return []
    found = []
    for dir in sessions.iterdir():
        if not dir.is_dir() or dir.name.startswith("."):
            continue
        try:
            found.append(load_session(dir))
        except SessionError:
            continue
    return sorted(found, key=lambda s: s.last_played, reverse=True)


def candidates(file: Path) -> list[Path]:
    """The file and its .bak copy, as far as they exist."""
    file = Path(file)
    return [p for p in (file, file.with_name(file.name + ".bak")) if p.exists()]


def missing_roms(s: Session) -> list[Path]:
    """ROM files of the session that no longer exist."""
    return [s.rom(sp.nr) for sp in s.player if not s.rom(sp.nr).exists()]


def staging_create(sessions: Path) -> Path:
    """Creates a temporary folder in which a new session is assembled."""
    sessions = Path(sessions)
    sessions.mkdir(parents=True, exist_ok=True)
    staging = sessions / f"{STAGING_PREFIX}{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    return staging


def staging_finish(staging: Path, s: Session, sessions: Path) -> Path:
    """Saves the session in the staging folder and moves it to its final folder."""
    s.dir = Path(staging)
    s.save()
    target = free_dir(sessions, s.name)
    os.replace(staging, target)
    s.dir = target
    return target


def session_delete(s: Session, sessions: Path) -> None:
    """Deletes the session folder with ROMs and saves permanently; only directly inside the sessions folder."""
    dir = Path(s.dir).resolve()
    if dir.parent != Path(sessions).resolve() or not (dir / FILE).exists():
        raise ValueError(f"Not a session folder: {dir}")

    def write_protect_away(function, path, _error):
        """Clears the read-only flag (Windows) and retries the failed operation."""
        os.chmod(path, 0o666)
        function(path)

    shutil.rmtree(dir, onerror=write_protect_away)


def staging_discard(staging: Path) -> None:
    """Deletes a staging folder."""
    staging = Path(staging)
    if not staging.name.startswith(STAGING_PREFIX):
        raise ValueError(f"Not a staging folder: {staging}")
    shutil.rmtree(staging, ignore_errors=True)
