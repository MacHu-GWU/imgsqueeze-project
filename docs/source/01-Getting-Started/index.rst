.. _getting-started:

Getting Started
==============================================================================

This page takes a folder of blog images from "never compressed" to
"done", and shows what ``imgsqueeze`` leaves behind.


Requirements
------------------------------------------------------------------------------

- **Python 3.11 or newer.**
- **mise.** ``imgsqueeze`` uses `mise <https://mise.jdx.dev/getting-started.html>`_
  to install and find the two PNG tools, pngquant and oxipng, at pinned
  versions. It never downloads a binary itself, and never changes your mise
  configuration. JPEG and WebP only need Pillow, which is installed with
  ``imgsqueeze``, so a batch without PNG files works even without mise.

Install ``imgsqueeze`` from PyPI, or run it with ``uvx`` without installing:

.. code-block:: console

    $ pip install imgsqueeze
    $ uvx imgsqueeze --version

Optionally install the PNG tools ahead of time. Otherwise this happens the
first time a PNG is compressed:

.. code-block:: console

    $ imgsqueeze setup
    pngquant 3.0.3 /Users/me/.local/share/mise/installs/conda-pngquant/3.0.3/.mise-bins/pngquant
    oxipng 10.2.1 /Users/me/.local/share/mise/installs/oxipng/10.2.1/oxipng-10.2.1-aarch64-apple-darwin/oxipng


Compress a folder
------------------------------------------------------------------------------

Give ``optimize`` any mix of files and folders. Folders are searched
recursively for ``.png``, ``.jpg``, ``.jpeg`` and ``.webp`` files, in any
letter case; hidden folders such as ``.git`` and symbolic links are skipped.

.. code-block:: console

    $ imgsqueeze optimize ~/blog/images
    optimized     /Users/me/blog/images/cover.jpg 419423 -> 76176 bytes (81.8% saved)
    optimized     /Users/me/blog/images/diagram.png 55537 -> 7793 bytes (86.0% saved)
    no_gain       /Users/me/blog/images/hero.webp 373482 -> 373482 bytes (0.0% saved)
    3 images: 2 optimized, 1 no_gain; saved 390991 bytes

- ``optimized``: the image was replaced by its compressed version.
- ``no_gain``: compressing did not save enough, so the original was kept.
  Here ``hero.webp`` had already been compressed by some other tool.

Every image now has a sidecar next to it:

.. code-block:: text

    images/
    ├── cover.jpg
    ├── cover.jpg.json
    ├── diagram.png
    ├── diagram.png.json
    ├── hero.webp
    └── hero.webp.json

**Commit the images and their sidecars together.** The sidecars are how
``imgsqueeze`` knows an image is done; :ref:`how-it-works` explains them.


Run it again
------------------------------------------------------------------------------

A second run finds nothing to do, whatever preset you choose:

.. code-block:: console

    $ imgsqueeze optimize ~/blog/images --preset aggressive
    already_done  /Users/me/blog/images/cover.jpg (optimized)
    already_done  /Users/me/blog/images/diagram.png (optimized)
    already_done  /Users/me/blog/images/hero.webp (no_gain)
    3 images: 3 already_done; saved 0 bytes

So you can run ``imgsqueeze optimize`` on the whole blog every time you add a
post: only new or replaced images are compressed.


When a result looks too compressed
------------------------------------------------------------------------------

Restore the original image, for example with ``git checkout``, then either:

- compress it again with a lighter preset: ``imgsqueeze optimize cover.jpg --preset light``.
  The restored file no longer matches its sidecar, so it is processed again,
  from the original; or
- keep it exactly as it is: ``imgsqueeze pin cover.jpg``.

Do not delete a sidecar to force another run: that compresses the
already compressed image a second time.


Next steps
------------------------------------------------------------------------------

- :ref:`command-line`: every command, option, and exit code, and the JSON output.
- :ref:`how-it-works`: sidecars, presets, and what happens to each format.
- :ref:`python-api`: the same features from Python.
