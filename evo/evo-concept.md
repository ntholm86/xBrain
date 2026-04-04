# evo — Autonomous Software Evolution Engine

## What Is It?

`evo` is a CLI tool that improves codebases autonomously. You point it at a git repo, tell it what "better" means (tests, coverage, lint score, benchmark times), and it runs a loop: analyze the code, propose improvements, implement them on a branch, verify nothing regressed, and merge if the change is provably better. Every iteration is documented with before/after metrics and an immutable proof trail.

It is a practical Gödel machine: a system that rewrites code only when it can prove the rewrite is an improvement. Not through formal mathematical proofs — through empirical evidence: tests pass, coverage went up, benchmarks didn't regress, linter score improved.

## The Core Loop

```
┌─────────────────────────────────────────────┐
│                 .evo.yaml                   │
│  (project config: what to run, what to      │
│   measure, what counts as "better")         │
└──────────────────┬──────────────────────────┘
                   │
           ┌───────▼───────┐
           │   1. ANALYZE   │  Read codebase. Run metrics. Find weaknesses.
           └───────┬───────┘  (coverage gaps, lint warnings, slow tests,
                   │           missing docs, architectural debt)
           ┌───────▼───────┐
           │   2. PROPOSE   │  LLM generates candidate improvements.
           └───────┬───────┘  (bug fixes, refactors, new tests, perf
                   │           optimizations, documentation)
           ┌───────▼───────┐
           │  3. IMPLEMENT  │  Create git branch. Apply changes. Commit.
           └───────┬───────┘
                   │
           ┌───────▼───────┐
           │   4. VERIFY    │  Run tests, linters, benchmarks, type checks.
           └───────┬───────┘  Compare before/after metrics quantitatively.
                   │
           ┌───────▼───────┐
           │   5. DECIDE    │  Improved? → Merge to master.
           └───────┬───────┘  Regressed? → Discard branch.
                   │           Uncertain? → Flag for human review.
           ┌───────▼───────┐
           │   6. RELEASE   │  Create release branch from master.
           └───────┬───────┘  Build + test again. Deploy if green.
                   │           If red → revert master, mark dead end.
           ┌───────▼───────┐
           │   7. EVOLVE    │  Record what worked. Adjust strategy.
           └───────┴───────┘  Feed into next iteration. Loop.
```

Each iteration produces a **proof ledger entry** — an immutable record with before/after metrics, the diff, and the verdict. This is not a log. It is evidence.

### How the Hard Steps Work

**ANALYZE** cannot read an entire codebase — context windows have limits. Instead, ANALYZE is *metric-driven*: run all metric commands first, then read only the files that surfaced as weak (low coverage, lint warnings, type errors). Metrics act as an attention allocator. This means evo's improvement trajectory follows its metrics: if you only measure coverage, evo only finds coverage gaps. The breadth of `.evo.yaml` metrics determines the breadth of improvements.

**IMPLEMENT** is the highest-risk step. The approach: LLM receives the full content of target files (within `max_files_per_change`), the proposal description, and the metric data. It outputs complete replacement files. A compile/build check runs immediately inside the same Docker sandbox used by VERIFY — if it fails, the LLM gets the error and retries (up to 3 attempts). If it still fails, the proposal is discarded. No partial edits, no diff-patching, no line-number guessing. Whole-file replacement is crude but reliable. Sophistication comes later, gated by merge-rate data.

### When IMPLEMENT Fails

Every implementation happens on a throwaway git branch. This is not a safety feature bolted on — it's the reason the system can be aggressive. `master` is never at risk.

**The retry cascade:**

```
IMPLEMENT attempt 1
  └─ compile/build check
       ├─ PASS → continue to VERIFY
       └─ FAIL → feed compiler error to LLM
            └─ attempt 2 (same context + error output)
                 ├─ PASS → continue to VERIFY
                 └─ FAIL → feed new error to LLM
                      └─ attempt 3 (same context + both errors)
                           ├─ PASS → continue to VERIFY
                           └─ FAIL → abandon proposal
```

Retry prompts are cheap and effective. The LLM already has the full file context loaded — appending a compiler error adds ~200 tokens. The error message is the most precise feedback an LLM can get: exact file, exact line, exact problem. Retry success rate on build failures is high because most LLM build errors are syntax mistakes or missing imports, not fundamental logic problems.

**When all retries fail:**

