"""Pipeline 1: IDEATE — the main orchestrator for idea generation."""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from xbrain.config import Config
from xbrain.llm import LLMClient
from xbrain.log import (
    log as _log,
    log_ok as _log_ok,
    log_warn as _log_warn,
    log_error as _log_error,
    log_detail as _log_detail,
    log_verdict as _log_verdict,
    log_phase as _log_phase_header,
    log_llm_call,
    log_progress,
    log_summary_block,
    fmt_verdict,
    fmt_verdicts,
    VERDICT_COLORS,
    _C,
)
from xbrain.memory import MemoryStore
from xbrain.models import (
    AttackResponse,
    DebateExchange,
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
from xbrain.pipeline_helpers import apply_calibration, sanitize_text, make_run_id
from xbrain.search import SearchAggregator, format_search_results
from xbrain.prompts import (
    CONSTRAINT_CHECK_SYSTEM,
    CONSTRAINT_CHECK_USER,
    CONVERGE_SYSTEM,
    CONVERGE_USER,
    CONVERGE_COMPARE_SYSTEM,
    CONVERGE_COMPARE_USER,
    CONVERGE_ENRICH_SYSTEM,
    CONVERGE_ENRICH_USER,
    DEDUP_SYSTEM,
    DEDUP_USER,
    DIVERGE_GAPFILL_SYSTEM,
    DIVERGE_GAPFILL_USER,
    DIVERGE_SYSTEM,
    DIVERGE_USER,
    EVOLVE_SYSTEM,
    EVOLVE_USER,
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
    build_winner_repulsion_context,
    build_failure_taxonomy_context,
    build_failure_blocklist_context,
    build_search_context,
    build_gene_context,
    build_mutation_archive_context,
    build_adaptive_stress_context,
    build_novelty_context,
    build_technique_weight_context,
    CANONICAL_FAILURE_TYPES,
)


# ------------------------------------------------------------------
# Phase name constants
# ------------------------------------------------------------------

PHASE_META = "meta"
PHASE_CONSTRAINTS = "constraints"
PHASE_DIVERGE = "diverge"
PHASE_DEDUP = "dedup"
PHASE_GAPFILL = "gapfill"
PHASE_CONVERGE = "converge"
PHASE_CONVERGE_CLUSTER = "converge-cluster"
PHASE_CONVERGE_COMPARE = "converge-compare"
PHASE_CONVERGE_ENRICH = "converge-enrich"
PHASE_STRESS = "stress"
PHASE_STRESS_ATTACK = "stress-attack"
PHASE_EVOLVE = "evolve"
PHASE_REFINE = "refine"
PHASE_REFINE_DIVERGE = "refine-diverge"
PHASE_REFINE_CONVERGE = "refine-converge"


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
        _log_warn("STRESS", f"[unwrap] {phase}/{idea_id}: bare list (len={len(data)})")
    elif wrapper_key in data:
        items = data[wrapper_key]
        item = items[0] if items else {}
    else:
        # LLM omitted the wrapper — the dict IS the item
        item = data
        _log_warn("STRESS", f"[unwrap] {phase}/{idea_id}: wrapper '{wrapper_key}' missing, using raw dict")

    if isinstance(item, dict):
        item.setdefault("idea_id", idea_id)
    return item


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
        self.search = SearchAggregator.from_config()
        if self.search.enabled:
            _log_detail("SEARCH", f"Web search enabled: {', '.join(self.search.provider_names)}")
        else:
            _log_detail("SEARCH", "No search providers available (install duckduckgo-search for web grounding)")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        constraints: list[str] | None = None,
        brief_text: str | None = None,
        language: str | None = None,
    ) -> Path:
        """Execute the full ideation pipeline and return the run directory."""
        self._language = language
        self._brief_text = brief_text
        run_id = make_run_id(brief_text)
        run_dir = self.cfg.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.monotonic()
        _log("IDEATE", f"Pipeline 1 started.  Run ID: {run_id}")
        if brief_text:
            preview = brief_text[:120] + ("..." if len(brief_text) > 120 else "")
            _log_detail("IDEATE", f"Brief: {preview}")
        if constraints:
            _log_detail("IDEATE", f"Constraints: {', '.join(constraints)}")
        if language:
            _log_detail("IDEATE", f"Language: {language}")
        if self.cfg.model_strategy != "single":
            _log_detail("IDEATE", f"Model strategy: {self.cfg.model_strategy}")

        # Cost estimate
        estimate = self.estimate_cost(
            model=self.cfg.model,
            ideas_per_round=self.cfg.ideas_per_round,
            converge_top_n=self.cfg.converge_top_n,
            has_constraints=bool(constraints),
            pricing=self.cfg.MODEL_PRICING,
            strategy=self.cfg.model_strategy,
            cheap_model=self.cfg.cheap_model,
            generations=self.cfg.generations,
        )
        _log_detail("IDEATE", f"Estimated cost: ${estimate['total_est_cost_usd']:.4f}")

        result = IdeateRunResult(
            run_id=run_id,
            brief_text=brief_text or "",
            constraints=constraints or [],
        )

        # Phase -1 — Meta-Learn (distill playbook if enough runs accumulated)
        self._maybe_distill_playbook()

        # Phase -0.5 — Constraint Conflict Check
        if constraints and len(constraints) >= 2:
            self._phase_check_constraints(constraints)

        # Phase 1 — Diverge
        _log_phase_header("DIVERGE", "Generating raw idea seeds")
        tp = time.monotonic()
        raw_ideas = self._phase_diverge(constraints, brief_text)
        result.raw_ideas = raw_ideas

        # Phase 1b — Dedup + Gap Analysis
        raw_ideas, gaps, overrepresented = self._phase_dedup(raw_ideas)

        # Phase 1c — Gap-Fill Divergence (multi-turn)
        if gaps:
            gap_ideas = self._phase_diverge_gapfill(
                gaps, overrepresented, raw_ideas, brief_text
            )
            if gap_ideas:
                raw_ideas.extend(gap_ideas)
                result.raw_ideas = raw_ideas
        _log_ok("DIVERGE", f"done in {time.monotonic() - tp:.0f}s")

        # Phase 2 — Converge
        _log_phase_header("CONVERGE", f"Scoring and ranking {len(raw_ideas)} ideas")
        tp = time.monotonic()
        candidates = self._phase_converge(raw_ideas)
        _log_ok("CONVERGE", f"done in {time.monotonic() - tp:.0f}s")
        result.candidates = candidates

        # Phase 3 — Stress Test
        _log_phase_header("STRESS TEST", f"Adversarial debate for {len(candidates)} candidates")
        tp = time.monotonic()
        stress_results = self._phase_stress_test(candidates)
        _log_ok("STRESS", f"done in {time.monotonic() - tp:.0f}s")
        result.stress_test_results = stress_results

        # Merge stress results into candidates to produce survivors
        survivors = self._merge_survivors(candidates, stress_results)
        result.survivors = survivors

        # Check if any ideas passed (BUILD or MUTATE) — only refine if everything is KILL
        pass_count = sum(1 for s in stress_results if s.verdict in ("BUILD", "MUTATE"))
        refinement_round = 0
        max_refinement_rounds = 3
        refinement_error = None

        # Pre-build context once for all refinement rounds
        _cached_ctx: dict[str, str] | None = None
        
        try:
            while pass_count == 0 and refinement_round < max_refinement_rounds:
                refinement_round += 1
                _log("IDEATE", "")
                _log_warn("IDEATE", f"Refinement Round {refinement_round}/{max_refinement_rounds}: No passing verdicts found. Extracting learnings...")

                if _cached_ctx is None:
                    _cached_ctx = {
                        "domain": build_domain_context(),
                        "constraint": build_constraint_context(constraints),
                        "memory": build_memory_context(
                            self.memory.past_idea_count(),
                            self.memory.get_domain_heat_map(),
                            self.memory.killed_idea_titles(),
                        ),
                        "immersion": "",
                        "brief": build_brief_context(brief_text),
                    }

                # Run refinement phase
                refinement_survivors = self._phase_refine(
                    raw_ideas, survivors, stress_results, constraints, brief_text,
                    iteration=refinement_round,
                    cached_context=_cached_ctx,
                )
                
                if not refinement_survivors:
                    _log_warn("REFINE", "No refined candidates generated. Stopping refinement loop.")
                    break
                
                # Re-run stress test on refined ideas
                refinement_stress = self._phase_stress_test(refinement_survivors)
                
                # Merge refinement survivors and stress results into the result
                result.survivors.extend(refinement_survivors)
                result.stress_test_results.extend(refinement_stress)
                
                # Re-merge to update verdicts
                survivors = self._merge_survivors(survivors + refinement_survivors, result.stress_test_results)
                result.survivors = survivors
                
                # Check for passing verdicts (BUILD or MUTATE) in this refinement round
                pass_count = sum(1 for s in refinement_stress if s.verdict in ("BUILD", "MUTATE"))
                kill_count = sum(1 for s in refinement_stress if s.verdict == "KILL")
                
                _log_detail("IDEATE", f"Refinement round {refinement_round} results: {pass_count} passed, {kill_count} KILL")
                
                if pass_count > 0:
                    _log_ok("IDEATE", f"{pass_count} idea(s) passed stress test!")
                    break
                elif refinement_round < max_refinement_rounds:
                    _log_detail("IDEATE", f"-> Will continue refining ({refinement_round}/{max_refinement_rounds})")
            
            if pass_count == 0 and refinement_round >= max_refinement_rounds:
                _log("IDEATE", f"")
                _log_warn("IDEATE", f"Reached maximum refinement rounds ({max_refinement_rounds}). Proceeding with {len(survivors)} candidates.")
        
        except Exception as e:
            refinement_error = e
            _log("IDEATE", f"")
            _log_warn("IDEATE", f"Refinement error after round {refinement_round}: {str(e)}")
            _log_detail("IDEATE", f"Proceeding with round {refinement_round} results.")

        # ── Multi-generation evolution loop ──────────────────────────
        if self.cfg.generations > 1:
            for gen in range(2, self.cfg.generations + 1):
                gen_pass = sum(1 for s in result.stress_test_results if s.verdict in ("BUILD", "MUTATE"))
                if gen_pass == 0:
                    _log_warn("IDEATE", f"No survivors for generation {gen}. Stopping evolution.")
                    break

                # EVOLVE phase: mutate, crossover, novelty-explore
                elites, evolved_raw = self._phase_evolve(
                    survivors, result.stress_test_results, gen, brief_text,
                )

                if not evolved_raw:
                    _log_warn("EVOLVE", f"No evolved ideas produced in generation {gen}. Stopping.")
                    break

                # CONVERGE on evolved ideas
                _log_phase_header("CONVERGE", f"Gen {gen}: Scoring {len(evolved_raw)} evolved ideas")
                tp2 = time.monotonic()
                evolved_candidates = self._phase_converge(evolved_raw)
                _log_ok("CONVERGE", f"Gen {gen} done in {time.monotonic() - tp2:.0f}s")

                # Tag evolution metadata on converged candidates
                # Build lookup of raw evolved idea source_technique by id
                evolved_technique_map = {r.id: r.source_technique for r in evolved_raw}
                for ec in evolved_candidates:
                    ec.generation = gen
                    ec.evolution_rationale = evolved_technique_map.get(ec.id, ec.source_technique)

                # Combine elites with evolved candidates for stress testing
                all_gen_candidates = list(elites) + evolved_candidates

                # STRESS TEST the new generation
                _log_phase_header("STRESS TEST", f"Gen {gen}: Testing {len(all_gen_candidates)} candidates")
                tp2 = time.monotonic()
                gen_stress = self._phase_stress_test(all_gen_candidates)
                _log_ok("STRESS", f"Gen {gen} done in {time.monotonic() - tp2:.0f}s")

                # Merge into result
                result.stress_test_results.extend(gen_stress)
                gen_survivors = self._merge_survivors(all_gen_candidates, gen_stress)

                # Tag generation on each survivor
                for s in gen_survivors:
                    s.phase = f"gen_{gen}"
                    s.generation = gen

                # Replace survivors with new generation (elites + evolved)
                survivors = gen_survivors
                result.survivors = survivors

                gen_build = sum(1 for s in gen_stress if s.verdict == "BUILD")
                gen_mutate = sum(1 for s in gen_stress if s.verdict == "MUTATE")
                gen_kill = sum(1 for s in gen_stress if s.verdict == "KILL")
                gen_verdicts = {"BUILD": gen_build, "MUTATE": gen_mutate, "KILL": gen_kill}
                _log_ok("EVOLVE", f"Gen {gen} results: {fmt_verdicts(gen_verdicts)}")

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
            _log_ok("IDEATE", f"Outputs written to {run_dir}/")
        except Exception as write_error:
            _log_error("IDEATE", f"Failed to write outputs: {write_error}")
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
        final_counts = {"BUILD": final_build, "MUTATE": final_mutate, "KILL": final_kill, "INCUBATE": final_incubate}

        sorted_survivors = sorted(result.survivors, key=lambda c: c.composite_score, reverse=True)

        lines = [
            "",
            f"{_C.BOLD}{_C.WHITE}{'=' * 60}{_C.RESET}",
            f"{_C.BOLD}{_C.WHITE}  xBrain Pipeline Complete{_C.RESET}",
            f"{_C.BOLD}{_C.WHITE}{'=' * 60}{_C.RESET}",
            "",
            f"  Ideas generated:  {len(result.raw_ideas)}",
            f"  After scoring:    {len(result.candidates)}",
            f"  Verdicts:         {fmt_verdicts(final_counts)}",
        ]
        if refinement_round > 0:
            lines.append(f"  Refinement:       {refinement_round} round(s)")
        if self.cfg.generations > 1:
            lines.append(f"  Generations:      {self.cfg.generations}")
        lines.append("")

        final_pass = final_build + final_mutate
        if sorted_survivors:
            lines.append("  Top ideas:")
            for i, c in enumerate(sorted_survivors[:5]):
                verdict = c.stress_test_verdict or "?"
                emoji = {"BUILD": "+", "MUTATE": "~", "KILL": "x", "INCUBATE": "?"}.get(verdict, " ")
                vc = VERDICT_COLORS.get(verdict, "")
                lines.append(f"    {vc}[{emoji}]{_C.RESET} #{i+1}  {c.composite_score:.1f}  {c.title}")
            lines.append("")

        elapsed = time.monotonic() - t0
        mins, secs = divmod(int(elapsed), 60)
        lines += [
            f"  {_C.DIM}Output directory: {run_dir}{_C.RESET}",
            f"    {_C.DIM}idea-report.md           Human-readable ranked report{_C.RESET}",
            f"    {_C.DIM}idea-cards.json          Machine-readable Idea Cards{_C.RESET}",
            f"    {_C.DIM}idea-log.json            Full pipeline trace{_C.RESET}",
            f"    {_C.DIM}stress-test-report.json  Adversarial debate results{_C.RESET}",
            "",
            f"  {_C.DIM}Elapsed: {mins}m {secs}s{_C.RESET}",
            f"  {_C.DIM}Tokens:  {result.total_input_tokens:,} in / {result.total_output_tokens:,} out{_C.RESET}",
            f"  {_C.DIM}Cost:    ${cost_info['total_cost_usd']:.4f}{_C.RESET}",
            "",
        ]

        if final_pass > 0:
            best = next((c for c in sorted_survivors if c.stress_test_verdict in ("BUILD", "MUTATE")), sorted_survivors[0])
            lines.append(f"  Next step:")
            lines.append(f"    python -m xbrain specify --idea {run_dir}/idea-cards.json --select {best.id}")
        else:
            if final_pass > 0:
                lines.append(f"  {final_pass} idea(s) passed stress testing. Review report for details.")
            else:
                lines.append(f"  No passing verdicts. Review ideas or re-run with different constraints.")

        lines.append("")
        log_summary_block(lines)

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
            technique_stats=self.memory.get_technique_verdict_stats(),
            refinement_stats=json.dumps(self.memory.get_refinement_history()[-5:]),
        )

        timer = log_llm_call("META", "Distilling cross-run playbook")
        data = self.llm.generate_json(
            META_LEARN_SYSTEM, prompt, temperature=0.3,
            model_override=self._model_for_phase(PHASE_META), phase=PHASE_META,
            max_tokens=self._max_tokens_for_phase(PHASE_META),
        )
        timer.done()

        playbook = data.get("playbook", "")
        calibration = data.get("score_calibration", {})

        if playbook:
            self.memory.save_playbook(playbook, total_runs)
            _log_ok("META", f"Playbook distilled ({len(playbook)} chars)")

        if calibration:
            self.memory.save_score_calibration(calibration)
            bias = calibration.get("bias_direction", "?")
            weak = calibration.get("weak_dimensions", [])
            _log_detail("META", f"Score calibration: bias={bias}, weak={weak}")

        anti_patterns = data.get("anti_patterns", [])
        if anti_patterns:
            _log_detail("META", f"Anti-patterns: {'; '.join(anti_patterns[:3])}")

        technique_weights = data.get("technique_weights", {})
        if technique_weights:
            self.memory.save_technique_weights(technique_weights)
            adjusted = {k: v for k, v in technique_weights.items() if v != 1.0}
            if adjusted:
                _log_detail("META", f"Technique weights: {adjusted}")

    def _phase_check_constraints(self, constraints: list[str]) -> None:
        """Detect contradictions in user-specified constraints before running the pipeline."""
        _log("CONSTCHK", f"Checking {len(constraints)} constraints for conflicts...")

        prompt = CONSTRAINT_CHECK_USER.format(
            constraint_count=len(constraints),
            constraints_list="\n".join(f"- {c}" for c in constraints),
        )

        try:
            timer = log_llm_call("CONSTCHK", "Validating constraints")
            data = self.llm.generate_json(
                CONSTRAINT_CHECK_SYSTEM, prompt, temperature=0.2,
                model_override=self._model_for_phase(PHASE_CONSTRAINTS), phase=PHASE_CONSTRAINTS,
                max_tokens=self._max_tokens_for_phase(PHASE_CONSTRAINTS),
            )
            timer.done()

            conflicts = data.get("conflicts", [])
            if conflicts:
                _log_warn("CONSTCHK", f"{len(conflicts)} conflict(s) detected:")
                for conflict in conflicts:
                    pair = conflict.get("constraints", [])
                    reason = conflict.get("reason", "")
                    suggestion = conflict.get("suggestion", "")
                    _log_warn("CONSTCHK", f"  CONFLICT: {' vs '.join(pair)}")
                    _log_detail("CONSTCHK", f"    Why: {reason}")
                    if suggestion:
                        _log_detail("CONSTCHK", f"    Fix: {suggestion}")
                _log_detail("CONSTCHK", "Proceeding anyway -- constraints will be applied as-is.")
            else:
                _log_ok("CONSTCHK", "No conflicts detected.")
        except Exception as e:
            _log_warn("CONSTCHK", f"Skipped (error: {e})")

    def _phase_diverge(
        self,
        constraints: list[str] | None,
        brief_text: str | None = None,
    ) -> list[RawIdea]:
        _log("DIVERGE", "Generating raw idea seeds...")

        domain_ctx = build_domain_context()
        constraint_ctx = build_constraint_context(constraints)
        memory_ctx = build_memory_context(
            self.memory.past_idea_count(),
            self.memory.get_domain_heat_map(),
            self.memory.killed_idea_titles(),
        )
        immersion_ctx = ""
        brief_ctx = build_brief_context(brief_text)

        winner_ctx = build_winner_repulsion_context(self.memory.get_previous_winners())
        failure_ctx = build_failure_taxonomy_context(self.memory.get_failure_taxonomy())
        gene_ctx = build_gene_context(self.memory.get_idea_genes())

        prompt = DIVERGE_USER.format(
            idea_count=self.cfg.ideas_per_round,
            domain_context=domain_ctx,
            constraint_context=constraint_ctx,
            memory_context=memory_ctx,
            immersion_context=immersion_ctx,
            brief_context=brief_ctx,
            playbook_context=build_playbook_context(self.memory.get_playbook()),
            winner_repulsion_context=winner_ctx,
            failure_taxonomy_context=failure_ctx,
            gene_context=gene_ctx,
            technique_weight_context=build_technique_weight_context(self.memory.get_technique_weights()),
        )

        timer = log_llm_call("DIVERGE", f"Generating {self.cfg.ideas_per_round} idea seeds")
        data = self.llm.generate_json(
            self._sys(DIVERGE_SYSTEM), prompt, temperature=0.9,
            model_override=self._model_for_phase(PHASE_DIVERGE), phase=PHASE_DIVERGE,
            max_tokens=self._max_tokens_for_phase(PHASE_DIVERGE),
        )
        timer.done()
        ideas_raw = data.get("ideas", [])

        ideas = []
        for item in ideas_raw:
            ideas.append(RawIdea(**item))

        # Summarise techniques used
        techniques = {}
        for idea in ideas:
            techniques[idea.source_technique] = techniques.get(idea.source_technique, 0) + 1
        tech_str = ", ".join(f"{k} ({v})" for k, v in techniques.items())
        _log_ok("DIVERGE", f"{len(ideas)} raw idea seeds generated.")
        _log_detail("DIVERGE", f"Techniques: {tech_str}")

        # List all raw ideas so user can follow the pipeline
        for idx, idea in enumerate(ideas, 1):
            _log_detail("DIVERGE", f"    {idx:>2}. [{idea.source_technique}] {idea.concept[:80]}")

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

        timer = log_llm_call("DEDUP", "Detecting duplicates")
        data = self.llm.generate_json(
            self._sys(DEDUP_SYSTEM), prompt, temperature=0.2,
            model_override=self._model_for_phase(PHASE_DEDUP), phase=PHASE_DEDUP,
            max_tokens=self._max_tokens_for_phase(PHASE_DEDUP),
        )
        timer.done()

        keep_ids = set(data.get("keep", [i.id for i in raw_ideas]))
        removed = data.get("remove", [])
        gaps = data.get("gap_areas", [])
        overrepresented = data.get("overrepresented_themes", [])

        if removed:
            _log_warn("DEDUP", f"Removed {len(removed)} duplicates:")
            for r in removed[:3]:
                _log_detail("DEDUP", f"  - {r.get('id', '?')} ~ {r.get('duplicate_of', '?')}: {r.get('reason', '')[:60]}")

        if overrepresented:
            _log_warn("DEDUP", f"Over-represented: {'; '.join(overrepresented[:3])}")

        if gaps:
            _log_detail("DEDUP", f"Gaps found: {'; '.join(gaps[:3])}")

        filtered = [i for i in raw_ideas if i.id in keep_ids]
        _log_ok("DEDUP", f"{len(raw_ideas)} -> {len(filtered)} unique ideas")

        # List surviving ideas after dedup
        if removed:
            for idx, idea in enumerate(filtered, 1):
                _log_detail("DEDUP", f"    {idx:>2}. {idea.concept[:80]}")

        return filtered, gaps, overrepresented

    def _phase_diverge_gapfill(
        self,
        gaps: list[str],
        overrepresented: list[str],
        existing_ideas: list[RawIdea],
        brief_text: str | None,
    ) -> list[RawIdea]:
        """Multi-turn divergence: generate new ideas to fill gaps from round 1."""
        # Cap at half of original idea count to keep total manageable
        gap_count = min(len(gaps) + 2, max(3, self.cfg.ideas_per_round // 2))
        _log("DIVERGE", f"Round 2 -- gap-filling {len(gaps)} gaps with {gap_count} new ideas...")

        prompt = DIVERGE_GAPFILL_USER.format(
            idea_count=gap_count,
            brief_context=build_brief_context(brief_text),
            domain_context=build_domain_context(),
            playbook_context=build_playbook_context(self.memory.get_playbook()),
            overrepresented="; ".join(overrepresented),
            gaps="; ".join(gaps),
            previous_titles="; ".join(i.concept[:60] for i in existing_ideas[:10]),
        )

        timer = log_llm_call("DIVERGE", f"Gap-filling {gap_count} ideas")
        data = self.llm.generate_json(
            self._sys(DIVERGE_GAPFILL_SYSTEM), prompt, temperature=0.95,
            model_override=self._model_for_phase(PHASE_GAPFILL), phase=PHASE_GAPFILL,
            max_tokens=self._max_tokens_for_phase(PHASE_GAPFILL),
        )
        timer.done()

        ideas_raw = data.get("ideas", [])
        gap_ideas = [RawIdea(**item) for item in ideas_raw]

        _log_ok("DIVERGE", f"Gap-fill generated {len(gap_ideas)} new ideas")
        if gap_ideas:
            techniques = {}
            for idea in gap_ideas:
                techniques[idea.source_technique] = techniques.get(idea.source_technique, 0) + 1
            _log_detail("DIVERGE", f"Techniques: {', '.join(f'{k} ({v})' for k, v in techniques.items())}")

            # List gap-fill ideas
            for idx, idea in enumerate(gap_ideas, 1):
                _log_detail("DIVERGE", f"    {idx:>2}. [gap] {idea.concept[:80]}")

        return gap_ideas

    def _phase_converge(self, raw_ideas: list[RawIdea]) -> list[IdeaCard]:
        _log("CONVERGE", f"Decomposed scoring pipeline for {len(raw_ideas)} ideas...")

        # ── Sub-phase 2A: CLUSTER + INITIAL SCORE ────────────────
        _log_detail("CONVERGE", "[2A] Clustering and initial scoring...")

        ideas_compact = [
            {"id": i.id, "concept": i.concept, "domain_tags": i.domain_tags,
             "source_technique": i.source_technique}
            for i in raw_ideas
        ]
        ideas_json = json.dumps(ideas_compact, indent=2, ensure_ascii=False)

        calibration_ctx = build_calibration_context(self.memory.get_score_stats())
        novelty_ctx = build_novelty_context(
            self.memory.get_previous_winners(), self.memory.past_idea_count()
        )

        prompt_a = CONVERGE_USER.format(
            idea_count=len(raw_ideas),
            top_n=self.cfg.converge_top_n,
            ideas_json=ideas_json,
            calibration_context=calibration_ctx,
            novelty_context=novelty_ctx,
            brief_context=build_brief_context(self._brief_text),
        )

        timer = log_llm_call("CONVERGE", f"Clustering {len(raw_ideas)} ideas → top {self.cfg.converge_top_n}")
        data_a = self.llm.generate_json(
            self._sys(CONVERGE_SYSTEM), prompt_a, temperature=0.5,
            model_override=self._model_for_phase(PHASE_CONVERGE), phase=PHASE_CONVERGE_CLUSTER,
            max_tokens=self._max_tokens_for_phase(PHASE_CONVERGE_CLUSTER),
        )
        timer.done()

        clustering = data_a.get("clustering_summary", "")
        if clustering:
            _log_detail("CONVERGE", f"Clustering: {clustering[:120]}")

        candidates_raw = data_a.get("candidates", [])
        candidates = []
        for c in candidates_raw:
            card = self._parse_candidate(c)
            candidates.append(card)
        candidates.sort(key=lambda c: c.composite_score, reverse=True)
        _log_ok("CONVERGE", f"[2A] {len(candidates)} candidates with initial scores.")

        # Show which ideas were selected vs dropped
        selected_ids = {c.id for c in candidates}
        dropped = [i for i in raw_ideas if i.id not in selected_ids]
        if dropped:
            _log_detail("CONVERGE", f"  Dropped {len(dropped)}: {', '.join(i.concept[:30] for i in dropped[:6])}{'...' if len(dropped) > 6 else ''}")

        if not candidates:
            return candidates

        # ── Sub-phase 2B: COMPARATIVE RANKING ────────────────────
        _log_detail("CONVERGE", "[2B] Pairwise comparative re-ranking...")

        compare_input = [
            {"id": c.id, "title": c.title, "rationale": c.rationale,
             "score_breakdown": c.score_breakdown.model_dump()}
            for c in candidates
        ]
        compare_json = json.dumps(compare_input, indent=2, ensure_ascii=False)

        prompt_b = CONVERGE_COMPARE_USER.format(
            candidate_count=len(candidates),
            candidates_json=compare_json,
            brief_context=build_brief_context(self._brief_text),
        )

        timer = log_llm_call("CONVERGE", "Pairwise comparative re-ranking")
        data_b = self.llm.generate_json(
            self._sys(CONVERGE_COMPARE_SYSTEM), prompt_b, temperature=0.3,
            model_override=self._model_for_phase(PHASE_CONVERGE), phase=PHASE_CONVERGE_COMPARE,
            max_tokens=self._max_tokens_for_phase(PHASE_CONVERGE_COMPARE),
        )
        timer.done()

        # Apply adjusted scores from comparative ranking
        final_ranking = data_b.get("final_ranking", [])
        adjusted_scores = {s["id"]: s for s in data_b.get("adjusted_scores", [])}

        if adjusted_scores:
            for card in candidates:
                adj = adjusted_scores.get(card.id)
                if adj and "score_breakdown" in adj:
                    sb_raw = adj["score_breakdown"]
                    card.score_breakdown = ScoreBreakdown(**sb_raw)
                    card.composite_score = compute_composite_score(card.score_breakdown)

        # Re-sort by final ranking if available, otherwise by composite score
        if final_ranking:
            rank_map = {id_: idx for idx, id_ in enumerate(final_ranking)}
            candidates.sort(key=lambda c: rank_map.get(c.id, 999))
            _log_ok("CONVERGE", f"[2B] Final ranking: {' -> '.join(c.title[:25] for c in candidates[:4])}...")
        else:
            candidates.sort(key=lambda c: c.composite_score, reverse=True)

        # Log score spread after comparative ranking
        if len(candidates) >= 2:
            spread = candidates[0].composite_score - candidates[-1].composite_score
            _log_detail("CONVERGE", f"[2B] Score spread after comparison: {spread:.1f}")

        # ── Sub-phase 2C: ENRICH + ASSUMPTION INVERSION ──────────
        _log_detail("CONVERGE", "[2C] Enriching with personas, assumptions + inversion...")

        # Batch enrichment to avoid token limit truncation (max 4 candidates per call)
        ENRICH_BATCH = 4
        all_enrichments: dict[str, dict] = {}
        total_batches = (len(candidates) + ENRICH_BATCH - 1) // ENRICH_BATCH
        for batch_start in range(0, len(candidates), ENRICH_BATCH):
            batch = candidates[batch_start:batch_start + ENRICH_BATCH]
            batch_num = batch_start // ENRICH_BATCH + 1
            batch_titles = ", ".join(c.title[:25] for c in batch)
            timer = log_llm_call("CONVERGE", f"Enriching batch {batch_num}/{total_batches} ({batch_titles})")
            enrich_input = [
                {"id": c.id, "title": c.title, "rationale": c.rationale,
                 "domain_tags": c.domain_tags}
                for c in batch
            ]
            enrich_json = json.dumps(enrich_input, indent=2, ensure_ascii=False)

            prompt_c = CONVERGE_ENRICH_USER.format(
                candidate_count=len(batch),
                candidates_json=enrich_json,
                brief_context=build_brief_context(self._brief_text),
            )

            data_c = self.llm.generate_json(
                self._sys(CONVERGE_ENRICH_SYSTEM), prompt_c, temperature=0.5,
                model_override=self._model_for_phase(PHASE_CONVERGE), phase=PHASE_CONVERGE_ENRICH,
                max_tokens=self._max_tokens_for_phase(PHASE_CONVERGE_ENRICH),
            )
            timer.done()

            for e in data_c.get("enrichments", []):
                all_enrichments[e["id"]] = e

        # Merge enrichment data into candidates
        fragile_count = 0
        for card in candidates:
            enrich = all_enrichments.get(card.id)
            if not enrich:
                continue
            # Persona
            persona_raw = enrich.get("primary_persona", {})
            if persona_raw:
                card.primary_persona = Persona(**persona_raw)
            # Assumptions with inversion
            raw_assumptions = enrich.get("key_assumptions", [])
            card.key_assumptions = self._normalize_assumptions(raw_assumptions)
            # Count fragile assumptions
            for a in card.key_assumptions:
                if a.get("fragility_flag") == "fragile":
                    fragile_count += 1
            # Other fields
            card.sustainability_model = enrich.get("sustainability_model", "")
            card.defensibility_notes = enrich.get("defensibility_notes", "")
            card.market_timing_notes = enrich.get("market_timing_notes", "")
            card.first_customer_profile = enrich.get("first_customer_profile", {})
            inv = enrich.get("inverse_score", {})
            card.inverse_terrible_conditions = inv.get("terrible_conditions", [])
            card.inverse_confidence = inv.get("inverse_confidence", 0.0)

        _log_ok("CONVERGE", f"[2C] Enriched {len(all_enrichments)} candidates, {fragile_count} fragile assumptions flagged.")

        # ── Enforce effort diversity ──────────────────────────────
        if len(candidates) >= 3:
            efforts = [c.estimated_effort for c in candidates]
            if len(set(efforts)) == 1:
                by_effort_score = sorted(candidates, key=lambda c: c.score_breakdown.effort)
                by_effort_score[0].estimated_effort = "small"
                by_effort_score[-1].estimated_effort = "large"
                _log_warn("CONVERGE", f"Effort diversity enforced: "
                     f"{by_effort_score[0].title[:30]}→small, "
                     f"{by_effort_score[-1].title[:30]}→large")

        # ── Apply mathematical calibration from META-LEARN ────────
        cal_status = apply_calibration(candidates, self.memory.get_score_stats(), tag="CONVERGE")

        _log_ok("CONVERGE", f"{len(candidates)} candidates scored.  ({cal_status})")
        for i, c in enumerate(candidates[:5]):
            sc = c.composite_score
            _sc_color = _C.GREEN if sc >= 7.5 else (_C.YELLOW if sc >= 5.0 else _C.RED)
            _log("CONVERGE", f"  #{i+1} {_sc_color}[{sc:.1f}]{_C.RESET} \"{c.title}\"")
            _log_detail("CONVERGE", f"       Domains: {', '.join(c.domain_tags)}")
            if c.primary_persona.who:
                _log_detail("CONVERGE", f"       Persona: {c.primary_persona.who}")
            if c.primary_persona.pain:
                _log_detail("CONVERGE", f"       Pain: {c.primary_persona.pain[:80]}")

        return candidates

    def _phase_stress_test(self, candidates: list[IdeaCard]) -> list[StressTestResult]:
        _log("STRESS", f"Adversarial stress test for {len(candidates)} candidates (parallel)...")
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

        stress_model = self._model_for_phase(PHASE_STRESS)
        sys_attack = self._sys(STRESS_TEST_SYSTEM)
        brief_ctx = build_brief_context(self._brief_text)
        adaptive_ctx = build_adaptive_stress_context(
            self.memory.get_attack_patterns(), self.memory.get_kill_log()
        )

        # ── Prior art search for each candidate ──────────────────────
        prior_art_by_id: dict[str, str] = {}
        if self.search.enabled:
            _log_detail("STRESS", "Searching for prior art / competitors...")
            for c in candidates:
                # Short title-based query to find existing products
                results = self.search.search(f"{c.title} existing product competitor", max_results=3)
                if results:
                    prior_art_by_id[c.id] = format_search_results(results, max_chars=800)
                    _log_detail("STRESS", f"  {c.title[:40]}: {len(results)} results")

        # ── Single round: Attack + Feasibility + Verdict (parallel across ideas) ──
        _log("STRESS", f"Attacking {len(candidates)} candidates ({len(candidates)} parallel calls)...")
        _attack_total = len(candidates)
        _attack_done = 0
        _attack_t0 = time.monotonic()

        async def _attack_one(c: IdeaCard) -> AttackResponse:
            nonlocal _attack_done
            _log_detail("STRESS", f"[{_attack_done}/{_attack_total}] Attacking: {c.title[:50]}...")
            cj = json.dumps([compact_by_id[c.id]], ensure_ascii=False)
            prior_art_ctx = ""
            if c.id in prior_art_by_id:
                prior_art_ctx = (
                    "\nPRIOR ART SEARCH RESULTS (from live web search — use these "
                    "to ground your prior art attack in real competitors):\n"
                    f"{prior_art_by_id[c.id]}\n---\n"
                )
            prompt = STRESS_TEST_USER.format(
                candidate_count=1, candidates_json=cj, brief_context=brief_ctx,
                adaptive_stress_context=adaptive_ctx,
            )
            if prior_art_ctx:
                prompt = prior_art_ctx + prompt
            try:
                data = await self.llm.generate_json_async(
                    sys_attack, prompt, temperature=0.4,
                    model_override=stress_model, phase=PHASE_STRESS_ATTACK,
                    max_tokens=self._max_tokens_for_phase(PHASE_STRESS_ATTACK),
                )
                raw = _unwrap_single(data, "results", c.id, "attack")
                _attack_done += 1
                _log_ok("STRESS", f"[{_attack_done}/{_attack_total}] {c.title[:50]} - attack received")
                return AttackResponse.model_validate(raw)
            except (ValueError, Exception) as e:
                _attack_done += 1
                _log_warn("STRESS", f"Attack failed for {c.id} (API crash -> INCUBATE): {e}")
                return AttackResponse(idea_id=c.id, freeform_attack="(attack failed — API crash, not a genuine verdict)", structured_attacks=[], verdict="INCUBATE", error_source="api_crash")

        attack_results = self._run_parallel([_attack_one(c) for c in candidates])
        _log_ok("STRESS", f"All {_attack_total} attacks completed in {time.monotonic() - _attack_t0:.1f}s")

        # ── Assemble final StressTestResults directly from attack ────

        results: list[StressTestResult] = []
        angles = [
            "Prior art", "Adoption failure", "Technical blocker",
            "Problem reframe", "Negative externalities", "Obsolescence",
            "Timing", "Defensibility", "Expertise gap",
        ]

        for ar in attack_results:
            idea_id = ar.idea_id
            title = next((c.title for c in candidates if c.id == idea_id), idea_id)

            _log_detail("STRESS", f"  {title}")
            _log_detail("STRESS", f"    Freeform: {ar.freeform_attack[:100]}")
            for atk in ar.structured_attacks[:3]:
                _log_detail("STRESS", f"    - {atk[:90]}")
            if len(ar.structured_attacks) > 3:
                _log_detail("STRESS", f"    ... and {len(ar.structured_attacks) - 3} more attacks")

            # Build debate rounds from attack + defense pairs
            debate_rounds: list[DebateExchange] = []
            defenses = ar.defenses or []
            for i, attack_text in enumerate(ar.structured_attacks):
                angle = angles[i] if i < len(angles) else f"Attack {i+1}"
                defense_text = defenses[i] if i < len(defenses) else ""

                # Determine outcome based on whether this attack is fatal
                # Use survived/fatal counts from the LLM's own assessment
                debate_rounds.append(DebateExchange(
                    angle=angle,
                    attack=attack_text,
                    defense=defense_text,
                    outcome="",  # No separate outcome per angle in single-round mode
                ))

            fm_raw = ar.feasibility_matrix or {}
            fm = FeasibilityMatrix(**fm_raw)

            st = StressTestResult(
                idea_id=idea_id,
                freeform_attack=ar.freeform_attack,
                structured_attacks=ar.structured_attacks,
                defenses=ar.defenses,
                debate_rounds=debate_rounds,
                attacks_made=ar.attacks_made or len(ar.structured_attacks),
                attacks_survived=ar.attacks_survived,
                attacks_fatal=ar.attacks_fatal,
                strongest_argument=ar.strongest_argument,
                strongest_defense=ar.strongest_defense,
                suggested_mutation=ar.suggested_mutation,
                feasibility_matrix=fm,
                feasibility_verdict=ar.feasibility_verdict,
                llm_capability_fit=ar.llm_capability_fit,
                kill_criteria=ar.kill_criteria,
                verdict=ar.verdict,
                error_source=getattr(ar, "error_source", ""),
            )
            results.append(st)

            survived = st.attacks_survived
            fatal = st.attacks_fatal
            if st.error_source:
                _log_warn("STRESS", f"  -> CRASH-INCUBATE (API error, not a genuine verdict)")
            else:
                _log_detail("STRESS", f"    -> {survived} survived, {fatal} fatal -> {fmt_verdict(st.verdict)}")

        # ── Programmatic verdict enforcement ────────────────────
        # The LLM tends to hedge with MUTATE even when its own numbers
        # say BUILD.  Enforce the quantitative rule from the prompt:
        # attacks_survived >= 5  AND  attacks_fatal <= 1  →  BUILD
        overrides = 0
        for r in results:
            if (r.verdict == "MUTATE"
                    and r.attacks_survived >= 5
                    and r.attacks_fatal <= 1):
                _log_warn("STRESS", f">> Override {r.idea_id}: MUTATE->BUILD "
                     f"(survived={r.attacks_survived}, fatal={r.attacks_fatal})")
                r.verdict = "BUILD"
                overrides += 1

        _log("STRESS", "")
        verdicts: dict[str, int] = {}
        for r in results:
            verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
        override_note = f" (after {overrides} override(s))" if overrides else ""
        _log_ok("STRESS", f"Verdicts{override_note}: {fmt_verdicts(verdicts)}")

        return results

    def _phase_evolve(
        self,
        survivors: list[IdeaCard],
        stress_results: list[StressTestResult],
        generation: int,
        brief_text: str | None,
    ) -> tuple[list[IdeaCard], list[RawIdea]]:
        """Evolutionary phase: mutate, crossover, and novelty-explore from survivors.

        Returns (elite_cards, evolved_raw_ideas) where elite_cards are carried
        forward unchanged and evolved_raw_ideas need scoring + stress testing.
        """
        _log_phase_header("EVOLVE", f"Generation {generation}/{self.cfg.generations}")

        # Separate by verdict
        build_ideas = [s for s in survivors if s.stress_test_verdict == "BUILD"]
        mutate_ideas = [s for s in survivors if s.stress_test_verdict == "MUTATE"]
        all_passing = build_ideas + mutate_ideas

        if not all_passing:
            _log_warn("EVOLVE", "No survivors to evolve. Skipping.")
            return [], []

        # Elites: top BUILD ideas carry forward unchanged
        elite_count = max(1, len(build_ideas) // 2)
        elites = sorted(build_ideas, key=lambda c: c.composite_score, reverse=True)[:elite_count]
        _log_ok("EVOLVE", f"Elites (carry-forward): {len(elites)}")
        for e in elites:
            _log_verdict("EVOLVE", "BUILD", f"{e.composite_score:.1f} {e.title}")

        # Build survivors JSON with stress test context
        survivors_data = []
        for c in all_passing:
            st = next((s for s in stress_results if s.idea_id == c.id), None)
            entry = {
                "id": c.id,
                "title": c.title,
                "rationale": c.rationale,
                "domain_tags": c.domain_tags,
                "composite_score": c.composite_score,
                "verdict": c.stress_test_verdict,
            }
            if st:
                entry["strongest_argument"] = st.strongest_argument
                entry["strongest_defense"] = st.strongest_defense
                entry["suggested_mutation"] = st.suggested_mutation
                entry["attacks_survived"] = st.attacks_survived
                entry["attacks_fatal"] = st.attacks_fatal
            survivors_data.append(entry)

        survivors_json = json.dumps(survivors_data, indent=2, ensure_ascii=False)
        gene_ctx = build_gene_context(self.memory.get_idea_genes())
        mutation_ctx = build_mutation_archive_context(self.memory.get_mutation_archive())
        brief_ctx = build_brief_context(brief_text)
        evolve_count = max(4, self.cfg.converge_top_n)

        prompt = EVOLVE_USER.format(
            generation=generation,
            max_generations=self.cfg.generations,
            brief_context=brief_ctx,
            survivors_json=survivors_json,
            gene_context=gene_ctx,
            mutation_archive_context=mutation_ctx,
            elite_count=elite_count,
            evolve_count=evolve_count,
        )

        timer = log_llm_call("EVOLVE", f"Evolving generation {generation} ({evolve_count} offspring)")
        data = self.llm.generate_json(
            self._sys(EVOLVE_SYSTEM), prompt, temperature=0.85,
            model_override=self._model_for_phase(PHASE_EVOLVE), phase=PHASE_EVOLVE,
            max_tokens=self._max_tokens_for_phase(PHASE_EVOLVE),
        )
        timer.done()

        # Parse evolved ideas as RawIdeas
        evolved_raw = data.get("evolved_ideas", [])
        evolved_ideas = []
        for item in evolved_raw:
            try:
                idea = RawIdea(**item)
                evolved_ideas.append(idea)
            except Exception:
                _log_warn("EVOLVE", f"Failed to parse evolved idea: {item.get('id', '?')}")

        # Log results
        techniques = {}
        for idea in evolved_ideas:
            techniques[idea.source_technique] = techniques.get(idea.source_technique, 0) + 1
        tech_str = ", ".join(f"{k} ({v})" for k, v in techniques.items())
        _log_ok("EVOLVE", f"{len(evolved_ideas)} evolved ideas: {tech_str}")
        for idx, idea in enumerate(evolved_ideas, 1):
            parents = ", ".join(idea.domain_tags[:2])
            _log_detail("EVOLVE", f"    {idx:>2}. [{idea.source_technique}] {idea.concept[:70]} ({parents})")

        return elites, evolved_ideas

    def _phase_refine(
        self,
        raw_ideas: list[RawIdea],
        candidates: list[IdeaCard],
        stress_results: list[StressTestResult],
        constraints: list[str] | None,
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

        _log_detail("REFINE", f"Mutations extracted: {len(mutations)} suggested improvements from MUTATE verdicts")
        if mutations[:2]:
            for m in mutations[:2]:
                _log_detail("REFINE", f"  - {m['idea_title']}: {m['suggested_mutation'][:80]}")

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

        _log_detail("REFINE", f"Attack patterns identified: {len(attack_patterns)} recurring threat vectors")
        if attack_patterns[:2]:
            for p in attack_patterns[:2]:
                _log_detail("REFINE", f"  - [{p['frequency']}x] {p['pattern'][:70]}")

        _log_ok("REFINE", f"Extracted {len(mutations)} mutations and {len(attack_patterns)} attack patterns")

        # Extract banned concepts: titles + one-line concepts of ALL prior candidates
        banned_concepts = []
        for c in candidates:
            banned_concepts.append(f"{c.title}: {c.rationale[:100] if c.rationale else c.title}")
        _log_detail("REFINE", f"Banned concepts: {len(banned_concepts)} previous ideas will be excluded")

        # Extract problem reframes from stress test structured attacks
        reframe_attacks = []
        for s in stress_results:
            # Check structured_attacks for "Reframe:" or "Problem reframe:" entries
            if s.structured_attacks:
                for attack in s.structured_attacks:
                    attack_lower = attack.lower()
                    if attack_lower.startswith("reframe:") or attack_lower.startswith("problem reframe:"):
                        # Strip the prefix and keep the reframe content
                        reframe_text = attack.split(":", 1)[1].strip() if ":" in attack else attack
                        if reframe_text and len(reframe_text) > 20:
                            reframe_attacks.append(reframe_text)
            # Also check freeform_attack for reframe insights
            if s.freeform_attack and "real problem" in s.freeform_attack.lower():
                # Extract sentences containing the reframe
                for sentence in s.freeform_attack.split("."):
                    if "real problem" in sentence.lower() or "actually about" in sentence.lower():
                        sentence = sentence.strip()
                        if len(sentence) > 20:
                            reframe_attacks.append(sentence)
        # Deduplicate and limit
        reframe_attacks = list(dict.fromkeys(reframe_attacks))[:5]
        _log_detail("REFINE", f"Problem reframes extracted: {len(reframe_attacks)} alternative framings from stress tests")
        if reframe_attacks[:2]:
            for r in reframe_attacks[:2]:
                _log_detail("REFINE", f"  - {r[:80]}")

        # Build refinement context for diverge phase
        refinement_ctx = build_refinement_context(mutations, attack_patterns, banned_concepts, reframe_attacks)
        _log_detail("REFINE", f"Learning context prepared: {len(mutations[:5])} mutations + {len(attack_patterns[:5])} patterns")

        # ── Extract canonical failure types for hard blocklist ────
        failure_types: dict[str, list[str]] = {}
        for s in stress_results:
            if s.verdict in ("KILL", "MUTATE"):
                all_attack_text = " ".join(s.structured_attacks + [s.freeform_attack, s.strongest_argument]).lower()
                for category, keywords in CANONICAL_FAILURE_TYPES.items():
                    if any(kw in all_attack_text for kw in keywords):
                        if category not in failure_types:
                            failure_types[category] = []
                        example = s.strongest_argument or (s.structured_attacks[0] if s.structured_attacks else "")
                        if example and example not in failure_types[category]:
                            failure_types[category].append(example)
        blocklist_ctx = build_failure_blocklist_context(failure_types)
        if failure_types:
            _log_detail("REFINE", f"Failure blocklist: {', '.join(failure_types.keys())}")

        # Use cached context if available, otherwise build fresh
        if cached_context:
            domain_ctx = cached_context["domain"]
            constraint_ctx = cached_context["constraint"]
            memory_ctx = cached_context["memory"]
            immersion_ctx = cached_context["immersion"]
            brief_ctx = cached_context["brief"]
        else:
            domain_ctx = build_domain_context()
            constraint_ctx = build_constraint_context(constraints)
            memory_ctx = build_memory_context(
                self.memory.past_idea_count(),
                self.memory.get_domain_heat_map(),
                self.memory.killed_idea_titles(),
            )
            immersion_ctx = ""
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
            winner_repulsion_context=build_winner_repulsion_context(self.memory.get_previous_winners()),
            failure_taxonomy_context=build_failure_taxonomy_context(self.memory.get_failure_taxonomy()),
            gene_context=build_gene_context(self.memory.get_idea_genes()),
            technique_weight_context=build_technique_weight_context(self.memory.get_technique_weights()),
        )

        # Append failure blocklist (hard constraints) BEFORE soft refinement context
        refined_prompt = prompt
        if blocklist_ctx:
            refined_prompt = refined_prompt + "\n\n" + blocklist_ctx
        refined_prompt = refined_prompt + "\n\n" + refinement_ctx

        # Adjust temperature: less creative on later iterations (more focused on solving problems)
        temperature = max(0.5, 0.9 - (iteration * 0.15))
        _log_detail("REFINE", f"DIVERGE: Generating {diverge_ideas_count} focused ideas (temperature={temperature:.2f})...")
        
        timer = log_llm_call("REFINE", f"Generating {diverge_ideas_count} refined ideas")
        data = self.llm.generate_json(self._sys(DIVERGE_SYSTEM), refined_prompt, temperature=temperature,
                                       model_override=self._model_for_phase(PHASE_REFINE), phase=PHASE_REFINE_DIVERGE,
                                       max_tokens=self._max_tokens_for_phase(PHASE_REFINE_DIVERGE))
        timer.done()
        ideas_raw = data.get("ideas", [])

        refined_raw_ideas = []
        for item in ideas_raw:
            refined_raw_ideas.append(RawIdea(**item))

        techniques = {}
        for idea in refined_raw_ideas:
            techniques[idea.source_technique] = techniques.get(idea.source_technique, 0) + 1
        tech_str = ", ".join(f"{k} ({v})" for k, v in techniques.items())
        _log_ok("REFINE", f"DIVERGE result: {len(refined_raw_ideas)} ideas -- {tech_str}")

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
            novelty_context=build_novelty_context(
                self.memory.get_previous_winners(), self.memory.past_idea_count()
            ),
            brief_context=build_brief_context(self._brief_text),
        )

        _log_detail("REFINE", f"CONVERGE: Scoring {len(refined_raw_ideas)} ideas, selecting top {converge_top_n}...")
        timer = log_llm_call("REFINE", f"Scoring {len(refined_raw_ideas)} refined candidates")
        data = self.llm.generate_json(self._sys(CONVERGE_SYSTEM), prompt, temperature=0.5,
                                       model_override=self._model_for_phase(PHASE_REFINE), phase=PHASE_REFINE_CONVERGE,
                                       max_tokens=self._max_tokens_for_phase(PHASE_REFINE_CONVERGE))
        timer.done()

        clustering = data.get("clustering_summary", "")
        if clustering:
            _log_detail("REFINE", f"  Clustering: {clustering[:100]}...")

        candidates_raw = data.get("candidates", [])
        refined_candidates = []
        for c in candidates_raw:
            card = self._parse_candidate(c)
            refined_candidates.append(card)

        # Apply calibration to refinement candidates too
        apply_calibration(refined_candidates, self.memory.get_score_stats(), tag="REFINE")

        _log_ok("REFINE", f"CONVERGE result: {len(refined_candidates)} candidates ready for stress test")
        for i, c in enumerate(refined_candidates[:3]):
            _log_detail("REFINE", f"  #{i+1} [{c.composite_score:.1f}] {c.title}")

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
        # Clamp all score values to [0, 10] — LLM sometimes returns dollar amounts
        for k, v in list(sb_raw.items()):
            if isinstance(v, (int, float)):
                sb_raw[k] = max(0.0, min(10.0, float(v)))
        sb = ScoreBreakdown(**sb_raw)
        composite = compute_composite_score(sb)

        persona_raw = c.get("primary_persona", {})
        persona = Persona(**persona_raw)

        return IdeaCard(
            id=c.get("id", ""),
            title=c.get("title", ""),
            rationale=c.get("rationale", ""),
            elevator_pitch=c.get("elevator_pitch", ""),
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
            inverse_terrible_conditions=(c.get("inverse_score") or {}).get("terrible_conditions", []),
            inverse_confidence=(c.get("inverse_score") or {}).get("inverse_confidence", 0.0),
            key_assumptions=self._normalize_assumptions(c.get("key_assumptions", [])),
            first_customer_profile=c.get("first_customer_profile", {}),
            cost_context=c.get("cost_context", ""),
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
            _log_warn("MERGE", f"Removed {dupes} duplicate idea(s) by title")
        return unique

    def _write_outputs(self, run_dir: Path, result: IdeateRunResult) -> None:
        """Write all pipeline outputs to disk."""
        # idea-report.md
        cost_info = self.actual_cost()
        report = generate_idea_report(result, cost_info=cost_info)
        report = sanitize_text(report)
        (run_dir / "idea-report.md").write_text(report, encoding="utf-8")

        # idea-cards.json — only survivors with BUILD or INCUBATE
        cards = [c.model_dump() for c in result.survivors]
        (run_dir / "idea-cards.json").write_text(
            json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8",
        )

        # idea-log.json — full trace (includes per-phase cost breakdown)
        log_data = result.model_dump()
        log_data["cost_info"] = cost_info
        (run_dir / "idea-log.json").write_text(
            json.dumps(log_data, indent=2, ensure_ascii=False),
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
        pass_count = sum(1 for c in result.survivors if c.stress_test_verdict in ("BUILD", "MUTATE"))
        metrics = {
            "run_id": result.run_id,
            "timestamp": result.timestamp,
            "ideas_generated": len(result.raw_ideas),
            "candidates": len(result.candidates),
            "build_count": build_count,
            "pass_count": pass_count,
            "tokens_in": result.total_input_tokens,
            "tokens_out": result.total_output_tokens,
        }

        self.memory.save_run(ideas_for_archive, list(domains_used), killed, metrics)

        # Save mutations and attack patterns for refinement learning
        if mutations:
            self.memory.save_mutations(mutations)
        if attack_patterns:
            self.memory.save_attack_patterns(attack_patterns)

        # Classify attacks into failure taxonomy categories
        _FAILURE_CATEGORIES = {
            "prior_art": ["already exists", "prior art", "been done", "existing", "commodity"],
            "adoption": ["nobody will", "won't use", "won't adopt", "adoption", "no demand"],
            "technical": ["impossible", "impractical", "technical", "can't build", "infeasible"],
            "timing": ["too early", "too late", "timing", "window", "obsolete"],
            "defensibility": ["clone", "no moat", "defensib", "competitor", "replicate"],
            "economics": ["cost", "expensive", "revenue", "pricing", "economics", "margin"],
        }
        taxonomy_updates: dict[str, list[str]] = {}
        for s in result.stress_test_results:
            for attack in s.structured_attacks:
                attack_lower = attack.lower()
                for category, keywords in _FAILURE_CATEGORIES.items():
                    if any(kw in attack_lower for kw in keywords):
                        taxonomy_updates.setdefault(category, []).append(
                            attack[:150]
                        )
                        break  # only classify into first matching category
        if taxonomy_updates:
            self.memory.save_failure_taxonomy(taxonomy_updates)

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
    def _normalize_assumptions(raw: list) -> list:
        """Normalize key_assumptions to structured dicts.

        The LLM may return plain strings (old format) or dicts with
        claim/validation_cost/validation_method and optional inversion
        fields (inverse_claim, inverse_defense_quality, fragility_flag).
        Always return a list of dicts sorted by validation cost.
        """
        COST_ORDER = {"low": 0, "medium": 1, "high": 2}
        result = []
        for item in raw:
            if isinstance(item, str):
                entry = {"claim": item, "validation_cost": "medium", "validation_method": ""}
            elif isinstance(item, dict):
                entry = {
                    "claim": item.get("claim", str(item)),
                    "validation_cost": item.get("validation_cost", "medium"),
                    "validation_method": item.get("validation_method", ""),
                }
                # Preserve inversion fields if present
                if "inverse_claim" in item:
                    entry["inverse_claim"] = item["inverse_claim"]
                if "inverse_defense_quality" in item:
                    entry["inverse_defense_quality"] = item["inverse_defense_quality"]
                if "fragility_flag" in item:
                    entry["fragility_flag"] = item["fragility_flag"]
            else:
                entry = {"claim": str(item), "validation_cost": "medium", "validation_method": ""}
            result.append(entry)
        result.sort(key=lambda a: COST_ORDER.get(a.get("validation_cost", "medium"), 1))
        return result

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

    def _max_tokens_for_phase(self, phase: str) -> int:
        """Return the max output-tokens budget for *phase* from config."""
        return self.cfg.PHASE_MAX_TOKENS.get(phase, self.cfg.max_tokens)

    # ------------------------------------------------------------------
    # Async helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_parallel(coros: list, max_concurrent: int = 2) -> list:
        """Run coroutines concurrently with a concurrency limit to avoid rate limits."""
        async def _gather():
            sem = asyncio.Semaphore(max_concurrent)
            async def _limited(idx: int, coro):
                async with sem:
                    if idx > 0:
                        await asyncio.sleep(1.5)  # stagger to avoid burst
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
        has_constraints: bool,
        pricing: dict[str, tuple[float, float]],
        strategy: str = "single",
        cheap_model: str = "",
        generations: int = 1,
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
        _add("diverge", 2000, 4000 + ideas_per_round * 120)
        _add("dedup", 1500 + ideas_per_round * 80, 1500)
        _add("gapfill", 1500, 2000)
        _add("converge", 2000 + ideas_per_round * 80, 5000 + converge_top_n * 500)
        _add("stress", 2000 + converge_top_n * 300, 5000 + converge_top_n * 800)

        # Add evolution loop cost (per extra generation)
        extra_gens = max(0, generations - 1)
        if extra_gens > 0:
            for _ in range(extra_gens):
                _add("evolve", 2000 + converge_top_n * 300, 4000 + converge_top_n * 200)
                _add("converge-evo", 2000 + converge_top_n * 80, 5000 + converge_top_n * 500)
                _add("stress-evo", 2000 + converge_top_n * 300, 5000 + converge_top_n * 800)

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
