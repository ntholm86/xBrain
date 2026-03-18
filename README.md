# xBrain — AI Idea Engine

Generate, score, stress-test, and refine project ideas using Claude. xBrain runs a multi-phase AI pipeline that generates diverse ideas, removes duplicates, fills creative gaps, scores with bias correction, and then attacks every idea like a hostile VC — so only the genuinely strong ones survive.

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

That's it. This scans all domains, generates ideas, deduplicates, fills gaps, scores, and stress-tests them. Results appear in `xbrain-runs/run-YYYYMMDD-HHMMSS/`.

## The Output

Each run creates a folder in `xbrain-runs/` containing:

| File | What it is |
|------|-----------|
| **idea-report.md** | The main document to read — ranked ideas with scores, verdicts, and analysis |
| idea-cards.json | Machine-readable idea data |
| idea-log.json | Full pipeline trace |
| stress-test-report.json | Detailed adversarial analysis |

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

Without `--domains`, the engine scans broadly across many fields.

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
XBRAIN_MODEL=claude-haiku-4-5-20251001  # Which Claude model to use
XBRAIN_MAX_TOKENS=16384             # Max output tokens per API call
```

## How It Works

xBrain runs a multi-phase pipeline where each phase builds on the last. The key insight: most ideation tools generate ideas and stop. xBrain generates ideas, then actively tries to destroy them — and the ideas that survive are the ones worth building.

### Pipeline Architecture

```
IMMERSE → DIVERGE → DEDUP → GAP-FILL → CONVERGE → STRESS TEST → REFINE → META-LEARN
```

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
- A specific **persona** (who exactly would use this?)
- **8-dimension scoring**: impact, confidence, effort, cost, ethical risk, sustainability, defensibility, market timing
- **Inverse scoring** ("what would need to be TRUE for this to be TERRIBLE?") — breaks the tendency to score everything 7-8 by forcing the AI to articulate failure conditions. If the idea is fragile (inverse_confidence > 6), positive scores get reduced
- **Score calibration** from the meta-learning playbook (if available)

**Phase 3 — STRESS TEST**
Devil's Advocate mode. Each idea is attacked from 9 angles:
- Prior art, adoption failure, technical blockers, problem reframe, negative externalities, obsolescence, timing, defensibility, and expertise gaps
- For expertise gap attacks, the AI evaluates whether AI tools can bridge the gap — only truly unbridgeable gaps (licensure, physical skills) count as fatal
- Each idea gets a verdict: **BUILD**, **MUTATE**, **KILL**, or **INCUBATE**

**Phase 4 — REFINE** (if no BUILD verdicts)
Iterative refinement loop (up to 3 rounds). Extracts mutations from MUTATE ideas and attack patterns from the stress test, then re-runs diverge+converge+stress with progressively tighter constraints and lower creativity. Each round learns from the failures of the previous round.

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

### The Report

Each run generates `idea-report.md` with:
- **Ideas at a Glance** — quick comparison table
- **Comparative Summary** — highest impact, highest confidence
- **Effort-Impact Quadrant** — quick wins vs strategic bets
- Per-idea: persona, 8-dimension scores, **inverse fragility check**, stress test attacks/defenses, feasibility matrix, kill criteria, competitive landscape, timeline alignment

## Cost

Each run makes 5-6 API calls (immerse + diverge + dedup + gap-fill + converge + stress test). Approximate cost per run with Haiku: **$0.03–$0.15**.
