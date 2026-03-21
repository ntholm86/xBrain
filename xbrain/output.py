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
    lines.append(f"**Run ID:** `{result.run_id}` | **Date:** {result.timestamp[:10]}")
    if result.brief_text:
        lines.append(f"> {result.brief_text}")
    if result.constraints:
        lines.append(f"**Constraints:** {', '.join(result.constraints)}")
    lines.append("")

    # Summary
    verdicts: dict[str, int] = {}
    for s in result.stress_test_results:
        verdicts[s.verdict] = verdicts.get(s.verdict, 0) + 1

    lines.append("## Summary")
    lines.append(f"- **Generated:** {len(result.raw_ideas)} | **Scored:** {len(result.candidates)}")
    verdict_str = ", ".join(f"{_verdict_emoji(k)} {v} {k}" for k, v in sorted(verdicts.items()))
    lines.append(f"- **Verdicts:** {verdict_str}")
    # Determine calibration status from candidates
    cal_statuses = {c.scoring_calibration_status for c in result.survivors if c.scoring_calibration_status}
    cal_status = "CALIBRATED" if "calibrated" in cal_statuses else "UNCALIBRATED"
    lines.append(f"- **Scoring Status:** {cal_status}")
    tokens_line = f"- **Tokens:** {result.total_input_tokens:,} in / {result.total_output_tokens:,} out"
    if cost_info:
        tokens_line += f" | **Cost:** ${cost_info['total_cost_usd']:.4f}"
    lines.append(tokens_line)

    # Per-phase cost breakdown table
    if cost_info and cost_info.get("phases"):
        lines.append("")
        lines.append("### Cost Breakdown")
        # Aggregate by phase
        phase_agg: dict[str, dict] = {}
        for p in cost_info["phases"]:
            key = p["phase"]
            model_short = p["model"].split("-")[1] if "-" in p["model"] else p["model"]
            if key not in phase_agg:
                phase_agg[key] = {"calls": 0, "model": model_short, "input": 0, "output": 0, "cost": 0.0}
            phase_agg[key]["calls"] += 1
            phase_agg[key]["input"] += p["input_tokens"]
            phase_agg[key]["output"] += p["output_tokens"]
            phase_agg[key]["cost"] += p["cost_usd"]
        lines.append("| Phase | Calls | Model | Input | Output | Cost |")
        lines.append("|-------|------:|-------|------:|-------:|-----:|")
        for phase_name, agg in phase_agg.items():
            lines.append(
                f"| {phase_name} | {agg['calls']} | {agg['model']} | "
                f"{agg['input']:,} | {agg['output']:,} | "
                f"${agg['cost']:.4f} |"
            )

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

    # Domain briefs summary (if immerse ran)
    if result.domain_briefs:
        lines.append("---")
        lines.append("## Domain Briefs")
        for brief in result.domain_briefs:
            lines.append(f"### {brief.domain.title()}")
            lines.append(f"{brief.summary}")
            if brief.pressure_points:
                lines.append("**Pressure Points:**")
                for pp in brief.pressure_points:
                    lines.append(f"- {pp}")
            lines.append("")

    # Ideas at a Glance
    lines.append("---")
    lines.append("## Ideas at a Glance")
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
        verdict_display = f"{_verdict_emoji(verdict.split()[0])} {verdict}"
        title_cell = f"{card.title[:50]}{'...' if len(card.title) > 50 else ''}"
        if has_evolution:
            lines.append(f"| {i+1} | {title_cell} | {card.composite_score:.1f} | {card.estimated_effort} | {verdict_display} | {card.generation} |")
        else:
            lines.append(f"| {i+1} | {title_cell} | {card.composite_score:.1f} | {card.estimated_effort} | {verdict_display} |")

    # Detailed cards
    lines.append("")
    lines.append("---")
    lines.append("## Ideas")

    for i, card in enumerate(sorted_survivors):
        stress = stress_map.get(card.id)
        verdict = card.stress_test_verdict or (stress.verdict if stress else "?")
        if stress and stress.error_source:
            verdict = f"{verdict} (! {stress.error_source})"
        emoji = _verdict_emoji(verdict.split()[0])

        lines.append(f"### {emoji} #{i+1}: {card.title}  (Score: {card.composite_score:.1f})")
        lines.append(f"**Verdict: {emoji} {verdict}**")
        lines.append(f"> {card.elevator_pitch or card.rationale}")

        # Quick Reference Card
        sb = card.score_breakdown
        cost_label = card.cost_context if card.cost_context else "monthly"
        market_snippet = (card.market_timing_notes[:60] + "...") if card.market_timing_notes and len(card.market_timing_notes) > 60 else (card.market_timing_notes or "TBD")
        lines.append(f"**Score:** {card.composite_score:.1f} | **Effort:** {card.estimated_effort} | **Cost:** ${card.estimated_cost_usd_month:.0f} ({cost_label}) | **Novelty:** {card.novelty_score:.2f} | **Confidence:** {sb.confidence:.1f}/10 | **Timing:** {market_snippet}")

        # Persona
        p = card.primary_persona
        lines.append(f"**Target Persona:** {p.who}")
        if p.pain:
            lines.append(f"- **Pain:** {p.pain}")
        if p.context:
            lines.append(f"- **Context:** {p.context}")
        if p.motivation:
            lines.append(f"- **Motivation:** {p.motivation}")

        # First Customer Profile (ICP)
        icp = card.first_customer_profile
        if icp:
            lines.append(f"**ICP:** {icp.get('type', 'Early adopter')} | Size: {icp.get('size', 'Varies')} | Readiness: {icp.get('readiness', 'High')}")
            if icp.get("why_first"):
                lines.append(f"- **Why First:** {icp['why_first']}")
        else:
            lines.append("**ICP:** Early adopter with acute pain point | Size: Varies | Readiness: High")

        # Score table
        _append_score_table(lines, card)

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

        # Stress test details
        if stress:
            _append_stress_details(lines, stress)

        # Competitive Landscape
        if card.defensibility_notes:
            lines.append(f"**Competitive Landscape:** {card.defensibility_notes}")

        # Meta (trimmed — effort/cost/novelty already in Quick Reference)
        meta_parts = [f"Domains: {', '.join(card.domain_tags)}", f"Source: {card.source_technique}"]
        if card.generation > 1:
            meta_parts.append(f"Gen: {card.generation}")
            if card.evolution_rationale:
                meta_parts.append(f"Evolution: {card.evolution_rationale}")
            if card.parent_ideas:
                meta_parts.append(f"Parents: {', '.join(card.parent_ideas)}")
        lines.append(f"**{' | '.join(meta_parts)}**")
        if card.sustainability_model:
            lines.append(f"**Sustainability:** {card.sustainability_model}")
        lines.append("")
        lines.append("---")

    # Next steps
    _append_next_steps(lines, result)

    return "\n".join(lines)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _verdict_emoji(verdict: str) -> str:
    return {
        "BUILD": "\u2705",
        "INCUBATE": "\U0001f9ea",
        "MUTATE": "\U0001f9ec",
        "KILL": "\u274c",
    }.get(verdict, "\u2753")


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
        lines.append(f"**Inverse Score (Fragility Check):** {card.inverse_confidence:.1f}/10")
        for cond in card.inverse_terrible_conditions:
            lines.append(f"- [!] {cond}")


