# xBrain — AI Idea Engine

Generate, score, stress-test, and refine project ideas using Claude. xBrain runs a multi-phase AI pipeline that generates diverse ideas, removes duplicates, fills creative gaps, scores with bias correction, and then runs adversarial stress testing — a devil's advocate attacks every idea from 9 angles — so only the genuinely strong ones survive.

Now with **adversarial stress testing**, **dynamic brief-adaptive scoring**, **cross-run diversity ratchet**, **failure taxonomy learning**, **mechanism stealing**, **moat archaeology**, **cost forecasting**, **constraint conflict detection**, **project spec generation**, **idea lineage tracking**, **score explainability**, and **PMO export** (CSV/Jira/Markdown).

## What's New in v1.1

**Dynamic CONVERGE** — The scoring/ranking phase now adapts its output fields to match the brief type. Product briefs get persona/ICP/go-to-market fields. Internal tool briefs get user role/workflow fit. Process briefs get current-state/proposed-change/metrics. No more forcing every idea into a SaaS product template.

**Diversity Ratchet** — Cross-run winner repulsion. Previous high-scoring ideas are injected into DIVERGE as an exclusion list, pushing the engine toward unexplored territory instead of regenerating the same winning patterns.

**Failure Taxonomy** — Structured learning from past attacks. Failed ideas are classified into 6 categories (prior art, adoption, technical, timing, defensibility, economics) and persisted. Future runs receive this taxonomy as context, steering generation away from idea shapes that repeatedly die to the same attack patterns.

