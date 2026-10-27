---
description: "The three quality presets in imgsqueeze/presets.py, where their numbers came from, why quality is judged by eye instead of by a metric, and the calibration page built by mise run calibrate. Read when changing a preset value, or when a user says images look too compressed or not compressed enough."
---

# Presets and Calibration

Each engine of `02-compression-engines.md` exposes exactly one quality knob. A preset sets all three.

---

## 1. The values

`PRESETS` in `imgsqueeze/presets.py`, default `DEFAULT_PRESET = "normal"`:

| Preset | PNG (pngquant `--quality`) | JPEG quality | WebP quality | For |
| :--- | :--- | :--- | :--- | :--- |
| `light` | 80-95 | 88 | 88 | detailed images, images with text |
| `normal` | 65-80 | 80 | 80 | most AI illustrations |
| `aggressive` | 50-70 | 70 | 70 | decorative headers, backgrounds |

Where they came from:

- JPEG and WebP q80 is the most common web optimization value; JPEG q80 measured SSIM about 0.97.
- pngquant 65-80 is the most common pngquant usage. pngquant uses as few colors as reach the upper bound; when even the lower bound cannot be reached (typical of large smooth gradients) it gives up with exit code 99 and the original is kept. The floor is the safety net against ugly output.
- `light` and `aggressive` are one step either side.
- **Status:** calibrated by eye on 2026-10-27 with the page in section 3, and kept unchanged.

The same numbers are repeated in user-facing places; change them together: `docs/source/03-How-It-Works/index.rst`, `.claude/skills/pypi-imgsqueeze/ref/public-api.md`.

---

## 2. Why by eye

"Visually about the same" is defined as: hard to tell apart from the original side by side at 1:1 size, as judged by the user. Rejected alternatives:

| Approach | Why not |
| :--- | :--- |
| Search the quality per image (binary search to a target score) | 6 to 7 encodes per image, and a scoring library at run time. |
| SSIMULACRA 2 | The Python implementations are immature, and its scores still disagree with the eye. |
| SSIM | Averaging over the image hides local artifacts, and it ignores color. Used only for rough comparisons during design. |

---

## 3. The calibration page

`mise run calibrate` runs `.mise/tasks/calibrate-presets.py`, a development script that is not part of the package. It compresses every image under `--input` (default `tests/img-raw`) with every preset by calling the engines directly, so `min_gain` never hides a result, and writes:

```text
tmp/calibration/                 (git-ignored; --output to change)
├── index.html                   one section per image: the original, then each preset below it
└── images/<path relative to the input>/<file name>/original.<ext>, light.<ext>, normal.<ext>, aggressive.<ext>
```

- The `images/` tree mirrors the input tree, and each image's folder is named with its extension, so `a/cover.png`, `b/cover.png` and `cover.jpg` never collide.
- Images are ordinary files, so they open on their own; the page shows each size (B, or KB and MB with one decimal), its gain, and whether `DEFAULT_MIN_GAIN` would keep it. Hovering a result swaps in the original.
- Only `images/` is deleted on each run, never anything else in `--output`.
- The four samples in `tests/img-raw` are not representative; the design asks for 10 to 20 real images covering photos, text and gradients. Pass `--input` with the user's own folder.
