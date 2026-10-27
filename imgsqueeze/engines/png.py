# -*- coding: utf-8 -*-

"""
Compress a PNG with pngquant (lossy), then oxipng (lossless).

Both tools drop the EXIF orientation, so an image whose orientation is not 1
is first rotated by Pillow (step 0). pngquant may decline to quantize: exit
code 98 means the result would be larger, 99 means the quality floor cannot be
reached. Both are normal, and oxipng then runs on the step 0 image instead.

An ICC profile is kept as follows: pngquant converts the pixels to sRGB and
tags the output sRGB, and oxipng keeps the profile when pngquant declined.

Deciding whether the result is worth keeping (``min_gain``) is the caller's job.
"""

from __future__ import annotations

import dataclasses
import subprocess

from pathlib import Path

from PIL import ExifTags
from PIL import Image
from PIL import ImageOps

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
    oriented: bool  #: ``True`` when the EXIF orientation was applied to the pixels.
    # fmt: on


class PngEngineError(Exception):
    """
    Raised when the source cannot be decoded, or when pngquant or oxipng
    fails, times out, or cannot be run.
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
    oriented_path = workdir / "oriented.png"
    quantized_path = workdir / "pngquant.png"
    optimized_path = workdir / "oxipng.png"
    oriented = _apply_orientation(src, oriented_path)
    if oriented:
        src = oriented_path
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
    return PngResult(path=optimized_path, quantized=quantized, oriented=oriented)


def _apply_orientation(src: Path, dst: Path) -> bool:
    """
    Write ``src`` rotated upright to ``dst``, keeping its ICC profile.

    Return ``False``, writing nothing, when the orientation is missing or 1.
    """
    try:
        with Image.open(src) as image:
            orientation = image.getexif().get(ExifTags.Base.Orientation, 1)
            if orientation == 1:
                return False
            upright = ImageOps.exif_transpose(image)
            icc_profile = image.info.get("icc_profile")
            if icc_profile:
                upright.save(dst, format="PNG", icc_profile=icc_profile)
            else:
                upright.save(dst, format="PNG")
    except (OSError, Image.DecompressionBombError) as e:
        raise PngEngineError(f"cannot decode {src}: {e}") from e
    return True


def _run(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, errors="replace", timeout=_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        raise PngEngineError(
            f"{' '.join(args)} timed out after {_TIMEOUT} seconds"
        ) from None
    except OSError as e:
        raise PngEngineError(f"cannot run {' '.join(args)}: {e}") from e


def _failure(name: str, result: subprocess.CompletedProcess) -> str:
    detail = (result.stderr or result.stdout).strip()
    return f"{name} exited with code {result.returncode}: {detail}"
