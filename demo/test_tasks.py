"""Acceptance tests: the done regression should initially fail, not be skipped."""

import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class TrackerTests(unittest.TestCase):
    def run_cli(self, *commands):
        argv = [sys.executable, str(HERE / "tasks.py")]
        for command in commands:
            argv.extend(["--command", command])
        return subprocess.run(argv, cwd=HERE, capture_output=True, text=True, timeout=5)

    def test_done_marks_requested_id_and_no_other_task(self):
        result = self.run_cli("done 1", "list")
        self.assertEqual(result.returncode, 0)
        self.assertIn('1,"Купить молоко",done', result.stdout)
        self.assertIn('2,"Позвонить",open', result.stdout)

    def test_add_preserves_existing_tasks(self):
        result = self.run_cli("add Читать книгу", "list")
        self.assertEqual(result.returncode, 0)
        self.assertIn('3,"Читать книгу",open', result.stdout)
        self.assertIn("tasks[3]", result.stdout)

    def test_unknown_id_does_not_succeed(self):
        result = self.run_cli("done 999")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stdout)


if __name__ == "__main__":
    unittest.main()
