# -*- coding: utf-8 -*-

"""
Three compression presets, and the default minimum gain per image format.
"""

from __future__ import annotations

import dataclasses

#: Preset used when the caller does not choose one.
DEFAULT_PRESET = "normal"


@dataclasses.dataclass(frozen=True)
class Preset:
    """
    Quality settings of one preset.

    pngquant gives up with exit code 99 when it cannot reach ``png_quality``'s
    lower bound, so the original PNG is kept.
    """

    # fmt: off
    name: str  #: Preset name, one of ``light``, ``normal``, ``aggressive``.
    png_quality: tuple[int, int]  #: ``(min, max)`` passed to pngquant ``--quality``.
    jpeg_quality: int  #: Pillow ``quality`` for JPEG re-encoding.
    webp_quality: int  #: Pillow ``quality`` for WebP re-encoding.
    # fmt: on


PRESETS: dict[str, Preset] = {
    "light": Preset(
        name="light",
        png_quality=(80, 95),
        jpeg_quality=88,
        webp_quality=88,
    ),
    "normal": Preset(
        name="normal",
        png_quality=(65, 80),
        jpeg_quality=80,
        webp_quality=80,
    ),
    "aggressive": Preset(
        name="aggressive",
        png_quality=(50, 70),
        jpeg_quality=70,
        webp_quality=70,
    ),
}

#: Valid preset names, from the lightest to the most aggressive.
PRESET_NAMES: tuple[str, ...] = tuple(PRESETS)

#: Default minimum relative size reduction per format, e.g. ``0.05`` means 5%.
#: A smaller gain keeps the original file.
DEFAULT_MIN_GAIN: dict[str, float] = {
    "png": 0.05,
    "jpeg": 0.05,
    "webp": 0.10,
}


def get_preset(name: str) -> Preset:
    """
    Return the preset called ``name``.

    :raises ValueError: if ``name`` is not one of ``PRESET_NAMES``.
    """
    try:
        return PRESETS[name]
    except KeyError:
        raise ValueError(
            f"unknown preset {name!r}, expected one of {', '.join(PRESET_NAMES)}"
        ) from None
