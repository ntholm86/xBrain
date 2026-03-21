# xBrain — AI Idea Engine

Generate, score, stress-test, and evolve project ideas using Claude. xBrain runs a multi-phase AI pipeline that generates diverse ideas, removes duplicates, fills creative gaps, scores with bias correction, and then runs adversarial stress testing — a devil's advocate attacks every idea from 9 angles — so only the genuinely strong ones survive. With `--generations N`, surviving ideas are evolved through mutation, crossover, and selection pressure across multiple generations, producing battle-hardened ideas that have beaten the stress test repeatedly.

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

That's it. The engine scans across all domains with no restrictions — technology, science, health, finance, agriculture, entertainment, and everything beyond. It generates ideas, deduplicates, fills gaps, scores, and stress-tests them through adversarial attack. Results appear in `xbrain-runs/YYYYMMDD-HHMMSS-<brief-slug>/`.

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

### `--generations` — Evolutionary refinement

Run multiple generations of evolutionary refinement. After the initial stress test, surviving ideas are mutated (fixing identified weaknesses), crossed over (combining best traits), and novelty-explored (maximally different new ideas). Each generation runs through scoring and stress testing again. Ideas that survive multiple generations are battle-hardened.

```
# Default: 1 generation (no evolution)
python -m xbrain ideate --generations 1

# 3 generations: mutate, crossover, and re-test survivors
python -m xbrain ideate --generations 3

# 10 generations: intense evolutionary pressure (higher cost, stronger ideas)
python -m xbrain ideate --brief problem.txt --generations 10
```

Cost scales linearly with generation count. Use `--dry-run` to preview the estimated cost before running.

### `--dry-run` — Preview without API calls

See what would happen without spending any credits.

```
python -m xbrain ideate --brief problem.txt --dry-run
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
python -m xbrain estimate --ideas 30 --top 10 --strategy balanced
```

Accepts `--ideas`, `--top`, `--constraints`, and `--strategy`.

## Examples

**Open-ended brainstorm:**
```
python -m xbrain ideate
```

**Solve a specific problem:**
```
python -m xbrain ideate --brief "Teachers spend 10+ hours per week grading essays and students get feedback too late to improve"
```

