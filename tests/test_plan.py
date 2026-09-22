import json

import httpx
import pytest

import agent


def test_plan_exposes_read_tools_only(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    requests = []

    def post(*args, **kwargs):
        requests.append(kwargs["json"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "План",
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(agent.httpx, "post", post)
    agent.ask_model([], mode="plan")
    assert requests[0]["messages"][0]["content"] == agent.PLAN_PROMPT
    assert {t["function"]["name"] for t in requests[0]["tools"]} == {"list_files", "read_file"}


def call(name, **arguments):
    return {
        "id": "c",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


def test_executor_blocks_forged_shell_in_plan(tmp_path):
    result = agent.execute_tool(call("shell", command="touch forbidden"), tmp_path, "plan")
    assert "запрещён" in result["error"]
    assert not (tmp_path / "forbidden").exists()


@pytest.mark.parametrize("path", ["../outside", "/etc/passwd", ".env", "sub/../../outside"])
def test_read_cannot_escape_or_read_hidden_files(tmp_path, path):
    result = agent.execute_tool(call("read_file", path=path), tmp_path, "plan")
    assert "error" in result


def test_symlink_escape_and_hidden_target_are_rejected(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("secret")
    (project / "escape").symlink_to(outside)
    (project / ".env").write_text("secret")
    (project / "hidden").symlink_to(project / ".env")
    for name in ("escape", "hidden"):
        assert "error" in agent.execute_tool(call("read_file", path=name), project, "plan")


def test_read_and_list_work_without_changing_files(tmp_path):
    (tmp_path / "hello.txt").write_text("Привет", encoding="utf-8")
    assert (
        agent.execute_tool(call("read_file", path="hello.txt"), tmp_path, "plan")["text"]
        == "Привет"
    )
    assert agent.list_files(tmp_path)["entries"] == ["hello.txt"]
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "Привет"


def test_invalid_mode_fails_closed(tmp_path):
    result = agent.execute_tool(call("shell", command="touch bad"), tmp_path, "typo")
    assert "error" in result
    assert not (tmp_path / "bad").exists()
