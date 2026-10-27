---
description: "The module map of imgsqueeze and how the pieces from the earlier references fit: the data flow from cli.py to runner.py, core.py and the engines, the per-file statuses, the housekeeping commands, the public API boundary in api.py, and the argparse CLI with its exit codes. Read when adding a module, a command, a status, or a public name."
---

# Architecture

---

## 1. Module map

| Module | Role | Detail in |
| :--- | :--- | :--- |
| `engines/png.py`, `engines/jpeg.py`, `engines/webp.py` | Compress one file into a work folder | `02-compression-engines.md` |
| `tools.py` | Resolve pngquant and oxipng through mise | `03-external-tools.md` |
| `presets.py` | Presets and `DEFAULT_MIN_GAIN` | `04-presets-and-calibration.md` |
| `detect.py` | Format and animation from the content, with Pillow | section 2 |
| `sidecar.py` | Read, validate and write sidecars | `06-sidecar.md` |
| `discover.py` | Expand inputs, triage into pending and done | `06-sidecar.md`, `07-file-safety.md` |
| `core.py` | Process one image end to end, in a worker | `07-file-safety.md` |
| `runner.py` | A whole batch: triage, tools, pool, `Report` | `07-file-safety.md` |
| `housekeeping.py` | `check`, `pin`, `doctor`: the commands that do not compress | section 3 |
| `cli.py` | argparse, output, exit codes | section 5 |
| `api.py` | The public API | section 4 |

Data flow of `imgsqueeze optimize`:

```text
cli._optimize -> runner.optimize -> discover.expand_inputs -> discover.triage
              -> tools.resolve_tool (only if a pending image is a PNG)
              -> core.process per image (pool) -> detect -> engines.* -> min_gain -> CAS -> replace -> sidecar
              -> Report -> text or JSON, exit code
```

---

## 2. Statuses of one image

`core.RESULT_STATUSES`, in summary order:

| Status | Sidecar | Set by |
| :--- | :--- | :--- |
| `optimized` | written | gain >= `min_gain`, file replaced |
| `no_gain` | written | gain < `min_gain`, original kept |
| `already_done` | already there | sidecar matches; `sidecar_status` tells which kind |
| `conflict` | no | the file changed during processing |
| `unsupported` | no | `detect_format` returned `None` (GIF, BMP, MPO, ...; `detect.unsupported_reason` says which), or the image is animated |
| `error` | no | missing file, `<image>.json` that is not a valid sidecar, Pillow cannot open it (`UnidentifiedImageError`), an engine failed, a write failed, any unexpected exception, or the PNG tools are unavailable (`missing_tools=True`) |

Format detection uses the content, never the extension: AI tools often save WebP as `.png`. A mismatch is processed as the real format, keeps its file name, and adds a warning.

---

## 3. Housekeeping commands

`housekeeping.py` holds the logic; `cli.py` only prints it.

- `check`: triage only, never writes. Exit 1 while anything is pending, which is meant for a pre-commit hook.
- `pin`: write a `pinned` sidecar (see `06-sidecar.md`).
- `doctor`: walks folders (hidden and symlinked ones skipped) for orphan sidecars (only files that parse as sidecars) and leftover temp files (`_TEMP_PATTERN`), plus the pending images of `check`. `--delete-orphans` deletes orphans only; temp files are never deleted because a running process may own them.
- `setup`: resolves both tools ahead of time.

---

## 4. Public API

`api.py` re-exports one name per line; anything not there is internal. Exported: the four commands (`optimize`, `check`, `pin`, `doctor`), their result types, every status constant, presets, sidecar helpers, and the tool resolver. Not exported: the engines, `Job`, `PngTools`, `process`, `detect`, `discover`.

Keep three things in sync with `api.py`: `tests/test_api.py` touches every name; `imgsqueeze/docs/__init__.py` builds the docs table of public functions and classes from `api.py` automatically; and the `pypi-imgsqueeze` skill documents every name (regenerate it with `pywf-oss-write-pypi-skill`).

Docstring summaries (first lines) appear in that docs table out of their module, so cross-references there use full paths such as ``:func:`~imgsqueeze.runner.optimize` ``.

---

## 5. The CLI (deviates from the template)

The template uses python-fire and excludes `cli.py` from coverage. imgsqueeze uses **argparse** (no extra dependency) and **measures `cli.py` coverage** like any module, because the CLI is the main interface for agents and its exit codes are a contract. `cli.py` was removed from the `.coveragerc` omit list; `tests/test_cli.py` covers it.

Rules: with `--json`, stdout holds exactly one JSON document and everything else goes to stderr. Every path-taking command accepts `--stdin`. Bad arguments exit 2 (argparse `parser.error`, including `ValueError` from `runner.optimize`).

| Command | 0 | 1 | 2 | 3 |
| :--- | :--- | :--- | :--- | :--- |
| `optimize` | no error | some `error` | bad arguments | some PNG skipped because the tools are unavailable; others processed |
| `check` | all done | some pending | bad arguments | |
| `pin` | success | some failure | bad arguments | |
| `doctor` | nothing left to fix | problems found | bad arguments | |
| `setup` | success | | bad arguments | mise missing or install failed |

`already_done`, `no_gain`, `conflict` and `unsupported` are not failures, so agents can always rerun. Exit 3 wins over exit 1. The missing-tools message is printed once on stderr, not per PNG.
