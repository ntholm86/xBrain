"""Output generators for Pipeline 1: human-readable Markdown reports."""

from __future__ import annotations

import csv
import io
import json

from xbrain.models import IdeaCard, IdeateRunResult, StressTestResult


def generate_idea_report(result: IdeateRunResult, cost_info: dict | None = None) -> str:
    """Generate idea-report.md — the flagship human-readable output."""
    lines: list[str] = []

    # Header
    lines.append("# xBrain Idea Report")
    lines.append("")
    lines.append(f"**Run ID:** `{result.run_id}`")
    lines.append(f"**Date:** {result.timestamp[:10]}")
    if result.brief_text:
        lines.append("")
        lines.append("**Original Brief:**")
        lines.append(f"> {result.brief_text}")
        lines.append("")
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
    # Determine calibration status from candidates
    cal_statuses = {c.scoring_calibration_status for c in result.survivors if c.scoring_calibration_status}
    cal_status = "CALIBRATED" if "calibrated" in cal_statuses else "UNCALIBRATED"
    lines.append(f"- **Scoring Status:** {cal_status}")
    lines.append(
        f"- **Tokens Used:** {result.total_input_tokens:,} in / "
        f"{result.total_output_tokens:,} out"
    )
    if cost_info:
        lines.append(f"- **Actual Cost:** ${cost_info['total_cost_usd']:.4f}")
    lines.append("")

    # Per-phase cost breakdown table
    if cost_info and cost_info.get("phases"):
        lines.append("### Cost Breakdown")
        lines.append("")
        lines.append("| Phase | Model | Input | Output | Cost |")
        lines.append("|-------|-------|------:|-------:|-----:|")
        for p in cost_info["phases"]:
            model_short = p["model"].split("-")[1] if "-" in p["model"] else p["model"]
            lines.append(
                f"| {p['phase']} | {model_short} | "
                f"{p['input_tokens']:,} | {p['output_tokens']:,} | "
                f"${p['cost_usd']:.4f} |"
            )
        lines.append("")

    # Sort survivors for comparative summary
    sorted_survivors = sorted(result.survivors, key=lambda c: c.composite_score, reverse=True)
    
    # Build a lookup for stress results (needed for all summaries)
    stress_map: dict[str, StressTestResult] = {
        s.idea_id: s for s in result.stress_test_results
    }
    
    # Comparative Summary
    if sorted_survivors:
        lines.append("### Comparative Summary")
        best_impact = max((c.score_breakdown.impact for c in sorted_survivors), default=0)
        best_confidence = max((c.score_breakdown.confidence for c in sorted_survivors), default=0)
        
        # Find ideas with best metrics
        highest_impact = next((c for c in sorted_survivors if c.score_breakdown.impact == best_impact), None)
        highest_conf = next((c for c in sorted_survivors if c.score_breakdown.confidence == best_confidence), None)
        
        if highest_impact:
            lines.append(f"- **Highest Impact:** {highest_impact.title} ({best_impact:.1f})")
        if highest_conf:
            lines.append(f"- **Highest Confidence:** {highest_conf.title} ({best_confidence:.1f})")
        
        # Effort-Impact Quadrant
        lines.append("")
        lines.append("### Effort-Impact Quadrant")
        effort_threshold = 5.0  # Low effort threshold
        impact_threshold = 7.5  # High impact threshold
        
        quick_wins = [c for c in sorted_survivors if c.score_breakdown.impact > impact_threshold and c.score_breakdown.effort > effort_threshold]
        strategic = [c for c in sorted_survivors if c.score_breakdown.impact > impact_threshold and c.score_breakdown.effort <= effort_threshold]
        low_impact = [c for c in sorted_survivors if c.score_breakdown.impact <= impact_threshold]
        
        if strategic:
            lines.append(f"- **Quick Wins** (High Impact, Lower Effort): {', '.join(c.title for c in strategic[:2])}")
        if quick_wins:
            lines.append(f"- **Strategic** (High Impact, High Effort): {', '.join(c.title for c in quick_wins[:2])}")
        if low_impact:
            lines.append(f"- **Blue Sky** (Interesting but lower priority): {', '.join(c.title for c in low_impact[:2])}")
        
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

    # Ideas at a Glance
    lines.append("## Ideas at a Glance")
    lines.append("")
    # Add Gen column only when multi-generation run
    has_evolution = any(c.generation > 1 for c in sorted_survivors)
    if has_evolution:
        lines.append("| # | Title | Score | Effort | Verdict | Gen |")
        lines.append("|---|-------|-------|--------|---------|-----|")
    else:
        lines.append("| # | Title | Score | Effort | Verdict |")
        lines.append("|---|-------|-------|--------|---------|")
    for i, card in enumerate(sorted_survivors):
        stress_entry = stress_map.get(card.id)
        verdict = card.stress_test_verdict or (stress_entry.verdict if stress_entry else "?")
        if stress_entry and stress_entry.error_source:
            verdict = f"{verdict} (! {stress_entry.error_source})"
        title_cell = f"{card.title[:50]}{'...' if len(card.title) > 50 else ''}"
        if has_evolution:
            lines.append(f"| {i+1} | {title_cell} | {card.composite_score:.1f} | {card.estimated_effort} | {verdict} | {card.generation} |")
        else:
            lines.append(f"| {i+1} | {title_cell} | {card.composite_score:.1f} | {card.estimated_effort} | {verdict} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Detailed cards
    lines.append("## Ideas")
    lines.append("")

    for i, card in enumerate(sorted_survivors):
        stress = stress_map.get(card.id)
        verdict = card.stress_test_verdict or (stress.verdict if stress else "?")
        if stress and stress.error_source:
            verdict = f"{verdict} (! {stress.error_source})"
        emoji = _verdict_emoji(verdict)

        lines.append(f"### {emoji} #{i+1}: {card.title}  (Score: {card.composite_score:.1f})")
        lines.append(f"**Verdict: {verdict}**")
        lines.append("")
        lines.append(f"> {card.elevator_pitch or card.rationale}")
        lines.append("")

        # Quick Reference Card
        sb = card.score_breakdown
        lines.append("**Quick Reference:**")
        cost_label = card.cost_context if card.cost_context else "monthly"
        lines.append(f"- **Composite Score:** {card.composite_score:.1f} | **Effort:** {card.estimated_effort} | **Cost:** ${card.estimated_cost_usd_month:.0f} ({cost_label})")
        market_snippet = (card.market_timing_notes[:60] + "...") if card.market_timing_notes and len(card.market_timing_notes) > 60 else (card.market_timing_notes or "TBD")
        lines.append(f"- **Novelty:** {card.novelty_score:.2f} | **Confidence:** {sb.confidence:.1f}/10 | **Timing:** {market_snippet}")
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

        # First Customer Profile (ICP)
        icp = card.first_customer_profile
        if icp:
            lines.append("**First Customer Profile (ICP):**")
            lines.append(f"- **Type:** {icp.get('type', 'Early adopter with acute pain point')}")
            lines.append(f"- **Size:** {icp.get('size', 'Varies')}")
            lines.append(f"- **Readiness:** {icp.get('readiness', 'High technical literacy')}")
            if icp.get("why_first"):
                lines.append(f"- **Why First:** {icp['why_first']}")
        else:
            lines.append("**First Customer Profile (ICP):**")
            lines.append("- **Type:** Early adopter with acute pain point in domain")
            lines.append("- **Size:** Varies")
            lines.append("- **Readiness:** High technical literacy, willing to pilot new tools")
        lines.append("")

        # Score table
        _append_score_table(lines, card)
        lines.append("")

        # Key Assumptions
        lines.append("**Key Assumptions (Critical Unknowns):**")
        if card.key_assumptions:
            for j, assumption in enumerate(card.key_assumptions, 1):
                if isinstance(assumption, dict):
                    claim = assumption.get("claim", str(assumption))
                    cost = assumption.get("validation_cost", "")
                    method = assumption.get("validation_method", "")
                    cost_badge = f" `[{cost}]`" if cost else ""
                    method_suffix = f" -- *{method}*" if method else ""
                    fragility = assumption.get("fragility_flag", "")
                    frag_badge = f" {'[!]' if fragility == 'fragile' else '[ok]'}" if fragility else ""
                    lines.append(f"{j}. {claim}{cost_badge}{frag_badge}{method_suffix}")
                    inverse = assumption.get("inverse_claim", "")
                    if inverse:
                        defense_q = assumption.get("inverse_defense_quality", "")
                        q_note = f" (defense: {defense_q}/5)" if defense_q else ""
                        lines.append(f"   - *Inverse:* {inverse}{q_note}")
                else:
                    lines.append(f"{j}. {assumption}")
        else:
            lines.append("1. Core value proposition resonates with target persona")
            lines.append("2. Technical approach is feasible within stated effort")
            lines.append("3. No blocking regulatory or legal constraints")
        lines.append("")

        # Stress test details
        if stress:
            _append_stress_details(lines, stress)
            lines.append("")

        # Competitive Landscape
        if card.defensibility_notes:
            lines.append("**Competitive Landscape:**")
            defense_snippet = (card.defensibility_notes[:150] + "...") if len(card.defensibility_notes) > 150 else card.defensibility_notes
            lines.append(f"- {defense_snippet}")
            lines.append("")

        # Timeline Alignment
        lines.append("**Timeline Alignment:**")
        if "high" in card.estimated_effort.lower():
            lines.append("- **Status:** \"Build in 18+ months\" -- strategic play, significant R&D required")
            lines.append("- **Trigger:** Wait for market consolidation or customer pressure to validate")
        elif "medium" in card.estimated_effort.lower():
            lines.append("- **Status:** \"Build in 12-18 months\" -- moderate scope, prove MVP first")
            lines.append("- **Trigger:** Validate customer fit with 2-3 pilot interviews")
        else:
            lines.append("- **Status:** \"Quick prototype in 4-8 weeks\" -- low-risk validation possible")
            lines.append("- **Trigger:** Run spike immediately if strategic fit is high")
        lines.append("")

        # Meta
        lines.append(f"**Domains:** {', '.join(card.domain_tags)}")
        lines.append(f"**Source:** {card.source_technique}")
        if card.generation > 1:
            lines.append(f"**Generation:** {card.generation}")
            if card.evolution_rationale:
                lines.append(f"**Evolution Operator:** {card.evolution_rationale}")
            if card.parent_ideas:
                lines.append(f"**Parent Ideas:** {', '.join(card.parent_ideas)}")
        lines.append(f"**Novelty:** {card.novelty_score:.2f}")
        lines.append(f"**Estimated Effort:** {card.estimated_effort}")
        cost_label = card.cost_context if card.cost_context else "monthly"
        lines.append(f"**Estimated Cost:** ${card.estimated_cost_usd_month:.0f} ({cost_label})")
        if card.sustainability_model:
            lines.append(f"**Sustainability:** {card.sustainability_model}")
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
        "BUILD": "[BUILD]",
        "INCUBATE": "[INCUBATE]",
        "MUTATE": "[MUTATE]",
        "KILL": "[KILL]",
    }.get(verdict, "[?]")


