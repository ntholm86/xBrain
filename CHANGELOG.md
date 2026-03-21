# Changelog

## v1.21.0 — 2026-03-21

### Added

#### Dynamic Attack Angle Selection
The stress test phase now auto-selects the most relevant attack angles from a catalog of 20 (across 5 categories: Universal, Execution, Economics, Environment, Personal) instead of using 9 hardcoded software/SaaS-focused angles. A cheap LLM call picks the N most relevant angles for the brief, with a relevance explanation per angle. The angle catalog is defined in `prompts.py` and the selection phase uses `ANGLE_SELECT_SYSTEM/USER` prompts.

- **Catalog categories:** Universal (6), Execution (4), Economics (4), Environment (4), Personal (2)
- **Dynamic threshold:** `survive_threshold = max(1, round(attack_count * 5 / 9))` scales automatically with attack count
- **Config:** `XBRAIN_ATTACK_COUNT` env var (default 9), `stress-angles` phase in routing
- **Report:** New "Attack Angles" section shows selected angles with categories and relevance
- **Fallback:** If angle selection fails, uses first N angles from catalog

#### Rich Spinners for Pipeline Phases
All major pipeline phases now display a Rich `Status` spinner in the terminal that shows the current phase name, description, and elapsed time. This provides continuous visual feedback during long-running LLM calls (10-60s each) so the user always knows the pipeline is alive and which phase is executing.

- Phases with spinners: DIVERGE (including dedup + gap-fill), CONVERGE, ANGLES, STRESS TEST, REFINE, EVOLVE
- Sub-step updates: spinners show progress like "12 seeds → dedup" or "gap-filling 3 gaps"
- Stress test attack progress now includes elapsed time per attack

#### Fragility-Aware Verdict Guard
BUILD ideas with high fragility (inverse_confidence >= 7.0) are now automatically downgraded to MUTATE. Previously, an idea could survive the stress test attacks narratively while being quantitatively fragile — all key assumptions flagged as `[!]` and a high inverse score — yet still receive BUILD. The new guard catches this mismatch.

#### Enhanced Dedup: Thematic Overlap Detection
The DEDUP phase now includes a third pass (PASS 3 — THEMATIC OVERLAP) that compares surviving ideas pairwise for same-end-user / same-activity / same-context overlap, even when the business model differs. This prevents two ideas targeting the same user doing essentially the same thing from both appearing in the final output.

### Changed

