"""CLI entry point for xBrain — ``python -m xbrain``."""

from __future__ import annotations

import argparse
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
        "--domains",
        nargs="*",
        metavar="DOMAIN",
        help=(
            "Focus on specific domains — any topic works "
            '(e.g. health fintech "urban planning" gaming agriculture).'
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

    domains = args.domains if args.domains else None
    constraints = args.constraints if args.constraints else None
    brief_text = _resolve_brief(args.brief)
    language = args.lang or None

    # Override pipeline defaults from CLI
    if args.ideas:
        cfg.ideas_per_round = args.ideas
    if args.top:
        cfg.converge_top_n = args.top

    if args.dry_run:
        print("[DRY-RUN] Pipeline 1: IDEATE")
        print(f"  Model:       {cfg.model}")
        print(f"  Max tokens:  {cfg.max_tokens}")
        print(f"  Domains:     {domains or '(broad scan)'}")
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
    pipeline.run(domains=domains, constraints=constraints, brief_text=brief_text, language=language)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "ideate":
            _cmd_ideate(args)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