def _append_score_table(lines: list[str], card: IdeaCard) -> None:
    sb = card.score_breakdown
    sr = card.score_reasoning
    has_reasoning = bool(sr)

    if has_reasoning:
        lines.append("| Dimension | Score | Direction | Reasoning |")
        lines.append("|-----------|-------|-----------|-----------|")
    else:
        lines.append("| Dimension | Score | Direction |")
        lines.append("|-----------|-------|-----------|")

    dims = [
        ("Impact", sb.impact, "(+)", "impact"),
        ("Confidence", sb.confidence, "(+)", "confidence"),
        ("Sustainability", sb.sustainability, "(+)", "sustainability"),
        ("Defensibility", sb.defensibility, "(+)", "defensibility"),
        ("Market Timing", sb.market_timing, "(+)", "market_timing"),
        ("Effort", sb.effort, "(-)", "effort"),
        ("Cost", sb.cost, "(-)", "cost"),
        ("Ethical Risk", sb.ethical_risk, "(-)", "ethical_risk"),
    ]

    for label, val, direction, key in dims:
        reason = sr.get(key, "")
        if has_reasoning and reason:
            lines.append(f"| {label} | {val:.1f} | {direction} | {reason} |")
        elif has_reasoning:
            lines.append(f"| {label} | {val:.1f} | {direction} | - |")
        else:
            lines.append(f"| {label} | {val:.1f} | {direction} |")

    if has_reasoning:
        lines.append(f"| **Composite** | **{card.composite_score:.1f}** | | |")
    else:
        lines.append(f"| **Composite** | **{card.composite_score:.1f}** | |")

    if card.inverse_terrible_conditions:
        lines.append("")
        lines.append(f"**Inverse Score (Fragility Check):** {card.inverse_confidence:.1f}/10")
        lines.append("")
        for cond in card.inverse_terrible_conditions:
            lines.append(f"- [!] {cond}")


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

    # Adversarial Debate
    if stress.debate_rounds:
        lines.append("#### Adversarial Debate")
        lines.append("")

        for rnd in stress.debate_rounds:
            outcome_label = rnd.outcome.upper() if rnd.outcome else ""
            if outcome_label:
                lines.append(f"**{rnd.angle}** -- *{outcome_label}*")
            else:
                lines.append(f"**{rnd.angle}**")
            if rnd.attack:
                lines.append(f"> **Attacker:** {rnd.attack}")
            if rnd.defense:
                lines.append(f"> **Defender:** {rnd.defense}")
            if rnd.attacker_rebuttal:
                lines.append(f"> **Attacker (rebuttal):** {rnd.attacker_rebuttal}")
            if rnd.defender_rebuttal:
                lines.append(f"> **Defender (rebuttal):** {rnd.defender_rebuttal}")
            lines.append("")
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


