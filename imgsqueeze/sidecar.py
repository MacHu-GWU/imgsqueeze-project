# -*- coding: utf-8 -*-

"""
Read and write the ``<image>.json`` sidecar that records a finished image.

A sidecar holds the sha256 of the image as it was left on disk. The image
counts as already done while that hash still matches the file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import tempfile

from pathlib import Path

#: Sidecar status of an image whose optimized file replaced the original.
STATUS_OPTIMIZED = "optimized"

#: Sidecar status of an image whose gain was below ``min_gain``, so the original was kept.
STATUS_NO_GAIN = "no_gain"

#: Sidecar status of an image the user declared to keep as it is.
STATUS_PINNED = "pinned"

#: Every valid sidecar status.
STATUSES = (STATUS_OPTIMIZED, STATUS_NO_GAIN, STATUS_PINNED)

_FIELD_NAMES = (
    "final_size",
    "original_size",
    "preset",
    "sha256",
    "status",
    "tool",
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_CHUNK_SIZE = 1 << 20


class InvalidSidecarError(Exception):
    """
    Raised when a sidecar file exists but cannot be parsed or fails validation.
    """


@dataclasses.dataclass(frozen=True)
class Sidecar:
    """
    The record of one finished image. Keys are written in sorted order.

    ``preset`` is ``None`` only for a ``pinned`` sidecar.
    """

    # fmt: off
    final_size: int  #: Size in bytes of the image as it is on disk now.
    original_size: int  #: Size in bytes before imgsqueeze touched the image.
    preset: str | None  #: Preset used, one of ``light``, ``normal``, ``aggressive``. ``None`` when pinned.
    sha256: str  #: sha256 of the image content on disk when the sidecar was written, in lowercase hex.
    status: str  #: One of ``STATUSES``.
    tool: str  #: imgsqueeze version that wrote the sidecar, e.g. ``imgsqueeze 0.1.1``.
    # fmt: on


def sidecar_path(image_path: Path) -> Path:
    """
    Return the sidecar path of an image, which is the image name plus ``.json``.

    :param image_path: path of the image file.
    """
    return image_path.with_name(image_path.name + ".json")


def sha256_file(path: Path) -> str:
    """
    Return the sha256 of a file's content as lowercase hex, read in chunks.

    :param path: path of the file to hash.
    """
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dumps(sidecar: Sidecar) -> str:
    """
    Serialize a sidecar to its file content: sorted keys, indent 2, final newline.

    The same sidecar always produces the same bytes.

    :param sidecar: the record to serialize.
    """
    return json.dumps(dataclasses.asdict(sidecar), indent=2, sort_keys=True) + "\n"


def read_sidecar(image_path: Path) -> Sidecar | None:
    """
    Return the sidecar of an image, or ``None`` if the image has none.

    :param image_path: path of the image file.
    :raises InvalidSidecarError: if the sidecar exists but is not a valid sidecar.
    """
    path = sidecar_path(image_path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as e:
        raise InvalidSidecarError(f"{path}: not UTF-8 text: {e}") from e
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise InvalidSidecarError(f"{path}: not valid JSON: {e}") from e
    return _from_dict(path, data)


def find_done(image_path: Path, sha256: str) -> Sidecar | None:
    """
    Return the sidecar if it records the given content hash, else ``None``.

    An image whose sidecar matches is already done and must be skipped.

    :param image_path: path of the image file.
    :param sha256: hash of the image content as it is on disk now.
    :raises InvalidSidecarError: if the sidecar exists but is not a valid sidecar.
    """
    sidecar = read_sidecar(image_path)
    if sidecar is None or sidecar.sha256 != sha256:
        return None
    return sidecar


def write_sidecar(image_path: Path, sidecar: Sidecar) -> None:
    """
    Atomically write the sidecar of an image.

    The content goes to a temporary file in the same folder, which then
    replaces the sidecar. A failed write leaves no temporary file behind.

    :param image_path: path of the image file.
    :param sidecar: the record to write.
    """
    path = sidecar_path(image_path)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(dumps(sidecar))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _from_dict(path: Path, data: object) -> Sidecar:
    if not isinstance(data, dict):
        raise InvalidSidecarError(f"{path}: top level must be a JSON object")
    if sorted(data) != sorted(_FIELD_NAMES):
        raise InvalidSidecarError(
            f"{path}: keys must be exactly {', '.join(_FIELD_NAMES)}, got {', '.join(sorted(data))}"
        )
    for name in ("final_size", "original_size"):
        value = data[name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise InvalidSidecarError(f"{path}: {name} must be a non-negative integer")
    if not isinstance(data["sha256"], str) or not _SHA256_PATTERN.fullmatch(
        data["sha256"]
    ):
        raise InvalidSidecarError(f"{path}: sha256 must be 64 lowercase hex characters")
    if data["status"] not in STATUSES:
        raise InvalidSidecarError(
            f"{path}: status must be one of {', '.join(STATUSES)}"
        )
    if not isinstance(data["tool"], str):
        raise InvalidSidecarError(f"{path}: tool must be a string")
    preset = data["preset"]
    if data["status"] == STATUS_PINNED:
        if preset is not None:
            raise InvalidSidecarError(f"{path}: pinned sidecar must have preset null")
    elif not isinstance(preset, str):
        raise InvalidSidecarError(
            f"{path}: {data['status']} sidecar must have a preset name"
        )
    return Sidecar(
        final_size=data["final_size"],
        original_size=data["original_size"],
        preset=preset,
        sha256=data["sha256"],
        status=data["status"],
        tool=data["tool"],
    )
