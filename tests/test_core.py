# -*- coding: utf-8 -*-

from imgsqueeze.core import process
from imgsqueeze.core import tool_version
from imgsqueeze.core import Job
from imgsqueeze.core import PngTools
from imgsqueeze.core import Result
from imgsqueeze.core import STATUS_ALREADY_DONE
from imgsqueeze.core import STATUS_CONFLICT
from imgsqueeze.core import STATUS_ERROR
from imgsqueeze.core import STATUS_UNSUPPORTED

import os
import shutil
from pathlib import Path

import pytest
from PIL import Image

import imgsqueeze.core as core_module
from imgsqueeze.presets import get_preset
from imgsqueeze.sidecar import read_sidecar
from imgsqueeze.sidecar import sha256_file
from imgsqueeze.sidecar import sidecar_path
from imgsqueeze.sidecar import Sidecar
from imgsqueeze.sidecar import STATUS_NO_GAIN
from imgsqueeze.sidecar import STATUS_OPTIMIZED
from imgsqueeze.sidecar import STATUS_PINNED
from imgsqueeze.sidecar import write_sidecar

JPEG = "blog-cover.jpg"
WEBP = "investing-in-the-public-benefit.webp"  # already lossy: always no_gain
PNG = "diagram.png"
MISSING_TOOLS = "pngquant 3.0.3 is required to compress PNG files"


def _job(path: Path, **kwargs) -> Job:
    options = dict(
        path=path,
        preset=get_preset("normal"),
        min_gain=None,
        dry_run=False,
        png_tools=None,
        png_tools_error=MISSING_TOOLS,
    )
    options.update(kwargs)
    return Job(**options)


def _hidden_files(folder: Path) -> list[str]:
    return [name for name in os.listdir(folder) if name.startswith(".")]


class TestOptimized:
    def test_jpeg_is_replaced_and_recorded(self, img_dir):
        path = img_dir / JPEG
        path.chmod(0o640)
        before = path.stat().st_size
        result = process(_job(path))
        assert result.status == STATUS_OPTIMIZED
        assert result.format == "jpeg"
        assert result.preset == "normal"
        assert result.before == before
        assert result.after == path.stat().st_size < before
        assert 0.5 < result.gain < 1
        assert result.warnings == ()
        assert path.stat().st_mode & 0o777 == 0o640
        assert read_sidecar(path) == Sidecar(
            final_size=result.after,
            original_size=before,
            preset="normal",
            sha256=sha256_file(path),
            status=STATUS_OPTIMIZED,
            tool=tool_version(),
        )
        assert _hidden_files(img_dir) == []

    def test_png_is_replaced(self, img_dir, png_tools):
        pngquant, oxipng = png_tools
        path = img_dir / PNG
        result = process(
            _job(
                path,
                png_tools=PngTools(pngquant.path, oxipng.path),
                png_tools_error=None,
            )
        )
        assert result.status == STATUS_OPTIMIZED
        assert result.format == "png"
        assert read_sidecar(path).sha256 == sha256_file(path)

    def test_second_run_is_already_done_whatever_the_preset(self, img_dir):
        path = img_dir / JPEG
        first = process(_job(path))
        content = path.read_bytes()
        second = process(_job(path, preset=get_preset("aggressive")))
        assert second.status == STATUS_ALREADY_DONE
        assert second.sidecar_status == STATUS_OPTIMIZED
        assert second.preset == "normal"
        assert (second.before, second.after) == (first.before, first.after)
        assert path.read_bytes() == content

    def test_rerun_without_sidecar_is_no_gain(self, img_dir):
        # The fixed point: a compressed image does not get smaller again.
        path = img_dir / JPEG
        process(_job(path))
        content = path.read_bytes()
        sidecar_path(path).unlink()
        result = process(_job(path))
        assert result.status == STATUS_NO_GAIN
        assert path.read_bytes() == content


