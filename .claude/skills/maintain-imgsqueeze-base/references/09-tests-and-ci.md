---
description: "How imgsqueeze is tested and what CI runs: the read-only sample images and the img_dir fixture, the png_tools fixture that needs mise, fake binaries for failure paths, CI on Ubuntu with Python 3.12 and mise, and the known false positive of the test layout check. Read when writing tests for imgsqueeze, or when CI or a test fails."
---

# Tests and CI

General test conventions (layout, run_cov_test, test writing) are in the `pywf-oss-base` skill and `pywf-oss-write-test`; this file holds what is specific to imgsqueeze.

---

## 1. Sample images

- `tests/img-raw/` holds the user's real, uncompressed samples: `blog-cover.jpg`, `diagram.png`, `pydantic-logo.png`, and `investing-in-the-public-benefit.webp` (already lossy WebP, so it always ends as `no_gain`, which makes it the natural `no_gain` fixture). **Never modify this folder.**
- The `img_dir` fixture in `tests/conftest.py` copies it to `tests/tmp/<uuid hex>/` and deletes the copy afterwards. `tests/tmp/` is git-ignored. Paths come from `path_enum.dir_unit_test_img_raw` and `path_enum.dir_unit_test_tmp` in `imgsqueeze/paths.py`.
- Everything else is generated with Pillow in `tmp_path`: gradients that make pngquant exit 98 (normal preset) or 99 (quality 95-100), two-color images for exact orientation checks, ICC profiles from `ImageCms.createProfile("sRGB")` (portable; no system profile files), animated WebP, corrupt and truncated files. Test images must be self-made or clearly redistributable, to keep the repo MIT-clean.

---

## 2. Real binaries and fakes

- The session-scoped `png_tools` fixture resolves the real pngquant and oxipng (installing them with mise if needed), and **skips** the test when `mise` is not on `PATH`. Without mise, the suite passes but coverage of the PNG success paths drops below 100%.
- Failure paths use fakes instead: small Python scripts with a shebang, written to `tmp_path` (a fake `mise` in `tests/test_tools.py` that logs its calls and installs fake binaries; fake `pngquant` and `oxipng` in `tests/engines/test_engines_png.py`). They need POSIX, so those tests are marked to skip on Windows.
- To force a missing-tool batch, monkeypatch `runner_module.resolve_tool` (or `cli_module.resolve_tool` for `setup`) to raise `ToolUnavailableError`.
- Concurrency is tested by monkeypatching `core_module._compress` to edit or delete the file mid-run, which must give `conflict`.

---

## 3. CI (deviates from the template)

`.github/workflows/main.yml` runs **only `ubuntu-latest` with Python 3.12**, by the user's decision, instead of the template's Ubuntu and Windows times every Python version. Reasons: imgsqueeze targets macOS; Ubuntu is the closest runner where mise can install the binaries; Windows cannot run the fake-binary tests and is not a target.

- `jdx/mise-action@v5` with `install: false`, then `mise install conda:pngquant@3.0.3 oxipng@10.2.1`, so the PNG tests run in CI. These versions must match `PNGQUANT` and `OXIPNG` in `imgsqueeze/tools.py`.
- `MISE_IGNORED_CONFIG_PATHS: ${{ github.workspace }}` makes mise ignore the repo's own `mise.toml`, whose `[env]` reads local secrets and whose `[tools]` are for the dev machine; Python comes from `actions/setup-python`.
- Codecov receives the 3.12 report.

---

## 4. Known false positive

`.claude/skills/pywf-oss-base/scripts/check_test_layout.py` hard-codes `cli.py` as a file without tests, so it reports `tests/test_cli.py` as an orphan. That is expected here, since `cli.py` is tested on purpose (`08-architecture.md`). Do not delete the test; `mise run lint` and `mise run cov` are unaffected.
