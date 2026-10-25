"""Tests of finding, importing and enabling plugins."""

import json
import sys

import pytest

from conftest import plugin_create
from soullink import config, paths, language
from soullink.plugin.api import API_VERSION, Setting, Plugin
from soullink.plugin.loader import ALTERNATING, CORE_DISPLAY, PACKET, Plugins, field_display, find, id_valid

WITH_SETTING = """from soullink.plugin.api import Setting, Plugin


class Testplugin(Plugin):
    def settings(self):
        return [Setting("color", self.api.t("color"), "selection", "red", ("red", "blue"))]


def create(api):
    return Testplugin(api)
"""


def _settings(base):
    """Loads the settings of a data directory."""
    return config.load_settings(base)


def _saved(base):
    """The stored settings.json content."""
    return json.loads((base / "settings.json").read_text(encoding="utf-8"))


def test_plugin_dir_is_in_the_data_dir(monkeypatch, tmp_path):
    """The plugin folder lies in the data directory."""
    monkeypatch.setenv("SOULLINK_BASE", str(tmp_path))
    assert paths.plugin_dir() == tmp_path / "plugins"
    assert paths.plugin_dir(tmp_path / "x") == tmp_path / "x" / "plugins"


def test_find_without_a_folder(tmp_path):
    """Finding plugins without a folder yields nothing."""
    assert find(tmp_path / "plugins") == []
    plugins = Plugins(tmp_path, _settings(tmp_path))
    assert plugins.infos == [] and plugins.active() == []


def test_find_reads_plugin_json_and_texts(tmp_path):
    """find() reads plugin.json and the language files."""
    dir = tmp_path / "plugins"
    plugin_create(dir, "second")
    plugin_create(dir, "first", data={"version": "1.2.0", "author": "Dellyx", "worker": "worker",
                                            "license": "LICENSE"},
                   texts={"de": "_description = Fallback text\n", "us": "_name = First plugin\n"})
    (dir / ".gitkeep").write_text("", encoding="utf-8")
    (dir / "__pycache__").mkdir()
    infos = find(dir)
    assert [i.id for i in infos] == ["first", "second"]
    first = infos[0]
    assert (first.version, first.author, first.api, first.worker, first.license) == \
        ("1.2.0", "Dellyx", 1, "worker", "LICENSE", )
    assert (first.name, first.description, first.status, first.dir) == \
        ("First plugin", "Fallback text", "ok", dir / "first")
    assert (infos[1].worker, infos[1].license) == (None, None)
    language.set_("us")
    first = find(dir)[0]
    assert (first.name, first.description) == ("First plugin", "Fallback text")


def test_name_without_language_file_is_the_id(tmp_path):
    """Without a language file the name is the id."""
    plugin_create(tmp_path, "without_text", texts={})
    info = find(tmp_path)[0]
    assert (info.name, info.description, info.status) == ("without_text", "", "ok")


def test_broken_plugin_json(tmp_path):
    """A broken plugin.json marks the plugin as broken."""
    plugin_create(tmp_path, "missing").joinpath("plugin.json").unlink()
    plugin_create(tmp_path, "no_json").joinpath("plugin.json").write_text("{broken", encoding="utf-8")
    plugin_create(tmp_path, "list").joinpath("plugin.json").write_text("[1]", encoding="utf-8")
    plugin_create(tmp_path, "api_text", data={"api": "1"})
    plugin_create(tmp_path, "version_number", data={"version": 2})
    plugin_create(tmp_path, "worker_number", data={"worker": 3})
    (tmp_path / "Gross-Name").mkdir()
    plugin_create(tmp_path, "core")
    infos = {i.id: i for i in find(tmp_path)}
    assert set(infos) == {"missing", "no_json", "list", "api_text", "version_number", "worker_number", "Gross-Name",
                          "core"}
    assert all(i.status == "broken" and i.error for i in infos.values()), {i.id: i.status for i in infos.values()}
    assert infos["missing"].name == "Missing"
    assert infos["Gross-Name"].name == "Gross-Name"
    assert [pid for pid in infos if not id_valid(pid)] == ["Gross-Name", "core"]


def test_wrong_api_version_is_incompatible(tmp_path):
    """A wrong API version makes the plugin incompatible."""
    dir = tmp_path / "plugins"
    plugin_create(dir, "new", data={"api": API_VERSION + 1},
                   code="raise RuntimeError('must not be imported')\n")
    settings = _settings(tmp_path)
    settings.plugins["new"] = True
    plugins = Plugins(tmp_path, settings)
    assert plugins.infos[0].status == "incompatible" and plugins.active() == []
    plugins.set_("new", True)
    assert plugins.infos[0].status == "incompatible" and f"{PACKET}.new" not in sys.modules
    assert not (tmp_path / "error.log").exists()