class TestNoGain:
    def test_original_is_kept_and_recorded(self, img_dir):
        path = img_dir / WEBP
        content = path.read_bytes()
        result = process(_job(path))
        assert result.status == STATUS_NO_GAIN
        assert result.before == result.after == len(content)
        assert result.gain == 0
        assert path.read_bytes() == content
        sidecar = read_sidecar(path)
        assert sidecar.status == STATUS_NO_GAIN
        assert sidecar.sha256 == sha256_file(path)
        assert sidecar.original_size == sidecar.final_size == len(content)

    def test_min_gain_overrides_the_default(self, img_dir):
        path = img_dir / JPEG
        content = path.read_bytes()
        result = process(_job(path, min_gain=0.99))
        assert result.status == STATUS_NO_GAIN
        assert path.read_bytes() == content


class TestDryRun:
    def test_optimized_writes_nothing(self, img_dir):
        path = img_dir / JPEG
        content = path.read_bytes()
        result = process(_job(path, dry_run=True))
        assert result.status == STATUS_OPTIMIZED
        assert result.after < result.before
        assert path.read_bytes() == content
        assert not sidecar_path(path).exists()

    def test_no_gain_writes_nothing(self, img_dir):
        path = img_dir / WEBP
        result = process(_job(path, dry_run=True))
        assert result.status == STATUS_NO_GAIN
        assert not sidecar_path(path).exists()


class TestSkipAndWarn:
    def test_pinned_image_is_already_done(self, img_dir):
        path = img_dir / JPEG
        content = path.read_bytes()
        pinned = Sidecar(
            final_size=len(content),
            original_size=len(content),
            preset=None,
            sha256=sha256_file(path),
            status=STATUS_PINNED,
            tool=tool_version(),
        )
        write_sidecar(path, pinned)
        result = process(_job(path))
        assert result.status == STATUS_ALREADY_DONE
        assert result.sidecar_status == STATUS_PINNED
        assert result.preset is None
        assert path.read_bytes() == content

    def test_foreign_json_is_never_overwritten(self, img_dir):
        path = img_dir / JPEG
        content = path.read_bytes()
        sidecar_path(path).write_text('{"prompt": "cat"}', encoding="utf-8")
        result = process(_job(path))
        assert result.status == STATUS_ERROR
        assert "is not a valid imgsqueeze sidecar; move or delete it" in result.error
        assert path.read_bytes() == content
        assert sidecar_path(path).read_text(encoding="utf-8") == '{"prompt": "cat"}'

    def test_webp_named_png_is_processed_as_webp(self, img_dir):
        path = img_dir / "disguised.png"
        shutil.move(img_dir / WEBP, path)
        result = process(_job(path))
        assert result.status == STATUS_NO_GAIN
        assert result.format == "webp"
        assert "content is WEBP but the extension is '.png'" in result.warnings[0]


