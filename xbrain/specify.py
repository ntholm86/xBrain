"""Pipeline 2: SPECIFY — convert validated ideas into project specs."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from xbrain.config import Config
from xbrain.llm import LLMClient
from xbrain.prompts import SPECIFY_SYSTEM, SPECIFY_USER


def _log(tag: str, msg: str) -> None:
    print(f"[{tag:<9s}] {msg}")
    sys.stdout.flush()


class SpecifyPipeline:
    """Convert a validated IdeaCard into an actionable project specification."""

    def __init__(self, config: Config | None = None):
        self.cfg = config or Config()
        if not self.cfg.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set.")
        self.llm = LLMClient(self.cfg.api_key, self.cfg.model, self.cfg.max_tokens)

    def run(
        self,
        idea_cards_path: Path,
        idea_id: str,
        stress_report_path: Path | None = None,
        language: str | None = None,
    ) -> Path:
        """Generate a project spec for the selected idea."""
        # Load idea cards
        cards = json.loads(idea_cards_path.read_text(encoding="utf-8"))
        card = next((c for c in cards if c.get("id") == idea_id), None)
        if not card:
            available = [c.get("id", "?") for c in cards[:20]]
            raise ValueError(
                f"Idea '{idea_id}' not found. Available: {', '.join(available)}"
            )

        _log("SPECIFY", f"Generating spec for: {card.get('title', idea_id)}")

        # Load stress test results if available
        stress_data = {}
        if stress_report_path and stress_report_path.exists():
            all_stress = json.loads(stress_report_path.read_text(encoding="utf-8"))
            stress_data = next(
                (s for s in all_stress if s.get("idea_id") == idea_id), {}
            )

        # Build prompt
        prompt = SPECIFY_USER.format(
            idea_json=json.dumps(card, indent=2, ensure_ascii=False),
            stress_json=json.dumps(stress_data, indent=2, ensure_ascii=False) if stress_data else "No stress test data available.",
        )

        sys_prompt = SPECIFY_SYSTEM
        if language:
            sys_prompt += (
                f" All human-readable text in your JSON response "
                f"MUST be written in {language}. Keep JSON keys in English."
            )

        # Route to best model for specify
        model_override = None
        if self.cfg.model_strategy != "single":
            routing = self.cfg.PHASE_ROUTING.get(self.cfg.model_strategy, {})
            tier = routing.get("specify", "best")
            if tier == "cheap":
                model_override = self.cfg.cheap_model or None
            else:
                model_override = self.cfg.best_model or None

        data = self.llm.generate_json(
            sys_prompt, prompt, temperature=0.4,
            model_override=model_override, phase="specify",
        )

        # Write output
        run_dir = idea_cards_path.parent
        spec_path = run_dir / f"spec-{idea_id}.md"
        spec_json_path = run_dir / f"spec-{idea_id}.json"

        # Save raw JSON
        spec_json_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Generate human-readable spec
        report = self._render_spec(data, card)
        spec_path.write_text(report, encoding="utf-8")

        cost_info = self._compute_cost()
        _log("SPECIFY", f"✓ Spec written to {spec_path}")
        _log("SPECIFY", f"  JSON: {spec_json_path}")
        _log("SPECIFY", f"  Tokens: {self.llm.total_input_tokens:,} in / {self.llm.total_output_tokens:,} out")
        _log("SPECIFY", f"  Cost: ${cost_info:.4f}")

        return spec_path

    def _compute_cost(self) -> float:
        total = 0.0
        for entry in self.llm._phase_token_log:
            rate = self.cfg.MODEL_PRICING.get(entry["model"], (3.0, 15.0))
            total += (entry["input_tokens"] / 1_000_000 * rate[0] +
                      entry["output_tokens"] / 1_000_000 * rate[1])
        return total

    def _render_spec(self, data: dict, card: dict) -> str:
        """Render a project spec as Markdown."""
        lines: list[str] = []
        title = data.get("title", card.get("title", "Untitled"))

        lines.append(f"# Project Spec: {title}")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
        lines.append(f"**Source Idea:** {card.get('id', '?')} (score: {card.get('composite_score', '?')})")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Overview
        lines.append("## Overview")
        lines.append("")
        lines.append(data.get("overview", "N/A"))
        lines.append("")

        # User Stories
        stories = data.get("user_stories", [])
        if stories:
            lines.append("## User Stories")
            lines.append("")
            for s in stories:
                priority = s.get("priority", "")
                priority_badge = f" `[{priority}]`" if priority else ""
                lines.append(f"### {s.get('id', '?')}{priority_badge}")
                lines.append("")
                lines.append(f"> {s.get('story', '')}")
                lines.append("")
                ac = s.get("acceptance_criteria", [])
                if ac:
                    lines.append("**Acceptance Criteria:**")
                    for criterion in ac:
                        lines.append(f"- [ ] {criterion}")
                    lines.append("")

        # Architecture
        arch = data.get("architecture", {})
        if arch:
            lines.append("## Architecture")
            lines.append("")
            stack = arch.get("tech_stack", {})
            if stack:
                lines.append("### Tech Stack")
                lines.append("")
                lines.append("| Layer | Technology |")
                lines.append("|-------|-----------|")
                for layer, tech in stack.items():
                    if isinstance(tech, list):
                        tech = ", ".join(tech)
                    lines.append(f"| {layer.title()} | {tech} |")
                lines.append("")

            components = arch.get("components", [])
            if components:
                lines.append("### Components")
                lines.append("")
                for comp in components:
                    lines.append(f"- {comp}")
                lines.append("")

            data_flow = arch.get("data_flow", "")
            if data_flow:
                lines.append("### Data Flow")
                lines.append("")
                lines.append(data_flow)
                lines.append("")

        # API Contracts
        apis = data.get("api_contracts", [])
        if apis:
            lines.append("## API Contracts")
            lines.append("")
            for api in apis:
                lines.append(f"### `{api.get('method', 'GET')} {api.get('path', '/')}`")
                lines.append("")
                lines.append(api.get("description", ""))
                lines.append("")
                auth = api.get("auth", "")
                if auth:
                    lines.append(f"**Auth:** {auth}")
                    lines.append("")
                req = api.get("request_body", {})
                if req:
                    lines.append("**Request:**")
                    lines.append("```json")
                    lines.append(json.dumps(req, indent=2))
                    lines.append("```")
                    lines.append("")
                res = api.get("response_body", {})
                if res:
                    lines.append("**Response:**")
                    lines.append("```json")
                    lines.append(json.dumps(res, indent=2))
                    lines.append("```")
                    lines.append("")

        # Data Model
        models = data.get("data_model", [])
        if models:
            lines.append("## Data Model")
            lines.append("")
            for model in models:
                lines.append(f"### {model.get('entity', '?')}")
                lines.append("")
                fields = model.get("fields", {})
                if fields:
                    lines.append("| Field | Type |")
                    lines.append("|-------|------|")
                    for fname, ftype in fields.items():
                        lines.append(f"| {fname} | {ftype} |")
                    lines.append("")
                rels = model.get("relationships", [])
                if rels:
                    for rel in rels:
                        lines.append(f"- {rel}")
                    lines.append("")

        # Tasks
        tasks = data.get("tasks", [])
        if tasks:
            lines.append("## Development Tasks")
            lines.append("")
            lines.append("| # | Task | Effort | Depends On |")
            lines.append("|---|------|--------|-----------|")
            for t in tasks:
                deps = ", ".join(t.get("depends_on", [])) or "—"
                lines.append(f"| {t.get('id', '?')} | {t.get('title', '')} | {t.get('effort_days', '?')}d | {deps} |")
            lines.append("")

            lines.append("### Task Details")
            lines.append("")
            for t in tasks:
                lines.append(f"#### {t.get('id', '?')}: {t.get('title', '')}")
                lines.append("")
                lines.append(t.get("description", ""))
                lines.append("")
                ac = t.get("acceptance_criteria", [])
                if ac:
                    for criterion in ac:
                        lines.append(f"- [ ] {criterion}")
                    lines.append("")

        # Risks
        risks = data.get("risks", [])
        if risks:
            lines.append("## Risks & Mitigations")
            lines.append("")
            lines.append("| Risk | Likelihood | Mitigation |")
            lines.append("|------|-----------|-----------|")
            for r in risks:
                lines.append(f"| {r.get('risk', '')} | {r.get('likelihood', '')} | {r.get('mitigation', '')} |")
            lines.append("")

        # Success Metrics
        metrics = data.get("success_metrics", [])
        if metrics:
            lines.append("## Success Metrics")
            lines.append("")
            lines.append("| Metric | Target | Method | Timeframe | Abort If |")
            lines.append("|--------|--------|--------|-----------|----------|")
            for m in metrics:
                abort = m.get("abort_threshold", "—") or "—"
                lines.append(f"| {m.get('metric', '')} | {m.get('target', '')} | {m.get('measurement_method', '')} | {m.get('timeframe', '')} | {abort} |")
            lines.append("")

        # Validation Plan
        experiments = data.get("validation_plan", [])
        if experiments:
            lines.append("## Validation Plan (Pre-Build Experiments)")
            lines.append("")
            for i, exp in enumerate(experiments, 1):
                lines.append(f"### Experiment {i}: {exp.get('experiment', '')}")
                lines.append("")
                lines.append(f"**Tests assumption:** {exp.get('assumption_tested', '')}")
                lines.append(f"**Method:** {exp.get('method', '')}")
                lines.append(f"**Duration:** {exp.get('duration', '')} | **Cost:** {exp.get('cost', '')}")
                lines.append(f"- ✅ **Proceed if:** {exp.get('success_signal', '')}")
                lines.append(f"- 🛑 **Stop if:** {exp.get('failure_signal', '')}")
                lines.append("")

        # MVP
        mvp = data.get("mvp_scope", {})
        if mvp:
            lines.append("## MVP Scope (2-week sprint)")
            lines.append("")
            lines.append(f"**Sprint Goal:** {mvp.get('sprint_goal', '')}")
            lines.append("")
            include = mvp.get("include", [])
            if include:
                lines.append("**Include:**")
                for item in include:
                    lines.append(f"- ✅ {item}")
                lines.append("")
            defer = mvp.get("defer", [])
            if defer:
                lines.append("**Defer:**")
                for item in defer:
                    lines.append(f"- ⏳ {item}")
                lines.append("")

        # Kill Criteria
        kc = data.get("kill_criteria", [])
        if kc:
            lines.append("## Kill Criteria")
            lines.append("")
            for criterion in kc:
                lines.append(f"- 🛑 {criterion}")
            lines.append("")

        return "\n".join(lines)
