# xBrain — AI Idea Engine

Generate, score, stress-test, and refine project ideas using Claude. xBrain runs a multi-phase AI pipeline that generates diverse ideas, removes duplicates, fills creative gaps, scores with bias correction, and then runs a 3-round adversarial debate — attacker vs defender with rebuttals — so only the genuinely strong ones survive.

Now with **adversarial debate stress testing**, **cost forecasting**, **constraint conflict detection**, **project spec generation**, **idea lineage tracking**, **score explainability**, and **PMO export** (CSV/Jira/Markdown).

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

That's it. Without `--domains`, the engine scans across ALL domains with no restrictions — technology, science, health, finance, agriculture, entertainment, and everything beyond. Use `--domains` to focus on specific areas. It generates ideas, deduplicates, fills gaps, scores, and stress-tests them through an adversarial debate. Results appear in `xbrain-runs/YYYYMMDD-HHMMSS-<brief-slug>/`.

## The Output

Each run creates a folder in `xbrain-runs/` containing:

| File | What it is |
|------|-----------|
| **idea-report.md** | The main document to read — ranked ideas with scores, verdicts, and analysis |
| idea-cards.json | Machine-readable idea data |
| idea-log.json | Full pipeline trace |
| stress-test-report.json | Adversarial debate results (attacker vs defender) |

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

### Pipeline Architecture

```
CONSTRAINT CHECK → IMMERSE → DIVERGE → DEDUP → GAP-FILL → CONVERGE → ATTACK → DEFEND → REBUTTAL → REFINE → META-LEARN
                                                                                                                   ↓
                                                                                                              SPECIFY (Pipeline 2)
```

**Phase -0.5 — CONSTRAINT CHECK** (automatic, when 2+ constraints provided)
Analyzes constraints for logical contradictions. Warns about conflicts and suggests resolutions. Non-blocking — the pipeline continues regardless.

**Phase 0 — IMMERSE** (optional, when `--domains` is provided)
Deep-dive domain research. For each domain, the AI maps tensions, incentive structures, regulatory landscape, existing players, historical failures, and underserved populations. This builds context that makes later idea generation more grounded.

**Phase 1 — DIVERGE** (Round 1)
Raw idea generation. Uses five techniques simultaneously:
1. **Domain Scan** — identify unsolved problems per domain
2. **Cross-Domain Collision** — force novel intersections between unrelated fields
3. **Contrarian Inversion** — flip conventional assumptions and build on the opposite
4. **Contextual Constraints** — apply real-world constraints (offline, free, no PII)
5. **AI-Augmentable Gap Detection** — find ideas where AI bridges the expertise gap, so a developer without domain credentials can still deliver expert-level value

**Phase 1b — DEDUP** (Semantic Deduplication)
Analyzes all raw ideas for semantic duplicates — same concept, different words. Collapses near-identical ideas and identifies which themes are over-represented and which areas have gaps. This prevents the scoring phase from wasting cycles on copies.

**Phase 1c — DIVERGE GAP-FILL** (Round 2)
Multi-turn divergence. Takes the gaps identified by dedup and generates new ideas specifically designed to fill those gaps. Uses higher creativity (temperature=0.95) and is explicitly told NOT to repeat over-represented themes. This forces diversity.

**Phase 2 — CONVERGE**
Clusters, scores, and ranks. Each idea gets:
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

**Phase 3 — STRESS TEST (Adversarial Debate)**
Three-round adversarial debate between a Devil's Advocate (attacker) and an Idea Champion (defender), judged by a neutral arbiter:

- **Round 1 — Attack:** The Devil's Advocate attacks each idea from 9 angles: prior art, adoption failure, technical blockers, problem reframe, negative externalities, obsolescence, timing, defensibility, and expertise gaps
- **Round 2 — Defense:** The Idea Champion responds to every attack with specific counter-arguments, identifies strengths the attacker ignored, and proposes pivots for valid weaknesses
- **Round 3 — Rebuttal + Verdict:** A neutral judge facilitates final rebuttals from both sides, then renders verdicts based on the full debate

The full debate (attack → defense → rebuttal) is visible in the report for each idea, letting you see exactly why an idea was approved or rejected.

