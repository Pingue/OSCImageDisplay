import os

# Must be set before pygame initialises a display: no real screen needed.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _video():
    pygame.display.init()
    pygame.display.set_mode((16, 16))
    yield
    pygame.quit()