def test_disabled_plugins_are_not_imported(tmp_path):
    """Disabled plugins are never imported."""
    dir = tmp_path / "plugins"
    code = "from pathlib import Path\nPath(__file__).with_name('imported.txt').write_text('yes')\nraise RuntimeError('no')\n"
    plugin_create(dir, "still", code=code)
    plugins = Plugins(tmp_path, _settings(tmp_path))
    plugins.new_read()
    assert plugins.infos[0].status == "ok" and not plugins.enabled("still") and plugins.active() == []
    assert not (dir / "still" / "imported.txt").exists() and f"{PACKET}.still" not in sys.modules
    assert not (tmp_path / "error.log").exists()


def test_enabling_imports_and_remembers(tmp_path):
    """Enabling imports the plugin and remembers the state."""
    plugin_create(tmp_path / "plugins", "one")
    plugins = Plugins(tmp_path, _settings(tmp_path))
    assert plugins.active() == [] and f"{PACKET}.one" not in sys.modules
    plugins.set_("one", True)
    (info, plugin), = plugins.active()
    assert info.id == "one" and isinstance(plugin, Plugin) and plugin.api.id == "one"
    assert _saved(tmp_path)["plugins"] == {"one": True}
    new = Plugins(tmp_path, _settings(tmp_path))
    assert new.enabled("one") and [i.id for i, _ in new.active()] == ["one"]
    new.set_("one", False)
    assert new.active() == [] and _saved(tmp_path)["plugins"] == {"one": False}
    assert not Plugins(tmp_path, _settings(tmp_path)).enabled("one")


def test_import_errors_go_to_the_log(tmp_path):
    """Import errors are written to the error log."""
    dir = tmp_path / "plugins"
    plugin_create(dir, "throws", code="raise RuntimeError('broken on import')\n")
    plugin_create(dir, "create_throws", code="def create(api):\n    raise ValueError('broken in create')\n")
    plugin_create(dir, "no_plugin", code="def create(api):\n    return None\n")
    plugin_create(dir, "without_create", code="VALUE = 1\n")
    plugins = Plugins(tmp_path, _settings(tmp_path))
    for pid in ("throws", "create_throws", "no_plugin", "without_create"):
        plugins.set_(pid, True)
        assert plugins.info(pid).status == "error" and plugins.info(pid).error, pid
    assert plugins.active() == []
    log = (tmp_path / "error.log").read_text(encoding="utf-8")
    assert log.startswith("--- ") and "Plugin throws" in log and "RuntimeError: broken on import" in log
    assert "Plugin create_throws" in log and "ValueError: broken in create" in log
    assert "Plugin no_plugin" in log and "Plugin without_create" in log
    new = Plugins(tmp_path, _settings(tmp_path))
    assert new.info("throws").status == "error" and new.active() == []
    new.set_("throws", False)
    assert not new.enabled("throws")


def test_enabling_retries_after_an_error(tmp_path):
    """Enabling again retries after an error."""
    path = plugin_create(tmp_path / "plugins", "repaired", code="raise RuntimeError('still broken')\n")
    plugins = Plugins(tmp_path, _settings(tmp_path))
    plugins.set_("repaired", True)
    assert plugins.info("repaired").status == "error"
    plugins.new_read()
    assert plugins.info("repaired").status == "error"
    (path / "__init__.py").write_text("from soullink.plugin.api import Plugin\n\n\ndef create(api):\n"
                                      "    return Plugin(api)\n", encoding="utf-8")
    plugins.set_("repaired", False)
    plugins.set_("repaired", True)
    assert plugins.info("repaired").status == "ok" and [i.id for i, _ in plugins.active()] == ["repaired"]


def test_relative_import_and_core_module_ids(tmp_path):
    """Relative imports work and plugin ids may equal core module names."""
    path = plugin_create(tmp_path / "plugins", "language",
                          code="from soullink.plugin.api import Plugin\nfrom .help import VALUE\n\n\n"
                               "class P(Plugin):\n    value = VALUE\n\n\ndef create(api):\n    return P(api)\n")
    (path / "help.py").write_text("VALUE = 42\n", encoding="utf-8")
    plugins = Plugins(tmp_path, _settings(tmp_path))
    plugins.set_("language", True)
    (_, plugin), = plugins.active()
    assert plugin.value == 42 and sys.modules["soullink.language"] is language


