# -*- coding: utf-8 -*-

from imgsqueeze.tools import resolve_tool
from imgsqueeze.tools import ToolUnavailableError
from imgsqueeze.tools import MISE_INSTALL_URL
from imgsqueeze.tools import OXIPNG
from imgsqueeze.tools import PNGQUANT

import pytest

import sys
from pathlib import Path

import imgsqueeze.tools as tools_module

# The fakes below are executable Python scripts with a shebang, which Windows
# cannot run directly. imgsqueeze only targets macOS (01-scope.md in the
# maintain-imgsqueeze-base skill).
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")

_FAKE_MISE = """#!{python}
# A stand-in for mise: supports "which <bin> --tool <spec>" and "install <spec>".
import os
import pathlib
import sys

state = pathlib.Path(os.environ["FAKE_MISE_STATE"])
if pathlib.Path("mise.toml").exists():
    # like mise with an untrusted or broken config in the current directory
    print("mise ERROR Config files in mise.toml are not trusted", file=sys.stderr)
    sys.exit(1)
with (state / "calls.log").open("a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")


def binary_path(spec, name):
    return state / "installs" / spec.replace(":", "-").replace("@", "-") / name


command = sys.argv[1]
if command == "which":
    name, spec = sys.argv[2], sys.argv[4]
    binary = binary_path(spec, name)
    if binary.exists() and not os.environ.get("FAKE_MISE_WHICH_BROKEN"):
        print(binary)
        sys.exit(0)
    print(f"mise ERROR {{name}} is not a mise bin", file=sys.stderr)
    sys.exit(1)
if command == "install":
    if os.environ.get("FAKE_MISE_INSTALL_FAIL"):
        print("network unreachable", file=sys.stderr)
        sys.exit(1)
    spec = sys.argv[2]
    tool, version = spec.rsplit("@", 1)
    name = tool.split(":")[-1]
    binary = binary_path(spec, name)
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(f"#!{{sys.executable}}\\nprint('{{name}} {{version}}')\\n")
    binary.chmod(0o755)
    sys.exit(0)
sys.exit(2)
"""