**Mechanism Stealing** (Inverse Ideation) — New DIVERGE technique (#6). Extracts working mechanisms from successful products in unrelated fields and transplants them into new contexts. Forces cross-pollination beyond simple domain collision.

**Moat Archaeology** — Defensibility as a first-class constraint. During CONVERGE, any idea scoring below 4 on defensibility triggers a mandatory moat check: the AI must suggest a concrete mutation that would add a defensibility moat (network effects, data flywheel, switching costs, etc.). A defensibility gate also adjusts composite scores.

**Streamlined Stress Test** — Reduced from 3-round adversarial debate (attack → defense → rebuttal) to single-round attack. Verdicts are now rendered immediately after the attack phase. This cut per-run cost from ~$0.30 to ~$0.14 and time from ~5 minutes to ~3 minutes, with no measurable loss in verdict quality.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Add your Anthropic API key:
   ```
   copy .env.example .env
   ```
   Open `.env` and paste your key after `ANTHROPIC_API_KEY=`

## Quick Start

```
python -m xbrain ideate
```

That's it. Without `--domains`, the engine scans across ALL domains with no restrictions — technology, science, health, finance, agriculture, entertainment, and everything beyond. Use `--domains` to focus on specific areas. It generates ideas, deduplicates, fills gaps, scores, and stress-tests them through adversarial attack. Results appear in `xbrain-runs/YYYYMMDD-HHMMSS-<brief-slug>/`.

## The Output

Each run creates a folder in `xbrain-runs/` containing:

| File | What it is |
|------|-----------|
| **idea-report.md** | The main document to read — ranked ideas with scores, verdicts, and analysis |
| idea-cards.json | Machine-readable idea data |
| idea-log.json | Full pipeline trace |
| stress-test-report.json | Adversarial stress test results (9-angle attack) |

Open **idea-report.md** to review your ideas.

## Parameters

### `--brief` — Give it context

The most powerful parameter. Feed in a problem to solve, an idea to improve, or a file with context.

```
# Inline text
python -m xbrain ideate --brief "How can small restaurants compete with delivery apps?"

# From a file
python -m xbrain ideate --brief my-problem.txt
```

Auto-detects: if the value is a path to an existing file, it reads the file. Otherwise treats it as text.

Without `--brief`, the engine generates ideas on its own across all domains.

### `--domains` — Focus areas

Narrow ideation to specific topics. Write anything — the AI interprets it.

```
python -m xbrain ideate --domains health

python -m xbrain ideate --domains fintech "urban planning" agriculture

python -m xbrain ideate --domains "developer tools" gaming education

python -m xbrain ideate --domains "B2B SaaS" "climate tech" logistics
```

Without `--domains`, the engine scans across all fields with no restrictions.

### `--constraints` — Add requirements

Force ideas to meet specific conditions. Write anything.

```
python -m xbrain ideate --constraints "must work offline"

python -m xbrain ideate --constraints "must be free" "must work on mobile" "no login required"

python -m xbrain ideate --constraints "solo developer" "launch in 2 weeks" "zero marketing budget"
```

### `--ideas` — How many raw ideas to generate

Default: 20. More ideas = more variety but higher cost.

```
python -m xbrain ideate --ideas 30
```

### `--top` — How many to score and stress-test

Default: 8. Only the best raw ideas get scored and attacked.

```
python -m xbrain ideate --top 5
```

### `--dry-run` — Preview without API calls

See what would happen without spending any credits.

```
python -m xbrain ideate --brief problem.txt --domains health --dry-run
```

### `--lang` — Output language

Get the report in any language.

```
python -m xbrain ideate --lang danish

python -m xbrain ideate --brief "problem.txt" --lang spanish
```

Default: english.

### `--strategy` — Model routing

Control which model handles which pipeline phase. Saves money by routing cheap phases to Haiku and expensive phases to a stronger model.

```
# Use one model for everything (default)
python -m xbrain ideate --strategy single

# Use cheapest model for all phases
python -m xbrain ideate --strategy cheapest

# Use Haiku for generation, best model for scoring/stress testing
python -m xbrain ideate --strategy balanced

# Use the best model for everything
python -m xbrain ideate --strategy best
```

Configure which models are "cheap" and "best" in `.env`:
```
XBRAIN_CHEAP_MODEL=claude-haiku-4-5-20251001
XBRAIN_BEST_MODEL=claude-sonnet-4-20250514
```

### `estimate` — Preview costs

Estimate API cost before running, with per-phase breakdown and strategy comparison. No API calls made.

```
python -m xbrain estimate --ideas 20 --top 8
python -m xbrain estimate --ideas 30 --top 10 --domains health fintech --strategy balanced
```

Accepts `--ideas`, `--top`, `--domains`, `--constraints`, and `--strategy`.

## Examples

**Open-ended brainstorm:**
```
python -m xbrain ideate
```

**Solve a specific problem:**
```
python -m xbrain ideate --brief "Teachers spend 10+ hours per week grading essays and students get feedback too late to improve"
```

**Explore a problem from a file with focused domains:**
```
python -m xbrain ideate --brief problem.txt --domains health technology
```

**Quick cheap run to test an idea:**
```
python -m xbrain ideate --brief "AI-powered restaurant menu optimizer" --ideas 10 --top 3
```

**Maximum breadth with constraints:**
```
python -m xbrain ideate --ideas 40 --top 15 --constraints "must cost under $100/month to run" "must not require user accounts"
```

## Pipeline 2: Specify — Project Spec Generator

After ideation, convert your top BUILD ideas into actionable project specs with user stories, API contracts, task breakdowns, and MVP scope.

```
python -m xbrain specify --idea ./xbrain-runs/20260319-143002-restaurant-menu/idea-cards.json --select idea-003
```

This generates:
- **spec-idea-003.md** — Human-readable project specification
- **spec-idea-003.json** — Machine-readable spec data

The spec includes:
- Executive summary
- User stories with acceptance criteria
- Architecture & tech stack recommendations
- API contracts (RESTful endpoints)
- Data model with relationships
- 10-15 development tasks ordered by dependency
- Technical risks and mitigations from the stress test
- MVP scope (what to build in a 2-week sprint)
- Kill criteria (when to abort)

### Specify options

```
# Generate spec in another language
python -m xbrain specify --idea ./xbrain-runs/20260319-143002-restaurant-menu/idea-cards.json --select idea-003 --lang danish
```

## Export (PMO Bridge)

Export BUILD ideas to project management tools. Three formats:

```
# CSV (importable to Jira, Linear, Asana, Excel)
python -m xbrain export --run ./xbrain-runs/20260319-143002-restaurant-menu --format csv

# Markdown task list
python -m xbrain export --run ./xbrain-runs/20260319-143002-restaurant-menu --format md

# Jira-compatible JSON (bulk import)
python -m xbrain export --run ./xbrain-runs/20260319-143002-restaurant-menu --format jira
```

By default, only BUILD ideas are exported. Use `--all` to include all ideas.

Write to a file instead of stdout:

```
python -m xbrain export --run ./xbrain-runs/20260319-143002-restaurant-menu --format csv --output ideas.csv
```

The CSV includes: ID, title, description, score, verdict, effort, estimated cost, domains, persona, pain point, kill criteria, and auto-mapped priority (Critical/High/Medium/Low based on score).

## Constraint Conflict Detection

When you provide 2+ constraints, xBrain automatically checks for logical contradictions before running the pipeline.

```
python -m xbrain ideate --constraints "must work offline" "must sync in real-time" "no user accounts"
```

If conflicts are found, you'll see:
```
[CONSTCHK ] ⚠ 1 conflict(s) detected:
[CONSTCHK ]   CONFLICT: must work offline vs must sync in real-time
[CONSTCHK ]     Why: Offline operation and real-time sync are contradictory
[CONSTCHK ]     Fix: Consider eventual sync instead of real-time
[CONSTCHK ] Proceeding anyway — constraints will be applied as-is.
```

The pipeline continues regardless — it's a warning, not a blocker. But it helps you catch impossible requirements early.

## Idea Lineage

Track idea evolution across runs. xBrain remembers every idea it generates, its score, verdict, and which run produced it.

```
# Browse all ideas across all runs
python -m xbrain lineage

# Filter by verdict
python -m xbrain lineage --verdict BUILD

# Filter by domain
python -m xbrain lineage --domain health

# Show top 50
python -m xbrain lineage --top 50
```

### Idea Genes

High-scoring ideas are automatically decomposed into reusable "idea genes" — problem patterns and solution patterns that get injected into future runs. Over time, xBrain builds an institutional memory of what works.

Genes are stored in `xbrain-memory/persistent/idea-genes.json` and used by the meta-learning phase.

## Verdicts

Each idea gets a verdict after stress-testing:

| Verdict | Meaning |
|---------|---------|
| **BUILD** | Survived attacks — worth building now |
| **MUTATE** | Good core but needs changes (mutation suggested in report) |
| **INCUBATE** | Promising but wrong timing or missing dependency |
| **KILL** | Fatal flaws that can't be fixed |

## Configuration

Edit `.env` to change defaults:

```
ANTHROPIC_API_KEY=sk-ant-...        # Required
XBRAIN_MODEL=claude-sonnet-4-20250514   # Which Claude model to use (default)
XBRAIN_MAX_TOKENS=16384             # Max output tokens per API call
XBRAIN_MODEL_STRATEGY=single        # Model routing: single|cheapest|balanced|best
XBRAIN_CHEAP_MODEL=claude-haiku-4-5-20251001   # Model for cheap phases (balanced strategy)
XBRAIN_BEST_MODEL=claude-sonnet-4-20250514     # Model for critical phases (balanced strategy)
```

## How It Works

xBrain runs a multi-phase pipeline where each phase builds on the last. The key insight: most ideation tools generate ideas and stop. xBrain generates ideas, then actively tries to destroy them — and the ideas that survive are the ones worth building.

### Pipeline Architecture (Detailed)

```
                                    xBrain Pipeline: Prompt to Report
                                    ==================================

  USER INPUT                                    PERSISTENT MEMORY
  +---------------------+                       +----------------------------+
  | --brief  (text/file)|                       | xbrain-memory/persistent/  |
  | --domains           |                       |   idea-archive.json        |
  | --constraints       |                       |   kill-log.json            |
  | --ideas N           |                       |   domain-heat-map.json     |
  | --top N             |                       |   playbook.json            |
  | --lang              |                       |   score-calibration.json   |
  | --strategy          |                       |   idea-lineage.json        |
  +--------+------------+                       |   idea-genes.json          |
           |                                    |   mutation-archive.json    |
           v                                    |   attack-patterns.json     |
  +========================================+    |   meta-metrics.json        |
  | PHASE -1: META-LEARN                   |    |   refinement-history.json  |
  | (every 3 runs — runs FIRST)            |    |   failure-taxonomy.json    |
  |                                        |    +----------+-----------------+
  |  Reads past run metrics, score history,|<---reads------+
  |  kill reasons, attack patterns.        |               |
  |  Distills into compact playbook        |               |
  |  (~200 tokens) + score calibration.    |               |
  |                                        |               |
  |  Output: playbook.json,               |               |
  |          score-calibration.json        |---writes----->+
  +==================+=====================+
                     |
                     v
  +========================================+
  | PHASE -0.5: CONSTRAINT CHECK           |
  | (auto, when 2+ constraints)            |
  |                                        |
  |  Detects logical contradictions.       |
  |  Warns but does NOT block pipeline.    |
  |  e.g. "offline" vs "real-time sync"    |
  +==================+=====================+
                     |
                     v
  +========================================+
  | PHASE 0: IMMERSE                       |
  | (optional, when --domains provided)    |
  |                                        |
  |  Per-domain deep dive:                 |
  |    - Incentive structures              |
  |    - Regulatory landscape              |
  |    - Existing players & blind spots    |
  |    - Historical failures               |
  |    - Technology gaps                   |
  |    - Underserved populations           |
  |                                        |
  |  Output: DomainBrief[] (JSON)          |
  +==================+=====================+
                     |
                     v
  +========================================+       +==========================+
  | PHASE 1: DIVERGE (Round 1)             |       | Injected Context:        |
  | temp=0.9                               |<------| - Playbook (meta-learn)  |
  |                                        |       | - Domain briefs          |
  |  Generate N raw idea seeds using       |       | - Memory (past ideas,    |
  |  6 simultaneous techniques:            |       |   killed titles, domain  |
  |                                        |       |   heat map)              |
  |  1. Domain Scan                        |       | - Brief text             |
  |  2. Cross-Domain Collision             |       | - Constraints            |
  |  3. Contrarian Inversion              |       | - Winner repulsion list  |
  |  4. Contextual Constraints             |       | - Failure taxonomy       |
  |  5. AI-Augmentable Gap Detection       |       +==========================+
  |  6. Mechanism Stealing                 |
  |                                        |
  |  Output: RawIdea[] (id, concept,       |
  |    source_technique, domain_tags,      |
  |    novelty_signal)                     |
  +==================+=====================+
                     |
                     v
  +========================================+
  | PHASE 1b: DEDUP                        |
  | (Semantic Deduplication)               |
  |                                        |
  |  Collapse near-identical ideas.        |
  |  Identify:                             |
  |    - Over-represented themes           |
  |    - Gap areas (missing topics)        |
  |                                        |
  |  Output: filtered RawIdea[],           |
  |    gaps[], overrepresented[]           |
  +==================+=====================+
                     |
                     v
  +========================================+
  | PHASE 1c: DIVERGE GAP-FILL (Round 2)  |
  | temp=0.95 (max creativity)             |
  |                                        |
  |  Generate new ideas ONLY in gap areas. |
  |  Explicitly avoids over-represented    |
  |  themes. Up to 50% of original count.  |
  |                                        |
  |  Output: additional RawIdea[]          |
  |    (merged with Round 1 results)       |
  +==================+=====================+
                     |
                     v
  +========================================+
  | PHASE 2: CONVERGE                      |
  | temp=0.5                               |
  |                                        |
  |  Cluster, score, rank. Select top N.   |
  |                                        |
  |  Per idea:                             |
  |    - Target persona (who/pain/context) |
  |    - 8-dim scoring (0-10 each):        |
  |      (+) impact, confidence,           |
  |          sustainability, defensibility,|
  |          market_timing                 |
  |      (-) effort, cost, ethical_risk    |
  |    - Score reasoning per dimension     |
  |    - Inverse scoring (fragility check) |
  |    - Composite = weighted sum + 3.0    |
  |      clamped to [0, 10]               |
  |    - Calibration from meta-learn       |
  |                                        |
  |  Output: IdeaCard[] (top N, ranked)    |
  +==================+=====================+
                     |
                     v
  +=================================================================+
  | PHASE 3: STRESS TEST (Single-Round Attack)                      |
  | ALL ideas tested IN PARALLEL (async API calls per idea)         |
  |                                                                 |
  |  +-----------------------------------------------------------+ |
  |  | ATTACK (Devil's Advocate)                     temp=0.4      | |
  |  |                                                            | |
  |  |  9 structured attack angles per idea:                      | |
  |  |  Prior art, Adoption failure, Technical blocker,           | |
  |  |  Problem reframe, Negative externalities, Obsolescence,    | |
  |  |  Timing, Defensibility, Expertise gap                      | |
  |  |  + 1 freeform devastating attack                           | |
  |  |                                                            | |
  |  |  Judge renders per-idea:                                   | |
  |  |    - Feasibility matrix (9 dims, 1-5 scale)               | |
  |  |    - Kill criteria (abort conditions)                      | |
  |  |    - Verdict: BUILD / MUTATE / KILL / INCUBATE             | |
  |  +-----------------------------------------------------------+ |
  +=========================+=======================================+
                            |
                            v
                   +--------+--------+
                   | Any BUILD       |
                   | verdicts?       |
                   +--------+--------+
                   YES |         | NO
                       |         v
                       |  +========================================+
                       |  | PHASE 4: REFINE (up to 3 rounds)       |
                       |  |                                        |
                       |  |  Round loop (temp: 0.75->0.60->0.50):  |
                       |  |                                        |
                       |  |  1. Extract mutations from MUTATE      |
                       |  |  2. Extract fatal attack patterns      |
                       |  |     (top 5 round 1, top 10 later)      |
                       |  |  3. Re-DIVERGE with learnings injected |
                       |  |     + winner repulsion + failure       |
                       |  |     taxonomy context                   |
                       |  |     (50%->33%->25% of idea count)      |
                       |  |  4. Re-CONVERGE + Re-STRESS TEST       |
                       |  |  5. Merge survivors (title dedup)      |
                       |  |                                        |
                       |  |  Stop when BUILD found or 3 rounds hit |
                       |  +==================+=====================+
                       |                     |
                       +<--------------------+
                       |
                       v
  +========================================+
  | PHASE 5: MEMORY UPDATE                 |
  | (automatic, every run)                 |
  |                                        |
  |  Writes to xbrain-memory/persistent/:  |
  |    - Idea archive (all survivors)      |
  |    - Kill log (KILL ideas + reasons)   |
  |    - Mutation archive                  |
  |    - Attack patterns                   |  +---> feeds into
  |    - Domain heat map                   |  |     future runs
  |    - Idea lineage (idea->run graph)    |  |     via META-LEARN
  |    - Idea genes (score >= 6.5)         |  |
  |    - Run metrics                       +--+
  +==================+=====================+
                     |
                     v
  +========================================+
  | OUTPUT FILES (xbrain-runs/<run-id>/)   |
  |                                        |
  |  idea-report.md ............ Flagship  |
  |    human-readable ranked report with   |
  |    scores, personas, stress tests,     |
  |    moat checks, feasibility matrices.  |
  |                                        |
  |  idea-cards.json ........... Machine-  |
  |    readable survivor data.             |
  |                                        |
  |  idea-log.json ............. Full      |
  |    pipeline trace (all phases).        |
  |                                        |
  |  stress-test-report.json ... All       |
  |    adversarial debate results.         |
  +==================+=====================+
                     |
                     | Human reviews report,
                     | picks a BUILD idea
                     v
  +========================================+
  | PIPELINE 2: SPECIFY                    |
  | python -m xbrain specify              |
  |   --idea idea-cards.json --select ID   |
  |                                        |
  |  Converts idea into actionable spec:   |
  |    - User stories + acceptance criteria|
  |    - Architecture + tech stack         |
  |    - API contracts (REST endpoints)    |
  |    - Data model + relationships        |
  |    - 10-15 dev tasks (ordered)         |
  |    - Risks & mitigations               |
  |    - MVP scope (2-week sprint)         |
  |    - Kill criteria                     |
  |                                        |
  |  Output: spec-<id>.md + spec-<id>.json |
  +========================================+
```

**Phase -1 — META-LEARN** (every 3 runs, runs at pipeline start)
Cross-session learning. Before any ideation begins, distills accumulated results from previous runs into a compact playbook:
- **Score calibration**: detects if scores are inflated/deflated and which dimensions need harsher scoring
- **Fatal patterns**: top reasons ideas die (injected into DIVERGE to avoid repeating mistakes)
- **Anti-patterns**: idea shapes to stop generating
- **Domain gaps**: underexplored areas worth targeting

The playbook is injected into future runs as fixed-size context (~200 tokens), replacing the growing raw data that would otherwise bloat prompts over time. Only triggers after 3+ runs have accumulated since the last distillation.

**Phase -0.5 — CONSTRAINT CHECK** (automatic, when 2+ constraints provided)
Analyzes constraints for logical contradictions. Warns about conflicts and suggests resolutions. Non-blocking — the pipeline continues regardless.

**Phase 0 — IMMERSE** (optional, when `--domains` is provided)
Deep-dive domain research. For each domain, the AI maps tensions, incentive structures, regulatory landscape, existing players, historical failures, and underserved populations. This builds context that makes later idea generation more grounded.

**Phase 1 — DIVERGE** (Round 1)
Raw idea generation. Uses six techniques simultaneously:
1. **Domain Scan** — identify unsolved problems per domain
2. **Cross-Domain Collision** — force novel intersections between unrelated fields
3. **Contrarian Inversion** — flip conventional assumptions and build on the opposite
4. **Contextual Constraints** — apply real-world constraints (offline, free, no PII)
5. **AI-Augmentable Gap Detection** — find ideas where AI bridges the expertise gap, so a developer without domain credentials can still deliver expert-level value
6. **Mechanism Stealing** (Inverse Ideation) — extract working mechanisms from successful products in unrelated fields and transplant them into new contexts

Additional context injected:
- **Winner repulsion list** — titles and domains of previous high-scoring ideas, instructing the AI to avoid similar territory (cross-run diversity ratchet)
- **Failure taxonomy** — categorized attack patterns from past runs (prior art, adoption, technical, timing, defensibility, economics), steering generation away from repeatedly fatal idea shapes

**Phase 1b — DEDUP** (Semantic Deduplication)
Analyzes all raw ideas for semantic duplicates — same concept, different words. Collapses near-identical ideas and identifies which themes are over-represented and which areas have gaps. This prevents the scoring phase from wasting cycles on copies.

**Phase 1c — DIVERGE GAP-FILL** (Round 2)
Multi-turn divergence. Takes the gaps identified by dedup and generates new ideas specifically designed to fill those gaps. Uses higher creativity (temperature=0.95) and is explicitly told NOT to repeat over-represented themes. This forces diversity.

**Phase 2 — CONVERGE**
Clusters, scores, and ranks. The output format dynamically adapts to the brief type:
- **Product/startup briefs** → persona, ICP, go-to-market fields
- **Internal tool briefs** → user role, workflow fit, integration surface
- **Process/workflow briefs** → current state, proposed change, success metrics
- **Default** → flexible format matching the brief's nature

Each idea also gets a **moat check** — if defensibility scores below 4, the AI must suggest a concrete mutation that would add a defensibility moat (network effects, data flywheel, switching costs, etc.). This is the **Moat Archaeology** feature.

Per idea:
- A specific **target persona** — not generic demographics, but a concrete person: who they are, what pain they feel, what context they work in, and what motivates them
- A **first customer profile (ICP)** — the ideal early adopter type, organization size, and readiness level
- **8-dimension scoring** (0-10 each):

| Dimension | Direction | Weight | What it measures |
|-----------|-----------|--------|------------------|
| Impact | Higher = better | 25% | How many people affected, how severe the pain |
| Confidence | Higher = better | 20% | How proven is the approach, how reliable the evidence |
| Sustainability | Higher = better | 10% | Revenue model strength, retention dynamics |
| Defensibility | Higher = better | 10% | Moat, switching costs, network effects |
| Market Timing | Higher = better | 5% | Is the window open now? |
| Effort | Lower = better | -10% | Implementation complexity (scored assuming developer + AI tools) |
| Cost | Lower = better | -10% | Infrastructure and operational costs |
| Ethical Risk | Lower = better | -10% | Potential for misuse or harm |

  Composite score formula: `(0.25 x impact + 0.20 x confidence + 0.10 x sustainability + 0.10 x defensibility + 0.05 x market_timing - 0.10 x effort - 0.10 x cost - 0.10 x ethical_risk) + 3.0`, clamped to 0-10.

- **Score reasoning**: for each dimension, a human-readable explanation of WHY that score was given — makes scoring auditable by non-technical stakeholders
- **Inverse scoring** ("what would need to be TRUE for this to be TERRIBLE?") — breaks the tendency to score everything 7-8 by forcing the AI to articulate failure conditions. If the idea is fragile (inverse_confidence > 6), positive scores get reduced
- **Score calibration** from the meta-learning playbook (if available). Scores are marked UNCALIBRATED until the meta-learning phase has run (every 3 runs). After calibration, weak dimensions are scored more harshly and inflated/deflated scores are adjusted

**Phase 3 — STRESS TEST (Adversarial Attack)**
Single-round adversarial attack by a Devil's Advocate. Each idea is tested **in parallel** — all ideas run their attack concurrently using async API calls, significantly reducing wall-clock time:

- **Attack:** The Devil's Advocate attacks each idea from 9 angles: prior art, adoption failure, technical blockers, problem reframe, negative externalities, obsolescence, timing, defensibility, and expertise gaps. A verdict is rendered immediately based on attack severity.

For expertise gap attacks, the AI evaluates whether AI tools can bridge the gap — only truly unbridgeable gaps (licensure, physical skills) count as fatal.

Additional outputs per idea:
- **Feasibility matrix** (9 dimensions, scored 1-5): technical risk, data availability, regulatory risk, infrastructure cost, time to prototype, maintenance burden, LLM capability fit, defensibility, and market timing
- **Kill criteria** — specific conditions under which to abort building
- **Verdict**: BUILD, MUTATE, KILL, or INCUBATE

**Phase 4 — REFINE** (automatic, if no BUILD verdicts)
Iterative refinement loop — up to 3 rounds. Triggered when the stress test produces zero BUILD verdicts. Each round:
1. **Extract mutations** — collects suggested improvements from every MUTATE verdict
2. **Extract attack patterns** — identifies the most frequent fatal arguments (top 5 in round 1, top 10 in later rounds)
3. **Re-generate** — runs a fresh DIVERGE with the mutations, patterns, winner repulsion list, and failure taxonomy injected as context, using progressively lower creativity (temperature drops from 0.75 → 0.60 → 0.50) and fewer ideas (50% → 33% → 25% of original count)
4. **Re-score and re-stress** — runs CONVERGE and STRESS TEST on the new batch
5. **Merge survivors** — new BUILD ideas are merged with previous rounds. Title-based deduplication ensures the same concept (from different rounds) only appears once — the highest-scored version is kept

The loop stops as soon as a BUILD verdict is found or 3 rounds are exhausted. This is how xBrain iterates toward quality — each round learns from the specific failure modes of the previous round.

**Phase 5 — MEMORY UPDATE** (automatic, end of every run)
Persists all run data to cross-session memory:
- **Idea archive**: all survivors (ID, title, score, verdict, domains) appended to the archive
- **Kill log**: KILL ideas and their strongest fatal argument recorded for future avoidance
- **Mutations**: MUTATE ideas with suggested improvements saved for refinement learning
- **Attack patterns**: recurring fatal arguments extracted and stored
- **Failure taxonomy**: attacks classified into 6 categories (prior art, adoption, technical, timing, defensibility, economics) for cross-run learning
- **Domain heat map**: domains used in this run tallied for exploration tracking
- **Lineage**: idea→run relationships recorded for cross-run lineage browsing
- **Idea genes**: high-scoring ideas (score ≥ 6.5) decomposed into reusable solution patterns (capped at 100 genes)
- **Run metrics**: token usage, build rate, and timestamps logged

### Persistent Memory

xBrain remembers across runs. Files in `xbrain-memory/persistent/`:

| File | Purpose |
|------|---------|
| `idea-archive.json` | All ideas ever generated (scores, verdicts, domains) |
| `kill-log.json` | Ideas that were killed and why |
| `domain-heat-map.json` | Which domains have been explored (avoids repetition) |
| `meta-metrics.json` | Run statistics (token usage, build rates) |
| `playbook.json` | Distilled meta-learning playbook |
| `score-calibration.json` | Score bias detection and correction |
| `idea-lineage.json` | Idea evolution graph (parent→child, run→idea) |
| `idea-genes.json` | Reusable idea patterns extracted from high-scoring ideas |
| `mutation-archive.json` | MUTATE ideas with their suggested mutations |
| `attack-patterns.json` | Recurring attack patterns from stress tests |
| `failure-taxonomy.json` | Categorized failure patterns (prior art, adoption, technical, timing, defensibility, economics) |
| `refinement-history.json` | History of refinement rounds |

### The Report

Each run generates `idea-report.md` with:
- **Summary** — ideas generated, scored, token usage, cost
- **Comparative Summary** — highest impact idea, highest confidence idea
- **Effort-Impact Quadrant** — categorizes ideas into Quick Wins (high impact, lower effort), Strategic (high impact, high effort), and Blue Sky (interesting but lower priority)
- **Domain Briefs** — if IMMERSE ran, the full domain research (tensions, pressure points, regulatory windows)
- **Ideas at a Glance** — quick comparison table with score, effort, and verdict
- **Per-idea detail**:
  - Target persona (who, pain, context, motivation) — dynamically adapted to brief type
  - First customer profile (ICP type, org size, readiness) — for product briefs only
  - 8-dimension score table with reasoning per dimension
  - Inverse fragility check (what would make this terrible?)
  - Key assumptions (critical unknowns that must be validated)
  - Stress test results: attacks made/survived/fatal, strongest attack, suggested mutation
  - Feasibility matrix (9 dimensions, 1-5 scale)
  - Moat check — if defensibility < 4, a moat-strengthening mutation is suggested
  - Kill criteria (abort conditions for the build phase)
  - Competitive landscape and timeline alignment

### Console Output

Each pipeline phase prints a visual header, and at the end of a run, xBrain prints a structured completion summary:
- Verdict breakdown (BUILD / MUTATE / KILL / INCUBATE counts)
- Refinement rounds used (if any)
- Top 5 ideas by score
- Output file locations
- Total tokens and cost
- Suggested next command (e.g. `specify` for the top BUILD idea)

## Cost

The stress test runs **per-idea parallel API calls** — with 8 ideas, each fires 8 concurrent requests instead of one batched request. This multiplies the number of API calls but dramatically reduces wall-clock time since all calls execute simultaneously. Combined with the sequential phases (constraint check, immerse, diverge, dedup, gap-fill, converge), a typical run makes ~15 API calls and completes in under 3 minutes.

If the refinement loop triggers (no BUILD verdicts), each refinement round adds diverge + converge + parallel stress test calls, up to 3 rounds.

The actual cost (tokens in/out and dollar amount) is tracked and shown in the terminal output and in the report header.

Approximate cost per run with Sonnet: **$0.10–$0.15** (simple run), **$0.20–$0.40** (with refinement rounds).

API calls include automatic **retry with exponential backoff** for rate limits, timeouts, and connection errors (up to 3 attempts).

Use `python -m xbrain estimate` to preview costs before running (no API calls made):

```
python -m xbrain estimate --ideas 20 --top 8 --domains health fintech
```

The `--dry-run` flag on `ideate` also shows estimated cost.
