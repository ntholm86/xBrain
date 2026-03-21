"""CLI entry point for xBrain — ``python -m xbrain``."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from xbrain.config import Config
from xbrain.log import (
    log as _log,
    log_ok as _log_ok,
    log_warn as _log_warn,
    log_error as _log_error,
    log_detail as _log_detail,
    log_summary_line,
    fmt_verdict,
    escape as _esc,
    console,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xbrain",
        description="xBrain: Self-Thinking AI Idea Engine",
    )
    sub = parser.add_subparsers(dest="command")

    # --- ideate ---
    ideate = sub.add_parser(
        "ideate",
        help="Run Pipeline 1: generate, score, and stress-test ideas",
    )
    ideate.add_argument(
        "--brief",
        metavar="TEXT_OR_FILE",
        help=(
            "Context to guide ideation: a problem statement, idea to improve, "
            "or path to a .txt file. Examples:\n"
            '  --brief problem.txt\n'
            '  --brief "How can AI help teachers grade essays faster?"'
        ),
    )
    ideate.add_argument(
        "--constraints",
        nargs="*",
        metavar="CONSTRAINT",
        help='Extra constraints (e.g. "must work offline" "budget under 1000/month")',
    )
    ideate.add_argument(
        "--ideas",
        type=int,
        metavar="N",
        help="Number of raw ideas to generate (default: 20)",
    )
    ideate.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Number of ideas to score and stress-test (default: 8)",
    )
    ideate.add_argument(
        "--generations",
        type=int,
        metavar="N",
        help="Evolutionary generations: survivors are mutated, crossed, and re-tested N times (default: 1, no evolution). Higher = better ideas but more cost.",
    )
    ideate.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned run without calling the LLM (useful for testing)",
    )
    ideate.add_argument(
        "--lang",
        metavar="LANGUAGE",
        help='Output language for the report (e.g. danish, spanish, german). Default: english',
    )
    ideate.add_argument(
        "--strategy",
        choices=["single", "cheapest", "balanced", "best"],
        help=(
            "Model routing strategy: "
            "'single' (default, use one model for everything), "
            "'cheapest' (Haiku everywhere), "
            "'balanced' (Haiku for generation, best model for scoring/stress), "
            "'best' (best model everywhere)"
        ),
    )

    # --- specify ---
    specify = sub.add_parser(
        "specify",
        help="Pipeline 2: convert a validated idea into a project spec",
    )
    specify.add_argument(
        "--idea",
        required=True,
        metavar="PATH",
        help="Path to idea-cards.json from a previous run",
    )
    specify.add_argument(
        "--select",
        required=True,
        metavar="IDEA_ID",
        help="ID of the idea to specify (e.g. idea-003)",
    )
    specify.add_argument(
        "--lang",
        metavar="LANGUAGE",
        help="Output language for the spec. Default: english",
    )

    # --- estimate ---
    estimate = sub.add_parser(
        "estimate",
        help="Estimate API cost before running (no API calls made)",
    )
    estimate.add_argument("--ideas", type=int, default=20, metavar="N", help="Ideas to generate")
    estimate.add_argument("--top", type=int, default=8, metavar="N", help="Ideas to score")
    estimate.add_argument("--generations", type=int, default=1, metavar="N", help="Evolutionary generations")
    estimate.add_argument("--constraints", nargs="*", metavar="CONSTRAINT", help="Constraints")
    estimate.add_argument(
        "--strategy",
        choices=["single", "cheapest", "balanced", "best"],
        default="single",
    )

    # --- lineage ---
    lineage_p = sub.add_parser(
        "lineage",
        help="Browse idea lineage across runs",
    )
    lineage_p.add_argument(
        "--top",
        type=int,
        default=20,
        metavar="N",
        help="Show top N ideas by score",
    )
    lineage_p.add_argument(
        "--domain",
        metavar="DOMAIN",
        help="Filter by domain",
    )
    lineage_p.add_argument(
        "--verdict",
        choices=["BUILD", "MUTATE", "KILL", "INCUBATE"],
        help="Filter by verdict",
    )

    # --- export ---
    export_p = sub.add_parser(
        "export",
        help="Export ideas to CSV, Markdown tasks, or Jira JSON for project management",
    )
    export_p.add_argument(
        "--run",
        required=True,
        metavar="PATH",
        help="Path to a run folder (e.g. ./xbrain-runs/run-20260318-190218)",
    )
    export_p.add_argument(
        "--format",
        choices=["csv", "md", "jira"],
        default="csv",
        help="Export format: csv (Jira/Linear import), md (Markdown tasks), jira (Jira JSON). Default: csv",
    )
    export_p.add_argument(
        "--all",
        action="store_true",
        dest="export_all",
        help="Export all ideas (default: BUILD only)",
    )
    export_p.add_argument(
        "--output",
        metavar="FILE",
        help="Write to file instead of stdout",
    )

    return parser


def _resolve_brief(value: str | None) -> str | None:
    """If value is a path to an existing file, read it. Otherwise return as-is."""
    if value is None:
        return None
    path = Path(value)
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            _log_warn("CLI", f"Brief file '{value}' is empty — ignoring.")
            return None
        return text
    # Treat as inline text
    return value.strip() or None


def _cmd_ideate(args: argparse.Namespace) -> None:
    cfg = Config()

    constraints = args.constraints if args.constraints else None
    brief_text = _resolve_brief(args.brief)
    language = args.lang or None

    # Override pipeline defaults from CLI
    if args.ideas:
        cfg.ideas_per_round = args.ideas
    if args.top:
        cfg.converge_top_n = args.top
    if args.generations:
        cfg.generations = args.generations
    if args.strategy:
        cfg.model_strategy = args.strategy

    if args.dry_run:
        from xbrain.ideate import IdeatePipeline

        estimate = IdeatePipeline.estimate_cost(
            model=cfg.model,
            ideas_per_round=cfg.ideas_per_round,
            converge_top_n=cfg.converge_top_n,
            has_constraints=bool(constraints),
            pricing=cfg.MODEL_PRICING,
            strategy=cfg.model_strategy,
            cheap_model=cfg.cheap_model,
            generations=cfg.generations,
        )
        _log("DRY-RUN", f"Pipeline 1: [accent]IDEATE[/accent]")
        _log_detail("DRY-RUN", f"Model:       {cfg.model}")
        _log_detail("DRY-RUN", f"Strategy:    {cfg.model_strategy}")
        _log_detail("DRY-RUN", f"Max tokens:  {cfg.max_tokens}")
        _log_detail("DRY-RUN", f"Constraints: {constraints or '(none)'}")
        _log_detail("DRY-RUN", f"Ideas:       {cfg.ideas_per_round}")
        _log_detail("DRY-RUN", f"Top N:       {cfg.converge_top_n}")
        _log_detail("DRY-RUN", f"Generations: {cfg.generations}")
        _log_detail("DRY-RUN", f"Language:    {language or 'english'}")
        if brief_text:
            preview = brief_text[:200] + ("..." if len(brief_text) > 200 else "")
            _log_detail("DRY-RUN", f"Brief:       {_esc(preview)}")
        else:
            _log_detail("DRY-RUN", f"Brief:       (none — open-ended ideation)")
        _log_detail("DRY-RUN", f"Runs dir:    {cfg.runs_dir}")
        _log_detail("DRY-RUN", f"Memory dir:  {cfg.memory_dir}")
        _log_ok("DRY-RUN", f"Est. cost:   ${estimate['total_est_cost_usd']:.4f}")
        _log("DRY-RUN", "")
        _log("DRY-RUN", f"[header]Phase breakdown:[/header]")
        for p in estimate["phases"]:
            _log_detail("DRY-RUN", f"  {p['phase']:<12s} {p['model']:<35s} ~${p['est_cost_usd']:.4f}")
        _log("DRY-RUN", "")
        _log_warn("DRY-RUN", "No API call will be made. Remove --dry-run to execute.")
        return

    if not cfg.api_key:
        _log_error("CLI", "ANTHROPIC_API_KEY not set.")
        _log_detail("CLI", "1. Copy .env.example to .env")
        _log_detail("CLI", "2. Add your Anthropic API key")
        _log_detail("CLI", "3. Run again")
        sys.exit(1)

    # Lazy import keeps startup fast when just checking --help
    from xbrain.ideate import IdeatePipeline  # noqa: E402

    pipeline = IdeatePipeline(config=cfg)
    pipeline.run(constraints=constraints, brief_text=brief_text, language=language)


def _cmd_specify(args: argparse.Namespace) -> None:
    cfg = Config()

    if not cfg.api_key:
        _log_error("CLI", "ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    idea_path = Path(args.idea)
    if not idea_path.exists():
        _log_error("CLI", f"File not found: {args.idea}")
        sys.exit(1)

    # Auto-discover stress test report in same directory
    stress_path = idea_path.parent / "stress-test-report.json"

    from xbrain.specify import SpecifyPipeline

    pipeline = SpecifyPipeline(config=cfg)
    pipeline.run(
        idea_cards_path=idea_path,
        idea_id=args.select,
        stress_report_path=stress_path if stress_path.exists() else None,
        language=args.lang,
    )


def _cmd_estimate(args: argparse.Namespace) -> None:
    cfg = Config()
    cfg.model_strategy = args.strategy

    from xbrain.ideate import IdeatePipeline

    estimate = IdeatePipeline.estimate_cost(
        model=cfg.model,
        ideas_per_round=args.ideas,
        converge_top_n=args.top,
        has_constraints=bool(args.constraints),
        pricing=cfg.MODEL_PRICING,
        strategy=args.strategy,
        cheap_model=cfg.cheap_model,
        generations=args.generations,
    )

    _log("ESTIMATE", f"[header]xBrain Cost Estimate[/header]")
    _log("ESTIMATE", f"[detail]{'=' * 50}[/detail]")
    _log_detail("ESTIMATE", f"Model:       {cfg.model}")
    _log_detail("ESTIMATE", f"Strategy:    {args.strategy}")
    _log_detail("ESTIMATE", f"Ideas:       {args.ideas}")
    _log_detail("ESTIMATE", f"Top N:       {args.top}")
    _log("ESTIMATE", "")
    _log("ESTIMATE", f"[header]Phase breakdown:[/header]")
    for p in estimate["phases"]:
        _log_detail("ESTIMATE", f"  {p['phase']:<12s} {p['model']:<35s} ~${p['est_cost_usd']:.6f}")
    _log("ESTIMATE", "")
    _log_ok("ESTIMATE", f"TOTAL ESTIMATED COST: ${estimate['total_est_cost_usd']:.4f}")
    _log("ESTIMATE", "")
    # Compare strategies
    _log("ESTIMATE", f"[header]Compare strategies:[/header]")
    for strat in ["cheapest", "balanced", "best"]:
        est = IdeatePipeline.estimate_cost(
            model=cfg.model,
            ideas_per_round=args.ideas,
            converge_top_n=args.top,
            has_constraints=bool(args.constraints),
            pricing=cfg.MODEL_PRICING,
            strategy=strat,
            cheap_model=cfg.cheap_model,
            generations=args.generations,
        )
        _log_detail("ESTIMATE", f"  {strat:<12s} ${est['total_est_cost_usd']:.4f}")


def _cmd_lineage(args: argparse.Namespace) -> None:
    cfg = Config()

    from xbrain.memory import MemoryStore

    memory = MemoryStore(cfg.memory_dir / "persistent")
    lineage = memory.get_lineage()

    if not lineage:
        _log_warn("LINEAGE", "No idea lineage yet. Run 'python -m xbrain ideate' first.")
        return

    # Apply filters
    if args.domain:
        lineage = [e for e in lineage if args.domain.lower() in
                   [d.lower() for d in e.get("domain_tags", [])]]
    if args.verdict:
        lineage = [e for e in lineage if e.get("verdict") == args.verdict]

    # Sort by score descending
    lineage.sort(key=lambda e: e.get("score", 0), reverse=True)
    lineage = lineage[:args.top]

    if not lineage:
        _log_warn("LINEAGE", "No ideas match the filter criteria.")
        return

    # Print table
    from rich.table import Table
    table = Table(show_header=True, header_style="bold", show_lines=False, pad_edge=False)
    table.add_column("ID", style="dim", width=25)
    table.add_column("Score", justify="right", width=5)
    table.add_column("Verdict", width=8)
    table.add_column("Run", style="dim", width=22)
    table.add_column("Title")
    for entry in lineage:
        idea_id = entry.get("idea_id", "?")[:24]
        score = entry.get("score", 0)
        verdict = entry.get("verdict", "?")
        run_id = entry.get("run_id", "?")[:21]
        title = entry.get("title", "?")[:50]
        table.add_row(idea_id, f"{score:.1f}", fmt_verdict(verdict), run_id, _esc(title))
    console.print(table)

    # Stats
    log_summary_line("")
    total = len(memory.get_lineage())
    builds = sum(1 for e in memory.get_lineage() if e.get("verdict") == "BUILD")
    genes = len(memory.get_idea_genes())
    _log_ok("LINEAGE", f"Total ideas tracked: {total} | BUILD: {builds} | Idea genes: {genes}")


def _cmd_export(args: argparse.Namespace) -> None:
    run_dir = Path(args.run)
    if not run_dir.is_dir():
        _log_error("EXPORT", f"Run folder not found: {args.run}")
        sys.exit(1)

    cards_path = run_dir / "idea-cards.json"
    stress_path = run_dir / "stress-test-report.json"

    if not cards_path.exists():
        _log_error("EXPORT", f"idea-cards.json not found in {run_dir}")
        sys.exit(1)

    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    stress_data = json.loads(stress_path.read_text(encoding="utf-8")) if stress_path.exists() else []

    # Filter to BUILD only unless --all
    if not args.export_all:
        cards = [c for c in cards if c.get("stress_test_verdict") == "BUILD"]
        if not cards:
            _log_warn("EXPORT", "No BUILD ideas found. Use --all to export all ideas.")
            sys.exit(0)

    from xbrain.output import export_csv, export_jira_json, export_markdown_tasks

    fmt = args.format
    if fmt == "csv":
        content = export_csv(cards, stress_data)
        ext = ".csv"
    elif fmt == "md":
        content = export_markdown_tasks(cards, stress_data)
        ext = ".md"
    elif fmt == "jira":
        content = export_jira_json(cards, stress_data)
        ext = ".json"
    else:
        _log_error("EXPORT", f"Unknown format: {fmt}")
        sys.exit(1)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(content, encoding="utf-8")
        _log_ok("EXPORT", f"Exported {len(cards)} idea(s) to {out_path}")
    else:
        sys.stdout.buffer.write(content.encode("utf-8"))


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "ideate":
            _cmd_ideate(args)
        elif args.command == "specify":
            _cmd_specify(args)
        elif args.command == "estimate":
            _cmd_estimate(args)
        elif args.command == "lineage":
            _cmd_lineage(args)
        elif args.command == "export":
            _cmd_export(args)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
