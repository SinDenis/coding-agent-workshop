import json
import time

import httpx
import pytest

import agent


@pytest.mark.parametrize("reason", ["length", "content_filter", "error", None])
def test_unfinished_api_response_never_executes(monkeypatch, reason):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    monkeypatch.setattr(
        agent.httpx,
        "post",
        lambda *a, **k: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": reason,
                        "message": {
                            "role": "assistant",
                            "content": "partial answer",
                        },
                    }
                ],
            },
        ),
    )
    with pytest.raises(RuntimeError, match="finish_reason"):
        agent.ask_model([])


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": ""}}]},
    ],
)
def test_malformed_or_empty_response_is_not_success(monkeypatch, payload):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    monkeypatch.setattr(agent.httpx, "post", lambda *a, **k: httpx.Response(200, json=payload))
    with pytest.raises(RuntimeError):
        agent.ask_model([])


def test_reasoning_details_are_preserved(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    message = {
        "role": "assistant",
        "content": "Done",
        "reasoning_details": [
            {"type": "reasoning.encrypted", "data": "opaque"},
        ],
    }
    monkeypatch.setattr(
        agent.httpx,
        "post",
        lambda *a, **k: httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": message}],
            },
        ),
    )
    assert agent.ask_model([]) == message


def test_timeout_kills_children_e2e(tmp_path):
    start = time.monotonic()
    result = agent.run_shell("(sleep 1; touch escaped) & wait", tmp_path, timeout=0.1)
    assert "Таймаут" in result["error"]
    assert time.monotonic() - start < 1
    time.sleep(1.05)
    assert not (tmp_path / "escaped").exists()


def test_output_is_bounded(tmp_path):
    result = agent.run_shell("head -c 30000 /dev/zero", tmp_path)
    assert len(result["stdout"]) < 13000
    assert "truncated" in result["stdout"]


@pytest.mark.parametrize("arguments", ["{", "[]", '{"command": 42}', '{"command":"ls","x":1}'])
def test_bad_arguments_are_tool_errors(tmp_path, arguments):
    result = agent.execute_tool({"function": {"name": "shell", "arguments": arguments}}, tmp_path)
    assert "error" in result


def test_overlong_history_is_rejected_before_api(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "ask_model", lambda _: pytest.fail("must not call API"))
    with pytest.raises(RuntimeError, match="История"):
        agent.agent_loop([{"role": "user", "content": "x" * 150001}], tmp_path)


def test_two_tool_calls_stay_paired_on_error(monkeypatch, tmp_path):
    call = {
        "id": "broken",
        "type": "function",
        "function": {
            "name": "shell",
            "arguments": "not-json",
        },
    }
    answers = iter(
        [
            {"role": "assistant", "tool_calls": [call]},
            {"role": "assistant", "content": "Не получилось"},
        ]
    )
    monkeypatch.setattr(agent, "ask_model", lambda _: next(answers))
    messages = []
    agent.agent_loop(messages, tmp_path)
    assert messages[1]["tool_call_id"] == "broken"
    assert "error" in json.loads(messages[1]["content"])
