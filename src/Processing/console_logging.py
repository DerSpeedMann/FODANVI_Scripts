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
    cap.write_log_to("reports/scan.log")   # or an exact path
"""

from __future__ import annotations

import io
import logging
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


# Ultralytics prints its per-class table through this logger, not through
# print. Its handler is bound to whatever sys.stdout was when the package was
# imported, which is the real stdout, so swapping sys.stdout afterwards does
# not reach it and the table is missing from the saved log, silently and
# exactly where it matters most.
LOGGERS = ("ultralytics",)


class capture_console:
    """Context manager that tees stdout, stderr and the library loggers into
    a buffer."""

    def __init__(self, loggers=LOGGERS) -> None:
        self._buffer = io.StringIO()
        self._stdout = None
        self._stderr = None
        self._names = tuple(loggers)
        self._handler = None

    def __enter__(self) -> "capture_console":
        self._stdout, self._stderr = sys.stdout, sys.stderr
        sys.stdout = _Tee(self._stdout, self._buffer)
        sys.stderr = _Tee(self._stderr, self._buffer)

        # Into the buffer only. The logger's own handler still writes to the
        # terminal, so adding a teeing one here would print everything twice.
        self._handler = logging.StreamHandler(self._buffer)
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        for name in self._names:
            logging.getLogger(name).addHandler(self._handler)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        for name in self._names:
            logging.getLogger(name).removeHandler(self._handler)
        self._handler = None
        sys.stdout, sys.stderr = self._stdout, self._stderr
        return False

    def write_log(self, run_dir, name: str = "console.log") -> Path:
        """Save the log under a run directory, as <run_dir>/logs/<name>."""
        return self.write_log_to(Path(run_dir) / "logs" / name)

    def write_log_to(self, path) -> Path:
        """Save the log to an exact path, for callers with no run directory."""
        path = Path(path)
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
