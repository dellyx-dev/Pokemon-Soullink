"""Tests of the session folder and file handling."""

import json
from datetime import date

import pytest

from soullink import session as S


def _session(name="2026-10-19 Emerald ×4", last="2026-10-19T20:00:00"):
    """A sample session."""
    return S.Session(
        name=name,
        created="2026-10-19T19:00:00",
        last_played=last,
        playtime_seconds=60,
        randomizer_preset="default.rnqs",
        core_version="mGBA 0.11",
        player=[S.Player(1, "Pokémon Emerald Version.zip", "123", True),
                 S.Player(2, "Pokémon Emerald Version.zip", None, False)],
    )


def test_dir_name():
    """Folder names are made file system safe."""
    assert S.dir_name("2026-10-19 Emerald ×4") == "2026-10-19-Emerald-x4"
    assert S.dir_name("Blattgrün Ärger!") == "Blattgruen-Aerger"
    assert S.dir_name("Straße") == "Strasse"


def test_free_dir(tmp_path):
    """An unused folder name is chosen."""
    assert S.free_dir(tmp_path, "A B") == tmp_path / "A-B"
    (tmp_path / "A-B").mkdir()
    assert S.free_dir(tmp_path, "A B") == tmp_path / "A-B-2"


def test_default_name():
    """The default session name is built from date and games."""
    assert S.default_name(date(2026, 10, 19), ["Emerald"] * 4) == "2026-10-19 Emerald ×4"
    assert S.default_name(date(2026, 10, 19), ["Ruby", "Sapphire"]) == "2026-10-19 Mixed ×2"


def test_save_and_load(tmp_path):
    """A session survives saving and loading."""
    s = _session()
    s.dir = tmp_path
    s.save()
    data = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))
    assert data["version"] == 1 and "dir" not in data
    loaded = S.load_session(tmp_path)
    assert loaded == s
    assert loaded.dir == tmp_path
    assert loaded.rom(2) == tmp_path / "p2" / "rom.gba"
    assert loaded.sav(1) == tmp_path / "p1" / "game.sav"
    assert loaded.state(1) == tmp_path / "p1" / "state.state"


def test_load_falls_back_to_bak(tmp_path):
    """A broken session file falls back to the backup."""
    s = _session()
    s.dir = tmp_path
    s.save()
    s.save()
    (tmp_path / "session.json").write_text("{broken", encoding="utf-8")
    assert S.load_session(tmp_path).name == s.name


def test_load_without_file(tmp_path):
    """Loading without a file raises an error."""
    with pytest.raises(S.SessionError):
        S.load_session(tmp_path)


def test_all_sessions(tmp_path):
    """All readable sessions are listed, newest first."""
    for name, time in (("Old", "2026-10-01T10:00:00"), ("New", "2026-10-18T10:00:00")):
        s = _session(name, time)
        s.dir = tmp_path / name
        s.dir.mkdir()
        s.save()
    (tmp_path / "Broken").mkdir()
    (tmp_path / "Broken" / "session.json").write_text("{", encoding="utf-8")
    (tmp_path / ".new-x").mkdir()
    assert [s.name for s in S.all_sessions(tmp_path)] == ["New", "Old"]
    assert S.all_sessions(tmp_path / "missing") == []


def test_candidates(tmp_path):
    """The file and its backup are candidates."""
    file = tmp_path / "state.state"
    assert S.candidates(file) == []
    (tmp_path / "state.state.bak").write_bytes(b"x")
    assert S.candidates(file) == [tmp_path / "state.state.bak"]
    file.write_bytes(b"y")
    assert S.candidates(file) == [file, tmp_path / "state.state.bak"]


def test_missing_roms(tmp_path):
    """Missing ROM files are reported."""
    s = _session()
    s.dir = tmp_path
    (tmp_path / "p1").mkdir()
    (tmp_path / "p1" / "rom.gba").write_bytes(b"x")
    assert S.missing_roms(s) == [tmp_path / "p2" / "rom.gba"]


def test_staging(tmp_path):
    """A session is assembled in a staging folder and moved."""
    staging = S.staging_create(tmp_path)
    assert staging.name.startswith(".new-") and staging.is_dir()
    s = _session()
    target = S.staging_finish(staging, s, tmp_path)
    assert target == tmp_path / "2026-10-19-Emerald-x4"
    assert (target / "session.json").exists() and s.dir == target
    assert not staging.exists()


def test_staging_discard(tmp_path):
    """A staging folder can be discarded."""
    staging = S.staging_create(tmp_path)
    (staging / "p1").mkdir()
    S.staging_discard(staging)
    assert not staging.exists()
    other = tmp_path / "Real-session"
    other.mkdir()
    with pytest.raises(ValueError):
        S.staging_discard(other)
    assert other.exists()


def test_system_per_player_and_legacy(tmp_path):
    """The system is stored per player; legacy sessions default to GBA."""
    s = S.Session("DS", "x", "x", 0, None, "", [S.Player(1, "p.zip", None, True, "nds")], tmp_path)
    assert s.rom(1) == tmp_path / "p1" / "rom.nds" and s.system == "nds"
    s.save()
    assert S.load_session(tmp_path).player[0].system == "nds"
    old = _session().to_dict()
    for sp in old["player"]:
        del sp["system"]
    loaded = S.Session.from_dict(old, tmp_path)
    assert loaded.system == "gba" and loaded.rom(1) == tmp_path / "p1" / "rom.gba"


def test_key_binding_per_player(tmp_path):
    """Key bindings are stored per player."""
    s = _session()
    s.dir = tmp_path
    s.player[1].keys = {"SOUTH": "GBA_A", "EAST": "GBA_W"}
    s.save()
    loaded = S.load_session(tmp_path)
    assert loaded.player[1].keys == {"SOUTH": "GBA_A", "EAST": "GBA_W"}
    assert loaded.player[0].keys is None


def test_player_name_and_label(tmp_path):
    """Player names appear in the label."""
    s = _session()
    s.player[0].name = "Dellyx"
    s.dir = tmp_path
    s.save()
    loaded = S.load_session(tmp_path)
    assert [sp.name for sp in loaded.player] == ["Dellyx", None]
    assert S.with_name("Emerald", "Dellyx") == "Dellyx · Emerald" and S.with_name("Emerald", None) == "Emerald"


def test_session_delete(tmp_path):
    """Deleting a session removes its folder."""
    import os
    import stat

    s = _session()
    target = S.staging_finish(S.staging_create(tmp_path), s, tmp_path)
    (target / "p1").mkdir()
    rom = target / "p1" / "rom.gba"
    rom.write_bytes(b"x")
    os.chmod(rom, stat.S_IREAD)
    with pytest.raises(ValueError):
        S.session_delete(s, tmp_path / "elsewhere")
    S.session_delete(s, tmp_path)
    assert not target.exists() and tmp_path.exists()
    foreign = tmp_path / "Foreign"
    foreign.mkdir()
    with pytest.raises(ValueError):
        S.session_delete(S.Session("x", "", "", 0, None, "", [], foreign), tmp_path)
    assert foreign.exists()
