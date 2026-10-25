"""Tests of the self-test and its plugin check."""

import json

from conftest import plugin_create
from soullink.__main__ import _plugins_check, selftest


def test_selftest(tmp_path, test_rom):
    """The self-test passes with a real ROM."""
    report = tmp_path / "selftest.txt"
    assert selftest(test_rom, report) == 0
    text = report.read_text(encoding="utf-8")
    assert "RESULT: OK" in text


def _check(monkeypatch, base):
    """Runs the plugin check for a data directory and returns the reported rows."""
    monkeypatch.setenv("SOULLINK_BASE", str(base))
    rows = []
    _plugins_check(lambda name, ok, info="": rows.append((name, ok, info)))
    return rows


def test_plugins_check_imports_only_enabled_plugins_and_leaves_the_file_unchanged(monkeypatch, tmp_path):
    """The plugin check imports only enabled plugins and leaves settings.json unchanged."""
    dir = tmp_path / "plugins"
    plugin_create(dir, "good")
    plugin_create(dir, "from", code="open(r'%s', 'w').close()\n" % (tmp_path / "executed"))
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"plugins": {"good": True}}), encoding="utf-8")
    before = settings.read_bytes()
    ((name, ok, info),) = _check(monkeypatch, tmp_path)
    assert (name, ok) == ("Plugins", True) and info.startswith("2 found, 1 enabled")
    assert not (tmp_path / "executed").exists()
    assert settings.read_bytes() == before


def test_plugins_import_error_is_reported(monkeypatch, tmp_path):
    """A plugin import error is reported by the check."""
    plugin_create(tmp_path / "plugins", "broken", code="import gives_es_not\n")
    (tmp_path / "settings.json").write_text(json.dumps({"plugins": {"broken": True}}), encoding="utf-8")
    ((name, ok, info),) = _check(monkeypatch, tmp_path)
    assert not ok and info.startswith("broken: ModuleNotFoundError")


def test_plugins_check_without_folder_and_settings(monkeypatch, tmp_path):
    """The plugin check works without a folder and settings."""
    ((name, ok, info),) = _check(monkeypatch, tmp_path)
    assert ok and info.startswith("0 found, 0 enabled")
