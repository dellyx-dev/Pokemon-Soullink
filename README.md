# Pokemon-Soullink

![Pokémon Soullink: up to 4 randomized Pokémon games on one screen](docs/images/banner.png)

Pokemon-Soullink runs up to 4 randomized Pokémon games side by side in one window. Made for Soullink runs on the
couch or via Steam Remote Play Together.

- **Up to 4 games at once:** GBA (gen 3) or NDS (gen 4/5), every player with their own controller, key profile and
  randomizer seed.
- **Soullink built in:** catch list per location, filled live from the games, dead pairs, level caps of the gyms.
- **Help while playing:** opposing types in battle, type chart and the Pokédex of your own randomized ROM – as an
  overlay over your game, while the others keep playing.
- **Together in the game world:** see the other players in your world, let your first Pokémon follow you, trade and
  battle over a virtual link cable.
- **Made with controllers in mind:** that is where it plays best. A keyboard works too and can do everything, but
  only as a fallback – the interface is designed around controller buttons, not keyboard keys.
- **Steam Controller:** start the program from within Steam (add it as a non-Steam game), otherwise all Steam
  Controllers act as one keyboard.
- **Windows**, and the Steam Deck through Proton (add the exe as a non-Steam game).

## Screenshots

> [!NOTE]
> **The screenshots show German game editions.** Dialogs, Pokémon and location names inside the games are German
> because of that; the program itself is shown in English. The games always run in the language of your ROMs.

### In action

<p align="center">
  <img src="docs/images/hero.webp" width="720" alt="Four players walk through LeafGreen and Sapphire at the same time; player 1 opens the Soullink list while the others keep playing">
  <br>
  <sub>4 players at once – player 1 checks the Soullink list while the others keep playing</sub>
</p>

### Up to 4 players

| 4 players, GBA | 3 players, NDS in columns |
|---|---|
| ![Four GBA games: LeafGreen and Sapphire](docs/images/gba-4-players.png) | ![Three SoulSilver games, top and bottom screen in columns](docs/images/nds-columns.png) |

| NDS hybrid view with the Soullink list in the free area |
|---|
| ![Three SoulSilver games in the hybrid view; the fourth area shows the Soullink list](docs/images/nds-hybrid.png) |

### Starting a session

