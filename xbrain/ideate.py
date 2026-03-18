"""Pipeline 1: IDEATE — the main orchestrator for idea generation."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from xbrain.config import Config
from xbrain.llm import LLMClient
from xbrain.memory import MemoryStore
from xbrain.models import (
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
    CONVERGE_SYSTEM,
    CONVERGE_USER,
    DIVERGE_SYSTEM,
    DIVERGE_USER,
    IMMERSE_SYSTEM,
    IMMERSE_USER,
    STRESS_TEST_SYSTEM,
    STRESS_TEST_USER,
    build_brief_context,
    build_constraint_context,
    build_domain_context,
    build_immersion_context,
    build_memory_context,
)


def _log(tag: str, msg: str) -> None:
    print(f"[{tag:<9s}] {msg}")
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
    ) -> Path:
        """Execute the full ideation pipeline and return the run directory."""
        run_id = self._make_run_id()
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

        result = IdeateRunResult(
            run_id=run_id,
            domains=domains or [],
            constraints=constraints or [],
        )

        # Phase 0 — Immerse (optional)
        domain_briefs: list[DomainBrief] = []
        if domains:
            domain_briefs = self._phase_immerse(domains)
            result.domain_briefs = domain_briefs

        # Phase 1 — Diverge
        raw_ideas = self._phase_diverge(domains, constraints, domain_briefs, brief_text)
        result.raw_ideas = raw_ideas

        # Phase 2 — Converge
        candidates = self._phase_converge(raw_ideas)
        result.candidates = candidates

        # Phase 3 — Stress Test
        stress_results = self._phase_stress_test(candidates)
        result.stress_test_results = stress_results

        # Merge stress results into candidates to produce survivors
        survivors = self._merge_survivors(candidates, stress_results)
        result.survivors = survivors

        # Token totals
        result.total_input_tokens = self.llm.total_input_tokens
        result.total_output_tokens = self.llm.total_output_tokens

        # Write outputs
        self._write_outputs(run_dir, result)

        # Persist to memory
        self._update_memory(result)

        # Print completion
        build_count = sum(1 for s in stress_results if s.verdict == "BUILD")
        _log("IDEATE", f"Pipeline 1 finished.  {build_count} ideas with BUILD verdict.")
        _log("IDEATE", f"Reports written to {run_dir}/")
        _log("IDEATE", f"  idea-report.md  — human-readable ranked report")
        _log("IDEATE", f"  idea-cards.json  — machine-readable Idea Cards")
        _log("IDEATE", f"  idea-log.json    — full trace")
        _log("IDEATE", f"  stress-test-report.json — adversarial analysis")
        _log("IDEATE", "")
        _log("IDEATE", "Review the report. When ready, run:")
        _log(
            "IDEATE",
            f"  python -m xbrain specify --idea {run_dir}/idea-cards.json --select <idea-id>",
        )
        _log("IDEATE", f"Tokens used: {result.total_input_tokens:,} in / {result.total_output_tokens:,} out")

        return run_dir

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    def _phase_immerse(self, domains: list[str]) -> list[DomainBrief]:
        _log("IMMERSE", f"Deep-diving into: {', '.join(domains)}")

        prompt = IMMERSE_USER.format(domains=", ".join(domains))
        data = self.llm.generate_json(IMMERSE_SYSTEM, prompt, temperature=0.6)
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

        domain_ctx = build_domain_context(domains, self.cfg.ALL_DOMAINS)
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
        )

        data = self.llm.generate_json(DIVERGE_SYSTEM, prompt, temperature=0.9)
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

    def _phase_converge(self, raw_ideas: list[RawIdea]) -> list[IdeaCard]:
        _log("CONVERGE", f"Clustering and scoring {len(raw_ideas)} ideas...")

        ideas_json = json.dumps(
            [i.model_dump() for i in raw_ideas], indent=2, ensure_ascii=False,
        )

        prompt = CONVERGE_USER.format(
            idea_count=len(raw_ideas),
            top_n=self.cfg.converge_top_n,
            ideas_json=ideas_json,
        )

        data = self.llm.generate_json(CONVERGE_SYSTEM, prompt, temperature=0.5)

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
            _log("CONVERGE", f"  #{i+1} [{c.composite_score:.1f}] \"{c.title}\" — {', '.join(c.domain_tags)}")

        return candidates

    def _phase_stress_test(self, candidates: list[IdeaCard]) -> list[StressTestResult]:
        _log("STRESS", f"Devil's Advocate attacking {len(candidates)} candidates...")

        candidates_json = json.dumps(
            [
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
            ],
            indent=2,
            ensure_ascii=False,
        )

        prompt = STRESS_TEST_USER.format(
            candidate_count=len(candidates),
            candidates_json=candidates_json,
        )

        data = self.llm.generate_json(STRESS_TEST_SYSTEM, prompt, temperature=0.4)

        results_raw = data.get("results", [])
        results = []
        for r in results_raw:
            st = self._parse_stress_result(r)
            results.append(st)
            _log(
                "STRESS",
                f"  {st.idea_id}: ATTACKS {st.attacks_made}, "
                f"SURVIVED {st.attacks_survived} → {st.verdict}",
            )

        verdicts = {}
        for r in results:
            verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
        _log("STRESS", f"  Verdicts: {verdicts}")

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
        """Merge stress test results into candidate cards and return all (sorted by score)."""
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
        return survivors

    def _write_outputs(self, run_dir: Path, result: IdeateRunResult) -> None:
        """Write all pipeline outputs to disk."""
        # idea-report.md
        report = generate_idea_report(result)
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
            {"id": c.id, "title": c.title, "score": c.composite_score, "verdict": c.stress_test_verdict}
            for c in result.survivors
        ]
        killed = [
            {"id": c.id, "title": c.title, "reason": next(
                (s.strongest_argument for s in result.stress_test_results if s.idea_id == c.id), ""),
            }
            for c in result.survivors if c.stress_test_verdict == "KILL"
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

    @staticmethod
    def _make_run_id() -> str:
        return "run-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
