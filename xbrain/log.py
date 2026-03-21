"""Shared logging utilities for xBrain pipeline output.

Uses Rich for high-quality terminal rendering: themed colors, panels,
spinners, and tables — all routed through a shared ``console`` instance.

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
"""

from __future__ import annotations

import os
import time

from rich.console import Console
from rich.markup import escape as _escape
from rich.panel import Panel
from rich.theme import Theme

# ── Shared Rich Console ──────────────────────────────────────────────────

_NO_COLOR = os.environ.get("NO_COLOR") is not None  # https://no-color.org/

XBRAIN_THEME = Theme({
    # Phase tag styles
    "tag.ideate":   "cyan",
    "tag.cli":      "cyan",
    "tag.dryrun":   "cyan",
    "tag.meta":     "magenta",
    "tag.constchk": "yellow",
    "tag.diverge":  "green",
    "tag.dedup":    "blue",
    "tag.converge": "blue",
    "tag.stress":   "red",
    "tag.refine":   "magenta",
    "tag.evolve":   "magenta",
    "tag.merge":    "dim",
    "tag.search":   "cyan",
    "tag.specify":  "cyan",
    "tag.estimate": "cyan",
    "tag.lineage":  "blue",
    "tag.export":   "green",
    "tag.retry":    "yellow",
    "tag.throttle": "yellow",
    "tag.llm":      "dim",
    # Verdict styles
    "verdict.build":    "green",
    "verdict.mutate":   "yellow",
    "verdict.kill":     "red",
    "verdict.incubate": "dim",
    # Semantic
    "ok":      "green",
    "warn":    "yellow",
    "error":   "red",
    "detail":  "dim",
    "header":  "bold white",
    "accent":  "cyan",
    "score":   "blue",
    "evolve":  "magenta",
})

console = Console(
    theme=XBRAIN_THEME,
    no_color=_NO_COLOR,
    highlight=False,
)

# Map phase tag strings to Rich style names
_TAG_STYLES: dict[str, str] = {
    "IDEATE":   "tag.ideate",
    "CLI":      "tag.cli",
    "DRY-RUN":  "tag.dryrun",
    "META":     "tag.meta",
    "CONSTCHK": "tag.constchk",
    "DIVERGE":  "tag.diverge",
    "DEDUP":    "tag.dedup",
    "CONVERGE": "tag.converge",
    "STRESS":   "tag.stress",
    "REFINE":   "tag.refine",
    "EVOLVE":   "tag.evolve",
    "MERGE":    "tag.merge",
    "SEARCH":   "tag.search",
    "SPECIFY":  "tag.specify",
    "ESTIMATE": "tag.estimate",
    "LINEAGE":  "tag.lineage",
    "EXPORT":   "tag.export",
    "RETRY":    "tag.retry",
    "THROTTLE": "tag.throttle",
    "LLM":      "tag.llm",
}

# Verdict → Rich style
_VERDICT_STYLES: dict[str, str] = {
    "BUILD":    "verdict.build",
    "MUTATE":   "verdict.mutate",
    "KILL":     "verdict.kill",
    "INCUBATE": "verdict.incubate",
}


def log(tag: str, msg: str) -> None:
    """Print a tagged log line with themed color."""
    style = _TAG_STYLES.get(tag.strip(), "")
    tag_str = f"[{style}]\\[{tag:<9s}][/{style}]" if style else f"\\[{tag:<9s}]"
    console.print(f"{tag_str} {msg}")


def escape(text: str) -> str:
    """Escape Rich markup in user-supplied text to prevent injection."""
    return _escape(text)


def log_ok(tag: str, msg: str) -> None:
    """Log a success/completion message (green OK prefix)."""
    log(tag, f"[ok]OK[/ok] {msg}")


def log_warn(tag: str, msg: str) -> None:
    """Log a warning message (yellow !! prefix)."""
    log(tag, f"[warn]!![/warn] {msg}")


def log_error(tag: str, msg: str) -> None:
    """Log an error/failure message (red FAIL prefix)."""
    log(tag, f"[error]FAIL[/error] {msg}")


def log_detail(tag: str, msg: str) -> None:
    """Log a secondary/detail line (dimmed text)."""
    log(tag, f"[detail]{msg}[/detail]")


def log_verdict(tag: str, verdict: str, msg: str) -> None:
    """Log a line with verdict-colored prefix."""
    vs = _VERDICT_STYLES.get(verdict, "")
    if vs:
        log(tag, f"[{vs}]\\[{verdict}][/{vs}] {msg}")
    else:
        log(tag, f"\\[{verdict}] {msg}")


def fmt_verdict(verdict: str) -> str:
    """Return a verdict string with proper Rich markup."""
    vs = _VERDICT_STYLES.get(verdict, "")
    return f"[{vs}]{verdict}[/{vs}]" if vs else verdict


def fmt_verdicts(verdict_counts: dict[str, int]) -> str:
    """Format a verdict count dict like '3 BUILD | 2 MUTATE | 0 KILL'."""
    parts = []
    for v in ("BUILD", "MUTATE", "KILL", "INCUBATE"):
        count = verdict_counts.get(v, 0)
        vs = _VERDICT_STYLES.get(v, "")
        if vs:
            parts.append(f"[{vs}]{count} {v}[/{vs}]")
        else:
            parts.append(f"{count} {v}")
    return "  |  ".join(parts)


def log_phase(phase: str, description: str) -> None:
    """Print a visible phase separator as a Rich Panel."""
    console.print()
    console.print(Panel(
        f"[header]{phase}: {description}[/header]",
        border_style="white",
        width=62,
        padding=(0, 1),
    ))


def log_llm_call(tag: str, description: str) -> "_LLMTimer":
    """Log the start of an LLM call with a spinner and return a timer.

    Usage::

        timer = log_llm_call("IMMERSE", "Generating domain briefs")
        data = self.llm.generate_json(...)
        timer.done()
    """
    log(tag, f"[detail]  ... {description}...[/detail]")
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
    log(tag, f"  \\[{current}/{total}]{suffix}")


def log_summary_line(msg: str) -> None:
    """Print a raw summary line (for final completion output)."""
    console.print(msg)


def log_summary_block(lines: list[str]) -> None:
    """Print multiple summary lines and flush once."""
    for line in lines:
        log_summary_line(line)
