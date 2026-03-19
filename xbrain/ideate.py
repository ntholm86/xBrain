"""Pipeline 1: IDEATE — the main orchestrator for idea generation."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from xbrain.config import Config
from xbrain.llm import LLMClient
from xbrain.memory import MemoryStore
from xbrain.models import (
    DebateExchange,
    DomainBrief,
    FeasibilityMatrix,
    IdeaCard,
    IdeateRunResult,
    Persona,
    RawIdea,
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
    print(f"[{tag:<9s}] {msg}")
    sys.stdout.flush()


def _log_phase_header(phase: str, description: str) -> None:
    """Print a visible phase separator for console readability."""
    print()
    print(f"{'=' * 60}")
    print(f"  {phase}: {description}")
    print(f"{'=' * 60}")
    sys.stdout.flush()


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
            domain_briefs = self._phase_immerse(domains)
            result.domain_briefs = domain_briefs

        # Phase 1 — Diverge
        _log_phase_header("DIVERGE", "Generating raw idea seeds")
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

        # Phase 2 — Converge
        _log_phase_header("CONVERGE", f"Scoring and ranking {len(raw_ideas)} ideas")
        candidates = self._phase_converge(raw_ideas)
        result.candidates = candidates

        # Phase 3 — Stress Test
        _log_phase_header("STRESS TEST", f"Adversarial debate for {len(candidates)} candidates")
        stress_results = self._phase_stress_test(candidates)
        result.stress_test_results = stress_results

        # Merge stress results into candidates to produce survivors
        survivors = self._merge_survivors(candidates, stress_results)
        result.survivors = survivors

        # Check if any ideas survived with BUILD verdict — if not, trigger iterative refinement loop
        build_count = sum(1 for s in stress_results if s.verdict == "BUILD")
        refinement_round = 0
        max_refinement_rounds = 3
        refinement_error = None
        
        try:
            while build_count == 0 and refinement_round < max_refinement_rounds:
                refinement_round += 1
                _log("IDEATE", f"")
                _log("IDEATE", f"Refinement Round {refinement_round}/{max_refinement_rounds}: No BUILD verdicts found. Extracting learnings...")
                
                # Run refinement phase
                refinement_survivors = self._phase_refine(
                    raw_ideas, survivors, stress_results, domains, constraints, domain_briefs, brief_text,
                    iteration=refinement_round
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
        print(f"  Tokens: {result.total_input_tokens:,} in / {result.total_output_tokens:,} out")
        print(f"  Cost:   ${cost_info['total_cost_usd']:.4f}")
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
            f"{sv['s']}→{sv['v'][0]}" for sv in score_history[-30:]
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
        )
        briefs_raw = data.get("domain_briefs", [])

        briefs = []
        for b in briefs_raw:
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
                                       model_override=self._model_for_phase("converge"), phase="converge")

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
        _log("STRESS", f"Adversarial debate for {len(candidates)} candidates...")
        _log("STRESS", "")

        candidates_compact = [
            {
                "id": c.id,
                "title": c.title,
                "rationale": c.rationale,
                "composite_score": c.composite_score,
                "domain_tags": c.domain_tags,
                "primary_persona": c.primary_persona.model_dump(),
                "score_breakdown": c.score_breakdown.model_dump(),
            }
            for c in candidates
        ]
        candidates_json = json.dumps(candidates_compact, indent=2, ensure_ascii=False)

        # ── Round 1: Devil's Advocate attacks ──────────────────────────
        _log("STRESS", "Round 1/3 — Devil's Advocate attacking...")

        attack_prompt = STRESS_TEST_USER.format(
            candidate_count=len(candidates),
            candidates_json=candidates_json,
        )

        attack_data = self.llm.generate_json(
            self._sys(STRESS_TEST_SYSTEM), attack_prompt, temperature=0.4,
            model_override=self._model_for_phase("stress"), phase="stress-attack",
        )

        attack_results_raw = attack_data.get("results", [])
        for ar in attack_results_raw:
            idea_id = ar.get("idea_id", "?")
            title = next((c.title for c in candidates if c.id == idea_id), idea_id)
            attacks = ar.get("structured_attacks", [])
            _log("STRESS", f"  {title}")
            _log("STRESS", f"    Freeform: {ar.get('freeform_attack', '')[:100]}")
            for atk in attacks[:3]:
                _log("STRESS", f"    - {atk[:90]}")
            if len(attacks) > 3:
                _log("STRESS", f"    ... and {len(attacks) - 3} more attacks")

        # ── Round 2: Idea Champion defends ─────────────────────────────
        _log("STRESS", "")
        _log("STRESS", "Round 2/3 — Idea Champion defending...")

        attacks_json = json.dumps(
            [
                {
                    "idea_id": ar.get("idea_id", ""),
                    "freeform_attack": ar.get("freeform_attack", ""),
                    "structured_attacks": ar.get("structured_attacks", []),
                }
                for ar in attack_results_raw
            ],
            indent=2,
            ensure_ascii=False,
        )

        defense_prompt = ADVERSARIAL_DEFENSE_USER.format(
            candidate_count=len(candidates),
            candidates_json=candidates_json,
            attacks_json=attacks_json,
        )

        defense_data = self.llm.generate_json(
            self._sys(ADVERSARIAL_DEFENSE_SYSTEM), defense_prompt, temperature=0.4,
            model_override=self._model_for_phase("stress"), phase="stress-defense",
        )

        defenses_raw = defense_data.get("defenses", [])
        defense_map: dict[str, dict] = {}
        for d in defenses_raw:
            idea_id = d.get("idea_id", "")
            defense_map[idea_id] = d
            title = next((c.title for c in candidates if c.id == idea_id), idea_id)
            exchanges = d.get("exchanges", [])
            _log("STRESS", f"  {title}")
            for ex in exchanges[:3]:
                outcome = ex.get("outcome", "?")
                _log("STRESS", f"    [{outcome:>8s}] {ex.get('angle', '?')}: {ex.get('defense', '')[:80]}")
            if len(exchanges) > 3:
                _log("STRESS", f"    ... and {len(exchanges) - 3} more defenses")

        # ── Round 3: Judge runs rebuttal round + verdict ───────────────
        _log("STRESS", "")
        _log("STRESS", "Round 3/3 — Final rebuttals and verdict...")

        debate_json = json.dumps(
            [
                {
                    "idea_id": ar.get("idea_id", ""),
                    "attacks": ar.get("structured_attacks", []),
                    "freeform_attack": ar.get("freeform_attack", ""),
                    "defenses": defense_map.get(ar.get("idea_id", ""), {}).get("exchanges", []),
                }
                for ar in attack_results_raw
            ],
            indent=2,
            ensure_ascii=False,
        )

        rebuttal_prompt = ADVERSARIAL_REBUTTAL_USER.format(
            candidate_count=len(candidates),
            candidates_json=candidates_json,
            debate_json=debate_json,
        )

        rebuttal_data = self.llm.generate_json(
            self._sys(ADVERSARIAL_REBUTTAL_SYSTEM), rebuttal_prompt, temperature=0.3,
            model_override=self._model_for_phase("stress"), phase="stress-rebuttal",
        )

        # ── Assemble final StressTestResults ───────────────────────────
        rebuttal_results_raw = rebuttal_data.get("results", [])
        rebuttal_map: dict[str, dict] = {r.get("idea_id", ""): r for r in rebuttal_results_raw}

        results: list[StressTestResult] = []
        for ar in attack_results_raw:
            idea_id = ar.get("idea_id", "")
            defense_info = defense_map.get(idea_id, {})
            rebuttal_info = rebuttal_map.get(idea_id, {})

            # Build debate rounds from all three phases
            debate_rounds: list[DebateExchange] = []
            attack_list = ar.get("structured_attacks", [])
            defense_exchanges = defense_info.get("exchanges", [])
            rebuttal_exchanges = rebuttal_info.get("exchanges", [])

            # Map defense and rebuttal exchanges by angle
            defense_by_angle = {ex.get("angle", "").lower(): ex for ex in defense_exchanges}
            rebuttal_by_angle = {ex.get("angle", "").lower(): ex for ex in rebuttal_exchanges}

            # Standard attack angles
            angles = [
                "Prior art", "Adoption failure", "Technical blocker",
                "Problem reframe", "Negative externalities", "Obsolescence",
                "Timing", "Defensibility", "Expertise gap",
            ]

            for i, attack_text in enumerate(attack_list):
                angle = angles[i] if i < len(angles) else f"Attack {i+1}"
                angle_key = angle.lower()

                dex = defense_by_angle.get(angle_key, {})
                rex = rebuttal_by_angle.get(angle_key, {})

                debate_rounds.append(DebateExchange(
                    angle=angle,
                    attack=attack_text,
                    defense=dex.get("defense", ""),
                    attacker_rebuttal=rex.get("attacker_rebuttal", ""),
                    defender_rebuttal=rex.get("defender_rebuttal", ""),
                    outcome=rex.get("final_outcome", dex.get("outcome", "")),
                ))

            # Use rebuttal verdict as source of truth, fall back to attack data
            fm_raw = rebuttal_info.get("feasibility_matrix", ar.get("feasibility_matrix", {}))
            fm = FeasibilityMatrix(**fm_raw)

            st = StressTestResult(
                idea_id=idea_id,
                freeform_attack=ar.get("freeform_attack", ""),
                structured_attacks=attack_list,
                defenses=ar.get("defenses", []),
                debate_rounds=debate_rounds,
                attacks_made=rebuttal_info.get("attacks_made", ar.get("attacks_made", len(attack_list))),
                attacks_survived=rebuttal_info.get("attacks_survived", ar.get("attacks_survived", 0)),
                attacks_fatal=rebuttal_info.get("attacks_fatal", ar.get("attacks_fatal", 0)),
                strongest_argument=rebuttal_info.get("strongest_argument", ar.get("strongest_argument", "")),
                strongest_defense=rebuttal_info.get("strongest_defense", defense_info.get("strongest_defense", "")),
                suggested_mutation=rebuttal_info.get("suggested_mutation", ar.get("suggested_mutation", "")),
                feasibility_matrix=fm,
                feasibility_verdict=rebuttal_info.get("feasibility_verdict", ar.get("feasibility_verdict", "")),
                llm_capability_fit=rebuttal_info.get("llm_capability_fit", ar.get("llm_capability_fit", "")),
                kill_criteria=rebuttal_info.get("kill_criteria", ar.get("kill_criteria", [])),
                verdict=rebuttal_info.get("verdict", ar.get("verdict", "")),
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

        # Diverge with refinement context — fewer ideas on later iterations for quality focus
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
                                       model_override=self._model_for_phase("refine"), phase="refine-diverge")
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
                                       model_override=self._model_for_phase("refine"), phase="refine-converge")

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
