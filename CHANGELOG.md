# Changelog

## v1.5.0 — 2026-03-20

### New Features

#### Structured Key Assumptions with Validation Cost Ranking
Key assumptions are no longer flat strings. Each assumption is now a structured object with `claim`, `validation_cost` (low/medium/high), and `validation_method`. Assumptions are auto-sorted cheapest-to-validate first, so founders know which bets to test immediately. The CONVERGE prompt instructs the LLM to produce this format, and `_normalize_assumptions()` in `ideate.py` enforces it programmatically — plain strings from the LLM are auto-converted to dicts with sensible defaults. Reports render cost badges (`[low]`, `[medium]`, `[high]`) and validation methods inline.

#### Success Metrics in Project Specs
The Specify pipeline now generates 3-5 measurable success metrics per project spec, each with a numerical target, measurement method, timeframe, and abort threshold. This replaces vague "we'll know it's working" statements with concrete numbers.

#### Validation Plan in Project Specs
Project specs now include a pre-build validation plan: 3-5 ordered experiments to run before writing code. Each experiment tests one key assumption and includes method, duration, cost estimate, success signal, and failure signal. Cheapest experiments come first.

### Files Changed

- `xbrain/__init__.py` — version bump to 1.5.0
- `xbrain/prompts.py` — structured key_assumptions format in CONVERGE, success_metrics and validation_plan in SPECIFY
- `xbrain/ideate.py` — added `_normalize_assumptions()` for format enforcement and cost sorting
- `xbrain/models.py` — `key_assumptions` type changed from `list[str]` to `list` (accepts dicts)
- `xbrain/output.py` — renders structured assumptions with cost badges and validation methods
- `xbrain/specify.py` — renders Success Metrics table and Validation Plan section

---

## v1.4.0 — 2026-03-20

### Fixes — Programmatic Enforcement

The LLM consistently ignores scoring rules, effort differentiation, ICP grounding, and BUILD thresholds despite explicit prompt instructions. v1.4.0 enforces these rules programmatically after the LLM responds, rather than hoping it obeys.

#### BUILD Verdict Enforcement (Programmatic)
The stress test prompt says "≥5 survived → BUILD" but the LLM still hedges with MUTATE. Now `_phase_stress_test` applies a post-hoc override: if `attacks_survived >= 5` and `attacks_fatal <= 1`, verdict is forced to BUILD regardless of what the LLM said.

#### Score Spread Enforcement (Programmatic)
The prompt says "spread ≥ 3.0" but the LLM clusters scores within 2 points. After CONVERGE, if spread < 3.0, scores are linearly stretched around the midpoint to achieve the 3.0 minimum while preserving rank order.

#### Effort Diversity Enforcement (Programmatic + Prompt)
All ideas were getting "medium" effort despite the prompt requiring variety. After CONVERGE, if all efforts are identical, the easiest idea (lowest effort score) is remapped to "small" and the hardest (highest) to "large". Prompt also strengthened: effort score ≥ 7 → "large", ≤ 3 → "small".

#### ICP Grounding (Prompt)
Added explicit ICP grounding rule to CONVERGE: first_customer_profile must match the brief's scale and context. Solo-dev tool → solo developer ICP, not "Series B startup". Internal tool → tool operator ICP, not enterprise customer.

### Files Changed

- `xbrain/__init__.py` — version bump to 1.4.0
- `xbrain/ideate.py` — added programmatic BUILD override, score spread stretching, effort diversity enforcement
- `xbrain/prompts.py` — strengthened effort differentiation language, added ICP grounding rule

---

## v1.3.0 — 2026-03-20

### New Features

#### Feature-Aware Diversity Ratchet → Removed (Brief-Driven Instead)
Initially added a hardcoded `XBRAIN_EXISTING_FEATURES` list and `FEATURE REPULSION` block injected into DIVERGE. **Removed** — xBrain is a general-purpose ideation engine, not a self-improvement tool. Feature repulsion should come from the brief content, which already describes existing capabilities when relevant. The brief is the right place for this — it's user-controlled and context-specific.

