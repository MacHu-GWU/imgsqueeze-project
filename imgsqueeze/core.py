# -*- coding: utf-8 -*-

"""
Process one image: compress it, decide whether to keep the result, and write
the image and its sidecar safely.

:func:`process` runs inside a worker process, so its input and output are
plain picklable dataclasses, and it never raises for a per-file problem: every
outcome is a :class:`Result` with one of the statuses below.

Concurrency control is optimistic: the hash ``H0`` of the content read at the
start must still match the file right before the file or sidecar is written.
Otherwise another process changed the file, and the result is ``conflict``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.metadata
import os
import stat
import tempfile

from pathlib import Path

from PIL import Image

from .detect import detect_format
from .detect import FORMAT_JPEG
from .detect import FORMAT_PNG
from .detect import FORMAT_WEBP
from .detect import is_animated
from .engines.jpeg import compress_jpeg
from .engines.jpeg import JpegEngineError
from .engines.png import compress_png
from .engines.png import PngEngineError
from .engines.webp import compress_webp
from .engines.webp import WebpEngineError
from .presets import DEFAULT_MIN_GAIN
from .presets import Preset
from .sidecar import find_done
from .sidecar import InvalidSidecarError
from .sidecar import sha256_file
from .sidecar import Sidecar
from .sidecar import STATUS_NO_GAIN
from .sidecar import STATUS_OPTIMIZED
from .sidecar import write_sidecar

#: Result status: the sidecar already matches the image, so it was skipped.
STATUS_ALREADY_DONE = "already_done"
#: Result status: another process changed the image while it was processed.
STATUS_CONFLICT = "conflict"
#: Result status: an animated image, or a format other than PNG, JPEG and WebP.
STATUS_UNSUPPORTED = "unsupported"
#: Result status: the image could not be read, decoded, compressed or written.
STATUS_ERROR = "error"

#: Every result status, in the order the summary reports them.
RESULT_STATUSES = (
    STATUS_OPTIMIZED,
    STATUS_NO_GAIN,
    STATUS_ALREADY_DONE,
    STATUS_CONFLICT,
    STATUS_UNSUPPORTED,
    STATUS_ERROR,
)

_SUFFIX_FORMATS = {
    ".png": FORMAT_PNG,
    ".jpg": FORMAT_JPEG,
    ".jpeg": FORMAT_JPEG,
    ".webp": FORMAT_WEBP,
}
_ENGINE_ERRORS = (PngEngineError, JpegEngineError, WebpEngineError)


@dataclasses.dataclass(frozen=True)
class PngTools:
    """
    The resolved pngquant and oxipng binaries, passed to every worker.
    """

    # fmt: off
    pngquant: Path  #: Path of the pngquant binary.
    oxipng: Path  #: Path of the oxipng binary.
    # fmt: on


@dataclasses.dataclass(frozen=True)
class Job:
    """
    Everything a worker needs to process one image.

    Exactly one of ``png_tools`` and ``png_tools_error`` is set: the tools are
    resolved once in the main process, and a PNG fails with the error message
    when they are unavailable.
    """

    # fmt: off
    path: Path  #: Real path of the image.
    preset: Preset  #: Compression strength.
    min_gain: float | None  #: Minimum gain to keep the result, or ``None`` for the per-format default.
    dry_run: bool  #: Compress and report, but write nothing.
    png_tools: PngTools | None  #: The PNG binaries, or ``None`` when unavailable.
    png_tools_error: str | None  #: Why the PNG binaries are unavailable.
    # fmt: on


@dataclasses.dataclass(frozen=True)
class Result:
    """
    The outcome of :func:`process` for one image.
    """

    # fmt: off
    path: Path  #: Real path of the image.
    status: str  #: One of ``RESULT_STATUSES``.
    format: str | None = None  #: ``png``, ``jpeg`` or ``webp``, once detected.
    preset: str | None = None  #: Preset name, when the image was compressed.
    before: int | None = None  #: Size in bytes before processing.
    after: int | None = None  #: Size in bytes on disk after processing (or that would be, with ``dry_run``).
    sidecar_status: str | None = None  #: Status recorded in the matching sidecar, for ``already_done``.
    error: str | None = None  #: Why the status is ``error`` or ``unsupported``.
    missing_tools: bool = False  #: ``True`` when a PNG failed because pngquant or oxipng is unavailable.
    warnings: tuple[str, ...] = ()  #: Problems that did not stop processing.
    # fmt: on

    @property
    def gain(self) -> float | None:
        """
        The fraction of bytes saved, ``1 - after / before``, or ``None``.
        """
        if not self.before or self.after is None:
            return None
        return 1 - self.after / self.before


def tool_version() -> str:
    """
    Return the ``tool`` value written into sidecars, e.g. ``imgsqueeze 0.1.1``.
    """
    return f"imgsqueeze {importlib.metadata.version('imgsqueeze')}"


def process(job: Job) -> Result:
    """
    Process one image and return what happened. Never raises for problems
    with the file itself.

    :param job: the image and settings.
    """
    path = job.path
    warnings: list[str] = []

    def result(status: str, **kwargs) -> Result:
        return Result(path=path, status=status, warnings=tuple(warnings), **kwargs)

    # 1. Read the content once, so everything below works on the same bytes.
    if not path.is_file() or path.is_symlink():
        return result(STATUS_ERROR, error=f"{path} is not a regular file")
    try:
        data = path.read_bytes()
    except OSError as e:
        return result(STATUS_ERROR, error=f"cannot read {path}: {e}")
    h0 = hashlib.sha256(data).hexdigest()
    try:
        done = find_done(path, h0)
    except InvalidSidecarError as e:
        warnings.append(f"ignored the sidecar: {e}")
        done = None
    if done is not None:
        return result(
            STATUS_ALREADY_DONE,
            preset=done.preset,
            before=done.original_size,
            after=done.final_size,
            sidecar_status=done.status,
        )

    # 2. Identify the format from the content, not the extension.
    try:
        fmt = detect_format(data)
        animated = is_animated(data)
    except (OSError, Image.DecompressionBombError) as e:
        return result(STATUS_ERROR, error=f"Pillow cannot open {path}: {e}")
    if fmt is None:
        return result(STATUS_UNSUPPORTED, error="not a PNG, JPEG or WebP image")
    if animated:
        return result(STATUS_UNSUPPORTED, format=fmt, error="animated image")
    if _SUFFIX_FORMATS.get(path.suffix.lower()) != fmt:
        warnings.append(
            f"the content is {fmt.upper()} but the extension is {path.suffix!r}; "
            f"processed as {fmt.upper()} and kept the file name"
        )
    if fmt == FORMAT_PNG and job.png_tools is None:
        return result(
            STATUS_ERROR, format=fmt, error=job.png_tools_error, missing_tools=True
        )

    # 3. Compress in a private temporary directory.
    before = len(data)
    with tempfile.TemporaryDirectory(prefix="imgsqueeze-") as tmp:
        workdir = Path(tmp)
        src = workdir / f"source.{fmt}"
        src.write_bytes(data)
        try:
            out = _compress(fmt, src, workdir, job)
        except _ENGINE_ERRORS as e:
            return result(STATUS_ERROR, format=fmt, error=str(e))
        after = out.stat().st_size
        common = dict(format=fmt, preset=job.preset.name, before=before)

        # 4. Keep the original when the gain is too small.
        min_gain = job.min_gain if job.min_gain is not None else DEFAULT_MIN_GAIN[fmt]
        if 1 - after / before < min_gain:
            if not job.dry_run:
                if not _unchanged(path, h0):
                    return result(STATUS_CONFLICT, **common)
                sidecar = _sidecar(STATUS_NO_GAIN, job, h0, before, before)
                try:
                    write_sidecar(path, sidecar)
                except OSError as e:
                    return result(
                        STATUS_ERROR, error=f"cannot write sidecar: {e}", **common
                    )
            return result(STATUS_NO_GAIN, after=before, **common)

        if job.dry_run:
            return result(STATUS_OPTIMIZED, after=after, **common)

        # 5. to 7. Replace the image atomically, then write the sidecar.
        try:
            replaced = _replace(path, out, h0)
        except OSError as e:
            return result(STATUS_ERROR, error=f"cannot replace {path}: {e}", **common)
        if not replaced:
            return result(STATUS_CONFLICT, **common)
        new_hash = sha256_file(out)
        sidecar = _sidecar(STATUS_OPTIMIZED, job, new_hash, before, after)
        try:
            write_sidecar(path, sidecar)
        except OSError as e:
            return result(STATUS_ERROR, error=f"cannot write sidecar: {e}", **common)
        return result(STATUS_OPTIMIZED, after=after, **common)


def _compress(fmt: str, src: Path, workdir: Path, job: Job) -> Path:
    if fmt == FORMAT_PNG:
        tools = job.png_tools
        return compress_png(src, workdir, job.preset, tools.pngquant, tools.oxipng).path
    if fmt == FORMAT_JPEG:
        return compress_jpeg(src, workdir, job.preset).path
    return compress_webp(src, workdir, job.preset).path


def _unchanged(path: Path, h0: str) -> bool:
    """
    The compare step of compare-and-swap: is the file still the one we read?
    """
    try:
        return sha256_file(path) == h0
    except OSError:
        return False


def _replace(path: Path, new_content: Path, h0: str) -> bool:
    """
    Replace ``path`` with ``new_content``, keeping its permissions, unless it
    changed since it was read. Return ``False`` on such a conflict.

    The new content is first copied into a hidden temporary file next to
    ``path``, because ``os.replace`` is only atomic within one file system.
    """
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(new_content.read_bytes())
        os.chmod(tmp_name, mode)
        if not _unchanged(path, h0):
            return False
        os.replace(tmp_name, path)
        return True
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def _sidecar(status: str, job: Job, sha256: str, before: int, after: int) -> Sidecar:
    return Sidecar(
        final_size=after,
        original_size=before,
        preset=job.preset.name,
        sha256=sha256,
        status=status,
        tool=tool_version(),
    )
