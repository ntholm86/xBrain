"""Shared logging utilities for xBrain pipeline output."""

from __future__ import annotations

import sys
import time


def log(tag: str, msg: str) -> None:
    """Print a tagged log line with encoding safety and flush."""
    line = f"[{tag:<9s}] {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(line.encode(enc, errors="replace").decode(enc, errors="replace"))
    sys.stdout.flush()


def log_phase(phase: str, description: str) -> None:
    """Print a visible phase separator for console readability."""
    print()
    print(f"{'=' * 60}")
    print(f"  {phase}: {description}")
    print(f"{'=' * 60}")
    sys.stdout.flush()


def log_llm_call(tag: str, description: str) -> "_LLMTimer":
    """Log the start of an LLM call and return a timer to log completion.

    Usage::

        timer = log_llm_call("IMMERSE", "Generating domain briefs")
        data = self.llm.generate_json(...)
        timer.done()
    """
    log(tag, f"  ⏳ {description}...")
    return _LLMTimer(tag)


class _LLMTimer:
    """Context helper that logs elapsed time on .done()."""

    __slots__ = ("_tag", "_t0")

    def __init__(self, tag: str) -> None:
        self._tag = tag
        self._t0 = time.monotonic()

    def done(self, extra: str = "") -> float:
        elapsed = time.monotonic() - self._t0
        suffix = f" — {extra}" if extra else ""
        log(self._tag, f"  ✓ done in {elapsed:.1f}s{suffix}")
        return elapsed


def log_progress(tag: str, current: int, total: int, label: str = "") -> None:
    """Log a progress indicator like [3/8]."""
    suffix = f" {label}" if label else ""
    log(tag, f"  [{current}/{total}]{suffix}")


def log_summary_line(msg: str) -> None:
    """Print a raw summary line (for final completion output)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


def log_summary_block(lines: list[str]) -> None:
    """Print multiple summary lines and flush once."""
    for line in lines:
        log_summary_line(line)
    sys.stdout.flush()
