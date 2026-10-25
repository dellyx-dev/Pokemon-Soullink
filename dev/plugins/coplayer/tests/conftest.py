"""Test helpers of the coplayer plugin: its texts, an app with the plugin switched on and small icon ROMs."""
import shutil
from pathlib import Path

import pytest

from conftest import test_rom  # noqa: F401
from soullink import language
from world_helpers import gen5_icon_rom, icon_rom, nds_icon_rom  # noqa: F401

PLUGIN = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def coplayer_texts(english):
    """Registers the plugin's language files like the loader does; the "english" fixture unregisters them again."""
    language.plugin_texts("coplayer", PLUGIN)


@pytest.fixture
def app(monkeypatch, tmp_path):
    """Dummy app with the Other players plugin (copy under <base>/plugins/coplayer), switched on."""
    from ui_helpers import dummy_app

    a = dummy_app(monkeypatch, tmp_path)
    shutil.copytree(PLUGIN, tmp_path / "plugins" / "coplayer",
                    ignore=shutil.ignore_patterns("tests", "__pycache__"))
    a.plugins.new_read()
    a.plugins.set_("coplayer", True)
    assert [i.id for i, _ in a.plugins.active()] == ["coplayer"]
    yield a
    a.close()

