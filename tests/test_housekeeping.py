# -*- coding: utf-8 -*-

from imgsqueeze.housekeeping import check
from imgsqueeze.housekeeping import doctor
from imgsqueeze.housekeeping import pin
from imgsqueeze.housekeeping import DoctorReport

import os
from pathlib import Path

import imgsqueeze.housekeeping as housekeeping_module
from imgsqueeze.runner import optimize
from imgsqueeze.sidecar import read_sidecar
from imgsqueeze.sidecar import sha256_file
from imgsqueeze.sidecar import sidecar_path

JPEG = "blog-cover.jpg"
WEBP = "investing-in-the-public-benefit.webp"  # already lossy: always no_gain


def _make(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TestCheck:
    def test_done_and_pending_in_input_order(self, img_dir):
        optimize([img_dir / WEBP], jobs=1)
        items = check([img_dir / WEBP, img_dir / JPEG])
        assert [(item.path.name, item.done) for item in items] == [
            (WEBP, True),
            (JPEG, False),
        ]
        assert items[0].sidecar_status == "no_gain"
        assert items[1].sidecar_status is None

    def test_changed_image_is_pending_again(self, img_dir):
        optimize([img_dir / WEBP], jobs=1)
        (img_dir / WEBP).write_bytes(b"replaced")
        (item,) = check([img_dir / WEBP])
        assert item.done is False

    def test_invalid_sidecar_warns(self, img_dir):
        sidecar_path(img_dir / JPEG).write_text("[]", encoding="utf-8")
        (item,) = check([img_dir / JPEG])
        assert item.done is False
        assert "top level must be a JSON object" in item.warning

    def test_checks_nothing_but_hashes(self, img_dir):
        content = (img_dir / JPEG).read_bytes()
        check([img_dir])
        assert (img_dir / JPEG).read_bytes() == content
        assert list(img_dir.glob("*.json")) == []


class TestPin:
    def test_pinned_sidecar_is_written(self, img_dir):
        path = img_dir / JPEG
        (item,) = pin([path])
        assert item.status == "pinned"
        assert item.error is None
        sidecar = read_sidecar(path)
        assert sidecar.status == "pinned"
        assert sidecar.preset is None
        assert sidecar.sha256 == sha256_file(path)
        assert sidecar.original_size == sidecar.final_size == path.stat().st_size

    def test_pinned_image_is_skipped_by_optimize(self, img_dir):
        path = img_dir / JPEG
        content = path.read_bytes()
        pin([path])
        (result,) = optimize([path], jobs=1).results
        assert result.status == "already_done"
        assert result.sidecar_status == "pinned"
        assert path.read_bytes() == content

    def test_matching_sidecar_is_kept(self, img_dir):
        path = img_dir / WEBP
        optimize([path], jobs=1)
        before = read_sidecar(path)
        (item,) = pin([path])
        assert item.status == "already_done"
        assert read_sidecar(path) == before

    def test_stale_or_invalid_sidecar_is_replaced(self, img_dir):
        stale, invalid = img_dir / WEBP, img_dir / JPEG
        optimize([stale], jobs=1)
        stale.write_bytes(b"restored original")
        sidecar_path(invalid).write_text("{", encoding="utf-8")
        assert [item.status for item in pin([stale, invalid])] == ["pinned", "pinned"]
        assert read_sidecar(stale).sha256 == sha256_file(stale)
        assert read_sidecar(invalid).status == "pinned"

    def test_any_file_can_be_pinned(self, tmp_path):
        gif = _make(tmp_path / "anim.gif", b"GIF89a")
        (item,) = pin([gif])
        assert item.status == "pinned"
        assert check([gif])[0].done is True

    def test_missing_file_is_an_error(self, tmp_path):
        (item,) = pin([tmp_path / "gone.png"])
        assert item.status == "error"
        assert "is not a regular file" in item.error

    def test_write_failure_is_an_error(self, img_dir, monkeypatch):
        def fail(image_path, sidecar):
            raise OSError("read-only")

        monkeypatch.setattr(housekeeping_module, "write_sidecar", fail)
        (item,) = pin([img_dir / JPEG])
        assert item.status == "error"
        assert item.error == "read-only"


class TestDoctor:
    def test_clean_folder(self, img_dir):
        optimize([img_dir], jobs=1, min_gain=1.0)  # no_gain everywhere, no PNG tools
        pin([img_dir / "diagram.png", img_dir / "pydantic-logo.png"])
        report = doctor([img_dir])
        assert report == DoctorReport(orphans=[], deleted=[], pending=[], temp_files=[])
        assert report.ok is True

    def test_finds_every_problem(self, tmp_path):
        orphan = _make(tmp_path / "sub" / "old.PNG.json", b"{}")
        temps = [
            _make(tmp_path / ".cover.png.ab12cd34.tmp"),
            _make(tmp_path / "sub" / ".photo.jpg.json.zz99yy88.tmp"),
        ]
        pending = _make(tmp_path / "new.webp")
        _make(tmp_path / "notes.json")  # not a sidecar name
        _make(tmp_path / ".hidden.tmp")  # not ours
        _make(tmp_path / ".git" / "gone.png.json")  # hidden folder is skipped
        report = doctor([tmp_path])
        assert report.orphans == [orphan.resolve()]
        assert report.deleted == []
        assert report.temp_files == sorted(t.resolve() for t in temps)
        assert report.pending == [pending.resolve()]
        assert report.ok is False
        assert orphan.exists()

    def test_delete_orphans(self, tmp_path):
        orphan = _make(tmp_path / "gone.jpeg.json", b"{}")
        image = _make(tmp_path / "kept.png")
        pin([image])
        report = doctor([tmp_path], delete_orphans=True)
        assert report.orphans == report.deleted == [orphan.resolve()]
        assert not orphan.exists()
        assert sidecar_path(image).exists()
        assert report.ok is True

    def test_symlinks_and_files_are_not_walked(self, tmp_path):
        outside = _make(tmp_path / "outside" / "gone.png.json", b"{}")
        root = tmp_path / "blog"
        root.mkdir()
        os.symlink(outside.parent, root / "linked-dir")
        os.symlink(outside, root / "linked.png.json")
        assert doctor([root]).orphans == []
        assert doctor([outside]).orphans == []
        assert doctor([root / "linked-dir"]).orphans == []


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.housekeeping",
        preview=False,
    )