Additional outputs per idea:
- For expertise gap attacks, the AI evaluates whether AI tools can bridge the gap — only truly unbridgeable gaps (licensure, physical skills) count as fatal
- Each idea gets a **feasibility matrix** (9 dimensions, scored 1-5): technical risk, data availability, regulatory risk, infrastructure cost, time to prototype, maintenance burden, LLM capability fit, defensibility, and market timing
- Each idea gets **kill criteria** — specific conditions under which to abort building
- Each idea gets a verdict: **BUILD**, **MUTATE**, **KILL**, or **INCUBATE**

**Phase 4 — REFINE** (automatic, if no BUILD verdicts)
Iterative refinement loop — up to 3 rounds. Triggered when the stress test produces zero BUILD verdicts. Each round:
1. **Extract mutations** — collects suggested improvements from every MUTATE verdict
2. **Extract attack patterns** — identifies the most frequent fatal arguments (top 5 in round 1, top 10 in later rounds)
3. **Re-generate** — runs a fresh DIVERGE with the mutations and patterns injected as context, using progressively lower creativity (temperature drops from 0.75 → 0.60 → 0.50) and fewer ideas (50% → 33% → 25% of original count)
4. **Re-score and re-stress** — runs CONVERGE and STRESS TEST on the new batch
5. **Merge survivors** — new BUILD ideas are merged with previous rounds. Title-based deduplication ensures the same concept (from different rounds) only appears once — the highest-scored version is kept

The loop stops as soon as a BUILD verdict is found or 3 rounds are exhausted. This is how xBrain iterates toward quality — each round learns from the specific failure modes of the previous round.

**Phase 5 — META-LEARN** (every 3 runs)
Cross-session learning. Distills accumulated results into a compact playbook:
- **Score calibration**: detects if scores are inflated/deflated and which dimensions need harsher scoring
- **Fatal patterns**: top reasons ideas die (injected into future DIVERGE to avoid repeating mistakes)
- **Anti-patterns**: idea shapes to stop generating
- **Domain gaps**: underexplored areas worth targeting

The playbook is injected into future runs as fixed-size context (~200 tokens), replacing the growing raw data that would otherwise bloat prompts over time.

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
| `refinement-history.json` | History of refinement rounds |

### The Report

Each run generates `idea-report.md` with:
- **Summary** — ideas generated, scored, token usage, cost
- **Comparative Summary** — highest impact idea, highest confidence idea
- **Effort-Impact Quadrant** — categorizes ideas into Quick Wins (high impact, lower effort), Strategic (high impact, high effort), and Blue Sky (interesting but lower priority)
- **Domain Briefs** — if IMMERSE ran, the full domain research (tensions, pressure points, regulatory windows)
- **Ideas at a Glance** — quick comparison table with score, effort, and verdict
- **Per-idea detail**:
  - Target persona (who, pain, context, motivation)
  - First customer profile (ICP type, org size, readiness)
  - 8-dimension score table with reasoning per dimension
  - Inverse fragility check (what would make this terrible?)
  - Key assumptions (critical unknowns that must be validated)
  - Stress test results: attacks made/survived/fatal, strongest attack, strongest defense, suggested mutation
  - **Full adversarial debate** — each attack angle shown with attacker argument, defender response, attacker rebuttal, defender rebuttal, and outcome (SURVIVED/FATAL/WEAKENED)
  - Feasibility matrix (9 dimensions, 1-5 scale)
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

Each run makes 8-10 API calls (constraint check + immerse + diverge + dedup + gap-fill + converge + 3 stress test calls). If the refinement loop triggers (no BUILD verdicts), each refinement round adds 5 more API calls (diverge + converge + 3 stress test calls), up to 3 rounds — so worst case is ~25 API calls.

The actual cost (tokens in/out and dollar amount) is tracked and shown in the terminal output and in the report header.

Approximate cost per run with Haiku: **$0.10–$0.30** (simple run), **$0.30–$0.60** (with refinement rounds). The adversarial debate (3 LLM calls per stress test round) adds ~$0.10–$0.15 compared to the previous single-call stress test.

Use `python -m xbrain estimate` to preview costs before running (no API calls made):

```
python -m xbrain estimate --ideas 20 --top 8 --domains health fintech
```

The `--dry-run` flag on `ideate` also shows estimated cost.
