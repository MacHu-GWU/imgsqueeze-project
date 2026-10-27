# -*- coding: utf-8 -*-

"""
Compress a JPEG by re-encoding it with Pillow.

The EXIF orientation is applied to the pixels first, because all EXIF is
dropped. Only the ICC profile is kept. There is no need to estimate the
source quality: re-encoding an image that is already below the preset quality
does not make it smaller, and the caller's ``min_gain`` check keeps the
original.
"""

from __future__ import annotations

import dataclasses

from pathlib import Path

from PIL import ExifTags
from PIL import Image
from PIL import ImageOps

from ..presets import Preset


@dataclasses.dataclass(frozen=True)
class JpegResult:
    """
    The output of :func:`compress_jpeg`.
    """

    # fmt: off
    path: Path  #: The compressed file, inside the work directory.
    oriented: bool  #: ``True`` when the EXIF orientation was applied to the pixels.
    # fmt: on


class JpegEngineError(Exception):
    """
    Raised when the source cannot be decoded or encoded.
    """


def compress_jpeg(src: Path, workdir: Path, preset: Preset) -> JpegResult:
    """
    Re-encode ``src`` into ``workdir``, leaving ``src`` unchanged.

    :param src: the JPEG to compress.
    :param workdir: an existing directory for the output file.
    :param preset: gives the JPEG ``quality``.
    :raises JpegEngineError: if Pillow cannot decode or encode the image.
    """
    out = workdir / "pillow.jpg"
    try:
        with Image.open(src) as image:
            orientation = image.getexif().get(ExifTags.Base.Orientation, 1)
            icc_profile = image.info.get("icc_profile")
            upright = ImageOps.exif_transpose(image)
            options = dict(
                format="JPEG",
                quality=preset.jpeg_quality,
                optimize=True,
                progressive=True,
                # Pillow copies the source comment unless told otherwise.
                comment=b"",
            )
            if icc_profile:
                options["icc_profile"] = icc_profile
            upright.save(out, **options)
    except (OSError, Image.DecompressionBombError) as e:
        raise JpegEngineError(f"cannot re-encode {src}: {e}") from e
    return JpegResult(path=out, oriented=orientation != 1)
