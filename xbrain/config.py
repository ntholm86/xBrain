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

    ALL_DOMAINS: list[str] = [
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
