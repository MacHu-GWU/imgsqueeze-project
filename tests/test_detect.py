# -*- coding: utf-8 -*-

from imgsqueeze.detect import detect_format
from imgsqueeze.detect import is_animated
from imgsqueeze.detect import FORMAT_JPEG
from imgsqueeze.detect import FORMAT_PNG
from imgsqueeze.detect import FORMAT_WEBP

import io

import pytest
from PIL import Image
from PIL import UnidentifiedImageError


def _encode(fmt: str, frames: int = 1) -> bytes:
    """
    Encode a small image with Pillow, as several frames when ``frames > 1``.
    """
    buf = io.BytesIO()
    images = [Image.new("RGB", (8, 8), (i * 40, 0, 0)) for i in range(frames)]
    if frames > 1:
        images[0].save(buf, fmt, save_all=True, append_images=images[1:])
    else:
        images[0].save(buf, fmt)
    return buf.getvalue()


@pytest.mark.parametrize(
    "data, expected",
    [
        (_encode("PNG"), FORMAT_PNG),
        (_encode("JPEG"), FORMAT_JPEG),
        (_encode("WEBP"), FORMAT_WEBP),
        (_encode("GIF"), None),
    ],
)
def test_detect_format(data, expected):
    assert detect_format(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image at all",
        b"\x89PNG\r\n\x1a\n" + b"\xff" * 40,
        b"\xff\xd8\xff\xe0",
    ],
)
def test_detect_format_unopenable(data):
    with pytest.raises(UnidentifiedImageError):
        detect_format(data)


def test_detect_format_ignores_extension():
    # the function only sees bytes, so a WebP body is WebP whatever the name is
    webp_bytes = _encode("WEBP")
    assert detect_format(webp_bytes) == FORMAT_WEBP


@pytest.mark.parametrize(
    "data, expected",
    [
        (_encode("PNG"), False),
        (_encode("PNG", frames=3), True),
        (_encode("WEBP"), False),
        (_encode("WEBP", frames=3), True),
        (_encode("JPEG"), False),
    ],
)
def test_is_animated(data, expected):
    assert is_animated(data) is expected


def test_is_animated_unopenable():
    with pytest.raises(UnidentifiedImageError):
        is_animated(b"")


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.detect",
        preview=False,
    )
