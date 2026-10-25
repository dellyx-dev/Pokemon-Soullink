"""Test helpers of the partner plugin: texts and an app with only the partner plugin."""
import shutil
from pathlib import Path

import pytest

from soullink import language

PLUGIN = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def partner_texts(english):
    """Registers the partner plugin language files."""
    language.plugin_texts("partner", PLUGIN)


@pytest.fixture
def partner_app(monkeypatch, tmp_path):
    """Dummy app with a copy of the partner plugin under <base>/plugins, switched on."""
    from ui_helpers import dummy_app

    a = dummy_app(monkeypatch, tmp_path)
    shutil.copytree(PLUGIN, tmp_path / "plugins" / "partner", ignore=shutil.ignore_patterns("tests", "__pycache__"))
    a.plugins.new_read()
    a.plugins.set_("partner", True)
    assert [i.id for i, _ in a.plugins.active()] == ["partner"]
    yield a
    a.close()
