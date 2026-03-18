import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

WORKSPACE_DIR = Path(__file__).parent.parent


class Config:
    api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model: str = os.getenv("XBRAIN_MODEL", "claude-sonnet-4-20250514")
    max_tokens: int = int(os.getenv("XBRAIN_MAX_TOKENS", "16384"))
    runs_dir: Path = WORKSPACE_DIR / "xbrain-runs"
    memory_dir: Path = WORKSPACE_DIR / "xbrain-memory"

    # Pipeline 1 defaults
    diverge_rounds: int = 1
    ideas_per_round: int = 20
    converge_top_n: int = 8
    stress_test_rounds: int = 1
    score_threshold: float = 8.0
    plateau_delta: float = 0.3

    DEFAULT_DOMAINS: list[str] = [
        "political", "scientific", "societal", "economic",
        "environmental", "technological", "creative", "health", "legal",
    ]

    # Scoring weights
    SCORING_WEIGHTS: dict[str, float] = {
        "impact": 0.25,
        "confidence": 0.20,
        "sustainability": 0.10,
        "defensibility": 0.10,
        "market_timing": 0.05,
        "effort": -0.10,
        "cost": -0.10,
        "ethical_risk": -0.10,
    }

    # Model routing strategy: "cheapest" | "balanced" | "best"
    model_strategy: str = os.getenv("XBRAIN_MODEL_STRATEGY", "single")

    # Per-1M-token pricing (input, output) — update as Anthropic changes prices
    MODEL_PRICING: dict[str, tuple[float, float]] = {
        "claude-haiku-4-5-20251001":   (1.00,  5.00),
        "claude-sonnet-4-20250514":    (3.00, 15.00),
        "claude-sonnet-4-5-20250929":  (3.00, 15.00),
        "claude-opus-4-20250514":      (15.00, 75.00),
        "claude-opus-4-1-20250805":    (15.00, 75.00),
        "claude-opus-4-5-20251101":    (15.00, 75.00),
        "claude-opus-4-6":             (15.00, 75.00),
    }

    # Phase → model routing for "cheapest" and "balanced" strategies
    # Maps phase name to model tier: "cheap" or "best"
    PHASE_ROUTING: dict[str, dict[str, str]] = {
        "cheapest": {
            "immerse": "cheap", "diverge": "cheap", "dedup": "cheap",
            "gapfill": "cheap", "converge": "cheap", "stress": "cheap",
            "refine": "cheap", "meta": "cheap", "constraints": "cheap",
            "specify": "cheap",
        },
        "balanced": {
            "immerse": "cheap", "diverge": "cheap", "dedup": "cheap",
            "gapfill": "cheap", "converge": "best", "stress": "best",
            "refine": "best", "meta": "cheap", "constraints": "cheap",
            "specify": "best",
        },
        "best": {
            "immerse": "best", "diverge": "best", "dedup": "best",
            "gapfill": "best", "converge": "best", "stress": "best",
            "refine": "best", "meta": "best", "constraints": "best",
            "specify": "best",
        },
    }

    # Cheap model (used for routing)
    cheap_model: str = os.getenv("XBRAIN_CHEAP_MODEL", "claude-haiku-4-5-20251001")
    best_model: str = os.getenv("XBRAIN_BEST_MODEL", "")
