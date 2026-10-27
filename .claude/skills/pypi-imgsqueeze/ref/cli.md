# imgsqueeze CLI (v0.1.1)

Run with `uvx imgsqueeze ...` (no install), or `imgsqueeze` / `.venv/bin/imgsqueeze` when installed. `imgsqueeze --version` prints `imgsqueeze 0.1.1`.

Commands that take paths accept files and folders mixed (folders searched recursively for `.png .jpg .jpeg .webp`, hidden folders and symlinks skipped), plus:

| flag | meaning |
|---|---|
| `--stdin` | also read paths from stdin, one per line (blank lines ignored) |
| `--json` | print one JSON document on stdout; messages go to stderr |

At least one path or `--stdin` is required (else exit 2). Prefer absolute paths.

## optimize

Compress every image not done yet, in place, and write its sidecar.

| flag | type | default | meaning |
|---|---|---|---|
| `paths` | paths | | images and folders |
| `--preset` | `light` \| `normal` \| `aggressive` | `normal` | strength |
| `--min-gain` | float 0..1 | png/jpeg 0.05, webp 0.10 | keep a result only if it saves this fraction; applies to every format when given |
| `--jobs` | int ≥ 1 | CPU count | worker processes |
| `--dry-run` | flag | off | compress and report, write nothing |

```console
$ uvx imgsqueeze optimize /abs/blog/images --json
$ find /abs/blog -name '*.png' | uvx imgsqueeze optimize --stdin --preset light
```

Text output: one line per image (`status  path  before -> after bytes (x% saved)`), warnings indented below, then `N images: ...; saved B bytes`.

JSON output:

```json
{
  "results": [
    {"path": "/abs/blog/images/cover.jpg", "status": "optimized", "format": "jpeg",
     "preset": "normal", "before": 419423, "after": 76176, "gain": 0.8184, "warnings": []}
  ],
  "summary": {"total": 1, "optimized": 1, "no_gain": 0, "already_done": 0,
              "conflict": 0, "unsupported": 0, "error": 0, "bytes_saved": 343247},
  "dry_run": false,
  "tools": {"pngquant": {"path": "...", "version": "3.0.3"},
            "oxipng": {"path": "...", "version": "10.2.1"}}
}
```

- `already_done` results add `sidecar_status` (`optimized` | `no_gain` | `pinned`); `format` is null for them.
- `error` and `unsupported` results add `error`.
- `gain` has 4 decimals, null when unknown.
- `tools` is present only when a PNG was compressed.

Statuses: `optimized`, `no_gain`, `already_done`, `conflict` (run again), `unsupported`, `error`.

## check

Hash each image and compare with its sidecar; never writes.

```console
$ imgsqueeze check /abs/blog/images
done (optimized)    /abs/blog/images/cover.jpg
pending             /abs/blog/images/new.png
2 images: 1 pending
```

JSON: `{"results": [{"path", "done", "sidecar_status", "warning"}], "summary": {"total", "done", "pending"}}`.

## pin

Write a `pinned` sidecar for the current content; `optimize` then skips it. A matching sidecar is left alone. Any file can be pinned.

```console
$ imgsqueeze pin /abs/blog/images/diagram.png
pinned        /abs/blog/images/diagram.png
```

JSON: `{"results": [{"path", "status": "pinned" | "already_done" | "error", "error"}]}`.

## doctor

Report orphan sidecars (image renamed or deleted), pending images, and leftover `.<name>.<random>.tmp` files.

| flag | default | meaning |
|---|---|---|
| `--delete-orphans` | off | delete orphan sidecars (temp files are only reported) |

```console
$ imgsqueeze doctor /abs/blog/images --delete-orphans
deleted orphan  /abs/blog/images/old.png.json
nothing to fix
```

JSON: `{"orphans": [], "deleted": [], "pending": [], "temp_files": [], "ok": true}`.

## setup

Install the pinned pngquant 3.0.3 and oxipng 10.2.1 with mise ahead of time, and print `name version path`. Only `--json` (`{"tools": {...}}`, or `{"error": "..."}` on failure).

## Exit codes

| command | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| optimize | no `error` | some `error` | bad arguments | some PNG skipped: pngquant/oxipng unavailable (others processed; fix-it message on stderr) |
| check | all done | some pending | bad arguments | |
| pin | success | some failure | bad arguments | |
| doctor | nothing to fix | problems found | bad arguments | |
| setup | success | | bad arguments | mise missing or install failed |

`already_done`, `no_gain`, `conflict`, `unsupported` are not failures; rerunning is always safe.

## Environment

| variable | effect |
|---|---|
| `IMGSQUEEZE_PNGQUANT`, `IMGSQUEEZE_OXIPNG` | use this binary instead of mise; must be executable and at least the pinned version |
