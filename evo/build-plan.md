# evo — Build Plan

## Phase 1: The Minimal Loop + Infrastructure

The goal: one complete iteration end-to-end, with all infrastructure wired from day one.

**Core loop:**
- `evo init` — scaffold `.evo.yaml` in target repo
- `evo analyze` — run metric commands, identify weaknesses, send to LLM
- `evo run` — one iteration: ANALYZE → PROPOSE → IMPLEMENT → VERIFY → DECIDE → RELEASE → EVOLVE
- Proof ledger with hash chain from the first entry

**Git strategy (from day one):**
- Work branches: `evo/iter-{N}-{slug}`, squash-merge on success
- Failed branches: `DEAD END:` commit, stay forever
- Release branches: `release/{timestamp}-{seq}`, created on every merge to master
- Release branch tests: full metric suite, revert master on failure
- No force-push, no rebase of master

**Docker sandbox:**
- IMPLEMENT compile checks and VERIFY run inside Docker containers
- `.evo.yaml` `sandbox:` config (image + setup, or custom Dockerfile)
- Container destroyed after each VERIFY cycle
- Dependency layer caching

**Feedback:**
- Terminal TUI (Rich) — live panels: current phase, metrics, cost, recent history
- Web dashboard (FastAPI + WebSocket, `:8420`) — read-only, for demos and remote observation
- `evo status` and `evo history` for proof ledger inspection

**Azure prep (abstraction, not deployment):**
- Storage interface: local file vs Azure Blob (proof ledger, metric genomes)
- Git auth via `GITHUB_TOKEN` env var
- `docker-compose.yml` for local dev
- All config via env vars or `.evo.yaml`

**Scope:** Point it at a simple Python repo with pytest. One metric (tests pass). One proposal category (test additions). Prove the loop works.

## Phase 2: Multi-Metric + EVOLVE Intelligence

Expand beyond "tests pass" to coverage, lint score, type checking, mutation testing. Proof ledger entries gain before/after deltas across all metrics.

- Pareto-dominant merge criteria: merge only if *no* metric got worse and *at least one* improved
- Statistical verification (Welch's t-test) for benchmark metrics
- EVOLVE tracks category success rates and adjusts PROPOSE weighting
- Convergence detection: stop when merge rate drops below floor
- Diff risk classifier: pattern-match diffs against risk lexicon
- Category scoping: lock PROPOSE to safe categories (tests, lint, docs, dead code)

## Phase 3: External-Only MVP

Run `evo` on real open-source repos. Measure merge rate. This is product validation.

- If merge rate >30%, the loop works
- If <10%, proposal quality needs work — iterate on ANALYZE/PROPOSE prompts
- Approval gates operational: merge, propose, risk_escalation, self_modify
- Demo mode (`autonomy: full`) tested end-to-end with live dashboard
- Azure deployment: Container App + Key Vault + Blob Storage

## Phase 4: Metric Genomes

Patterns from the proof ledger become transferable knowledge.

- Gene extraction from aggregate EVOLVE entries across repos
- Trigger matching on new repos (coverage thresholds, module types, etc.)
- Gene success rate tracking and decay/pruning
- "Repos with low coverage respond best to test-generation proposals"
- "Refactoring proposals have 2x the merge rate of feature proposals"

## Phase 5: Self-Improvement

Point `evo` at itself. Benchmark canary suite gates all self-modifications.

- evo's own repo has tests, coverage, benchmarks
- Canary suite: fixed set of repos with known improvement opportunities
- A/B testing: run old-evo and new-evo on same canaries, isolate changed component
- `self_modify` approval gate on by default — human reviews self-modifications
- The tool improves the tool
