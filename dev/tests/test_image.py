"""Tests of image scaling and symbols."""

import pygame
import pytest

from soullink import image


def test_between_factor():
    """The intermediate scale factor is an integer multiple."""
    assert image.between_factor((240, 160), (810, 540)) == 3
    assert image.between_factor((240, 160), (200, 100)) == 1
    assert image.between_factor((240, 160), (480, 320)) == 2


def test_scale_returns_the_target_size_and_caches():
    """Scaling returns the target size and caches surfaces."""
    source = pygame.Surface((240, 160))
    s = image.Scaler()
    a = s.scale(source, (810, 540))
    assert a.get_size() == (810, 540)
    assert s.scale(source, (810, 540)) is a
    assert s.scale(source, (480, 320)).get_size() == (480, 320)


def test_symbols():
    """All status symbols draw."""
    area = pygame.Surface((100, 100))
    for kind in image.SYMBOLS:
        image.draw_symbol(area, kind, pygame.Rect(10, 10, 24, 24))
    with pytest.raises(ValueError):
        image.draw_symbol(area, "missing", pygame.Rect(0, 0, 10, 10))


def test_between_factor_rounds_for_ds():
    """The intermediate factor rounds sensibly for DS sizes."""
    assert image.between_factor((256, 192), (480, 360)) == 2
    assert image.between_factor((256, 192), (320, 240)) == 1


def test_scale_down():
    """Scaling down works."""
    s = image.Scaler()
    assert s.scale(pygame.Surface((256, 192)), (480, 360)).get_size() == (480, 360)
