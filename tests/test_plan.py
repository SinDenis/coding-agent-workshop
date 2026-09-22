import httpx

import agent


def test_plan_prompt_still_exposes_shell(monkeypatch):
    """Pedagogical counterexample: a prompt alone does not remove write capability."""
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
    assert requests[0]["tools"][0]["function"]["name"] == "shell"
