import subprocess
import sys

from prepare_demo import prepare


def test_demo_copies_are_independent(tmp_path):
    first, second = prepare(tmp_path), prepare(tmp_path)
    assert first != second
    (first / "tasks.py").write_text("modified", encoding="utf-8")
    assert "def main" in (second / "tasks.py").read_text(encoding="utf-8")


def test_known_demo_failure_is_reproducible_e2e(tmp_path):
    demo = prepare(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-v"],
        cwd=demo,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "FAIL: test_done_marks_requested_id" in result.stderr
    assert "failures=1" in result.stderr


def test_tracker_rejects_unknown_flags(tmp_path):
    demo = prepare(tmp_path)
    result = subprocess.run(
        [sys.executable, str(demo / "tasks.py"), "--typo"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert "error:" in result.stdout
