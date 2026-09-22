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


def test_chat_keeps_history(monkeypatch):
    questions = iter(["Привет", "Продолжи", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(questions))
    snapshots = []

    def ask(messages):
        snapshots.append([dict(message) for message in messages])
        return {"role": "assistant", "content": "Ответ"}

    monkeypatch.setattr(agent, "ask_model", ask)
    agent.chat()
    assert [m["role"] for m in snapshots[1]] == ["user", "assistant", "user"]
    assert snapshots[1][0]["content"] == "Привет"


def test_tool_schema_is_only_data():
    tool = agent.TOOLS[0]["function"]
    assert tool["name"] == "shell"
    assert tool["parameters"]["required"] == ["command"]
    assert not hasattr(agent, "run_shell")
