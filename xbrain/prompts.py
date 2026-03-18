"""Prompt templates for xBrain Pipeline 1: IDEATE phases."""

# ---------------------------------------------------------------------------
# Phase 0: IMMERSE
# ---------------------------------------------------------------------------

IMMERSE_SYSTEM = (
    "You are a domain research engine. You perform deep dives into specified "
    "domains to identify tensions, opportunities, and pressure points for "
    "software intervention. You are thorough and evidence-based. "
    "You MUST respond with valid JSON only — no markdown, no commentary."
)

IMMERSE_USER = """\
Perform a deep-dive domain study for: {domains}

For EACH domain, study and report:
1. Incentive structures — who are the players? misaligned incentives?
2. Regulatory landscape — what's legal, changing, ambiguous?
3. Existing players — who's here? blind spots?
4. Historical failures — what failed? why? what changed?
5. Adjacent domains — technologies that could be imported?
6. User archetypes — who suffers most?

Respond with ONLY valid JSON:
{{
  "domain_briefs": [
    {{
      "domain": "health",
      "key_tensions": ["tension 1", "tension 2"],
      "underserved_populations": ["population 1"],
      "regulatory_windows": ["window 1"],
      "technology_gaps": ["gap 1", "gap 2"],
      "pressure_points": ["point 1", "point 2", "point 3"],
      "summary": "A paragraph summarizing key opportunities"
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# Phase 1: DIVERGE
# ---------------------------------------------------------------------------

DIVERGE_SYSTEM = (
    "You are a divergent thinking engine. Your job is to generate RAW, "
    "UNFILTERED idea seeds for software projects. Do NOT self-censor. "
    "Do NOT evaluate feasibility yet. Prioritize novelty and surprise. "
    "Think weird, go deep, find the unexpected. "
    "You MUST respond with valid JSON only — no markdown, no commentary."
)

DIVERGE_USER = """\
Generate {idea_count} raw project idea seeds. Every idea must be a \
buildable software project.

{brief_context}
{domain_context}
{constraint_context}
{memory_context}
{immersion_context}

Apply these techniques:

1. DOMAIN SCAN: For each domain, identify 2-3 unsolved problems or \
emerging opportunities that are programmable.

2. CROSS-DOMAIN COLLISION: Pick 4-5 pairs of domains and force novel \
intersections. Example: "epidemiology + misinformation = information \
contagion modeling tool."

3. CONTRARIAN INVERSION: Take 3 conventional assumptions in these \
domains and flip them. What if the opposite were true? What would you build?

4. CONTEXTUAL CONSTRAINTS: For 3-4 ideas, apply a domain-appropriate \
constraint that stress-tests real-world viability:
   - For developing-world ideas: "must work offline" or "must work on 2G"
   - For consumer ideas: "must be usable by a 10-year-old"
   - For underserved-market ideas: "must cost $0 to run"
   - For sensitive-data ideas: "must work without collecting PII"

Respond with ONLY valid JSON:
{{
  "ideas": [
    {{
      "id": "idea-001",
      "concept": "One sentence description of the idea",
      "source_technique": "domain_scan",
      "domain_tags": ["political", "technology"],
      "novelty_signal": "Why this hasn't been done or what makes it fresh"
    }}
  ]
}}

Generate at least {idea_count} idea seeds. Be bold. Go wide.
"""

# ---------------------------------------------------------------------------
# Phase 2: CONVERGE
# ---------------------------------------------------------------------------

CONVERGE_SYSTEM = (
    "You are a convergence and evaluation engine. You take raw idea seeds "
    "and filter them through clustering, persona definition, novelty "
    "assessment, and multi-dimensional scoring. You are rigorous but fair. "
    "You MUST respond with valid JSON only — no markdown, no commentary."
)

CONVERGE_USER = """\
Take these {idea_count} raw idea seeds and converge them into the top \
{top_n} strongest candidates.

RAW IDEAS:
{ideas_json}

STEPS:
1. CLUSTER: Group similar ideas. Merge overlapping concepts into stronger \
hybrids. Eliminate duplicates.

2. PERSONA: For EVERY surviving idea, define a specific primary persona:
   - who: specific role, not generic (e.g. "City council member in a \
mid-size US city")
   - pain: what problem does this solve for them?
   - context: what's their day like? tools? technical literacy?
   - motivation: why would they switch to this?

