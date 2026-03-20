# Changelog

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
