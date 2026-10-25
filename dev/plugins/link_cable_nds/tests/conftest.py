"""Test helpers of Link cable NDS: the plugin texts in every test (ROMs and worker helpers: plugins/conftest.py)."""
from pathlib import Path

import pytest

from soullink import language

PLUGIN = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def link_cable_nds_texts(english):
    """Registers the plugin's language files like the loader does; the "english" fixture unregisters them again."""
    language.plugin_texts("link_cable_nds", PLUGIN)
