---
description: "How imgsqueeze tracks which images are done: the <image>.json sidecar in imgsqueeze/sidecar.py, its fields, strict validation and byte-stable serialization, the decision flow in discover.triage, orphans, write order and the crash window, and why there is no database. Read when changing the sidecar format or how an image is matched to its record."
---

# Sidecar

The "done" state of `05-already-done.md` has to survive across runs, machines and git clones. It is stored next to each image.

---

## 1. Design

Each processed image gets a file with the same name plus `.json` (`sidecar_path`):

```text
images/cover.png
images/cover.png.json
images/photo.jpeg
images/photo.jpeg.json
```

The sidecar is committed with the image. There is no external database: the state moves, copies and merges with the files themselves.

Rejected: a SQLite database under `~/.cache` (also considered for locking). It would separate the state from the images, so a fresh clone or another machine would recompress everything.

---

## 2. Content

```json
{
  "final_size": 357204,
  "original_size": 1096818,
  "preset": "normal",
  "sha256": "9f2c...e1",
  "status": "optimized",
  "tool": "imgsqueeze 0.1.1"
}
```

| Field | Meaning |
| :--- | :--- |
| `sha256` | Hash of the image content **on disk after processing**: the new file for `optimized`, the untouched original for `no_gain` and `pinned`. The only thing ever compared. |
| `status` | `STATUS_OPTIMIZED`, `STATUS_NO_GAIN` or `STATUS_PINNED`. |
| `preset` | Preset name; `null` exactly when `pinned`. |
| `original_size`, `final_size` | Bytes, for statistics. Equal for `no_gain` and `pinned`. |
| `tool` | `imgsqueeze <version>` from `importlib.metadata` (`core.tool_version`), for debugging. |

- **Byte-stable:** `dumps` uses sorted keys, indent 2, UTF-8, one final newline. The same record always gives the same bytes.
- **Written once:** a sidecar is never rewritten when imgsqueeze is upgraded, so upgrades create no git diff. Adding a field therefore needs a migration plan, not just a new key.
- **Strict validation** (`read_sidecar`, `_from_dict`): exactly these keys; sizes are non-negative ints and not bools; `sha256` is 64 lowercase hex characters; `status` is valid; `preset` is null if and only if pinned. Anything else raises `InvalidSidecarError`.
- **Atomic write** (`write_sidecar`): a temp file `.<sidecar name>.<random>.tmp` in the same folder (`tempfile.mkstemp`), chmod 0o644 (mkstemp creates 0o600), then `os.replace`; the temp file is removed on failure.

---

## 3. Decision flow

`discover.triage` and `core.process` both apply it:

```text
no sidecar                    -> process
sidecar cannot be parsed      -> error, the file is left alone
sidecar.sha256 != sha256(img) -> process (the image was replaced or restored)
sidecar.sha256 == sha256(img) -> done, skip
```

An `<image>.json` that is not a valid sidecar may be the user's own file (an AI tool's prompt, say), so nothing ever overwrites it: `triage` marks the image pending with the parse error as its warning, `core.process` returns `error` ("move or delete it"), and `pin` returns `error`. A real sidecar that got corrupted (a merge conflict) also needs the user to delete it; that is the price of never destroying user data. Rejected: overwriting files whose keys look like a sidecar's, which is a fuzzy rule.

There is no mtime + size shortcut: git checkout changes mtimes, so it is unreliable, and hashing a blog image takes milliseconds.

`pin` (`housekeeping.pin`) writes a `pinned` sidecar, but leaves an already matching sidecar alone so the original sizes of an `optimized` record are not lost. Any file can be pinned, including unsupported formats, which is the way to keep `check` quiet about them.

---

## 4. Write order and the crash window

1. Replace the image atomically (skipped for `no_gain`).
2. Write the sidecar atomically.

A crash between the two leaves a compressed image without a record. The next run processes it once more. With the same or a lighter preset, PNG and JPEG measured a 0% second-pass gain and WebP a gain under its 10% threshold, so it ends as `no_gain` and the image does not change again. A heavier preset compresses it again (light then normal measured 13% to 19% more), which is what the user asked for. Accepted.

---

## 5. Orphans

A sidecar whose image was renamed or deleted is an orphan: a `*.png.json`, `*.jpg.json`, `*.jpeg.json` or `*.webp.json` (any case) without its image. Only a file that parses as a sidecar is an orphan (`housekeeping._is_sidecar`), so `--delete-orphans` never deletes a user's JSON; hidden names count too, while `._*` AppleDouble files do not parse and are ignored. `imgsqueeze doctor` reports them, and deletes them with `--delete-orphans`; a failed delete leaves the orphan reported but not in `deleted`. Renaming an image without its sidecar only costs one more pass, which ends as `no_gain` as in section 4 (with the same or a lighter preset).

Static site generators that copy the image folder copy the sidecars too; users exclude `*.json` in their site config if needed.
