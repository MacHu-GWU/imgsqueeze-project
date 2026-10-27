# -*- coding: utf-8 -*-

"""
Compress a PNG with pngquant (lossy), then oxipng (lossless).

pngquant may decline to quantize: exit code 98 means the result would be
larger, 99 means the quality floor cannot be reached. Both are normal, and
oxipng then runs on the source image instead. Deciding whether the result is
worth keeping (``min_gain``) is the caller's job.
"""

from __future__ import annotations

import dataclasses
import subprocess

from pathlib import Path

from ..presets import Preset

#: pngquant exit code: the result would be larger than the input.
PNGQUANT_EXIT_LARGER = 98
#: pngquant exit code: the quality floor of ``--quality`` cannot be reached.
PNGQUANT_EXIT_QUALITY = 99

_TIMEOUT = 300


@dataclasses.dataclass(frozen=True)
class PngResult:
    """
    The output of :func:`compress_png`.
    """

    # fmt: off
    path: Path  #: The compressed file, inside the work directory.
    quantized: bool  #: ``False`` when pngquant declined (exit code 98 or 99).
    # fmt: on


class PngEngineError(Exception):
    """
    Raised when pngquant or oxipng fails, times out, or cannot be run.
    """


def compress_png(
    src: Path,
    workdir: Path,
    preset: Preset,
    pngquant: Path,
    oxipng: Path,
) -> PngResult:
    """
    Compress ``src`` into ``workdir``, leaving ``src`` unchanged.

    oxipng is limited to one thread, because the caller already runs one
    process per CPU.

    :param src: the PNG to compress.
    :param workdir: an existing directory for intermediate and final files.
    :param preset: gives the pngquant ``--quality`` range.
    :param pngquant: path of the pngquant binary.
    :param oxipng: path of the oxipng binary.
    :raises PngEngineError: if either tool fails.
    """
    quantized_path = workdir / "pngquant.png"
    optimized_path = workdir / "oxipng.png"
    low, high = preset.png_quality
    result = _run(
        [
            str(pngquant),
            f"--quality={low}-{high}",
            "--skip-if-larger",
            "--strip",
            "--speed",
            "3",
            "--force",
            "--output",
            str(quantized_path),
            "--",
            str(src),
        ]
    )
    if result.returncode == 0:
        quantized = True
        lossless_input = quantized_path
    elif result.returncode in (PNGQUANT_EXIT_LARGER, PNGQUANT_EXIT_QUALITY):
        quantized = False
        lossless_input = src
    else:
        raise PngEngineError(_failure("pngquant", result))
    result = _run(
        [
            str(oxipng),
            "-o",
            "2",
            "--strip",
            "safe",
            "--threads",
            "1",
            "--quiet",
            "--out",
            str(optimized_path),
            str(lossless_input),
        ]
    )
    if result.returncode != 0:
        raise PngEngineError(_failure("oxipng", result))
    return PngResult(path=optimized_path, quantized=quantized)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise PngEngineError(
            f"{' '.join(args)} timed out after {_TIMEOUT} seconds"
        ) from None
    except OSError as e:
        raise PngEngineError(f"cannot run {' '.join(args)}: {e}") from e


def _failure(name: str, result: subprocess.CompletedProcess) -> str:
    detail = (result.stderr or result.stdout).strip()
    return f"{name} exited with code {result.returncode}: {detail}"