**Explore a problem from a file:**
```
python -m xbrain ideate --brief problem.txt
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
- Success metrics with numerical targets and abort thresholds
- Validation plan — cheapest pre-build experiments to test assumptions
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

xBrain runs a multi-phase pipeline inspired by evolutionary computation. Most ideation tools generate ideas and stop. xBrain generates ideas, then actively tries to destroy them — and optionally evolves survivors through multiple generations of mutation, crossover, and selection pressure. Ideas that survive are battle-hardened.

With `--generations N`, the pipeline becomes an evolutionary engine: after stress testing, surviving ideas are mutated (fixing weaknesses), crossed over (combining best traits from multiple ideas), and novelty-explored (maximally different new ideas). Each generation runs through scoring and stress testing again. The ideas that come out of 5 or 10 generations have been pressure-tested repeatedly — the weak mutations die, the strong ones compound.

The system also learns across runs. Meta-learning distills patterns from previous results (what scores well, what gets killed, which generation techniques work), injecting that accumulated knowledge into future runs. Idea "genes" — reusable solution patterns extracted from high-scoring ideas — are recombined into new contexts. Technique weights are adjusted based on which generation methods produce the most survivors.

<details>
<summary><strong>Pipeline Architecture (click to expand)</strong></summary>

```
                                    xBrain Pipeline
                                    ===============

  USER INPUT                                    PERSISTENT MEMORY
  +---------------------+                       +----------------------------+
  | --brief  (text/file)|                       | xbrain-memory/persistent/  |
  | --constraints       |                       |   idea-archive.json        |
  | --ideas N           |                       |   kill-log.json            |
  | --top N             |                       |   domain-heat-map.json     |
  | --generations N     |                       |   playbook.json            |
  | --lang              |                       |   score-calibration.json   |
  | --strategy          |                       |   idea-lineage.json        |
  +--------+------------+                       |   idea-genes.json          |
           |                                    |   technique-weights.json   |
           v                                    |   mutation-archive.json    |
  +========================================+    |   attack-patterns.json     |
  | PHASE -1: META-LEARN                   |    |   meta-metrics.json        |
  | (every 3 runs — runs FIRST)            |    |   refinement-history.json  |
  |                                        |    |   failure-taxonomy.json    |
  |  Reads past run metrics, score history,|    +----------+-----------------+
  |  kill reasons, attack patterns,        |<---reads------+
  |  technique→verdict stats, refinement   |               |
  |  effectiveness.                        |               |
  |                                        |               |
  |  Distills into:                        |               |
  |  • Compact playbook (~200 tokens)      |               |
  |  • Score calibration multipliers       |               |
  |  • Technique weights (which methods    |               |
  |    produce the most BUILD verdicts)    |               |
  |                                        |               |
  |  Output: playbook.json,               |               |
  |          score-calibration.json,       |               |
  |          technique-weights.json        |---writes----->+
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
  +========================================+       +==========================+
  | PHASE 1: DIVERGE                       |       | Injected Context:        |
  | temp=0.9                               |<------| - Playbook (meta-learn)  |
  |                                        |       | - Idea genes (reusable   |
  |  Generate N raw idea seeds using       |       |   patterns from past     |
  |  6 simultaneous techniques:            |       |   high-scorers)          |
  |                                        |       | - Technique weights      |
  |  1. Domain Scan                        |       | - Memory (past ideas,    |
  |  2. Cross-Domain Collision             |       |   killed titles, domain  |
  |  3. Contrarian Inversion              |       |   heat map)              |
  |  4. Contextual Constraints             |       | - Brief text             |
  |  5. AI-Augmentable Gap Detection       |       | - Constraints            |
  |  6. Mechanism Stealing                 |       | - Winner repulsion list  |
  |                                        |       | - Failure taxonomy       |
  |  Output: RawIdea[] (id, concept,       |       +==========================+
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
  | PHASE 1c: DIVERGE GAP-FILL            |
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
  +========================================+       +==========================+
  | PHASE 2: CONVERGE                      |       | Novelty Scoring:         |
  | temp=0.5                               |       | When generations > 1,    |
  |                                        |<------| CONVERGE adds a novelty  |
  |  Cluster, score, rank. Select top N.   |       | dimension that rewards   |
  |                                        |       | ideas solving problems   |
  |  Per idea:                             |       | in genuinely new ways.   |
  |    - Target persona (who/pain/context) |       | Prevents evolutionary    |
  |    - 8-dim scoring (0-10 each):        |       | convergence to a local   |
  |      (+) impact, confidence,           |       | optimum.                 |
  |          sustainability, defensibility,|       +==========================+
  |          market_timing                 |
  |      (-) effort, cost, ethical_risk    |
  |    - Score reasoning per dimension     |
  |    - Inverse scoring (fragility check) |
  |    - Composite = weighted sum + 3.0    |
  |      clamped to [0, 10]               |
  |    - Post-LLM: score spread stretch,  |
  |      effort diversity enforcement,     |
  |      calibration multipliers applied   |
  |                                        |
  |  Output: IdeaCard[] (top N, ranked)    |
  +==================+=====================+
                     |
                     v
  +=================================================================+
  | PHASE 3: STRESS TEST                                            |
  | ALL ideas tested IN PARALLEL (async API calls per idea)         |
  |                                                                 |
  |  Web search: prior art lookup per idea                          |
  |    (title + "existing product competitor")                      |
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
  |  |  +--- Adaptive Weights ----------------------+             | |
  |  |  | Attack angles that historically kill more |             | |
  |  |  | ideas are weighted MORE heavily. Learned  |             | |
  |  |  | from cross-run kill patterns.             |             | |
  |  |  +------------------------------------------+             | |
  |  |                                                            | |
  |  |  Judge renders per-idea:                                   | |
  |  |    - Feasibility matrix (9 dims, 1-5 scale)               | |
  |  |    - Kill criteria (abort conditions)                      | |
  |  |    - Verdict: BUILD / MUTATE / KILL / INCUBATE             | |
  |  |  On API crash: INCUBATE + error_source="api_crash"         | |
  |  +-----------------------------------------------------------+ |
  +=========================+=======================================+
                            |
                            v
              +-------------+------------------+
              | --generations > 1?             |
              +------+---+--------------------++
               YES   |   |  NO
              +------+   +----> continue to REFINE / OUTPUT
              |
              v
  +=================================================================+
  | PHASE 3.5: EVOLVE (repeated for each generation 2..N)           |
  |                                                                 |
  |  +----- EVOLUTIONARY OPERATORS -----+                           |
  |  |                                  |                           |
  |  |  1. ELITE CARRY-FORWARD          |  Top BUILD ideas survive  |
  |  |     unchanged into next gen      |  as anchors.              |
  |  |                                  |                           |
  |  |  2. MUTATION                     |  Each MUTATE idea gets    |
  |  |     Fix the specific weakness    |  its suggested_mutation   |
  |  |     from stress testing          |  applied. Past mutations  |
  |  |                                  |  from cross-run archive   |
  |  |  3. CROSSOVER                    |  inform the process.      |
  |  |     Combine mechanism from A     |                           |
  |  |     with audience from B         |                           |
  |  |     (2-3 hybrid offspring)       |                           |
  |  |                                  |                           |
  |  |  4. NOVELTY EXPLORER             |  Maximally different from |
  |  |     Generate ideas unlike ALL    |  all survivors to prevent |
  |  |     survivors (2-3 new ideas)    |  convergence to a local   |
  |  |                                  |  optimum.                 |
  |  |                                  |                           |
  |  |  5. GENE RECOMBINATION           |  If idea genes exist from |
  |  |     Transplant proven patterns   |  previous runs, inject    |
  |  |     into new contexts            |  them into crossovers.    |
  |  +----------------------------------+                           |
  |                                                                 |
  |  Evolved ideas → CONVERGE → STRESS TEST → next generation      |
  |                                                                 |
  |  Verdict override: MUTATE ideas that survive 5+ attacks with    |
  |  ≤1 fatal get promoted to BUILD (battle-hardened).              |
  +=================================================================+
                            |
                            | (loops back to CONVERGE + STRESS TEST
                            |  for each generation)
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
                       |  |  3. Extract canonical failure types    |
                       |  |     → hard blocklist (prohibitions)    |
                       |  |  4. Ban all previous idea concepts     |
                       |  |  5. Extract problem reframes from      |
                       |  |     stress test attacks                |
                       |  |  6. Re-DIVERGE with blocklist +        |
                       |  |     learnings + winner repulsion +     |
                       |  |     failure taxonomy context           |
                       |  |     (50%->33%->25% of idea count)      |
                       |  |  7. Re-CONVERGE + Re-STRESS TEST       |
                       |  |  8. Merge survivors (title dedup)      |
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
  |    - Kill log (KILL ideas + why)       |
  |    - Mutation archive (cross-run       |
  |      mutation learning)                |
  |    - Attack patterns                   |  +---> feeds into
  |    - Domain heat map                   |  |     future runs
  |    - Idea lineage (idea→run graph)     |  |     via META-LEARN
  |    - Idea genes (score ≥ 6.5)          |  |
  |    - Technique weights                 |  |
  |    - Failure taxonomy                  |  |
  |    - Refinement history                |  |
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

</details>

<details>
<summary><strong>Phase Details (click to expand)</strong></summary>

**Phase -1 — META-LEARN** (every 3 runs, runs at pipeline start)
Cross-session learning. Reads accumulated data from all previous runs: score distributions, kill reasons, attack patterns, technique→verdict correlations, and refinement effectiveness. Distills into a compact playbook with score calibration multipliers (0.5–1.5), technique weights (which generation methods produce the most survivors), fatal patterns, anti-patterns, and domain gaps. Score calibration is applied post-LLM in CONVERGE — scores are corrected in code, not by asking the LLM. Technique weights bias DIVERGE toward methods that historically produce BUILD verdicts. Only triggers after 3+ runs.

**Phase -0.5 — CONSTRAINT CHECK** (automatic, when 2+ constraints provided)
Analyzes constraints for logical contradictions. Warns about conflicts and suggests resolutions. Non-blocking.

**Phase 1 — DIVERGE**
Raw idea generation using six techniques: Domain Scan, Cross-Domain Collision, Contrarian Inversion, Contextual Constraints, AI-Augmentable Gap Detection, and Mechanism Stealing. Each technique is weighted by meta-learning: techniques that historically produce more BUILD ideas are emphasized, while poor-performing techniques are dampened. Idea genes from high-scoring past ideas are injected as recombination material — proven solution patterns transplanted into new domains.

**Phase 1b — DEDUP** (Semantic Deduplication)
Collapses near-identical ideas and identifies over-represented themes and gap areas.

**Phase 1c — DIVERGE GAP-FILL**
Generates new ideas specifically for gap areas at higher creativity (temperature=0.95), avoiding over-represented themes.

**Phase 2 — CONVERGE**
Clusters, scores, and ranks. Output format adapts to brief type (product, internal tool, process). Each idea gets a target persona, ICP, 8-dimension scoring with reasoning, inverse fragility check, and moat check. When running multi-generation evolution, a novelty dimension is added that rewards ideas solving problems in genuinely new ways — preventing evolutionary convergence to a local optimum. Scores are calibrated post-LLM using meta-learning multipliers.

Scoring dimensions: Impact (25%), Confidence (20%), Sustainability (10%), Defensibility (10%), Market Timing (5%), Effort (-10%), Cost (-10%), Ethical Risk (-10%). Composite = weighted sum + 3.0, clamped to [0, 10].

**Phase 3 — STRESS TEST**
Adversarial attack with adaptive weights. Each idea tested in parallel via async API calls. Web search finds real prior art per idea before attacking. 9 structured attack angles + 1 freeform. Attack angles that historically kill more ideas (learned from cross-run patterns) are weighted more heavily. Produces feasibility matrix (9 dims, 1-5), kill criteria, and verdict (BUILD/MUTATE/KILL/INCUBATE).

**Phase 3.5 — EVOLVE** (when `--generations > 1`)
The evolutionary engine. For each generation after the first, applies four operators to survivors: (1) **Elite carry-forward** — top BUILD ideas survive unchanged as anchors. (2) **Mutation** — each MUTATE idea gets its suggested fix applied, informed by the cross-run mutation archive. (3) **Crossover** — combines the mechanism of one high-scorer with the audience of another, producing hybrid offspring. (4) **Novelty explorer** — generates ideas maximally different from all survivors, preventing the population from collapsing to a single niche. Idea genes from past runs are recombined into crossover and novelty ideas. Each generation's offspring go through CONVERGE and STRESS TEST again. MUTATE ideas that survive 5+ attacks with ≤1 fatal get promoted to BUILD (battle-hardened through evolutionary pressure).

**Phase 4 — REFINE** (automatic, if no BUILD verdicts)
Up to 3 refinement rounds. Extracts mutations, attack patterns, failure blocklist, and problem reframes from previous round. Re-generates with progressively lower creativity and fewer ideas. Stops when BUILD found or 3 rounds exhausted.

**Phase 5 — MEMORY UPDATE** (automatic, end of every run)
Persists idea archive, kill log, mutation archive (for cross-run mutation learning), attack patterns, failure taxonomy, domain heat map, lineage, idea genes (score ≥ 6.5), technique weights, refinement history, and run metrics. All data feeds back into future runs via META-LEARN.

</details>

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
| `technique-weights.json` | Learned technique multipliers (which methods produce survivors) |
| `mutation-archive.json` | Cross-run mutation patterns (what fixes work) |
| `attack-patterns.json` | Recurring attack patterns from stress tests |
| `failure-taxonomy.json` | Categorized failure patterns |
| `refinement-history.json` | Refinement effectiveness history (fed into META-LEARN) |

### The Report

Each run generates `idea-report.md` with:
- **Summary** — ideas generated, scored, token usage, cost
- **Comparative Summary** — highest impact idea, highest confidence idea
- **Effort-Impact Quadrant** — Quick Wins, Strategic, Blue Sky
- **Ideas at a Glance** — comparison table with score, effort, and verdict
- **Per-idea detail** — persona, ICP, 8-dimension scores with reasoning, inverse fragility check, assumptions, stress test results, feasibility matrix, moat check, kill criteria

## Cost

The stress test runs **per-idea parallel API calls** — with 8 ideas, each fires 8 concurrent requests. Combined with sequential phases (constraint check, diverge, dedup, gap-fill, converge), a typical single-generation run makes ~12 API calls and completes in under 3 minutes.

Approximate cost per run with Sonnet: **$0.10–$0.15** (1 generation), **$0.20–$0.40** (with refinement), **~$0.25** per extra generation.

With Haiku, costs are roughly 10x lower. A 2-generation run with Haiku costs ~$0.24.

API calls include automatic **retry with exponential backoff** for rate limits, timeouts, and connection errors (up to 3 attempts).

Use `python -m xbrain estimate` to preview costs before running (no API calls made):

```
python -m xbrain estimate --ideas 20 --top 8
```

The `--dry-run` flag on `ideate` also shows estimated cost.
