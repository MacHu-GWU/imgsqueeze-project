---
description: "Which program compresses each format and why: pngquant plus oxipng for PNG, Pillow for JPEG and WebP; the exact pipelines in imgsqueeze/engines/, the measured tool behaviors they rely on, how metadata is handled, and the engines that were rejected. Read when changing anything in imgsqueeze/engines/, or when a format is compressed badly."
---

# Compression Engines

---

## 1. Which tool does the compression

| Format | Lossy step | Lossless step | Module |
| :--- | :--- | :--- | :--- |
| PNG | pngquant (palette quantization) | oxipng | `imgsqueeze/engines/png.py` |
| JPEG | Pillow re-encode | Pillow `optimize=True`, same call | `imgsqueeze/engines/jpeg.py` |
| WebP | Pillow re-encode | none | `imgsqueeze/engines/webp.py` |

- **PNG needs two tools** because they solve different problems. pngquant decides what information to keep: it reduces the image to at most 256 colors, which is where most of the gain comes from (54% to 67% smaller on photos). oxipng decides how to pack it: better filters and deflate, without changing any pixel. When pngquant declines, oxipng is the only step that still helps: a gradient illustration went from 36 KB to 22 KB with oxipng alone.
- **pngquant only reads PNG,** so JPEG and WebP never use it.
- **Every engine has the same contract:** `compress_<format>(src, workdir, preset, ...)` writes its result inside `workdir`, never touches `src`, and returns a small frozen dataclass (`PngResult`, `JpegResult`, `WebpResult`) with the output path. Every failure raises the module's own exception (`PngEngineError`, `JpegEngineError`, `WebpEngineError`); decode errors and `Image.DecompressionBombError` (not an `OSError`) are both caught. Whether the result is kept is not the engine's decision.

---

## 2. PNG pipeline (`compress_png`)

0. **Orientation.** `_apply_orientation`: if the EXIF orientation is not 1, Pillow writes an upright copy, keeping the ICC profile; the next steps use it. Both pngquant `--strip` and oxipng `--strip safe` drop the eXIf chunk (measured), so without this step the orientation would be lost.
1. **pngquant** `--quality=<low>-<high> --skip-if-larger --strip --speed 3 --force --output <tmp> -- <src>`.
   - Exit 0: use the quantized file.
   - Exit 98 (`PNGQUANT_EXIT_LARGER`, result would be larger) or 99 (`PNGQUANT_EXIT_QUALITY`, the quality floor cannot be reached): normal, not errors. oxipng then runs on the step 0 image. `PngResult.quantized` is `False`.
   - Anything else is an error. A file that is not a PNG gives exit 25 in 3.0.3.
   - `--force` is required: pngquant skips, instead of overwriting, an output file that already exists.
2. **oxipng** `-o 2 --strip safe --threads 1 --quiet --out <tmp2> <input>`.
   - `--threads 1` because imgsqueeze already runs one worker process per CPU; N processes with N threads each would oversubscribe the machine.
   - Level 2: level 4 was only 0.2% to 2.5% smaller and about 3 times slower.
   - oxipng writes `--out` even when it cannot improve the input, so the output always exists.

**Smooth gradients are pngquant's weak spot:** 256 colors cannot hold them, so it dithers, and dither noise compresses badly. Without `--skip-if-larger`, one gradient grew from 36 KB to 223 KB at SSIM 0.75. Three guards make the worst case "keep the original": the `--quality` floor, `--skip-if-larger`, and the caller's `min_gain`.

---

## 3. JPEG and WebP pipelines

- **JPEG** (`compress_jpeg`): `ImageOps.exif_transpose`, then save with `quality=<preset>`, `optimize=True`, `progressive=True`, the ICC profile, and `comment=b""`. There is no need to estimate the source quality: re-encoding an image that is already below the preset quality does not make it smaller, and `min_gain` keeps the original.
- **WebP** (`compress_webp`): rejects animated files, then `exif_transpose`, then save lossy with `quality=<preset>`, `method=6`, the ICC profile, keeping alpha. A lossless source is re-encoded lossy too; when that does not pay, `min_gain` keeps the original.

**Pillow's metadata behavior, read from its source (Pillow 12):** the JPEG writer copies only the `comment` from the source image (`info.get("comment", im.info.get("comment"))`), hence `comment=b""`; EXIF, XMP and ICC are written only when passed. The WebP writer copies nothing. So passing `icc_profile` explicitly is what keeps the profile.

---

## 4. Metadata rules

- **Keep the ICC profile;** dropping it can shift colors.
- **Apply the EXIF orientation to the pixels, then drop all EXIF.**
- **Drop everything else:** EXIF, XMP, comments, PNG text chunks.
- **Known exception, accepted by the user:** pngquant 3.0.3 converts ICC-tagged pixels to sRGB and tags the output sRGB, with values identical to an lcms conversion. Colors do not shift on sRGB, but wide-gamut colors are clipped (Display P3 `(250, 20, 20)` becomes sRGB `(255, 0, 0)`). Blog images target the web, so this is fine. When pngquant declines, oxipng keeps the ICC profile unchanged (`--strip safe` keeps cICP, iCCP, sRGB, pHYs). Keeping wide gamut would need stripping the ICC before pngquant and writing it back after; the user declined that.

---

## 5. Rejected engines

| Candidate | Why not |
| :--- | :--- |
| Pillow's built-in PNG quantizer (FASTOCTREE) | Pillow wheels lack libimagequant; the built-in quantizer is visibly worse (astronaut SSIM 0.877 against pngquant's 0.944) and bands flat illustrations. |
| `imagequant` Python binding | Loads GPL libimagequant into the MIT imgsqueeze process. |
| `pyoxipng` binding | Bound oxipng 9.1.1 while 10.2.1 was out; with pngquant already a binary, both binaries keep the toolchain uniform. |
| cwebp | Pillow wheels ship the same libwebp. |
| mozjpeg | Only 0.9% to 3.5% smaller than Pillow's `optimize=True, progressive=True`, and not installable through mise or conda-forge on macOS arm64. |
| jpegoptim | Not on mise or conda-forge for macOS arm64, Homebrew only. |
