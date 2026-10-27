.. _how-it-works:

How It Works
==============================================================================


Every image is compressed once
------------------------------------------------------------------------------

An image is **done** when a sidecar file sits next to it and records the
sha256 of its current content. ``optimize`` writes the sidecar after it
compresses an image, whether the compressed version replaced the original
(``optimized``) or did not save enough and was discarded (``no_gain``).
``pin`` writes one too (``pinned``).

A done image is skipped by every later run, with any preset. ``imgsqueeze``
never compresses the same image twice, because repeated lossy compression
only loses more quality: PNG and JPEG stop shrinking after one pass, and WebP
keeps shrinking a little, and losing a little quality, on every pass.

When the image changes, for example when you restore the original or replace
it with a new picture, its hash no longer matches, and it is compressed again
as a new image.


.. _sidecar:

The sidecar
------------------------------------------------------------------------------

The sidecar of ``cover.png`` is ``cover.png.json``:

.. code-block:: json

    {
      "final_size": 357204,
      "original_size": 1096818,
      "preset": "normal",
      "sha256": "9f2c...e1",
      "status": "optimized",
      "tool": "imgsqueeze 0.1.1"
    }

.. list-table::
    :header-rows: 1

    * - Field
      - Meaning
    * - ``sha256``
      - Hash of the image as it is on disk after processing. The only thing compared.
    * - ``status``
      - ``optimized``, ``no_gain`` or ``pinned``.
    * - ``preset``
      - The preset used; ``null`` for ``pinned``.
    * - ``original_size``, ``final_size``
      - Sizes in bytes before and after.
    * - ``tool``
      - The ``imgsqueeze`` version that wrote it.

The file is written once, with sorted keys, and never rewritten, so upgrading
``imgsqueeze`` does not change it in git. A sidecar that cannot be parsed is
ignored with a warning, and the image is processed as a new one. If a static
site generator copies the image folder to its output, exclude ``*.json``
there if needed.


.. _presets:

Presets and the minimum gain
------------------------------------------------------------------------------

There is one quality setting per format, chosen by the preset:

.. list-table::
    :header-rows: 1

    * - Preset
      - PNG (pngquant ``--quality``)
      - JPEG quality
      - WebP quality
      - For
    * - ``light``
      - 80-95
      - 88
      - 88
      - images with fine detail or text
    * - ``normal`` (default)
      - 65-80
      - 80
      - 80
      - most illustrations and photos
    * - ``aggressive``
      - 50-70
      - 70
      - 70
      - decorative headers and backgrounds

The values were calibrated by eye: at 1:1 size, side by side with the
original, the difference should be hard to see.

A result is kept only when it saves at least the minimum gain, 5% for PNG and
JPEG and 10% for WebP; ``--min-gain`` overrides it for every format.
Otherwise the original stays as it is, because a few percent are not worth a
lossy step and a new binary change in git.


What happens to each format
------------------------------------------------------------------------------

**PNG**

1. If the EXIF orientation is not 1, Pillow rotates the pixels upright,
   because both tools below drop EXIF.
2. `pngquant <https://pngquant.org/>`_ reduces the image to at most 256
   colors (lossy) with ``--skip-if-larger``. It may decline, when the result
   would be larger or the quality floor cannot be reached, as with large
   smooth gradients; the image then continues unquantized.
3. `oxipng <https://github.com/shssoichiro/oxipng>`_ repacks the result
   without changing any pixel (``-o 2 --strip safe``).

**JPEG**: Pillow applies the EXIF orientation, then re-encodes with the
preset quality, ``optimize=True`` and ``progressive=True``.

**WebP**: Pillow applies the EXIF orientation, then re-encodes lossy with
the preset quality and ``method=6``, keeping the alpha channel. Animated
WebP is not supported.

**Metadata**: the ICC color profile is kept; all other metadata (EXIF, XMP,
comments, PNG text) is dropped. One exception: when pngquant quantizes an
image with an ICC profile, it converts the colors to sRGB, so colors outside
sRGB in a wide-gamut image are clipped.


External tools
------------------------------------------------------------------------------

pngquant 3.0.3 and oxipng 10.2.1 are pinned, so every machine produces the
same result. ``imgsqueeze`` finds them with
``mise which <tool> --tool <tool>@<version>``, and installs a missing one with
``mise install``. Neither command changes any mise configuration, and
``imgsqueeze`` never looks for these tools on ``PATH``. To use another binary,
set ``IMGSQUEEZE_PNGQUANT`` or ``IMGSQUEEZE_OXIPNG`` to its path; it must be
at least the pinned version.

pngquant is dual-licensed under GPL-3.0 or a commercial license.
``imgsqueeze`` runs it as a separate program and never bundles it, and the
images it produces are not covered by its license.


Safety
------------------------------------------------------------------------------

- The compressed file replaces the original atomically (``os.replace``),
  keeping its file permissions, so an image is never half-written.
- Before replacing an image or writing a sidecar, ``imgsqueeze`` hashes the
  image again. If another process changed it in the meantime, the result is
  discarded and reported as ``conflict``.
- Symbolic links are skipped, both given directly and found in folders.
- If a run stops between replacing an image and writing its sidecar, the
  next run compresses the image once more; that second pass ends as
  ``no_gain``, so the image does not change again.
