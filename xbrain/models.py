"""Data models for xBrain Pipeline 1: IDEATE."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    impact: float = Field(ge=0, le=10, default=0)
    confidence: float = Field(ge=0, le=10, default=0)
    effort: float = Field(ge=0, le=10, default=0)
    cost: float = Field(ge=0, le=10, default=0)
    ethical_risk: float = Field(ge=0, le=10, default=0)
    sustainability: float = Field(ge=0, le=10, default=0)
    defensibility: float = Field(ge=0, le=10, default=0)
    market_timing: float = Field(ge=0, le=10, default=0)


class Persona(BaseModel):
    who: str = ""
    pain: str = ""
    context: str = ""
    motivation: str = ""


class DemandSignal(BaseModel):
    method: str = ""
    score: float = 0.0
    sample_size: int = 0
    key_quote: str = ""


class FeasibilityMatrix(BaseModel):
    technical_risk: int = Field(ge=1, le=5, default=3)
    data_availability: int = Field(ge=1, le=5, default=3)
    regulatory_risk: int = Field(ge=1, le=5, default=3)
    cost_infra_month: int = Field(ge=1, le=5, default=3)
    time_to_prototype: int = Field(ge=1, le=5, default=3)
    maintenance_burden: int = Field(ge=1, le=5, default=3)
    llm_capability_fit: int = Field(ge=1, le=5, default=3)
    defensibility: int = Field(ge=1, le=5, default=3)
    market_timing: int = Field(ge=1, le=5, default=3)


class DebateExchange(BaseModel):
    """A single attack-defense-rebuttal exchange in the adversarial debate."""
    angle: str = ""                 # e.g. "Prior art", "Adoption failure"
    attack: str = ""
    defense: str = ""
    attacker_rebuttal: str = ""
    defender_rebuttal: str = ""
    outcome: str = ""               # SURVIVED / FATAL / WEAKENED


# ------------------------------------------------------------------
# LLM response shapes (used for validation, not stored)
# ------------------------------------------------------------------

class AttackResponse(BaseModel):
    """Shape returned by the attack-phase LLM for a single idea."""
    idea_id: str = ""
    freeform_attack: str = ""
    structured_attacks: list[str] = Field(default_factory=list)
    defenses: list[str] = Field(default_factory=list)
    attacks_made: int = 0
    attacks_survived: int = 0
    attacks_fatal: int = 0
    strongest_argument: str = ""
    strongest_defense: str = ""
    suggested_mutation: str = ""
    feasibility_matrix: dict = Field(default_factory=dict)
    feasibility_verdict: str = ""
    llm_capability_fit: str = ""
    kill_criteria: list[str] = Field(default_factory=list)
    verdict: str = ""
    error_source: str = ""         # "" = genuine, "api_crash" = exception fallback


class DefenseExchangeItem(BaseModel):
    """One angle's defense from the defense-phase LLM."""
    angle: str = ""
    attack_summary: str = ""
    defense: str = ""
    strengths_ignored: str = ""
    pivot_if_needed: str = ""
    outcome: str = ""


class DefenseResponse(BaseModel):
    """Shape returned by the defense-phase LLM for a single idea."""
    idea_id: str = ""
    exchanges: list[DefenseExchangeItem] = Field(default_factory=list)
    overall_defense_strength: str = ""
    strongest_defense: str = ""


class RebuttalExchangeItem(BaseModel):
    """One angle's rebuttal from the rebuttal-phase LLM."""
    angle: str = ""
    attacker_rebuttal: str = ""
    defender_rebuttal: str = ""
    final_outcome: str = ""


class RebuttalResponse(BaseModel):
    """Shape returned by the rebuttal-phase LLM for a single idea."""
    idea_id: str = ""
    exchanges: list[RebuttalExchangeItem] = Field(default_factory=list)
    strongest_argument: str = ""
    strongest_defense: str = ""
    suggested_mutation: str = ""
    feasibility_matrix: dict = Field(default_factory=dict)
    feasibility_verdict: str = ""
    llm_capability_fit: str = ""
    kill_criteria: list[str] = Field(default_factory=list)
    attacks_made: int = 0
    attacks_survived: int = 0
    attacks_fatal: int = 0
    verdict: str = ""


