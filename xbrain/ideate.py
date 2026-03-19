"""Pipeline 1: IDEATE — the main orchestrator for idea generation."""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from xbrain.config import Config
from xbrain.llm import LLMClient
from xbrain.memory import MemoryStore
from xbrain.models import (
    AttackResponse,
    DebateExchange,
    DefenseResponse,
    DomainBrief,
    FeasibilityMatrix,
    IdeaCard,
    IdeateRunResult,
    Persona,
    RawIdea,
    RebuttalResponse,
    ScoreBreakdown,
    StressTestResult,
    compute_composite_score,
)
from xbrain.output import generate_idea_report
from xbrain.prompts import (
    ADVERSARIAL_DEFENSE_SYSTEM,
    ADVERSARIAL_DEFENSE_USER,
    ADVERSARIAL_REBUTTAL_SYSTEM,
    ADVERSARIAL_REBUTTAL_USER,
    CONSTRAINT_CHECK_SYSTEM,
    CONSTRAINT_CHECK_USER,
    CONVERGE_SYSTEM,
    CONVERGE_USER,
    DEDUP_SYSTEM,
    DEDUP_USER,
    DIVERGE_GAPFILL_SYSTEM,
    DIVERGE_GAPFILL_USER,
    DIVERGE_SYSTEM,
    DIVERGE_USER,
    IMMERSE_SYSTEM,
    IMMERSE_USER,
    META_LEARN_SYSTEM,
    META_LEARN_USER,
    STRESS_TEST_SYSTEM,
    STRESS_TEST_USER,
    build_brief_context,
    build_calibration_context,
    build_constraint_context,
    build_domain_context,
    build_immersion_context,
    build_memory_context,
    build_playbook_context,
    build_refinement_context,
)


def _log(tag: str, msg: str) -> None:
    line = f"[{tag:<9s}] {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))
    sys.stdout.flush()


def _log_phase_header(phase: str, description: str) -> None:
    """Print a visible phase separator for console readability."""
    print()
    print(f"{'=' * 60}")
    print(f"  {phase}: {description}")
    print(f"{'=' * 60}")
    sys.stdout.flush()


# ------------------------------------------------------------------
# LLM response helpers
# ------------------------------------------------------------------

def _unwrap_single(data: dict | list, wrapper_key: str, idea_id: str, phase: str) -> dict:
    """Extract a single-item result from an LLM JSON response.

    The prompts ask for ``{wrapper_key: [item, ...]}``, but when
    ``candidate_count=1`` the LLM sometimes returns the item directly
    without the wrapper array.  This helper handles both shapes and
    always returns a plain dict suitable for Pydantic validation.
    """
    if isinstance(data, list):
        # Rare: LLM returned a bare list
        item = data[0] if data else {}
        _log("STRESS", f"  [unwrap] {phase}/{idea_id}: bare list (len={len(data)})")
    elif wrapper_key in data:
        items = data[wrapper_key]
        item = items[0] if items else {}
    else:
        # LLM omitted the wrapper — the dict IS the item
        item = data
        _log("STRESS", f"  [unwrap] {phase}/{idea_id}: wrapper '{wrapper_key}' missing, using raw dict")

    if isinstance(item, dict):
        item.setdefault("idea_id", idea_id)
    return item


_ANGLE_KEYWORDS = [
    "prior", "adoption", "technical", "reframe",
    "externali", "obsolesc", "timing", "defensib", "expertise",
]


def _coerce_str(item) -> str:
    """Coerce an LLM value to a plain string.

    The LLM sometimes returns dicts (e.g. {"point": "...", "opportunity": "..."})
    where a plain string is expected.  Join all values into one string.
    """
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return "; ".join(str(v) for v in item.values() if v)
    return str(item)


def _match_exchange(exchanges: list, idx: int):
    """Match a defense/rebuttal exchange to an attack by position.

    Accepts either a list of Pydantic models (with .angle) or dicts.
    Uses index-based matching (prompts list attacks in order), with a
    keyword fallback for robustness when the LLM reorders items.
    Returns the matched item or None.
    """
    if not exchanges:
        return None

    def _get_angle(ex) -> str:
        return (getattr(ex, "angle", None) or (ex.get("angle", "") if isinstance(ex, dict) else "")).lower()

    # Skip any leading freeform-defense entry
    offset = 0
    if "freeform" in _get_angle(exchanges[0]):
        offset = 1

    adj = idx + offset
    if adj < len(exchanges):
        return exchanges[adj]

    # Keyword fallback
    kw = _ANGLE_KEYWORDS[idx] if idx < len(_ANGLE_KEYWORDS) else ""
    if kw:
        for ex in exchanges:
            if kw in _get_angle(ex):
                return ex

    return None


