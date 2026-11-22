# OSC Image Display

Fullscreen image display controlled over OSC (UDP, port 1340).

```bash
pip install -r requirements.txt
python oscimagedisplay.py --directory /path/to/images
```

Options: `--port` (default 1340), `--host` (default 0.0.0.0), `-v` for debug logging.
Press ESC or Q to quit.

| Address | Argument | Effect |
|---|---|---|
| `/oscimagedisplay/image` | string: filename relative to `--directory` | Load and display the image (scaled to fit, aspect ratio kept) |
| `/oscimagedisplay/show` | none | Show the current image |
| `/oscimagedisplay/hide` | none | Black the screen (the loaded image is kept) |

The screen starts black. Filenames may include subdirectories (`sub/a.png`), but
absolute paths, `..` traversal and symlinks leading outside `--directory` are
rejected and logged. Failed loads leave the current image unchanged.

Tests: `pip install pytest && pytest`
