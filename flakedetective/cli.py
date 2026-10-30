"""Command line: run the suite, then read the verdict.

Exit codes are part of the contract: 0 nothing flaky, 3 flaky tests found,
2 bad usage. CI can gate on 3 without parsing text.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Sequence

from . import __version__
from .analyze import analyze
from .report import render_json, render_text
from .runner import load_results, run_suite
from . import quarantine

EXIT_CLEAN = 0
EXIT_USAGE = 2
EXIT_FLAKY = 3


def _split_command(argv: Sequence[str]) -> List[str]:
    if "--" not in argv:
        return []
    idx = list(argv).index("--")
    return list(argv)[idx + 1:]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flakedetective",
                                description="Find flaky tests, rank the likely cause, and print how to prove it.")
    p.add_argument("--version", action="version", version="flakedetective {}".format(__version__))
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a suite N times and report")
    r.add_argument("--runs", type=int, default=10)
    r.add_argument("--timeout", type=float, default=None, help="per-run timeout in seconds")
    r.add_argument("--parser", default="auto", choices=["auto", "pytest", "jest", "unittest"])
    r.add_argument("--cwd", default=None, help="directory to run the suite in")
    r.add_argument("--state-dir", default=None, help="where the runs.jsonl ledger lives (default: <cwd>/.flakedetective)")
    r.add_argument("--json", action="store_true")
    r.add_argument("--top", type=int, default=10)
    r.add_argument("--no-color", action="store_true")
    r.add_argument("command", nargs=argparse.REMAINDER, help="suite command after --")

    a = sub.add_parser("analyze", help="analyze an existing runs.jsonl")
    a.add_argument("path", nargs="?", default=None)
    a.add_argument("--parser", default="auto", choices=["auto", "pytest", "jest", "unittest"])
    a.add_argument("--json", action="store_true")
    a.add_argument("--top", type=int, default=10)
    a.add_argument("--no-color", action="store_true")

    q = sub.add_parser("quarantine", help="print a quarantine snippet for known flaky tests")
    q.add_argument("path", nargs="?", default=None)
    q.add_argument("--format", default="pytest", choices=["pytest", "jest"])
    q.add_argument("--min-score", type=float, default=0.0)

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)

    if args.cmd == "run":
        command = [c for c in (args.command or []) if c != "--"]
        if not command:
            print("error: pass the suite command after --", file=sys.stderr)
            return EXIT_USAGE
        state_dir = args.state_dir or (
            os.path.join(args.cwd, ".flakedetective") if args.cwd else ".flakedetective")
        results = run_suite(command, runs=args.runs, timeout=args.timeout,
                            cwd=args.cwd, parser=args.parser, state_dir=state_dir)
        analysis = analyze(results, parser=args.parser)
    else:
        results = load_results(args.path)
        if not results:
            print("no runs found; run `flakedetective run --runs 10 -- <suite>` first", file=sys.stderr)
            return EXIT_USAGE
        analysis = analyze(results, parser=getattr(args, "parser", "auto"))

    if args.cmd == "quarantine":
        ids = [c.test_id for c in analysis.flaky if c.score >= args.min_score]
        if not ids:
            print("nothing to quarantine", file=sys.stderr)
            return EXIT_CLEAN
        print(quarantine.emit(ids, fmt=args.format))
        return EXIT_CLEAN

    print(render_json(analysis) if args.json else
          render_text(analysis, top=args.top, color=not args.no_color))
    return EXIT_FLAKY if analysis.flaky else EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