class IdeatePipeline:
    """Runs the full IDEATE pipeline: Immerse → Diverge → Converge → Stress Test."""

    def __init__(
        self,
        config: Config | None = None,
        llm: LLMClient | None = None,
        memory: MemoryStore | None = None,
    ):
        self.cfg = config or Config()
        self.memory = memory or MemoryStore(self.cfg.memory_dir / "persistent")
        if llm:
            self.llm = llm
        else:
            if not self.cfg.api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key."
                )
            self.llm = LLMClient(self.cfg.api_key, self.cfg.model, self.cfg.max_tokens)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        domains: list[str] | None = None,
        constraints: list[str] | None = None,
        brief_text: str | None = None,
        language: str | None = None,
    ) -> Path:
        """Execute the full ideation pipeline and return the run directory."""
        self._language = language
        run_id = self._make_run_id(brief_text)
        run_dir = self.cfg.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.monotonic()
        _log("IDEATE", f"Pipeline 1 started.  Run ID: {run_id}")
        if brief_text:
            preview = brief_text[:120] + ("..." if len(brief_text) > 120 else "")
            _log("IDEATE", f"Brief: {preview}")
        if domains:
            _log("IDEATE", f"Focus domains: {', '.join(domains)}")
        if constraints:
            _log("IDEATE", f"Constraints: {', '.join(constraints)}")
        if language:
            _log("IDEATE", f"Language: {language}")
        if self.cfg.model_strategy != "single":
            _log("IDEATE", f"Model strategy: {self.cfg.model_strategy}")

        # Cost estimate
        estimate = self.estimate_cost(
            model=self.cfg.model,
            ideas_per_round=self.cfg.ideas_per_round,
            converge_top_n=self.cfg.converge_top_n,
            has_domains=bool(domains),
            has_constraints=bool(constraints),
            pricing=self.cfg.MODEL_PRICING,
            strategy=self.cfg.model_strategy,
            cheap_model=self.cfg.cheap_model,
        )
        _log("IDEATE", f"Estimated cost: ${estimate['total_est_cost_usd']:.4f}")

        result = IdeateRunResult(
            run_id=run_id,
            domains=domains or [],
            constraints=constraints or [],
        )

        # Phase -1 — Meta-Learn (distill playbook if enough runs accumulated)
        self._maybe_distill_playbook()

        # Phase -0.5 — Constraint Conflict Check
        if constraints and len(constraints) >= 2:
            self._phase_check_constraints(constraints)

        # Phase 0 — Immerse (optional)
        domain_briefs: list[DomainBrief] = []
        if domains:
            _log_phase_header("IMMERSE", f"Deep-diving into {', '.join(domains)}")
            tp = time.monotonic()
            domain_briefs = self._phase_immerse(domains)
            _log("IMMERSE", f"done in {time.monotonic() - tp:.0f}s")
            result.domain_briefs = domain_briefs

        # Phase 1 — Diverge
        _log_phase_header("DIVERGE", "Generating raw idea seeds")
        tp = time.monotonic()
        raw_ideas = self._phase_diverge(domains, constraints, domain_briefs, brief_text)
        result.raw_ideas = raw_ideas

        # Phase 1b — Dedup + Gap Analysis
        raw_ideas, gaps, overrepresented = self._phase_dedup(raw_ideas)

        # Phase 1c — Gap-Fill Divergence (multi-turn)
        if gaps:
            gap_ideas = self._phase_diverge_gapfill(
                gaps, overrepresented, raw_ideas, domains, brief_text
            )
            if gap_ideas:
                raw_ideas.extend(gap_ideas)
                result.raw_ideas = raw_ideas
        _log("DIVERGE", f"done in {time.monotonic() - tp:.0f}s")

        # Phase 2 — Converge
        _log_phase_header("CONVERGE", f"Scoring and ranking {len(raw_ideas)} ideas")
        tp = time.monotonic()
        candidates = self._phase_converge(raw_ideas)
        _log("CONVERGE", f"done in {time.monotonic() - tp:.0f}s")
        result.candidates = candidates

        # Phase 3 — Stress Test
        _log_phase_header("STRESS TEST", f"Adversarial debate for {len(candidates)} candidates")
        tp = time.monotonic()
        stress_results = self._phase_stress_test(candidates)
        _log("STRESS", f"done in {time.monotonic() - tp:.0f}s")
        result.stress_test_results = stress_results

        # Merge stress results into candidates to produce survivors
        survivors = self._merge_survivors(candidates, stress_results)
        result.survivors = survivors

        # Check if any ideas survived with BUILD verdict — if not, trigger iterative refinement loop
        build_count = sum(1 for s in stress_results if s.verdict == "BUILD")
        refinement_round = 0
        max_refinement_rounds = 3
        refinement_error = None

        # Pre-build context once for all refinement rounds
        _cached_ctx: dict[str, str] | None = None
        
        try:
            while build_count == 0 and refinement_round < max_refinement_rounds:
                refinement_round += 1
                _log("IDEATE", f"")
                _log("IDEATE", f"Refinement Round {refinement_round}/{max_refinement_rounds}: No BUILD verdicts found. Extracting learnings...")

                if _cached_ctx is None:
                    _cached_ctx = {
                        "domain": build_domain_context(domains, self.cfg.DEFAULT_DOMAINS),
                        "constraint": build_constraint_context(constraints),
                        "memory": build_memory_context(
                            self.memory.past_idea_count(),
                            self.memory.get_domain_heat_map(),
                            self.memory.killed_idea_titles(),
                        ),
                        "immersion": build_immersion_context(
                            [b.model_dump() for b in domain_briefs] if domain_briefs else None
                        ),
                        "brief": build_brief_context(brief_text),
                    }

                # Run refinement phase
                refinement_survivors = self._phase_refine(
                    raw_ideas, survivors, stress_results, domains, constraints, domain_briefs, brief_text,
                    iteration=refinement_round,
                    cached_context=_cached_ctx,
                )
                
                if not refinement_survivors:
                    _log("REFINE", "  No refined candidates generated. Stopping refinement loop.")
                    break
                
                # Re-run stress test on refined ideas
                refinement_stress = self._phase_stress_test(refinement_survivors)
                
                # Merge refinement survivors and stress results into the result
                result.survivors.extend(refinement_survivors)
                result.stress_test_results.extend(refinement_stress)
                
                # Re-merge to update verdicts
                survivors = self._merge_survivors(survivors + refinement_survivors, result.stress_test_results)
                result.survivors = survivors
                
                # Check for BUILD verdicts in this refinement round
                build_count = sum(1 for s in refinement_stress if s.verdict == "BUILD")
                mutate_count = sum(1 for s in refinement_stress if s.verdict == "MUTATE")
                kill_count = sum(1 for s in refinement_stress if s.verdict == "KILL")
                
                _log("IDEATE", f"  Refinement round {refinement_round} results: {build_count} BUILD, {mutate_count} MUTATE, {kill_count} KILL")
                
                if build_count > 0:
                    _log("IDEATE", f"  ✓ SUCCESS: {build_count} idea(s) passed all quality gates!")
                    break
                elif refinement_round < max_refinement_rounds:
                    _log("IDEATE", f"  → Will continue refining ({refinement_round}/{max_refinement_rounds})")
            
            if build_count == 0 and refinement_round >= max_refinement_rounds:
                _log("IDEATE", f"")
                _log("IDEATE", f"Reached maximum refinement rounds ({max_refinement_rounds}). Proceeding with {len(survivors)} candidates.")
        
        except Exception as e:
            refinement_error = e
            _log("IDEATE", f"")
            _log("IDEATE", f"⚠ Refinement error after round {refinement_round}: {str(e)}")
            _log("IDEATE", f"Proceeding with round {refinement_round} results.")

        # Token totals
        result.total_input_tokens = self.llm.total_input_tokens
        result.total_output_tokens = self.llm.total_output_tokens

        # Deduplicate stress test results to match deduplicated survivors
        survivor_ids = {c.id for c in result.survivors}
        seen_stress_ids: set[str] = set()
        unique_stress: list[StressTestResult] = []
        for st in result.stress_test_results:
            if st.idea_id in survivor_ids and st.idea_id not in seen_stress_ids:
                seen_stress_ids.add(st.idea_id)
                unique_stress.append(st)
        result.stress_test_results = unique_stress

        # Write outputs (do this BEFORE any other processing to ensure files exist)
        try:
            self._write_outputs(run_dir, result)
            _log("IDEATE", f"✓ Outputs written to {run_dir}/")
        except Exception as write_error:
            _log("IDEATE", f"✗ Failed to write outputs: {write_error}")
            if refinement_error:
                raise refinement_error  # Raise refinement error if outputs failed
            else:
                raise write_error

        # Persist to memory
        self._update_memory(result)

        # ── Completion Summary ─────────────────────────────────────────
        cost_info = self.actual_cost()
        final_build = sum(1 for s in result.stress_test_results if s.verdict == "BUILD")
        final_mutate = sum(1 for s in result.stress_test_results if s.verdict == "MUTATE")
        final_kill = sum(1 for s in result.stress_test_results if s.verdict == "KILL")
        final_incubate = sum(1 for s in result.stress_test_results if s.verdict == "INCUBATE")

        sorted_survivors = sorted(result.survivors, key=lambda c: c.composite_score, reverse=True)

        print()
        print("=" * 60)
        print("  xBrain Pipeline Complete")
        print("=" * 60)
        print()
        print(f"  Ideas generated:  {len(result.raw_ideas)}")
        print(f"  After scoring:    {len(result.candidates)}")
        print(f"  Verdicts:         {final_build} BUILD  |  {final_mutate} MUTATE  |  {final_kill} KILL  |  {final_incubate} INCUBATE")
        if refinement_round > 0:
            print(f"  Refinement:       {refinement_round} round(s)")
        print()

        if sorted_survivors:
            print("  Top ideas:")
            for i, c in enumerate(sorted_survivors[:5]):
                verdict = c.stress_test_verdict or "?"
                emoji = {"BUILD": "+", "MUTATE": "~", "KILL": "x", "INCUBATE": "?"}.get(verdict, " ")
                print(f"    [{emoji}] #{i+1}  {c.composite_score:.1f}  {c.title}")
            print()

        print(f"  Output directory: {run_dir}")
        print(f"    idea-report.md           Human-readable ranked report")
        print(f"    idea-cards.json          Machine-readable Idea Cards")
        print(f"    idea-log.json            Full pipeline trace")
        print(f"    stress-test-report.json  Adversarial debate results")
        print()
        elapsed = time.monotonic() - t0
        mins, secs = divmod(int(elapsed), 60)
        print(f"  Elapsed: {mins}m {secs}s")
        print(f"  Tokens:  {result.total_input_tokens:,} in / {result.total_output_tokens:,} out")
        print(f"  Cost:    ${cost_info['total_cost_usd']:.4f}")
        print()

        if final_build > 0:
            best = next((c for c in sorted_survivors if c.stress_test_verdict == "BUILD"), sorted_survivors[0])
            print(f"  Next step:")
            print(f"    python -m xbrain specify --idea {run_dir}/idea-cards.json --select {best.id}")
        else:
            print(f"  No BUILD verdicts. Review MUTATE ideas or re-run with different constraints.")

        print()
        sys.stdout.flush()

        return run_dir

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    def _maybe_distill_playbook(self) -> None:
        """Run meta-learning distillation every 3 runs to compress learnings."""
        runs_since = self.memory.runs_since_last_distill()
        if runs_since < 3:
            return  # Not enough new data to justify distillation

        _log("META", f"Distilling playbook from {runs_since} new runs...")

        # Gather compact data for distillation
        score_history = self.memory.get_score_history_compact()
        if not score_history:
            return

        kill_log = self.memory.get_kill_log()
        kill_reasons = [
            k.get("reason", "")[:80] for k in kill_log[-10:]
        ]
        attack_patterns = self.memory.get_attack_patterns()
        domain_heat = self.memory.get_domain_heat_map()
        total_runs = len(self.memory.get_meta_metrics())

        # Compact score→verdict string: "7.5→M, 6.8→K, 8.1→B"
        score_verdicts = ", ".join(
            f"{sv['s']}→{sv['v'][0] if sv.get('v') else '?'}" for sv in score_history[-30:]
        )

        prompt = META_LEARN_USER.format(
            run_count=total_runs,
            score_verdicts=score_verdicts,
            kill_reasons="; ".join(kill_reasons[:5]),
            attack_patterns="; ".join(
                p.get("pattern", "")[:60] for p in (attack_patterns or [])[:5]
            ),
            domain_heat=json.dumps(domain_heat),
        )

        data = self.llm.generate_json(
            META_LEARN_SYSTEM, prompt, temperature=0.3,
            model_override=self._model_for_phase("meta"), phase="meta",
            max_tokens=2048,
        )

        playbook = data.get("playbook", "")
        calibration = data.get("score_calibration", {})

        if playbook:
            self.memory.save_playbook(playbook, total_runs)
            _log("META", f"  Playbook distilled ({len(playbook)} chars)")

        if calibration:
            self.memory.save_score_calibration(calibration)
            bias = calibration.get("bias_direction", "?")
            weak = calibration.get("weak_dimensions", [])
            _log("META", f"  Score calibration: bias={bias}, weak={weak}")

        anti_patterns = data.get("anti_patterns", [])
        if anti_patterns:
            _log("META", f"  Anti-patterns: {'; '.join(anti_patterns[:3])}")

    def _phase_check_constraints(self, constraints: list[str]) -> None:
        """Detect contradictions in user-specified constraints before running the pipeline."""
        _log("CONSTCHK", f"Checking {len(constraints)} constraints for conflicts...")

        prompt = CONSTRAINT_CHECK_USER.format(
            constraint_count=len(constraints),
            constraints_list="\n".join(f"- {c}" for c in constraints),
        )

        try:
            data = self.llm.generate_json(
                CONSTRAINT_CHECK_SYSTEM, prompt, temperature=0.2,
                model_override=self._model_for_phase("constraints"), phase="constraints",
                max_tokens=1024,
            )

            conflicts = data.get("conflicts", [])
            if conflicts:
                _log("CONSTCHK", f"  ⚠ {len(conflicts)} conflict(s) detected:")
                for conflict in conflicts:
                    pair = conflict.get("constraints", [])
                    reason = conflict.get("reason", "")
                    suggestion = conflict.get("suggestion", "")
                    _log("CONSTCHK", f"    CONFLICT: {' vs '.join(pair)}")
                    _log("CONSTCHK", f"      Why: {reason}")
                    if suggestion:
                        _log("CONSTCHK", f"      Fix: {suggestion}")
                _log("CONSTCHK", "  Proceeding anyway — constraints will be applied as-is.")
            else:
                _log("CONSTCHK", "  ✓ No conflicts detected.")
        except Exception as e:
            _log("CONSTCHK", f"  Skipped (error: {e})")

    def _phase_immerse(self, domains: list[str]) -> list[DomainBrief]:
        _log("IMMERSE", f"Deep-diving into: {', '.join(domains)}")

        prompt = IMMERSE_USER.format(domains=", ".join(domains))
        data = self.llm.generate_json(
            self._sys(IMMERSE_SYSTEM), prompt, temperature=0.6,
            model_override=self._model_for_phase("immerse"), phase="immerse",
            max_tokens=4096,
        )
        briefs_raw = data.get("domain_briefs", [])

        briefs = []
        for b in briefs_raw:
            # Normalize list-of-str fields: LLM sometimes returns dicts instead of strings
            for key in ("pressure_points", "key_tensions", "underserved_populations",
                        "regulatory_windows", "technology_gaps"):
                if key in b:
                    b[key] = [_coerce_str(item) for item in b[key]]
            briefs.append(DomainBrief(**b))
            _log("IMMERSE", f"  {b.get('domain','?').upper()}: {len(b.get('pressure_points',[]))} pressure points")

        _log("IMMERSE", f"Domain briefs generated for {len(briefs)} domains.")
        return briefs

    def _phase_diverge(
        self,
        domains: list[str] | None,
        constraints: list[str] | None,
        domain_briefs: list[DomainBrief],
        brief_text: str | None = None,
    ) -> list[RawIdea]:
        _log("DIVERGE", f"Round 1/{self.cfg.diverge_rounds} — generating raw idea seeds...")

        domain_ctx = build_domain_context(domains, self.cfg.DEFAULT_DOMAINS)
        constraint_ctx = build_constraint_context(constraints)
        memory_ctx = build_memory_context(
            self.memory.past_idea_count(),
            self.memory.get_domain_heat_map(),
            self.memory.killed_idea_titles(),
        )
        immersion_ctx = build_immersion_context(
            [b.model_dump() for b in domain_briefs] if domain_briefs else None
        )
        brief_ctx = build_brief_context(brief_text)

        prompt = DIVERGE_USER.format(
            idea_count=self.cfg.ideas_per_round,
            domain_context=domain_ctx,
            constraint_context=constraint_ctx,
            memory_context=memory_ctx,
            immersion_context=immersion_ctx,
            brief_context=brief_ctx,
            playbook_context=build_playbook_context(self.memory.get_playbook()),
        )

        data = self.llm.generate_json(
            self._sys(DIVERGE_SYSTEM), prompt, temperature=0.9,
            model_override=self._model_for_phase("diverge"), phase="diverge",
            max_tokens=10240,
        )
        ideas_raw = data.get("ideas", [])

        ideas = []
        for item in ideas_raw:
            ideas.append(RawIdea(**item))

        # Summarise techniques used
        techniques = {}
        for idea in ideas:
            techniques[idea.source_technique] = techniques.get(idea.source_technique, 0) + 1
        tech_str = ", ".join(f"{k} ({v})" for k, v in techniques.items())
        _log("DIVERGE", f"  {len(ideas)} raw idea seeds generated.")
        _log("DIVERGE", f"  Techniques: {tech_str}")

        return ideas

    def _phase_dedup(
        self, raw_ideas: list[RawIdea],
    ) -> tuple[list[RawIdea], list[str], list[str]]:
        """Semantic deduplication: collapse near-identical ideas, identify gaps."""
        if len(raw_ideas) < 4:
            return raw_ideas, [], []

        _log("DEDUP", f"Analyzing {len(raw_ideas)} ideas for duplicates...")

        ideas_json = json.dumps(
            [{"id": i.id, "concept": i.concept, "domain_tags": i.domain_tags}
             for i in raw_ideas],
            indent=2, ensure_ascii=False,
        )

        prompt = DEDUP_USER.format(
            idea_count=len(raw_ideas),
            ideas_json=ideas_json,
        )

        data = self.llm.generate_json(
            self._sys(DEDUP_SYSTEM), prompt, temperature=0.2,
            model_override=self._model_for_phase("dedup"), phase="dedup",
            max_tokens=2048,
        )

        keep_ids = set(data.get("keep", [i.id for i in raw_ideas]))
        removed = data.get("remove", [])
        gaps = data.get("gap_areas", [])
        overrepresented = data.get("overrepresented_themes", [])

        if removed:
            _log("DEDUP", f"  Removed {len(removed)} duplicates:")
            for r in removed[:3]:
                _log("DEDUP", f"    - {r.get('id', '?')} ≈ {r.get('duplicate_of', '?')}: {r.get('reason', '')[:60]}")

        if overrepresented:
            _log("DEDUP", f"  Over-represented: {'; '.join(overrepresented[:3])}")

        if gaps:
            _log("DEDUP", f"  Gaps found: {'; '.join(gaps[:3])}")

        filtered = [i for i in raw_ideas if i.id in keep_ids]
        _log("DEDUP", f"  {len(raw_ideas)} → {len(filtered)} unique ideas")

        return filtered, gaps, overrepresented

    def _phase_diverge_gapfill(
        self,
        gaps: list[str],
        overrepresented: list[str],
        existing_ideas: list[RawIdea],
        domains: list[str] | None,
        brief_text: str | None,
    ) -> list[RawIdea]:
        """Multi-turn divergence: generate new ideas to fill gaps from round 1."""
        # Cap at half of original idea count to keep total manageable
        gap_count = min(len(gaps) + 2, max(3, self.cfg.ideas_per_round // 2))
        _log("DIVERGE", f"Round 2 — gap-filling {len(gaps)} gaps with {gap_count} new ideas...")

        prompt = DIVERGE_GAPFILL_USER.format(
            idea_count=gap_count,
            brief_context=build_brief_context(brief_text),
            domain_context=build_domain_context(domains, self.cfg.DEFAULT_DOMAINS),
            playbook_context=build_playbook_context(self.memory.get_playbook()),
            overrepresented="; ".join(overrepresented),
            gaps="; ".join(gaps),
            previous_titles="; ".join(i.concept[:60] for i in existing_ideas[:10]),
        )

        data = self.llm.generate_json(
            self._sys(DIVERGE_GAPFILL_SYSTEM), prompt, temperature=0.95,
            model_override=self._model_for_phase("gapfill"), phase="gapfill",
            max_tokens=8192,
        )

        ideas_raw = data.get("ideas", [])
        gap_ideas = [RawIdea(**item) for item in ideas_raw]

        _log("DIVERGE", f"  Gap-fill generated {len(gap_ideas)} new ideas")
        if gap_ideas:
            techniques = {}
            for idea in gap_ideas:
                techniques[idea.source_technique] = techniques.get(idea.source_technique, 0) + 1
            _log("DIVERGE", f"  Techniques: {', '.join(f'{k} ({v})' for k, v in techniques.items())}")

        return gap_ideas

    def _phase_converge(self, raw_ideas: list[RawIdea]) -> list[IdeaCard]:
        _log("CONVERGE", f"Clustering and scoring {len(raw_ideas)} ideas...")

        # Send only essential fields to keep prompt compact
        ideas_compact = [
            {"id": i.id, "concept": i.concept, "domain_tags": i.domain_tags,
             "source_technique": i.source_technique}
            for i in raw_ideas
        ]
        ideas_json = json.dumps(ideas_compact, indent=2, ensure_ascii=False)

        calibration_ctx = build_calibration_context(self.memory.get_score_stats())

        prompt = CONVERGE_USER.format(
            idea_count=len(raw_ideas),
            top_n=self.cfg.converge_top_n,
            ideas_json=ideas_json,
            calibration_context=calibration_ctx,
        )

        data = self.llm.generate_json(self._sys(CONVERGE_SYSTEM), prompt, temperature=0.5,
                                       model_override=self._model_for_phase("converge"), phase="converge",
                                       max_tokens=12288)

        clustering = data.get("clustering_summary", "")
        if clustering:
            _log("CONVERGE", f"  Clustering: {clustering[:120]}")

        candidates_raw = data.get("candidates", [])
        candidates = []
        for c in candidates_raw:
            card = self._parse_candidate(c)
            candidates.append(card)

        # Sort by composite score descending
        candidates.sort(key=lambda c: c.composite_score, reverse=True)

        _log("CONVERGE", f"  {len(candidates)} candidates scored.  (UNCALIBRATED)")
        for i, c in enumerate(candidates[:5]):
            _log("CONVERGE", f"  #{i+1} [{c.composite_score:.1f}] \"{c.title}\"")
            _log("CONVERGE", f"       Domains: {', '.join(c.domain_tags)}")
            if c.primary_persona.who:
                _log("CONVERGE", f"       Persona: {c.primary_persona.who}")
            if c.primary_persona.pain:
                _log("CONVERGE", f"       Pain: {c.primary_persona.pain[:80]}")

        return candidates

    def _phase_stress_test(self, candidates: list[IdeaCard]) -> list[StressTestResult]:
        _log("STRESS", f"Adversarial debate for {len(candidates)} candidates (parallel)...")
        _log("STRESS", "")

        # Build per-idea compact dicts once (slim: no persona/score_breakdown to save tokens)
        compact_by_id: dict[str, dict] = {}
        for c in candidates:
            compact_by_id[c.id] = {
                "id": c.id,
                "title": c.title,
                "rationale": c.rationale,
                "domain_tags": c.domain_tags,
            }

        # Slim version for defense/rebuttal (no full persona/score breakdown)
        slim_by_id: dict[str, dict] = {}
        for c in candidates:
            slim_by_id[c.id] = {
                "id": c.id,
                "title": c.title,
                "composite_score": c.composite_score,
                "domain_tags": c.domain_tags,
            }

        stress_model = self._model_for_phase("stress")
        sys_attack = self._sys(STRESS_TEST_SYSTEM)
        sys_defense = self._sys(ADVERSARIAL_DEFENSE_SYSTEM)
        sys_rebuttal = self._sys(ADVERSARIAL_REBUTTAL_SYSTEM)

        # ── Round 1: Devil's Advocate attacks (parallel across ideas) ──
        _log("STRESS", f"Round 1/3 — Devil's Advocate attacking ({len(candidates)} parallel calls)...")

        async def _attack_one(c: IdeaCard) -> AttackResponse:
            cj = json.dumps([compact_by_id[c.id]], ensure_ascii=False)
            prompt = STRESS_TEST_USER.format(candidate_count=1, candidates_json=cj)
            try:
                data = await self.llm.generate_json_async(
                    sys_attack, prompt, temperature=0.4,
                    model_override=stress_model, phase="stress-attack",
                    max_tokens=4096,
                )
                raw = _unwrap_single(data, "results", c.id, "attack")
                return AttackResponse.model_validate(raw)
            except (ValueError, Exception) as e:
                _log("STRESS", f"  [WARN] Attack failed for {c.id}: {e}")
                return AttackResponse(idea_id=c.id, freeform_attack="(attack failed)", structured_attacks=[], verdict="INCUBATE")

        attack_results = self._run_parallel([_attack_one(c) for c in candidates])

        for ar in attack_results:
            title = next((c.title for c in candidates if c.id == ar.idea_id), ar.idea_id)
            _log("STRESS", f"  {title}")
            _log("STRESS", f"    Freeform: {ar.freeform_attack[:100]}")
            for atk in ar.structured_attacks[:3]:
                _log("STRESS", f"    - {atk[:90]}")
            if len(ar.structured_attacks) > 3:
                _log("STRESS", f"    ... and {len(ar.structured_attacks) - 3} more attacks")

        # ── Round 2: Idea Champion defends (parallel, slim context) ────
        _log("STRESS", "")
        _log("STRESS", f"Round 2/3 — Idea Champion defending ({len(candidates)} parallel calls)...")

        async def _defend_one(ar: AttackResponse) -> DefenseResponse:
            slim_json = json.dumps([slim_by_id.get(ar.idea_id, {"id": ar.idea_id})], ensure_ascii=False)
            atk_json = json.dumps([{
                "idea_id": ar.idea_id,
                "freeform_attack": ar.freeform_attack,
                "structured_attacks": ar.structured_attacks,
            }], ensure_ascii=False)
            prompt = ADVERSARIAL_DEFENSE_USER.format(
                candidate_count=1, candidates_json=slim_json, attacks_json=atk_json,
            )
            try:
                data = await self.llm.generate_json_async(
                    sys_defense, prompt, temperature=0.4,
                    model_override=stress_model, phase="stress-defense",
                    max_tokens=6144,
                )
                raw = _unwrap_single(data, "defenses", ar.idea_id, "defense")
                return DefenseResponse.model_validate(raw)
            except (ValueError, Exception) as e:
                _log("STRESS", f"  [WARN] Defense failed for {ar.idea_id}: {e}")
                return DefenseResponse(idea_id=ar.idea_id, exchanges=[])

        defenses_list = self._run_parallel([_defend_one(ar) for ar in attack_results])

        defense_map: dict[str, DefenseResponse] = {}
        for d in defenses_list:
            defense_map[d.idea_id] = d
            title = next((c.title for c in candidates if c.id == d.idea_id), d.idea_id)
            _log("STRESS", f"  {title}")
            for ex in d.exchanges[:3]:
                _log("STRESS", f"    [{ex.outcome:>8s}] {ex.angle}: {ex.defense[:80]}")
            if len(d.exchanges) > 3:
                _log("STRESS", f"    ... and {len(d.exchanges) - 3} more defenses")

        # ── Round 3: Judge runs rebuttal round + verdict (parallel, slim context) ──
        _log("STRESS", "")
        _log("STRESS", f"Round 3/3 — Final rebuttals and verdict ({len(candidates)} parallel calls)...")

        async def _rebuttal_one(ar: AttackResponse) -> RebuttalResponse:
            slim_json = json.dumps([slim_by_id.get(ar.idea_id, {"id": ar.idea_id})], ensure_ascii=False)
            def_resp = defense_map.get(ar.idea_id)
            def_exchanges = [ex.model_dump() for ex in def_resp.exchanges] if def_resp else []
            debate = json.dumps([{
                "idea_id": ar.idea_id,
                "attacks": ar.structured_attacks,
                "freeform_attack": ar.freeform_attack,
                "defenses": def_exchanges,
            }], ensure_ascii=False)
            prompt = ADVERSARIAL_REBUTTAL_USER.format(
                candidate_count=1, candidates_json=slim_json, debate_json=debate,
            )
            try:
                data = await self.llm.generate_json_async(
                    sys_rebuttal, prompt, temperature=0.3,
                    model_override=stress_model, phase="stress-rebuttal",
                    max_tokens=8192,
                )
                raw = _unwrap_single(data, "results", ar.idea_id, "rebuttal")
                return RebuttalResponse.model_validate(raw)
            except (ValueError, Exception) as e:
                _log("STRESS", f"  [WARN] Rebuttal failed for {ar.idea_id}: {e}")
                return RebuttalResponse(idea_id=ar.idea_id, exchanges=[], verdict="INCUBATE")

        rebuttal_list = self._run_parallel([_rebuttal_one(ar) for ar in attack_results])
        rebuttal_map: dict[str, RebuttalResponse] = {r.idea_id: r for r in rebuttal_list}

        # ── Assemble final StressTestResults ───────────────────────────

        results: list[StressTestResult] = []
        for ar in attack_results:
            idea_id = ar.idea_id
            defense_info = defense_map.get(idea_id)
            rebuttal_info = rebuttal_map.get(idea_id)

            # Build debate rounds from all three phases
            debate_rounds: list[DebateExchange] = []
            defense_exchanges = defense_info.exchanges if defense_info else []
            rebuttal_exchanges = rebuttal_info.exchanges if rebuttal_info else []

            # Standard attack angles
            angles = [
                "Prior art", "Adoption failure", "Technical blocker",
                "Problem reframe", "Negative externalities", "Obsolescence",
                "Timing", "Defensibility", "Expertise gap",
            ]

            for i, attack_text in enumerate(ar.structured_attacks):
                angle = angles[i] if i < len(angles) else f"Attack {i+1}"

                dex = _match_exchange(defense_exchanges, i)
                rex = _match_exchange(rebuttal_exchanges, i)

                debate_rounds.append(DebateExchange(
                    angle=angle,
                    attack=attack_text,
                    defense=dex.defense if dex else "",
                    attacker_rebuttal=rex.attacker_rebuttal if rex else "",
                    defender_rebuttal=rex.defender_rebuttal if rex else "",
                    outcome=(
                        (rex.final_outcome if rex and rex.final_outcome else "")
                        or (dex.outcome if dex else "")
                    ),
                ))

            # Use rebuttal verdict as source of truth, fall back to attack data
            fm_raw = (
                rebuttal_info.feasibility_matrix if rebuttal_info and rebuttal_info.feasibility_matrix
                else ar.feasibility_matrix
            ) or {}
            fm = FeasibilityMatrix(**fm_raw)

            def _pick(attr: str) -> str | int | list:
                """Pick first non-empty value: rebuttal > attack."""
                if rebuttal_info:
                    val = getattr(rebuttal_info, attr, None)
                    if val:  # non-empty string, non-zero int, non-empty list
                        return val
                return getattr(ar, attr)

            st = StressTestResult(
                idea_id=idea_id,
                freeform_attack=ar.freeform_attack,
                structured_attacks=ar.structured_attacks,
                defenses=ar.defenses,
                debate_rounds=debate_rounds,
                attacks_made=_pick("attacks_made") or len(ar.structured_attacks),
                attacks_survived=_pick("attacks_survived"),
                attacks_fatal=_pick("attacks_fatal"),
                strongest_argument=_pick("strongest_argument"),
                strongest_defense=(
                    (rebuttal_info.strongest_defense if rebuttal_info else "")
                    or (defense_info.strongest_defense if defense_info else "")
                    or ar.strongest_defense
                ),
                suggested_mutation=_pick("suggested_mutation"),
                feasibility_matrix=fm,
                feasibility_verdict=_pick("feasibility_verdict"),
                llm_capability_fit=_pick("llm_capability_fit"),
                kill_criteria=_pick("kill_criteria"),
                verdict=_pick("verdict"),
            )
            results.append(st)

            title = next((c.title for c in candidates if c.id == idea_id), idea_id)
            survived = st.attacks_survived
            fatal = st.attacks_fatal
            _log("STRESS", f"  {title}: {survived} survived, {fatal} fatal → {st.verdict}")

        _log("STRESS", "")
        verdicts: dict[str, int] = {}
        for r in results:
            verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
        _log("STRESS", f"  Verdicts: {verdicts}")

        return results

    def _phase_refine(
        self,
        raw_ideas: list[RawIdea],
        candidates: list[IdeaCard],
        stress_results: list[StressTestResult],
        domains: list[str] | None,
        constraints: list[str] | None,
        domain_briefs: list[DomainBrief],
        brief_text: str | None,
        iteration: int = 1,
        cached_context: dict[str, str] | None = None,
    ) -> list[IdeaCard]:
        """Refinement phase: extract learnings from failed ideas and generate improved ideas.
        
        Iteration controls learning aggressiveness:
        - Iteration 1: Extract top mutations + attack patterns
        - Iteration 2+: Extract more patterns, tighter constraints, lower creativity
        """
        _log("REFINE", f"Refinement Iteration {iteration}: Analyzing failures and learning patterns...")

        # Extract mutations from MUTATE ideas (suggest specific improvements)
        mutations = []
        for c in candidates:
            stress = next((s for s in stress_results if s.idea_id == c.id), None)
            if stress and stress.verdict == "MUTATE" and stress.suggested_mutation:
                mutations.append({
                    "idea_id": c.id,
                    "idea_title": c.title,
                    "suggested_mutation": stress.suggested_mutation,
                })

        _log("REFINE", f"  Mutations extracted: {len(mutations)} suggested improvements from MUTATE verdicts")
        if mutations[:2]:
            for m in mutations[:2]:
                _log("REFINE", f"    - {m['idea_title']}: {m['suggested_mutation'][:80]}")

        # Extract attack patterns (what kills ideas repeatedly?)
        attack_counter = {}
        for s in stress_results:
            if s.strongest_argument:
                key = s.strongest_argument[:80]
                attack_counter[key] = attack_counter.get(key, {"count": 0, "text": s.strongest_argument})
                attack_counter[key]["count"] += 1

        # On later iterations, be more aggressive: extract more patterns
        max_patterns = 5 if iteration == 1 else 10
        attack_patterns = [
            {"pattern": v["text"], "frequency": v["count"]}
            for v in sorted(attack_counter.values(), key=lambda x: -x["count"])[:max_patterns]
        ]

        _log("REFINE", f"  Attack patterns identified: {len(attack_patterns)} recurring threat vectors")
        if attack_patterns[:2]:
            for p in attack_patterns[:2]:
                _log("REFINE", f"    - [{p['frequency']}x] {p['pattern'][:70]}")

        _log("REFINE", f"  Extracted {len(mutations)} mutations and {len(attack_patterns)} attack patterns")

        # Build refinement context for diverge phase
        refinement_ctx = build_refinement_context(mutations, attack_patterns)
        _log("REFINE", f"  Learning context prepared: {len(mutations[:5])} mutations + {len(attack_patterns[:5])} patterns")

        # Use cached context if available, otherwise build fresh
        if cached_context:
            domain_ctx = cached_context["domain"]
            constraint_ctx = cached_context["constraint"]
            memory_ctx = cached_context["memory"]
            immersion_ctx = cached_context["immersion"]
            brief_ctx = cached_context["brief"]
        else:
            domain_ctx = build_domain_context(domains, self.cfg.DEFAULT_DOMAINS)
            constraint_ctx = build_constraint_context(constraints)
            memory_ctx = build_memory_context(
                self.memory.past_idea_count(),
                self.memory.get_domain_heat_map(),
                self.memory.killed_idea_titles(),
            )
            immersion_ctx = build_immersion_context(
                [b.model_dump() for b in domain_briefs] if domain_briefs else None
            )
            brief_ctx = build_brief_context(brief_text)

        # Adjust idea count by iteration: 1st=50%, 2nd=33%, 3rd=25%
        ideas_divisor = 2 if iteration == 1 else (3 if iteration == 2 else 4)
        diverge_ideas_count = max(4, self.cfg.ideas_per_round // ideas_divisor)
        
        prompt = DIVERGE_USER.format(
            idea_count=diverge_ideas_count,
            domain_context=domain_ctx,
            constraint_context=constraint_ctx,
            memory_context=memory_ctx,
            immersion_context=immersion_ctx,
            brief_context=brief_ctx,
            playbook_context=build_playbook_context(self.memory.get_playbook()),
        )

        # Append refinement context to the prompt
        refined_prompt = prompt + "\n\n" + refinement_ctx

        # Adjust temperature: less creative on later iterations (more focused on solving problems)
        temperature = max(0.5, 0.9 - (iteration * 0.15))
        _log("REFINE", f"  DIVERGE: Generating {diverge_ideas_count} focused ideas (temperature={temperature:.2f})...")
        
        data = self.llm.generate_json(self._sys(DIVERGE_SYSTEM), refined_prompt, temperature=temperature,
                                       model_override=self._model_for_phase("refine"), phase="refine-diverge",
                                       max_tokens=8192)
        ideas_raw = data.get("ideas", [])

        refined_raw_ideas = []
        for item in ideas_raw:
            refined_raw_ideas.append(RawIdea(**item))

        techniques = {}
        for idea in refined_raw_ideas:
            techniques[idea.source_technique] = techniques.get(idea.source_technique, 0) + 1
        tech_str = ", ".join(f"{k} ({v})" for k, v in techniques.items())
        _log("REFINE", f"  DIVERGE result: {len(refined_raw_ideas)} ideas — {tech_str}")

        # Converge on refined ideas
        ideas_json = json.dumps(
            [i.model_dump() for i in refined_raw_ideas], indent=2, ensure_ascii=False,
        )

        converge_top_n = max(2, self.cfg.converge_top_n // ideas_divisor)
        prompt = CONVERGE_USER.format(
            idea_count=len(refined_raw_ideas),
            top_n=converge_top_n,
            ideas_json=ideas_json,
            calibration_context=build_calibration_context(self.memory.get_score_stats()),
        )

        _log("REFINE", f"  CONVERGE: Scoring {len(refined_raw_ideas)} ideas, selecting top {converge_top_n}...")
        data = self.llm.generate_json(self._sys(CONVERGE_SYSTEM), prompt, temperature=0.5,
                                       model_override=self._model_for_phase("refine"), phase="refine-converge",
                                       max_tokens=12288)

        clustering = data.get("clustering_summary", "")
        if clustering:
            _log("REFINE", f"    Clustering: {clustering[:100]}...")

        candidates_raw = data.get("candidates", [])
        refined_candidates = []
        for c in candidates_raw:
            card = self._parse_candidate(c)
            refined_candidates.append(card)

        _log("REFINE", f"  CONVERGE result: {len(refined_candidates)} candidates ready for stress test")
        for i, c in enumerate(refined_candidates[:3]):
            _log("REFINE", f"    #{i+1} [{c.composite_score:.1f}] {c.title}")

        # Save refinement run to memory
        self.memory.save_refinement_run({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iteration": iteration,
            "refined_ideas_count": len(refined_candidates),
            "mutations_extracted": len(mutations),
            "attack_patterns_extracted": len(attack_patterns),
        })

        return refined_candidates

    def _parse_candidate(self, c: dict) -> IdeaCard:
        """Parse a candidate dict from the LLM into an IdeaCard with computed score."""
        sb_raw = c.get("score_breakdown", {})
        sb = ScoreBreakdown(**sb_raw)
        composite = compute_composite_score(sb)

        persona_raw = c.get("primary_persona", {})
        persona = Persona(**persona_raw)

        return IdeaCard(
            id=c.get("id", ""),
            title=c.get("title", ""),
            rationale=c.get("rationale", ""),
            composite_score=composite,
            score_breakdown=sb,
            novelty_score=c.get("novelty_score", 0.0),
            domain_tags=c.get("domain_tags", []),
            source_technique=c.get("source_technique", ""),
            primary_persona=persona,
            estimated_effort=c.get("estimated_effort", ""),
            estimated_cost_usd_month=c.get("estimated_cost_usd_month", 0),
            ethical_risk=c.get("ethical_risk_level", ""),
            sustainability_model=c.get("sustainability_model", ""),
            defensibility_notes=c.get("defensibility_notes", ""),
            market_timing_notes=c.get("market_timing_notes", ""),
            score_reasoning=c.get("score_reasoning", {}),
            inverse_terrible_conditions=c.get("inverse_score", {}).get("terrible_conditions", []),
            inverse_confidence=c.get("inverse_score", {}).get("inverse_confidence", 0.0),
        )

    def _parse_stress_result(self, r: dict) -> StressTestResult:
        fm_raw = r.get("feasibility_matrix", {})
        fm = FeasibilityMatrix(**fm_raw)
        return StressTestResult(
            idea_id=r.get("idea_id", ""),
            freeform_attack=r.get("freeform_attack", ""),
            structured_attacks=r.get("structured_attacks", []),
            defenses=r.get("defenses", []),
            attacks_made=r.get("attacks_made", 0),
            attacks_survived=r.get("attacks_survived", 0),
            attacks_fatal=r.get("attacks_fatal", 0),
            strongest_argument=r.get("strongest_argument", ""),
            strongest_defense=r.get("strongest_defense", ""),
            suggested_mutation=r.get("suggested_mutation", ""),
            feasibility_matrix=fm,
            feasibility_verdict=r.get("feasibility_verdict", ""),
            llm_capability_fit=r.get("llm_capability_fit", ""),
            kill_criteria=r.get("kill_criteria", []),
            verdict=r.get("verdict", ""),
        )

    def _merge_survivors(
        self, candidates: list[IdeaCard], stress_results: list[StressTestResult],
    ) -> list[IdeaCard]:
        """Merge stress test results into candidate cards, deduplicate, and return sorted."""
        result_map = {r.idea_id: r for r in stress_results}
        survivors = []
        for card in candidates:
            st = result_map.get(card.id)
            if st:
                card.stress_test_verdict = st.verdict
                card.kill_arguments_survived = st.attacks_survived
                card.llm_capability_fit = st.llm_capability_fit
            survivors.append(card)
        survivors.sort(key=lambda c: c.composite_score, reverse=True)

        # Deduplicate by normalized title — keep highest-scored version
        seen_titles: dict[str, int] = {}
        unique: list[IdeaCard] = []
        dupes = 0
        for card in survivors:
            key = card.title.strip().lower()
            if key in seen_titles:
                dupes += 1
                continue
            seen_titles[key] = len(unique)
            unique.append(card)
        if dupes:
            _log("MERGE", f"  Removed {dupes} duplicate idea(s) by title")
        return unique

    def _write_outputs(self, run_dir: Path, result: IdeateRunResult) -> None:
        """Write all pipeline outputs to disk."""
        # idea-report.md
        cost_info = self.actual_cost()
        report = generate_idea_report(result, cost_info=cost_info)
        (run_dir / "idea-report.md").write_text(report, encoding="utf-8")

        # idea-cards.json — only survivors with BUILD or INCUBATE
        cards = [c.model_dump() for c in result.survivors]
        (run_dir / "idea-cards.json").write_text(
            json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8",
        )

        # idea-log.json — full trace
        (run_dir / "idea-log.json").write_text(
            json.dumps(result.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # stress-test-report.json
        stress_data = [s.model_dump() for s in result.stress_test_results]
        (run_dir / "stress-test-report.json").write_text(
            json.dumps(stress_data, indent=2, ensure_ascii=False), encoding="utf-8",
        )

    def _update_memory(self, result: IdeateRunResult) -> None:
        """Persist run data to cross-session memory."""
        ideas_for_archive = [
            {"id": c.id, "title": c.title, "score": c.composite_score,
             "verdict": c.stress_test_verdict, "domains": c.domain_tags}
            for c in result.survivors
        ]
        killed = [
            {"id": c.id, "title": c.title, "reason": next(
                (s.strongest_argument for s in result.stress_test_results if s.idea_id == c.id), ""),
            }
            for c in result.survivors if c.stress_test_verdict == "KILL"
        ]

        # Extract mutations from MUTATE ideas
        mutations = []
        for c in result.survivors:
            if c.stress_test_verdict == "MUTATE":
                stress = next((s for s in result.stress_test_results if s.idea_id == c.id), None)
                if stress and stress.suggested_mutation:
                    mutations.append({
                        "idea_id": c.id,
                        "idea_title": c.title,
                        "suggested_mutation": stress.suggested_mutation,
                    })

        # Extract attack patterns (most common strongest_arguments)
        attack_counter = {}
        for s in result.stress_test_results:
            if s.strongest_argument:
                key = s.strongest_argument[:80]  # Use first 80 chars as key
                attack_counter[key] = attack_counter.get(key, {"count": 0, "text": s.strongest_argument})
                attack_counter[key]["count"] += 1

        attack_patterns = [
            {"pattern": v["text"], "frequency": v["count"]}
            for v in sorted(attack_counter.values(), key=lambda x: -x["count"])[:5]
        ]

        domains_used: set[str] = set()
        for c in result.survivors:
            domains_used.update(c.domain_tags)

        build_count = sum(1 for c in result.survivors if c.stress_test_verdict == "BUILD")
        metrics = {
            "run_id": result.run_id,
            "timestamp": result.timestamp,
            "ideas_generated": len(result.raw_ideas),
            "candidates": len(result.candidates),
            "build_count": build_count,
            "tokens_in": result.total_input_tokens,
            "tokens_out": result.total_output_tokens,
        }

        self.memory.save_run(ideas_for_archive, list(domains_used), killed, metrics)

        # Save mutations and attack patterns for refinement learning
        if mutations:
            self.memory.save_mutations(mutations)
        if attack_patterns:
            self.memory.save_attack_patterns(attack_patterns)

        # Save lineage: track which ideas came from which run + source technique
        lineage_entries = []
        for c in result.survivors:
            entry = {
                "idea_id": c.id,
                "title": c.title,
                "run_id": result.run_id,
                "timestamp": result.timestamp,
                "source_technique": c.source_technique,
                "parent_ideas": c.parent_ideas,
                "domain_tags": c.domain_tags,
                "score": c.composite_score,
                "verdict": c.stress_test_verdict,
            }
            lineage_entries.append(entry)
        if lineage_entries:
            self.memory.save_lineage(lineage_entries)

        # Extract idea genes from high-scoring ideas
        genes = []
        for c in result.survivors:
            if c.composite_score >= 6.5:
                genes.append({
                    "gene_type": "solution_pattern",
                    "source_idea": c.id,
                    "source_run": result.run_id,
                    "title": c.title,
                    "domains": c.domain_tags,
                    "pattern": c.rationale[:200] if c.rationale else "",
                    "score": c.composite_score,
                    "verdict": c.stress_test_verdict,
                })
        if genes:
            self.memory.save_idea_genes(genes)

    def _sys(self, base_prompt: str) -> str:
        """Inject language instruction into a system prompt if set."""
        if self._language:
            return (
                base_prompt + f" All human-readable text in your JSON response "
                f"(titles, rationales, descriptions, attacks, defenses, personas, etc.) "
                f"MUST be written in {self._language}. Keep JSON keys in English."
            )
        return base_prompt

    @staticmethod
    def _make_run_id(brief_text: str | None = None) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        if not brief_text:
            return ts
        # Normalize unicode, keep ASCII letters/digits, collapse whitespace to hyphens
        slug = unicodedata.normalize("NFKD", brief_text).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^a-zA-Z0-9\s-]", "", slug)
        slug = re.sub(r"[\s_-]+", "-", slug).strip("-").lower()
        # Truncate to ~40 chars on a word boundary
        if len(slug) > 40:
            slug = slug[:40].rsplit("-", 1)[0]
        return f"{ts}-{slug}" if slug else ts

    # ------------------------------------------------------------------
    # Model routing
    # ------------------------------------------------------------------

    def _model_for_phase(self, phase: str) -> str | None:
        """Return model override for a phase, or None to use default."""
        strategy = self.cfg.model_strategy
        if strategy == "single":
            return None  # use self.llm.model everywhere
        routing = self.cfg.PHASE_ROUTING.get(strategy, {})
        tier = routing.get(phase, "best")
        if tier == "cheap":
            return self.cfg.cheap_model or None
        return (self.cfg.best_model or self.cfg.model) or None

    # ------------------------------------------------------------------
    # Async helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_parallel(coros: list, max_concurrent: int = 8) -> list:
        """Run coroutines concurrently with a concurrency limit to avoid rate limits."""
        async def _gather():
            sem = asyncio.Semaphore(max_concurrent)
            async def _limited(idx: int, coro):
                async with sem:
                    if idx > 0:
                        await asyncio.sleep(0.1)  # brief stagger to avoid burst
                    return await coro
            tasks = [_limited(i, c) for i, c in enumerate(coros)]
            return await asyncio.gather(*tasks)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _gather()).result()
        return asyncio.run(_gather())

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_cost(
        model: str,
        ideas_per_round: int,
        converge_top_n: int,
        has_domains: bool,
        has_constraints: bool,
        pricing: dict[str, tuple[float, float]],
        strategy: str = "single",
        cheap_model: str = "",
    ) -> dict:
        """Estimate API cost before running. Returns phase breakdown and total."""
        # Rough token estimates per phase (based on observed runs)
        phases = []
        def _add(name: str, inp: int, out: int):
            m = model
            if strategy != "single" and cheap_model:
                from xbrain.config import Config
                routing = Config.PHASE_ROUTING.get(strategy, {})
                tier = routing.get(name, "best")
                if tier == "cheap":
                    m = cheap_model
            phases.append({"phase": name, "model": m,
                           "est_input_tokens": inp, "est_output_tokens": out})

        if has_constraints:
            _add("constraints", 800, 600)
        if has_domains:
            _add("immerse", 600, 3000)
        _add("diverge", 2000, 4000 + ideas_per_round * 120)
        _add("dedup", 1500 + ideas_per_round * 80, 1500)
        _add("gapfill", 1500, 2000)
        _add("converge", 2000 + ideas_per_round * 80, 5000 + converge_top_n * 500)
        _add("stress", 2000 + converge_top_n * 300, 5000 + converge_top_n * 800)
        _add("stress-defense", 2000 + converge_top_n * 500, 4000 + converge_top_n * 600)
        _add("stress-rebuttal", 2000 + converge_top_n * 600, 5000 + converge_top_n * 700)

        total_cost = 0.0
        for p in phases:
            rate = pricing.get(p["model"], (3.0, 15.0))  # default to sonnet pricing
            cost = (p["est_input_tokens"] / 1_000_000 * rate[0] +
                    p["est_output_tokens"] / 1_000_000 * rate[1])
            p["est_cost_usd"] = round(cost, 6)
            total_cost += cost

        return {
            "phases": phases,
            "total_est_cost_usd": round(total_cost, 4),
            "model": model,
            "strategy": strategy,
        }

    def actual_cost(self) -> dict:
        """Return actual cost breakdown after a run."""
        total = 0.0
        phases = []
        for entry in self.llm._phase_token_log:
            rate = self.cfg.MODEL_PRICING.get(entry["model"], (3.0, 15.0))
            cost = (entry["input_tokens"] / 1_000_000 * rate[0] +
                    entry["output_tokens"] / 1_000_000 * rate[1])
            phases.append({**entry, "cost_usd": round(cost, 6)})
            total += cost
        return {"phases": phases, "total_cost_usd": round(total, 4)}
