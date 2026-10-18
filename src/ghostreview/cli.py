"""GhostReview CLI.

  ghostreview review <project> [--diff <file.diff> | --staged]
                     [--verify-report <verify-report.json>]
                     [--scope-pack <pack-dir|scope.json>]
                     [-o <out-dir>] [--json]
  ghostreview mcp

Default diff source: the git working tree against HEAD. Default output
directory: the current directory (REVIEW.md + review.json). The project
tree is never modified. Exit codes: 0 straightforward / needs-a-look,
1 needs-attention, 2 could-not-review.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import build_review
from .inputs import diff_from_file, diff_from_git
from .reports import write_reports


def _print_summary(report: dict) -> None:
    print(f"ghostreview: {report.get('verdict')} "
          f"(exit {report.get('exit_code', '?')})")
    print(f"  {report.get('verdict_summary', '')}")
    for r in report.get("risks", []):
        loc = f":{r['line']}" if r.get("line") else ""
        print(f"  [{r['level']}] {r['rule']} {r['file']}{loc}: {r['detail']}")
    for n in report.get("notes", []):
        print(f"  note: {n}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ghostreview",
        description="Plain-English verdict layer for GhostSlice changes")
    parser.add_argument("--version", action="version",
                        version=f"ghostreview {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("review", help="review a diff and write REVIEW.md + review.json")
    p.add_argument("project", help="project root the diff belongs to")
    p.add_argument("--diff", help="read the diff from this file ('-' for stdin); "
                                  "default is the git working tree vs HEAD")
    p.add_argument("--staged", action="store_true",
                   help="use staged changes only (git diff --cached)")
    p.add_argument("--verify-report",
                   help="path to a GhostVerify verify-report.json to cite")
    p.add_argument("--scope-pack",
                   help="path to a GhostScope pack directory or its scope.json")
    p.add_argument("-o", "--out-dir", default=".",
                   help="where to write REVIEW.md + review.json (default: .)")
    p.add_argument("--no-report", action="store_true",
                   help="do not write REVIEW.md / review.json")
    p.add_argument("--json", action="store_true",
                   help="print the full review.json to stdout")

    sub.add_parser("mcp", help="run the stdio MCP server (local only)")

    args = parser.parse_args(argv)
    if args.command == "mcp":
        from .mcp_server import serve
        return serve()
    if args.command != "review":
        parser.print_help()
        return 2

    notes: list = []
    if args.diff:
        try:
            diff_text, source = diff_from_file(args.diff)
        except OSError as exc:
            print(f"ghostreview: could not read diff file: {exc}",
                  file=sys.stderr)
            return 2
    else:
        diff_text, source, notes = diff_from_git(Path(args.project),
                                                 staged=args.staged)
    report = build_review(args.project, diff_text, source,
                          verify_report=args.verify_report,
                          scope_pack=args.scope_pack,
                          extra_notes=notes)
    if not args.no_report:
        write_reports(report, args.out_dir)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_summary(report)
    return int(report.get("exit_code", 2))


if __name__ == "__main__":
    raise SystemExit(main())
