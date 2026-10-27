# -*- coding: utf-8 -*-

from imgsqueeze.engines.png import compress_png
from imgsqueeze.engines.png import PngEngineError

import sys
from pathlib import Path

import pytest
from PIL import ExifTags
from PIL import Image
from PIL import ImageCms
from PIL import ImageOps

import imgsqueeze.engines.png as png_module
from imgsqueeze.presets import get_preset
from imgsqueeze.presets import Preset

NORMAL = get_preset("normal")
# A quality floor no smooth gradient can reach, so pngquant exits with 99.
STRICT = Preset(name="strict", png_quality=(95, 100), jpeg_quality=95, webp_quality=95)
SRGB_ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _rotated_exif(orientation: int) -> Image.Exif:
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientation
    return exif


def _gradient(path: Path, **save_kwargs) -> Path:
    # Too many colours for a palette: pngquant either gives up or grows the file.
    image = Image.new("RGB", (256, 128))
    image.putdata([(x, y, (x + y) // 2) for y in range(128) for x in range(256)])
    image.save(path, **save_kwargs)
    return path


def _two_halves(path: Path, **save_kwargs) -> Path:
    # Wider than tall, red on the left, blue on the right: easy to quantize exactly.
    image = Image.new("RGB", (64, 32), (255, 0, 0))
    image.paste((0, 0, 255), (32, 0, 64, 32))
    image.save(path, **save_kwargs)
    return path


def _pixels(path: Path) -> bytes:
    with Image.open(path) as image:
        return image.convert("RGBA").tobytes()


def _upright_pixels(path: Path) -> bytes:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGBA").tobytes()


def _script(path: Path, body: str) -> Path:
    path.write_text(f"#!{sys.executable}\nimport sys\n{body}\n")
    path.chmod(0o755)
    return path


@pytest.mark.parametrize("name", ["diagram.png", "pydantic-logo.png"])
def test_real_image_is_quantized_and_smaller(img_dir, tmp_path, png_tools, name):
    pngquant, oxipng = png_tools
    src = img_dir / name
    before = src.read_bytes()
    result = compress_png(src, tmp_path, NORMAL, pngquant.path, oxipng.path)
    assert result.quantized is True
    assert result.path.parent == tmp_path
    assert result.path.stat().st_size < len(before)
    assert src.read_bytes() == before
    with Image.open(result.path) as out, Image.open(src) as original:
        assert out.format == "PNG"
        assert out.size == original.size


def test_larger_result_falls_back_to_lossless(tmp_path, png_tools):
    pngquant, oxipng = png_tools
    src = _gradient(tmp_path / "gradient.png")
    work = tmp_path / "work"
    work.mkdir()
    result = compress_png(src, work, NORMAL, pngquant.path, oxipng.path)
    assert result.quantized is False
    assert _pixels(result.path) == _pixels(src)


def test_unreachable_quality_falls_back_to_lossless(tmp_path, png_tools):
    pngquant, oxipng = png_tools
    src = _gradient(tmp_path / "gradient.png")
    work = tmp_path / "work"
    work.mkdir()
    result = compress_png(src, work, STRICT, pngquant.path, oxipng.path)
    assert result.quantized is False
    assert _pixels(result.path) == _pixels(src)


@pytest.mark.parametrize("orientation", [6, 3, 8])
def test_exif_orientation_is_applied(tmp_path, png_tools, orientation):
    # pngquant and oxipng both drop eXIf, so step 0 must rotate the pixels.
    pngquant, oxipng = png_tools
    src = _two_halves(tmp_path / "rotated.png", exif=_rotated_exif(orientation))
    work = tmp_path / "work"
    work.mkdir()
    result = compress_png(src, work, NORMAL, pngquant.path, oxipng.path)
    assert result.oriented is True
    assert _pixels(result.path) == _upright_pixels(src)
    with Image.open(result.path) as out:
        assert ExifTags.Base.Orientation not in out.getexif()


def test_orientation_one_is_left_alone(tmp_path, png_tools):
    pngquant, oxipng = png_tools
    src = _two_halves(tmp_path / "upright.png", exif=_rotated_exif(1))
    work = tmp_path / "work"
    work.mkdir()
    result = compress_png(src, work, NORMAL, pngquant.path, oxipng.path)
    assert result.oriented is False
    assert not (work / "oriented.png").exists()
    assert _pixels(result.path) == _pixels(src)


def test_icc_kept_when_rotated_and_not_quantized(tmp_path, png_tools):
    pngquant, oxipng = png_tools
    src = _gradient(
        tmp_path / "gradient.png", exif=_rotated_exif(6), icc_profile=SRGB_ICC
    )
    work = tmp_path / "work"
    work.mkdir()
    result = compress_png(src, work, STRICT, pngquant.path, oxipng.path)
    assert result.oriented is True
    assert result.quantized is False
    assert _pixels(result.path) == _upright_pixels(src)
    with Image.open(result.path) as out:
        assert out.size == (128, 256)
        assert out.info["icc_profile"] == SRGB_ICC


def test_icc_becomes_srgb_when_quantized(tmp_path, png_tools):
    # pngquant converts the pixels from the ICC profile to sRGB and tags the
    # result sRGB instead of keeping the profile.
    pngquant, oxipng = png_tools
    src = _two_halves(tmp_path / "tagged.png", icc_profile=SRGB_ICC)
    work = tmp_path / "work"
    work.mkdir()
    result = compress_png(src, work, NORMAL, pngquant.path, oxipng.path)
    assert result.quantized is True
    assert _pixels(result.path) == _pixels(src)
    with Image.open(result.path) as out:
        assert "icc_profile" not in out.info
        assert "srgb" in out.info


def test_undecodable_source(tmp_path):
    src = tmp_path / "bad.png"
    src.write_bytes(b"not a png")
    with pytest.raises(PngEngineError, match="cannot decode"):
        compress_png(src, tmp_path, NORMAL, Path("pngquant"), Path("oxipng"))


# The tests below use fake binaries: executable scripts with a shebang, which
# Windows cannot run directly.
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")


@posix_only
def test_pngquant_failure_is_reported(tmp_path):
    pngquant = _script(
        tmp_path / "pngquant", "print('cannot decode', file=sys.stderr)\nsys.exit(25)"
    )
    src = _gradient(tmp_path / "gradient.png")
    with pytest.raises(PngEngineError) as e:
        compress_png(src, tmp_path, NORMAL, pngquant, pngquant)
    assert str(e.value) == "pngquant exited with code 25: cannot decode"


@posix_only
def test_oxipng_failure_is_reported(tmp_path):
    pngquant = _script(tmp_path / "pngquant", "sys.exit(99)")
    oxipng = _script(
        tmp_path / "oxipng", "print('broken input', file=sys.stderr)\nsys.exit(1)"
    )
    src = _gradient(tmp_path / "gradient.png")
    with pytest.raises(PngEngineError) as e:
        compress_png(src, tmp_path, NORMAL, pngquant, oxipng)
    assert str(e.value) == "oxipng exited with code 1: broken input"


@posix_only
def test_tool_that_cannot_run(tmp_path):
    pngquant = tmp_path / "pngquant"
    pngquant.write_text("not executable")
    src = _gradient(tmp_path / "gradient.png")
    with pytest.raises(PngEngineError, match="cannot run"):
        compress_png(src, tmp_path, NORMAL, pngquant, pngquant)


@posix_only
def test_tool_that_hangs(tmp_path, monkeypatch):
    pngquant = _script(tmp_path / "pngquant", "import time\ntime.sleep(5)")
    src = _gradient(tmp_path / "gradient.png")
    monkeypatch.setattr(png_module, "_TIMEOUT", 0.5)
    with pytest.raises(PngEngineError, match="timed out after 0.5 seconds"):
        compress_png(src, tmp_path, NORMAL, pngquant, pngquant)


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.engines.png",
        preview=False,
    )
