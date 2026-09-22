"""Check every tagged checkpoint in an isolated temporary checkout, without an API key."""

import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    tags = subprocess.check_output(
        ["git", "tag", "--list", "step-*", "--sort=refname"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    if not tags:
        raise SystemExit("Нет учебных тегов. Выполните git fetch --tags")
    results = []
    for tag in tags:
        archive = subprocess.check_output(["git", "archive", tag], cwd=ROOT)
        with tempfile.TemporaryDirectory(prefix="workshop-check-") as directory:
            with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
                bundle.extractall(directory, filter="data")
            environment = dict(os.environ)
            environment.pop("OPENROUTER_API_KEY", None)
            environment["PYTHONPATH"] = directory
            commands = [
                [sys.executable, "-m", "ruff", "check", "."],
                [sys.executable, "-m", "ruff", "format", "--check", "."],
                [sys.executable, "-m", "pytest", "-q"],
            ]
            if (Path(directory) / "agent.py").exists():
                commands.append([sys.executable, "agent.py", "--help"])
            for command in commands:
                result = subprocess.run(
                    command,
                    cwd=directory,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode:
                    print(tag, command, result.stdout, result.stderr)
                    raise SystemExit(result.returncode)
            summary = next(r for r in commands if "pytest" in r)
            results.append({"tag": tag, "passed": True, "check": " ".join(summary[1:])})
            print(f"{tag}: PASS (lint, format, tests, CLI help)", flush=True)
    checks = ROOT / ".checks"
    checks.mkdir(exist_ok=True)
    (checks / "history.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
