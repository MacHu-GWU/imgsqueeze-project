---
description: "What imgsqueeze is for, who uses it and how, what it deliberately does not do, and research kept for the out-of-scope features. Read before adding a feature or an option, to check that it belongs in imgsqueeze at all."
---

# Scope

---

## 1. The problem

Blog images are mostly AI generated, and come in three formats only: PNG, JPEG and WebP. They are usually far larger than they need to be. Before imgsqueeze, they were compressed by hand on tinypng.com, or by an ad hoc script that ran pngquant three times on each PNG.

imgsqueeze replaces both with one command that an AI agent can run whenever it adds or replaces images in a blog repo: `uvx imgsqueeze optimize <paths> --json`.

---

## 2. Goals

- **TinyPNG-level results.** Lossy compression is fully accepted, as long as the result looks about the same as the original at 1:1 size.
- **Compress each image once.** Running it again on the whole blog is cheap and changes nothing that is already done. Defining "done" is the core of the design.
- **Agent friendly.** Non-interactive, idempotent, safe to rerun, machine-readable output (`--json`), stable exit codes.
- **Runs from anywhere with `uvx`.** The only Python dependency is Pillow. The two PNG binaries, pngquant and oxipng, come from mise.
- **Local Mac use.** It is used on the maintainer's Mac, inside blog repos. Linux works and is what CI runs on; Windows is not a target.

---

## 3. Non-goals

| Not done | Why |
| :--- | :--- |
| Resizing or cropping | Not compression. |
| Format conversion (such as PNG to JPEG) | Changes the file name, so every post that links the image must change too. A different tool's job (section 4). |
| Protecting originals from being overwritten | Users have backups, normally git. A possible design is in section 5. |
| Animated images (APNG, animated WebP) | Not needed. Reported as `unsupported`. |
| Fallbacks for cloud or sandboxed agents without mise | Only local use is targeted. Without mise, PNG files fail with exit code 3. |
| A database or any central state | All state lives in a sidecar file next to each image. |
| A quality score at run time (SSIM, SSIMULACRA 2) | Quality is set by presets calibrated by eye. |

A request for one of these is a new tool or a design change, not a small addition: discuss it with the user first.

---

## 4. Research kept for format conversion

Measured at the same quality (SSIM 0.97) during design, for whoever builds a converter:

- Photographic content stored as PNG is a mismatch: JPEG or WebP is 3 to 10 times smaller.
- Text and diagrams get larger and uglier as JPEG; keep them PNG or lossless WebP.
- Images with transparent pixels cannot become JPEG. Many AI PNGs have an alpha channel that is fully opaque; treat those as photos.
- For photos, WebP is 9% to 43% smaller than JPEG at the same SSIM, and AVIF another 40% to 55% smaller than WebP.
- A workable rule: keep PNG when any pixel is transparent; otherwise try both "convert to JPEG" and "pngquant + oxipng", and keep the smaller.

---

## 5. A design kept for protecting originals

If overwrite protection is ever wanted:

- Before replacing, copy the original to a content-addressed store such as `~/.cache/imgsqueeze/originals/<sha256>.<ext>`, and record `original_sha256` in the sidecar.
- `imgsqueeze restore <path>` finds the backup through the sidecar; `imgsqueeze gc --older-than 30d` cleans the store.
- A two-step preview: `optimize --preview` writes results to a temp folder, and `imgsqueeze apply <preview-id>` replaces the originals after checking their hashes did not change.

Rejected: an interactive "replace? [y/n]" prompt. Agents hang on prompts, so the tool would need two modes, and the mode agents can use would be the unsafe one. If interaction is ever added, it must be an explicit `-i` flag that fails when stdin is not a terminal.