# ------------------------------------------------------------------
# Export generators (PMO Bridge)
# ------------------------------------------------------------------

def export_csv(cards: list[dict], stress_data: list[dict]) -> str:
    """Export ideas as CSV importable into Jira/Linear/Asana."""
    stress_map = {s["idea_id"]: s for s in stress_data}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "ID", "Title", "Description", "Score", "Verdict", "Effort",
        "Est. Cost ($/mo)", "Domains", "Persona", "Pain Point",
        "Kill Criteria", "Priority",
    ])

    for card in cards:
        sid = card.get("id", "")
        stress = stress_map.get(sid, {})
        sb = card.get("score_breakdown", {})
        persona = card.get("primary_persona", {})
        kill = stress.get("kill_criteria", [])

        # Map score to priority
        score = card.get("composite_score", 0)
        priority = "Critical" if score >= 7.5 else "High" if score >= 6.5 else "Medium" if score >= 5.5 else "Low"

        writer.writerow([
            sid,
            card.get("title", ""),
            card.get("elevator_pitch") or card.get("rationale", ""),
            f"{score:.1f}",
            card.get("stress_test_verdict", ""),
            card.get("estimated_effort", ""),
            f"{card.get('estimated_cost_usd_month', 0):.0f}",
            ", ".join(card.get("domain_tags", [])),
            persona.get("who", ""),
            persona.get("pain", ""),
            "; ".join(kill[:3]),
            priority,
        ])

    return buf.getvalue()


