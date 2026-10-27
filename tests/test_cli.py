# -*- coding: utf-8 -*-

from imgsqueeze.cli import main

import io
import json
from pathlib import Path

import pytest

import imgsqueeze.cli as cli_module
import imgsqueeze.runner as runner_module
from imgsqueeze.core import Result
from imgsqueeze.core import tool_version
from imgsqueeze.runner import Report
from imgsqueeze.tools import ToolUnavailableError

JPEG = "blog-cover.jpg"
WEBP = "investing-in-the-public-benefit.webp"  # already lossy: always no_gain
PNG = "diagram.png"


@pytest.fixture
def no_png_tools(monkeypatch):
    def fail(spec):
        raise ToolUnavailableError(f"{spec.name} is missing\nfix: mise install")

    monkeypatch.setattr(runner_module, "resolve_tool", fail)


def _exit_code(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as e:
        main(argv)
    return e.value.code


class TestUsage:
    def test_version(self, capsys):
        assert _exit_code(["--version"]) == 0
        assert capsys.readouterr().out.strip() == tool_version()

    def test_command_is_required(self, capsys):
        assert _exit_code([]) == 2

    def test_optimize_needs_a_path(self, capsys):
        assert _exit_code(["optimize"]) == 2
        assert "give at least one path" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "extra, message",
        [
            (["--preset", "extreme"], "invalid choice"),
            (["--min-gain", "2"], "min_gain must be between 0 and 1"),
            (["--jobs", "0"], "jobs must be at least 1"),
            (["--jobs", "many"], "invalid int value"),
        ],
    )
    def test_bad_arguments(self, tmp_path, capsys, extra, message):
        assert _exit_code(["optimize", str(tmp_path), *extra]) == 2
        assert message in capsys.readouterr().err


class TestOptimizeText:
    def test_results_and_summary(self, img_dir, capsys):
        jpeg, webp = img_dir / JPEG, img_dir / WEBP
        assert main(["optimize", str(jpeg), str(webp), "--jobs", "1"]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].startswith(f"optimized     {jpeg} 419423 -> ")
        assert lines[0].endswith("% saved)")
        assert lines[1].startswith(f"no_gain       {webp} 373482 -> 373482 bytes")
        assert lines[2].startswith("2 images: 1 optimized, 1 no_gain; saved ")

    def test_second_run_is_already_done(self, img_dir, capsys):
        jpeg = img_dir / JPEG
        main(["optimize", str(jpeg)])
        capsys.readouterr()
        assert main(["optimize", str(jpeg), "--preset", "light"]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert lines[0] == f"already_done  {jpeg} (optimized)"
        assert lines[1] == "1 images: 1 already_done; saved 0 bytes"

    def test_dry_run_and_warnings(self, img_dir, capsys):
        disguised = img_dir / "photo.png"
        (img_dir / JPEG).rename(disguised)
        assert main(["optimize", str(disguised), "--dry-run"]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert lines[1].startswith(f"{'':<13} warning: the content is JPEG")
        assert "would save" in lines[2]
        assert not disguised.with_name("photo.png.json").exists()

    def test_empty_folder(self, tmp_path, capsys):
        assert main(["optimize", str(tmp_path)]) == 0
        assert capsys.readouterr().out == "0 images: nothing to do; saved 0 bytes\n"

    def test_error_exits_with_1(self, img_dir, capsys):
        path = img_dir / "notes.png"
        path.write_text("not an image")
        assert main(["optimize", str(path)]) == 1
        assert capsys.readouterr().out.startswith(f"error         {path}: Pillow")

    def test_missing_tools_exits_with_3(self, img_dir, capsys, no_png_tools):
        code = main(
            ["optimize", str(img_dir / PNG), str(img_dir / JPEG), "--jobs", "1"]
        )
        assert code == 3
        captured = capsys.readouterr()
        lines = captured.out.splitlines()
        assert lines[0] == f"error         {img_dir / PNG}"
        assert lines[1].startswith("optimized")
        assert captured.err == "pngquant is missing\nfix: mise install\n"

    def test_conflict_line(self, tmp_path, capsys):
        report = Report(
            results=[Result(path=tmp_path, status="conflict", before=10)], tools=[]
        )
        cli_module._print_text(report, dry_run=False)
        assert "changed by another process" in capsys.readouterr().out


class TestOptimizeJson:
    def test_document(self, img_dir, capsys):
        jpeg = img_dir / JPEG
        assert main(["optimize", str(jpeg), "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["dry_run"] is False
        assert "tools" not in data
        (result,) = data["results"]
        assert result["path"] == str(jpeg)
        assert result["status"] == "optimized"
        assert result["format"] == "jpeg"
        assert result["preset"] == "normal"
        assert result["before"] == 419423
        assert result["after"] == jpeg.stat().st_size
        assert result["gain"] == round(1 - result["after"] / 419423, 4)
        assert result["warnings"] == []
        assert "error" not in result and "sidecar_status" not in result
        assert data["summary"]["total"] == 1
        assert data["summary"]["bytes_saved"] == 419423 - result["after"]

    def test_already_done_and_error_fields(self, img_dir, capsys, no_png_tools):
        main(["optimize", str(img_dir / WEBP)])
        capsys.readouterr()
        code = main(["optimize", str(img_dir / WEBP), str(img_dir / PNG), "--json"])
        assert code == 3
        captured = capsys.readouterr()
        done, failed = json.loads(captured.out)["results"]
        assert done["sidecar_status"] == "no_gain"
        assert done["gain"] == 0
        assert failed["error"] == "pngquant is missing\nfix: mise install"
        assert failed["gain"] is None
        assert "pngquant is missing" in captured.err

    def test_tools_listed_when_png_compressed(self, img_dir, capsys, png_tools):
        assert main(["optimize", str(img_dir / PNG), "--json"]) == 0
        tools = json.loads(capsys.readouterr().out)["tools"]
        assert tools["pngquant"]["version"] == "3.0.3"
        assert tools["oxipng"]["path"] == str(png_tools[1].path)


def test_paths_from_stdin(img_dir, capsys, monkeypatch):
    stdin = f"{img_dir / JPEG}\n\n{img_dir / WEBP}\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    assert main(["optimize", "--stdin", "--json", "--dry-run"]) == 0
    paths = [Path(r["path"]) for r in json.loads(capsys.readouterr().out)["results"]]
    assert paths == [img_dir / JPEG, img_dir / WEBP]


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.cli",
        preview=False,
    )
