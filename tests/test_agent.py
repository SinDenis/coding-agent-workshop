import json

import httpx
import pytest

import agent


def test_model_request_contract(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")
    messages = [{"role": "user", "content": "Привет"}]

    def post(url, **kwargs):
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test-key-not-real"
        assert kwargs["json"]["model"] == "test/model"
        assert kwargs["json"]["reasoning"] == {"enabled": False}
        assert kwargs["json"]["messages"] == [
            {"role": "system", "content": agent.SYSTEM},
            *messages,
        ]
        assert kwargs["timeout"] == 60
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "Здравствуйте",
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(agent.httpx, "post", post)
    assert agent.ask_model(messages)["content"] == "Здравствуйте"
    assert len(messages) == 1
    assert "test-key-not-real" not in json.dumps(messages)


def test_key_required_before_network(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        agent.ask_model([])


def test_chat_keeps_history(monkeypatch, tmp_path):
    questions = iter(["Привет", "Продолжи", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(questions))
    snapshots = []

    def ask(messages):
        snapshots.append([dict(message) for message in messages])
        return {"role": "assistant", "content": "Ответ"}

    monkeypatch.setattr(agent, "ask_model", ask)
    agent.chat(tmp_path)
    assert [m["role"] for m in snapshots[1]] == ["user", "assistant", "user"]
    assert snapshots[1][0]["content"] == "Привет"


def test_tool_schema_is_only_data():
    tool = agent.TOOLS[0]["function"]
    assert tool["name"] == "shell"
    assert tool["parameters"]["required"] == ["command"]


def test_shell_returns_real_output_exit_code_and_cwd(tmp_path):
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
    result = agent.run_shell("cat hello.txt; printf error >&2; exit 7", tmp_path)
    assert result == {"stdout": "hello", "stderr": "error", "exit_code": 7}


def test_shell_does_not_inherit_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "do-not-share")
    result = agent.run_shell("printenv OPENROUTER_API_KEY", tmp_path)
    assert "do-not-share" not in result["stdout"]
    assert result["exit_code"] != 0


def tool_call(command="printf hello", call_id="call_1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": "shell",
            "arguments": json.dumps({"command": command}),
        },
    }


def test_feedback_sends_matching_tool_result(monkeypatch, tmp_path):
    snapshots = []

    def ask(messages):
        snapshots.append([dict(message) for message in messages])
        if len(snapshots) == 1:
            return {"role": "assistant", "content": None, "tool_calls": [tool_call()]}
        return {"role": "assistant", "content": "Готово"}

    monkeypatch.setattr(agent, "ask_model", ask)
    history = [{"role": "user", "content": "Привет"}]
    agent.agent_loop(history, tmp_path)
    assert [m["role"] for m in snapshots[1]] == ["user", "assistant", "tool"]
    result = snapshots[1][-1]
    assert result["tool_call_id"] == "call_1"
    assert json.loads(result["content"])["stdout"] == "hello"


def test_loop_handles_more_than_two_requests(monkeypatch, tmp_path):
    answers = iter(
        [
            {"role": "assistant", "tool_calls": [tool_call(call_id="a"), tool_call(call_id="b")]},
            {"role": "assistant", "tool_calls": [tool_call(call_id="c")]},
            {"role": "assistant", "content": "Готово"},
        ]
    )
    monkeypatch.setattr(agent, "ask_model", lambda _: next(answers))
    history = []
    assert agent.agent_loop(history, tmp_path)["content"] == "Готово"
    assert [m["tool_call_id"] for m in history if m["role"] == "tool"] == ["a", "b", "c"]


def test_loop_has_a_hard_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        agent,
        "ask_model",
        lambda _: {
            "role": "assistant",
            "tool_calls": [tool_call()],
        },
    )
    with pytest.raises(RuntimeError, match="лимит шагов"):
        agent.agent_loop([], tmp_path, max_steps=2)
