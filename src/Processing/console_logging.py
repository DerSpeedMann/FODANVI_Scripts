"""
console_logging.py

Mirror a script's console output (stdout + stderr) into an in-memory buffer
while still printing live, then save a cleaned log into a ``logs`` folder
inside the run's result directory.

Progress-bar redraws (carriage returns from tqdm) are collapsed to their final
state so the saved log stays readable.

Usage:
    with capture_console() as cap:
        results = model.val(...)
    cap.write_log(results.save_dir)   # -> <save_dir>/logs/console.log
"""

from __future__ import annotations

import io
import sys
from pathlib import Path


class _Tee:
    """Write-through stream that duplicates writes into a buffer and delegates
    everything else (isatty, fileno, encoding, ...) to the real stream."""

    def __init__(self, real, buffer: io.StringIO):
        self._real = real
        self._buffer = buffer

    def write(self, data: str) -> int:
        self._real.write(data)
        self._buffer.write(data)
        return len(data)

    def flush(self) -> None:
        self._real.flush()

    def __getattr__(self, name):
        return getattr(self._real, name)


class capture_console:
    """Context manager that tees stdout and stderr into a buffer."""

    def __init__(self) -> None:
        self._buffer = io.StringIO()
        self._stdout = None
        self._stderr = None

    def __enter__(self) -> "capture_console":
        self._stdout, self._stderr = sys.stdout, sys.stderr
        sys.stdout = _Tee(self._stdout, self._buffer)
        sys.stderr = _Tee(self._stderr, self._buffer)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        sys.stdout, sys.stderr = self._stdout, self._stderr
        return False

    def write_log(self, run_dir, name: str = "console.log") -> Path:
        path = Path(run_dir) / "logs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_clean(self._buffer.getvalue()), encoding="utf-8")
        return path


def _clean(text: str) -> str:
    """Collapse carriage-return progress redraws to the final state per line."""
    lines = []
    for line in text.split("\n"):
        if "\r" in line:
            line = line.split("\r")[-1]
        lines.append(line.rstrip())
    return "\n".join(lines)