- **Feasibility Matrix: LLM Capability Fit** — The stress test prompt now instructs the LLM to default `llm_capability_fit` to 3 for non-tech ideas (physical products, services, offline businesses). Previously this dimension scored low for non-tech briefs, dragging down averages meaninglessly.
- **EVOLVE crash resilience** — The evolve loop body is wrapped in try-except so a single generation failure doesn't lose the entire pipeline.
- **JSON extraction** — Improved handling of LLM responses wrapped in \`\`\`json fences and/or truncated at max_tokens.

### Files Changed
- `xbrain/__init__.py` — version bump to 1.21.0
- `xbrain/prompts.py` — 20-angle `ATTACK_ANGLE_CATALOG`, `ANGLE_SELECT_SYSTEM/USER`, `build_angle_catalog_text()`, `build_attack_angles_text()`, dynamic `STRESS_TEST_USER` placeholders, DEDUP PASS 3, feasibility llm_capability_fit guidance
- `xbrain/ideate.py` — `_phase_select_attack_angles()`, dynamic survive threshold, fragility verdict guard, `phase_spinner` integration, attack progress with elapsed time
- `xbrain/models.py` — `selected_attack_angles` field on `IdeateRunResult`
- `xbrain/output.py` — Attack Angles report section with table
- `xbrain/config.py` — `stress_attack_count`, `stress-angles` phase routing and max tokens
- `xbrain/log.py` — `phase_spinner()` context manager, `_PhaseSpinner` class
- `xbrain/llm.py` — improved `_extract_json()` for fenced+truncated responses
- `README.md` — updated 4 references from hardcoded 9 angles to dynamic catalog

---

## v1.20.0 — 2026-03-21

### Added

#### Constraint Extraction Phase
A new `CONSTXT` micro-phase runs before DIVERGE and automatically extracts hard constraints from the brief text using a cheap Haiku call (~$0.003). Previously, constraints were only available via CLI `--constraint` flags — now the pipeline reads the brief itself and identifies non-negotiable guardrails (e.g., "Must not require CVR registration") with source quotes. Extracted constraints are merged with any CLI constraints and propagated to all downstream phases.

#### Constraint Propagation to CONVERGE and EVOLVE
CONVERGE and EVOLVE prompts now receive the full `{constraint_context}` block. Previously, constraints were only visible to DIVERGE and GAP-FILL — meaning the scoring and evolution phases were blind to user constraints. Ideas violating hard constraints could score highly and survive into the final output.

- **CONVERGE:** Added `CONSTRAINT COMPLIANCE` scoring rule — ideas violating a hard constraint are scored 0 on impact and 0 on confidence.
- **EVOLVE:** Constraint context injected into the evolution prompt so mutations and crossovers respect constraints.

#### Thematic Diversity Enforcement
Three new diversity rules prevent the pipeline from collapsing into a single thematic niche:

- **CONVERGE:** "The top N MUST span at least 3 genuinely different solution categories. No single category may hold more than half the top-N slots." Previously required only 2 categories.
- **EVOLVE CROSSOVER:** "Pick 2 survivors from DIFFERENT DOMAIN CLUSTERS" instead of the previous "Take the 2 highest-scoring survivors" — prevents crossover from amplifying a dominant theme.
- **EVOLVE DIVERSITY RULE:** "The full set of evolved ideas MUST span at least 3 distinct solution categories." If mutations and crossovers cluster into one theme, the model must add novelty explorer ideas from under-represented categories.

#### "Obvious First" Ideation Technique
DIVERGE now includes a 7th technique: **OBVIOUS FIRST (Grounded Practicality)** — generates 2-3 ideas based on the most proven, pragmatic approaches before exploring exotic angles. Ensures the portfolio includes boring-but-effective options alongside novel ones.

### Changed

- **DIVERGE system prompt:** Replaced "Do NOT self-censor. Do NOT evaluate feasibility yet." with constraint-aware language: "you MUST respect all user-specified HARD CONSTRAINTS. Constraints are non-negotiable guardrails."
- **`build_constraint_context()`:** When constraints exist, header changed from "USER-SPECIFIED CONSTRAINTS:" to "MANDATORY CONSTRAINTS — EVERY idea MUST satisfy ALL of these. Ideas that violate any constraint are INVALID and must not be generated."
- **EVOLVE NOVELTY EXPLORER:** Now requires "at least 1 OBVIOUS/PRACTICAL idea that a pragmatic person would try first."
- **Report header:** Extracted constraints are now listed under the brief in `idea-report.md`.

### Files Changed
- `xbrain/__init__.py` — version bump to 1.20.0
- `xbrain/prompts.py` — new `CONSTRAINT_EXTRACT_SYSTEM`/`CONSTRAINT_EXTRACT_USER` prompts, hardened `DIVERGE_SYSTEM`, technique 7 "OBVIOUS FIRST", `{constraint_context}` in CONVERGE/EVOLVE/GAP-FILL, diversity mandates, `build_constraint_context()` hardened
- `xbrain/ideate.py` — new `_phase_extract_constraints()` method, `self._constraints` storage, constraint wiring into `_phase_converge()`, `_phase_evolve()`, `_phase_diverge_gapfill()`

---

## v1.19.0 — 2026-03-21

### Added

#### Rich Terminal Output
All terminal output now uses the [Rich](https://github.com/Textualize/rich) library instead of raw ANSI escape codes. A shared `Console` with a custom `Theme` (31 named styles) provides consistent, high-quality rendering across platforms:
- **Phase panels:** Phase separators render as Rich `Panel` widgets instead of raw `=====` lines.
- **Themed tags:** 20 phase tags (`tag.ideate`, `tag.stress`, etc.), 4 verdict styles, and 7 semantic styles (`ok`, `warn`, `error`, `detail`, `header`, `accent`, `score`, `evolve`).
- **Lineage table:** The `lineage` command now renders a Rich `Table` with proper column alignment (previously misaligned due to ANSI escape code character counts in f-string padding).
- **Markup injection safety:** User-supplied data (briefs, idea titles, constraints, run IDs) is escaped via `rich.markup.escape` to prevent Rich tags in LLM output from breaking terminal rendering.
- **New dependency:** `rich>=13.0.0` added to `requirements.txt`.

#### Attack Outcomes per Debate Round
The stress test prompt now requests per-attack outcome judgments (`survived`, `fatal`, `weakened`). These are stored in the new `attack_outcomes` field on `AttackResponse` and wired into `DebateExchange.outcome`, giving each debate round an explicit result instead of an empty string.

### Changed

#### Report Condensed (~31% smaller)
The `idea-report.md` output has been condensed for faster scanning:
- Header fields merged onto fewer lines (Run ID + Date on one line).
- Summary tokens + cost on one line; Quick Reference fields combined.
- ICP compressed to a single line with inline fields.
- Meta section fields joined with `|` separators.
- Redundant blank lines and `---` separators removed throughout.
- Stress test header, competitive landscape, and kill criteria inlined.

### Fixed
- **Dead code in summary block:** Removed unreachable `if final_pass > 0` branch inside `else` where `final_pass` is guaranteed ≤ 0 — the "passed stress testing" message was never displayed.
- **Unused imports:** Removed `Status` from `log.py` and unused `console` import from `ideate.py`.

### Files Changed
- `xbrain/__init__.py` — version bump to 1.19.0
- `xbrain/log.py` — complete rewrite: Rich Console + Theme replaces ANSI `_C` class, added `escape()`, Panel-based phase separators
- `xbrain/ideate.py` — all `_C.*` → Rich markup, `_esc()` on user data, dead code removal
- `xbrain/cli.py` — Rich markup + Rich `Table` for lineage, `_esc()` on brief text
- `xbrain/specify.py` — Rich markup + `_esc()` on title
- `xbrain/pipeline_helpers.py` — Rich markup for calibration display
- `xbrain/output.py` — report whitespace condensing (22 locations)
- `xbrain/models.py` — `attack_outcomes` field on `AttackResponse`
- `xbrain/prompts.py` — attack outcomes instructions + JSON example in stress test prompt
- `requirements.txt` — added `rich>=13.0.0`

---

## v1.18.0 — 2026-03-21

### Changed

#### Report Redesign — Compressed & Visual
The idea-report.md output has been redesigned for scannability:
- **Adversarial Debate**: Compressed from full multi-paragraph transcript to a compact summary table (angle + result per row). Fatal rounds are expanded below the table with full attack/defense details; survived/weakened rounds show only the one-line verdict.
- **Emoji Verdicts**: Verdicts now display ✅ BUILD, 🧬 MUTATE, 🧪 INCUBATE, ❌ KILL throughout the report — in the summary, at-a-glance table, and per-idea headers.
- **Feasibility Bars**: The feasibility matrix shows visual bars (█████░) alongside numeric scores, plus an average score row.
- **Phase-Grouped Costs**: The cost breakdown table aggregates API calls by pipeline phase (DIVERGE, CONVERGE, etc.) instead of listing every individual API call.

#### Removed Redundant Sections
- **Timeline Alignment**: Removed hardcoded timeline text (was identical boilerplate based on effort level, added no insight).
- **Meta duplication**: Removed Novelty, Estimated Effort, and Estimated Cost from the Meta section (already shown in Quick Reference).
- **Competitive Landscape truncation**: Full defensibility notes are now shown instead of being cut at 150 characters.

### Fixed

#### Pydantic Validation Crash on Structured Attacks
The LLM occasionally returns `structured_attacks` and `defenses` as lists of dicts (`[{"attack_type": "Prior art", "description": "..."}]`) instead of lists of strings. Added `field_validator` with `mode="before"` on both `AttackResponse` and `StressTestResult` that coerces dict entries to formatted strings, preventing Pydantic `ValidationError` crashes.

### Files Changed
- `xbrain/__init__.py` — version bump to 1.18.0
- `xbrain/output.py` — report format redesign (compressed debate, emoji verdicts, feasibility bars, phase-grouped costs, removed redundant sections)
- `xbrain/models.py` — `field_validator` for dict→string coercion on `structured_attacks` and `defenses`

---

## v1.17.0 — 2026-03-21

### New Features

#### Kill-Reason Pre-Filter
The kill-log previously only injected killed idea *titles* into DIVERGE as context. Now `build_kill_reason_context()` extracts the actual *reasons* ideas were killed (deduplicated, capped at 8) and injects them as explicit "AVOID" constraints. Ideas that died because of "no moat against incumbents" will now steer future generation away from moat-less ideas, rather than just avoiding the same title.

#### Attack Pattern Recycling into Evolve
The EVOLVE phase now receives attack pattern context from the cross-run memory. Previously only STRESS TEST used adaptive attack weights. Now evolved ideas (mutations, crossovers, novelty explorers) are informed about historically lethal attack angles, allowing them to pre-emptively defend against the most common kill vectors during evolution — not just during stress testing.

#### Cost Tracking in Memory
Per-run cost (USD) is now persisted in `meta-metrics.json` alongside token counts. META-LEARN can now reason about cost efficiency across runs: which strategies produce BUILD verdicts per dollar, whether cost is trending up/down, and whether refinement rounds justify their cost.

#### Confidence-Weighted Scoring
The STRESS TEST prompt now requests `attack_confidence` (0.0–1.0) — the devil's advocate's self-assessed confidence in its attack. High confidence (0.8+) means iron-clad evidence; low confidence (<0.4) means speculative reasoning. This field is stored on both `AttackResponse` and `StressTestResult` models. Low-confidence KILLs (confidence < 0.4) are automatically overridden to MUTATE, preventing speculative attacks from permanently destroying ideas.

#### Parallel Multi-Prompt Diverge
DIVERGE now runs 3 parallel async LLM calls instead of 1 sequential call. Each stream requests `ideas_per_round / 3` ideas with a different creative emphasis:
- **Stream 1**: Balanced (all 6 techniques equally)
- **Stream 2**: Contrarian emphasis (techniques 3 + 6: contrarian inversion + mechanism stealing)
- **Stream 3**: Cross-domain emphasis (techniques 2 + 4: cross-domain collision + contextual constraints)

Total idea count and token cost remain the same. Diversity increases because the 3 streams don't influence each other — each LLM call generates ideas independently, preventing single-context anchoring.

#### Stress Test Fidelity Monitor (Enhanced)
The completion summary now surfaces API crash counts directly. Override and crash stats are persisted in `meta-metrics.json` (`verdict_overrides`, `api_crashes`), enabling META-LEARN to track stress test reliability over time.

### Changed

#### Strengthened Effort Diversity Enforcement
Previously only triggered when ALL ideas had identical effort levels (all "medium"). Now triggers whenever at least one of "small" or "large" is missing from the candidate set. The idea with the lowest effort score gets remapped to "small"; the highest to "large". This ensures every run produces a quick-win and a strategic option.

#### README: Key Concepts Section
Added a comprehensive "Key Concepts" section to the README documenting 15 named methodologies: Evolutionary Computation Framework, Self-Improving Loop, Mechanism Stealing, Moat Archaeology, Assumption Inversion, Calibration Enforcement, Diversity Ratchet, Failure Taxonomy & Blocklist, Adaptive Stress Weighting, Dynamic CONVERGE, Programmatic Enforcement Rules, Web Search Grounding, Structured Key Assumptions, Memory Pruning, and the new features from this release.

### New Files
- `PARKED-IDEAS.md` — Tier 2 and Tier 3 improvement ideas parked for future reference (8 items)

### Files Changed
- `xbrain/__init__.py` — version bump to 1.17.0
- `xbrain/ideate.py` — kill-reason pre-filter in DIVERGE + REFINE, attack patterns in EVOLVE, cost in memory metrics, strengthened effort diversity, parallel 3-stream DIVERGE, confidence-weighted verdict override, fidelity stats in metrics + summary
- `xbrain/prompts.py` — `build_kill_reason_context()`, `{kill_reason_context}` in DIVERGE_USER, `{attack_pattern_context}` in EVOLVE_USER, `attack_confidence` field + instructions in STRESS_TEST
- `xbrain/models.py` — `attack_confidence` field on `AttackResponse` and `StressTestResult`
- `README.md` — added Key Concepts section (15 named methodologies)
- `PARKED-IDEAS.md` — NEW, parked improvement ideas for future reference

---

## v1.16.0 — 2026-03-21

### Refactored — DRY Extraction & Phase Constants

#### New Module: `pipeline_helpers.py`
Extracted shared helper functions into `xbrain/pipeline_helpers.py` to eliminate DRY violations:
- `apply_calibration()` — replaces a 12-line calibration block that was duplicated verbatim in `_phase_converge()` and `_phase_refine()`. Applies META-LEARN dimension multipliers, clamps scores, recomputes composites, and re-sorts candidates.
- `sanitize_text()` — Unicode→ASCII text cleanup (moved from `ideate.py`)
- `make_run_id()` — timestamped run ID generation (moved from `ideate.py`)
- `coerce_str()` — LLM value coercion utility (was dead code in `ideate.py`, preserved for future use)

#### Phase Name Constants
Added 15 module-level constants for all pipeline phase names (`PHASE_META`, `PHASE_DIVERGE`, `PHASE_CONVERGE`, etc.). All 13 LLM call sites and model-routing calls now use constants instead of magic strings, preventing typo bugs and enabling IDE navigation.

#### Dead Code Removal
- Removed unused `_coerce_str()` function from `ideate.py`
- Removed `_sanitize_text()` and `_make_run_id()` method definitions (moved to `pipeline_helpers.py`)
- Removed unused `unicodedata` import

### Files Changed
- `xbrain/__init__.py` — version bump to 1.16.0
- `xbrain/pipeline_helpers.py` — NEW: extracted shared helpers
- `xbrain/ideate.py` — replaced duplicated calibration blocks with `apply_calibration()`, replaced `_make_run_id`/`_sanitize_text` with module imports, added 15 phase constants, replaced all 26 phase string literals with constants, removed dead code

## v1.15.0 — 2026-03-21

### Added — Comprehensive Terminal Coloring

#### Full Semantic Log Migration
Migrated all remaining terminal output across the entire codebase to use semantic log functions. Every `print()` call and plain `_log()` call now uses the appropriate semantic function (`log_ok`, `log_warn`, `log_error`, `log_detail`) for consistent, meaningful coloring.

#### New Tag Colors
Added 9 new tag colors to `log.py`: `CLI` (cyan), `DRY-RUN` (cyan), `ESTIMATE` (cyan), `LINEAGE` (blue), `EXPORT` (green), `RETRY` (yellow), `THROTTLE` (yellow), `LLM` (dim), `SPECIFY` (cyan). Upgraded existing tags: `META` dim→magenta, `DEDUP` dim→blue, `SEARCH` dim→cyan.

#### CLI Output Overhaul
Replaced all 39 raw `print()` calls in `cli.py` with semantic log functions. Dry-run, estimate, lineage, and export commands now display with proper tag prefixes and color semantics. Lineage table uses `fmt_verdict()` for colored verdict display.

#### Pipeline Log Cleanup
- `ideate.py`: Migrated ~30 remaining `_log()` calls across DIVERGE, DEDUP, CONVERGE, STRESS, EVOLVE, REFINE, and MERGE phases to semantic functions
- `llm.py`: Migrated 9 calls using unregistered tags (RETRY, THROTTLE, WARN, ERROR) to `log_warn`/`log_error` with `LLM` tag
- `specify.py`: Migrated 4 calls to `log_ok`/`log_detail` with `SPECIFY` tag

### Files Changed
- `xbrain/__init__.py` — version bump to 1.15.0
- `xbrain/log.py` — added 9 new tag colors, upgraded 3 existing tag colors
- `xbrain/ideate.py` — migrated ~30 remaining plain _log() calls to semantic functions
- `xbrain/llm.py` — migrated all 9 log calls to log_warn/log_error with LLM tag
- `xbrain/specify.py` — migrated 4 log calls to log_ok/log_detail
- `xbrain/cli.py` — replaced all 39 print() calls with semantic log functions, added log imports

## v1.14.0 — 2026-03-21

### Added — Semantic Logging, Brief in Report, Evolution Metadata

#### Standardized Terminal Coloring
Added semantic log functions to `log.py`: `log_ok()`, `log_warn()`, `log_error()`, `log_detail()`, `log_verdict()`, `fmt_verdict()`, `fmt_verdicts()`. Migrated all ~40 ad-hoc color patterns in `ideate.py` to use these functions, ensuring consistent color semantics: GREEN=success/BUILD, YELLOW=warning/MUTATE, RED=error/KILL, CYAN=phase info, DIM=detail, MAGENTA=evolution. Verdict counts now display with proper coloring everywhere (terminal summary, stress test results, evolution results).

#### Original Brief in Report
Added `brief_text` field to `IdeateRunResult` model. The original prompt/brief is now displayed prominently in the report header as a blockquote, so readers always know what the run was about.

#### Evolution Metadata per Idea
Added `generation` and `evolution_rationale` fields to `IdeaCard` model. Multi-generation runs now tag each idea with its generation number and the evolutionary operator that created it. The "Ideas at a Glance" table adds a "Gen" column for multi-gen runs, and detailed cards show generation, evolution operator, and parent ideas when applicable.

### Files Changed
- `xbrain/__init__.py` — version bump to 1.14.0
- `xbrain/log.py` — added color semantics docstring, `EVOLVE` tag color, `VERDICT_COLORS` dict, 7 semantic log functions
- `xbrain/ideate.py` — migrated all log calls to semantic functions, added `VERDICT_COLORS` import, set `brief_text` on result, tag `generation`/`evolution_rationale` on evolved ideas
- `xbrain/models.py` — added `brief_text` to `IdeateRunResult`, added `generation` and `evolution_rationale` to `IdeaCard`
- `xbrain/output.py` — display brief in report header, add Gen column to glance table, show evolution metadata in detailed cards

## v1.13.1 — 2026-03-21

### Fixed — Dead Code Cleanup & Pipeline Wiring

#### Removed Dead Prompt Templates
Removed `ADVERSARIAL_DEFENSE_SYSTEM/USER` and `ADVERSARIAL_REBUTTAL_SYSTEM/USER` — 140 lines of prompt engineering from an abandoned multi-round debate feature that was never called.

#### Removed Unused Config Values
Removed `stress_test_rounds`, `score_threshold`, `plateau_delta`, and `diverge_rounds` from Config — all were defined but never referenced in pipeline logic.

#### Wired Mutation Archive into EVOLVE Phase
`mutation-archive.json` was being written every run but never read. Now injected into the EVOLVE prompt via `build_mutation_archive_context()`, giving the evolutionary engine cross-run mutation learning — past mutations inform future evolution.

#### Wired Refinement History into META-LEARN
`refinement-history.json` was being written every run but never read. Now passed to META-LEARN as `{refinement_stats}`, enabling the meta-learner to assess refinement effectiveness and recommend whether refinement rounds are productive.

#### Updated README — How It Works
Rewrote the pipeline architecture diagram and phase details to reflect the evolutionary engine: EVOLVE phase, gene recombination, novelty scoring, adaptive stress weights, technique weights, and the `--generations N` loop. Updated cost section with generation pricing.

### Files Changed
- `xbrain/__init__.py` — version bump to 1.13.1
- `xbrain/prompts.py` — removed 140 lines of dead prompts, added `build_mutation_archive_context()`, added `{mutation_archive_context}` to EVOLVE_USER, added `{refinement_stats}` to META_LEARN_USER
- `xbrain/config.py` — removed 4 unused config values
- `xbrain/ideate.py` — fixed diverge log message, wired mutation archive into EVOLVE, wired refinement history into META-LEARN
- `README.md` — rewrote How It Works section with evolutionary pipeline

## v1.13.0 — 2026-03-20

### Added

#### Multi-Generation Evolution (`--generations N`)
New `--generations` flag enables evolutionary idea refinement. After the initial stress test, survivors are evolved through mutation (fixing weaknesses), crossover (combining best traits of two ideas), and novelty exploration (maximally different ideas). Each generation runs through CONVERGE + STRESS TEST again. Ideas that survive multiple generations are battle-hardened. Default: 1 (no evolution). Cost scales linearly with generation count — users control their own API spend.

#### Idea Gene Recombination
High-scoring ideas now extract reusable "genes" (solution patterns, mechanisms, audience fits) stored in `idea-genes.json`. These genes are injected into both DIVERGE and EVOLVE prompts, enabling cross-run recombination — a proven mechanism from run #5 can be transplanted into a completely different domain in run #12.

#### Novelty Scoring in CONVERGE
CONVERGE now receives the full archive of previous winners and scores `novelty_score` more harshly for ideas that resemble past output. Ideas with novelty < 0.5 are penalised, ensuring each run produces genuinely new ideas rather than rehashing previous winners.

#### Adaptive Stress Test Weights
Stress testing now learns from history. Attack angles that have historically killed the most ideas (e.g., "Prior art" or "Defensibility") receive extra scrutiny weight, making the stress test progressively harder in the areas that matter most.

#### Self-Modifying Technique Weights
META-LEARN now tracks which generation techniques (domain_scan, mechanism_stealing, etc.) produce the most BUILD verdicts vs KILLs. Technique weights are stored in `technique-weights.json` and injected into DIVERGE, automatically allocating more idea slots to productive techniques and fewer to underperforming ones.

### Files Changed
- `xbrain/__init__.py` — version bump to 1.13.0
- `xbrain/config.py` — added `generations` field, `evolve` phase routing and token config
- `xbrain/cli.py` — added `--generations` argument to ideate and estimate subcommands
- `xbrain/prompts.py` — EVOLVE_SYSTEM/EVOLVE_USER prompts, gene/novelty/stress/technique context builders, META_LEARN_USER extended with technique_stats
- `xbrain/ideate.py` — `_phase_evolve()` method, generation loop in `run()`, gene/novelty/stress/technique context wiring, cost estimate updated
- `xbrain/memory.py` — `get_technique_weights()`, `save_technique_weights()`, `get_technique_verdict_stats()`

## v1.12.0 — 2026-03-20

### Added

#### Plain-Language Elevator Pitch
Idea descriptions were dense technical jargon that nobody could understand. Each idea now gets an `elevator_pitch` field — a 1-2 sentence plain-language summary explaining WHAT the idea is and WHY someone would want it, like you're telling a friend over coffee. The existing `rationale` field is preserved for technical details. Reports and CSV exports now display the elevator pitch by default.

#### ANSI Terminal Colors
Pipeline output now uses color-coded tags for each phase: IDEATE (cyan), DIVERGE (green), CONVERGE (blue), STRESS (red), REFINE (magenta). Verdict counts are colored (BUILD=green, MUTATE=yellow, KILL=red). Score brackets show green/yellow/red based on value. Respects `NO_COLOR` environment variable. No new dependencies — uses raw ANSI escape codes with Windows 10+ auto-detection.

### Changed

#### CONVERGE Prompt Split
The `rationale` field instruction changed from "one paragraph" (which produced dense jargon) to "Technical details: defensibility, confidence drivers, key risks" — keeping it useful for experts while the new `elevator_pitch` handles human readability.

### Files Changed
- `xbrain/__init__.py` — version bump to 1.12.0
- `xbrain/models.py` — added `elevator_pitch` field to IdeaCard
- `xbrain/prompts.py` — CONVERGE_USER prompt updated with elevator_pitch instructions
- `xbrain/ideate.py` — `_parse_candidate()` reads elevator_pitch; summary block + verdict lines colorized
- `xbrain/output.py` — reports/CSV prefer elevator_pitch over rationale
- `xbrain/log.py` — full ANSI color infrastructure (_C class, _TAG_COLORS, color detection, Windows support)

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