def export_markdown_tasks(cards: list[dict], stress_data: list[dict]) -> str:
    """Export ideas as a markdown task list for project management."""
    stress_map = {s["idea_id"]: s for s in stress_data}
    lines: list[str] = []

    lines.append("# xBrain - Project Task Export")
    lines.append("")

    for card in cards:
        sid = card.get("id", "")
        title = card.get("title", "")
        score = card.get("composite_score", 0)
        verdict = card.get("stress_test_verdict", "")
        effort = card.get("estimated_effort", "")
        persona = card.get("primary_persona", {})
        stress = stress_map.get(sid, {})

        lines.append(f"## [{verdict}] {title} (Score: {score:.1f})")
        lines.append("")
        lines.append(f"> {card.get('elevator_pitch') or card.get('rationale', '')}")
        lines.append("")
        lines.append(f"- **Effort:** {effort}")
        lines.append(f"- **Est. Cost:** ${card.get('estimated_cost_usd_month', 0):.0f}/mo")
        lines.append(f"- **Target User:** {persona.get('who', 'TBD')}")
        lines.append(f"- **Pain:** {persona.get('pain', 'TBD')}")
        lines.append("")

        # Tasks
        lines.append("### Tasks")
        lines.append("")
        lines.append(f"- [ ] Validate customer fit (interview 2-3 target personas)")
        lines.append(f"- [ ] Design MVP scope and architecture")
        lines.append(f"- [ ] Build prototype ({effort} effort)")
        lines.append(f"- [ ] Run pilot with early adopters")
        lines.append("")

        # Kill criteria as acceptance gates
        kill = stress.get("kill_criteria", [])
        if kill:
            lines.append("### Kill Criteria (abort if true)")
            lines.append("")
            for kc in kill:
                lines.append(f"- [ ] {kc}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def export_jira_json(cards: list[dict], stress_data: list[dict]) -> str:
    """Export ideas as Jira-compatible JSON (bulk import format)."""
    stress_map = {s["idea_id"]: s for s in stress_data}
    issues = []

    for card in cards:
        sid = card.get("id", "")
        stress = stress_map.get(sid, {})
        score = card.get("composite_score", 0)
        persona = card.get("primary_persona", {})
        kill = stress.get("kill_criteria", [])

        priority = "Critical" if score >= 7.5 else "High" if score >= 6.5 else "Medium" if score >= 5.5 else "Low"

        description_parts = [
            card.get("elevator_pitch") or card.get("rationale", ""),
            "",
            f"*Score:* {score:.1f} | *Effort:* {card.get('estimated_effort', '')} | *Verdict:* {card.get('stress_test_verdict', '')}",
            "",
            f"*Target Persona:* {persona.get('who', '')}",
            f"*Pain Point:* {persona.get('pain', '')}",
        ]

        if kill:
            description_parts.extend(["", "*Kill Criteria:*"])
            for kc in kill:
                description_parts.append(f"* {kc}")

        issues.append({
            "summary": card.get("title", ""),
            "description": "\n".join(description_parts),
            "priority": priority,
            "labels": card.get("domain_tags", []),
            "issueType": "Story",
        })

    return json.dumps({"issues": issues}, indent=2, ensure_ascii=False)