def _append_stress_details(lines: list[str], stress: StressTestResult) -> None:
    lines.append(
        f"**Stress Test:** Attacks: {stress.attacks_made} | "
        f"Survived: {stress.attacks_survived} | Fatal: {stress.attacks_fatal}"
    )
    if stress.strongest_argument:
        lines.append(f"- **Strongest Attack:** {stress.strongest_argument}")
    if stress.strongest_defense:
        lines.append(f"- **Strongest Defense:** {stress.strongest_defense}")
    if stress.suggested_mutation:
        lines.append(f"- **Suggested Mutation:** {stress.suggested_mutation}")

    # Adversarial Debate (compact table + fatal expansions)
    if stress.debate_rounds:
        lines.append("#### Adversarial Debate")
        lines.append("| # | Angle | Result |")
        lines.append("|---|-------|--------|")
        fatal_rounds = []
        for idx, rnd in enumerate(stress.debate_rounds, 1):
            outcome_raw = (rnd.outcome or "").upper()
            if "FATAL" in outcome_raw:
                result_badge = "\u274c FATAL"
                fatal_rounds.append(rnd)
            elif "SURVIVED" in outcome_raw:
                result_badge = "\u2705 survived"
            elif "WEAKENED" in outcome_raw:
                result_badge = "\u26a0\ufe0f weakened"
            else:
                result_badge = outcome_raw or "—"
            lines.append(f"| {idx} | {rnd.angle} | {result_badge} |")

        # Expand fatal angles with full attack/defense
        if fatal_rounds:
            for rnd in fatal_rounds:
                lines.append(f"**\u274c {rnd.angle}** (fatal)")
                if rnd.attack:
                    lines.append(f"> **Attack:** {rnd.attack}")
                if rnd.defense:
                    lines.append(f"> **Defense:** {rnd.defense}")
                if rnd.attacker_rebuttal:
                    lines.append(f"> **Rebuttal:** {rnd.attacker_rebuttal}")

    # Feasibility matrix with visual bars
    fm = stress.feasibility_matrix
    fm_dims = [
        ("Technical Risk", fm.technical_risk),
        ("Data Availability", fm.data_availability),
        ("Regulatory Risk", fm.regulatory_risk),
        ("Cost (infra/month)", fm.cost_infra_month),
        ("Time to Prototype", fm.time_to_prototype),
        ("Maintenance Burden", fm.maintenance_burden),
        ("LLM Capability Fit", fm.llm_capability_fit),
        ("Defensibility", fm.defensibility),
        ("Market Timing", fm.market_timing),
    ]
    fm_avg = sum(v for _, v in fm_dims) / len(fm_dims)
    lines.append("**Feasibility Matrix** (1-5):")
    lines.append("| Dimension | Score | |")
    lines.append("|-----------|------:|---|")
    for label, val in fm_dims:
        bar = "\u2588" * val + "\u2591" * (5 - val)
        lines.append(f"| {label} | {val} | {bar} |")
    lines.append(f"| **Average** | **{fm_avg:.1f}** | |")
    if stress.kill_criteria:
        lines.append("**Kill Criteria:**")
        for kc in stress.kill_criteria:
            lines.append(f"- {kc}")


def _append_next_steps(lines: list[str], result: IdeateRunResult) -> None:
    lines.append("## Next Steps")
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