1. **Branch stays.** Don't delete it. Git branches are pointers, not storage. Zero cost.
2. **Proof ledger records the failure:**
   ```json
   {
     "iteration": 14,
     "prev_hash": "c9f1a2...",
     "timestamp": "2026-03-22T10:45:00Z",
     "verdict": "BUILD_FAILED",
     "branch": "evo/iter-014-refactor-config",
     "proposal": "Refactor config loader to use dataclasses",
     "attempts": 3,
     "final_error": "TypeError: expected str, got Optional[str] at line 42",
     "cost_usd": 0.63,
     "proposal_category": "refactor",
     "entry_hash": "e4a7b3..."
   }
   ```
3. **EVOLVE learns from it.** If 80% of "refactor" proposals fail to build, PROPOSE deprioritizes refactors on the next iteration. Failure data is training data.

**Cost of failure:** A failed iteration with 3 retries costs ~2x a successful one (the retries send truncated prompts — context is already loaded, only the error is new). Under `max_cost_per_run`, failures eat into the budget and evo stops when it's exhausted. You don't burn unlimited money on an LLM that can't implement what it proposed.

**What about tests that pass but behavior is wrong?** That's not a build failure — that's a *test gap*. If the test suite doesn't catch incorrect behavior, evo has no way to know. This is by design: evo is exactly as safe as your test suite is thorough. Mutation testing (`mutmut`) helps close this gap by ensuring tests actually detect faults, not just execute code paths.

## The Vision

Most AI coding tools generate code and hope for the best. `evo` closes the feedback loop. It doesn't just write code — it *proves the code is better*, merges it, and learns from the outcome to make better proposals next time.

The end state is a system that:

1. **Improves any codebase you point it at** — given a git repo and a `.evo.yaml` config, it autonomously finds and executes improvements, limited only by what the test suite and metrics can verify.

2. **Improves itself** — `evo`'s own code is a git repo with tests, coverage, and benchmarks. Point `evo` at itself. If it proposes an improvement to its own analysis engine and that improvement passes all tests and metrics, it merges. The tool that makes code better *becomes the code that gets made better*.

3. **Accumulates knowledge across repos** — patterns that work (e.g., "adding property-based tests to data validation code always improves robustness") become **metric genomes** that transfer to new projects. Cross-pollination of improvement strategies.

This is not AGI. It is not sentient. It is an automated version of what a disciplined engineer already does: analyze, branch, improve, test, merge, document. The LLM provides the creative proposals; the test suite provides the objective verification; git provides the safety net.

## The Contract: `.evo.yaml`

Every project `evo` operates on has a config file that defines what "better" means:

```yaml
# .evo.yaml — the project's evolution contract
project: my-app
language: python

# Commands evo can run to measure the codebase
metrics:
  test:     "pytest --tb=short"
  coverage: "pytest --cov=src --cov-report=json"
  lint:     "ruff check src/"
  typecheck: "mypy src/"
  benchmark: "pytest benchmarks/ --benchmark-json=bench.json"
  mutation: "mutmut run --paths-to-mutate=src/"  # optional: detects weak tests

# What counts as "better" — all must hold for a merge
improvement_criteria:
  - tests_pass: true              # non-negotiable
  - coverage: ">= previous"      # never decrease
  - lint_errors: "<= previous"   # never increase
  - mutation_score: ">= previous" # tests must detect real bugs, not just run
  - benchmark: "statistical"      # Welch's t-test over N runs, not thresholds

# Safety & budget
max_files_per_change: 5           # scope limit per iteration
max_cost_per_run: 5.00            # USD — stop when budget exhausted
allowed_scopes:                   # what evo is allowed to touch
  - "src/**"
  - "tests/**"
  - "docs/**"
blocked_scopes:                   # what evo must never touch
  - ".evo.yaml"                   # can't rewrite its own rules
  - "migrations/**"               # too dangerous
  - "requirements*.txt"           # dependency changes need human review
  - "**/package.json"             # same
  - "Cargo.toml"                  # same

# Sandbox for running tests (Docker isolation)
sandbox:
  image: "python:3.12-slim"       # base image
  setup: "pip install -r requirements.txt"
  # or: dockerfile: ".evo.Dockerfile"

# Human approval gates — where the human gets a lever
approval_gates:
  merge: true                     # confirm before merging to master
  propose: false                  # review proposals before implementing
  risk_escalation: true           # confirm when diff risk classifier triggers
  self_modify: true               # confirm when evo targets its own code
  # autonomy: full                # uncomment to disable ALL gates (demo mode)
```