class TestUnsupportedAndErrors:
    def test_gif_is_unsupported(self, tmp_path):
        path = tmp_path / "anim.gif"
        Image.new("RGB", (8, 8)).save(path)
        result = process(_job(path))
        assert result.status == STATUS_UNSUPPORTED
        assert result.format is None
        assert result.error == "GIF is not a PNG, JPEG or WebP image"

    def test_mpo_is_unsupported_with_a_clear_reason(self, tmp_path):
        path = tmp_path / "phone.jpg"
        frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
        frames[0].save(path, format="MPO", save_all=True, append_images=frames[1:])
        result = process(_job(path))
        assert result.status == STATUS_UNSUPPORTED
        assert result.error == "multi-picture JPEG (MPO) is not supported"

    def test_animated_webp_is_unsupported(self, tmp_path):
        path = tmp_path / "anim.webp"
        frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=100)
        result = process(_job(path))
        assert result.status == STATUS_UNSUPPORTED
        assert result.error == "animated image"
        assert not sidecar_path(path).exists()

    def test_missing_file(self, tmp_path):
        result = process(_job(tmp_path / "gone.jpg"))
        assert result.status == STATUS_ERROR
        assert "is not a regular file" in result.error

    def test_unreadable_file(self, img_dir):
        path = img_dir / JPEG
        path.chmod(0o000)
        try:
            result = process(_job(path))
        finally:
            path.chmod(0o644)
        assert result.status == STATUS_ERROR
        assert "cannot read" in result.error

    def test_not_an_image(self, tmp_path):
        path = tmp_path / "notes.png"
        path.write_text("hello")
        result = process(_job(path))
        assert result.status == STATUS_ERROR
        assert "Pillow cannot open" in result.error

    def test_corrupt_body_is_an_engine_error(self, img_dir):
        path = img_dir / JPEG
        content = path.read_bytes()
        path.write_bytes(content[: len(content) // 2])
        result = process(_job(path))
        assert result.status == STATUS_ERROR
        assert result.format == "jpeg"
        assert "cannot re-encode" in result.error

    def test_png_without_tools(self, img_dir):
        path = img_dir / PNG
        content = path.read_bytes()
        result = process(_job(path))
        assert result.status == STATUS_ERROR
        assert result.missing_tools is True
        assert result.error == MISSING_TOOLS
        assert path.read_bytes() == content

    def test_unreadable_sidecar(self, img_dir, monkeypatch):
        def fail(image_path, sha256):
            raise PermissionError("denied")

        monkeypatch.setattr(core_module, "find_done", fail)
        result = process(_job(img_dir / JPEG))
        assert result.status == STATUS_ERROR
        assert result.error == "cannot read the sidecar: denied"

    def test_unexpected_exception_is_an_error(self, img_dir, monkeypatch):
        def fail(*args):
            raise RuntimeError("boom")

        monkeypatch.setattr(core_module, "_compress", fail)
        result = process(_job(img_dir / JPEG))
        assert result.status == STATUS_ERROR
        assert result.error == "unexpected RuntimeError: boom"
        assert _hidden_files(img_dir) == []

    def test_jpeg_needs_no_png_tools(self, img_dir):
        result = process(_job(img_dir / JPEG))
        assert result.missing_tools is False

    def test_failed_replace_keeps_original(self, img_dir, monkeypatch):
        path = img_dir / JPEG
        content = path.read_bytes()

        def fail(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr(core_module.os, "replace", fail)
        result = process(_job(path))
        assert result.status == STATUS_ERROR
        assert "disk full" in result.error
        assert path.read_bytes() == content
        assert _hidden_files(img_dir) == []

    @pytest.mark.parametrize("name", [JPEG, WEBP])
    def test_failed_sidecar_write(self, img_dir, monkeypatch, name):
        def fail(image_path, sidecar):
            raise OSError("read-only")

        monkeypatch.setattr(core_module, "write_sidecar", fail)
        result = process(_job(img_dir / name))
        assert result.status == STATUS_ERROR
        assert "cannot write sidecar: read-only" in result.error

    def test_gain_is_none_without_sizes(self, tmp_path):
        assert Result(path=tmp_path, status=STATUS_ERROR).gain is None


class TestConflict:
    @pytest.mark.parametrize("name", [JPEG, WEBP])
    def test_file_changed_during_compression(self, img_dir, monkeypatch, name):
        # JPEG reaches the replace step, WebP the no_gain step.
        path = img_dir / name
        compress = core_module._compress

        def compress_while_someone_edits(*args):
            out = compress(*args)
            path.write_bytes(b"edited by another process")
            return out

        monkeypatch.setattr(core_module, "_compress", compress_while_someone_edits)
        result = process(_job(path))
        assert result.status == STATUS_CONFLICT
        assert path.read_bytes() == b"edited by another process"
        assert not sidecar_path(path).exists()
        assert _hidden_files(img_dir) == []

    @pytest.mark.parametrize("name", [JPEG, WEBP])
    def test_file_deleted_during_compression(self, img_dir, monkeypatch, name):
        # JPEG reaches the replace step, WebP the no_gain step.
        path = img_dir / name
        compress = core_module._compress

        def compress_while_someone_deletes(*args):
            out = compress(*args)
            path.unlink()
            return out

        monkeypatch.setattr(core_module, "_compress", compress_while_someone_deletes)
        assert process(_job(path)).status == STATUS_CONFLICT
        assert not sidecar_path(path).exists()
        assert _hidden_files(img_dir) == []

    def test_file_became_png_after_the_batch_started(self, img_dir):
        # The batch saw no PNG, so it resolved no tools.
        result = process(_job(img_dir / PNG, png_tools_error=None))
        assert result.status == STATUS_CONFLICT
        assert result.missing_tools is False
        assert "became a PNG" in result.warnings[0]


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.core",
        preview=False,
    )
