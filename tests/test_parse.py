import pytest

from oscimagedisplay import Command, parse_command

P = "/oscimagedisplay/"


@pytest.fixture
def base(tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    return tmp_path


def test_image(base):
    cmd = parse_command(P + "image", ("a.png",), base)
    assert cmd == Command("image", (base / "a.png").resolve(), None)


def test_image_with_fade(base):
    assert parse_command(P + "image", ("a.png", 2), base).fade == 2.0
    assert parse_command(P + "image", ("a.png", 0.5), base).fade == 0.5


@pytest.mark.parametrize("args", [(), (5,), ("a.png", "x"), ("a.png", 1, 2), ("../a.png",), ("a.png", -1), ("a.png", float("nan")), ("a.png", 1e9), ("a.png", True)])
def test_image_rejected(base, args):
    with pytest.raises(ValueError):
        parse_command(P + "image", args, base)


@pytest.mark.parametrize("name", ["show", "hide"])
def test_show_hide(base, name):
    assert parse_command(P + name, (), base) == Command(name, None, None)
    assert parse_command(P + name, (1.5,), base).fade == 1.5
    with pytest.raises(ValueError):
        parse_command(P + name, (1, 2), base)


@pytest.mark.parametrize("addr", ["colour", "color"])
def test_colour_alias_and_forms(base, addr):
    assert parse_command(P + addr, (255, 0, 10), base) == Command("colour", (255, 0, 10), None)
    assert parse_command(P + addr, (1.0, 0.0, 0.5), base).value == (255, 0, 128)
    assert parse_command(P + addr, ("#ff0080",), base).value == (255, 0, 128)
    assert parse_command(P + addr, ("ff0080", 3), base) == Command("colour", (255, 0, 128), 3.0)
    assert parse_command(P + addr, (1, 2, 3, 4), base).fade == 4.0


@pytest.mark.parametrize("args", [(), (1, 2), (256, 0, 0), (-1, 0, 0), (1.5, 0.0, 0.0), ("#fff",), ("#gggggg",), ("red",), (1, 2, "x"), (1, 2, 3, 4, 5), (True, 0, 0)])
def test_colour_rejected(base, args):
    with pytest.raises(ValueError):
        parse_command(P + "colour", args, base)


def test_fade_and_scale(base):
    assert parse_command(P + "fade", (2,), base) == Command("fade", 2.0)
    assert parse_command(P + "scale", ("Fill",), base) == Command("scale", "fill")
    for args in [(), (1, 2)]:
        with pytest.raises(ValueError):
            parse_command(P + "fade", args, base)
    for args in [(), ("zoom",), (1,)]:
        with pytest.raises(ValueError):
            parse_command(P + "scale", args, base)


def test_unknown_address(base):
    assert parse_command("/other/thing", (), base) is None
