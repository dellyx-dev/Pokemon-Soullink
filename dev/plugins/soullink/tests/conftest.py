"""Test helpers of the Soullink plugin: the plugin texts in every test, an app with the plugin on, text API."""
import shutil
from pathlib import Path

import pytest

from soullink import language

PLUGIN = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def soullink_texts(english):
    """Registers the plugin's language files like the loader does; the "english" fixture unregisters them again."""
    language.plugin_texts("soullink", PLUGIN)


@pytest.fixture
def api():
    """Only the plugin API texts (api.t), for tabs without a running game."""
    class TextApi:
        """Fake plugin API that only provides texts."""
        id = "soullink"

        @staticmethod
        def t(key, **values):
            """Text from the plugin's language files."""
            return language.t(f"soullink.{key}", **values)

    return TextApi()


@pytest.fixture
def app(monkeypatch, tmp_path):
    """Dummy app with the Soullink plugin (copy under <base>/plugins/soullink), switched on."""
    from ui_helpers import dummy_app

    a = dummy_app(monkeypatch, tmp_path)
    shutil.copytree(PLUGIN, tmp_path / "plugins" / "soullink", ignore=shutil.ignore_patterns("tests", "__pycache__"))
    a.plugins.new_read()
    a.plugins.set_("soullink", True)
    assert [i.id for i, _ in a.plugins.active()] == ["soullink"]
    yield a
    a.close()
