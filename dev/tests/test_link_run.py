"""Tests of the shared code of the link cable runs."""
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import gba_cable_club  # noqa: E402
import link_run  # noqa: E402
import nds_packets  # noqa: E402


def test_plan_from_keys_script():
    """A key script is parsed into steps."""
    assert link_run.plan("LINK -:5 A:5 UP+B:3 IMAGE:x INFO") == [
        ("keys", 0, 5), ("keys", 1 << 8, 5), ("keys", (1 << 4) | (1 << 0), 3), ("image", "x")]


@pytest.mark.parametrize("module, photos", [(gba_cable_club, 4), (nds_packets, 5)])
def test_default_scripts_can_be_parsed(module, photos):
    """The built-in scripts can be parsed."""
    plans = [link_run.plan(s) for s in module.DEFAULT]
    assert len(plans) == 2 and all(sum(1 for s in p if s[0] == "image") == photos for p in plans)


def test_paths_never_in_project(tmp_path, monkeypatch):
    """Paths inside the project are refused."""
    rom = tmp_path / "rom.gba"
    rom.write_bytes(b"x")
    assert link_run.path(str(rom), "SOULLINK_LINK_ROM", "ROM") == rom
    monkeypatch.setenv("SOULLINK_LINK_ROM", str(rom))
    assert link_run.path(None, "SOULLINK_LINK_ROM", "ROM") == rom
    with pytest.raises(SystemExit, match="inside the project"):
        link_run.path(str(link_run.PROJECT / "README.md"), "X", "ROM")
    with pytest.raises(SystemExit, match="does not exist"):
        link_run.path(str(tmp_path / "missing.gba"), "X", "ROM")
    monkeypatch.delenv("SOULLINK_LINK_ROM")
    with pytest.raises(SystemExit, match="SOULLINK_LINK_ROM"):
        link_run.path(None, "SOULLINK_LINK_ROM", "ROM")


def test_arguments_with_scripts_after_the_double_dash(tmp_path):
    """Arguments with scripts after "--" are parsed."""
    (tmp_path / "rom.nds").write_bytes(b"x")
    (tmp_path / "z.state").write_bytes(b"y")
    a = link_run.arguments("Test", ".nds", ["--rom", str(tmp_path / "rom.nds"), "--state", str(tmp_path / "z.state"),
                                            "--output", str(tmp_path / "output"), "--work", str(tmp_path / "work"),
                                            "--", "-:30 A:5", "-:30 B:5"])
    assert a.scripts == ["-:30 A:5", "-:30 B:5"] and not a.own_work and a.work == tmp_path / "work"
    dir = link_run.player_dir(a.work, 2, a.rom, a.state, "nds")
    assert (dir / "rom.nds").read_bytes() == b"x" and (dir / "state.state").read_bytes() == b"y"
    with pytest.raises(SystemExit):
        link_run.arguments("Test", ".nds", ["--rom", str(tmp_path / "rom.nds"), "--state", str(tmp_path / "z.state"),
                                             "--output", str(link_run.DEV / "photos")])
