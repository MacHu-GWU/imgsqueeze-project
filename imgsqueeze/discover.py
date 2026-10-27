# -*- coding: utf-8 -*-

"""
Expand the inputs into image files, then split them into pending and done.

Files given directly are always included. Directories are searched
recursively for image extensions, skipping hidden subdirectories such as
``.git`` and the ``._*`` metadata files macOS writes on non-Apple disks.
Symlinks are skipped everywhere: imgsqueeze only touches regular
files and directories.
"""

from __future__ import annotations

import dataclasses
import os

from pathlib import Path

from .sidecar import find_done
from .sidecar import InvalidSidecarError
from .sidecar import sha256_file
from .sidecar import Sidecar

#: Extensions picked up inside directories. Compared case-insensitively.
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


@dataclasses.dataclass(frozen=True)
class Pending:
    """
    An image that still needs processing.

    ``warning`` is set when its sidecar exists but cannot be used, or when
    the file cannot be read.
    """

    # fmt: off
    path: Path  #: Real path of the file.
    warning: str | None  #: Why the sidecar or the file cannot be used, or ``None``.
    # fmt: on


@dataclasses.dataclass(frozen=True)
class Done:
    """
    An image whose sidecar matches its current content, so it is already done.
    """

    # fmt: off
    path: Path  #: Real path of the file.
    sidecar: Sidecar  #: The matching sidecar.
    # fmt: on


@dataclasses.dataclass(frozen=True)
class Triage:
    """
    The inputs split into what to process and what is already done.
    """

    pending: list[Pending]
    done: list[Done]


def expand_inputs(inputs: list[Path]) -> list[Path]:
    """
    Return the real paths of all image candidates, in a stable order.

    Each input is a file, which is kept whatever its extension, or a directory,
    which is searched recursively. A symlink, given directly or found inside a
    directory, is skipped. Inputs that do not exist are kept, so the caller can
    report them as errors. Duplicates, such as the same file given twice, are
    removed after resolving each path with ``os.path.realpath``.

    :param inputs: files and directories given by the user.
    """
    candidates: list[Path] = []
    for item in inputs:
        if item.is_symlink():
            continue
        if item.is_dir():
            candidates.extend(_walk_images(item))
        else:
            candidates.append(item)
    return _unique_real_paths(candidates)


def triage(paths: list[Path]) -> Triage:
    """
    Split the paths into pending images and images whose sidecar matches.

    A path that is not a regular file, or cannot be read, is pending, so the
    worker reports the real error; its warning says why. A sidecar that cannot
    be parsed makes the image pending, with a warning saying why.

    :param paths: real paths, as returned by :func:`expand_inputs`.
    """
    pending: list[Pending] = []
    done: list[Done] = []
    for path in paths:
        if not path.is_file():
            reason = "is not a regular file" if path.exists() else "does not exist"
            pending.append(Pending(path=path, warning=f"{path} {reason}"))
            continue
        try:
            digest = sha256_file(path)
            sidecar = find_done(path, digest)
        except InvalidSidecarError as e:
            pending.append(Pending(path=path, warning=str(e)))
            continue
        except OSError as e:
            pending.append(Pending(path=path, warning=f"cannot read: {e}"))
            continue
        if sidecar is None:
            pending.append(Pending(path=path, warning=None))
        else:
            done.append(Done(path=path, sidecar=sidecar))
    return Triage(pending=pending, done=done)


def _walk_images(top: Path) -> list[Path]:
    found: list[Path] = []
    # os.walk does not descend into symlinked directories by default, but it
    # still lists them in dirnames and lists symlinked files in filenames.
    for root, dirnames, filenames in os.walk(top):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".") and not os.path.islink(os.path.join(root, name))
        )
        for name in sorted(filenames):
            path = Path(root) / name
            if name.startswith("._"):
                continue  # AppleDouble metadata, not an image
            if name.lower().endswith(IMAGE_SUFFIXES) and not path.is_symlink():
                found.append(path)
    return found


def _unique_real_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        real = Path(os.path.realpath(path))
        if real not in seen:
            seen.add(real)
            unique.append(real)
    return unique
