#!/usr/bin/env python3
"""OSC-controlled fullscreen image display.

Listens for OSC messages (UDP, default port 1340). Addresses (all under
/oscimagedisplay/), with [fade] an optional fade time in seconds:

    image <filename> [fade]      load <filename> (relative to --directory)
    colour <r> <g> <b> [fade]    solid colour: ints 0-255 or floats 0.0-1.0
    colour <#rrggbb> [fade]      solid colour as hex (/color is an alias)
    show [fade]                  show the current image/colour
    hide [fade]                  black out the screen (content is kept)
    fade <seconds>               set the default fade time
    scale <mode>                 fit | fill | stretch | none

Starts as a fullscreen black screen. Press ESC or Q to quit.
"""

import argparse
import logging
import math
import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pygame
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

DEFAULT_PORT = 1340
PREFIX = "/oscimagedisplay/"
ADDR_IMAGE = PREFIX + "image"
ADDR_SHOW = PREFIX + "show"
ADDR_HIDE = PREFIX + "hide"
ADDR_COLOUR = PREFIX + "colour"
ADDR_COLOR = PREFIX + "color"
ADDR_FADE = PREFIX + "fade"
ADDR_SCALE = PREFIX + "scale"

SCALE_MODES = ("fit", "fill", "stretch", "none")
MAX_FADE = 3600.0  # seconds; guards against typos like 1e9

log = logging.getLogger("oscimagedisplay")


# --------------------------------------------------------------------------
# Command parsing (pure; no pygame state)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Command:
    kind: str  # image | colour | show | hide | fade | scale
    value: object = None
    fade: "float | None" = None  # None -> use the default fade time


def resolve_image_path(base_dir: Path, name: str) -> Path:
    """Resolve ``name`` inside ``base_dir``, refusing anything that escapes it.

    Rejects absolute paths, ``..`` traversal and symlinks pointing outside the
    directory. Raises ValueError if the name is unacceptable.
    """
    if not isinstance(name, str) or not name or "\0" in name:
        raise ValueError("invalid filename")
    # Treat Windows-style separators as separators on every platform.
    name = name.replace("\\", "/")
    if Path(name).is_absolute() or name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        raise ValueError("absolute paths are not allowed")

    base = base_dir.resolve()
    candidate = (base / name).resolve()  # resolves symlinks and '..'
    if not candidate.is_relative_to(base) or candidate == base:
        raise ValueError("path escapes the image directory")
    if not candidate.is_file():
        raise ValueError("file not found")
    return candidate


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_fade(value) -> float:
    if not _is_number(value):
        raise ValueError("fade time must be a number of seconds")
    seconds = float(value)
    if not math.isfinite(seconds) or not 0 <= seconds <= MAX_FADE:
        raise ValueError(f"fade time must be between 0 and {MAX_FADE:g} seconds")
    return seconds


def _optional_fade(rest) -> "float | None":
    if not rest:
        return None
    if len(rest) > 1:
        raise ValueError("too many arguments")
    return parse_fade(rest[0])


