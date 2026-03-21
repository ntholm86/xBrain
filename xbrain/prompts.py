"""Prompt templates for xBrain Pipeline 1: IDEATE phases."""

# ---------------------------------------------------------------------------
# Constraint Conflict Detection
# ---------------------------------------------------------------------------

CONSTRAINT_CHECK_SYSTEM = (
    "You are a constraint analysis engine. Detect logical contradictions, "
    "tensions, and impossible combinations in user-specified constraints. "
    "Be precise. Only flag REAL conflicts, not minor tensions. "
    "You MUST respond with valid JSON only — no markdown, no commentary."
)

CONSTRAINT_CHECK_USER = """\
Analyze these {constraint_count} constraints for logical conflicts:

{constraints_list}

For each pair of constraints that CONFLICT (are logically impossible or \
very difficult to satisfy simultaneously), report:
- Which two constraints conflict
- Why they conflict
- A suggested resolution (relax one, prioritize, or reframe)

Only report REAL conflicts — not minor tensions. If constraints are merely \
challenging but not contradictory, do NOT flag them.

Respond with ONLY valid JSON:
{{
  "conflicts": [
    {{
      "constraints": ["constraint A text", "constraint B text"],
      "reason": "Why these conflict",
      "severity": "hard|soft",
      "suggestion": "How to resolve"
    }}
  ],
  "notes": "Any general observations about the constraint set"
}}

If there are NO conflicts, respond with: {{"conflicts": [], "notes": "No conflicts detected."}}
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
Generate {idea_count} raw idea seeds. Ideas can be anything: software \
projects, features, process changes, integrations, research directions, \
architectural redesigns, or unconventional approaches. Let the brief \
define what's in scope — don't pre-filter by format.

{brief_context}
{domain_context}
{constraint_context}
{memory_context}
{immersion_context}
{playbook_context}
{winner_repulsion_context}
{failure_taxonomy_context}
{kill_reason_context}
{gene_context}
{technique_weight_context}

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

5. EXPERTISE-AGNOSTIC: Don't filter out ideas based on assumed builder \
skill level. If the brief doesn't specify who's building, generate ideas \
across all difficulty levels — from quick wins to ambitious moonshots. \
Include ideas that leverage AI tools where relevant, but also include \
ideas that don't.

6. MECHANISM STEALING (Inverse Ideation): Think of 3-5 products or \
systems that have succeeded recently (in ANY domain). Extract their \
core MECHANISM — the underlying pattern that makes them work (e.g., \
"Uber's mechanism = real-time matching of idle capacity to immediate \
demand"). Now apply each mechanism to the brief's domain or a completely \
different domain. The idea should NOT be a clone — it should transplant \
the mechanism into a new context where it creates unexpected value.

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
# Phase 1b: DEDUP — Semantic deduplication pre-filter
# ---------------------------------------------------------------------------

DEDUP_SYSTEM = (
    "You are a deduplication engine. Your job is to identify semantically "
    "identical or near-identical ideas — same core concept expressed in "
    "different words. Be aggressive about collapsing true duplicates but "
    "preserve genuinely distinct variations. "
    "You MUST respond with valid JSON only — no markdown, no commentary."
)

DEDUP_USER = """\
Analyze these {idea_count} raw idea seeds and identify duplicates or \
near-duplicates (same core concept, different wording).

IDEAS:
{ideas_json}

DEDUP in TWO passes:

PASS 1 — SURFACE DEDUP: Find ideas with the same core concept expressed \
in different words. For each cluster, keep the BEST version (most specific, \
most novel framing) and mark the rest for removal.

PASS 2 — CONCEPTUAL CONVERGENCE: Step back and look at the ABSTRACT \
solution shape of each surviving idea. Group ideas by their underlying \
mechanism (e.g., "aggregation platform", "monitoring dashboard", \
"marketplace connector", "AI analysis layer"). If more than 40% of \
surviving ideas share the same abstract solution shape, mark the \
weakest examples for removal and add their solution shape to \
overrepresented_themes. The final set MUST have at least 3 genuinely \
different solution approaches.

Also report what themes are OVER-REPRESENTED (too many similar ideas) \
and what areas have GAPS (no ideas generated despite being relevant).

Respond with ONLY valid JSON:
{{
  "keep": ["idea-001", "idea-003", "idea-005"],
  "remove": [
    {{"id": "idea-002", "duplicate_of": "idea-001", "reason": "Same concept as idea-001 but less specific"}}
  ],
  "overrepresented_themes": ["theme 1", "theme 2"],
  "gap_areas": ["area with no ideas that should have been explored", "another gap"]
}}
"""

# ---------------------------------------------------------------------------
# Phase 1c: DIVERGE GAP-FILL — Fill gaps identified by dedup
# ---------------------------------------------------------------------------

DIVERGE_GAPFILL_SYSTEM = (
    "You are a divergent thinking engine specializing in gap-filling. "
    "You have seen the ideas from a previous round and know which themes "
    "are over-represented and which areas are unexplored. Your job is to "
    "generate ideas ONLY in the gap areas — do NOT repeat themes that "
    "already have enough ideas. Be maximally creative and diverse. "
    "You MUST respond with valid JSON only — no markdown, no commentary."
)

DIVERGE_GAPFILL_USER = """\
Generate {idea_count} NEW idea seeds that fill the gaps from a previous \
ideation round.

