import pygame
import pytest

from oscimagedisplay import Command, Display

SIZE = (100, 50)


def px(surface, x, y):
    return tuple(surface.get_at((x, y)))[:3]


def frame(display, now=0.0):
    screen = pygame.Surface(SIZE)
    display.render(screen, now)
    return screen


def image_file(tmp_path, size, colour, name="img.png", alpha=255):
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill((*colour, alpha))
    path = tmp_path / name
    pygame.image.save(surf, str(path))
    return path


def test_starts_black():
    assert px(frame(Display(SIZE)), 50, 25) == (0, 0, 0)


def test_colour_hide_show():
    d = Display(SIZE)
    d.apply(Command("colour", (10, 20, 30)), 0)
    assert px(frame(d), 5, 5) == (10, 20, 30)
    d.apply(Command("hide"), 0)
    assert px(frame(d), 5, 5) == (0, 0, 0)
    d.apply(Command("show"), 0)
    assert px(frame(d), 5, 5) == (10, 20, 30)


def test_image_fit_letterboxes(tmp_path):
    d = Display(SIZE, scale="fit")
    d.apply(Command("image", image_file(tmp_path, (10, 10), (255, 0, 0))), 0)
    f = frame(d)
    assert px(f, 50, 25) == (255, 0, 0)  # centre square
    assert px(f, 5, 25) == (0, 0, 0)  # bars at the sides


def test_image_fill_crops(tmp_path):
    d = Display(SIZE, scale="fill")
    d.apply(Command("image", image_file(tmp_path, (10, 10), (255, 0, 0))), 0)
    f = frame(d)
    assert px(f, 1, 1) == (255, 0, 0) and px(f, 98, 48) == (255, 0, 0)


def test_image_stretch(tmp_path):
    d = Display(SIZE, scale="stretch")
    d.apply(Command("image", image_file(tmp_path, (10, 10), (255, 0, 0))), 0)
    f = frame(d)
    assert px(f, 1, 1) == (255, 0, 0) and px(f, 98, 48) == (255, 0, 0)


def test_scale_none_keeps_pixels(tmp_path):
    d = Display(SIZE, scale="none")
    d.apply(Command("image", image_file(tmp_path, (10, 10), (255, 0, 0))), 0)
    f = frame(d)
    assert px(f, 50, 25) == (255, 0, 0)
    assert px(f, 30, 25) == (0, 0, 0)


def test_scale_command_rescales_current_image(tmp_path):
    d = Display(SIZE, scale="none")
    d.apply(Command("image", image_file(tmp_path, (10, 10), (255, 0, 0))), 0)
    assert px(frame(d), 1, 1) == (0, 0, 0)
    d.apply(Command("scale", "stretch"), 0)
    assert px(frame(d), 1, 1) == (255, 0, 0)


def test_transparent_png_composites_over_black(tmp_path):
    d = Display(SIZE, scale="stretch")
    d.apply(Command("image", image_file(tmp_path, (4, 4), (255, 255, 255), alpha=0)), 0)
    assert px(frame(d), 50, 25) == (0, 0, 0)


def test_bad_image_keeps_current(tmp_path):
    d = Display(SIZE)
    d.apply(Command("colour", (1, 2, 3)), 0)
    bad = tmp_path / "bad.png"
    bad.write_text("nope")
    d.apply(Command("image", bad), 0)
    assert px(frame(d), 5, 5) == (1, 2, 3)


def test_fade_progresses():
    d = Display(SIZE)
    d.apply(Command("colour", (200, 200, 200), 2.0), now=10.0)
    assert px(frame(d, 10.0), 5, 5) == (0, 0, 0)
    mid = px(frame(d, 11.0), 5, 5)
    assert 95 <= mid[0] <= 105
    assert px(frame(d, 12.0), 5, 5) == (200, 200, 200)
    assert px(frame(d, 99.0), 5, 5) == (200, 200, 200)


def test_default_fade_used_and_overridable():
    d = Display(SIZE)
    d.apply(Command("fade", 4.0), 0)
    d.apply(Command("colour", (200, 200, 200)), now=0.0)
    assert px(frame(d, 2.0), 5, 5)[0] < 150  # default fade applies
    d.apply(Command("colour", (50, 50, 50), 0.0), now=5.0)  # explicit 0 = cut
    assert px(frame(d, 5.0), 5, 5) == (50, 50, 50)


def test_fade_out_via_hide():
    d = Display(SIZE)
    d.apply(Command("colour", (200, 200, 200)), 0)
    d.apply(Command("hide", None, 2.0), now=1.0)
    mid = px(frame(d, 2.0), 5, 5)
    assert 95 <= mid[0] <= 105
    assert px(frame(d, 3.0), 5, 5) == (0, 0, 0)


def test_interrupting_a_fade_starts_from_current_frame():
    d = Display(SIZE)
    d.apply(Command("colour", (200, 200, 200), 2.0), now=0.0)
    d.apply(Command("hide", None, 2.0), now=1.0)  # was ~100 grey at this point
    start = px(frame(d, 1.0), 5, 5)
    assert 95 <= start[0] <= 105
