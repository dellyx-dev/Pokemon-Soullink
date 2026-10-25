"""Tests of the language files and texts."""

import re
import string
from pathlib import Path

import pytest

from soullink import language

SOURCES = Path(language.__file__).resolve().parent


def _file(abbreviation):
    """Texts of the language file for an abbreviation."""
    return language.read_file(language.dir() / f"{abbreviation}.txt")


def _placeholder(text):
    """Placeholder names used in a text."""
    return {field for _, field, _, _ in string.Formatter().parse(text) if field}


def test_languages_in_folder():
    """The languages in the language folder are found."""
    assert dict(language.available()) == {"de": "Deutsch", "us": "English"}


@pytest.mark.parametrize("abbreviation", ["us"])
def test_all_languages_complete_and_with_same_placeholders(abbreviation):
    """All languages are complete and use the same placeholders."""
    de, other = _file("de"), _file(abbreviation)
    assert set(other) == set(de), (set(de) ^ set(other))
    wrong = {k for k in de if _placeholder(de[k]) != _placeholder(other[k])}
    assert not wrong, wrong


def test_each_key_used_in_code_exists_in_the_language_file():
    """Every language key used in the code exists in the language file."""
    de = _file("de")
    literal = set()
    for file in SOURCES.rglob("*.py"):
        literal |= set(re.findall(r'\bt\(\s*"([a-z_]+\.[A-Za-z0-9_.]+)"', file.read_text(encoding="utf-8")))
    assert literal and not literal - set(de), sorted(literal - set(de))


def test_placeholders_in_code_match_the_texts():
    """Every t() call with values passes exactly the placeholders its text uses."""
    import ast

    de = _file("de")
    wrong = []
    for file in SOURCES.rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t"
                    and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in de):
                continue
            names = {k.arg for k in node.keywords}
            if not names or None in names:
                continue
            if names != _placeholder(de[node.args[0].value]):
                wrong.append((file.name, node.lineno, node.args[0].value))
    assert not wrong, wrong


def test_composite_keys_are_present():
    """Keys built at runtime exist in the language file."""
    from soullink import layout, types
    from soullink.dex import evolution_text  # noqa: F401
    from soullink.input.wizard import STEPS
    from soullink.input.keys import Key
    from soullink.input.key_binding import GAME_KEYS, Function, _NAMED
    from soullink.roms import GAMES
    from soullink.ui.pokemon_components import VALUES
    from soullink.ui.game import BUTTON_SHORT
    from soullink.ui.types_overlay import TABLE_RESULT

    needed = {f"key.{t.name.lower()}" for t in Key}
    needed |= {f"function.{f.name.lower()}" for f in Function if f not in GAME_KEYS}
    needed |= {"keyboard." + n.replace(" ", "_") for n in _NAMED}
    needed |= {f"type.{types._key(x)}" for x in types.TYPES} | {f"type_short.{types._key(x)}" for x in types.TYPES}
    needed |= {f"game.{code}" for games in GAMES.values() for code in games}
    needed |= {f"wizard.{t.name.lower()}" for t in STEPS}
    needed |= {f"view.{a}" for a in layout.VIEWS} | {f"value.{w}" for w in VALUES}
    needed |= set(TABLE_RESULT.values())
    needed |= {k for k in BUTTON_SHORT.values() if k.startswith("button.")}
    from soullink.ui.settings import GROUPS, STATUS_KIND
    from soullink.ui.game import MENU_GROUPS

    from soullink.ui.keys_menu import GROUPS as KEYS_GROUPS

    needed |= set(MENU_GROUPS.values()) | set(GROUPS.values()) | set(KEYS_GROUPS)
    needed |= {f"once.status_{a}{e}" for a in STATUS_KIND.values() for e in ("", "_1")}
    from soullink.ui.settings import STATUS_TEXT

    needed |= {k for pair in STATUS_TEXT.values() for k in pair}
    for abbreviation in ("de", "us"):
        missing = needed - set(_file(abbreviation))
        assert not missing, (abbreviation, sorted(missing))


def test_switching_and_fallback(tmp_path):
    """Switching the language works and missing texts fall back."""
    assert language.set_("us") == "us" and language.t("start.end") == "Quit"
    assert language.t("resume.rom_missing", file="x.gba") == "ROM missing: x.gba"
    from soullink import types
    from soullink.roms import game_name

    assert types.display("Fire") == "Fire" and types.short("Bug") == "BUG" and game_name("BPED") == "Emerald"
    assert language.set_("xx") == "de" and language.t("start.end") == "Beenden"
    (tmp_path / "de.txt").write_text("_name = Deutsch\nonly.de = nur deutsch\n", encoding="utf-8")
    (tmp_path / "us.txt").write_text("# empty\n_name = English\n", encoding="utf-8")
    language.set_("us", tmp_path)
    assert language.t("only.de") == "nur deutsch" and language.t("exists.not") == "exists.not"


def test_plugin_texts_with_prefix_and_fallback(tmp_path):
    """Plugin texts get a prefix and fall back to German."""
    language.set_("de")
    dir = tmp_path / "mine"
    (dir / "language").mkdir(parents=True)
    (dir / "language" / "de.txt").write_text("_name = Meins\ngreeting = Hallo {name}\nonly_de = Nur deutsch\n",
                                                encoding="utf-8")
    (dir / "language" / "us.txt").write_text("_name = Mine\ngreeting = Hello {name}\n", encoding="utf-8")
    language.plugin_texts("mine", dir)
    assert language.t("mine.greeting", name="Ash") == "Hallo Ash" and language.present("mine._name")
    language.set_("us")
    assert language.t("mine.greeting", name="Ash") == "Hello Ash" and language.t("mine.only_de") == "Nur deutsch"
    assert language.t("once.title") == "Settings"
    only_de = tmp_path / "onlyde"
    (only_de / "language").mkdir(parents=True)
    (only_de / "language" / "de.txt").write_text("title = Nur auf Deutsch\n", encoding="utf-8")
    language.plugin_texts("onlyde", only_de)
    assert language.t("onlyde.title") == "Nur auf Deutsch"
    once = tmp_path / "once"
    (once / "language").mkdir(parents=True)
    (once / "language" / "us.txt").write_text("title = Overridden\n", encoding="utf-8")
    language.plugin_texts("once", once)
    assert language.t("once.title") == "Settings"
    language.plugin_texts("mine", None)
    assert language.t("mine.greeting") == "mine.greeting" and not language.present("mine._name")
    away = tmp_path / "away"
    language.plugin_texts("away", away)
    language.set_("de")
    assert language.t("away._name") == "away._name"


def test_language_setting_switches_and_persists(monkeypatch, tmp_path):
    """The language setting switches the language and persists."""
    monkeypatch.setattr(language, "system_language", lambda: "de")
    language.set_("de")
    import json

    from soullink.input.devices import KeysEvent
    from soullink.input.keys import Key
    from soullink.ui.settings import SettingsScreen
    from ui_helpers import dummy_app

    app = dummy_app(monkeypatch, tmp_path)
    try:
        bs = SettingsScreen(app)
        bs.selection = [z[0] for z in bs.rows].index("language")
        bs.event(KeysEvent("c1", Key.RIGHT, True))
        assert language.current() == "us" and language.t("once.title") == "Settings"
        assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["language"] == "us"
        bs.draw(app.area)
    finally:
        app.close()
