"""Create a disposable project copy without deleting earlier attempts."""

import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def prepare(base: Path = ROOT / ".runs") -> Path:
    base.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="tracker-", dir=base))
    shutil.copytree(
        ROOT / "demo",
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return destination.resolve()


if __name__ == "__main__":
    print(prepare())
