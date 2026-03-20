# Changelog

## v1.11.0 — 2026-03-20

### Removed

#### `--domains` Parameter
The `--domains` CLI parameter has been removed from both `ideate` and `estimate` subcommands. The AI now determines which domains to explore based entirely on the brief context — no predefined domain list needed.

#### IMMERSE Phase
The IMMERSE pipeline phase (domain-specific research) has been removed. It only ran when `--domains` was provided. Domain context is now inferred during DIVERGE via broad exploration. This reduces the pipeline from ~15 API calls to ~12.

#### `DEFAULT_DOMAINS` Config
The hardcoded `DEFAULT_DOMAINS` list in `config.py` has been removed along with the `"immerse"` entry in `PHASE_ROUTING` and `PHASE_MAX_TOKENS`.

### Changed

#### `build_domain_context()` Simplified
No longer accepts parameters — always returns broad "scan all domains" exploration text, letting the AI determine relevant domains from the brief.

#### README Cleaned Up
- Removed 10 "What's New" sections (content lives in CHANGELOG.md)
- Removed feature-spam intro paragraph
- Moved Setup to top, before architecture details
- Wrapped pipeline diagram and phase descriptions in collapsible `<details>` sections
- Removed all `--domains` documentation and examples
- Condensed phase descriptions from ~200 lines to ~40 lines

### Files Changed
- `xbrain/__init__.py` — version bump to 1.11.0
- `xbrain/cli.py` — removed `--domains` from ideate/estimate parsers, removed `has_domains` from estimate calls
- `xbrain/config.py` — removed `DEFAULT_DOMAINS`, removed `"immerse"` from `PHASE_ROUTING` and `PHASE_MAX_TOKENS`
- `xbrain/ideate.py` — removed `domains` parameter from `run()`, deleted `_phase_immerse()`, removed `domains`/`domain_briefs` from diverge/gapfill/refine, removed `has_domains` from `estimate_cost()`
- `xbrain/prompts.py` — deleted `IMMERSE_SYSTEM`/`IMMERSE_USER` constants, simplified `build_domain_context()`
- `xbrain/models.py` — removed `domains` field from `IdeateRunResult`
- `xbrain/output.py` — removed "Focus Domains" line from report header
- `README.md` — major cleanup (see Changed above)

---

## v1.10.0 — 2026-03-20

### New Features

#### Shared Logging Module (`xbrain/log.py`)
New centralized logging module replaces three separate `_log()` definitions across ideate.py, search.py, and specify.py. Provides encoding-safe output on Windows (handles `UnicodeEncodeError`), consistent `[TAG      ]` formatting, and flush-after-write across the entire pipeline.

#### LLM Call Timing
Every LLM call now shows a `⏳ description...` line before the call and `✓ done in Xs` after it returns, eliminating silent gaps where the pipeline appeared frozen. All 12 LLM calls in the ideation pipeline and the SPECIFY call are timed.

#### Batch & Parallel Progress Indicators
- **CONVERGE 2C enrichment**: Shows `Enriching batch 1/2 (Title1, Title2, ...)` with per-batch timing
- **Stress test attacks**: Shows `[0/8] Attacking: Idea Title...` → `[1/8] Idea Title — attack received` with a completion summary (`All 8 attacks completed in 84.0s`)

### Changed

#### Unified Output Streams
All 10 `print(..., file=sys.stderr)` calls in `llm.py` (retry, throttle, JSON warnings, errors) now route through the shared `_log()` function on stdout, keeping all pipeline output on a single stream with consistent tagging (`[RETRY]`, `[THROTTLE]`, `[WARN]`, `[ERROR]`).

#### Encoding-Safe Summary Output
The final completion summary (previously 21 raw `print()` calls) now uses `log_summary_block()` with encoding error handling, preventing crashes on terminals with limited Unicode support.

### Fixes

#### specify.py Encoding Crash
The `_log()` function in specify.py had no `UnicodeEncodeError` handler — it would crash on Windows when LLM output contained Unicode characters. Now uses the shared encoding-safe implementation.

### Files Changed
- `xbrain/log.py` — **new** shared logging module (log, log_phase, log_llm_call, log_progress, log_summary_block)
- `xbrain/__init__.py` — version bump to 1.10.0
- `xbrain/ideate.py` — removed local `_log`/`_log_phase_header`, imports from `xbrain.log`, all 12 LLM calls timed, batch/parallel progress, summary via `log_summary_block`
- `xbrain/llm.py` — imports `_log` from `xbrain.log`, replaced 10 stderr prints with unified logging
- `xbrain/search.py` — removed local `_log`, imports from `xbrain.log`
- `xbrain/specify.py` — removed weak `_log` (no encoding handler), imports from `xbrain.log`, SPECIFY LLM call timed

---

## v1.9.0 — 2026-03-20

### New Features

