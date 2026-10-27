# -*- coding: utf-8 -*-

from imgsqueeze.sidecar import Sidecar
from imgsqueeze.sidecar import InvalidSidecarError
from imgsqueeze.sidecar import dumps
from imgsqueeze.sidecar import find_done
from imgsqueeze.sidecar import read_sidecar
from imgsqueeze.sidecar import sha256_file
from imgsqueeze.sidecar import sidecar_path
from imgsqueeze.sidecar import write_sidecar
from imgsqueeze.sidecar import STATUS_NO_GAIN
from imgsqueeze.sidecar import STATUS_OPTIMIZED
from imgsqueeze.sidecar import STATUS_PINNED

import hashlib
import json

import pytest

import imgsqueeze.sidecar as sidecar_module

_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _record(**overrides) -> Sidecar:
    values = dict(
        final_size=357204,
        original_size=1096818,
        preset="normal",
        sha256=_HASH_A,
        status=STATUS_OPTIMIZED,
        tool="imgsqueeze 0.1.1",
    )
    values.update(overrides)
    return Sidecar(**values)


def test_sidecar_path(tmp_path):
    image = tmp_path / "cover.png"
    assert sidecar_path(image) == tmp_path / "cover.png.json"


def test_sha256_file(tmp_path):
    image = tmp_path / "photo.jpeg"
    content = b"hello" * 1000
    image.write_bytes(content)
    assert sha256_file(image) == hashlib.sha256(content).hexdigest()


def test_dumps_is_stable():
    text = dumps(_record())
    assert text.endswith("\n")
    assert text == dumps(_record())
    assert list(json.loads(text)) == sorted(json.loads(text))
    assert text.startswith('{\n  "final_size": 357204,\n')


def test_write_then_read_round_trip(tmp_path):
    image = tmp_path / "cover.png"
    record = _record()
    write_sidecar(image, record)
    assert read_sidecar(image) == record
    assert sidecar_path(image).read_text(encoding="utf-8") == dumps(record)


def test_write_overwrites_existing_sidecar(tmp_path):
    image = tmp_path / "cover.png"
    write_sidecar(image, _record(status=STATUS_NO_GAIN))
    write_sidecar(image, _record(status=STATUS_OPTIMIZED))
    assert read_sidecar(image).status == STATUS_OPTIMIZED


def test_write_pinned_sidecar(tmp_path):
    image = tmp_path / "diagram.png"
    record = _record(preset=None, status=STATUS_PINNED)
    write_sidecar(image, record)
    assert read_sidecar(image) == record


def test_write_failure_leaves_no_temporary_file(tmp_path, monkeypatch):
    image = tmp_path / "cover.png"

    def fail_replace(src, dst):
        raise OSError("disk went away")

    monkeypatch.setattr(sidecar_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk went away"):
        write_sidecar(image, _record())
    assert list(tmp_path.iterdir()) == []


def test_read_missing_sidecar_returns_none(tmp_path):
    assert read_sidecar(tmp_path / "cover.png") is None


def test_find_done_matching_hash(tmp_path):
    image = tmp_path / "cover.png"
    record = _record(sha256=_HASH_A)
    write_sidecar(image, record)
    assert find_done(image, _HASH_A) == record


def test_find_done_hash_changed(tmp_path):
    image = tmp_path / "cover.png"
    write_sidecar(image, _record(sha256=_HASH_A))
    assert find_done(image, _HASH_B) is None


def test_find_done_without_sidecar(tmp_path):
    assert find_done(tmp_path / "cover.png", _HASH_A) is None


def _valid_data(**overrides) -> dict:
    data = dict(
        final_size=1,
        original_size=2,
        preset="normal",
        sha256=_HASH_A,
        status=STATUS_OPTIMIZED,
        tool="imgsqueeze 0.1.1",
    )
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    "content",
    [
        "not json at all",
        "[1, 2, 3]",
        json.dumps(_valid_data(final_size="1")),
        json.dumps(_valid_data(final_size=-1)),
        json.dumps(_valid_data(original_size=True)),
        json.dumps(_valid_data(sha256="A" * 64)),
        json.dumps(_valid_data(sha256="abc")),
        json.dumps(_valid_data(status="done")),
        json.dumps(_valid_data(tool=3)),
        json.dumps(_valid_data(preset=None)),
        json.dumps(_valid_data(status=STATUS_PINNED, preset="normal")),
        json.dumps({k: v for k, v in _valid_data().items() if k != "tool"}),
        json.dumps(_valid_data(extra=1)),
    ],
)
def test_read_invalid_sidecar(tmp_path, content):
    image = tmp_path / "cover.png"
    sidecar_path(image).write_text(content, encoding="utf-8")
    with pytest.raises(InvalidSidecarError):
        read_sidecar(image)


def test_read_sidecar_not_utf8(tmp_path):
    image = tmp_path / "cover.png"
    sidecar_path(image).write_bytes(b"\xff\xfe\x00")
    with pytest.raises(InvalidSidecarError, match="not UTF-8"):
        read_sidecar(image)


def test_read_valid_pinned_sidecar_by_hand(tmp_path):
    image = tmp_path / "cover.png"
    data = _valid_data(preset=None, status=STATUS_PINNED)
    sidecar_path(image).write_text(json.dumps(data), encoding="utf-8")
    assert read_sidecar(image) == Sidecar(**data)


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.sidecar",
        preview=False,
    )
