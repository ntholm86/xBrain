"""Shared helpers for pipeline phases — DRY extractions from ideate.py."""

from __future__ import annotations

import re
import unicodedata

from xbrain.log import log_detail as _log_detail
from xbrain.models import IdeaCard, ScoreBreakdown, compute_composite_score


# ------------------------------------------------------------------
# Score calibration
# ------------------------------------------------------------------

_SCORE_DIMENSIONS = (
    "impact", "confidence", "effort", "cost", "ethical_risk",
    "sustainability", "defensibility", "market_timing",
)


def apply_calibration(
    candidates: list[IdeaCard],
    calibration_data: dict | None,
    *,
    tag: str = "CONVERGE",
) -> str:
    """Apply dimension multipliers from META-LEARN to candidate scores.

    Modifies candidates in-place, re-sorts by composite score,
    and returns ``"CALIBRATED"`` or ``"UNCALIBRATED"``.
    """
    multipliers = (
        (calibration_data.get("dimension_multipliers") or {})
        if calibration_data else {}
    )
    if not multipliers:
        return "UNCALIBRATED"

    for c in candidates:
        sb = c.score_breakdown
        for dim in _SCORE_DIMENSIONS:
            m = multipliers.get(dim)
            if m is not None and m != 1.0:
                orig = getattr(sb, dim)
                setattr(sb, dim, round(max(0.0, min(10.0, orig * m)), 2))
        c.composite_score = compute_composite_score(sb)
        c.scoring_calibration_status = "calibrated"
    candidates.sort(key=lambda c: c.composite_score, reverse=True)
    _log_detail(tag, f"Calibration applied: [score]{multipliers}[/score]")
    return "CALIBRATED"


# ------------------------------------------------------------------
# Text helpers
# ------------------------------------------------------------------

def sanitize_text(text: str) -> str:
    """Replace common Unicode characters with ASCII-safe equivalents."""
    return (text
        .replace("\u2014", "--")   # em dash
        .replace("\u2013", "-")    # en dash
        .replace("\u2018", "'")    # left single quote
        .replace("\u2019", "'")    # right single quote
        .replace("\u201c", '"')    # left double quote
        .replace("\u201d", '"')    # right double quote
        .replace("\u2026", "...")   # ellipsis
        .replace("\u2192", "->")   # right arrow
        .replace("\u2190", "<-")   # left arrow
        .replace("\u2248", "~")    # approximately equal
    )


def make_run_id(brief_text: str | None = None) -> str:
    """Generate a timestamped run ID, optionally slugified from the brief."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if not brief_text:
        return ts
    slug = unicodedata.normalize("NFKD", brief_text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-").lower()
    if len(slug) > 40:
        slug = slug[:40].rsplit("-", 1)[0]
    return f"{ts}-{slug}" if slug else ts


def coerce_str(item) -> str:
    """Coerce an LLM value to a plain string.

    The LLM sometimes returns dicts where a plain string is expected.
    """
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return "; ".join(str(v) for v in item.values() if v)
    return str(item)
