"""CLI entry point for xBrain — ``python -m xbrain``."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from xbrain.config import Config


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
            print(f"WARNING: Brief file '{value}' is empty — ignoring.", file=sys.stderr)
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
        )
        print("[DRY-RUN] Pipeline 1: IDEATE")
        print(f"  Model:       {cfg.model}")
        print(f"  Strategy:    {cfg.model_strategy}")
        print(f"  Max tokens:  {cfg.max_tokens}")
        print(f"  Constraints: {constraints or '(none)'}")
        print(f"  Ideas:       {cfg.ideas_per_round}")
        print(f"  Top N:       {cfg.converge_top_n}")
        print(f"  Language:    {language or 'english'}")
        if brief_text:
            preview = brief_text[:200] + ("..." if len(brief_text) > 200 else "")
            print(f"  Brief:       {preview}")
        else:
            print(f"  Brief:       (none — open-ended ideation)")
        print(f"  Runs dir:    {cfg.runs_dir}")
        print(f"  Memory dir:  {cfg.memory_dir}")
        print(f"  Est. cost:   ${estimate['total_est_cost_usd']:.4f}")
        print()
        print("  Phase breakdown:")
        for p in estimate["phases"]:
            print(f"    {p['phase']:<12s} {p['model']:<35s} ~${p['est_cost_usd']:.4f}")
        print()
        print("No API call will be made. Remove --dry-run to execute.")
        return

    if not cfg.api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY not set.\n"
            "  1. Copy .env.example to .env\n"
            "  2. Add your Anthropic API key\n"
            "  3. Run again",
            file=sys.stderr,
        )
        sys.exit(1)

    # Lazy import keeps startup fast when just checking --help
    from xbrain.ideate import IdeatePipeline  # noqa: E402

    pipeline = IdeatePipeline(config=cfg)
    pipeline.run(constraints=constraints, brief_text=brief_text, language=language)


def _cmd_specify(args: argparse.Namespace) -> None:
    cfg = Config()

    if not cfg.api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    idea_path = Path(args.idea)
    if not idea_path.exists():
        print(f"ERROR: File not found: {args.idea}", file=sys.stderr)
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
    )

    print("xBrain Cost Estimate")
    print("=" * 50)
    print(f"  Model:       {cfg.model}")
    print(f"  Strategy:    {args.strategy}")
    print(f"  Ideas:       {args.ideas}")
    print(f"  Top N:       {args.top}")
    print()
    print("  Phase breakdown:")
    for p in estimate["phases"]:
        print(f"    {p['phase']:<12s} {p['model']:<35s} ~${p['est_cost_usd']:.6f}")
    print()
    print(f"  TOTAL ESTIMATED COST: ${estimate['total_est_cost_usd']:.4f}")
    print()
    # Compare strategies
    print("  Compare strategies:")
    for strat in ["cheapest", "balanced", "best"]:
        est = IdeatePipeline.estimate_cost(
            model=cfg.model,
            ideas_per_round=args.ideas,
            converge_top_n=args.top,
            has_constraints=bool(args.constraints),
            pricing=cfg.MODEL_PRICING,
            strategy=strat,
            cheap_model=cfg.cheap_model,
        )
        print(f"    {strat:<12s} ${est['total_est_cost_usd']:.4f}")


def _cmd_lineage(args: argparse.Namespace) -> None:
    cfg = Config()

    from xbrain.memory import MemoryStore

    memory = MemoryStore(cfg.memory_dir / "persistent")
    lineage = memory.get_lineage()

    if not lineage:
        print("No idea lineage yet. Run 'python -m xbrain ideate' first.")
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
        print("No ideas match the filter criteria.")
        return

    # Print table
    print(f"{'ID':<25s} {'Score':>5s}  {'Verdict':<8s} {'Run':<22s} {'Title'}")
    print("-" * 100)
    for entry in lineage:
        idea_id = entry.get("idea_id", "?")[:24]
        score = entry.get("score", 0)
        verdict = entry.get("verdict", "?")
        run_id = entry.get("run_id", "?")[:21]
        title = entry.get("title", "?")[:50]
        print(f"{idea_id:<25s} {score:5.1f}  {verdict:<8s} {run_id:<22s} {title}")

    # Stats
    print()
    total = len(memory.get_lineage())
    builds = sum(1 for e in memory.get_lineage() if e.get("verdict") == "BUILD")
    genes = len(memory.get_idea_genes())
    print(f"Total ideas tracked: {total} | BUILD: {builds} | Idea genes: {genes}")


def _cmd_export(args: argparse.Namespace) -> None:
    run_dir = Path(args.run)
    if not run_dir.is_dir():
        print(f"ERROR: Run folder not found: {args.run}", file=sys.stderr)
        sys.exit(1)

    cards_path = run_dir / "idea-cards.json"
    stress_path = run_dir / "stress-test-report.json"

    if not cards_path.exists():
        print(f"ERROR: idea-cards.json not found in {run_dir}", file=sys.stderr)
        sys.exit(1)

    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    stress_data = json.loads(stress_path.read_text(encoding="utf-8")) if stress_path.exists() else []

    # Filter to BUILD only unless --all
    if not args.export_all:
        cards = [c for c in cards if c.get("stress_test_verdict") == "BUILD"]
        if not cards:
            print("No BUILD ideas found. Use --all to export all ideas.", file=sys.stderr)
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
        print(f"ERROR: Unknown format: {fmt}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(content, encoding="utf-8")
        print(f"Exported {len(cards)} idea(s) to {out_path}")
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