{brief_context}
{domain_context}
{playbook_context}

PREVIOUS ROUND ANALYSIS:
- Over-represented themes (DO NOT generate more of these): {overrepresented}
- Gap areas (FOCUS here): {gaps}
- Previous ideas (DO NOT duplicate): {previous_titles}

Generate ideas that are MAXIMALLY DIFFERENT from the previous round. \
Explore the gap areas aggressively. Use contrarian thinking.

Respond with ONLY valid JSON:
{{
  "ideas": [
    {{
      "id": "gap-001",
      "concept": "One sentence description",
      "source_technique": "gap_fill",
      "domain_tags": ["domain1", "domain2"],
      "novelty_signal": "Why this fills a gap"
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# Phase 2: CONVERGE (decomposed into 3 sub-phases)
# ---------------------------------------------------------------------------

# --- Sub-phase 2A: CLUSTER + INITIAL SCORE ---

CONVERGE_SYSTEM = (
    "You are a convergence and evaluation engine. You take raw idea seeds "
    "and filter them through clustering and multi-dimensional scoring. "
    "You are rigorous but fair. "
    "You MUST respond with valid JSON only — no markdown, no commentary."
)

CONVERGE_USER = """\
Converge {idea_count} raw idea seeds into the top {top_n} candidates.

{brief_context}

RAW IDEAS:
{ideas_json}

{calibration_context}
{novelty_context}

STEPS:
1. CLUSTER similar ideas, merge overlaps, eliminate duplicates.
2. ADAPT OUTPUT TO BRIEF TYPE: Read the brief carefully and match your output:
   - If the brief describes a PRODUCT/STARTUP opportunity → use product fields \
(persona=target customer, cost=infrastructure cost, defensibility=market moat).
   - If the brief describes an INTERNAL TOOL IMPROVEMENT → use internal fields \
(persona=tool operator/developer, cost=implementation effort, \
defensibility=why this approach is better than alternatives).
   - If the brief describes a PROCESS/WORKFLOW change → use process fields \
(persona=person doing the work, cost=transition cost, \
defensibility=why this process is hard to replicate).
   - If no brief or unclear → default to product fields.
   CRITICAL: Do NOT force product framing on non-product ideas. If the brief \
asks "how to improve X internally", the persona is the builder/operator of X, \
not an external customer. The cost is implementation effort, not SaaS pricing.
3. NOVELTY: Score 0.0-1.0. Does this exist? What's the gap?
4. SCORE on 8 dimensions (0-10). effort/cost/ethical_risk are NEGATIVE (high=bad). \
Consider AI leverage when scoring effort.
   Dimensions: impact, confidence, effort, cost, ethical_risk, sustainability, \
defensibility, market_timing.

SCORING RULES (mandatory):
- USE THE FULL RANGE: The best idea should score 8-10 on its strongest dimension. \
The weakest should have at least one dimension scoring 3 or below.
- DIFFERENTIATE EFFORT: Not every idea is "medium" effort. At least one must be \
"small" and at least one must be "large" (if {top_n} >= 3). \
Use the effort SCORE to decide: effort >= 7 → "large", effort <= 3 → "small". \
DO NOT mark all ideas as medium — that means you failed to differentiate.
- BE HARSH on ideas that are generic, vague, or that any competent developer \
could build in a weekend. These should score below 5 on impact and defensibility.

Respond with ONLY this JSON structure:
{{
  "clustering_summary": "...",
  "candidates": [{{
    "id": "idea-001", "title": "...",
    "elevator_pitch": "Plain-language summary anyone can understand — no jargon, no buzzwords. Explain WHAT it is and WHY someone would want it, like you're telling a friend over coffee. 1-2 sentences.",
    "rationale": "Technical details: defensibility, confidence drivers, key risks. Dense and specific.",
    "source_technique": "...", "domain_tags": ["..."],
    "novelty_score": 0.78,
    "score_breakdown": {{"impact": 9, "confidence": 7, "effort": 6, "cost": 3, \
"ethical_risk": 2, "sustainability": 6, "defensibility": 7, "market_timing": 8}},
    "estimated_effort": "small|medium|large",
    "estimated_cost_usd_month": 45,
    "cost_context": "monthly infra|one-time implementation|monthly labor|transition cost",
    "ethical_risk_level": "low|medium|high"
  }}]
}}

LENGTH LIMIT: Keep elevator_pitch under 200 characters — plain language only, \
no technical jargon. Keep rationale under 200 characters — dense and technical.

Return EXACTLY {top_n} candidates, best first. Be critical, not generous.
"""

# --- Sub-phase 2B: COMPARATIVE RANKING ---

CONVERGE_COMPARE_SYSTEM = (
    "You are a comparative judgment engine. You force-rank ideas by direct "
    "head-to-head comparison on specific dimensions. You are decisive and "
    "must pick clear winners — never declare ties. "
    "You MUST respond with valid JSON only — no markdown fences, no commentary, no ```."
)

CONVERGE_COMPARE_USER = """\
You have {candidate_count} idea candidates with initial scores. Your job \
is to FORCE-RANK them by comparative analysis on 3 key dimensions: \
impact, confidence, and defensibility.

{brief_context}

CANDIDATES (with initial scores):
{candidates_json}

PROCESS:
1. For EACH of the 3 dimensions, produce a ranked list from strongest to \
weakest. No ties allowed. Justify each ranking with one sentence.
2. Synthesize the 3 dimension rankings into a SINGLE overall final ranking.
3. Produce adjusted scores that SPREAD across the full range.

SCORING ADJUSTMENTS:
- The gap between rank #1 and rank #{candidate_count} must be at least 3.0 \
points on impact, confidence, and defensibility.
- Rank #1 gets 9-10 on its strongest dim. Last place gets 3-5.
- Keep effort, cost, ethical_risk, sustainability, market_timing from the \
initial scores unless you found a clear error.

Respond with ONLY this JSON (no markdown fences):
{{
  "dimension_rankings": {{
    "impact": [{{"id": "idea-001", "reason": "One sentence"}}],
    "confidence": [{{"id": "idea-001", "reason": "One sentence"}}],
    "defensibility": [{{"id": "idea-001", "reason": "One sentence"}}]
  }},
  "final_ranking": ["idea-001", "idea-003", "idea-002"],
  "adjusted_scores": [
    {{
      "id": "idea-001",
      "score_breakdown": {{"impact": 9, "confidence": 8, "effort": 6, "cost": 3, \
"ethical_risk": 2, "sustainability": 7, "defensibility": 8, "market_timing": 7}},
      "rank_rationale": "One sentence: why this rank"
    }}
  ]
}}
"""

# --- Sub-phase 2C: ENRICH + ASSUMPTION INVERSION ---

CONVERGE_ENRICH_SYSTEM = (
    "You are an idea enrichment and risk analysis engine. Your job is to "
    "deeply characterize ranked idea candidates: define personas, generate "
    "specific assumptions, stress-test those assumptions via inversion, "
    "and build customer profiles. You are thorough and evidence-based. "
    "You MUST respond with valid JSON only — no markdown fences, no commentary, no ```."
)

CONVERGE_ENRICH_USER = """\
Enrich these {candidate_count} ranked idea candidates with deep characterization.

{brief_context}

CANDIDATES (already scored and ranked):
{candidates_json}

For EACH candidate, generate:

1. PRIMARY PERSONA: Match the brief's context.
   - If brief describes internal tooling → persona = tool operator/developer
   - If brief describes a product → persona = target customer
   - NEVER default to "Series B startup" unless the brief says so.

2. KEY ASSUMPTIONS with INVERSION TEST: For each idea, list 3-5 assumptions \
that are UNIQUE TO THAT IDEA. Do NOT use generic assumptions like "target \
persona exists" — name the specific, falsifiable claim.

   For EACH assumption, also generate:
   - inverse_claim: The OPPOSITE of the assumption (e.g., if assumption is \
"LLM can parse regulatory filings with >90% accuracy", the inverse is \
"LLM CANNOT parse regulatory filings with >90% accuracy")
   - inverse_defense_quality: 1-5 rating of how well the INVERSE can be \
defended. If the inverse is easy to defend (score 4-5), the original \
assumption is FRAGILE and the idea has a critical vulnerability.
   - fragility_flag: "fragile" if inverse_defense_quality >= 4, else "solid"

   Order assumptions cheapest-to-validate FIRST.

3. MOAT CHECK: Assess defensibility. If weak, suggest a concrete mutation.

4. INVERSE CONDITIONS: 2-3 conditions that would make this terrible. \
Rate inverse_confidence 0-10 (10=fragile).

5. FIRST CUSTOMER PROFILE: Must match the brief's scale and context.

Respond with ONLY this JSON:
{{
  "enrichments": [
    {{
      "id": "idea-001",
      "primary_persona": {{"who": "...", "pain": "...", "context": "...", "motivation": "..."}},
      "key_assumptions": [
        {{
          "claim": "Specific falsifiable claim",
          "inverse_claim": "The opposite claim",
          "inverse_defense_quality": 3,
          "fragility_flag": "solid",
          "validation_cost": "low|medium|high",
          "validation_method": "How to test this cheaply"
        }}
      ],
      "sustainability_model": "...",
      "defensibility_notes": "...",
      "market_timing_notes": "...",
      "first_customer_profile": {{"type": "...", "size": "...", "readiness": "...", "why_first": "..."}},
      "inverse_score": {{"terrible_conditions": ["..."], "inverse_confidence": 4.5}}
    }}
  ]
}}

LENGTH LIMIT: sustainability_model, defensibility_notes, market_timing_notes \
each under 150 characters. claims and inverse_claims under 100 characters. Be dense.
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
perform a thorough adversarial analysis, then assess feasibility.

{brief_context}
{adaptive_stress_context}

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
   - Expertise gap: "Building this requires domain expertise in [X] — \
assess whether that expertise is obtainable"

3. STRONGEST DEFENSE: For each structured attack, also provide the \
strongest possible counter-argument in one sentence. Be fair — if the \
idea has a genuine strength that neutralizes the attack, say so.

4. FEASIBILITY (score each 1-5, where 5 is best/lowest risk):
   - technical_risk, data_availability, regulatory_risk, cost_infra_month
   - time_to_prototype, maintenance_burden, llm_capability_fit
   - defensibility, market_timing

5. KILL CRITERIA: 2-3 conditions that should abort a build if discovered.

6. VERDICT (be decisive — MUTATE is not a safe default):
   - BUILD: more attacks survived than failed, no single fatal flaw \
that invalidates the core concept. Most ideas should get BUILD if they \
have a strong core. QUANTITATIVE RULE: if attacks_survived >= 5 out of 9, \
the verdict MUST be BUILD unless there is exactly one irreparable fatal flaw.
   - MUTATE: the core concept is valid BUT a specific, named flaw \
requires a concrete change (you MUST describe the exact mutation). \
Do NOT use MUTATE as a hedge — if the idea works, say BUILD. \
MUTATE is ONLY for ideas where you can name the exact thing to change.
   - KILL: a fatal flaw that cannot be fixed by any mutation. The \
fundamental premise is wrong. Use this for ideas with broken economics, \
impossible technical requirements, or saturated markets with no gap.
   - INCUBATE: the idea is good but depends on something that doesn't \
exist yet (regulation, technology, market shift). Name the dependency.

LENGTH LIMIT: Keep each field under 150 characters. Each structured_attack \
and defense entry must be ONE sentence. freeform_attack max 2 sentences. Be dense.

ATTACK CONFIDENCE: Rate your overall confidence in your attack assessment \
(attack_confidence: 0.0-1.0). 1.0 = iron-clad evidence, concrete prior art, \
proven failure pattern. 0.5 = speculative attack based on general reasoning. \
0.0 = you're guessing. Be honest — a hedged attack with low confidence is \
more useful than a confident-sounding attack that's actually speculative.

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
        "Prior art defense: ...",
        "Adoption defense: ...",
        "Technical defense: ..."
      ],
      "attacks_made": 9,
      "attacks_survived": 6,
      "attacks_fatal": 3,
      "strongest_argument": "The single most compelling attack",
      "strongest_defense": "The single most compelling counter-argument",
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
      "kill_criteria": [
        "Abort if ...",
        "Abort if ..."
      ],
      "attack_confidence": 0.8,
      "verdict": "BUILD"
    }}
  ]
}}
"""

def build_search_context(search_text: str) -> str:
    if not search_text:
        return ""
    return (
        "CURRENT MARKET DATA (from live web search — use this to ground your analysis "
        "in current reality, validate competitors, and identify recent trends):\n"
        f"{search_text}\n"
        "---\n"
        "Use the above search results to inform your analysis. Correct any outdated "
        "assumptions. If search results contradict your prior knowledge, prefer the "
        "search results (they are more recent).\n"
    )


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


def build_domain_context() -> str:
    return (
        "SCAN ALL DOMAINS — no domain restrictions. Explore every field of human "
        "activity: technology, science, health, finance, education, agriculture, "
        "logistics, entertainment, government, law, art, sports, manufacturing, "
        "energy, real estate, social impact, defense, space, food, fashion, "
        "religion, philosophy, psychology, and ANY other domain you can think of. "
        "Do NOT anchor on a small set of familiar domains. Go maximally wide. "
        "The best ideas often come from domains nobody thought to look at."
    )


def build_constraint_context(constraints: list[str] | None) -> str:
    if not constraints:
        return "No specific constraints — apply contextual ones as described above."
    return "USER-SPECIFIED CONSTRAINTS:\n" + "\n".join(f"- {c}" for c in constraints)


def build_winner_repulsion_context(previous_winners: list[dict]) -> str:
    """Build context that penalizes ideas too similar to previous run winners."""
    if not previous_winners:
        return ""
    lines = [
        "DIVERSITY RATCHET — Previous runs produced these winning ideas. "
        "Do NOT generate ideas that are semantically similar to any of these. "
        "Each new run must explore DIFFERENT solution spaces, mechanisms, and "
        "domains. If you find yourself generating something that sounds like "
        "a rephrasing of a previous winner, STOP and think of something "
        "structurally different:"
    ]
    for w in previous_winners:
        domains = ", ".join(w.get("domains", [])[:3])
        lines.append(f"- [{w.get('score', 0):.1f}] {w['title']} ({domains})")
    return "\n".join(lines)


def build_kill_reason_context(kill_log: list[dict]) -> str:
    """Build negative constraints from kill reasons — inject WHY ideas died, not just titles."""
    if not kill_log:
        return ""
    # Deduplicate reasons by first 60 chars to collapse similar kill reasons
    seen: set[str] = set()
    unique_reasons: list[str] = []
    for k in kill_log[-20:]:  # Recent 20 kills
        reason = (k.get("reason", "") or "").strip()
        if not reason or len(reason) < 15:
            continue
        key = reason[:60].lower()
        if key not in seen:
            seen.add(key)
            unique_reasons.append(reason[:150])
    if not unique_reasons:
        return ""
    lines = [
        "KILL-REASON PRE-FILTER — These are the specific reasons ideas were "
        "KILLED in previous runs. DO NOT generate ideas vulnerable to these "
        "attack vectors:"
    ]
    for reason in unique_reasons[:8]:
        lines.append(f"- AVOID: {reason}")
    return "\n".join(lines)


def build_failure_taxonomy_context(taxonomy: dict) -> str:
    """Build context from structured failure taxonomy to help ideas pre-empt common failure modes."""
    if not taxonomy:
        return ""
    lines = [
        "FAILURE AUTOPSY — These are the most common ways ideas have died in "
        "previous runs. Design your ideas to pre-empt these failure modes:"
    ]
    for category, entries in taxonomy.items():
        if entries:
            # Show category with count and most recent example
            lines.append(f"- {category} ({len(entries)} occurrences): {entries[-1][:100]}")
    return "\n".join(lines)


# Canonical failure categories for blocklist extraction
CANONICAL_FAILURE_TYPES = {
    "prior_art": ["prior art", "already exists", "existing solution", "competitor", "been done"],
    "adoption": ["adoption", "switching cost", "user acquisition", "won't use", "no demand"],
    "technical": ["technical", "infeasible", "can't build", "complexity", "scalability"],
    "timing": ["timing", "too early", "too late", "market window", "premature"],
    "defensibility": ["defensib", "moat", "easily copied", "no barrier", "commodit"],
    "economics": ["economic", "unit economics", "revenue", "pricing", "margin", "cost"],
}


def build_failure_blocklist_context(failure_types: dict[str, list[str]]) -> str:
    """Build HARD constraint blocklist from canonical failure types found in stress tests.

    Unlike soft context, this uses imperative prohibitions to prevent the LLM
    from regenerating ideas that fall into the same failure categories.
    """
    if not failure_types:
        return ""
    lines = [
        "🚫 HARD FAILURE BLOCKLIST — DO NOT generate ideas that fall into these "
        "failure categories. These specific weaknesses killed or damaged ideas "
        "in the previous round. Any new idea exhibiting these patterns will be "
        "immediately rejected:",
    ]
    for category, examples in failure_types.items():
        label = category.replace("_", " ").title()
        example_text = examples[0][:120] if examples else ""
        lines.append(f"- BLOCKED: {label} — \"{example_text}\"")
    lines.append(
        "\nEvery new idea MUST include a one-sentence explanation of why it "
        "does NOT suffer from any of the blocked failure types above."
    )
    return "\n".join(lines)


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


def build_refinement_context(
    mutations: list[dict] | None,
    attack_patterns: list[dict] | None,
    banned_concepts: list[str] | None = None,
    reframe_attacks: list[str] | None = None,
) -> str:
    """Build context from previous failed ideas to guide refinement round."""
    if not mutations and not attack_patterns and not banned_concepts and not reframe_attacks:
        return ""

    lines = ["LEARNING FROM PREVIOUS ROUND (Refinement Context):"]

    if banned_concepts:
        lines.append("\nBANNED CONCEPTS — DO NOT generate ideas similar to ANY of these. "
                      "They have already been tried and either failed stress tests or are "
                      "too similar to existing candidates. Generate ideas in COMPLETELY "
                      "DIFFERENT solution spaces:")
        for concept in banned_concepts:
            lines.append(f"- {concept}")

    if reframe_attacks:
        lines.append("\nPROBLEM REFRAMES — Stress testing revealed these alternative ways "
                      "to think about the problem. Use these as STARTING POINTS for new ideas "
                      "instead of the original brief framing:")
        for reframe in reframe_attacks:
            lines.append(f"- {reframe}")

    if mutations:
        lines.append("\nSuggested mutations from MUTATE ideas:")
        for m in mutations[:5]:  # Top 5 mutations to avoid overwhelming
            idea_title = m.get("idea_title", "")
            mutation = m.get("suggested_mutation", "")
            if mutation:
                lines.append(f"- [{idea_title}]: {mutation}")

    if attack_patterns:
        lines.append("\nCommon fatal attacks to avoid in new ideas:")
        for pattern in attack_patterns[:5]:  # Top 5 patterns
            pattern_text = pattern.get("pattern", "")
            frequency = pattern.get("frequency", 0)
            if pattern_text:
                lines.append(f"- [{frequency}x]: {pattern_text}")

    lines.append(
        "\nUSE THIS: Generate ideas that are STRUCTURALLY DIFFERENT from banned concepts, "
        "explore the problem reframes as alternative angles, incorporate mutation learnings, "
        "and pre-emptively defend against the common fatal attacks listed above."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 4: EVOLVE — Multi-generation evolutionary operators
# ---------------------------------------------------------------------------

EVOLVE_SYSTEM = (
    "You are an evolutionary idea-engineering engine. You take ideas that "
    "survived adversarial stress testing and apply evolutionary operators "
    "(mutation, crossover, novelty search) to produce a superior next "
    "generation. Every new idea must be STRICTLY BETTER than its parents — "
    "specifically addressing the weaknesses exposed by stress testing. "
    "You MUST respond with valid JSON only — no markdown, no commentary."
)

EVOLVE_USER = """\
GENERATION {generation}/{max_generations}: Evolve survivors into a stronger next generation.

{brief_context}

SURVIVORS FROM PREVIOUS GENERATION (with stress test results):
{survivors_json}

{gene_context}

{mutation_archive_context}

{attack_pattern_context}

EVOLUTIONARY OPERATORS — apply ALL of these:

1. ELITE CARRY-FORWARD: The top {elite_count} BUILD-verdict ideas survive \
unchanged into the next generation. List their IDs in "elites".

2. MUTATION (for each MUTATE-verdict idea): Apply the suggested_mutation \
from its stress test. The mutated idea must:
   - Fix the specific weakness identified
   - Preserve the core strength that earned a passing score
   - Get a NEW id (e.g., "evo-{generation}-mut-001")

3. CROSSOVER: Take the 2 highest-scoring survivors and COMBINE them:
   - Extract the MECHANISM from idea A (how it works)
   - Extract the AUDIENCE from idea B (who it serves)
   - Create a hybrid that uses A's mechanism to serve B's audience
   - Or: combine A's distribution channel with B's core value proposition
   - Generate 2-3 crossover offspring with NEW ids (e.g., "evo-{generation}-cross-001")

4. NOVELTY EXPLORER: Generate 2-3 ideas that are MAXIMALLY DIFFERENT from \
ALL survivors. These ideas must:
   - Use a completely different solution mechanism
   - Target a different audience or domain
   - NOT be a variation of any surviving idea
   - Explore angles that were completely absent from previous generation
   - Get NEW ids (e.g., "evo-{generation}-novel-001")

IDEA GENE RECOMBINATION: If idea genes from previous runs are available \
above, incorporate 1-2 high-scoring genes into your crossover or novelty \
ideas — transplant a proven mechanism/pattern into a new context.

Respond with ONLY valid JSON:
{{
  "generation": {generation},
  "elites": ["idea-001", "idea-003"],
  "evolved_ideas": [
    {{
      "id": "evo-{generation}-mut-001",
      "concept": "One sentence description",
      "source_technique": "mutation|crossover|novelty_explorer",
      "parent_ideas": ["idea-002"],
      "domain_tags": ["domain1", "domain2"],
      "novelty_signal": "What makes this different from parents",
      "evolution_rationale": "What weakness was fixed or what was combined"
    }}
  ]
}}

Generate at least {evolve_count} evolved ideas (mutations + crossovers + novelty). Be bold.
"""

# ---------------------------------------------------------------------------
# Context builders for evolutionary features
# ---------------------------------------------------------------------------


def build_gene_context(genes: list[dict]) -> str:
    """Build context from extracted idea genes for recombination in DIVERGE/EVOLVE."""
    if not genes:
        return ""
    lines = [
        "IDEA GENES (reusable patterns extracted from high-scoring ideas in "
        "previous runs — recombine these into new contexts):"
    ]
    for g in genes[:15]:  # Cap at 15 to avoid token bloat
        title = g.get("title", "?")
        pattern = g.get("pattern", "")[:120]
        score = g.get("score", 0)
        verdict = g.get("verdict", "?")
        domains = ", ".join(g.get("domains", [])[:3])
        lines.append(f"- [{score:.1f}/{verdict}] {title} ({domains}): {pattern}")
    lines.append(
        "\nUse these genes as RECOMBINATION material — transplant a proven "
        "mechanism or pattern into a completely different domain or audience. "
        "Do NOT clone the original idea."
    )
    return "\n".join(lines)


def build_mutation_archive_context(mutations: list[dict]) -> str:
    """Build context from cross-run mutation archive for EVOLVE phase."""
    if not mutations:
        return ""
    lines = [
        "MUTATION ARCHIVE (past mutations from previous runs — learn from these):"
    ]
    for m in mutations[-10:]:  # Most recent 10
        title = m.get("idea_title", "?")
        mutation = (m.get("suggested_mutation", "") or "")[:120]
        lines.append(f"- {title}: {mutation}")
    lines.append(
        "\nUse these past mutations as inspiration. If a similar weakness "
        "appears in current survivors, apply a SIMILAR fix. Avoid repeating "
        "mutation strategies that appear frequently — try novel mutations."
    )
    return "\n".join(lines)


def build_adaptive_stress_context(attack_patterns: list[dict], kill_log: list[dict]) -> str:
    """Build context that weights stress test angles by historical kill rates."""
    if not attack_patterns and not kill_log:
        return ""
    # Count kills by attack angle category
    angle_kills: dict[str, int] = {}
    for k in kill_log:
        reason = (k.get("reason", "") or "").lower()
        if "prior art" in reason or "already exists" in reason:
            angle_kills["Prior art"] = angle_kills.get("Prior art", 0) + 1
        elif "adopt" in reason or "won't use" in reason:
            angle_kills["Adoption failure"] = angle_kills.get("Adoption failure", 0) + 1
        elif "technical" in reason or "infeasible" in reason:
            angle_kills["Technical blocker"] = angle_kills.get("Technical blocker", 0) + 1
        elif "defensib" in reason or "clone" in reason or "moat" in reason:
            angle_kills["Defensibility"] = angle_kills.get("Defensibility", 0) + 1
        elif "timing" in reason or "too late" in reason:
            angle_kills["Timing"] = angle_kills.get("Timing", 0) + 1
        elif "cost" in reason or "economic" in reason:
            angle_kills["Economics"] = angle_kills.get("Economics", 0) + 1
    if not angle_kills:
        return ""
    # Sort by frequency, most lethal first
    sorted_angles = sorted(angle_kills.items(), key=lambda x: -x[1])
    lines = [
        "ADAPTIVE STRESS WEIGHTS — These attack angles have historically "
        "been the most lethal. Apply EXTRA SCRUTINY to these angles and be "
        "MORE AGGRESSIVE in your attacks along these dimensions:"
    ]
    for angle, count in sorted_angles[:5]:
        lines.append(f"- {angle}: {count} kills (HIGH PRIORITY — probe deeply)")
    lines.append(
        "\nFor the high-priority angles above, require STRONGER evidence "
        "before marking as 'survived'. A vague defense is not enough."
    )
    return "\n".join(lines)


def build_novelty_context(previous_winners: list[dict], archive_size: int) -> str:
    """Build context for novelty scoring in CONVERGE — penalise similarity to archive."""
    if not previous_winners:
        return ""
    lines = [
        f"NOVELTY SCORING — {archive_size} ideas already exist in the archive. "
        "Score novelty_score HARSHLY for any idea that resembles these past winners:"
    ]
    for w in previous_winners[:10]:
        lines.append(f"- {w['title']}")
    lines.append(
        "\nNovelty 0.9+: Nothing like this in the archive. "
        "Novelty 0.5-0.8: Similar mechanism or domain but different angle. "
        "Novelty <0.5: Too close to existing ideas — penalise heavily."
    )
    return "\n".join(lines)


def build_technique_weight_context(weights: dict[str, float]) -> str:
    """Build context to guide technique allocation in DIVERGE based on learned weights."""
    if not weights:
        return ""
    adjusted = {k: v for k, v in weights.items() if v != 1.0}
    if not adjusted:
        return ""
    lines = [
        "TECHNIQUE ALLOCATION (learned from previous runs -- adjust technique "
        "mix based on what historically produces survivors):"
    ]
    sorted_w = sorted(weights.items(), key=lambda x: -x[1])
    for tech, weight in sorted_w:
        if weight > 1.2:
            lines.append(f"- {tech}: USE MORE (weight {weight:.1f}x) -- historically produces more BUILD verdicts")
        elif weight < 0.8:
            lines.append(f"- {tech}: USE LESS (weight {weight:.1f}x) -- historically produces more KILL verdicts")
    if len(lines) == 1:
        return ""  # No meaningful adjustments
    lines.append(
        "\nAllocate more idea slots to high-weight techniques and fewer to low-weight ones."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Meta-Learning: Distilled playbook + score calibration
# ---------------------------------------------------------------------------

META_LEARN_SYSTEM = (
    "You are a meta-learning engine. Analyze ideation pipeline data and "
    "produce compact, actionable insights. Be terse. No fluff. "
    "You MUST respond with valid JSON only."
)

META_LEARN_USER = """\
Analyze these results from {run_count} ideation runs.

SCORE DISTRIBUTION (score->verdict): {score_verdicts}
KILL REASONS (truncated): {kill_reasons}
ATTACK PATTERNS: {attack_patterns}
DOMAIN HEAT MAP: {domain_heat}
TECHNIQUE STATS: {technique_stats}
REFINEMENT HISTORY: {refinement_stats}

Distill into a compact playbook (max 200 words) with:
1. SCORING BIAS: Are scores inflated? Which dimensions are consistently over/under-rated?
2. FATAL PATTERNS: Top 3 reasons ideas die (one sentence each)
3. WINNING TRAITS: What surviving ideas have in common
4. DOMAIN GAPS: Underexplored domains worth targeting
5. ANTI-PATTERNS: 3 idea shapes to avoid generating
6. TECHNIQUE PERFORMANCE: Which generation techniques produce the most BUILD verdicts? \
Which produce mostly KILLs? Recommend technique weight adjustments.
7. REFINEMENT EFFECTIVENESS: Are refinement rounds productive? How many rounds \
typically produce a BUILD? If refinement rarely helps, note that.

Respond with ONLY valid JSON:
{{
  "playbook": "The compact playbook text (200 words max)",
  "score_calibration": {{
    "bias_direction": "inflated|deflated|balanced",
    "adjustment": "Brief instruction for scoring LLM (1 sentence)",
    "weak_dimensions": ["dimension names that need harsher scoring"],
    "dimension_multipliers": {{
      "impact": 1.0,
      "confidence": 1.0,
      "effort": 1.0,
      "cost": 1.0,
      "ethical_risk": 1.0,
      "sustainability": 1.0,
      "defensibility": 1.0,
      "market_timing": 1.0
    }}
  }},
  "technique_weights": {{
    "domain_scan": 1.0,
    "cross_domain_collision": 1.0,
    "contrarian_inversion": 1.0,
    "constraint_injection": 1.0,
    "mechanism_stealing": 1.0,
    "gap_fill": 1.0
  }},
  "domain_recommendations": ["domain1", "domain2"],
  "anti_patterns": ["pattern1", "pattern2", "pattern3"]
}}

dimension_multipliers: Set each to a value between 0.5 and 1.5.
- <1.0 means the LLM historically OVER-scores that dimension -> deflate it.
- >1.0 means the LLM historically UNDER-scores that dimension -> inflate it.
- 1.0 means no correction needed.

technique_weights: Set each to a value between 0.5 and 2.0.
- >1.0 means this technique produces more survivors -> use it more.
- <1.0 means this technique produces more kills -> use it less.
- 1.0 means no adjustment.
"""


def build_playbook_context(playbook: str) -> str:
    """Inject distilled playbook into prompts (very compact)."""
    if not playbook:
        return ""
    return (
        "PLAYBOOK (learned from previous runs — follow these guidelines):\n"
        f"{playbook}\n"
    )


def build_calibration_context(calibration: dict) -> str:
    """Inject score calibration into CONVERGE prompt."""
    if not calibration:
        return ""
    adj = calibration.get("adjustment", "")
    weak = calibration.get("weak_dimensions", [])
    if not adj and not weak:
        return ""
    lines = ["SCORE CALIBRATION (apply these corrections):"]
    if adj:
        lines.append(f"- {adj}")
    if weak:
        lines.append(f"- Score these dimensions MORE HARSHLY: {', '.join(weak)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline 2: SPECIFY — Execution Accelerator
# ---------------------------------------------------------------------------

SPECIFY_SYSTEM = (
    "You are a senior software architect and product manager. Your job is to "
    "convert validated idea cards into actionable project specifications that "
    "a developer can start coding immediately. Be specific, concrete, and "
    "opinionated about technology choices. No hand-waving. "
    "You MUST respond with valid JSON only — no markdown, no commentary."
)

SPECIFY_USER = """\
Generate a complete project specification for this validated idea:

IDEA:
{idea_json}

STRESS TEST RESULTS:
{stress_json}

Create a specification with:

1. OVERVIEW: One-paragraph executive summary
2. USER STORIES: 5-8 user stories in "As a [persona], I want [action] so that [benefit]" format. \
Include acceptance criteria for each.
3. ARCHITECTURE: Recommended tech stack, system components, data flow. \
Be opinionated — pick specific technologies.
4. API CONTRACTS: Define 3-5 core API endpoints (method, path, request/response shapes). \
Use RESTful conventions.
5. DATA MODEL: Core entities and their relationships.
6. TASK BREAKDOWN: Break into 10-15 development tasks, ordered by dependency. \
Each task should be completable in 1-3 days. Include acceptance criteria.
7. RISKS & MITIGATIONS: Top 3 technical risks from the stress test and how to handle them.
8. SUCCESS METRICS: 3-5 measurable outcomes with numerical thresholds that define \
success vs failure. Each metric needs a target value, measurement method, and \
timeframe. Include at least one "abort threshold" — a number that means stop building.
9. VALIDATION PLAN: Ordered list of 3-5 cheapest experiments to run BEFORE building \
the full product. Each experiment should test one key assumption and take at most \
1-2 weeks. Include expected outcome, cost, and what you learn if it fails.
10. MVP SCOPE: What to build first (2-week sprint). What to defer.
11. KILL CRITERIA: Conditions that should abort the project (from stress test).

Respond with ONLY valid JSON:
{{
  "title": "Project title",
  "overview": "Executive summary paragraph",
  "user_stories": [
    {{
      "id": "US-001",
      "story": "As a [persona], I want [action] so that [benefit]",
      "acceptance_criteria": ["criterion 1", "criterion 2"],
      "priority": "must-have|should-have|nice-to-have"
    }}
  ],
  "architecture": {{
    "tech_stack": {{"frontend": "...", "backend": "...", "database": "...", "hosting": "...", "other": ["..."]}},
    "components": ["component 1 description", "component 2 description"],
    "data_flow": "Description of how data flows through the system"
  }},
  "api_contracts": [
    {{
      "method": "POST",
      "path": "/api/v1/resource",
      "description": "What this endpoint does",
      "request_body": {{"field": "type and description"}},
      "response_body": {{"field": "type and description"}},
      "auth": "required|optional|none"
    }}
  ],
  "data_model": [
    {{
      "entity": "EntityName",
      "fields": {{"field_name": "type — description"}},
      "relationships": ["relates to EntityB via foreign key"]
    }}
  ],
  "tasks": [
    {{
      "id": "T-001",
      "title": "Task title",
      "description": "What to do",
      "depends_on": [],
      "effort_days": 2,
      "acceptance_criteria": ["criterion 1"]
    }}
  ],
  "risks": [
    {{
      "risk": "What could go wrong",
      "likelihood": "high|medium|low",
      "mitigation": "How to handle it"
    }}
  ],
  "success_metrics": [
    {{
      "metric": "What to measure",
      "target": "Numerical threshold for success",
      "measurement_method": "How to measure it",
      "timeframe": "When to measure",
      "abort_threshold": "Number that means stop (optional)"
    }}
  ],
  "validation_plan": [
    {{
      "experiment": "What to test",
      "assumption_tested": "Which key assumption this validates",
      "method": "How to run the experiment",
      "duration": "1-2 weeks",
      "cost": "$0-500",
      "success_signal": "What result means proceed",
      "failure_signal": "What result means pivot or stop"
    }}
  ],
  "mvp_scope": {{
    "include": ["feature 1", "feature 2"],
    "defer": ["feature 3", "feature 4"],
    "sprint_goal": "What the 2-week MVP should demonstrate"
  }},
  "kill_criteria": ["condition 1", "condition 2"]
}}
"""

