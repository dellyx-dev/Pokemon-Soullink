"""Displayed texts from language/<abbreviation>.txt files ("key = text" lines, {name} marks a placeholder); a missing text
falls back to German, then to the key itself. Plugins ship their own files whose keys are prefixed with "<id>.", and
core keys win on a clash."""
from __future__ import annotations

import locale
from pathlib import Path

from . import paths

REFERENCE = "de"
SUFFIX = ".txt"

_texts: dict[str, str] = {}
_reference: dict[str, str] = {}
_abbreviation: str | None = None
_plugin_dir: dict[str, Path] = {}
_plugin_texts: dict[str, str] = {}
_plugin_reference: dict[str, str] = {}


def dir() -> Path:
    """The folder holding the language files."""
    return paths.language_dir()


def read_file(path: Path) -> dict[str, str]:
    """Parses "key = text" lines; "#" starts a comment and a literal backslash-n becomes a line break."""
    texts = {}
    for row in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if not row.strip() or row.lstrip().startswith("#") or "=" not in row:
            continue
        key, text = row.split("=", 1)
        texts[key.strip()] = text.strip().replace("\\n", "\n")
    return texts


def available(language_dir: Path | None = None) -> list[tuple[str, str]]:
    """Pairs of (abbreviation, display name) for all language files in the folder, sorted by display name."""
    language_dir = Path(language_dir or dir())
    languages = []
    for file in sorted(language_dir.glob("*" + SUFFIX)) if language_dir.is_dir() else []:
        try:
            name = read_file(file).get("_name") or file.stem.upper()
        except (OSError, UnicodeDecodeError):
            continue
        languages.append((file.stem.lower(), name))
    return sorted(languages, key=lambda s: s[1].casefold())


def system_language() -> str:
    """"de" if the operating system language is German, otherwise "us"."""
    try:
        name = (locale.getlocale()[0] or locale.getdefaultlocale()[0] or "").lower()
    except (ValueError, TypeError):
        name = ""
    return "de" if name.startswith(("de", "german")) else "us"


def set_(abbreviation: str | None, language_dir: Path | None = None) -> str:
    """Loads a language, falling back to the reference language when its file is missing, and returns the abbreviation in
    use."""
    global _texts, _reference, _abbreviation
    language_dir = Path(language_dir or dir())
    reference = language_dir / (REFERENCE + SUFFIX)
    _reference = read_file(reference) if reference.exists() else {}
    abbreviation = (abbreviation or REFERENCE).lower()
    file = language_dir / (abbreviation + SUFFIX)
    if not file.exists():
        abbreviation = REFERENCE
        file = reference
    _texts = read_file(file) if file.exists() else {}
    _abbreviation = abbreviation
    _plugin_texts.clear()
    _plugin_reference.clear()
    for plugin_id in _plugin_dir:
        _plugin_load(plugin_id)
    return abbreviation


def _plugin_file(path: Path) -> dict[str, str]:
    """Like read_file, but a missing or unreadable plugin file is just empty."""
    try:
        return read_file(path) if path.is_file() else {}
    except (OSError, UnicodeDecodeError):
        return {}


def _plugin_remove(plugin_id: str) -> None:
    """Drops all texts of one plugin."""
    prefix = plugin_id + "."
    for texts in (_plugin_texts, _plugin_reference):
        for key in [k for k in texts if k.startswith(prefix)]:
            del texts[key]


def _plugin_load(plugin_id: str) -> None:
    """Loads the texts of one plugin for the current language and the reference language."""
    _plugin_remove(plugin_id)
    prefix = plugin_id + "."
    languages = _plugin_dir[plugin_id] / "language"
    reference = _plugin_file(languages / (REFERENCE + SUFFIX))
    own = reference if _abbreviation == REFERENCE else _plugin_file(languages / (_abbreviation + SUFFIX))
    _plugin_reference.update({prefix + k: v for k, v in reference.items()})
    _plugin_texts.update({prefix + k: v for k, v in own.items()})


def plugin_texts(plugin_id: str, plugin_dir: Path | None) -> None:
    """Registers the language folder of a plugin (None unregisters it); set_ loads it from then on."""
    if plugin_dir is None:
        _plugin_dir.pop(plugin_id, None)
        _plugin_remove(plugin_id)
        return
    _plugin_dir[plugin_id] = Path(plugin_dir)
    if _abbreviation is not None:
        _plugin_load(plugin_id)


def current() -> str:
    """The abbreviation of the language currently in use."""
    if _abbreviation is None:
        set_(REFERENCE)
    return _abbreviation


def present(key: str) -> bool:
    """True if a text exists for the key in the current or the reference language."""
    if _abbreviation is None:
        set_(REFERENCE)
    return any(key in texts for texts in (_texts, _plugin_texts, _reference, _plugin_reference))


def t(key: str, **values) -> str:
    """The text for the key in the current language with {name} placeholders filled from the keyword arguments."""
    if _abbreviation is None:
        set_(REFERENCE)
    text = (_texts.get(key) or _plugin_texts.get(key) or _reference.get(key)
            or _plugin_reference.get(key) or key)
    if values:
        try:
            return text.format(**values)
        except (KeyError, IndexError, ValueError):
            return text
    return text
