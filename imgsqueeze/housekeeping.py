# -*- coding: utf-8 -*-

"""
The commands that do not compress: check, pin and doctor.

- ``check`` hashes each image and compares it with its sidecar.
- ``pin`` writes a ``pinned`` sidecar, so an image is kept as it is.
- ``doctor`` finds orphan sidecars, images not done yet, and temporary files
  left behind by an interrupted run.
"""

from __future__ import annotations

import dataclasses
import os
import re

from pathlib import Path

from .core import tool_version
from .discover import expand_inputs
from .discover import IMAGE_SUFFIXES
from .discover import triage
from .sidecar import find_done
from .sidecar import InvalidSidecarError
from .sidecar import sha256_file
from .sidecar import Sidecar
from .sidecar import STATUS_PINNED
from .sidecar import write_sidecar

#: Pin result: a ``pinned`` sidecar was written.
PIN_PINNED = "pinned"
#: Pin result: the sidecar already matches the image, so nothing was written.
PIN_ALREADY_DONE = "already_done"
#: Pin result: the image could not be read, or the sidecar not written.
PIN_ERROR = "error"

_SIDECAR_SUFFIXES = tuple(suffix + ".json" for suffix in IMAGE_SUFFIXES)
# Hidden temporary files from core._replace and sidecar.write_sidecar:
# ".<image name>.<random>.tmp" and ".<image name>.json.<random>.tmp".
_TEMP_PATTERN = re.compile(
    r"^\..+\.(png|jpg|jpeg|webp)(\.json)?\.[^.]+\.tmp$", re.IGNORECASE
)


@dataclasses.dataclass(frozen=True)
class CheckItem:
    """
    Whether one image is already done.
    """

    # fmt: off
    path: Path  #: Real path of the image.
    done: bool  #: ``True`` when its sidecar matches its content.
    sidecar_status: str | None  #: Status in the matching sidecar, when done.
    warning: str | None  #: Why an existing sidecar was ignored.
    # fmt: on


@dataclasses.dataclass(frozen=True)
class PinItem:
    """
    What :func:`~imgsqueeze.housekeeping.pin` did with one image.
    """

    # fmt: off
    path: Path  #: Real path of the image.
    status: str  #: ``pinned``, ``already_done`` or ``error``.
    error: str | None  #: Why it failed, for ``error``.
    # fmt: on


@dataclasses.dataclass(frozen=True)
class DoctorReport:
    """
    Problems found by :func:`~imgsqueeze.housekeeping.doctor`.
    """

    # fmt: off
    orphans: list[Path]  #: Sidecars whose image no longer exists.
    deleted: list[Path]  #: Orphans that were deleted.
    pending: list[Path]  #: Images with no matching sidecar.
    temp_files: list[Path]  #: Temporary files left by an interrupted run.
    # fmt: on

    @property
    def ok(self) -> bool:
        """
        ``True`` when nothing is left to fix.
        """
        return not (
            set(self.orphans) - set(self.deleted) or self.pending or self.temp_files
        )


def check(inputs: list[Path]) -> list[CheckItem]:
    """
    Report which images are already done, without compressing anything.

    :param inputs: files and directories; directories are searched recursively.
    """
    paths = expand_inputs(inputs)
    split = triage(paths)
    items = {
        done.path: CheckItem(
            path=done.path, done=True, sidecar_status=done.sidecar.status, warning=None
        )
        for done in split.done
    }
    for pending in split.pending:
        items[pending.path] = CheckItem(
            path=pending.path, done=False, sidecar_status=None, warning=pending.warning
        )
    return [items[path] for path in paths]


def pin(inputs: list[Path]) -> list[PinItem]:
    """
    Write a ``pinned`` sidecar for each image, so it is never compressed.

    An image whose sidecar already matches is left alone. Any file can be
    pinned, including one imgsqueeze does not support, such as a GIF given
    directly, which keeps ``check`` from reporting it.

    :param inputs: files and directories; directories are searched recursively.
    """
    return [_pin_one(path) for path in expand_inputs(inputs)]


def doctor(inputs: list[Path], delete_orphans: bool = False) -> DoctorReport:
    """
    Find orphan sidecars, pending images, and leftover temporary files.

    Temporary files are only reported: another run may still be using them.

    :param inputs: directories to inspect, searched recursively like
        ``optimize`` (hidden and symlinked directories are skipped).
    :param delete_orphans: delete the orphan sidecars that were found.
    """
    orphans: list[Path] = []
    temp_files: list[Path] = []
    for path in _walk_files(inputs):
        name = path.name
        if _TEMP_PATTERN.match(name):
            temp_files.append(path)
        elif name.lower().endswith(_SIDECAR_SUFFIXES) and not name.startswith("."):
            image = path.with_name(name[: -len(".json")])
            if not image.exists():
                orphans.append(path)
    deleted: list[Path] = []
    if delete_orphans:
        for orphan in orphans:
            orphan.unlink(missing_ok=True)
            deleted.append(orphan)
    pending = [item.path for item in check(inputs) if not item.done]
    return DoctorReport(
        orphans=orphans, deleted=deleted, pending=pending, temp_files=temp_files
    )


def _pin_one(path: Path) -> PinItem:
    try:
        if not path.is_file():
            raise OSError(f"{path} is not a regular file")
        digest = sha256_file(path)
        try:
            if find_done(path, digest) is not None:
                return PinItem(path=path, status=PIN_ALREADY_DONE, error=None)
        except InvalidSidecarError:
            pass  # replaced below
        size = path.stat().st_size
        sidecar = Sidecar(
            final_size=size,
            original_size=size,
            preset=None,
            sha256=digest,
            status=STATUS_PINNED,
            tool=tool_version(),
        )
        write_sidecar(path, sidecar)
    except OSError as e:
        return PinItem(path=path, status=PIN_ERROR, error=str(e))
    return PinItem(path=path, status=PIN_PINNED, error=None)


def _walk_files(inputs: list[Path]) -> list[Path]:
    found: list[Path] = []
    for top in inputs:
        if top.is_symlink() or not top.is_dir():
            continue
        for root, dirnames, filenames in os.walk(top):
            dirnames[:] = sorted(
                name
                for name in dirnames
                if not name.startswith(".")
                and not os.path.islink(os.path.join(root, name))
            )
            for name in sorted(filenames):
                path = os.path.join(root, name)
                if not os.path.islink(path):
                    found.append(Path(os.path.realpath(path)))
    return sorted(set(found))
