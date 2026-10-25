"""Tests of the graphics helpers."""

import pygame

from soullink.ui import graphics


def test_poppins_is_bundled():
    """The Poppins font files are bundled."""
    for weight in ("Regular", "Medium", "SemiBold", "Bold", "ExtraBold"):
        assert (graphics.FONTS / f"Poppins-{weight}.ttf").exists()
    pygame.font.init()
    assert graphics.load_font(30, "Bold").size("Pokémon")[0] > 0


def test_surfaces_are_cached():
    """Rendered surfaces are cached."""
    a = graphics.rounded_rect((200, 60), 16, (255, 255, 255, 16), 2, (255, 255, 255, 30))
    assert a is graphics.rounded_rect((200, 60), 16, (255, 255, 255, 16), 2, (255, 255, 255, 30))
    assert a.get_size() == (200, 60)
    assert graphics.gradient_rect((300, 80), 20).get_size() == (300, 80)


def test_player_colors_and_shorten():
    """Player colors cycle and text is shortened to fit."""
    assert graphics.player_color(1) != graphics.player_color(2)
    assert graphics.player_color(5) == graphics.player_color(1)
    pygame.font.init()
    lang = "A very long session name that never fits into a card"
    shortened = graphics.shorten(lang, 30, 200)
    assert shortened.endswith("…") and graphics.load_font(30).size(shortened)[0] <= 200


def test_components_draw_without_error():
    """All components draw without errors."""
    pygame.font.init()
    area = pygame.Surface((1280, 720))
    area.blit(graphics.background((1280, 720)), (0, 0))
    graphics.card(area, (100, 100, 400, 70), chosen=True)
    graphics.panel(area, (100, 200, 400, 200))
    graphics.badge(area, (120, 450), 3, 20)
    graphics.footer(area, [("A", "Select"), ("<>", "Change"), ("SELECT", "Back")])
    graphics.spinner(area, (600, 600), 20, 1.5)


def _visible_texts():
    """String literals of the user interface without docstrings, plus the game names."""
    import ast
    from pathlib import Path

    from soullink import roms

    texts = []
    dir = Path(graphics.__file__).resolve().parents[1]
    for file in [*dir.joinpath("ui").glob("*.py"), dir / "image.py"]:
        tree = ast.parse(file.read_text(encoding="utf-8"))
        docstrings = {id(k.body[0].value) for k in ast.walk(tree)
                      if isinstance(k, (ast.Module, ast.ClassDef, ast.FunctionDef)) and k.body
                      and isinstance(k.body[0], ast.Expr) and isinstance(k.body[0].value, ast.Constant)}
        texts += [(f"{file.name}:{k.lineno}", k.value) for k in ast.walk(tree)
                  if isinstance(k, ast.Constant) and isinstance(k.value, str) and id(k) not in docstrings]
    texts += [("Game name", n) for n in [*roms.GEN3.values(), *roms.GEN45.values()]]
    from soullink import language

    for file in sorted(language.dir().glob("*.txt")):
        texts += [(f"{file.name}:{k}", v) for k, v in language.read_file(file).items()]
    return texts


def test_poppins_has_all_visible_characters():
    """Poppins has every visible character used in the texts."""
    pygame.font.init()
    font = graphics.load_font(30, "Medium")

    def image(z):
        """Renders a character and returns its pixels."""
        s = font.render(z, True, (255, 255, 255), (0, 0, 0))
        return s.get_size(), pygame.image.tobytes(s, "RGB")

    replacement = image(chr(0xE000))
    missing = {(location, z) for location, text in _visible_texts() for z in set(text) if ord(z) > 32 and image(z) == replacement}
    assert not missing, sorted(missing)


def test_pokeball_as_ico():
    """The Pokeball renders as a Windows icon."""
    import struct

    from soullink.ui import graphics

    data = graphics.ico_data((16, 256))
    assert struct.unpack("<HHH", data[:6]) == (0, 1, 2)
    width, height, _, _, _, bpp, length, offset = struct.unpack("<BBBBHHII", data[22:38])
    assert (width, height, bpp) == (0, 0, 32)
    assert data[offset:offset + 4] == b"\x89PNG" and offset + length == len(data)


def test_button_row_centered_and_shortened():
    """The button row is centered and shortened to fit."""
    import pygame

    from soullink.ui import graphics

    pygame.font.init()
    area = pygame.Surface((400, 60), pygame.SRCALPHA)
    entries = [("A", "Select"), ("B", "Back"), ("X", "Something long"), ("Y", "And even more")]
    graphics.button_row(area, (200, 30), entries, 24, 16, 20, 300)
    drawn = pygame.mask.from_surface(area).get_bounding_rects()
    left, right = min(r.left for r in drawn), max(r.right for r in drawn)
    assert right - left <= 300
    assert abs((left + right) / 2 - 200) <= 6