3. NOVELTY: Does this already exist? If so, what's the specific gap? \
Score novelty 0.0 to 1.0.

4. SCORE each candidate on 8 dimensions (each 0-10):
   - impact: affected population size × pain severity × urgency
   - confidence: certainty this will work, evidence strength
   - effort: implementation complexity (10 = trivial, 0 = massive)
   - cost: infrastructure cost (10 = free, 0 = very expensive)
   - ethical_risk: misuse potential (10 = very risky, 0 = no risk)
   - sustainability: revenue potential, community sustainability
   - defensibility: network effects, data moats, switching costs
   - market_timing: tech readiness, regulatory window, cultural moment

   NOTE: effort, cost, ethical_risk are NEGATIVE factors — high = bad.
   Be honest and critical, not generous.

Respond with ONLY valid JSON:
{{
  "clustering_summary": "Brief description of how ideas were clustered",
  "candidates": [
    {{
      "id": "idea-001",
      "title": "Short catchy title",
      "rationale": "One paragraph — why this matters, what it does",
      "source_technique": "domain_scan",
      "domain_tags": ["political", "game_theory"],
      "novelty_score": 0.78,
      "primary_persona": {{
        "who": "City council member in a mid-size US city",
        "pain": "No way to preview policy impact before voting",
        "context": "Non-technical, uses Excel and email",
        "motivation": "Wants data-driven decisions without hiring analysts"
      }},
      "score_breakdown": {{
        "impact": 9.0,
        "confidence": 7.5,
        "effort": 6.0,
        "cost": 3.0,
        "ethical_risk": 2.0,
        "sustainability": 6.5,
        "defensibility": 7.0,
        "market_timing": 8.0
      }},
      "estimated_effort": "medium",
      "estimated_cost_usd_month": 45,
      "ethical_risk_level": "low",
      "sustainability_model": "SaaS for municipalities at $99/month",
      "defensibility_notes": "Data moat from municipal API integrations",
      "market_timing_notes": "Open data mandates expanding"
    }}
  ]
}}

Return EXACTLY {top_n} candidates, ranked by quality (best first).
"""

# ---------------------------------------------------------------------------
# Phase 3: STRESS TEST
# ---------------------------------------------------------------------------

STRESS_TEST_SYSTEM = (
    "You are a ruthless Devil's Advocate and technical feasibility assessor. "
    "Your job is to DESTROY weak ideas and validate strong ones. Be specific, "
    "evidence-based, and devastating. An idea that survives your attacks is "
    "genuinely worth building. "
    "You MUST respond with valid JSON only — no markdown, no commentary."
)

STRESS_TEST_USER = """\
Stress-test these {candidate_count} idea candidates. For EACH idea, \
perform a thorough adversarial analysis.

CANDIDATES:
{candidates_json}

For EACH candidate:

1. FREEFORM ATTACK: Study the idea deeply. Find its weakest assumption. \
Construct the most devastating argument you can — something the creators \
didn't anticipate. Think like:
   - A competitor who wants to build something better
   - A journalist writing a takedown piece
   - A VC who's seen this pitch 50 times
   - A user who tried something similar and got burned

2. STRUCTURED ATTACKS (check each angle):
   - Prior art: "This already exists as [X]"
   - Adoption failure: "Nobody will use this because..."
   - Technical blocker: "This is impossible/impractical because..."
   - Problem reframe: "The real problem isn't what you think..."
   - Negative externalities: "This will cause harm because..."
   - Obsolescence: "In 2 years this'll be irrelevant because..."
   - Timing: "This is too early/too late because..."
   - Defensibility: "A competitor could clone this in [X] days"

3. DEFENSE: For each attack, attempt a counterargument. Be fair.

4. FEASIBILITY ASSESSMENT (score each 1-5, where 5 is best/lowest risk):
   - technical_risk, data_availability, regulatory_risk, cost_infra_month
   - time_to_prototype, maintenance_burden, llm_capability_fit
   - defensibility, market_timing
   For llm_capability_fit, consider what Claude Code is strong at (text, \
code gen, API integration, web apps) vs weak at (real-time data, custom \
visual design, native mobile, audio/video, hardware).

5. KILL CRITERIA: For surviving ideas, define 2-3 conditions that should \
abort a build if discovered during execution.