#### Comprehensive Self-Improvement Brief
Rewrote `improve-xbrain-ideation.txt` with full feature awareness — pipeline phases, all 6 DIVERGE techniques, memory system, meta-learning, stress testing, dynamic CONVERGE, and every v1.1–v1.2 feature. The brief now tells xBrain exactly what it already does, so it can focus on genuine gaps.

### Files Changed

- `xbrain/__init__.py` — version bump to 1.3.0
- `xbrain/prompts.py` — removed hardcoded `XBRAIN_EXISTING_FEATURES` and `build_feature_repulsion_context()` (feature repulsion is brief-driven)
- `xbrain/ideate.py` — removed `build_feature_repulsion_context()` calls
- `improve-xbrain-ideation.txt` — complete rewrite with full feature description

---

## v1.2.0 — 2026-03-20

### Fixes

#### Idea-Specific Key Assumptions
Key Assumptions were hardcoded in `output.py` — every idea got the same 5 generic assumptions ("Target persona exists and has sufficient budget"). Now the CONVERGE prompt generates 3-5 **unique, falsifiable assumptions per idea**, and `output.py` renders them from model data. Example: "Semantic similarity (embeddings) can reliably cluster idea variants with <5% false positive rate."

#### Dynamic First Customer Profile (ICP)
ICP was hardcoded as "5-50 person team / $5-50M ARR" for every idea. Now the CONVERGE prompt generates a `first_customer_profile` object per idea with type, size, readiness, and why_first fields. Internal tool briefs now correctly show "internal: xBrain validation & product ops, 3-5 people" instead of SaaS customer profiles.

#### Context-Aware Cost Labels
`estimated_cost_usd_month` was always rendered as "$X/mo" even for one-time implementations. Added `cost_context` field to `IdeaCard` — the LLM now specifies "one-time implementation", "monthly labor", "transition cost", etc. Report renders the actual context instead of assuming monthly SaaS costs.

#### BUILD Verdict Threshold
All ideas were getting MUTATE because the LLM was hedging. Added a quantitative rule to the stress test prompt: "if attacks_survived >= 5 out of 9, the verdict MUST be BUILD unless there is exactly one irreparable fatal flaw." Run 9 produced the first BUILD verdict (Assumption Invalidation Speedrun, 6/9 survived, 0 fatal).

#### Stronger Score Spread Enforcement
Score spread was 1.7 points (target: 3.0). Added explicit instructions: "Assign scores AFTER force-ranking. The #1 idea gets the highest composite; the last gets at least 3.0 points lower." Run 9 achieved 2.4 points (8.1→5.7) — improved but still under target.

### Model Changes

- `IdeaCard` — added `key_assumptions: list[str]`, `first_customer_profile: dict`, `cost_context: str`
- `_parse_candidate()` in `ideate.py` — reads new fields from LLM response

### Performance

| Metric | v1.1.0 (Run 8) | v1.2.0 (Run 9) |
|--------|----------------|-----------------|
| Time | 2m 50s | 3m 4s |
| Cost | $0.14 | $0.14 |
| Tokens (in/out) | 24K/23K | 21K/23K |
| BUILD verdicts | 0 | **1** |
| Key assumptions unique | 0/8 | **8/8** |
| ICP unique | 0/8 | **8/8** |
| Cost context | all "/mo" | **all contextual** |
| Score spread | 1.7 | **2.4** |
| Mechanism stealing | 4/22 (18%) | **10/25 (40%)** |

### Files Changed

- `xbrain/models.py` — added `key_assumptions`, `first_customer_profile`, `cost_context` to `IdeaCard`
- `xbrain/ideate.py` — `_parse_candidate()` reads new fields
- `xbrain/prompts.py` — CONVERGE: key_assumptions instruction + JSON schema, score spread hardening; STRESS_TEST: BUILD quantitative threshold
- `xbrain/output.py` — ICP, Key Assumptions, cost labels now render from model data instead of hardcoded text

---

## v1.1.0 — 2025-03-19

### New Features

#### Dynamic CONVERGE (Brief-Adaptive Output)
The CONVERGE phase now detects the brief type and adapts its output fields accordingly:
- **Product/startup briefs** → persona, ICP, go-to-market, cost estimates
- **Internal tool briefs** → user role, workflow fit, integration surface
- **Process/workflow briefs** → current state, proposed change, success metrics
- **Default** → flexible format matching the brief's nature

