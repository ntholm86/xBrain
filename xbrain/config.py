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
    ideas_per_round: int = 20
    converge_top_n: int = 8
    generations: int = 1  # Number of evolutionary generations (1 = no evolution loop)

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
            "diverge": "cheap", "dedup": "cheap",
            "gapfill": "cheap", "converge": "cheap", "stress": "cheap",
            "refine": "cheap", "meta": "cheap", "constraints": "cheap",
            "specify": "cheap", "evolve": "cheap",
        },
        "balanced": {
            "diverge": "cheap", "dedup": "cheap",
            "gapfill": "cheap", "converge": "best", "stress": "best",
            "refine": "best", "meta": "cheap", "constraints": "cheap",
            "specify": "best", "evolve": "cheap",
        },
        "best": {
            "diverge": "best", "dedup": "best",
            "gapfill": "best", "converge": "best", "stress": "best",
            "refine": "best", "meta": "best", "constraints": "best",
            "specify": "best", "evolve": "best",
        },
    }

    # Per-phase max output tokens — keeps LLM responses tight and saves cost.
    # Override globally with XBRAIN_MAX_TOKENS env var; tweak individual phases here.
    PHASE_MAX_TOKENS: dict[str, int] = {
        "meta":              2048,
        "constraints":       1024,
        "diverge":           10240,
        "dedup":             2048,
        "gapfill":           8192,
        "converge-cluster":  6144,
        "converge-compare":  12288,
        "converge-enrich":   12288,
        "stress-attack":     4096,
        "refine-diverge":    8192,
        "refine-converge":   12288,
        "evolve":            8192,
    }

    # Cheap model (used for routing)
    cheap_model: str = os.getenv("XBRAIN_CHEAP_MODEL", "claude-haiku-4-5-20251001")
    best_model: str = os.getenv("XBRAIN_BEST_MODEL", "") or os.getenv("XBRAIN_MODEL", "claude-sonnet-4-20250514")
