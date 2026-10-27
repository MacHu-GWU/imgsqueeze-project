---
description: "How imgsqueeze changes files safely: input expansion and symlink skipping in discover.py, the optimistic compare-and-swap on the content hash in core.py, atomic replacement that keeps permissions, the hidden temp file naming that doctor relies on, and parallelism with a process pool. Read when changing how files are found, read, replaced, or processed in parallel."
---

# File Safety and Concurrency

Writing the image and the sidecar of `06-sidecar.md` must never corrupt either, even with several imgsqueeze runs at once.

---

## 1. Which files are touched

`discover.expand_inputs`:

- A file given directly is kept whatever its extension; a folder is walked recursively for `IMAGE_SUFFIXES` (`.png .jpg .jpeg .webp`, any case).
- Hidden subfolders (`.git`, `.cache`) are not walked; a hidden folder given directly is. `._*` files (AppleDouble metadata macOS writes on exFAT and network disks) are skipped; they are not images.
- **Symlinks are skipped everywhere:** given directly, as files in a folder, and as subfolders. Handling them is not imgsqueeze's job, and `os.replace` on a symlink would turn it into a regular file. Decided by the user.
- Paths are resolved with `os.path.realpath` and de-duplicated in first-seen order, so `a/../a/x.png` and `x.png` given twice are one image.
- Paths that do not exist are kept, so the worker reports them as `error`; `triage` gives them a warning saying why (`does not exist`, `is not a regular file`, or the read error), which `check` shows.

---

## 2. Compare and swap on the content

There are no locks. The image content itself is the version number (`core.process`):

1. Read the file **once**, and hash those bytes: `H0`. Recheck the sidecar against `H0` (it may have changed since triage).
2. Write those exact bytes to `source.<format>` in a private `tempfile.TemporaryDirectory`, and run the engine on that copy. Detection and compression therefore see the content `H0` describes, even if the file changes meanwhile.
3. Right before writing anything (`_unchanged`, and the `stat` at the top of `_replace`), hash the file again. A different hash, or a file that is gone, means another process changed it: discard the result and return `conflict`.
4. `os.replace`, then write the sidecar.

The race window is only between steps 3 and 4. Losing it means one image is processed one more time; `os.replace` is atomic, so no file is ever half-written. `conflict` is not an error; the next run sees the new content.

Rejected: a SQLite lock with expiry (state outside the files, a global database to maintain, and two processes on one image are rare locally), and a lock keyed by the image hash (the thing to protect is the path, and the hash may be stale while waiting).

---

## 3. Atomic replacement (`_replace`)

- Intermediate files live in the system temp folder; only the final result enters the image's folder, keeping the time a temp file sits in a blog repo short.
- The result is copied to a hidden temp file next to the image, because `os.replace` is atomic only within one file system.
- The original's permission bits are copied onto it (`stat.S_IMODE`); mkstemp creates 0o600, so without this a replaced image would lose its permissions.
- It is flushed and `os.fsync`ed before `os.replace` (same in `sidecar.write_sidecar`), so a power loss cannot leave a renamed but truncated file. The folder itself is not fsynced, and on macOS `fsync` does not force the drive cache; good enough for a blog repo under git.
- `finally` removes the temp file whatever happens.

**Temp file names are a contract:** `.<image name>.<random>.tmp` here and `.<image name>.json.<random>.tmp` for sidecars. `housekeeping._TEMP_PATTERN` matches exactly these to report leftovers from a crashed run. Change both together.

---

## 4. Parallelism

`runner.optimize`:

1. Expand and triage in the main process; done images never reach a worker.
2. Resolve pngquant and oxipng once, only if a pending image is a PNG (`03-external-tools.md`).
3. Run `core.process` in a `ProcessPoolExecutor` with `jobs` workers (default `os.cpu_count()`, at most one per image). A single image, or `jobs=1`, runs in the main process: starting a pool has a noticeable cost, since macOS starts workers with spawn.

`Job` and `Result` are frozen dataclasses because they cross the process boundary by pickling; keep them picklable. `process` never raises: expected failures become specific `error` results, and a last-resort `except Exception` around `_process` turns anything else into `error` ("unexpected <type>: ..."), so one bad image cannot break the batch or the `--json` report. Subprocess output is decoded with `errors="replace"` for the same reason.

The tools are resolved only when triage saw a PNG, so a `Job` may have both `png_tools` and `png_tools_error` set to `None`. If such a worker finds a PNG (the file changed after triage), it returns `conflict` with a warning, not `error`, so the run does not exit with 3.

Callers of `optimize` from a script need the `if __name__ == "__main__":` guard: macOS starts workers with spawn, which re-imports the script. The user docs and `pypi-imgsqueeze` say so.
