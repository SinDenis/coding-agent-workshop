"""Exercise the real CLI and JSON encoding, without network or a real API key."""

import inspect
import json
import os
import pty
import select
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

import agent

ROOT = Path(__file__).resolve().parents[1]
CLI = """
import json
import runpy
import sys
import httpx

def post(url, **kwargs):
    request = httpx.Request("POST", url, json=kwargs["json"])
    print("request: " + json.dumps(kwargs["json"]["messages"], ensure_ascii=False), flush=True)
    return httpx.Response(200, request=request, json={
        "choices": [{"finish_reason": "stop",
                     "message": {"role": "assistant", "content": "Ответ"}}]
    })

httpx.post = post
sys.argv = ["agent.py", *sys.argv[1:]]
runpy.run_path("agent.py", run_name="__main__")
"""


def cli_environment():
    return {
        **os.environ,
        "OPENROUTER_API_KEY": "test-key-not-real",
        "PYTHONIOENCODING": "utf-8:surrogateescape",
        "TERM": "dumb",
    }


def cli_command(workspace):
    command = [sys.executable, "-u", "-c", CLI]
    if "workspace" in inspect.signature(agent.chat).parameters:
        command.extend(["--workspace", str(workspace)])
    return command


def requests_in(output):
    return [
        json.loads(line.split("request: ", 1)[1])
        for line in output.decode("utf-8", errors="replace").splitlines()
        if "request: " in line
    ]


def read_prompt(master, after=b""):
    output = bytearray()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if select.select([master], [], [], 0.1)[0]:
            try:
                data = os.read(master, 65536)
            except OSError:
                break
            if not data:
                break
            output.extend(data)
            if after in output and output.endswith(b"> "):
                return bytes(output)
    raise AssertionError(output.decode("utf-8", errors="backslashreplace"))


def drain_terminal(master, process):
    # libedit can wait for terminal output to drain while restoring its settings.
    deadline = time.monotonic() + 5
    while process.poll() is None and time.monotonic() < deadline:
        if select.select([master], [], [], 0.1)[0]:
            try:
                if not os.read(master, 65536):
                    break
            except OSError:
                break


@pytest.mark.parametrize("deleted_character", ["я", "🙂"])
def test_cli_unicode_backspace_preserves_valid_text_and_history(tmp_path, deleted_character):
    master, slave = pty.openpty()
    settings = termios.tcgetattr(slave)
    settings[6][termios.VERASE] = b"\x7f"
    termios.tcsetattr(slave, termios.TCSANOW, settings)
    process = subprocess.Popen(
        cli_command(tmp_path),
        cwd=ROOT,
        env=cli_environment(),
        stdin=slave,
        stdout=slave,
        stderr=slave,
    )
    os.close(slave)
    question = "можешь посмотреть мой проект что это?"
    try:
        read_prompt(master)
        os.write(master, "привет\n".encode())
        first = read_prompt(master, after=b"request: ")
        # Delete a multibyte character, just as with Backspace in Terminal.
        os.write(master, (question + deleted_character).encode() + b"\x7f\n")
        second = read_prompt(master, after=b"request: ")
        os.write(master, b"/quit\n")
        drain_terminal(master, process)
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
    assert requests_in(first)[0][-1]["content"] == "привет"
    history = requests_in(second)[0]
    assert [message["role"] for message in history] == ["system", "user", "assistant", "user"]
    assert history[-1]["content"] == question


def test_cli_rejects_invalid_utf8_without_polluting_history(tmp_path):
    result = subprocess.run(
        cli_command(tmp_path),
        cwd=ROOT,
        env=cli_environment(),
        input="привет\n".encode() + b"broken\xd1\n" + "ещё вопрос\n/quit\n".encode(),
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert "error:" in result.stdout.decode()
    assert "UTF-8" in result.stdout.decode()
    requests = requests_in(result.stdout)
    assert len(requests) == 2
    assert [message["content"] for message in requests[-1][1:]] == ["привет", "Ответ", "ещё вопрос"]


def test_cli_eof_exits_without_a_request(tmp_path):
    result = subprocess.run(
        cli_command(tmp_path),
        cwd=ROOT,
        env=cli_environment(),
        input=b"",
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert requests_in(result.stdout) == []
