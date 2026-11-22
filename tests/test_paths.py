import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from oscimagedisplay import resolve_image_path  # noqa: E402


@pytest.fixture
def tree(tmp_path):
    base = tmp_path / "images"
    (base / "sub").mkdir(parents=True)
    (base / "a.png").write_bytes(b"x")
    (base / "sub" / "b.png").write_bytes(b"x")
    (tmp_path / "secret.png").write_bytes(b"x")
    return base


def test_simple_and_subdir(tree):
    assert resolve_image_path(tree, "a.png") == (tree / "a.png").resolve()
    assert resolve_image_path(tree, "sub/b.png") == (tree / "sub" / "b.png").resolve()


@pytest.mark.parametrize("name", [
    "../secret.png", "sub/../../secret.png", "..\\secret.png", "/etc/passwd",
    "C:/x.png", "", "a.png\0", ".", "missing.png",
])
def test_rejected(tree, name):
    with pytest.raises(ValueError):
        resolve_image_path(tree, name)


def test_absolute_path_inside_dir_rejected(tree):
    with pytest.raises(ValueError):
        resolve_image_path(tree, str(tree / "a.png"))


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_symlink_escape_rejected(tree):
    os.symlink(tree.parent / "secret.png", tree / "link.png")
    with pytest.raises(ValueError):
        resolve_image_path(tree, "link.png")