#### Per-Phase Cost Breakdown
Every run now persists a full per-phase cost breakdown in `idea-log.json`, recording the model used, input/output token counts, and dollar cost for each LLM call. The `idea-report.md` renders this as a **Cost Breakdown** table in the summary section, giving immediate visibility into where tokens are spent.

#### Configurable Per-Phase Token Budgets
New `PHASE_MAX_TOKENS` dict in `config.py` centralizes the max output-token budget for every pipeline phase (meta, constraints, immerse, diverge, dedup, gapfill, converge-cluster, converge-compare, converge-enrich, stress-attack, refine-diverge, refine-converge). All `generate_json` calls now read from this config via `_max_tokens_for_phase()` instead of using hardcoded values. Unknown phases fall back to the global `max_tokens` default.

### Fixes

#### Score Value Clamping
The LLM occasionally returns dollar amounts (e.g. `cost: 12000`) instead of 0–10 scores in `score_breakdown`, causing `ValidationError` crashes. `_parse_candidate()` now clamps all numeric score values to [0, 10] before passing to `ScoreBreakdown`.

### Files Changed
- `xbrain/__init__.py` — version bump to 1.9.0
- `xbrain/config.py` — added `PHASE_MAX_TOKENS` dict
- `xbrain/ideate.py` — `_max_tokens_for_phase()` helper, all LLM calls use it, score clamping in `_parse_candidate()`, cost_info persisted in idea-log.json
- `xbrain/output.py` — Cost Breakdown table in report summary

---

## v1.8.0 — 2026-03-20

### New Features

#### Decomposed CONVERGE Pipeline
The single CONVERGE phase is now split into three sub-phases for better scoring accuracy:
- **2A — Cluster + Initial Score**: Clusters raw ideas and produces initial multi-dimensional scores. Prompt is simplified — no more persona, assumptions, or moat analysis at this stage.
- **2B — Comparative Ranking**: Force-ranks candidates head-to-head on impact, confidence, and defensibility. Adjusts scores to enforce a ≥3.0 point spread. Replaces the old mechanical score-stretching with LLM-driven comparative judgment.
- **2C — Enrich + Assumption Inversion**: Adds personas, key assumptions, moat analysis, customer profiles, and sustainability models. Each assumption gets an **inverse claim** and **fragility rating** — if the inverse is easy to defend (score ≥4/5), the assumption is flagged 🔴 fragile. Enrichment is batched (4 candidates per call) to avoid token truncation.

#### Assumption Inversion & Fragility Badges
Each key assumption now includes `inverse_claim`, `inverse_defense_quality` (1-5), and `fragility_flag` (fragile/solid). Reports render 🔴/🟢 badges and show the inverse claim with defense quality rating. Fragile assumptions surface critical vulnerabilities before stress testing.

### Files Changed
- `xbrain/__init__.py` — version bump to 1.8.0
- `xbrain/prompts.py` — simplified CONVERGE_USER, new CONVERGE_COMPARE_SYSTEM/USER and CONVERGE_ENRICH_SYSTEM/USER prompts
- `xbrain/ideate.py` — `_phase_converge()` decomposed into 3 sub-phases with batched enrichment, `_normalize_assumptions()` preserves inversion fields, removed score-stretch enforcement
- `xbrain/output.py` — fragility badges (🔴/🟢) and inverse claims in assumption rendering

---

## v1.7.0 — 2026-03-20

### New Features

#### Web Search Grounding
xBrain now grounds its analysis in live web data. Before the IMMERSE phase LLM call, the pipeline queries DuckDuckGo and HackerNews for each domain (e.g. `"{domain} startups trends 2025 2026"`, `"{domain} biggest problems pain points"`). Search results are injected as `CURRENT MARKET DATA` context, so domain briefs reflect current reality instead of Claude's training cutoff. In the STRESS TEST phase, each idea is searched for prior art (`"{title} existing product competitor"`) before the attack, grounding the prior art attack angle in real competitors.

#### Pluggable Search Architecture
New `xbrain/search.py` module with a `SearchProvider` base class and `SearchAggregator` that fans queries to all enabled providers and deduplicates results by URL. Adding a new provider = subclass `SearchProvider` + implement `search()` + register in `from_config()`. Current providers:
- **DuckDuckGoProvider** — free, no API key, requires `duckduckgo-search` or `ddgs` package
- **HackerNewsProvider** — free, no API key, uses stdlib `urllib` against Algolia API

Search is best-effort: if no providers are available (packages not installed, network down), the pipeline runs exactly as before with no errors.