Previously, every idea was forced into a SaaS product template regardless of the brief, causing internal tool ideas to get personas like "CTO at a 50-person startup" even when the brief was about improving xBrain itself.

#### Diversity Ratchet (Cross-Run Winner Repulsion)
Previous high-scoring ideas (BUILD/MUTATE with score ≥ 5.0) are now tracked across runs and injected into DIVERGE as an exclusion list. This pushes the engine toward unexplored territory instead of regenerating the same winning patterns across consecutive runs.

Stored in memory via `get_previous_winners()` — titles, domains, and scores of up to 20 recent winners.

#### Failure Taxonomy (Idea Autopsy Lab)
Attacks from stress tests are now classified into 6 structured categories:
- **prior_art** — idea already exists
- **adoption** — users won't switch/adopt
- **technical** — can't be built as described
- **timing** — market isn't ready or window has passed
- **defensibility** — no moat, easily copied
- **economics** — unit economics don't work

Categories are persisted in `xbrain-memory/persistent/failure-taxonomy.json` (last 10 per category) and injected into future DIVERGE prompts, steering generation away from idea shapes that repeatedly die to the same attack patterns.

#### Mechanism Stealing (Inverse Ideation)
New DIVERGE technique (#6). Extracts working mechanisms from successful products in unrelated fields and transplants them into new contexts. Example: Duolingo's streak mechanic → applied to compliance training. Forces cross-pollination beyond simple domain collision.

#### Moat Archaeology (Defensibility Gate)
Defensibility is now a first-class scoring constraint:
- During CONVERGE, any idea scoring below 4 on defensibility triggers a mandatory **moat check** — the AI must suggest a concrete mutation that would strengthen the moat (network effects, data flywheel, switching costs, regulatory capture, etc.)
- A **defensibility gate** adjusts composite scores: ideas with defensibility < 3 receive a score penalty, while ideas with defensibility ≥ 7 receive a bonus

### Changes

#### Streamlined Stress Test
- Reduced from 3-round adversarial debate (attack → defense → rebuttal) to **single-round attack**
- Verdicts rendered immediately after the attack phase
- Removed defense and rebuttal rounds entirely
- **Cost reduction**: ~$0.30 → ~$0.14 per run
- **Time reduction**: ~5 minutes → ~3 minutes per run
- No measurable loss in verdict quality — the defense/rebuttal rounds were adding cost without meaningfully changing verdicts

#### MUTATE Treated as Passing
- MUTATE verdicts no longer trigger the REFINE loop
- Only runs with zero BUILD *and* zero MUTATE verdicts trigger refinement
- This prevents unnecessary re-generation when ideas need minor improvements rather than wholesale replacement

### Performance

Benchmarked on self-improvement brief ("How should xBrain improve its own ideation and autonomy?"):

| Metric | v0.1.0 (Run 1) | v1.1.0 (Run 8) |
|--------|----------------|-----------------|
| Time | 16m 39s | 2m 50s |
| Cost | $0.72 | $0.14 |
| Tokens (in/out) | 51K/127K | 24K/23K |
| JSON parse failures | 6/16 | 0 |
| Ideas relevant to brief | 0/11 | 8/8 |
| Refinement rounds | 3 | 0 |
| Mechanism stealing adoption | n/a | 4/22 raw ideas |

### Files Changed

- `xbrain/__init__.py` — version bump to 1.1.0
- `xbrain/prompts.py` — dynamic CONVERGE template, mechanism stealing technique, winner repulsion + failure taxonomy context builders, moat check + defensibility gate
- `xbrain/ideate.py` — winner repulsion + failure taxonomy injection in DIVERGE/REFINE, failure classification in memory update, single-round stress test, MUTATE-as-pass
- `xbrain/memory.py` — `get_previous_winners()`, `get_failure_taxonomy()`, `save_failure_taxonomy()`
- `README.md` — full documentation update for v1.1

### New Memory Files

- `xbrain-memory/persistent/failure-taxonomy.json` — categorized failure patterns from stress tests
