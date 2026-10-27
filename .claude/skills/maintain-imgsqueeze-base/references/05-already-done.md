---
description: "The central invariant of imgsqueeze: what counts as an image that cannot be compressed further, why it means one pass instead of compressing until the gain is small, the min_gain threshold, and the recompression rules. Read before changing when an image is processed, skipped, or kept as is."
---

# Already Done

---

## 1. Definition

> An image **cannot be compressed further** (is "done") when it has been through the pipeline of `02-compression-engines.md` once, or the user pinned it, and its content has not changed since.

So **every image is compressed at most once.** A done image is skipped by every later run, with any preset. How "once" is recorded is the sidecar's job; this file is about why "once" is the right definition.

An image becomes done in exactly three ways:

| Outcome | What happens to the image |
| :--- | :--- |
| `optimized` | The compressed version replaced it. |
| `no_gain` | The gain was below `min_gain`; the original was kept. |
| `pinned` | The user ran `imgsqueeze pin`; nothing was compressed. |

`conflict`, `unsupported` and `error` do not make an image done: the next run tries again.

---

## 2. Why one pass, not a loop

The first idea was to recompress until one round saved less than a threshold (say 5%, never below 3% to avoid an endless loop). Measurements (six rounds each, with a "write only if smaller" guard) killed it:

| Format | Round 1 | Rounds 2 to 6 | Fixed point |
| :--- | :--- | :--- | :--- |
| PNG, pngquant `--skip-if-larger` | 54% to 67% smaller | 0.0%: pngquant refuses with exit 98 | yes |
| JPEG, re-encoded at q80 | 54% to 79% smaller | 0.0%, SSIM 0.9999 | yes |
| WebP, re-encoded at q80 | 62% to 64% smaller | 1% to 8% smaller every round, still shrinking at round 6 | **no** |

- PNG and JPEG reach their fixed point in one pass, so a loop does nothing. The old "compress three times" script ran two empty passes. TinyPNG's "always 0% the second time" comes from the same effect.
- WebP has no fixed point: each pass shrinks it a little and lowers quality a little (SSIM from about 0.97 after round 1 to 0.93 to 0.95 after round 6). A loop would keep degrading WebP.

So "done" is defined as "processed once", not as "converged". There is no loop, so there is no endless loop to guard against.

---

## 3. The minimum gain

After the one pass, a result is kept only if `1 - after / before >= min_gain`. Defaults, `DEFAULT_MIN_GAIN` in `imgsqueeze/presets.py`:

| Format | Default | Why |
| :--- | :--- | :--- |
| PNG | 0.05 | A second pass with the same preset measured 0%; any positive threshold is safe. |
| JPEG | 0.05 | Same. |
| WebP | 0.10 | A second pass with the same preset measured 6.7% to 7.7%. If a sidecar is lost and the image is processed again, 10% blocks a second lossy pass. |

`--min-gain` (a fraction, like the JSON `gain`) overrides it for every format.

These second-pass numbers hold for the same or a lighter preset. A heavier preset on an already compressed image is a real new pass: light then normal measured 13% to 19% more savings, so it ends as `optimized`. The sidecar normally prevents that; it only happens when the sidecar is lost.

**Below the threshold, the original is kept, not the slightly smaller result** (the first idea was to keep the result). A few percent are not worth a lossy step, nor a meaningless binary change in git. The image is still marked done (`no_gain`), so it is never tried again. Example: `tests/img-raw/investing-in-the-public-benefit.webp` is already lossy WebP; re-encoding gives -13.9% (light), -5.1% (normal) and +5.9% (aggressive), so every preset ends as `no_gain`.

---

## 4. Recompression rules

**Done is done.** There is no `--force`.

To compress an image again with another preset:

- **Recommended:** restore the original (for example `git checkout`). Its hash no longer matches, so the next run treats it as new and compresses it **from the original**: one lossy step in total.
- **Not recommended:** deleting the done record and running again. That compresses the already compressed image: two lossy steps stacked.

After restoring, doing nothing means the next batch run compresses it again with the default preset. To keep the restored original as it is, pin it.
