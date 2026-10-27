# -*- coding: utf-8 -*-

from imgsqueeze.engines.webp import compress_webp
from imgsqueeze.engines.webp import WebpEngineError

from pathlib import Path

import pytest
from PIL import ExifTags
from PIL import Image
from PIL import ImageCms

from imgsqueeze.presets import get_preset

NORMAL = get_preset("normal")
SRGB_ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _two_halves(path: Path, mode: str = "RGB", **save_kwargs) -> Path:
    # Wider than tall, red on the left, blue on the right.
    image = Image.new(mode, (64, 32), (255, 0, 0, 255)[: len(mode)])
    image.paste((0, 0, 255, 255)[: len(mode)], (32, 0, 64, 32))
    image.save(path, lossless=True, **save_kwargs)
    return path


def _exif(orientation: int) -> Image.Exif:
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientation
    exif[ExifTags.Base.Make] = "Camera"
    return exif


def _close(a: tuple, b: tuple, tolerance: int = 24) -> bool:
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


def test_real_image_is_reencoded(img_dir, tmp_path):
    # This sample is already lossy WebP: at q80 the result is about 5% larger,
    # which the caller's min_gain check turns into no_gain.
    src = img_dir / "investing-in-the-public-benefit.webp"
    before = src.read_bytes()
    result = compress_webp(src, tmp_path, NORMAL)
    assert result.path.parent == tmp_path
    assert result.oriented is False
    assert src.read_bytes() == before
    with Image.open(result.path) as out, Image.open(src) as original:
        assert out.format == "WEBP"
        assert out.size == original.size


def test_lossless_photo_becomes_much_smaller(img_dir, tmp_path):
    src = tmp_path / "photo.webp"
    with Image.open(img_dir / "blog-cover.jpg") as image:
        image.save(src, lossless=True)
    result = compress_webp(src, tmp_path, NORMAL)
    assert result.path.stat().st_size < src.stat().st_size / 2


def test_orientation_is_applied_and_exif_dropped(tmp_path):
    # Orientation 6: the stored image is shown rotated 90 degrees clockwise,
    # so the red left half ends up on top.
    src = _two_halves(tmp_path / "rotated.webp", exif=_exif(6))
    result = compress_webp(src, tmp_path, NORMAL)
    assert result.oriented is True
    with Image.open(result.path) as out:
        assert out.size == (32, 64)
        assert not out.getexif()
        rgb = out.convert("RGB")
        assert _close(rgb.getpixel((16, 8)), (255, 0, 0))
        assert _close(rgb.getpixel((16, 56)), (0, 0, 255))


def test_alpha_and_icc_are_kept(tmp_path):
    src = tmp_path / "transparent.webp"
    image = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
    image.paste((0, 0, 0, 0), (0, 0, 16, 32))
    image.save(src, lossless=True, icc_profile=SRGB_ICC)
    result = compress_webp(src, tmp_path, NORMAL)
    with Image.open(result.path) as out:
        assert out.mode == "RGBA"
        assert out.getpixel((4, 16))[3] == 0
        assert out.getpixel((28, 16))[3] == 255
        assert out.info["icc_profile"] == SRGB_ICC


def test_lossless_source_is_reencoded(tmp_path):
    src = _two_halves(tmp_path / "lossless.webp")
    result = compress_webp(src, tmp_path, NORMAL)
    with Image.open(result.path) as out:
        assert out.format == "WEBP"
        assert out.size == (64, 32)


def test_animated_source_is_rejected(tmp_path):
    src = tmp_path / "animated.webp"
    frames = [Image.new("RGB", (16, 16), color) for color in ("red", "blue")]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=100)
    with pytest.raises(WebpEngineError, match="is animated"):
        compress_webp(src, tmp_path, NORMAL)


def test_undecodable_source(tmp_path):
    src = tmp_path / "bad.webp"
    src.write_bytes(b"not a webp")
    with pytest.raises(WebpEngineError, match="cannot re-encode"):
        compress_webp(src, tmp_path, NORMAL)


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.engines.webp",
        preview=False,
    )