def test_plugin_api(tmp_path):
    """The plugin API provides texts and settings."""
    plugin_create(tmp_path / "plugins", "one", code=WITH_SETTING,
                   texts={"us": "_name = One\ncolor = Color\ngreeting = Hello {name}\n"})
    settings = _settings(tmp_path)
    plugins = Plugins(tmp_path, settings)
    plugins.set_("one", True)
    api = plugins.api("one")
    assert api.id == "one" and api.dir == tmp_path / "plugins" / "one"
    assert api.t("greeting", name="Ash") == "Hello Ash" and api.t("color") == "Color"
    assert api.setting("color") == "red"
    plugins.value_set("one", "color", "blue")
    assert api.setting("color") == "blue" and _saved(tmp_path)["plugin_values"] == {"one": {"color": "blue"}}
    settings.plugin_values["one"]["color"] = "purple"
    assert api.setting("color") == "red"
    assert api.setting("exists_not") is None
    api.log("Something went wrong")
    log = (tmp_path / "error.log").read_text(encoding="utf-8")
    assert "Plugin one" in log and "Something went wrong" in log


@pytest.mark.parametrize("hook, call", [
    ("settings", None),
    ("display_names", lambda plugins: plugins.show()),
])
def test_error_in_a_hook_switches_the_plugin_off(tmp_path, hook, call):
    """An error in a hook switches the plugin off."""
    code = (f"from soullink.plugin.api import Plugin\n\n\nclass P(Plugin):\n    def {hook}(self):\n"
            "        raise KeyError('hook')\n\n\ndef create(api):\n    return P(api)\n")
    plugin_create(tmp_path / "plugins", "hook", code=code)
    plugins = Plugins(tmp_path, _settings(tmp_path))
    state = plugins.state
    plugins.set_("hook", True)
    if call is not None:
        assert plugins.info("hook").status == "ok"
        assert call(plugins) == []
    assert plugins.info("hook").status == "error" and plugins.active() == [] and plugins.state != state
    assert plugins.settings_of("hook") == []
    assert "KeyError: 'hook'" in (tmp_path / "error.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("definition", [
    "Setting('x', 'X', 'slider', 1)",
    "Setting('x', 'X', 'selection', 'purple', ('red', 'blue'))",
    "Setting('x', 'X', 'number', 3)",
    "Setting('x', 'X', 'switch', 1)",
])
def test_invalid_settings_are_an_error(tmp_path, definition):
    """Invalid settings count as a plugin error."""
    code = ("from soullink.plugin.api import Setting, Plugin\n\n\nclass P(Plugin):\n"
            f"    def settings(self):\n        return [{definition}]\n\n\n"
            "def create(api):\n    return P(api)\n")
    plugin_create(tmp_path / "plugins", "wrong", code=code)
    plugins = Plugins(tmp_path, _settings(tmp_path))
    plugins.set_("wrong", True)
    assert plugins.settings_of("wrong") == [] and plugins.info("wrong").status == "error"
    assert "invalid setting" in (tmp_path / "error.log").read_text(encoding="utf-8")


DEPENDENT = """from soullink.plugin.api import Setting, Plugin

CALLS = []


class P(Plugin):
    def settings(self):
        CALLS.append(1)
        list_ = [Setting("mode", "Mode", "selection", "exact", ("simple", "exact"))]
        if self.api.setting("mode") == "exact":
            list_.append(Setting("level", "Levels", "number", 2, (1, 2, 3)))
        return list_


def create(api):
    plugin = P(api)
    plugin.at_create = api.setting("mode")
    return plugin
"""


def test_dependent_settings_without_recursion(tmp_path):
    """Settings that depend on each other do not recurse."""
    plugin_create(tmp_path / "plugins", "dependent", code=DEPENDENT)
    plugins = Plugins(tmp_path, _settings(tmp_path))
    plugins.set_("dependent", True)
    (info, plugin), = plugins.active()
    assert info.status == "ok" and not (tmp_path / "error.log").exists()
    api = plugins.api("dependent")
    assert api.setting("mode") == "exact" and api.setting("level") == 2
    module = sys.modules[f"{PACKET}.dependent"]
    calls = len(module.CALLS)
    for _ in range(5):
        api.setting("level")
    assert len(module.CALLS) == calls
    assert [e.key for e in plugins.settings_of("dependent")] == ["mode", "level"]
    plugins.value_set("dependent", "mode", "simple")
    assert [e.key for e in plugins.settings_of("dependent")] == ["mode"]


