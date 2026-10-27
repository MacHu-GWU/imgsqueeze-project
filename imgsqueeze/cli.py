# -*- coding: utf-8 -*-

"""
The ``imgsqueeze`` command line.

It only parses arguments, calls :mod:`imgsqueeze.runner`, prints the report
and picks the exit code. With ``--json``, stdout carries exactly one JSON
document and everything else goes to stderr.

Exit codes of ``optimize``: 0 no error, 1 at least one error, 2 bad
arguments, 3 some PNG was not processed because pngquant or oxipng is
unavailable.
"""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

from .core import Result
from .core import STATUS_ALREADY_DONE
from .core import STATUS_CONFLICT
from .core import STATUS_ERROR
from .core import tool_version
from .presets import DEFAULT_PRESET
from .presets import PRESET_NAMES
from .runner import optimize
from .runner import Report

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_MISSING_TOOLS = 3


def main(argv: list[str] | None = None) -> int:
    """
    Run the command line and return the exit code.

    :param argv: arguments without the program name, default ``sys.argv[1:]``.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.handler(parser, args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imgsqueeze",
        description="Compress blog images once, and remember that they are done.",
    )
    parser.add_argument("--version", action="version", version=tool_version())
    commands = parser.add_subparsers(dest="command", required=True)

    sub = commands.add_parser(
        "optimize",
        help="compress images that are not done yet",
        description="Compress PNG, JPEG and WebP images in place, "
        "and write a .json sidecar next to each one.",
    )
    sub.add_argument("paths", nargs="*", type=Path, help="image files and folders")
    sub.add_argument(
        "--preset",
        choices=PRESET_NAMES,
        default=DEFAULT_PRESET,
        help=f"compression strength (default: {DEFAULT_PRESET})",
    )
    sub.add_argument(
        "--stdin", action="store_true", help="also read paths from stdin, one per line"
    )
    sub.add_argument(
        "--jobs", type=int, help="number of worker processes (default: CPU count)"
    )
    sub.add_argument(
        "--min-gain",
        type=float,
        help="minimum fraction of bytes saved to keep a result, e.g. 0.05 "
        "(default: 0.05 for PNG and JPEG, 0.10 for WebP)",
    )
    sub.add_argument("--json", action="store_true", help="print a JSON report")
    sub.add_argument(
        "--dry-run", action="store_true", help="compress and report, but write nothing"
    )
    sub.set_defaults(handler=_optimize)
    return parser


def _optimize(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    paths = list(args.paths)
    if args.stdin:
        paths.extend(Path(line.strip()) for line in sys.stdin if line.strip())
    if not paths:
        parser.error("optimize: give at least one path, or use --stdin")
    try:
        report = optimize(
            paths,
            preset=args.preset,
            min_gain=args.min_gain,
            jobs=args.jobs,
            dry_run=args.dry_run,
        )
    except ValueError as e:
        parser.error(f"optimize: {e}")
    if args.json:
        print(json.dumps(_report_json(report, args.dry_run), indent=2))
    else:
        _print_text(report, args.dry_run)
    if report.missing_tools:
        missing = next(r for r in report.results if r.missing_tools)
        print(missing.error, file=sys.stderr)
        return EXIT_MISSING_TOOLS
    if report.summary[STATUS_ERROR]:
        return EXIT_ERROR
    return EXIT_OK


def _result_json(result: Result) -> dict:
    data = {
        "path": str(result.path),
        "status": result.status,
        "format": result.format,
        "preset": result.preset,
        "before": result.before,
        "after": result.after,
        "gain": None if result.gain is None else round(result.gain, 4),
        "warnings": list(result.warnings),
    }
    if result.status == STATUS_ALREADY_DONE:
        data["sidecar_status"] = result.sidecar_status
    if result.error is not None:
        data["error"] = result.error
    return data


def _report_json(report: Report, dry_run: bool) -> dict:
    data = {
        "results": [_result_json(result) for result in report.results],
        "summary": report.summary,
        "dry_run": dry_run,
    }
    if report.tools:
        data["tools"] = {
            tool.name: {"path": str(tool.path), "version": tool.version}
            for tool in report.tools
        }
    return data


def _print_text(report: Report, dry_run: bool) -> None:
    for result in report.results:
        print(f"{result.status:<13} {result.path}{_detail(result)}")
        for warning in result.warnings:
            print(f"{'':<13} warning: {warning}")
    summary = report.summary
    counts = ", ".join(
        f"{summary[status]} {status}"
        for status in summary
        if status not in ("total", "bytes_saved") and summary[status]
    )
    saved = "would save" if dry_run else "saved"
    print(
        f"{summary['total']} images: {counts or 'nothing to do'}; "
        f"{saved} {summary['bytes_saved']} bytes"
    )


def _detail(result: Result) -> str:
    if result.status == STATUS_ALREADY_DONE:
        return f" ({result.sidecar_status})"
    if result.error is not None:
        # The missing tools message is long, and printed once at the end.
        return "" if result.missing_tools else f": {result.error}"
    if result.status == STATUS_CONFLICT:
        return ": changed by another process while compressing, run again"
    return f" {result.before} -> {result.after} bytes ({result.gain:.1%} saved)"