| New session | Randomizing |
|---|---|
| ![Players, games, randomizer preset and session name with a layout preview](docs/images/new-session.png) | ![Every player's ROM is randomized with its own seed](docs/images/randomizing.png) |

| Assign controllers | Key profiles |
|---|---|
| ![Every player presses A and picks a key profile](docs/images/controller-assignment.png) | ![Editing a key profile and naming a new one](docs/images/key-profile.png) |

### Overlay (hold L2)

Tabs over your own game; L/R switches between them while the other players keep playing.

![In a wild battle player 1 pages through the tabs: opponent, level caps, type chart, Pokédex with details and the Soullink list](docs/images/overlay.webp)

| Soullink list | Pokédex details |
|---|---|
| ![Catches of all players per location, dead pairs greyed out](docs/images/overlay-soullink.png) | ![Stats, evolution and level-up moves of one Pokémon](docs/images/overlay-pokedex-details.png) |

### Player menu (press L2)

| Player menu | Plugins | Remap keys in game |
|---|---|---|
| ![Continue, volume, overlay, plugins, remap, save](docs/images/player-menu.png) | ![Switches of the plugins for this player](docs/images/player-menu-plugins.png) | ![Waiting for the new key for GBA-L](docs/images/keys-in-game.png) |

### In the game world

Each player sees where the others are, shown as their first Pokémon with a marker, live while they walk. And your
own first Pokémon follows you.

![Two players in LeafGreen walk towards each other; each one sees the other's Pokémon and marker move](docs/images/other-players.webp)

| Link cable plugged in | Both players in the Union Room |
|---|---|
| ![Link cable switched on in the plugins menu](docs/images/link-cable-plugged-in.png) | ![Each player sees the other one in the SoulSilver Union Room](docs/images/link-cable.png) |

### Menus

| Main menu | Continue session |
|---|---|
| ![Main menu](docs/images/main-menu.png) | ![Saved sessions with play time](docs/images/resume.png) |

| Settings | Plugins in the settings |
|---|---|
| ![General, game and folder settings](docs/images/settings.png) | ![Plugins switched on and their settings](docs/images/settings-plugins.png) |

## ROMs

**No games or ROMs are included.** You have to provide your own ROM files, dumped from game cartridges you own.
Downloading ROMs of games you do not own is illegal in most countries. Put them (`.gba`, `.nds` or `.zip`) into
`roms\gba` and `roms\nds`.

## Installation

1. Extract the release zip anywhere and start `Pokemon-Soullink\Pokemon-Soullink.exe`. The folder is portable:
   settings, sessions and ROMs stay inside it. To update, extract the new zip over it – your data is kept.
2. Install **Java 8 or newer (64-bit)**. It is needed for randomizing and the Pokédex data, only on the PC that hosts
   the game.
3. A standard randomizer preset is included. For your own, create settings in the
   [Universal Pokemon Randomizer ZX](https://github.com/Ajarmar/universal-pokemon-randomizer-zx), save them as `.rnqs`
   ("Save Settings") and put the file into `presets\`.
4. Under **Settings** check the ROM folders and switch on the plugins you want (all plugins start switched off).

## Playing

1. **New session:** number of players, a game and a name per player, preset → "Go!". A session is either GBA or NDS.
2. **Assign controllers:** everybody presses A one after another, then picks a **key profile** in their card:
   Default, an own one or "+ New profile". Y adjusts a profile, X deletes it (after a confirmation). Profiles are
   separate for controller and keyboard and for GBA and NDS.
3. **Play.** The game saves automatically every 5 minutes and with "Save" in the player menu.
4. **Resume:** choose the session and assign the controllers again. X deletes a session (type `DELETE` to confirm).

## Music

No music is included – bring your own. Put music files (`.mp3`, `.ogg`, `.wav`, `.flac` or `.opus`) into `sound\`;
they play in random order, in the menus and during the game.

- **Volume:** in the settings and in the player menu ("Music", applies to everybody). A on "Music" in the player menu
  mutes it and turns it back on.
- **Other folder:** Settings → Music folder.
- **Game sound** has its own volume per player in the player menu ("Game").

## Controls

Keys as printed on an Xbox controller:

| Key | GBA | NDS |
|---|---|---|
| D-pad / left stick, A, B, L, R, Start, Select | as on the console | as on the console |
| X / Y | – | X / Y |
| L2 short | **player menu** | **player menu** |
| L2 held | **overlay** (tabs, L/R to switch) | **overlay** |
| R3 | fast forward on/off | fast forward on/off |
| R2 / right stick | – | tap / move touch cursor |
| L3 | – | swap screens |

- **Player menu:** continue, game and music volume, NDS view (Hybrid or Columns), touch with d-pad, overlay, plugins,
  change controller, bind keys, save.
- **Keyboard:** arrows, X = A, Y/Z = B, A = L, S = R, Enter = Start, Backspace = Select, Tab/Esc = menu,
  Space = fast forward, T = overlay; NDS: C = X, V = Y, Q = swap screens. The mouse taps the lower DS screen.
- **Menus:** A selects, B goes back, Start = done. Holding a direction repeats. Y opens the search in lists.
- **Own default binding:** copy `default-keys.json` into the data folder and change it there.

## Plugins

Everything beyond playing comes from plugins in `plugins\`, switched on under **Settings → Plugins**. In the game they
appear in the player menu (**More → Plugins**), as overlay tabs and in the free screen area.

| Plugin | What it does |
|---|---|
| Soullink | Catch list per route, filled live from the games; mark pairs dead; level caps of the gym leaders |
| Opponent | Types of the opposing Pokémon in battle and what not to send in |
| Pokédex | All Pokémon of your own randomized ROM with types, stats, evolutions and moves |
| Other players | Shows the other players in your world, if they play the same region |
| Partner | Your first Pokémon follows you in the overworld (not in HeartGold/SoulSilver) |
| Link cable GBA / NDS | Trade and battle between the players as on real hardware |

**Caution:** plugins are Python code with full access to your computer – only use plugins from a trusted source.
Writing plugins: [docs/plugins.md](docs/plugins.md).

## Steam Remote Play Together

1. Copy the program files (`Pokemon-Soullink.exe`, `_internal\`, `core\`, `randomizer\`, `language\`, `licenses\`,
   `default-keys.json`) into the folder of any Steam game you own that supports Remote Play Together, and save
   `Pokemon-Soullink.exe` there under the name of the game's exe. Repeat after every update.
2. Put a `soullink-base.txt` beside it, so your sessions and settings are used from your Pokemon-Soullink folder. Its
   only line is the path of that folder, for example:
   ```
   D:\Games\Pokemon-Soullink
   ```

## Languages

German and English are included (`language\de.txt`, `us.txt`). For a new language copy `us.txt`, rename it (e.g.
`fr.txt`) and translate the texts right of the `=`.

Every plugin brings its own texts in `plugins\<plugin>\language\`. Translate them the same way with a file of the same
name (e.g. `plugins\soullink\language\fr.txt`).

## Troubleshooting

- **Crash or plugin error:** see `error.log` in the program folder.
- **A game crashed:** press A in its screen area; it restarts from the last autosave.
- **Self-test:** `Pokemon-Soullink.exe --selftest <game.gba> selftest.txt` checks core, Java, randomizer and saving.
- **"Java missing":** install Java (see Installation) or set `JAVA_HOME`.
- **Unknown controller with analog triggers** (no SDL mapping): the setup wizard may take releasing a trigger as the
  next key. Then press Esc and set up again.

## Roadmap

Planned for version 2.0.0, without a date yet – plans can still change:

- **Online multiplayer:** every player runs their own game on their own PC, and the others see it as a stream. Only
  game data is shared – catches, dead Pokémon, positions in the world – so no ROMs are passed around.
- **More systems:** since every game runs on its own PC, other systems can follow later, for example 3DS or Switch.

## Development

Pokemon-Soullink is written in Python 3.13 with pygame-ce. Every game runs in the libretro cores mGBA (GBA) and
melonDS DS (NDS), loaded through ctypes in its own worker process; randomizing uses the Universal Pokemon Randomizer
ZX through Java. All source code is in `dev/`, the plugins in `dev/plugins/`. How to write a plugin:
[docs/plugins.md](docs/plugins.md).

All commands run in `dev/` on Windows.

**Set up** a virtual environment with Python 3.13 and install the dependencies:

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

**Start** the program from source. With the environment variable `SOULLINK_WINDOW=1` it opens in a window instead of
full screen.

```
.venv\Scripts\python -m soullink
```

**Test.** Tests with real games only run when `SOULLINK_TEST_ROM` (GBA), `SOULLINK_TEST_NDS` and
`SOULLINK_TEST_PRESET` point to a ROM and a randomizer preset; otherwise they are skipped.

```
.venv\Scripts\python -m pytest -q
```

**Build** the portable program folder `../build/` and the release zip in `../release/`:

```
.venv\Scripts\python ..\build.py --zip
```

**Rebuild the mGBA core.** It is an own build with link cable support (`dev/tools/mgba/`) and needs LLVM-MinGW, CMake
and Ninja. melonDS DS 1.4.0 is used unchanged.

```
.venv\Scripts\python tools\mgba_build.py
```

**Rebuild the Java helper** for the Pokédex data (needs a JDK):

```
.venv\Scripts\python tools\dex_build.py
```

## Credits

This project was developed with the help of AI (Claude by Anthropic); all code and documentation were reviewed by me.

## License

Pokemon-Soullink is free software under the [GNU General Public License v3.0](LICENSE). Bundled third-party software
keeps its own license, see [dev/licenses/THIRD_PARTY.md](dev/licenses/THIRD_PARTY.md) or **About** in the program.

Pokémon is a registered trademark of Nintendo, Creatures Inc. and GAME FREAK inc. Pokemon-Soullink is an unofficial
fan project, not affiliated with or endorsed by Nintendo, The Pokémon Company, Creatures or GAME FREAK.
