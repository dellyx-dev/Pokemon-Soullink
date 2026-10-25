# Writing plugins

Everything beyond emulation, input, audio, sessions and menus is a plugin. **Plugins are plain Python with full
access to the computer – there is no sandbox.**

**Start:** copy `docs/plugin-example/hello/` into `<data folder>/plugins/`. The bundled plugins in `dev/plugins/` show
the rest:

| Plugin | Shows |
|---|---|
| `pokedex` | a single overlay tab |
| `soullink` | tabs, free panel, player menu, session data |
| `coplayer` | worker part, drawing over the game frame, main menu setting |
| `link_cable_gba` | ProcessGroup, pause and fast forward |

## Folder

```
<data folder>/plugins/<id>/        <id> = folder name: a-z, 0-9, _ ("core" is reserved)
  plugin.json                       {"version": "1.0.0", "author": "...", "api": 1, "worker": "worker", "license": "LICENSE"}
  __init__.py                       def create(api) -> Plugin
  worker.py                         optional, only with "worker": runs in the player process
  language/de.txt, language/us.txt  required: _name, _description and all texts of the plugin
  tests/test_<id>_*.py              optional, run with the whole suite
```

## Rules

- **`"api"`** must equal `soullink.plugin.api.API_VERSION` (1), else the plugin is grey ("incompatible").
- **Off by default:** switched on under Settings → Plugins. A plugin that is off is never imported.
- **Imports:** the plugin is `soullink_plugins.<id>` (relative imports work). Available: standard library, pygame,
  numpy, `soullink.*`; other libraries only as pure Python in the own folder.
- **Independent:** never import or read another plugin; shared code belongs in the core
  (`dev/tests/test_plugins_alone.py` checks this).
- **Texts:** `api.t("key", **values)` from the plugin's `de.txt`/`us.txt` (fallback German); core keys win, so pick
  own names. No texts in the code.

## The plugin class

`create(api)` returns a `soullink.plugin.api.Plugin`; every method is optional.

| Method | Purpose |
|---|---|
| **Setup** | |
| `settings() -> list[Setting]` | main menu settings (`switch`, `selection`, `number`), shown while the plugin is on |
| `display_names() -> list[(id, title)]` | displays offered for the free panel |
| `fits(session)` | `True` active · `str` grey in the "Plugins" submenu with this reason · `False` not responsible, hidden · `None`/`""` grey with a general reason |
| `process_group(session) -> bool` | GBA: all players in one process (needed for mGBA lockstep) |
| **Game** | |
| `session_start(game: GameApi)` / `session_end()` | game start: create state · game end: clean up |
| `update(dt)` | every frame |
| `event(nr, e)` | from the player process: `("sram",)`, `("ram", blocks)`, `("ready", info)`, `("plugin", id, reply)` (own replies only) |
| `save()` | autosave and end of the game |
| **Display** | |
| `player_menu(nr) -> list[MenuEntry]` | rows under "Plugins" in the player menu (action, switch, grey with `reason`) |
| `overlay_tab(nr) -> list[Tab]` | overlay tabs, sorted by `position`; `replaced` = id of a tab to replace |
| `display(id) -> Display` | content for the free panel |
| `draw_game_frame(area, nr, target, source)` | draw over the game frame, clipped to `target`; `source` is "gba", "top" or "bottom" |
| `symbols(nr) -> list[str]` | symbols in the player label (names from `soullink.image.draw_symbol`) |
| **Behaviour** | |
| `runs_in_menu(nr) -> bool` | `True`: the game keeps running while the own menu is open |
| `fast_forward_allowed(nr)` | `False` or `str` (notice) blocks fast forward |

- **Tab positions:** Soullink 10, Opponent 20, Level 30, Types 40 (core), Pokédex 50. If two plugins replace the same
  tab, the first id wins.
- **Life cycle:** one object lives across games; create all state in `session_start` (the old game's `session_end`
  always runs first). `fits()` and `process_group()` must not keep state; `api.setting()` is `None` in `create()`.
- **Errors:** an exception in a hook is logged to `error.log`, the plugin is off for the rest of this game and the
  players see a notice.

## GameApi (argument of `session_start`)

Like `api` (`t`, `setting`, `log`) plus:

| Member | Returns / does |
|---|---|
| `session`, `playtime` | the session (folder, players), seconds played |
| `data_dir` | `Sessions/<name>/plugins/<id>/` for own files (write through `soullink.atomic`) |
| `player_numbers()`, `player_info(nr)` | player numbers · system, code, family, rom, game_name, dir, color |
| `ready_info(nr)` | report of the player process; `["plugins"][id]` = `ready()` of the worker part |
| `dex(nr)`, `dex_error(nr)` | data of the player's randomized ROM, loaded in the background (`None` until ready) |
| `location_name(nr, location)`, `location_key(nr, location)` | name of a location · key that counts same-named locations as one |
| `ram_request()` | RAM dump of all players, arrives as `event(nr, ("ram", ...))` |
| `report(nr, text)`, `overlay_open(nr, tab_id)` | notice for a player · open the overlay on a tab |
| `worker_command(nr, data)`, `worker_data(nr)` | command to the worker part · its latest data slot |

**Core helpers** (details in their docstrings):

- `soullink.pokemon_data`: Pokémon records of gen 3/4/5.
- `soullink.ui.graphics`, `soullink.ui.pokemon_components`: UI building blocks.
- `soullink.world`: player position, map keys shared across players, party icons; usable in the worker too (see
  `coplayer`, `partner`).

## Worker part (`worker.py`)

Runs at the emulator's pace in the player process, e.g. to read memory or use link functions. Set
`"worker": "worker"` in `plugin.json`; the module has `create(core, job, shared) -> part | None`.

- Loaded **without** `__init__.py` (shared code in sibling modules), no pygame.
- `job`: `nr`, `rom`, `base` (data folder), `group` (True in the ProcessGroup), and more.
- `shared`: one dict per plugin and process; in the ProcessGroup shared by all player threads (use a lock).
- `core`: `ram_blocks()`, `read(address, length)`, `can_link`/`link_*`, `can_network`/`network_*`.
- `part` (all optional): `ready() -> dict`; `before_image()`/`after_image() -> bytes | None` around every frame (max.
  1024 bytes → `game.worker_data(nr)`); `command(data) -> reply` (→ `("plugin", id, reply)`); `end()`.
- An exception only switches off the part and reports `("plugin_error", id, traceback)`.

## Tests

- In `dev/plugins/<id>/tests/`, run from `dev/` with the whole suite or alone:
  `.venv\Scripts\python -m pytest -q -p no:cacheprovider -c pytest.ini plugins/<id>`.
- Fixtures: `plugin_app(*ids)`, `worker_parts` and ROMs in `dev/plugins/conftest.py`; `FakeProcess`, `fake_session`,
  `input` in `dev/tests/ui_helpers.py`.
- Prefix test files and own fixtures with the plugin id (names are shared across plugins).
