"""Output generators for Pipeline 1: human-readable Markdown reports."""

from __future__ import annotations

from xbrain.models import IdeaCard, IdeateRunResult, StressTestResult


def generate_idea_report(result: IdeateRunResult) -> str:
    """Generate idea-report.md — the flagship human-readable output."""
    lines: list[str] = []

    # Header
    lines.append("# xBrain Idea Report")
    lines.append("")
    lines.append(f"**Run ID:** `{result.run_id}`")
    lines.append(f"**Date:** {result.timestamp[:10]}")
    if result.domains:
        lines.append(f"**Focus Domains:** {', '.join(result.domains)}")
    if result.constraints:
        lines.append(f"**Constraints:** {', '.join(result.constraints)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary
    verdicts: dict[str, int] = {}
    for s in result.stress_test_results:
        verdicts[s.verdict] = verdicts.get(s.verdict, 0) + 1

    lines.append("## Summary")
    lines.append(f"- **Ideas Generated:** {len(result.raw_ideas)}")
    lines.append(f"- **After Scoring:** {len(result.candidates)}")
    verdict_str = ", ".join(f"{v} {k}" for k, v in sorted(verdicts.items()))
    lines.append(f"- **Verdicts:** {verdict_str}")
    lines.append("- **Scoring Status:** UNCALIBRATED")
    lines.append(
        f"- **Tokens Used:** {result.total_input_tokens:,} in / "
        f"{result.total_output_tokens:,} out"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Domain briefs summary (if immerse ran)
    if result.domain_briefs:
        lines.append("## Domain Briefs")
        for brief in result.domain_briefs:
            lines.append(f"### {brief.domain.title()}")
            lines.append(f"{brief.summary}")
            if brief.pressure_points:
                lines.append("")
                lines.append("**Pressure Points:**")
                for pp in brief.pressure_points:
                    lines.append(f"- {pp}")
            lines.append("")
        lines.append("---")
        lines.append("")

    # Build a lookup for stress results
    stress_map: dict[str, StressTestResult] = {
        s.idea_id: s for s in result.stress_test_results
    }

    # Detailed cards
    lines.append("## Ideas")
    lines.append("")

    for i, card in enumerate(result.survivors):
        stress = stress_map.get(card.id)
        verdict = card.stress_test_verdict or (stress.verdict if stress else "?")
        emoji = _verdict_emoji(verdict)

        lines.append(f"### {emoji} #{i+1}: {card.title}  (Score: {card.composite_score:.1f})")
        lines.append(f"**Verdict: {verdict}**")
        lines.append("")
        lines.append(f"> {card.rationale}")
        lines.append("")

        # Persona
        p = card.primary_persona
        lines.append(f"**Target Persona:** {p.who}")
        if p.pain:
            lines.append(f"- **Pain:** {p.pain}")
        if p.context:
            lines.append(f"- **Context:** {p.context}")
        if p.motivation:
            lines.append(f"- **Motivation:** {p.motivation}")
        lines.append("")

        # Score table
        _append_score_table(lines, card)
        lines.append("")

        # Stress test details
        if stress:
            _append_stress_details(lines, stress)
            lines.append("")

        # Meta
        lines.append(f"**Domains:** {', '.join(card.domain_tags)}")
        lines.append(f"**Source:** {card.source_technique}")
        lines.append(f"**Novelty:** {card.novelty_score:.2f}")
        lines.append(f"**Estimated Effort:** {card.estimated_effort}")
        lines.append(f"**Estimated Cost:** ${card.estimated_cost_usd_month:.0f}/month")
        if card.sustainability_model:
            lines.append(f"**Sustainability:** {card.sustainability_model}")
        if card.defensibility_notes:
            lines.append(f"**Defensibility:** {card.defensibility_notes}")
        if card.market_timing_notes:
            lines.append(f"**Market Timing:** {card.market_timing_notes}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Next steps
    _append_next_steps(lines, result)

    return "\n".join(lines)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _verdict_emoji(verdict: str) -> str:
    return {
        "BUILD": "\U0001f3c6",      # 🏆
        "INCUBATE": "\U0001f504",    # 🔄
        "MUTATE": "\u26a1",          # ⚡
        "KILL": "\u274c",            # ❌
    }.get(verdict, "❓")


def _append_score_table(lines: list[str], card: IdeaCard) -> None:
    sb = card.score_breakdown
    lines.append("| Dimension | Score | Direction |")
    lines.append("|-----------|-------|-----------|")
    lines.append(f"| Impact | {sb.impact:.1f} | (+) |")
    lines.append(f"| Confidence | {sb.confidence:.1f} | (+) |")
    lines.append(f"| Sustainability | {sb.sustainability:.1f} | (+) |")
    lines.append(f"| Defensibility | {sb.defensibility:.1f} | (+) |")
    lines.append(f"| Market Timing | {sb.market_timing:.1f} | (+) |")
    lines.append(f"| Effort | {sb.effort:.1f} | (-) |")
    lines.append(f"| Cost | {sb.cost:.1f} | (-) |")
    lines.append(f"| Ethical Risk | {sb.ethical_risk:.1f} | (-) |")
    lines.append(f"| **Composite** | **{card.composite_score:.1f}** | |")


def _append_stress_details(lines: list[str], stress: StressTestResult) -> None:
    lines.append("**Stress Test:**")
    lines.append(
        f"- Attacks: {stress.attacks_made} | Survived: {stress.attacks_survived} "
        f"| Fatal: {stress.attacks_fatal}"
    )
    if stress.strongest_argument:
        lines.append(f"- **Strongest Attack:** {stress.strongest_argument}")
    if stress.strongest_defense:
        lines.append(f"- **Strongest Defense:** {stress.strongest_defense}")
    if stress.suggested_mutation:
        lines.append(f"- **Suggested Mutation:** {stress.suggested_mutation}")
    lines.append("")

    # Feasibility matrix
    fm = stress.feasibility_matrix
    lines.append("**Feasibility Matrix** (1-5, higher = better):")
    lines.append("| Dimension | Score |")
    lines.append("|-----------|-------|")
    lines.append(f"| Technical Risk | {fm.technical_risk} |")
    lines.append(f"| Data Availability | {fm.data_availability} |")
    lines.append(f"| Regulatory Risk | {fm.regulatory_risk} |")
    lines.append(f"| Cost (infra/month) | {fm.cost_infra_month} |")
    lines.append(f"| Time to Prototype | {fm.time_to_prototype} |")
    lines.append(f"| Maintenance Burden | {fm.maintenance_burden} |")
    lines.append(f"| LLM Capability Fit | {fm.llm_capability_fit} |")
    lines.append(f"| Defensibility | {fm.defensibility} |")
    lines.append(f"| Market Timing | {fm.market_timing} |")
    lines.append("")

    if stress.kill_criteria:
        lines.append("**Build-Phase Kill Criteria:**")
        for kc in stress.kill_criteria:
            lines.append(f"- {kc}")


def _append_next_steps(lines: list[str], result: IdeateRunResult) -> None:
    lines.append("## Next Steps")
    lines.append("")

    build_ideas = [
        c for c in result.survivors if c.stress_test_verdict == "BUILD"
    ]

    if build_ideas:
        best = build_ideas[0]
        lines.append(
            f"**{len(build_ideas)} idea(s)** survived with BUILD verdict. "
            "Pick one and produce a project specification:"
        )
        lines.append("")
        lines.append("```bash")
        lines.append(
            f"python -m xbrain specify "
            f"--idea ./xbrain-runs/{result.run_id}/idea-cards.json "
            f"--select {best.id}"
        )
        lines.append("```")
    else:
        lines.append("No ideas received a BUILD verdict. Consider:")
        lines.append("- Running `python -m xbrain ideate` again with different domains/constraints")
        lines.append("- Reviewing INCUBATE or MUTATE ideas for potential")
    lines.append("")
