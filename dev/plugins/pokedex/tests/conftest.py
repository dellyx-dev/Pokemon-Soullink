"""Fixtures of the Pokedex plugin tests."""
from pathlib import Path

import pytest

from soullink import language

PLUGIN = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def pokedex_texts(english):
    """Registers the plugin's language files like the loader does; the "english" fixture unregisters them again."""
    language.plugin_texts("pokedex", PLUGIN)


@pytest.fixture
def pokedex_api():
    """What the tab needs from the GameApi: api.t, dex(nr) and dex_error(nr), with the return values set through .dex_value
    and .error."""
    class FakeApi:
        """Fake game API."""
        id = "pokedex"
        dex_value = None
        error = None

        @staticmethod
        def t(key, **values):
            """Text from the plugin's language files."""
            return language.t(f"pokedex.{key}", **values)

        def dex(self, nr):
            """The prepared dex."""
            return self.dex_value

        def dex_error(self, nr):
            """The prepared error."""
            return self.error

    return FakeApi()
