import queue
import threading

import pytest
from pythonosc.udp_client import SimpleUDPClient

from oscimagedisplay import Command, make_server


@pytest.fixture
def server(tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    commands = queue.Queue()
    srv = make_server("127.0.0.1", 0, tmp_path, commands)  # port 0: any free port
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    client = SimpleUDPClient("127.0.0.1", srv.server_address[1])
    yield client, commands, tmp_path
    srv.shutdown()
    srv.server_close()


def test_messages_become_commands(server):
    client, commands, base = server
    client.send_message("/oscimagedisplay/image", ["a.png", 1.5])
    client.send_message("/oscimagedisplay/hide", [])
    client.send_message("/oscimagedisplay/color", [255, 0, 0])
    assert commands.get(timeout=2) == Command("image", (base / "a.png").resolve(), 1.5)
    assert commands.get(timeout=2) == Command("hide")
    assert commands.get(timeout=2) == Command("colour", (255, 0, 0))


def test_bad_messages_are_dropped(server):
    client, commands, _ = server
    client.send_message("/oscimagedisplay/image", "../a.png")
    client.send_message("/oscimagedisplay/image", 5)
    client.send_message("/something/else", 1)
    client.send_message("/oscimagedisplay/show", [])  # sentinel: arrives last
    assert commands.get(timeout=2) == Command("show")
    assert commands.empty()