def _channel(value) -> int:
    """ints are 0-255, floats are 0.0-1.0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("colour components must be numbers")
    if isinstance(value, int):
        if not 0 <= value <= 255:
            raise ValueError("integer colour components must be 0-255")
        return value
    if not 0.0 <= value <= 1.0:  # also rejects NaN
        raise ValueError("float colour components must be 0.0-1.0")
    return round(value * 255)


def parse_colour(args) -> "tuple[tuple[int, int, int], float | None]":
    if not args:
        raise ValueError("expected: r g b [fade] or #rrggbb [fade]")
    if isinstance(args[0], str):
        text = args[0].removeprefix("#")
        if len(text) != 6:
            raise ValueError("hex colour must look like #rrggbb")
        try:
            rgb = (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
        except ValueError:
            raise ValueError("hex colour must look like #rrggbb") from None
        rest = args[1:]
    else:
        if len(args) < 3:
            raise ValueError("expected: r g b [fade]")
        rgb = tuple(_channel(a) for a in args[:3])
        rest = args[3:]
    return rgb, _optional_fade(rest)


def parse_command(address: str, args, base_dir: Path) -> "Command | None":
    """Turn an OSC message into a Command. Returns None for unknown addresses;
    raises ValueError for known addresses with bad arguments."""
    if address == ADDR_IMAGE:
        if not args or len(args) > 2 or not isinstance(args[0], str):
            raise ValueError("expected: filename [fade]")
        path = resolve_image_path(base_dir, args[0])
        return Command("image", path, _optional_fade(args[1:]))
    if address in (ADDR_SHOW, ADDR_HIDE):
        return Command(address[len(PREFIX):], None, _optional_fade(args))
    if address in (ADDR_COLOUR, ADDR_COLOR):
        rgb, fade = parse_colour(args)
        return Command("colour", rgb, fade)
    if address == ADDR_FADE:
        if len(args) != 1:
            raise ValueError("expected: seconds")
        return Command("fade", parse_fade(args[0]))
    if address == ADDR_SCALE:
        if len(args) != 1 or not isinstance(args[0], str) or args[0].lower() not in SCALE_MODES:
            raise ValueError("expected one of: " + ", ".join(SCALE_MODES))
        return Command("scale", args[0].lower())
    return None


def make_server(host: str, port: int, base_dir: Path, commands: "queue.Queue"):
    """Build the OSC server. Deliberately single-threaded (not Threading...):
    a thread per packet can reorder messages sent back to back. The handler only
    parses/validates and enqueues, so it is fast enough;
    the main thread owns all pygame work."""

    def handler(address, *args):
        try:
            cmd = parse_command(address, args, base_dir)
        except ValueError as exc:
            log.warning("rejected %s %r: %s", address, args, exc)
            return
        if cmd is None:
            log.debug("unhandled %s %r", address, args)
            return
        commands.put(cmd)

    dispatcher = Dispatcher()
    dispatcher.set_default_handler(handler)
    return BlockingOSCUDPServer((host, port), dispatcher)


# --------------------------------------------------------------------------
# Display state and rendering
# --------------------------------------------------------------------------

class Display:
    """What is on screen, and how it fades between states.

    Content is an image or a solid colour (setting one replaces the other).
    ``hide`` shows black without discarding the content; ``show`` reveals it.
    Every change cross-fades from whatever is currently on screen.
    Time is passed in explicitly so behaviour is testable.
    """

    def __init__(self, size, scale: str = "fit", fade: float = 0.0):
        self.size = tuple(size)
        self.scale = scale
        self.default_fade = fade
        self.visible = True
        self.colour = None  # (r, g, b) or None
        self.image = None  # source pygame.Surface (unscaled) or None
        self._from = None  # frame we are fading away from, during a fade
        self._t0 = 0.0
        self._duration = 0.0
        self._target = self._build_target()

    # -- state changes -----------------------------------------------------

    def apply(self, cmd: Command, now: float) -> None:
        fade = self.default_fade if cmd.fade is None else cmd.fade
        if cmd.kind == "image":
            try:
                img = pygame.image.load(str(cmd.value)).convert_alpha()
            except (pygame.error, OSError) as exc:
                log.warning("could not load %s: %s", cmd.value, exc)
                return
            self.image, self.colour = img, None
            log.info("image %s (fade %gs)", cmd.value, fade)
        elif cmd.kind == "colour":
            self.colour, self.image = cmd.value, None
            log.info("colour %s (fade %gs)", cmd.value, fade)
        elif cmd.kind == "show":
            self.visible = True
            log.info("show (fade %gs)", fade)
        elif cmd.kind == "hide":
            self.visible = False
            log.info("hide (fade %gs)", fade)
        elif cmd.kind == "fade":
            self.default_fade = cmd.value
            log.info("default fade %gs", cmd.value)
            return
        elif cmd.kind == "scale":
            self.scale = cmd.value
            log.info("scale %s", cmd.value)
            # Applied immediately; doesn't disturb a fade already in progress.
            self._target = self._build_target()
            return
        else:
            return
        self._retarget(fade, now)

    def _retarget(self, fade: float, now: float) -> None:
        new_target = self._build_target()
        if fade > 0:
            snapshot = pygame.Surface(self.size)
            self.render(snapshot, now)  # what is on screen right now
            self._from = snapshot
        else:
            self._from = None
        self._t0, self._duration, self._target = now, fade, new_target

    # -- rendering ---------------------------------------------------------

    def _scaled(self, image: "pygame.Surface") -> "pygame.Surface":
        iw, ih = image.get_size()
        sw, sh = self.size
        if self.scale == "stretch":
            size = (sw, sh)
        elif self.scale in ("fit", "fill"):
            pick = min if self.scale == "fit" else max
            factor = pick(sw / iw, sh / ih)
            size = (max(1, round(iw * factor)), max(1, round(ih * factor)))
        else:  # "none": original pixels, centred (cropped if larger)
            return image
        return image if size == (iw, ih) else pygame.transform.smoothscale(image, size)

    def _build_target(self) -> "pygame.Surface":
        surface = pygame.Surface(self.size)
        surface.fill((0, 0, 0))
        if self.visible:
            if self.colour is not None:
                surface.fill(self.colour)
            elif self.image is not None:
                img = self._scaled(self.image)
                surface.blit(img, img.get_rect(center=surface.get_rect().center))
        return surface

    def render(self, screen: "pygame.Surface", now: float) -> None:
        if self._from is not None:
            progress = (now - self._t0) / self._duration if self._duration > 0 else 1.0
            if progress < 1.0:
                screen.blit(self._from, (0, 0))
                self._target.set_alpha(int(max(progress, 0.0) * 255))
                screen.blit(self._target, (0, 0))
                self._target.set_alpha(None)
                return
            self._from = None
        screen.blit(self._target, (0, 0))


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

def list_monitors() -> None:
    pygame.display.init()
    for index, (width, height) in enumerate(pygame.display.get_desktop_sizes()):
        print(f"{index}: {width}x{height}")


def run(base_dir: Path, host: str, port: int, monitor: int, fade: float, scale: str) -> None:
    pygame.display.init()
    count = pygame.display.get_num_displays()
    if not 0 <= monitor < count:
        raise SystemExit(f"--monitor {monitor} is not available ({count} display(s); see --list-monitors)")
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN, display=monitor)
    pygame.display.set_caption("OSC Image Display")
    pygame.mouse.set_visible(False)
    display = Display(screen.get_size(), scale=scale, fade=fade)

    commands: "queue.Queue" = queue.Queue()
    server = make_server(host, port, base_dir, commands)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("listening on %s:%d, images from %s, monitor %d", host, port, base_dir, monitor)

    clock = pygame.time.Clock()
    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q)
                ):
                    running = False
            now = time.monotonic()
            while True:
                try:
                    display.apply(commands.get_nowait(), now)
                except queue.Empty:
                    break
            display.render(screen, now)
            pygame.display.flip()
            clock.tick(60)
    finally:
        server.shutdown()
        server.server_close()
        pygame.quit()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="OSC-controlled fullscreen image display")
    parser.add_argument("--directory", type=Path, help="directory containing the images (required)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"UDP port to listen on (default {DEFAULT_PORT})")
    parser.add_argument("--host", default="0.0.0.0", help="address to bind (default 0.0.0.0)")
    parser.add_argument("--monitor", type=int, default=0, help="display index to use (default 0; see --list-monitors)")
    parser.add_argument("--list-monitors", action="store_true", help="list available displays and exit")
    parser.add_argument("--fade", type=float, default=0.0, help="default fade time in seconds (default 0)")
    parser.add_argument("--scale", choices=SCALE_MODES, default="fit", help="initial scale mode (default fit)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    if args.list_monitors:
        list_monitors()
        return 0
    if args.directory is None:
        parser.error("--directory is required")
    if not args.directory.is_dir():
        parser.error(f"--directory {args.directory} is not a directory")
    try:
        fade = parse_fade(args.fade)
    except ValueError as exc:
        parser.error(f"--fade: {exc}")

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.directory.resolve(), args.host, args.port, args.monitor, fade, args.scale)
    return 0


if __name__ == "__main__":
    sys.exit(main())