The contract is the guardrail. `evo` cannot redefine what "better" means — that stays under human control.

## The Proof Ledger

Every iteration produces an immutable JSON entry:

```json
{
  "iteration": 14,
  "prev_hash": "b7e2d4...",
  "timestamp": "2026-03-22T10:30:00Z",
  "branch": "evo/iter-014-add-edge-case-tests",
  "proposal": "Add edge case tests for empty input handling in parser module",
  "metrics_before": {
    "tests": 142, "coverage": 84.2, "lint_errors": 3
  },
  "metrics_after": {
    "tests": 148, "coverage": 86.7, "lint_errors": 3
  },
  "delta": {
    "tests": "+6", "coverage": "+2.5%", "lint_errors": "0"
  },
  "files_changed": ["tests/test_parser.py"],
  "verdict": "MERGE",
  "reason": "All metrics improved or held. Coverage +2.5%. No regressions.",
  "cost_usd": 0.42,
  "diff_hash": "a3f8c1...",
  "entry_hash": "c9f1a2..."
}
```

Each entry includes `prev_hash` (hash of the previous entry) and `entry_hash` (hash of the current entry including `prev_hash`). This creates a hash chain — any tampering breaks the chain and is detectable. Not blockchain, just the same integrity primitive: append-only by construction.

Cost tracking per iteration (`cost_usd`) lets operators calculate cost-per-merge and stop when ROI goes negative.

## Self-Improvement (The Gödel Machine Aspect)

This is what makes `evo` different from "AI code assistant that makes PRs."

Phase 1: **External only.** `evo` improves *other* repos. This is already useful and validates the core loop without risk.

Phase 2: **Self-targeting.** Point `evo` at its own repository. Now `evo`'s analysis engine, proposal generator, and verification logic are all targets for improvement. If `evo` proposes a better prompt for its ANALYZE phase and that change results in higher-quality proposals (measured by merge rate on benchmark repos), it merges the improvement into itself.

The safety mechanism: a **benchmark canary suite** — a set of known repos with known improvement opportunities. Before any self-modification merges, `evo` runs the modified version against these canaries. If the new version performs worse than the old version on the canaries, the self-modification is rejected. This prevents Goodhart's Law (optimizing a metric until it stops meaning what you think it means).

**The attribution problem:** when evo changes one component (e.g., its ANALYZE prompt) and measures end-to-end merge rate, did merge rate improve because ANALYZE got better, or because the new phrasing accidentally biased PROPOSE toward easier changes? Solution: controlled comparison. Run old-evo and new-evo on the *same* canary repos with the *same* proposals where possible, isolating the changed component. A/B testing, not end-to-end assumption.

This is empirical self-improvement, like AlphaGo's self-play. Not formal mathematical proof like Gödel's original concept. But it's practical, measurable, and falsifiable.

## EVOLVE (What Happens After Each Iteration)

EVOLVE is the feedback loop that makes evo get smarter over time, not just repeat the same strategy. It runs after every iteration — successful or failed.

**What EVOLVE does concretely:**

1. **Write proof ledger entry.** Every iteration gets a hash-chained entry recording the proposal, metrics, verdict, cost, and branch. This is the raw data everything else feeds on.

2. **Update category success rates.** Track merge rate per proposal category (test additions, lint fixes, refactors, etc.). If test additions merge 60% of the time but refactors merge 15%, PROPOSE weights the next iteration toward test additions. This is the mechanism behind the expected merge rates — not hardcoded, learned from the repo's own history.

3. **Update failure patterns.** If BUILD_FAILED, record which category, which files, and which error type. If 3 out of 4 refactors targeting `parser.py` failed to build, deprioritize proposals touching that file for refactoring (but not for test additions — those might still work).

4. **Detect convergence.** Check rolling merge rate over the last N iterations. If below the floor (default 10%) for 10+ iterations, signal convergence and stop.

5. **Feed metric genomes.** Successful patterns (trigger conditions + proposal category + outcome) are candidates for the gene library. EVOLVE doesn't create genes directly — genes emerge from aggregate patterns across many EVOLVE entries.

