"""Tests of the screen layout."""

from soullink.layout import Rect, compute, compute_ds, logical_resolution, grid


def test_grid():
    """The grid size follows the player count."""
    assert [grid(n) for n in (1, 2, 3, 4)] == [(1, 1), (2, 1), (2, 2), (2, 2)]


def test_one_player_1080p():
    """One player on 1080p fills the screen."""
    (z,) = compute(1, 1920, 1080)
    assert z.game == Rect(150, 0, 1620, 1080)
    assert z.margin == Rect(0, 0, 150, 1080) and z.vertical


def test_two_players_1080p():
    """Two players on 1080p split the screen."""
    a, b = compute(2, 1920, 1080)
    assert a.cell == Rect(0, 0, 960, 1080) and b.cell == Rect(960, 0, 960, 1080)
    assert b.game == Rect(960, 220, 960, 640)
    assert b.margin == Rect(960, 0, 960, 220) and not b.vertical


def test_four_players_1080p():
    """Four players on 1080p form a 2x2 grid."""
    cells = compute(4, 1920, 1080)
    assert len(cells) == 4
    assert cells[3].game == Rect(960 + 75, 540, 810, 540)
    assert cells[3].margin.w == 75 and cells[3].vertical


def test_four_players_800p_without_margin():
    """On 800p the four cells need no label margin."""
    cells = compute(4, 1280, 800)
    assert cells[0].game == Rect(20, 0, 600, 400)
    assert cells[0].margin is None


def test_three_players_have_four_cells():
    """Three players still use four cells."""
    assert len(compute(3, 1920, 1080)) == 4


def test_logical_resolution():
    """The logical resolution is capped."""
    assert logical_resolution(3840, 2160) == (1920, 1080)
    assert logical_resolution(2560, 1440) == (1920, 1080)
    assert logical_resolution(1280, 800) == (1280, 800)


def test_ds_columns_four_players():
    """Four DS players in columns share the width."""
    cells = compute_ds(4, 1920, 1080, "columns")
    assert len(cells) == 4
    z = cells[1]
    assert z.large == Rect(480, 180, 480, 360) and z.small == Rect(480, 540, 480, 360)
    assert z.free == Rect(480, 0, 480, 180) and not z.vertical


def test_ds_columns_one_player_uses_the_margin():
    """A single DS column uses the label margin."""
    (z,) = compute_ds(1, 1920, 1080, "columns")
    assert z.large == Rect(600, 0, 720, 540) and z.small == Rect(600, 540, 720, 540)
    assert z.free == Rect(0, 0, 600, 1080) and z.vertical


def test_ds_hybrid_four_players_side_by_side():
    """Four DS players in hybrid view put the small screen beside the large one."""
    cells = compute_ds(4, 1920, 1080, "hybrid")
    assert len(cells) == 4
    z = cells[0]
    assert z.large == Rect(0, 30, 640, 480)
    assert z.small == Rect(640, 270, 320, 240)
    assert z.free == Rect(640, 30, 320, 240)


def test_ds_hybrid_two_players_stacked():
    """Two DS players in hybrid view stack the small screen below."""
    a, b = compute_ds(2, 1920, 1080, "hybrid")
    assert b.large == Rect(960, 0, 960, 720)
    assert b.small == Rect(1440, 720, 480, 360)
    assert b.free == Rect(960, 720, 480, 360)


def test_ds_hybrid_three_players_have_four_cells():
    """Three DS players in hybrid view use four cells."""
    assert len(compute_ds(3, 1920, 1080, "hybrid")) == 4
    assert len(compute_ds(3, 1920, 1080, "columns")) == 3
