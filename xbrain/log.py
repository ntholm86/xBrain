"""Shared logging utilities for xBrain pipeline output.

Color semantics
===============
GREEN   success, BUILD verdict, completion messages
YELLOW  warning, MUTATE verdict, overrides, conflicts
RED     error, KILL verdict, fatal outcomes
CYAN    pipeline info, phase starts, configuration
MAGENTA refinement, evolution, transformations
BLUE    scoring, CONVERGE data
DIM     detail, secondary info, item listings
WHITE   headers, separators

All log functions route through ``_safe_print`` for encoding safety.
"""

from __future__ import annotations

import os
import sys
import time

# ── ANSI color codes ──────────────────────────────────────────────────────

_NO_COLOR = os.environ.get("NO_COLOR") is not None  # https://no-color.org/

def _supports_color() -> bool:
    if _NO_COLOR:
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    if sys.stdout.isatty():
        return True
    # VS Code integrated terminal sets TERM_PROGRAM
    return os.environ.get("TERM_PROGRAM") == "vscode"

_COLOR = _supports_color()

# Enable ANSI on Windows 10+
if _COLOR and sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

class _C:
    """ANSI escape codes — all empty strings when color is disabled."""
    RESET   = "\033[0m"  if _COLOR else ""
    BOLD    = "\033[1m"  if _COLOR else ""
    DIM     = "\033[2m"  if _COLOR else ""
    CYAN    = "\033[36m" if _COLOR else ""
    GREEN   = "\033[32m" if _COLOR else ""
    YELLOW  = "\033[33m" if _COLOR else ""
    RED     = "\033[31m" if _COLOR else ""
    MAGENTA = "\033[35m" if _COLOR else ""
    BLUE    = "\033[34m" if _COLOR else ""
    WHITE   = "\033[97m" if _COLOR else ""

# Map phase tags to colors
_TAG_COLORS: dict[str, str] = {
    "IDEATE":   _C.CYAN,
    "CLI":      _C.CYAN,
    "DRY-RUN":  _C.CYAN,
    "META":     _C.MAGENTA,
    "CONSTCHK": _C.YELLOW,
    "DIVERGE":  _C.GREEN,
    "DEDUP":    _C.BLUE,
    "CONVERGE": _C.BLUE,
    "STRESS":   _C.RED,
    "REFINE":   _C.MAGENTA,
    "EVOLVE":   _C.MAGENTA,
    "MERGE":    _C.DIM,
    "SEARCH":   _C.CYAN,
    "SPECIFY":  _C.CYAN,
    "ESTIMATE": _C.CYAN,
    "LINEAGE":  _C.BLUE,
    "EXPORT":   _C.GREEN,
    "RETRY":    _C.YELLOW,
    "THROTTLE": _C.YELLOW,
    "LLM":      _C.DIM,
}

# Verdict colors (consistent everywhere)
VERDICT_COLORS: dict[str, str] = {
    "BUILD":    _C.GREEN,
    "MUTATE":   _C.YELLOW,
    "KILL":     _C.RED,
    "INCUBATE": _C.DIM,
}


def _safe_print(text: str) -> None:
    """Print with encoding safety."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def log(tag: str, msg: str) -> None:
    """Print a tagged log line with color, encoding safety, and flush."""
    color = _TAG_COLORS.get(tag.strip(), "")
    reset = _C.RESET if color else ""
    line = f"{color}[{tag:<9s}]{reset} {msg}"
    _safe_print(line)
    sys.stdout.flush()


def log_ok(tag: str, msg: str) -> None:
    """Log a success/completion message (green OK prefix)."""
    log(tag, f"{_C.GREEN}OK{_C.RESET} {msg}")


def log_warn(tag: str, msg: str) -> None:
    """Log a warning message (yellow !! prefix)."""
    log(tag, f"{_C.YELLOW}!!{_C.RESET} {msg}")


def log_error(tag: str, msg: str) -> None:
    """Log an error/failure message (red FAIL prefix)."""
    log(tag, f"{_C.RED}FAIL{_C.RESET} {msg}")


def log_detail(tag: str, msg: str) -> None:
    """Log a secondary/detail line (dimmed text)."""
    log(tag, f"{_C.DIM}{msg}{_C.RESET}")


def log_verdict(tag: str, verdict: str, msg: str) -> None:
    """Log a line with verdict-colored prefix."""
    vc = VERDICT_COLORS.get(verdict, "")
    log(tag, f"{vc}[{verdict}]{_C.RESET} {msg}")


def fmt_verdict(verdict: str) -> str:
    """Return a verdict string with proper coloring."""
    vc = VERDICT_COLORS.get(verdict, "")
    return f"{vc}{verdict}{_C.RESET}"


def fmt_verdicts(verdict_counts: dict[str, int]) -> str:
    """Format a verdict count dict like '3 BUILD | 2 MUTATE | 0 KILL'."""
    parts = []
    for v in ("BUILD", "MUTATE", "KILL", "INCUBATE"):
        count = verdict_counts.get(v, 0)
        vc = VERDICT_COLORS.get(v, "")
        parts.append(f"{vc}{count} {v}{_C.RESET}")
    return "  |  ".join(parts)


def log_phase(phase: str, description: str) -> None:
    """Print a visible phase separator for console readability."""
    print()
    bar = f"{_C.BOLD}{_C.WHITE}{'=' * 60}{_C.RESET}"
    title = f"{_C.BOLD}{_C.WHITE}  {phase}: {description}{_C.RESET}"
    _safe_print(bar)
    _safe_print(title)
    _safe_print(bar)
    sys.stdout.flush()


def log_llm_call(tag: str, description: str) -> "_LLMTimer":
    """Log the start of an LLM call and return a timer to log completion.

    Usage::

        timer = log_llm_call("IMMERSE", "Generating domain briefs")
        data = self.llm.generate_json(...)
        timer.done()
    """
    log(tag, f"  ... {description}...")
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
        log_ok(self._tag, f"done in {elapsed:.1f}s{suffix}")
        return elapsed


def log_progress(tag: str, current: int, total: int, label: str = "") -> None:
    """Log a progress indicator like [3/8]."""
    suffix = f" {label}" if label else ""
    log(tag, f"  [{current}/{total}]{suffix}")


def log_summary_line(msg: str) -> None:
    """Print a raw summary line (for final completion output)."""
    _safe_print(msg)


def log_summary_block(lines: list[str]) -> None:
    """Print multiple summary lines and flush once."""
    for line in lines:
        log_summary_line(line)
    sys.stdout.flush()
