# OSC Image Display

Fullscreen image display controlled over OSC (UDP, port 1340).

```bash
pip install -r requirements.txt
python oscimagedisplay.py --directory /path/to/images
```

| Option | Default | |
|---|---|---|
| `--directory` | required | where images are found |
| `--port` / `--host` | 1340 / 0.0.0.0 | OSC listen address |
| `--monitor N` | 0 | which display to use |
| `--list-monitors` | | print displays and exit |
| `--fade SECONDS` | 0 | default fade time |
| `--scale MODE` | fit | initial scale mode |
| `-v` | | debug logging |

Press ESC or Q to quit.

## OSC commands

All addresses are under `/oscimagedisplay/`. `[fade]` is an optional fade time in
seconds (0 = instant); if omitted the default fade time is used.

| Address | Arguments | Effect |
|---|---|---|
| `image` | `"file.png"` `[fade]` | Show an image from `--directory` (subdirectories allowed) |
| `colour` / `color` | `r g b` `[fade]` | Solid colour. Ints are 0-255, floats are 0.0-1.0 |
| `colour` / `color` | `"#rrggbb"` `[fade]` | Solid colour as hex |
| `show` | `[fade]` | Reveal the current image/colour |
| `hide` | `[fade]` | Fade to black; the content is kept |
| `fade` | `seconds` | Set the default fade time |
| `scale` | `fit` \| `fill` \| `stretch` \| `none` | How images fill the screen (see below) |

Scale modes: **fit** keeps aspect ratio with black bars; **fill** keeps aspect
ratio and crops to cover the screen; **stretch** ignores aspect ratio; **none**
shows original pixels, centred. Changing scale re-applies to the current image.

Setting an image replaces a colour and vice versa. `image`/`colour` while hidden
change the content but stay hidden until `show`. Fades start from whatever is on
screen, so interrupting a fade is smooth. PNG transparency shows over black.

Filenames may not escape `--directory`: absolute paths, `..` and symlinks pointing
outside it are rejected and logged. Bad messages and unloadable files are logged
and leave the display unchanged.

## Docker

Images are published to `ghcr.io/pingue/oscimagedisplay`. A fullscreen window needs
access to a display; on Linux with X11:

```bash
xhost +local:docker
docker run --rm -e DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v "$PWD/images:/images:ro" -p 1340:1340/udp \
  ghcr.io/pingue/oscimagedisplay --monitor 0 --fade 1
```

## Development

```bash
pip install -r requirements-dev.txt
SDL_VIDEODRIVER=dummy pytest
```

## Releases

Commits to `main` use [Conventional Commits](https://www.conventionalcommits.org/).
After tests pass, the release workflow computes the next [semver](https://semver.org/)
version: `feat` bumps minor, `fix`/`perf` bump patch, and `!` or a `BREAKING CHANGE:`
footer bumps major. Other types (`docs`, `ci`, `chore`, `test`, ...) don't release.
When there is something to release it publishes the Docker image, tags the commit
`vX.Y.Z` and creates a GitHub release with notes grouped by commit type.