**What EVOLVE does NOT do:** It doesn't modify evo's own code (that's self-improvement, Phase 5). It adjusts *strategy* — which categories to propose, which files to target, when to stop — within the same codebase run.

## Approval Gates (Human Control)

evo has four points where a human can pull a lever. Each is independently configurable in `.evo.yaml`.

| Gate | When it fires | Default | Why it exists |
|---|---|---|---|
| `merge` | Before merging a verified improvement to master | **on** | Merge is the point of no return. The human sees the diff, the proof ledger entry, and the before/after metrics, then approves or rejects. |
| `propose` | Before implementing a proposal | off | Lets the human veto bad ideas before compute is spent. Useful during trust-building. |
| `risk_escalation` | When the diff risk classifier triggers | **on** | Changes touching auth/crypto/serialization patterns get flagged regardless of other settings. |
| `self_modify` | When evo targets its own codebase | **on** | Self-modification is the highest-stakes operation. Default: always ask. |

**Demo mode:** Set `autonomy: full` to disable all gates. evo runs the complete loop — analyze, propose, implement, verify, merge, release branch — without any human interaction. Branches appear, commits land on master, release branches accumulate, all visible in real time on GitHub. Useful for live demonstrations: share your screen, point evo at a repo, and watch it work.

**Normal mode:** `merge: true` is the recommended minimum. evo does all the work — you just confirm the final merge. This is the "autopilot with seatbelt" configuration: the system drives, you approve lane changes.

## What It Is Not

- **Not a code generator.** It doesn't write apps from scratch. It makes existing code measurably better. Feature generation is architecturally possible but deliberately deferred — scope constraints keep the MVP focused.
- **Not a chat assistant.** No conversation. A pipeline: in goes a repo, out come verified improvements.
- **Not magic.** It can only improve what it can *measure*. No tests? Nothing to verify against. Bad metrics? Bad improvements. The quality ceiling is the quality of your test suite and benchmarks.
- **Not unsupervised by default.** Merge, risk escalation, and self-modification require human approval out of the box. Full autonomy is opt-in, not default.

## Expected Merge Rates

Realistic expectations for what percentage of evo's proposals will actually pass verification and merge:

| Category | Expected merge rate | Why |
|---|---|---|
| Test additions | 40–60% | Well-scoped, low risk, LLMs are good at test generation |
| Lint fixes | 70–90% | Mechanical, deterministic, hard to get wrong |
| Documentation | 50–70% | Low risk but subjective quality varies |
| Dead code removal | 60–80% | Lint-detected, but false positives exist |
| Refactors | 15–30% | Multi-file changes, subtle breakage |
| Performance | 10–20% | Benchmarks are noisy, optimizations are hard |

A system that merges 30% of proposals overall is already valuable. The 70% that fail cost only API credits — they're discarded on their branches, zero harm to the codebase. As LLMs improve, merge rates go up automatically. As metric genomes accumulate, evo targets higher-probability proposals first.

## Built-In Defenses

Five design-level protections against known failure modes. These are not optional features — they are structural properties of the system.

### Statistical Verification (not arbitrary thresholds)
**Problem:** Single-run benchmarks are noisy. A "5% regression threshold" is arbitrary and either too strict (blocks valid changes due to random variance) or too loose (lets real regressions through).
**Solution:** VERIFY runs metrics N times, compares before/after *distributions* using Welch's t-test ($p < 0.05$). Rejects only statistically significant regressions. No arbitrary thresholds. This is how science works — evo should work the same way.

### Mutation Testing as a First-Class Metric
**Problem:** Coverage is gameable. Adding `assert True` increases coverage without improving correctness. A system that optimizes for coverage will learn to generate trivial tests.
**Solution:** Mutation testing (e.g., `mutmut`) injects small bugs into source code and checks if tests catch them. Mutation score measures whether tests actually *detect* faults, not just *execute* code. If evo adds a trivial test, mutation score stays flat → no improvement → no merge. Metric gaming structurally eliminated.

### Diff Risk Classifier
**Problem:** Automated edits touching auth, crypto, serialization, or input validation could introduce security vulnerabilities that pass all tests. Tests verify correctness, not security.
**Solution:** DECIDE phase pattern-matches every diff against a hardcoded risk lexicon (`password`, `secret`, `token`, `auth`, `eval`, `exec`, `deserialize`, `SQL`, `CORS`, `certificate`, etc.). Any match fires the `risk_escalation` approval gate. In normal mode this pauses for human review. In demo mode (`autonomy: full`) it logs the risk flag in the proof ledger but proceeds — the audit trail records that the risk was detected even if no human was present.

### Category Scoping (progressive trust)
**Problem:** Complex refactors and performance optimizations have low merge rates and high risk. Starting with these wastes compute and erodes trust in the system.
**Solution:** Phase 1 locks PROPOSE to high-signal, low-risk categories only:
- **Test additions** — highest signal, lowest risk
- **Lint fixes** — mechanical, always safe
- **Documentation** — zero regression risk
- **Dead code removal** — lint-detected, safe

Complex refactors, performance changes, and feature additions unlock in later phases, gated by proven merge-rate data from earlier categories.

### Convergence Detection
**Problem:** As metrics approach their ceiling (95% coverage, 0 lint errors, high mutation score), the space of Pareto-improving changes shrinks to near-zero. Without detection, evo burns API credits proposing changes that all get rejected.
**Solution:** Track rolling merge rate over the last N iterations. If merge rate drops below a configurable floor (default: 10%) for 10+ consecutive iterations, evo reports "convergence reached" and stops. The codebase has reached its measurably improvable limit — a feature, not a failure.

## Metric Genomes (Cross-Repo Learning)

As the proof ledger accumulates entries across repos, patterns emerge. Metric genomes are those patterns, extracted and ranked:

```json
{
  "gene": "add-edge-case-tests-for-parsing",
  "trigger": "coverage < 80% AND module_has_parser",
  "success_rate": 0.83,
  "avg_coverage_delta": "+4.2%",
  "repos_tested": 12,
  "failure_mode": "breaks when parser uses streaming input"
}
```

**How they work:** After N proof ledger entries, evo groups merged proposals by category and trigger conditions. Patterns with high success rates become genes. When evo runs on a new repo, it checks which genes' triggers match the codebase and proposes those first — highest-probability improvements before novel exploration.

**How they evolve:** New genes emerge when the LLM proposes a novel improvement that succeeds. Genes that stop working (because codebases or LLMs evolve) see their success rates decay and are eventually pruned. This is the open-ended evolution aspect — the gene library grows organically, never converging to a fixed set.

## CLI Interface

```
evo init                    # Create .evo.yaml in current repo
evo analyze                 # Run metrics, report weaknesses
evo run                     # Execute one improvement iteration
evo run --iterations 5      # Run 5 iterations
evo run --dashboard         # Run with web dashboard on :8420
evo status                  # Show proof ledger summary
evo history                 # Full proof ledger
evo cleanup --older-than 30d  # Prune dead-end branches
```

## Git Strategy

evo's git operations are plumbing, not intelligence. They should be reliable and boring. Master is production. Every merge triggers a release. True continuous deployment.

**The full lifecycle:**

```
master ──────●──────────●──────────●──── master (production)
            ╱          ╱          ╱
           ╱   ┌──────╱──────────╱── release/20260322-103000-01
          ╱   ╱      ╱              release/20260322-104500-01
         ╱   ╱      ╱
  evo/iter-014 ●──●──●  (work branch, squash-merged)
  evo/iter-015 ●──● DEAD END  (failed, marked)
  evo/iter-016 ●──●──●  (work branch, squash-merged)
```

### Work branches

1. **Branch from master.** Always. Every iteration starts from the latest `master`. Name: `evo/iter-{N}-{slug}`.
2. **Commit per attempt.** Each IMPLEMENT attempt gets its own commit. The branch shows the work, including retries with build errors.
3. **Squash-merge on success.** Verified improvements land as one clean commit on `master` with a meaningful message. The branch preserves the messy reality; master shows the polished result.

### Failed branches: mark and learn

Failed branches stay. They're pointers, not storage — zero cost. But unlike silent abandonment, evo makes the failure *visible*:

```
git commit --allow-empty -m "DEAD END: BUILD_FAILED after 3 attempts — TypeError: expected str, got Optional[str] in parser.py"
```

When anyone browses the branch list on GitHub, the latest commit message on each `evo/` branch immediately tells the story: either a successful squash-merge reference, or a `DEAD END:` with the reason. No need to dig into the proof ledger to understand what happened. The proof ledger has the full details; the commit message is the headline.

Optional: `evo cleanup --older-than 30d` prunes dead-end branches for repos that care about branch hygiene. Never deletes branches that were merged.

### Release branches: continuous deployment

Every squash-merge to master triggers a release attempt:

1. **Create release branch:** `release/{timestamp}-{sequence}` (e.g., `release/20260322-103000-01`). Branched from the merge commit on master.
2. **Build + test on release branch.** Full metric suite runs again — identical commands from `.evo.yaml`. This is the *real* deployment gate. VERIFY on the work branch was a pre-filter; the release branch test is proof that the merged state of master is deployable.
3. **Tests pass → deployable.** The release branch is the deployment artifact. Logged in the proof ledger, ready for deployment (or auto-deployed, depending on the target repo's CD pipeline).
4. **Tests fail → revert master, mark release as dead end.** See below.

**When the release branch fails:**

This *should not happen* — VERIFY already passed these tests on the work branch. But it can: flaky tests, environment drift, a race condition with another push. When it does, master has a bad commit. The fix:

```
# 1. Revert the merge commit on master (new commit, no history rewriting)
git checkout master
git revert --no-edit <merge-commit-hash>
# Commit message: "Revert evo/iter-014: release branch tests failed — test_parser.py::test_edge_case FAILED"

# 2. Mark the release branch as dead end
git checkout release/20260322-103000-01
git commit --allow-empty -m "DEAD END: RELEASE_FAILED — test_parser.py::test_edge_case FAILED after merge to master. Master reverted."

# 3. Mark the work branch too
git checkout evo/iter-014-add-edge-case-tests
git commit --allow-empty -m "DEAD END: RELEASE_FAILED — passed VERIFY but failed on release branch. Reverted from master."
```

**Why `git revert`, not `git reset`?** Revert creates a new commit — append-only, no history rewriting. Anyone who already pulled master sees the revert as a normal commit. `reset --hard` would rewrite history, which violates the safety rules and breaks anyone who pulled between merge and reset.

**Cost:** A release failure costs one iteration of wasted compute plus the revert. But the proof ledger records the full story — `RELEASE_FAILED` verdict with the merge hash, the revert hash, and the test output. This data is valuable: if release failures cluster around a specific test or module, ANALYZE can flag it as a flaky zone and PROPOSE can avoid it.

**Proof ledger entry for a release failure:**
```json
{
  "iteration": 14,
  "prev_hash": "c9f1a2...",
  "timestamp": "2026-03-22T10:50:00Z",
  "verdict": "RELEASE_FAILED",
  "branch": "evo/iter-014-add-edge-case-tests",
  "release_branch": "release/20260322-103000-01",
  "proposal": "Add edge case tests for empty input handling in parser module",
  "merge_hash": "a3f8c1...",
  "revert_hash": "d7b2e9...",
  "failure": "test_parser.py::test_edge_case — AssertionError: expected 'foo', got None",
  "note": "Passed VERIFY on work branch. Failed on release branch. Likely flaky test or environment drift.",
  "cost_usd": 0.71,
  "entry_hash": "f2d8c5..."
}
```

**Why release branches, not tags?** Branches are visible in GitHub's branch dropdown. During a demo, you see `release/20260322-103000-01`, `release/20260322-104500-01`, `release/20260322-110000-01` accumulating in real time. Every improvement evo merges produces a release. Tags work too, but branches are more visible for the audience. Failed release branches stay with their `DEAD END:` commit — visible proof that the system caught the problem and self-corrected.

**Sequence number (`-01`):** Handles the case where two iterations merge in the same second. In practice this won't happen (evo runs sequentially), but the format is defensive.

### Merge conflicts

If `master` moved while evo was working (another developer pushed, or a previous iteration just merged), the branch may conflict. evo doesn't resolve conflicts — it discards the branch (with a `DEAD END: MERGE_CONFLICT` commit) and re-proposes from the new `master`. Conflict resolution is a creative act that requires understanding both sides. Cheaper to re-propose on the new baseline than to have the LLM guess at a merge.

### Safety rules

- **No force-push, no rebase of master.** evo never rewrites shared history. Reverts are new commits, not history edits.
- **Master is always deployable.** Only squash-merges from verified branches. If a release branch fails, the merge is reverted immediately — master never stays broken.
- **Release branches are immutable.** Once created, never modified. They're snapshots — even failed ones stay as evidence.
- **Not in evo's improvement scope.** Git operations are in `blocked_scopes` alongside `.evo.yaml`. There's no metric for "is this merge strategy better?" and a bad change could corrupt the working tree or break the release pipeline. Get it right once, leave it alone.

## Technology

- **Python** — LLM API latency (10-60s per call) is the bottleneck, not local compute. Python iterates fastest for prompt engineering.
- **Git** — all changes on branches. Squash-merge only on verified improvement. Full rollback always available.
- **Claude API** — for ANALYZE, PROPOSE, and IMPLEMENT phases. Structured JSON output for reliable parsing.
- **Docker** — sandbox containers for running target repo tests. Isolation, reproducibility, portability.

**Language-agnostic, with a caveat.** VERIFY is truly language-agnostic — it runs whatever commands `.evo.yaml` specifies inside a Docker container. PROPOSE depends on the LLM's competence in the target language. Python, TypeScript, Rust, Go — strong proposals. Niche languages — proposal quality drops. evo is language-agnostic in *verification*, LLM-bound in *proposal quality*.

## Runtime Architecture

evo has three components. Locally they run via `docker compose`. In Azure they run as container apps. Same containers, same behavior, different host.

```
┌─────────────────────────────────────────────────────────────┐
│  evo orchestrator (Python)                                  │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐   │
│  │ANALYZE │→│PROPOSE │→│IMPLMNT │→│ VERIFY │→│ DECIDE │   │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘   │
│      │                      │         │          │         │
│      │ LLM API              │ git     │ docker   │ git     │
│      ▼                      ▼         ▼          ▼         │
│  Claude API           GitHub remote sandbox  proof ledger  │
│                                       ▲                    │
│             RELEASE + EVOLVE ─────────┘ (also use sandbox) │
│                                                             │
│  ┌─────────────────────────┐  ┌──────────────────────────┐  │
│  │  Terminal UI (Rich)     │  │  Web dashboard (:8420)   │  │
│  │  (operator view)        │  │  (demo/audience view)    │  │
│  └─────────────────────────┘  └──────────────────────────┘  │
└───────────────────────┬─────────────────────────────────────┘
                        │ docker run (per iteration)
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  sandbox container (ephemeral)                              │
│                                                             │
│  Target repo clone + dependencies                           │
│  Runs: pytest, ruff, mypy, benchmarks, mutmut              │
│  Returns: exit codes + structured metric output             │
│  Destroyed after each VERIFY cycle                          │
└─────────────────────────────────────────────────────────────┘
```

### Live Feedback: Terminal UI

The operator running evo sees a Rich TUI in the terminal — live panels, not scrolling logs:

```
┌─ evo iter-014 ─────────────────────────────────────────────┐
│ Phase: VERIFY ██████████░░░░░░░░░░  tests running (47s)    │
│ Proposal: Add edge case tests for parser empty input       │
│ Category: test_addition                                    │
│ Branch: evo/iter-014-add-edge-case-tests                   │
│ Attempt: 1/3                                               │
├─ Metrics ──────────────────────────────────────────────────┤
│ tests:      142 → running...    coverage: 84.2% → ...      │
│ lint_errors: 3  → ...           mutation:  71%  → ...       │
├─ This Run ─────────────────────────────────────────────────┤
│ Iterations: 3/5   Merged: 2   Failed: 1   Cost: $1.47     │
│ Merge rate: 66%   Budget remaining: $3.53                  │
├─ Recent ───────────────────────────────────────────────────┤
│ ✓ iter-012  lint fixes in utils/       +0 coverage  $0.31  │
│ ✓ iter-013  tests for auth module      +3.1% cov   $0.42  │
│ ✗ iter-011  refactor config loader     BUILD_FAILED $0.74  │
└────────────────────────────────────────────────────────────┘
```

This replaces scrolling text with a live dashboard. Current phase, current proposal, attempt count, metrics updating in real time, running cost, recent history. The operator sees everything without needing to check git or the proof ledger.

### Live Feedback: Web Dashboard

For demos and remote observation. A lightweight web server (FastAPI + WebSocket) built into evo, served on port 8420.

**What it shows:**
- Current loop phase with elapsed time
- Current proposal and branch name
- Live metric comparison (before → after, updating as VERIFY runs)
- Proof ledger as a scrollable timeline — each entry shows verdict (green ✓ / red ✗), delta, cost
- Running totals: merge rate, total cost, iterations completed
- Git activity feed: branches created, merges, release branches, dead ends

**What it doesn't do:**
- No controls. The dashboard is read-only. Approval gates are handled via the terminal UI (locally) or via API webhook (Azure).
- No auth in Phase 1. It's a local dashboard. Azure deployment puts it behind Azure AD.

**Demo setup:** Share two browser tabs on Teams — the evo dashboard and the GitHub repo page. Colleagues see evo working in real time on the left, and branches/commits appearing on GitHub on the right.

### Docker: Sandbox Isolation

VERIFY must not run the target repo's tests directly on the machine running evo. Reasons:
- **Safety.** The target repo's tests could do anything — delete files, make network calls, spawn processes. The sandbox contains the blast radius.
- **Reproducibility.** Same Docker image = same environment, local and Azure. No "works on my machine" discrepancies between VERIFY on the work branch and tests on the release branch.
- **Cleanup.** Container is destroyed after each VERIFY. No leftover state from one iteration polluting the next.

**How it works:**

`.evo.yaml` specifies the Docker image for the sandbox:

```yaml
sandbox:
  image: "python:3.12-slim"       # base image
  setup: "pip install -r requirements.txt"  # run once per container
  # or:
  dockerfile: ".evo.Dockerfile"   # custom Dockerfile in the target repo
```

For each VERIFY cycle:
1. evo starts a container from the sandbox image
2. Mounts the work branch checkout (read-only source + writable test output directory)
3. Runs `setup` command (install deps)
4. Runs all metric commands from `.evo.yaml`
5. Collects exit codes and structured output (coverage JSON, benchmark JSON, etc.)
6. Container is destroyed

**Caching:** Dependency installation is slow. Two mitigations:
- **Layer caching:** If using `.evo.Dockerfile`, Docker layer cache means `pip install` only re-runs when `requirements.txt` changes. Most iterations won't change dependencies (they're in `blocked_scopes`).
- **Pre-built sandbox image:** For repos with heavy dependencies, pre-build a sandbox image with deps installed. `.evo.yaml` points to it. VERIFY just runs tests — no install step.

**Release branch testing** uses the same sandbox image and process. Same environment = if it passed VERIFY, it should pass release. Failures indicate genuine environmental issues, not "different pip version" noise.

### Azure Deployment

For demos and long-running autonomous operation. evo runs in Azure, targets a GitHub repo, colleagues watch via URL.

```
┌───────────────────────────────────────────────────┐
│  Azure Container App                              │
│                                                   │
│  evo orchestrator container                       │
│   ├─ Web dashboard (:8420, behind Azure AD)       │
│   ├─ Proof ledger → Azure Blob Storage            │
│   └─ Metric genomes → Azure Blob Storage          │
│                                                   │
│  Sandbox sidecar / Azure Container Instance       │
│   └─ Ephemeral per VERIFY cycle                   │
│                                                   │
│  Secrets (Azure Key Vault):                       │
│   ├─ ANTHROPIC_API_KEY                            │
│   ├─ GITHUB_TOKEN (repo push access)              │
│   └─ (no other secrets needed)                    │
│                                                   │
│  Storage (Azure Blob):                            │
│   ├─ proof-ledger/{repo}/ledger.json              │
│   └─ metric-genomes/genes.json                    │
└───────────────────────────────────────────────────┘
```

**What Azure gives us:**
- **Persistent runtime.** evo can run 50 iterations overnight. You check the dashboard in the morning and see what it did.
- **Shared dashboard.** Colleagues open the URL, authenticate via Azure AD, watch evo work. No screen sharing required.
- **Cost visibility.** Azure Container Apps bills by vCPU-second. Combined with evo's own `cost_usd` tracking (LLM API spend), you get total cost: infrastructure + API.
- **Scaling to zero.** When evo isn't running, the container app scales to zero. No idle cost.

**What to prep for Azure (do during Phase 1):**
- Proof ledger read/write abstracted behind a storage interface (local file vs. Azure Blob). Don't hardcode file paths.
- Dashboard served as a built-in web server, not a separate deployment.
- Git operations use `GITHUB_TOKEN` env var, not SSH keys or credential helpers. Tokens work everywhere.
- All config via environment variables or `.evo.yaml` — no Azure-specific config files.
- Docker socket access: the orchestrator container needs to spin up sandbox containers. Azure Container Apps supports sidecar containers; alternatively, use Azure Container Instances spawned via API.

**`docker-compose.yml` for local development:**

```yaml
services:
  evo:
    build: .
    ports:
      - "8420:8420"           # web dashboard
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # to spawn sandbox containers
      - ./proof-ledger:/data/proof-ledger
      - ./metric-genomes:/data/metric-genomes
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - EVO_TARGET_REPO=https://github.com/user/target-repo.git
      - EVO_STORAGE=local        # 'local' or 'azure-blob'
```

Run `docker compose up`, open `localhost:8420`, watch evo work. Same experience as Azure, different host.

## One Sentence

`evo` is `git bisect` in reverse — instead of finding which commit broke things, it finds which commit *improves* things, and makes that commit for you.
