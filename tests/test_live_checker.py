import pytest

from scripts.live_check import assert_final_answer


@pytest.mark.parametrize(
    "reason, message",
    [
        ("tool_calls", {"tool_calls": [{"id": "pending"}]}),
        ("length", {"content": "partial"}),
        ("stop", {"content": None}),
    ],
)
def test_live_checker_does_not_confuse_working_files_with_finished_agent(reason, message):
    with pytest.raises(AssertionError):
        assert_final_answer([{"choices": [{"finish_reason": reason, "message": message}]}])


def test_live_checker_accepts_final_text():
    assert_final_answer([{"choices": [{"finish_reason": "stop", "message": {"content": "Done"}}]}])
