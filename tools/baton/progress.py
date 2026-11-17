"""Progress on stderr for the long commands, so a run never looks hung.

A step line per phase (`context build [2/5] scanning code for branch points (0:03)`), and a counter for long
loops. On a terminal the counter updates in place; elsewhere (a log, CI) it prints a line at most every
`every` seconds, and always the last one. stdout is untouched, so `--json` output stays clean.
BATON_QUIET=1 silences it.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterable, Iterator
from typing import TypeVar

T = TypeVar("T")


class Progress:
    def __init__(self, name: str, steps: int = 0, stream=None, every: float = 5.0):
        self.name, self.steps, self.done_steps, self.every = name, steps, 0, every
        self.stream = stream if stream is not None else sys.stderr
        self.quiet = os.environ.get("BATON_QUIET", "") not in ("", "0")
        self.tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self.start = time.monotonic()
        self._inplace = False

    def elapsed(self) -> str:
        seconds = int(time.monotonic() - self.start)
        return f"{seconds // 60}:{seconds % 60:02d}"

    def _emit(self, text: str, inplace: bool = False) -> None:
        if self.quiet:
            return
        if inplace and self.tty:
            self.stream.write("\r\033[K" + text)
            self._inplace = True
        else:
            if self._inplace:
                self.stream.write("\r\033[K")
                self._inplace = False
            self.stream.write(text + "\n")
        self.stream.flush()

    def step(self, text: str) -> None:
        self.done_steps += 1
        where = f"[{self.done_steps}/{self.steps}] " if self.steps else ""
        self._emit(f"{self.name} {where}{text} ({self.elapsed()})")

    def note(self, text: str) -> None:
        self._emit(f"  {text}")

    def each(self, items: Iterable[T], label: str, unit: str = "files", extra=None) -> Iterator[T]:
        """Yield every item, showing `label: i/n unit` as it goes; `extra()` adds a live count."""
        items = list(items)
        total, last = len(items), 0.0
        for index, item in enumerate(items, 1):
            yield item
            now = time.monotonic()
            if (
                index == total
                or (self.tty and now - last >= 0.2)
                or (not self.tty and now - last >= self.every)
            ):
                last = now
                more = f", {extra()}" if extra else ""
                line = f"  {label}: {index}/{total} {unit}{more} ({self.elapsed()})"
                self._emit(line, inplace=index != total)
        if not total:
            self._emit(f"  {label}: no {unit}")


def silent() -> Progress:
    """For callers that pass none: the same calls, no output."""
    progress = Progress("")
    progress.quiet = True
    return progress