class StressTestResult(BaseModel):
    idea_id: str
    freeform_attack: str = ""
    structured_attacks: list[str] = Field(default_factory=list)
    defenses: list[str] = Field(default_factory=list)
    debate_rounds: list[DebateExchange] = Field(default_factory=list)
    attacks_made: int = 0
    attacks_survived: int = 0
    attacks_fatal: int = 0
    strongest_argument: str = ""
    strongest_defense: str = ""
    suggested_mutation: str = ""
    feasibility_matrix: FeasibilityMatrix = Field(default_factory=FeasibilityMatrix)
    feasibility_verdict: str = ""  # BUILDABLE / NEEDS_SCOPING / NOT_FEASIBLE
    llm_capability_fit: str = ""   # strong / moderate / weak
    kill_criteria: list[str] = Field(default_factory=list)
    verdict: str = ""              # BUILD / KILL / MUTATE / INCUBATE
    error_source: str = ""         # "" = genuine verdict, "api_crash" = exception fallback


class RawIdea(BaseModel):
    id: str
    concept: str
    source_technique: str  # domain_scan / cross_domain_collision / contrarian_inversion / constraint_injection
    domain_tags: list[str] = Field(default_factory=list)
    novelty_signal: str = ""


class DomainBrief(BaseModel):
    domain: str
    key_tensions: list[str] = Field(default_factory=list)
    underserved_populations: list[str] = Field(default_factory=list)
    regulatory_windows: list[str] = Field(default_factory=list)
    technology_gaps: list[str] = Field(default_factory=list)
    pressure_points: list[str] = Field(default_factory=list)
    summary: str = ""


class IdeaCard(BaseModel):
    id: str
    title: str
    rationale: str
    elevator_pitch: str = ""  # Plain-language summary for non-experts
    hypotheses: list = Field(default_factory=list)  # Populated by Pipeline 2
    composite_score: float = 0.0
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    scoring_calibration_status: str = "uncalibrated"
    estimated_effort: str = ""       # small / medium / large
    estimated_cost_usd_month: float = 0.0
    ethical_risk: str = ""           # low / medium / high
    novelty_score: float = 0.0
    domain_tags: list[str] = Field(default_factory=list)
    source_technique: str = ""
    parent_ideas: list[str] = Field(default_factory=list)
    primary_persona: Persona = Field(default_factory=Persona)
    distribution_channel: str = ""
    demand_signal: Optional[DemandSignal] = None
    sustainability_model: str = ""
    defensibility_notes: str = ""
    market_timing_notes: str = ""
    score_reasoning: dict[str, str] = Field(default_factory=dict)
    inverse_terrible_conditions: list[str] = Field(default_factory=list)
    inverse_confidence: float = 0.0
    llm_capability_fit: str = ""
    key_assumptions: list = Field(default_factory=list)  # list of dicts: {claim, validation_cost, validation_method}
    first_customer_profile: dict = Field(default_factory=dict)
    cost_context: str = ""  # e.g. "monthly infra" or "one-time implementation"
    backlog_state: str = "active"
    stress_test_verdict: str = ""
    kill_arguments_survived: int = 0
    phase: str = "stress_test"
    generation: int = 1
    evolution_rationale: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class IdeateRunResult(BaseModel):
    run_id: str
    brief_text: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    constraints: list[str] = Field(default_factory=list)
    domain_briefs: list[DomainBrief] = Field(default_factory=list)
    raw_ideas: list[RawIdea] = Field(default_factory=list)
    candidates: list[IdeaCard] = Field(default_factory=list)
    stress_test_results: list[StressTestResult] = Field(default_factory=list)
    survivors: list[IdeaCard] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0


def compute_composite_score(sb: ScoreBreakdown) -> float:
    """Compute the normalized composite score (0-10) from raw dimension scores."""
    from .config import Config
    w = Config.SCORING_WEIGHTS
    raw = (
        w["impact"] * sb.impact
        + w["confidence"] * sb.confidence
        + w["sustainability"] * sb.sustainability
        + w["defensibility"] * sb.defensibility
        + w["market_timing"] * sb.market_timing
        + w["effort"] * sb.effort
        + w["cost"] * sb.cost
        + w["ethical_risk"] * sb.ethical_risk
    )
    # Raw range: -3.0 to 7.0 → normalize to 0-10
    normalized = raw + 3.0
    return round(max(0.0, min(10.0, normalized)), 1)
