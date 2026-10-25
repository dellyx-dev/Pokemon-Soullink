"""Key profiles in the data folder (profile.json)."""
import json

from soullink.profile import MAX_NAME, Profile, kind_of


def test_create_names_and_binding(tmp_path):
    """Profiles are created with unique names and bindings."""
    p = Profile(tmp_path)
    assert p.names("controller", "gba") == [] and p.binding("controller", None, "gba") is None
    assert p.create("controller", "gba", "  Dellyx  ") == "Dellyx"
    assert p.create("controller", "gba", "Dellyx") == "Dellyx 2"
    assert p.create("controller", "gba", "x" * 30) == "x" * MAX_NAME
    p.set_("controller", "Dellyx", "gba", {"WEST": "X"})
    p.set_("keyboard", "Keys", "gba", None)
    new = Profile(tmp_path)
    assert new.names("controller", "gba") == ["Dellyx", "Dellyx 2", "x" * MAX_NAME]
    assert new.binding("controller", "Dellyx", "gba") == {"WEST": "X"}
    assert new.binding("controller", "Dellyx 2", "gba") is None
    assert new.exists("keyboard", "Keys", "gba") and not new.exists("controller", "Keys", "gba")


def test_profiles_belong_to_one_system(tmp_path):
    """A profile created for GBA is not offered for NDS; the same name may exist in both."""
    p = Profile(tmp_path)
    p.create("controller", "gba", "Dellyx", {"WEST": "A"})
    assert p.names("controller", "nds") == [] and not p.exists("controller", "Dellyx", "nds")
    assert p.create("controller", "nds", "Dellyx") == "Dellyx"
    assert p.binding("controller", "Dellyx", "nds") is None
    assert p.binding("controller", "Dellyx", "gba") == {"WEST": "A"}


def test_delete(tmp_path):
    """A deleted profile is gone for its system only, also after reloading."""
    p = Profile(tmp_path)
    p.create("keyboard", "gba", "A", {"k": "A"})
    p.create("keyboard", "nds", "A", {"k": "B"})
    p.delete("keyboard", "A", "gba")
    p.delete("keyboard", "missing", "gba")
    new = Profile(tmp_path)
    assert new.names("keyboard", "gba") == [] and new.binding("keyboard", "A", "nds") == {"k": "B"}


def test_old_layout_is_migrated(tmp_path):
    """The old layout (name, then system) becomes one profile per system."""
    old = {"keyboard": {"LOCKI": {"gba": {"a": "LEFT"}, "nds": {"a": "UP"}}},
           "controller": {"Dellyx": {"gba": None}, "P2": {"nds": {"WEST": "X"}}}}
    (tmp_path / "profile.json").write_text(json.dumps(old), encoding="utf-8")
    p = Profile(tmp_path)
    assert p.names("keyboard", "gba") == ["LOCKI"] and p.names("keyboard", "nds") == ["LOCKI"]
    assert p.binding("keyboard", "LOCKI", "nds") == {"a": "UP"}
    assert p.names("controller", "gba") == ["Dellyx"] and p.names("controller", "nds") == ["P2"]
    p.save()
    assert Profile(tmp_path).binding("keyboard", "LOCKI", "gba") == {"a": "LEFT"}


def test_broken_file_and_device_kind(tmp_path):
    """A broken file is tolerated and device kinds are separate."""
    (tmp_path / "profile.json").write_text("{broken", encoding="utf-8")
    assert Profile(tmp_path).names("controller", "gba") == []
    (tmp_path / "profile.json").write_text('{"version": 2, "controller": {"gba": {"A": 5, "B": null}, "nds": 3}}',
                                           encoding="utf-8")
    p = Profile(tmp_path)
    assert p.names("controller", "gba") == ["B"] and p.names("controller", "nds") == []
    assert kind_of("keyboard") == "keyboard" and kind_of("c3") == "controller" and kind_of(None) == "controller"
