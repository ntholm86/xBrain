# xBrain — AI Idea Engine

Generate, score, and stress-test project ideas using Claude.

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

That's it. This scans all domains, generates 20 ideas, scores the top 8, and stress-tests them. Results appear in `xbrain-runs/run-YYYYMMDD-HHMMSS/`.

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

Narrow ideation to specific domains. Available domains:

| Domain | What it covers |
|--------|---------------|
| `political` | Governance, policy, civic tech, elections |
| `scientific` | Research tools, lab tech, data analysis |
| `societal` | Education, community, social impact |
| `economic` | Finance, markets, business tools |
| `environmental` | Climate, sustainability, energy |
| `technological` | Dev tools, infrastructure, AI/ML |
| `creative` | Art, music, content, design |
| `health` | Medical, wellness, biotech |
| `legal` | Compliance, contracts, justice |

```
# Single domain
python -m xbrain ideate --domains health

# Multiple domains
python -m xbrain ideate --domains health technology legal
```

Without `--domains`, all nine domains are scanned.

### `--constraints` — Add requirements

Force ideas to meet specific conditions.

```
python -m xbrain ideate --constraints "must work offline"

python -m xbrain ideate --constraints "must be free" "must work on mobile" "no login required"
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

## Cost

Each run makes 3-4 API calls. Approximate cost per run with Haiku: **$0.02–$0.10**.
