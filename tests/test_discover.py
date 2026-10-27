# -*- coding: utf-8 -*-

from imgsqueeze.discover import expand_inputs
from imgsqueeze.discover import triage
from imgsqueeze.discover import Done
from imgsqueeze.discover import Pending
from imgsqueeze.sidecar import Sidecar
from imgsqueeze.sidecar import sha256_file
from imgsqueeze.sidecar import sidecar_path
from imgsqueeze.sidecar import write_sidecar

import os

import imgsqueeze.discover as discover_module


def _real(path):
    return os.path.realpath(path)


def _make(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_expand_file_kept_whatever_its_extension(tmp_path):
    note = _make(tmp_path / "notes.txt")
    assert expand_inputs([note]) == [note.resolve()]


def test_expand_directory_is_recursive_and_case_insensitive(tmp_path):
    a = _make(tmp_path / "a.PNG")
    b = _make(tmp_path / "sub" / "deeper" / "b.Jpeg")
    c = _make(tmp_path / "sub" / "c.webp")
    _make(tmp_path / "sub" / "readme.md")
    found = expand_inputs([tmp_path])
    assert set(found) == {a.resolve(), b.resolve(), c.resolve()}


def test_expand_skips_hidden_subdirectories(tmp_path):
    visible = _make(tmp_path / "cover.png")
    _make(tmp_path / ".git" / "hidden.png")
    _make(tmp_path / "sub" / ".cache" / "hidden.jpg")
    assert expand_inputs([tmp_path]) == [visible.resolve()]


def test_expand_skips_apple_double_files(tmp_path):
    image = _make(tmp_path / "cover.png")
    _make(tmp_path / "._cover.png")
    assert expand_inputs([tmp_path]) == [image.resolve()]


def test_expand_hidden_input_directory_itself_is_searched(tmp_path):
    hidden_root = tmp_path / ".assets"
    image = _make(hidden_root / "cover.png")
    assert expand_inputs([hidden_root]) == [image.resolve()]


def test_expand_keeps_missing_path(tmp_path):
    missing = tmp_path / "gone.png"
    assert expand_inputs([missing]) == [missing.resolve()]


def test_expand_skips_symlinked_file_in_directory(tmp_path):
    real = _make(tmp_path / "cover.png")
    os.symlink(real, tmp_path / "link.png")
    assert expand_inputs([tmp_path]) == [real.resolve()]


def test_expand_skips_symlink_given_directly(tmp_path):
    real = _make(tmp_path / "cover.png")
    link = tmp_path / "link.png"
    os.symlink(real, link)
    assert expand_inputs([link]) == []


def test_expand_skips_symlinked_directory(tmp_path):
    outside = _make(tmp_path / "outside" / "photo.jpg")
    root = tmp_path / "blog"
    image = _make(root / "cover.png")
    os.symlink(outside.parent, root / "linked-dir")
    assert expand_inputs([root]) == [image.resolve()]
    assert expand_inputs([root / "linked-dir"]) == []


def test_expand_dedupes_same_file_given_twice(tmp_path):
    image = _make(tmp_path / "sub" / "cover.png")
    same = tmp_path / "sub" / ".." / "sub" / "cover.png"
    assert expand_inputs([image, same, tmp_path]) == [image.resolve()]


def test_expand_keeps_first_seen_order(tmp_path):
    first = _make(tmp_path / "z.png")
    second = _make(tmp_path / "a.png")
    assert expand_inputs([first, second]) == [first.resolve(), second.resolve()]


def test_triage_new_image_is_pending(tmp_path):
    image = _make(tmp_path / "cover.png")
    result = triage([image.resolve()])
    assert result.pending == [Pending(path=image.resolve(), warning=None)]
    assert result.done == []


def test_triage_image_with_matching_sidecar_is_done(tmp_path):
    image = _make(tmp_path / "cover.png", b"content")
    record = Sidecar(
        final_size=7,
        original_size=9,
        preset="normal",
        sha256=sha256_file(image),
        status="optimized",
        tool="imgsqueeze 0.1.1",
    )
    write_sidecar(image, record)
    result = triage([image.resolve()])
    assert result.pending == []
    assert result.done == [Done(path=image.resolve(), sidecar=record)]


def test_triage_stale_sidecar_is_pending(tmp_path):
    image = _make(tmp_path / "cover.png", b"content")
    write_sidecar(
        image,
        Sidecar(
            final_size=7,
            original_size=9,
            preset="normal",
            sha256="0" * 64,
            status="optimized",
            tool="imgsqueeze 0.1.1",
        ),
    )
    result = triage([image.resolve()])
    assert result.pending == [Pending(path=image.resolve(), warning=None)]
    assert result.done == []


def test_triage_invalid_sidecar_is_pending_with_warning(tmp_path):
    image = _make(tmp_path / "cover.png")
    sidecar_path(image).write_text("not json", encoding="utf-8")
    result = triage([image.resolve()])
    assert len(result.pending) == 1
    assert result.pending[0].path == image.resolve()
    assert "not valid JSON" in result.pending[0].warning
    assert result.done == []


def test_triage_missing_path_is_pending_with_reason(tmp_path):
    missing = (tmp_path / "gone.png").resolve()
    folder = tmp_path.resolve()
    result = triage([missing, folder])
    assert result.pending == [
        Pending(path=missing, warning=f"{missing} does not exist"),
        Pending(path=folder, warning=f"{folder} is not a regular file"),
    ]


def test_triage_unreadable_file_is_pending_with_reason(tmp_path, monkeypatch):
    # the worker reads the file again and reports the real error
    image = _make(tmp_path / "cover.png")

    def fail(path):
        raise PermissionError("denied")

    monkeypatch.setattr(discover_module, "sha256_file", fail)
    result = triage([image.resolve()])
    assert result.pending == [
        Pending(path=image.resolve(), warning="cannot read: denied")
    ]


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.discover",
        preview=False,
    )