6. VERDICT:
   - BUILD: survived attacks, feasible, worth building now
   - MUTATE: good core but needs changes (describe mutation)
   - KILL: fatal flaws that can't be fixed
   - INCUBATE: promising but wrong timing or missing dependency

Respond with ONLY valid JSON:
{{
  "results": [
    {{
      "idea_id": "idea-001",
      "freeform_attack": "The most devastating attack...",
      "structured_attacks": [
        "Prior art: ...",
        "Adoption: ...",
        "Technical: ...",
        "Reframe: ...",
        "Externalities: ...",
        "Obsolescence: ...",
        "Timing: ...",
        "Defensibility: ..."
      ],
      "defenses": [
        "Defense against freeform: ...",
        "Defense against prior art: ...",
        "Defense against adoption: ...",
        "Defense against technical: ...",
        "Defense against reframe: ...",
        "Defense against externalities: ...",
        "Defense against obsolescence: ...",
        "Defense against timing: ...",
        "Defense against defensibility: ..."
      ],
      "attacks_made": 9,
      "attacks_survived": 6,
      "attacks_fatal": 3,
      "strongest_argument": "The single most compelling attack",
      "strongest_defense": "The single most compelling defense",
      "suggested_mutation": "How the idea should change (empty if BUILD)",
      "feasibility_matrix": {{
        "technical_risk": 4,
        "data_availability": 3,
        "regulatory_risk": 4,
        "cost_infra_month": 4,
        "time_to_prototype": 3,
        "maintenance_burden": 3,
        "llm_capability_fit": 4,
        "defensibility": 3,
        "market_timing": 4
      }},
      "feasibility_verdict": "BUILDABLE",
      "llm_capability_fit": "strong",
      "kill_criteria": [
        "Abort if key data API access is denied",
        "Abort if scope exceeds 3x original estimate"
      ],
      "verdict": "BUILD"
    }}
  ]
}}
"""


# ---------------------------------------------------------------------------
# Helpers to fill templates
# ---------------------------------------------------------------------------

def build_brief_context(brief_text: str | None) -> str:
    if not brief_text:
        return ""  # Open-ended ideation — no specific brief
    return (
        "USER BRIEF — This is the primary focus for ideation. All ideas should "
        "relate to or be inspired by this context:\n"
        "---\n"
        f"{brief_text}\n"
        "---\n"
        "Generate ideas that SOLVE this problem, IMPROVE on this concept, or "
        "explore ADJACENT opportunities revealed by this brief."
    )


def build_domain_context(domains: list[str] | None, default_domains: list[str]) -> str:
    if domains:
        return f"FOCUS DOMAINS: {', '.join(domains)}"
    return f"SCAN BROADLY — suggested starting domains include: {', '.join(default_domains)} (but explore beyond these if relevant)"


def build_constraint_context(constraints: list[str] | None) -> str:
    if not constraints:
        return "No specific constraints — apply contextual ones as described above."
    return "USER-SPECIFIED CONSTRAINTS:\n" + "\n".join(f"- {c}" for c in constraints)


def build_memory_context(
    past_idea_count: int,
    domain_heat_map: dict[str, int],
    killed_ideas: list[str],
) -> str:
    if past_idea_count == 0:
        return "MEMORY: This is the first run. No prior history."

    lines = [f"MEMORY: {past_idea_count} ideas generated in previous sessions."]

    if domain_heat_map:
        sorted_domains = sorted(domain_heat_map.items(), key=lambda x: -x[1])
        most = ", ".join(f"{d} ({n})" for d, n in sorted_domains[:3])
        least = ", ".join(f"{d} ({n})" for d, n in sorted_domains[-3:])
        lines.append(f"Most explored: {most}. Least explored: {least}.")

    if killed_ideas:
        lines.append("Previously killed (avoid regenerating): " + "; ".join(killed_ideas[:10]))

    return "\n".join(lines)


def build_immersion_context(domain_briefs: list[dict] | None) -> str:
    if not domain_briefs:
        return ""
    lines = ["DOMAIN BRIEFS FROM IMMERSION PHASE:"]
    for brief in domain_briefs:
        lines.append(f"\n### {brief.get('domain', 'unknown').upper()}")
        lines.append(brief.get("summary", ""))
        if brief.get("pressure_points"):
            lines.append("Pressure points: " + "; ".join(brief["pressure_points"]))
    return "\n".join(lines)