def _make_script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n{body}\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def fake_mise(tmp_path, monkeypatch) -> Path:
    """
    Put a fake mise alone on PATH, and return its state directory.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    mise = bin_dir / "mise"
    mise.write_text(_FAKE_MISE.format(python=sys.executable))
    mise.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("FAKE_MISE_STATE", str(state))
    monkeypatch.delenv(PNGQUANT.env_var, raising=False)
    monkeypatch.delenv(OXIPNG.env_var, raising=False)
    return state


@pytest.fixture
def no_mise(tmp_path, monkeypatch):
    """
    Leave PATH with no mise on it, and clear the override variables.
    """
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.delenv(PNGQUANT.env_var, raising=False)
    monkeypatch.delenv(OXIPNG.env_var, raising=False)


def _calls(state: Path) -> list[str]:
    return (state / "calls.log").read_text().splitlines()


def test_pinned_specs():
    assert PNGQUANT.mise_spec == "conda:pngquant@3.0.3"
    assert OXIPNG.mise_spec == "oxipng@10.2.1"


class TestResolveWithMise:
    def test_missing_tool_is_installed_then_found(self, fake_mise):
        tool = resolve_tool(PNGQUANT)
        assert tool.name == "pngquant"
        assert tool.version == "3.0.3"
        assert tool.path.is_file()
        assert _calls(fake_mise) == [
            "which pngquant --tool conda:pngquant@3.0.3",
            "install conda:pngquant@3.0.3",
            "which pngquant --tool conda:pngquant@3.0.3",
        ]

    def test_project_mise_config_is_not_read(self, fake_mise, tmp_path, monkeypatch):
        project = tmp_path / "blog"
        project.mkdir()
        (project / "mise.toml").write_text("[env]\n_.file = '.env'\n")
        monkeypatch.chdir(project)
        assert resolve_tool(PNGQUANT).version == "3.0.3"

    def test_installed_tool_is_not_installed_again(self, fake_mise):
        first = resolve_tool(OXIPNG)
        (fake_mise / "calls.log").unlink()
        second = resolve_tool(OXIPNG)
        assert second == first
        assert _calls(fake_mise) == ["which oxipng --tool oxipng@10.2.1"]

    def test_install_failure_reports_mise_output(self, fake_mise, monkeypatch):
        monkeypatch.setenv("FAKE_MISE_INSTALL_FAIL", "1")
        with pytest.raises(ToolUnavailableError) as e:
            resolve_tool(PNGQUANT)
        message = str(e.value)
        assert "mise install conda:pngquant@3.0.3 failed" in message
        assert "network unreachable" in message
        assert PNGQUANT.env_var in message

    def test_which_still_fails_after_install(self, fake_mise, monkeypatch):
        monkeypatch.setenv("FAKE_MISE_WHICH_BROKEN", "1")
        with pytest.raises(ToolUnavailableError, match="still cannot find oxipng"):
            resolve_tool(OXIPNG)

    def test_mise_not_on_path(self, no_mise):
        with pytest.raises(ToolUnavailableError) as e:
            resolve_tool(PNGQUANT)
        message = str(e.value)
        assert "mise is not on PATH" in message
        assert MISE_INSTALL_URL in message
        assert "pngquant 3.0.3 is required" in message


class TestResolveOverride:
    def test_valid_override_skips_mise(self, tmp_path, no_mise, monkeypatch):
        binary = _make_script(tmp_path / "pngquant", "print('3.0.4 (October 2026)')")
        monkeypatch.setenv(PNGQUANT.env_var, str(binary))
        tool = resolve_tool(PNGQUANT)
        assert tool.path == binary
        assert tool.version == "3.0.4"

    def test_version_compared_as_numbers(self, tmp_path, no_mise, monkeypatch):
        binary = _make_script(tmp_path / "oxipng", "print('oxipng 10.10.0')")
        monkeypatch.setenv(OXIPNG.env_var, str(binary))
        assert resolve_tool(OXIPNG).version == "10.10.0"

    def test_override_too_old(self, tmp_path, no_mise, monkeypatch):
        binary = _make_script(tmp_path / "pngquant", "print('3.0.2')")
        monkeypatch.setenv(PNGQUANT.env_var, str(binary))
        with pytest.raises(ToolUnavailableError, match="older than 3.0.3"):
            resolve_tool(PNGQUANT)

    def test_override_missing_file(self, tmp_path, no_mise, monkeypatch):
        monkeypatch.setenv(PNGQUANT.env_var, str(tmp_path / "nope"))
        with pytest.raises(ToolUnavailableError, match="is not an executable file"):
            resolve_tool(PNGQUANT)

    def test_override_not_executable(self, tmp_path, no_mise, monkeypatch):
        binary = tmp_path / "pngquant"
        binary.write_text("not executable")
        monkeypatch.setenv(PNGQUANT.env_var, str(binary))
        with pytest.raises(ToolUnavailableError, match="is not an executable file"):
            resolve_tool(PNGQUANT)

    def test_override_reports_no_version(self, tmp_path, no_mise, monkeypatch):
        binary = _make_script(tmp_path / "pngquant", "print('hello')")
        monkeypatch.setenv(PNGQUANT.env_var, str(binary))
        with pytest.raises(ToolUnavailableError, match="did not report a version"):
            resolve_tool(PNGQUANT)

    def test_override_exits_with_error(self, tmp_path, no_mise, monkeypatch):
        binary = _make_script(
            tmp_path / "pngquant", "import sys\nprint('3.0.3')\nsys.exit(1)"
        )
        monkeypatch.setenv(PNGQUANT.env_var, str(binary))
        with pytest.raises(ToolUnavailableError, match="did not report a version"):
            resolve_tool(PNGQUANT)

    def test_override_cannot_be_run(self, tmp_path, no_mise, monkeypatch):
        binary = tmp_path / "pngquant"
        binary.write_bytes(b"\x00\x01 not a program")
        binary.chmod(0o755)
        monkeypatch.setenv(PNGQUANT.env_var, str(binary))
        with pytest.raises(ToolUnavailableError, match="cannot run"):
            resolve_tool(PNGQUANT)

    def test_override_with_non_utf8_output(self, tmp_path, no_mise, monkeypatch):
        body = "import sys\nsys.stdout.buffer.write(b'\\xffpngquant 3.0.3\\n')"
        binary = _make_script(tmp_path / "pngquant", body)
        monkeypatch.setenv(PNGQUANT.env_var, str(binary))
        assert resolve_tool(PNGQUANT).version == "3.0.3"

    def test_override_times_out(self, tmp_path, no_mise, monkeypatch):
        binary = _make_script(tmp_path / "pngquant", "import time\ntime.sleep(5)")
        monkeypatch.setenv(PNGQUANT.env_var, str(binary))
        monkeypatch.setattr(tools_module, "_VERSION_TIMEOUT", 0.5)
        with pytest.raises(ToolUnavailableError, match="timed out"):
            resolve_tool(PNGQUANT)


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.tools",
        preview=False,
    )
