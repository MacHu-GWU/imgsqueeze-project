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


class TestCheck:
    def test_pending_then_done(self, img_dir, capsys):
        webp = img_dir / WEBP
        assert main(["check", str(webp)]) == 1
        assert (
            capsys.readouterr().out
            == f"pending             {webp}\n1 images: 1 pending\n"
        )
        main(["optimize", str(webp)])
        capsys.readouterr()
        assert main(["check", str(webp)]) == 0
        assert capsys.readouterr().out.startswith(f"done (no_gain)      {webp}\n")

    def test_json_and_warning(self, img_dir, capsys):
        jpeg = img_dir / JPEG
        (img_dir / f"{JPEG}.json").write_text("{", encoding="utf-8")
        assert main(["check", str(jpeg), "--json"]) == 1
        data = json.loads(capsys.readouterr().out)
        assert data["summary"] == {"total": 1, "done": 0, "pending": 1}
        assert data["results"][0]["done"] is False
        assert "not valid JSON" in data["results"][0]["warning"]
        assert main(["check", str(jpeg)]) == 1
        assert "warning: " in capsys.readouterr().out

    def test_needs_a_path(self, capsys):
        assert _exit_code(["check"]) == 2
        assert "check: give at least one path" in capsys.readouterr().err


class TestPin:
    def test_pin_then_optimize_skips(self, img_dir, capsys):
        jpeg = img_dir / JPEG
        content = jpeg.read_bytes()
        assert main(["pin", str(jpeg)]) == 0
        assert capsys.readouterr().out == f"pinned        {jpeg}\n"
        assert main(["optimize", str(jpeg)]) == 0
        assert "(pinned)" in capsys.readouterr().out
        assert jpeg.read_bytes() == content

    def test_failure_exits_with_1(self, tmp_path, capsys):
        missing = tmp_path / "gone.png"
        assert main(["pin", str(missing), "--json"]) == 1
        (item,) = json.loads(capsys.readouterr().out)["results"]
        assert item["status"] == "error"
        assert main(["pin", str(missing)]) == 1
        assert "is not a regular file" in capsys.readouterr().out


class TestDoctor:
    def test_problems_then_fixed(self, tmp_path, capsys):
        orphan = tmp_path / "gone.png.json"
        orphan.write_text("{}")
        temp = tmp_path / ".cover.png.ab12cd34.tmp"
        temp.write_bytes(b"x")
        pending = tmp_path / "new.jpg"
        pending.write_bytes(b"x")
        assert main(["doctor", str(tmp_path)]) == 1
        assert capsys.readouterr().out.splitlines() == [
            f"orphan sidecar  {orphan}",
            f"pending         {pending}",
            f"temp file       {temp}",
        ]
        temp.unlink()
        main(["pin", str(pending)])
        capsys.readouterr()
        assert main(["doctor", str(tmp_path), "--delete-orphans"]) == 0
        assert capsys.readouterr().out.splitlines() == [
            f"deleted orphan  {orphan}",
            "nothing to fix",
        ]

    def test_json(self, tmp_path, capsys):
        assert main(["doctor", str(tmp_path), "--json"]) == 0
        assert json.loads(capsys.readouterr().out) == {
            "orphans": [],
            "deleted": [],
            "pending": [],
            "temp_files": [],
            "ok": True,
        }


class TestSetup:
    def test_success(self, capsys, png_tools):
        assert main(["setup"]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].startswith("pngquant 3.0.3 /")
        assert lines[1].startswith("oxipng 10.2.1 /")
        assert main(["setup", "--json"]) == 0
        tools = json.loads(capsys.readouterr().out)["tools"]
        assert tools["oxipng"]["path"] == str(png_tools[1].path)

    @pytest.mark.parametrize("as_json", [False, True])
    def test_failure_exits_with_3(self, capsys, monkeypatch, as_json):
        def fail(spec):
            raise ToolUnavailableError("mise is not on PATH")

        monkeypatch.setattr(cli_module, "resolve_tool", fail)
        argv = ["setup", "--json"] if as_json else ["setup"]
        assert main(argv) == 3
        captured = capsys.readouterr()
        assert captured.err == "mise is not on PATH\n"
        if as_json:
            assert json.loads(captured.out) == {"error": "mise is not on PATH"}
        else:
            assert captured.out == ""


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.cli",
        preview=False,
    )
