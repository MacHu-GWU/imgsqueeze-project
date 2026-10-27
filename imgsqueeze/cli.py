# -*- coding: utf-8 -*-

"""
The ``imgsqueeze`` command line.

It only parses arguments, calls :mod:`imgsqueeze.runner` and
:mod:`imgsqueeze.housekeeping`, prints the report and picks the exit code.
With ``--json``, stdout carries exactly one JSON document and everything else
goes to stderr.

Exit codes (2 is always bad arguments):

- ``optimize``: 0 no error, 1 at least one error, 3 some PNG was not
  processed because pngquant or oxipng is unavailable.
- ``check``: 0 every image is done, 1 some image is not.
- ``pin``: 0 success, 1 at least one failure.
- ``doctor``: 0 nothing left to fix, 1 problems found.
- ``setup``: 0 success, 3 mise is missing or the install failed.
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
from .housekeeping import check
from .housekeeping import doctor
from .housekeeping import pin
from .housekeeping import PIN_ERROR
from .presets import DEFAULT_PRESET
from .presets import PRESET_NAMES
from .runner import optimize
from .runner import Report
from .tools import OXIPNG
from .tools import PNGQUANT
from .tools import resolve_tool
from .tools import ToolUnavailableError

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
    _add_paths(sub)
    sub.add_argument(
        "--preset",
        choices=PRESET_NAMES,
        default=DEFAULT_PRESET,
        help=f"compression strength (default: {DEFAULT_PRESET})",
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
    sub.add_argument(
        "--dry-run", action="store_true", help="compress and report, but write nothing"
    )
    sub.set_defaults(handler=_optimize)

    sub = commands.add_parser(
        "check",
        help="exit 1 if some image is not done yet (for a pre-commit hook)",
        description="Compare each image with its sidecar, without compressing.",
    )
    _add_paths(sub)
    sub.set_defaults(handler=_check)

    sub = commands.add_parser(
        "pin",
        help="keep images as they are from now on",
        description="Write a pinned sidecar for the current content of each image.",
    )
    _add_paths(sub)
    sub.set_defaults(handler=_pin)

    sub = commands.add_parser(
        "doctor",
        help="find orphan sidecars, pending images and leftover temporary files",
        description="Find orphan sidecars, images not done yet, and temporary "
        "files left by an interrupted run.",
    )
    _add_paths(sub)
    sub.add_argument(
        "--delete-orphans",
        action="store_true",
        help="delete sidecars whose image no longer exists",
    )
    sub.set_defaults(handler=_doctor)

    sub = commands.add_parser(
        "setup",
        help="install pngquant and oxipng with mise ahead of time",
        description="Install the pinned pngquant and oxipng with mise, "
        "and print where they are.",
    )
    sub.add_argument("--json", action="store_true", help="print a JSON report")
    sub.set_defaults(handler=_setup)
    return parser


def _add_paths(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("paths", nargs="*", type=Path, help="image files and folders")
    sub.add_argument(
        "--stdin", action="store_true", help="also read paths from stdin, one per line"
    )
    sub.add_argument("--json", action="store_true", help="print a JSON report")


def _paths(parser: argparse.ArgumentParser, args: argparse.Namespace) -> list[Path]:
    paths = list(args.paths)
    if args.stdin:
        paths.extend(Path(line.strip()) for line in sys.stdin if line.strip())
    if not paths:
        parser.error(f"{args.command}: give at least one path, or use --stdin")
    return paths


def _print_json(data: dict) -> None:
    print(json.dumps(data, indent=2))


def _check(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    items = check(_paths(parser, args))
    pending = [item for item in items if not item.done]
    if args.json:
        _print_json(
            {
                "results": [
                    {
                        "path": str(item.path),
                        "done": item.done,
                        "sidecar_status": item.sidecar_status,
                        "warning": item.warning,
                    }
                    for item in items
                ],
                "summary": {
                    "total": len(items),
                    "done": len(items) - len(pending),
                    "pending": len(pending),
                },
            }
        )
    else:
        for item in items:
            label = f"done ({item.sidecar_status})" if item.done else "pending"
            print(f"{label:<19} {item.path}")
            if item.warning:
                print(f"{'':<19} warning: {item.warning}")
        print(f"{len(items)} images: {len(pending)} pending")
    return EXIT_ERROR if pending else EXIT_OK


def _pin(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    items = pin(_paths(parser, args))
    failed = [item for item in items if item.status == PIN_ERROR]
    if args.json:
        _print_json(
            {
                "results": [
                    {"path": str(item.path), "status": item.status, "error": item.error}
                    for item in items
                ]
            }
        )
    else:
        for item in items:
            detail = f": {item.error}" if item.error else ""
            print(f"{item.status:<13} {item.path}{detail}")
    return EXIT_ERROR if failed else EXIT_OK


def _doctor(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    report = doctor(_paths(parser, args), delete_orphans=args.delete_orphans)
    sections = {
        "orphans": report.orphans,
        "deleted": report.deleted,
        "pending": report.pending,
        "temp_files": report.temp_files,
    }
    if args.json:
        data = {key: [str(path) for path in paths] for key, paths in sections.items()}
        _print_json({**data, "ok": report.ok})
    else:
        deleted = set(report.deleted)
        for path in report.orphans:
            label = "deleted orphan" if path in deleted else "orphan sidecar"
            print(f"{label:<15} {path}")
        for path in report.pending:
            print(f"{'pending':<15} {path}")
        for path in report.temp_files:
            print(f"{'temp file':<15} {path}")
        if report.ok:
            print("nothing to fix")
    return EXIT_OK if report.ok else EXIT_ERROR


def _setup(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    try:
        tools = [resolve_tool(PNGQUANT), resolve_tool(OXIPNG)]
    except ToolUnavailableError as e:
        if args.json:
            _print_json({"error": str(e)})
        print(e, file=sys.stderr)
        return EXIT_MISSING_TOOLS
    if args.json:
        _print_json(
            {
                "tools": {
                    tool.name: {"path": str(tool.path), "version": tool.version}
                    for tool in tools
                }
            }
        )
    else:
        for tool in tools:
            print(f"{tool.name} {tool.version} {tool.path}")
    return EXIT_OK


def _optimize(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    paths = _paths(parser, args)
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
        _print_json(_report_json(report, args.dry_run))
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
