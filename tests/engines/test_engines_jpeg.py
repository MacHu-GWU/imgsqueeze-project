# -*- coding: utf-8 -*-

from imgsqueeze.engines.jpeg import compress_jpeg
from imgsqueeze.engines.jpeg import JpegEngineError

from pathlib import Path

import pytest
from PIL import ExifTags
from PIL import Image
from PIL import ImageCms

from imgsqueeze.presets import get_preset

NORMAL = get_preset("normal")
SRGB_ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _two_halves(path: Path, **save_kwargs) -> Path:
    # Wider than tall, red on the left, blue on the right.
    image = Image.new("RGB", (64, 32), (255, 0, 0))
    image.paste((0, 0, 255), (32, 0, 64, 32))
    image.save(path, quality=100, **save_kwargs)
    return path


def _exif(orientation: int) -> Image.Exif:
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientation
    exif[ExifTags.Base.Make] = "Camera"
    return exif


def _close(a: tuple, b: tuple, tolerance: int = 24) -> bool:
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


def test_real_image_is_smaller_and_progressive(img_dir, tmp_path):
    src = img_dir / "blog-cover.jpg"
    before = src.read_bytes()
    result = compress_jpeg(src, tmp_path, NORMAL)
    assert result.path.parent == tmp_path
    assert result.oriented is False
    assert result.path.stat().st_size < len(before)
    assert src.read_bytes() == before
    with Image.open(result.path) as out, Image.open(src) as original:
        assert out.format == "JPEG"
        assert out.size == original.size
        assert out.info.get("progressive") == 1


def test_orientation_is_applied_and_exif_dropped(tmp_path):
    # Orientation 6: the stored image is shown rotated 90 degrees clockwise,
    # so the red left half ends up on top.
    src = _two_halves(tmp_path / "rotated.jpg", exif=_exif(6))
    result = compress_jpeg(src, tmp_path, NORMAL)
    assert result.oriented is True
    with Image.open(result.path) as out:
        assert out.size == (32, 64)
        assert not out.getexif()
        rgb = out.convert("RGB")
        assert _close(rgb.getpixel((16, 8)), (255, 0, 0))
        assert _close(rgb.getpixel((16, 56)), (0, 0, 255))


def test_orientation_one_keeps_layout(tmp_path):
    src = _two_halves(tmp_path / "upright.jpg", exif=_exif(1))
    result = compress_jpeg(src, tmp_path, NORMAL)
    assert result.oriented is False
    with Image.open(result.path) as out:
        assert out.size == (64, 32)
        assert not out.getexif()


def test_icc_kept_and_comment_dropped(tmp_path):
    src = _two_halves(tmp_path / "tagged.jpg", icc_profile=SRGB_ICC, comment=b"hi")
    result = compress_jpeg(src, tmp_path, NORMAL)
    with Image.open(result.path) as out:
        assert out.info["icc_profile"] == SRGB_ICC
        assert "comment" not in out.info


def test_grayscale_stays_grayscale(tmp_path):
    src = tmp_path / "gray.jpg"
    Image.new("L", (32, 32), 128).save(src, quality=100)
    result = compress_jpeg(src, tmp_path, NORMAL)
    with Image.open(result.path) as out:
        assert out.mode == "L"


def test_undecodable_source(tmp_path):
    src = tmp_path / "bad.jpg"
    src.write_bytes(b"not a jpeg")
    with pytest.raises(JpegEngineError, match="cannot re-encode"):
        compress_jpeg(src, tmp_path, NORMAL)


def test_truncated_source(tmp_path):
    full = (_two_halves(tmp_path / "full.jpg")).read_bytes()
    src = tmp_path / "truncated.jpg"
    src.write_bytes(full[: len(full) // 2])
    with pytest.raises(JpegEngineError, match="cannot re-encode"):
        compress_jpeg(src, tmp_path, NORMAL)


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.engines.jpeg",
        preview=False,
    )
