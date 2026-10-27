# -*- coding: utf-8 -*-

"""
Compress a WebP by re-encoding it (lossy) with Pillow.

The EXIF orientation is applied to the pixels first, because all EXIF is
dropped. Only the ICC profile and the alpha channel are kept. A lossless
source is re-encoded lossy too; when that does not pay off, the caller's
``min_gain`` check keeps the original. Animated WebP is not supported.
"""

from __future__ import annotations

import dataclasses

from pathlib import Path

from PIL import ExifTags
from PIL import Image
from PIL import ImageOps

from ..presets import Preset


@dataclasses.dataclass(frozen=True)
class WebpResult:
    """
    The output of :func:`compress_webp`.
    """

    # fmt: off
    path: Path  #: The compressed file, inside the work directory.
    oriented: bool  #: ``True`` when the EXIF orientation was applied to the pixels.
    # fmt: on


class WebpEngineError(Exception):
    """
    Raised when the source is animated, or cannot be decoded or encoded.
    """


def compress_webp(src: Path, workdir: Path, preset: Preset) -> WebpResult:
    """
    Re-encode ``src`` into ``workdir``, leaving ``src`` unchanged.

    :param src: the WebP to compress.
    :param workdir: an existing directory for the output file.
    :param preset: gives the WebP ``quality``.
    :raises WebpEngineError: if the image is animated, or Pillow cannot decode
        or encode it.
    """
    out = workdir / "pillow.webp"
    try:
        with Image.open(src) as image:
            if getattr(image, "n_frames", 1) > 1:
                raise WebpEngineError(f"{src} is animated, which is not supported")
            orientation = image.getexif().get(ExifTags.Base.Orientation, 1)
            icc_profile = image.info.get("icc_profile")
            upright = ImageOps.exif_transpose(image)
            options = dict(format="WEBP", quality=preset.webp_quality, method=6)
            if icc_profile:
                options["icc_profile"] = icc_profile
            upright.save(out, **options)
    except (OSError, Image.DecompressionBombError) as e:
        raise WebpEngineError(f"cannot re-encode {src}: {e}") from e
    return WebpResult(path=out, oriented=orientation != 1)
