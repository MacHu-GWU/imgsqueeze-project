# -*- coding: utf-8 -*-

"""
Locate the external pngquant and oxipng binaries through mise.

imgsqueeze never downloads a binary itself. Each tool is pinned to one
version and located with ``mise which --tool``, which ignores the global and
project mise config. A missing version is installed with ``mise install``,
which changes no config file. mise itself must already be installed.
"""

from __future__ import annotations

import dataclasses
import os
import re
import shutil
import subprocess

from pathlib import Path

#: Where to send users who do not have mise yet.
MISE_INSTALL_URL = "https://mise.jdx.dev/getting-started.html"

_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_WHICH_TIMEOUT = 60
_INSTALL_TIMEOUT = 600
_VERSION_TIMEOUT = 30


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    """
    An external binary pinned to one version.
    """

    # fmt: off
    name: str  #: Binary name, e.g. ``pngquant``.
    mise_tool: str  #: mise tool name, e.g. ``conda:pngquant``.
    version: str  #: Pinned version, also the minimum accepted from ``env_var``.
    env_var: str  #: Environment variable that points to a binary to use instead of mise.
    # fmt: on

    @property
    def mise_spec(self) -> str:
        """
        The ``<mise_tool>@<version>`` string passed to mise.
        """
        return f"{self.mise_tool}@{self.version}"


#: pngquant, installed from conda-forge by mise's conda backend.
PNGQUANT = ToolSpec(
    name="pngquant",
    mise_tool="conda:pngquant",
    version="3.0.3",
    env_var="IMGSQUEEZE_PNGQUANT",
)

#: oxipng, installed from GitHub Releases by mise's aqua backend.
OXIPNG = ToolSpec(
    name="oxipng",
    mise_tool="oxipng",
    version="10.2.1",
    env_var="IMGSQUEEZE_OXIPNG",
)


@dataclasses.dataclass(frozen=True)
class ResolvedTool:
    """
    A binary that was found and answered ``--version``.
    """

    # fmt: off
    name: str  #: Binary name, e.g. ``pngquant``.
    path: Path  #: Absolute path to run.
    version: str  #: Version reported by the binary, e.g. ``3.0.3``.
    # fmt: on


class ToolUnavailableError(Exception):
    """
    Raised when a binary cannot be found, installed, or run.

    The message says what is missing, why, and how to fix it, so it can be
    shown to the user as it is.
    """


def resolve_tool(spec: ToolSpec) -> ResolvedTool:
    """
    Return the binary to run for ``spec``, installing it with mise if needed.

    The environment variable ``spec.env_var`` wins when set, and never falls
    back to mise. Otherwise the pinned version is located with
    ``mise which --tool``, and installed with ``mise install`` first if missing.
    PATH is never searched for the tool itself.

    :param spec: the tool to resolve, such as :data:`PNGQUANT`.
    :raises ToolUnavailableError: if the binary cannot be found, installed, or run.
    """
    override = os.environ.get(spec.env_var)
    if override:
        return _resolve_override(spec, Path(override))
    return _resolve_with_mise(spec)


def _resolve_override(spec: ToolSpec, path: Path) -> ResolvedTool:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ToolUnavailableError(
            _explain(spec, f"{spec.env_var}={path} is not an executable file")
        )
    version = _probe_version(spec, path)
    if _version_tuple(version) < _version_tuple(spec.version):
        raise ToolUnavailableError(
            _explain(
                spec,
                f"{spec.env_var}={path} is version {version}, older than {spec.version}",
            )
        )
    return ResolvedTool(name=spec.name, path=path, version=version)


def _resolve_with_mise(spec: ToolSpec) -> ResolvedTool:
    mise = shutil.which("mise")
    if mise is None:
        raise ToolUnavailableError(
            _explain(spec, f"mise is not on PATH, install it first: {MISE_INSTALL_URL}")
        )
    path = _mise_which(mise, spec)
    if path is None:
        _mise_install(mise, spec)
        path = _mise_which(mise, spec)
    if path is None:
        raise ToolUnavailableError(
            _explain(
                spec,
                f"mise install {spec.mise_spec} succeeded, "
                f"but mise which still cannot find {spec.name}",
            )
        )
    version = _probe_version(spec, path)
    return ResolvedTool(name=spec.name, path=path, version=version)


def _mise_which(mise: str, spec: ToolSpec) -> Path | None:
    args = [mise, "which", spec.name, "--tool", spec.mise_spec]
    result = _run(spec, args, _WHICH_TIMEOUT)
    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        return None
    return Path(output)


def _mise_install(mise: str, spec: ToolSpec) -> None:
    args = [mise, "install", spec.mise_spec]
    result = _run(spec, args, _INSTALL_TIMEOUT)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ToolUnavailableError(
            _explain(spec, f"mise install {spec.mise_spec} failed:\n{detail}")
        )


def _probe_version(spec: ToolSpec, path: Path) -> str:
    result = _run(spec, [str(path), "--version"], _VERSION_TIMEOUT)
    match = _VERSION_PATTERN.search(result.stdout + result.stderr)
    if result.returncode != 0 or match is None:
        raise ToolUnavailableError(
            _explain(spec, f"{path} --version did not report a version")
        )
    return match.group(0)


def _run(
    spec: ToolSpec, args: list[str], timeout: float
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolUnavailableError(
            _explain(spec, f"{' '.join(args)} timed out after {timeout} seconds")
        ) from None
    except OSError as e:
        raise ToolUnavailableError(
            _explain(spec, f"cannot run {' '.join(args)}: {e}")
        ) from e


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _explain(spec: ToolSpec, reason: str) -> str:
    return (
        f"{spec.name} {spec.version} is required to compress PNG files, "
        f"but it is not available.\n"
        f"Reason: {reason}\n"
        f"To fix it, do one of:\n"
        f"  - install it with mise: mise install {spec.mise_spec}\n"
        f"  - if mise is missing, install mise first: {MISE_INSTALL_URL}\n"
        f"  - set {spec.env_var} to an existing {spec.name} binary, "
        f"version {spec.version} or newer"
    )