def test_setting_in_create(tmp_path):
    """A setting can be read inside create()."""
    plugin_create(tmp_path / "plugins", "early", code=DEPENDENT)
    plugins = Plugins(tmp_path, _settings(tmp_path))
    plugins.set_("early", True)
    assert plugins.active()[0][1].at_create is None
    settings = _settings(tmp_path)
    settings.plugin_values["early"] = {"mode": "simple"}
    new = Plugins(tmp_path, settings)
    assert new.active()[0][1].at_create == "simple"


def test_after_an_error_in_create_the_plugin_is_imported_anew(tmp_path):
    """After an error in create() the plugin is imported again."""
    path = plugin_create(tmp_path / "plugins", "first_broken",
                          code="from .help import VALUE\n\n\ndef create(api):\n    raise RuntimeError(VALUE)\n")
    (path / "help.py").write_text("VALUE = 'broken'\n", encoding="utf-8")
    plugins = Plugins(tmp_path, _settings(tmp_path))
    plugins.set_("first_broken", True)
    assert plugins.info("first_broken").status == "error"
    assert not [n for n in sys.modules if n.startswith(f"{PACKET}.first_broken")]
    (path / "__init__.py").write_text("from soullink.plugin.api import Plugin\nfrom .help import VALUE\n\n\n"
                                      "class P(Plugin):\n    value = VALUE\n\n\ndef create(api):\n"
                                      "    return P(api)\n", encoding="utf-8")
    (path / "help.py").write_text("VALUE = 'repaired'\n", encoding="utf-8")
    plugins.set_("first_broken", False)
    plugins.set_("first_broken", True)
    (_, plugin), = plugins.active()
    assert plugin.value == "repaired"


def test_disabled_plugins_run_no_hook(tmp_path):
    """Disabled plugins run no hook."""
    plugin_create(tmp_path / "plugins", "away", code=WITH_SETTING, texts={"us": "color = Color\n"})
    plugins = Plugins(tmp_path, _settings(tmp_path))
    plugins.set_("away", True)
    assert plugins.api("away") is not None and plugins.safe("away", lambda p: "ran") == "ran"
    plugins.settings.plugins["away"] = False
    assert plugins.safe("away", lambda p: "ran", "not") == "not"
    plugins.set_("away", False)
    assert plugins.api("away") is None and plugins.value("away", "color") is None
    assert plugins.safe("away", lambda p: "ran", "not") == "not"
    plugins.set_("away", True)
    assert plugins.value("away", "color") == "red"
    import shutil

    shutil.rmtree(tmp_path / "plugins" / "away")
    plugins.new_read()
    assert plugins.api("away") is None and plugins.safe("away", lambda p: "ran", "not") == "not"


def test_displays_of_active_plugins(tmp_path):
    """The displays of active plugins are listed."""
    code = ("from soullink.plugin.api import Plugin\n\n\nclass P(Plugin):\n    def display_names(self):\n"
            "        return [('list', 'List'), ('map', 'Map')]\n\n\ndef create(api):\n    return P(api)\n")
    plugin_create(tmp_path / "plugins", "an", code=code)
    plugin_create(tmp_path / "plugins", "from", code=code)
    plugins = Plugins(tmp_path, _settings(tmp_path))
    assert plugins.show() == []
    plugins.set_("an", True)
    assert plugins.show() == [("an.list", "List"), ("an.map", "Map")]


def test_field_display():
    """The free-field display falls back sensibly."""
    assert field_display("", []) == CORE_DISPLAY
    assert field_display("", ["a.list", "b.map"]) == "a.list"
    assert field_display("b.map", ["a.list", "b.map"]) == "b.map"
    assert field_display("away.list", ["a.list"]) == "a.list"
    assert field_display(ALTERNATING, []) == ALTERNATING and field_display(CORE_DISPLAY, ["a.x"]) == CORE_DISPLAY


def test_base_class_has_all_hooks_without_effect():
    """The base class provides every hook without effect."""
    plugin = Plugin(None)
    assert plugin.settings() == [] and plugin.display_names() == []
    assert plugin.fits(None) is True and plugin.process_group(None) is False
    assert plugin.session_start(None) is None and plugin.update(0.016) is None
    assert plugin.event(1, ("sram",)) is None and plugin.player_menu(1) == [] and plugin.overlay_tab(1) == []
    assert plugin.display("list") is None and plugin.draw_game_frame(None, 1, None, None) is None
    assert plugin.symbols(1) == [] and plugin.runs_in_menu(1) is False and plugin.fast_forward_allowed(1) is True
    assert plugin.save() is None and plugin.session_end() is None
    e = Setting("x", "X", "number", 3, (1, 2, 3))
    assert e.display is None and e.values == (1, 2, 3)
