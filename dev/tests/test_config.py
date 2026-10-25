"""Tests of the settings file."""

import json
from pathlib import Path

from soullink import config


def test_missing_file_is_created(tmp_path):
    """A missing settings file is created with defaults."""
    e = config.load_settings(tmp_path)
    assert e.fast_forward_factor == 3
    assert e.autosave_minutes == 5
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert data["sessions_dir"] == "sessions"
    assert data["rom_dir"] == config.default_rom_dir() == str(Path("roms") / "gba")
    assert data["rom_dir_nds"] == str(Path("roms") / "nds")


def test_partial_file_is_completed(tmp_path):
    """A partial file gets the missing keys added."""
    (tmp_path / "settings.json").write_text('{"fast_forward_factor": 4, "unknown": 1}', encoding="utf-8")
    e = config.load_settings(tmp_path)
    assert e.fast_forward_factor == 4
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert set(data) >= {"rom_dir", "sessions_dir", "presets_dir", "fast_forward_factor", "autosave_minutes"}
    assert data["fast_forward_factor"] == 4


def test_broken_file_stays_untouched(tmp_path):
    """A broken settings file is left untouched."""
    (tmp_path / "settings.json").write_text("{broken", encoding="utf-8")
    e = config.load_settings(tmp_path)
    assert e.fast_forward_factor == 3
    assert (tmp_path / "settings.json").read_text(encoding="utf-8") == "{broken"


def test_resolve(tmp_path):
    """Relative folders resolve against the data directory."""
    assert config.resolve(tmp_path, "Sessions") == tmp_path / "Sessions"
    absolute = tmp_path / "x"
    assert config.resolve(tmp_path / "y", str(absolute)) == absolute


def test_default_folders_are_created(tmp_path):
    """All default folders are created inside the data directory, existing ones are left alone."""
    (tmp_path / "presets").mkdir()
    created = config.folders_create(tmp_path, config.load_settings(tmp_path))
    names = {p.relative_to(tmp_path).as_posix() for p in created}
    assert names == {"sessions", "sound", "roms/gba", "roms/nds"}
    assert all(p.is_dir() for p in created)
    assert config.folders_create(tmp_path, config.load_settings(tmp_path)) == []


def test_absolute_folders_are_not_created(tmp_path):
    """Folders outside the data directory (e.g. a network drive) are never created."""
    settings = config.load_settings(tmp_path)
    settings.rom_dir = str(tmp_path / "elsewhere" / "gba")
    settings.rom_dir_nds = ""
    created = config.folders_create(tmp_path / "data", settings)
    assert not (tmp_path / "elsewhere").exists()
    assert {p.name for p in created} == {"sessions", "presets", "sound"}


def test_plugin_fields(tmp_path):
    """Plugin state and values are stored and restored."""
    e = config.load_settings(tmp_path)
    assert (e.plugins, e.plugin_values, e.free_field) == ({}, {}, "")
    e.plugins["soullink"] = True
    e.plugin_values["soullink"] = {"stylus": False, "color": "red"}
    e.free_field = "alternating"
    config.save_settings(tmp_path, e)
    new = config.load_settings(tmp_path)
    assert (new.plugins, new.plugin_values, new.free_field) == \
        ({"soullink": True}, {"soullink": {"stylus": False, "color": "red"}}, "alternating")
    assert config.load_settings(tmp_path / "different").plugins == {}


def test_plugin_fields_with_wrong_type(tmp_path):
    """Plugin fields of the wrong type fall back to defaults."""
    (tmp_path / "settings.json").write_text('{"plugins": [1], "plugin_values": "x", "fast_forward_factor": 4}',
                                                 encoding="utf-8")
    e = config.load_settings(tmp_path)
    assert (e.plugins, e.plugin_values, e.fast_forward_factor) == ({}, {}, 4)


def test_nds_folder_and_view(tmp_path):
    """The NDS folder and DS view settings are stored."""
    e = config.load_settings(tmp_path)
    assert e.rom_dir_nds == config.default_rom_dir("nds")
    assert e.ds_view == "hybrid"
    e.ds_view = "columns"
    config.save_settings(tmp_path, e)
    assert config.load_settings(tmp_path).ds_view == "columns"
