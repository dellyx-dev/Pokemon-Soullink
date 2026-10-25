"""Every bundled plugin works on its own: it imports with no other plugin beside it, main part and worker part."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BUNDLED

DEV = Path(__file__).resolve().parents[1]
PLUGINS = sorted(d.name for d in BUNDLED.iterdir() if (d / "plugin.json").exists())


@pytest.mark.parametrize("plugin_id", PLUGINS)
def test_plugin_imports_without_the_other_plugins(plugin_id, tmp_path):
    """Copies one plugin alone into an empty plugin folder and imports its package and worker module there."""
    shutil.copytree(BUNDLED / plugin_id, tmp_path / plugin_id, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    modules = [plugin_id]
    worker = json.loads((BUNDLED / plugin_id / "plugin.json").read_text(encoding="utf-8")).get("worker")
    if worker:
        modules.append(f"{plugin_id}.{worker}")
    code = (
        "import importlib, sys, types\n"
        "package = types.ModuleType('soullink_plugins')\n"
        f"package.__path__ = [{str(tmp_path)!r}]\n"
        "sys.modules['soullink_plugins'] = package\n"
        f"for name in {modules!r}:\n"
        "    importlib.import_module('soullink_plugins.' + name)\n"
    )
    output = subprocess.run([sys.executable, "-c", code], cwd=DEV, capture_output=True, text=True, timeout=60,
                            env={**os.environ, "PYTHONPATH": str(DEV), "PYGAME_HIDE_SUPPORT_PROMPT": "1"})
    assert output.returncode == 0, output.stderr
