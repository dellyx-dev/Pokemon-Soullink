"""Finds and unpacks the base ROMs (GBA and NDS) of the ROM folder."""
from __future__ import annotations

import shutil
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .language import t

GEN3 = {"AXV": "Ruby", "AXP": "Sapphire", "BPE": "Emerald", "BPR": "FireRed", "BPG": "LeafGreen"}
GEN45 = {"ADA": "Diamond", "APA": "Pearl", "CPU": "Platinum", "IPK": "HeartGold", "IPG": "SoulSilver",
         "IRB": "Black", "IRA": "White", "IRE": "Black 2", "IRD": "White 2"}
GAMES = {"gba": GEN3, "nds": GEN45}
_FAMILY = {"AXV": "rs", "AXP": "rs", "BPE": "emerald", "BPR": "frlg", "BPG": "frlg", "ADA": "dp", "APA": "dp",
            "CPU": "pt", "IPK": "hgss", "IPG": "hgss", "IRB": "bw", "IRA": "bw", "IRE": "bw2", "IRD": "bw2"}
SUFFIXES = {".gba": "gba", ".nds": "nds"}
CODE_OFFSET = {"gba": 0xAC, "nds": 0x0C}
HEADER_LENGTH = 0xB0


@dataclass(frozen=True)
class BaseRom:
    """A base ROM file, optionally an entry inside a ZIP, with its game code and system."""
    file: Path
    entry: str | None
    code: str
    system: str = "gba"

    @property
    def game(self) -> str:
        """Name of the game edition."""
        return game_name(self.code, self.system)

    @property
    def suffix(self) -> str:
        """File suffix of the ROM for its system."""
        return f".{self.system}"


def _without_accents(text: str) -> str:
    """Text with accents removed."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def name_fits(filename: str) -> bool:
    """True if the file name contains "pokemon", ignoring accents and case."""
    return "pokemon" in _without_accents(filename).lower()


def read_code(header: bytes, system: str = "gba") -> str | None:
    """Game code from the ROM header; None if unreadable."""
    start = CODE_OFFSET[system]
    if len(header) < start + 4:
        return None
    try:
        code = header[start:start + 4].decode("ascii")
    except UnicodeDecodeError:
        return None
    return code if code.isalnum() else None


def family(game_code: str | None) -> str | None:
    """Group of games sharing the same map numbering (rs, emerald, frlg, dp, pt, hgss, bw, bw2); None for non-Pokemon
    games."""
    return _FAMILY.get((game_code or "")[:3])


def game_name(code: str | None, system: str = "gba") -> str | None:
    """Name of the edition in the current language; None for unknown codes."""
    return t(f"game.{code[:3]}") if code and code[:3] in GAMES[system] else None


def game_name_from_file(rom: Path) -> str | None:
    """Edition name of a .gba/.nds file; None if unknown or unreadable."""
    system = SUFFIXES.get(Path(rom).suffix.lower())
    if system is None:
        return None
    try:
        with open(rom, "rb") as f:
            return game_name(read_code(f.read(HEADER_LENGTH), system), system)
    except OSError:
        return None


def _header_read(file: Path) -> tuple[str | None, str | None, str | None]:
    """Reads (ZIP entry or None, system, game code) from a ROM or ZIP file."""
    system = SUFFIXES.get(file.suffix.lower())
    if system is not None:
        with open(file, "rb") as f:
            return None, system, read_code(f.read(HEADER_LENGTH), system)
    with zipfile.ZipFile(file) as z:
        entry = next((n for n in z.namelist() if Path(n).suffix.lower() in SUFFIXES), None)
        if entry is None:
            return None, None, None
        system = SUFFIXES[Path(entry).suffix.lower()]
        with z.open(entry) as f:
            return entry, system, read_code(f.read(HEADER_LENGTH), system)


def find_base_roms(dir: Path) -> list[BaseRom]:
    """Base ROMs of known Pokemon editions in the folder, sorted by system, game and file name."""
    dir = Path(dir)
    if not dir.is_dir():
        return []
    found = []
    for file in dir.iterdir():
        if file.suffix.lower() not in (".gba", ".nds", ".zip") or not name_fits(file.name) or not file.is_file():
            continue
        try:
            entry, system, code = _header_read(file)
        except (OSError, zipfile.BadZipFile):
            continue
        if system and game_name(code, system):
            found.append(BaseRom(file, entry, code, system))
    return sorted(found, key=lambda r: (r.system, r.game, r.file.name.lower()))


def unpack(rom: BaseRom, target: Path) -> Path:
    """Copies or extracts the base ROM to the target path."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if rom.entry is None:
        shutil.copyfile(rom.file, target)
    else:
        with zipfile.ZipFile(rom.file) as z, z.open(rom.entry) as source, open(target, "wb") as out:
            shutil.copyfileobj(source, out)
    return target


def code_from_file(rom: Path) -> str | None:
    """Four-character ROM code (e.g. BPRD, IRED) of a .gba/.nds file."""
    system = SUFFIXES.get(Path(rom).suffix.lower())
    if system is None:
        return None
    try:
        with open(rom, "rb") as f:
            return read_code(f.read(HEADER_LENGTH), system)
    except OSError:
        return None
