# -*- coding: utf-8 -*-

"""
Identify the image format and animation with Pillow.

Pillow reads the file content, never the file extension, so a WebP image saved
with a ``.png`` name is reported as WebP.
"""

from __future__ import annotations

import io

from PIL import Image

#: Format name of PNG images.
FORMAT_PNG = "png"

#: Format name of JPEG images, both ``.jpg`` and ``.jpeg``.
FORMAT_JPEG = "jpeg"

#: Format name of WebP images.
FORMAT_WEBP = "webp"

_PILLOW_FORMAT_NAMES = {
    "PNG": FORMAT_PNG,
    "JPEG": FORMAT_JPEG,
    "WEBP": FORMAT_WEBP,
}


def detect_format(data: bytes) -> str | None:
    """
    Return ``png``, ``jpeg`` or ``webp``, or ``None`` for any other format Pillow can open.

    Only the header is read. A file whose header is valid but whose body is
    corrupt still returns its format, and fails later in the codec.

    :param data: the whole file content.
    :raises UnidentifiedImageError: if Pillow cannot open the data at all.
    """
    fmt, _ = _inspect(data)
    return fmt


def is_animated(data: bytes) -> bool:
    """
    Return whether the image has more than one frame, which imgsqueeze skips.

    :param data: the whole file content.
    :raises UnidentifiedImageError: if Pillow cannot open the data at all.
    """
    _, animated = _inspect(data)
    return animated


def _inspect(data: bytes) -> tuple[str | None, bool]:
    with Image.open(io.BytesIO(data)) as img:
        fmt = _PILLOW_FORMAT_NAMES.get(img.format or "")
        return fmt, getattr(img, "n_frames", 1) > 1
