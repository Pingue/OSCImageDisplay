#!/usr/bin/env python3
"""OSC-controlled fullscreen image display.

Listens for OSC messages (UDP, default port 1340):

    /oscimagedisplay/image <filename>   load <filename> (relative to --directory)
    /oscimagedisplay/show               show the current image
    /oscimagedisplay/hide               black out the screen (image is kept)

Starts as a fullscreen black screen. Press ESC or Q to quit.
"""

import argparse
import logging
import queue
import sys
from pathlib import Path

import pygame
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

DEFAULT_PORT = 1340
ADDR_IMAGE = "/oscimagedisplay/image"
ADDR_SHOW = "/oscimagedisplay/show"
ADDR_HIDE = "/oscimagedisplay/hide"

log = logging.getLogger("oscimagedisplay")


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


def make_server(host: str, port: int, base_dir: Path, commands: "queue.Queue"):
    """Build the OSC server. Handlers only validate and enqueue; the main
    thread owns all pygame work."""
    dispatcher = Dispatcher()

    def on_image(_addr, *args):
        if len(args) != 1 or not isinstance(args[0], str):
            log.warning("%s expects one string argument, got %r", ADDR_IMAGE, args)
            return
        try:
            path = resolve_image_path(base_dir, args[0])
        except ValueError as exc:
            log.warning("rejected %r: %s", args[0], exc)
            return
        commands.put(("image", path))

    dispatcher.map(ADDR_IMAGE, on_image)
    dispatcher.map(ADDR_SHOW, lambda _a, *_r: commands.put(("show", None)))
    dispatcher.map(ADDR_HIDE, lambda _a, *_r: commands.put(("hide", None)))
    dispatcher.set_default_handler(lambda addr, *a: log.debug("unhandled %s %r", addr, a))
    return ThreadingOSCUDPServer((host, port), dispatcher)


def fit_surface(image: "pygame.Surface", size) -> "pygame.Surface":
    """Scale ``image`` to fit inside ``size`` keeping aspect ratio."""
    sw, sh = size
    iw, ih = image.get_size()
    scale = min(sw / iw, sh / ih)
    new_size = (max(1, round(iw * scale)), max(1, round(ih * scale)))
    return pygame.transform.smoothscale(image, new_size)


def run(base_dir: Path, host: str, port: int) -> None:
    commands: "queue.Queue" = queue.Queue()
    server = make_server(host, port, base_dir, commands)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("listening on %s:%d, serving images from %s", host, port, base_dir)

    pygame.display.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("OSC Image Display")
    pygame.mouse.set_visible(False)
    screen_size = screen.get_size()

    image = None  # pre-scaled surface, or None
    visible = True
    clock = pygame.time.Clock()
    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q)
                ):
                    running = False

            while True:
                try:
                    cmd, arg = commands.get_nowait()
                except queue.Empty:
                    break
                if cmd == "image":
                    try:
                        image = fit_surface(pygame.image.load(str(arg)).convert(), screen_size)
                        log.info("loaded %s", arg)
                    except (pygame.error, OSError) as exc:
                        log.warning("could not load %s: %s", arg, exc)
                elif cmd == "show":
                    visible = True
                elif cmd == "hide":
                    visible = False

            screen.fill((0, 0, 0))
            if visible and image is not None:
                screen.blit(image, image.get_rect(center=screen.get_rect().center))
            pygame.display.flip()
            clock.tick(30)
    finally:
        server.shutdown()
        server.server_close()
        pygame.quit()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="OSC-controlled fullscreen image display")
    parser.add_argument("--directory", required=True, type=Path, help="directory containing the images")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"UDP port to listen on (default {DEFAULT_PORT})")
    parser.add_argument("--host", default="0.0.0.0", help="address to bind (default 0.0.0.0)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not args.directory.is_dir():
        parser.error(f"--directory {args.directory} is not a directory")
    run(args.directory.resolve(), args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
