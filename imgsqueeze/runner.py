# -*- coding: utf-8 -*-

"""
Run a whole batch: collect the images, skip the ones already done, process
the rest in parallel, and summarize.

pngquant and oxipng are resolved once, in the main process, and only when a
pending image is a PNG. When they are unavailable, every PNG fails with the
same message and the other images are processed as usual.
"""

from __future__ import annotations

import dataclasses
import os

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

from .core import Job
from .core import PngTools
from .core import process
from .core import Result
from .core import RESULT_STATUSES
from .core import STATUS_ALREADY_DONE
from .discover import expand_inputs
from .discover import triage
from .presets import DEFAULT_PRESET
from .presets import get_preset
from .sidecar import STATUS_OPTIMIZED
from .tools import OXIPNG
from .tools import PNGQUANT
from .tools import resolve_tool
from .tools import ResolvedTool
from .tools import ToolUnavailableError


@dataclasses.dataclass(frozen=True)
class Report:
    """
    The outcome of :func:`optimize`.
    """

    # fmt: off
    results: list[Result]  #: One result per image, in input order.
    tools: list[ResolvedTool]  #: External binaries used, empty when no PNG was compressed.
    # fmt: on

    @property
    def summary(self) -> dict[str, int]:
        """
        The number of results per status, the total, and ``bytes_saved``.
        """
        counts = {"total": len(self.results)}
        counts.update({status: 0 for status in RESULT_STATUSES})
        for result in self.results:
            counts[result.status] += 1
        counts["bytes_saved"] = sum(
            result.before - result.after
            for result in self.results
            if result.status == STATUS_OPTIMIZED
        )
        return counts

    @property
    def missing_tools(self) -> bool:
        """
        ``True`` when some PNG was not processed because pngquant or oxipng is
        unavailable.
        """
        return any(result.missing_tools for result in self.results)


def optimize(
    inputs: list[Path],
    preset: str = DEFAULT_PRESET,
    min_gain: float | None = None,
    jobs: int | None = None,
    dry_run: bool = False,
) -> Report:
    """
    Compress every image found in ``inputs`` that is not already done.

    :param inputs: files and directories; directories are searched recursively.
    :param preset: ``light``, ``normal`` or ``aggressive``.
    :param min_gain: minimum fraction of bytes saved to keep a result, such as
        ``0.05``. ``None`` uses the per-format default.
    :param jobs: number of worker processes, default the number of CPUs.
    :param dry_run: compress and report, but write nothing.
    :raises ValueError: if ``preset``, ``min_gain`` or ``jobs`` is invalid.
    """
    resolved_preset = get_preset(preset)
    if min_gain is not None and not 0 <= min_gain <= 1:
        raise ValueError(f"min_gain must be between 0 and 1, got {min_gain}")
    if jobs is not None and jobs < 1:
        raise ValueError(f"jobs must be at least 1, got {jobs}")

    paths = expand_inputs(inputs)
    split = triage(paths)
    by_path: dict[Path, Result] = {
        done.path: Result(
            path=done.path,
            status=STATUS_ALREADY_DONE,
            preset=done.sidecar.preset,
            before=done.sidecar.original_size,
            after=done.sidecar.final_size,
            sidecar_status=done.sidecar.status,
        )
        for done in split.done
    }
    # triage's sidecar warnings are not used: process() checks the sidecar
    # again and reports the same warning.
    pending = [item.path for item in split.pending]

    tools: list[ResolvedTool] = []
    png_tools = None
    png_tools_error = None
    if any(_is_png(path) for path in pending):
        try:
            tools = [resolve_tool(PNGQUANT), resolve_tool(OXIPNG)]
            png_tools = PngTools(pngquant=tools[0].path, oxipng=tools[1].path)
        except ToolUnavailableError as e:
            png_tools_error = str(e)

    job_list = [
        Job(
            path=path,
            preset=resolved_preset,
            min_gain=min_gain,
            dry_run=dry_run,
            png_tools=png_tools,
            png_tools_error=png_tools_error,
        )
        for path in pending
    ]
    for result in _run(job_list, jobs or os.cpu_count() or 1):
        by_path[result.path] = result
    return Report(results=[by_path[path] for path in paths], tools=tools)


def _run(job_list: list[Job], jobs: int) -> list[Result]:
    # A single image, or a single worker, is not worth starting a pool for.
    if len(job_list) <= 1 or jobs == 1:
        return [process(job) for job in job_list]
    with ProcessPoolExecutor(max_workers=min(jobs, len(job_list))) as pool:
        return list(pool.map(process, job_list))


def _is_png(path: Path) -> bool:
    # Image.open reads only the header. Any problem is reported by the worker.
    try:
        with Image.open(path) as image:
            return image.format == "PNG"
    except (OSError, Image.DecompressionBombError):
        return False
