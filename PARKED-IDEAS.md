# xBrain — Parked Improvement Ideas

Ideas from cross-run analysis of 61 self-improvement ideas across 9 pipeline runs. These are improvements that scored well but require more investment or external dependencies. Parked here for future reference.

---

## Tier 2 — Medium Investment (require new infrastructure or moderate prompt engineering)

### 1. Assumption Dependency Mapping
Build a dependency graph between key assumptions within each idea. If assumption A depends on assumption B being true, and B is flagged fragile, A inherits that fragility. Currently assumptions are scored independently — this would surface cascading risk.

**Estimated effort:** ~80 lines across prompts.py + ideate.py + output.py
**Why parked:** Requires significant CONVERGE prompt changes and a graph data structure in models.py. Medium-complexity prompt engineering to teach the LLM to identify dependency edges between assumptions.

### 2. Micro-GTM Validator
After CONVERGE, add a lightweight phase that generates a 1-paragraph go-to-market test for each idea's first customer profile. Tests whether the ICP is reachable through the proposed distribution channel. Currently the ICP and distribution channel are generated but never validated against each other.

**Estimated effort:** ~100 lines (new phase + prompt + output section)
**Why parked:** Adds a new LLM call per run (~$0.01-0.02 cost increase). Needs careful prompt design to avoid generic advice. Would benefit from web search grounding to find actual communities/channels.

### 3. Domain-Aware Scoring Weights
Different domains should weight scoring dimensions differently. A healthcare idea should weight ethical_risk higher; a developer tool should weight defensibility lower. Currently all ideas use the same 8-dimension weights regardless of domain.

**Estimated effort:** ~60 lines in config.py + ideate.py
**Why parked:** Needs a domain→weight mapping that's hard to get right without empirical data. Risk of over-fitting to assumptions about what matters in each domain.

---

## Tier 3 — High Investment (require significant architecture changes or external services)

### 4. Outcome Tracking & Feedback Loop
Track which ideas actually get built and whether they succeed. Create a feedback mechanism where users can report "I built idea X and it worked/failed because Y." This closes the loop: META-LEARN could incorporate real-world outcomes, not just LLM-assessed verdicts.

**Estimated effort:** New module + CLI commands + persistence layer
**Why parked:** Requires user behavior change (manually reporting outcomes). No way to automate. The feedback data would be extremely valuable but sparse — most ideas never get built.

### 5. Multi-Source Signal Intelligence
Go beyond DuckDuckGo + HackerNews. Add Reddit API, ProductHunt, GitHub trending, patent databases, and academic paper search. Use these signals to ground ideas in actual market demand signals before scoring.

**Estimated effort:** New search providers + API key management + rate limiting
**Why parked:** Each new source needs an API key (cost), rate limiting, parsing, and relevance filtering. Reddit and ProductHunt APIs have changed frequently. The existing 2-source approach (DuckDuckGo + HN) provides 80% of the value.

### 6. Multi-Agent Debate Architecture
Replace single-LLM stress testing with a multi-agent setup: one agent attacks, a different agent defends, a third judges. Different LLM models or temperatures for attacker vs. defender. Would produce higher-fidelity verdicts because the defender isn't the same "mind" that generated the attack.

**Estimated effort:** Major refactor of stress test + LLM client changes
**Why parked:** Triples stress test cost. Requires orchestrating multiple concurrent LLM sessions. The current single-round attack already produces good verdicts — diminishing returns.

### 7. Idea Portfolio Optimization
After scoring, optimize the final selection not just by individual score but by portfolio diversity: maximize total expected value while minimizing correlation risk. If idea A and idea B both depend on the same market trend, selecting both is risky.

**Estimated effort:** ~150 lines (portfolio optimization algorithm + correlation detection)
**Why parked:** Requires defining "correlation" between ideas, which is hard to quantify. Meaningful only when selecting 5+ ideas for parallel execution — most users pick 1-2.

### 8. Automated Brief Enhancement
Before running the pipeline, analyze the user's brief for gaps: missing target audience, unclear constraints, vague problem statement. Suggest specific questions the user should answer to improve the brief, or auto-enrich with web search context.

**Estimated effort:** New pre-pipeline phase + prompt + CLI interaction
**Why parked:** The borderline between "helpful suggestion" and "annoying nag" is thin. Users who write good briefs don't need this; users who write bad briefs might not know how to answer the questions. Could be a simple `--analyze-brief` flag instead.

---

## Previously Implemented (from self-improvement runs)

These ideas from the analysis have already been implemented:

- **Kill-Reason Pre-Filter** → v1.17.0 (this release)
- **Attack Pattern Recycling into Evolve** → v1.17.0
- **Cost Tracking in Memory** → v1.17.0
- **Effort-Diversity Enforcement** (strengthened) → v1.17.0
- **Confidence-Weighted Scoring** → v1.17.0
- **Parallel Multi-Prompt Diverge** → v1.17.0
- **Stress Test Fidelity Monitor** (enhanced) → v1.17.0
- **Calibration Enforcement Layer** → v1.6.0
- **Stress Test Crash Tagging** → v1.6.0
- **Failure Blocklist** → v1.6.0
- **Adaptive Stress Weighting** → v1.13.0
- **Technique Weight Adaptation** → v1.13.0
- **Multi-Generation Evolution** → v1.13.0
- **Idea Genes & Recombination** → v1.13.0