### Files Changed
- `xbrain/__init__.py` — version bump to 1.7.0
- `xbrain/search.py` — NEW: pluggable search module with DuckDuckGo + HackerNews providers
- `xbrain/ideate.py` — search aggregator initialization in `__init__`, web search in `_phase_immerse()` and `_phase_stress_test()`
- `xbrain/prompts.py` — `{search_context}` placeholder in `IMMERSE_USER`, new `build_search_context()` function
- `xbrain/output.py` — compact adversarial debate formatting (removed blank lines between attacker/defender quotes)
- `requirements.txt` — added `duckduckgo-search>=7.0.0`

---

## v1.6.0 — 2026-03-20

### New Features

#### Calibration Enforcement Layer
META-LEARN now outputs per-dimension calibration multipliers (0.5–1.5) alongside the existing text-based calibration. After CONVERGE scores ideas, xBrain applies these multipliers mathematically to each dimension score and recomputes the composite — removing reliance on the LLM voluntarily following calibration instructions. Candidates are tagged `calibrated` or `uncalibrated` in the report. Calibration is also applied during refinement rounds.

#### Stress Test Fidelity Monitor
When the stress test API call crashes (timeout, JSON error, rate limit), the fallback INCUBATE verdict is now tagged with `error_source: api_crash`. The pipeline log shows `⚠ CRASH-INCUBATE` instead of a normal verdict, and the report shows `(⚠ api_crash)` next to the verdict — so crash-based INCUBATEs are never mistaken for genuine assessments.

#### Report Calibration Status
The report summary previously hardcoded "Scoring Status: UNCALIBRATED" regardless of whether calibration was actually applied. Now reads the `scoring_calibration_status` from candidates and shows CALIBRATED or UNCALIBRATED accurately.

#### Refinement Failure Blocklist
Refinement rounds now extract canonical failure types (prior_art, adoption, technical, timing, defensibility, economics) from KILL/MUTATE stress results and inject them as hard prohibitions before the soft refinement context. The blocklist uses imperative language ("DO NOT generate ideas that...") and requires each new idea to explain why it avoids the blocked failure types — stronger than the existing soft attack-pattern context.

### Files Changed

- `xbrain/__init__.py` — version bump to 1.6.0
- `xbrain/prompts.py` — META-LEARN outputs `dimension_multipliers`; added `CANONICAL_FAILURE_TYPES` map and `build_failure_blocklist_context()` function
- `xbrain/models.py` — `error_source` field on `AttackResponse` and `StressTestResult`
- `xbrain/ideate.py` — calibration enforcement in `_phase_converge()` and `_phase_refine()`, crash-INCUBATE tagging in `_phase_stress_test()`, failure blocklist extraction and injection in `_phase_refine()`
- `xbrain/output.py` — report shows `error_source` flag on verdicts in both summary table and detail cards; scoring status reads from candidates instead of hardcoded

---

## v1.5.1 — 2026-03-20

### Fixes — Pipeline Audit

Full codebase audit identified 6 issues across 5 files. All fixed.

#### Null Safety: `inverse_score` Parsing
If the LLM returns `"inverse_score": null` (key present, value null), `c.get("inverse_score", {})` returns `null` instead of the default `{}`, crashing with `AttributeError`. Changed to `(c.get("inverse_score") or {})` to coerce null to empty dict.

#### Corrupt Memory File Recovery
`MemoryStore._read()` had no error handling on `json.load()`. A corrupted JSON file (partial write, disk error) would crash the entire pipeline. Now catches `JSONDecodeError` and returns the default value instead.

#### Scoring Weights Single Source of Truth
`compute_composite_score()` hardcoded weight values that duplicated `Config.SCORING_WEIGHTS`. If weights were changed in config, scores wouldn't reflect them. Now reads from `Config.SCORING_WEIGHTS` directly — one truth source.

#### Memory File Pruning
Four memory files grew without bound: `idea-archive.json`, `kill-log.json`, `meta-metrics.json`, and `idea-lineage.json`. After hundreds of runs these would become multi-MB. Added retention caps: archive (500), kill log (200), metrics (100), lineage (500). `idea-genes.json` already capped at 100.

#### Async Lock Availability
Added `asyncio.Lock` to `LLMClient` alongside the existing `threading.Lock` for use in async code paths. The threading lock is still used for shared data since `_record_usage` is called from both sync and async contexts.

#### Model Routing Fallback
`Config.best_model` defaulted to empty string when `XBRAIN_BEST_MODEL` wasn't set. The `balanced` strategy would silently fall back to the default model with no indication routing was bypassed. Now falls back to `XBRAIN_MODEL` (the main configured model).

### Files Changed

- `xbrain/__init__.py` — version bump to 1.5.1
- `xbrain/ideate.py` — null-safe `inverse_score` parsing
- `xbrain/memory.py` — corrupt JSON recovery, memory file pruning caps
- `xbrain/models.py` — `compute_composite_score()` uses `Config.SCORING_WEIGHTS`
- `xbrain/llm.py` — added `asyncio.Lock` for async code paths
- `xbrain/config.py` — `best_model` falls back to main model

---

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
