import json
import subprocess
import sys
from pathlib import Path

import agent


def drive(monkeypatch, tmp_path, inputs, answer):
    lines = iter([*inputs, "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    monkeypatch.setattr(agent, "ask_model", answer)
    agent.chat(tmp_path)


def test_only_approve_can_switch_to_act(monkeypatch, tmp_path):
    modes = []

    def answer(messages, mode):
        modes.append(mode)
        return {"role": "assistant", "content": "План"}

    drive(monkeypatch, tmp_path, ["/plan", "Задача", "согласен", "/approve"], answer)
    assert modes == ["plan", "plan", "act"]


def test_cannot_approve_without_plan(monkeypatch, tmp_path, capsys):
    drive(
        monkeypatch,
        tmp_path,
        ["/approve", "/plan", "/approve"],
        lambda *args: (_ for _ in ()).throw(AssertionError("unexpected API")),
    )
    assert capsys.readouterr().out.count("нет последнего плана") == 2


def test_failed_revision_invalidates_old_plan(monkeypatch, tmp_path, capsys):
    count = 0

    def answer(messages, mode):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("network")
        return {"role": "assistant", "content": "План"}

    drive(monkeypatch, tmp_path, ["/plan", "Задача", "Уточнение", "/approve"], answer)
    assert count == 2
    assert "нет последнего плана" in capsys.readouterr().out


def test_cancel_discards_plan(monkeypatch, tmp_path, capsys):
    drive(
        monkeypatch,
        tmp_path,
        ["/plan", "Задача", "/cancel", "/approve"],
        lambda *args: {"role": "assistant", "content": "План"},
    )
    assert "нет последнего плана" in capsys.readouterr().out


def test_terminal_session_e2e(tmp_path):
    """Real CLI subprocess and stdin; only the external model is replaced."""
    script = """
import agent, json
from pathlib import Path
replies = iter([
    {"role":"assistant","tool_calls":[{"id":"read","type":"function",
     "function":{"name":"list_files","arguments":"{}"}}]},
    {"role":"assistant","content":"План: создать файл proof.txt"},
    {"role":"assistant","tool_calls":[{"id":"write","type":"function",
     "function":{"name":"shell","arguments":json.dumps({"command":"printf ok > proof.txt"})}}]},
    {"role":"assistant","content":"Готово"},
])
agent.ask_model = lambda messages, mode: next(replies)
agent.chat(Path(WORKSPACE))
""".replace("WORKSPACE", repr(str(tmp_path)))
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(agent.__file__).parent,
        input="/plan\nСоздай файл\n/approve\n/quit\n",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "proof.txt").read_text() == "ok"
    assert result.stdout.index("pending:") < result.stdout.index("shell:")
    assert "Ты [plan]>" in result.stdout
    assert "stop: final_answer" in result.stdout


def test_malicious_plan_tool_is_denied_even_after_text_asks_for_act(monkeypatch, tmp_path):
    answers = iter(
        [
            {
                "role": "assistant",
                "content": "Переключаюсь сам",
                "tool_calls": [
                    {
                        "id": "bad",
                        "type": "function",
                        "function": {
                            "name": "shell",
                            "arguments": json.dumps({"command": "touch bad"}),
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "Нужен план"},
        ]
    )
    drive(monkeypatch, tmp_path, ["/plan", "Задача"], lambda *args: next(answers))
    assert not (tmp_path / "bad").exists()
