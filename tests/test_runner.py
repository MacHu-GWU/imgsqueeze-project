# -*- coding: utf-8 -*-

from imgsqueeze.runner import optimize

import pytest
from PIL import Image

import imgsqueeze.runner as runner_module
from imgsqueeze.sidecar import sha256_file
from imgsqueeze.sidecar import Sidecar
from imgsqueeze.sidecar import write_sidecar
from imgsqueeze.tools import ToolUnavailableError

JPEG = "blog-cover.jpg"
WEBP = "investing-in-the-public-benefit.webp"  # already lossy: always no_gain
PNGS = ("diagram.png", "pydantic-logo.png")


@pytest.fixture
def no_png_tools(monkeypatch):
    """
    Make pngquant and oxipng unavailable, and record each resolve attempt.
    """
    calls = []

    def fail(spec):
        calls.append(spec.name)
        raise ToolUnavailableError(f"{spec.name} is missing")

    monkeypatch.setattr(runner_module, "resolve_tool", fail)
    return calls


@pytest.fixture
def no_pool(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no process pool expected")

    monkeypatch.setattr(runner_module, "ProcessPoolExecutor", fail)


def _statuses(report) -> dict[str, str]:
    return {result.path.name: result.status for result in report.results}


def test_mixed_batch_without_png_tools(img_dir, no_png_tools):
    (img_dir / "notes.txt").write_text("not an image")  # not picked up from a folder
    gif = img_dir / "anim.gif"
    Image.new("RGB", (8, 8)).save(gif)
    report = optimize([img_dir, gif], jobs=1)
    assert _statuses(report) == {
        "blog-cover.jpg": "optimized",
        "diagram.png": "error",
        "anim.gif": "unsupported",
        WEBP: "no_gain",
        "pydantic-logo.png": "error",
    }
    pngs = [r for r in report.results if r.path.name in PNGS]
    assert all(r.error == "pngquant is missing" and r.missing_tools for r in pngs)
    assert report.missing_tools is True
    assert report.tools == []
    assert no_png_tools == ["pngquant"]  # resolved once for the whole batch


def test_png_batch_with_real_tools(img_dir, png_tools):
    report = optimize([img_dir], jobs=1)
    assert _statuses(report)["diagram.png"] == "optimized"
    assert _statuses(report)["pydantic-logo.png"] == "optimized"
    assert [tool.name for tool in report.tools] == ["pngquant", "oxipng"]
    assert report.missing_tools is False


def test_batch_without_png_does_not_resolve_tools(img_dir, no_png_tools):
    report = optimize([img_dir / JPEG, img_dir / WEBP], jobs=1)
    assert no_png_tools == []
    assert report.tools == []
    assert report.missing_tools is False


def test_done_png_does_not_resolve_tools(img_dir, no_png_tools):
    png = img_dir / PNGS[0]
    size = png.stat().st_size
    pinned = Sidecar(
        final_size=size,
        original_size=size,
        preset=None,
        sha256=sha256_file(png),
        status="pinned",
        tool="imgsqueeze 0.1.1",
    )
    write_sidecar(png, pinned)
    report = optimize([png], jobs=1)
    assert _statuses(report) == {png.name: "already_done"}
    assert no_png_tools == []


def test_results_follow_input_order_and_merge_done(img_dir, no_png_tools):
    optimize([img_dir / WEBP], jobs=1)
    report = optimize([img_dir / WEBP, img_dir / JPEG, img_dir / WEBP], jobs=1)
    assert [r.path.name for r in report.results] == [WEBP, JPEG]
    done = report.results[0]
    assert done.status == "already_done"
    assert done.sidecar_status == "no_gain"
    assert done.preset == "normal"
    assert done.before == done.after


def test_summary(img_dir, no_png_tools):
    jpeg = img_dir / JPEG
    before = jpeg.stat().st_size
    report = optimize([img_dir], jobs=1)
    assert report.summary == {
        "total": 4,
        "optimized": 1,
        "no_gain": 1,
        "already_done": 0,
        "conflict": 0,
        "unsupported": 0,
        "error": 2,
        "bytes_saved": before - jpeg.stat().st_size,
    }


def test_dry_run_writes_nothing(img_dir, no_png_tools):
    jpeg = img_dir / JPEG
    content = jpeg.read_bytes()
    report = optimize([img_dir], dry_run=True, jobs=1)
    assert report.summary["optimized"] == 1
    assert report.summary["bytes_saved"] > 0
    assert jpeg.read_bytes() == content
    assert list(img_dir.glob("*.json")) == []


def test_parallel_matches_serial(img_dir, no_png_tools):
    files = [img_dir / JPEG, img_dir / WEBP]
    report = optimize(files, jobs=2, dry_run=True)
    serial = optimize(files, jobs=1, dry_run=True)
    assert report.results == serial.results


def test_single_file_skips_the_pool(img_dir, no_png_tools, no_pool):
    report = optimize([img_dir / JPEG], jobs=8)
    assert _statuses(report) == {JPEG: "optimized"}


def test_default_jobs(img_dir, no_png_tools, no_pool):
    assert optimize([img_dir / WEBP]).summary["no_gain"] == 1


def test_missing_input_is_an_error(img_dir, no_png_tools):
    missing = img_dir / "gone.png"
    report = optimize([missing], jobs=1)
    assert _statuses(report) == {"gone.png": "error"}
    assert no_png_tools == []


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(preset="extreme"), "unknown preset"),
        (dict(min_gain=1.5), "min_gain must be between 0 and 1"),
        (dict(min_gain=-0.1), "min_gain must be between 0 and 1"),
        (dict(jobs=0), "jobs must be at least 1"),
    ],
)
def test_invalid_arguments(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        optimize([tmp_path], **kwargs)


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.runner",
        preview=False,
    )
