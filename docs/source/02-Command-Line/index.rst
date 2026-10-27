.. _command-line:

Command Line
==============================================================================

``imgsqueeze`` has five commands. Every command that takes paths accepts any
mix of files and folders, reads more paths from stdin (one per line) with
``--stdin``, and prints a JSON document on stdout with ``--json``. Relative
paths are resolved against the current directory.

.. code-block:: console

    $ imgsqueeze optimize ~/blog/images ~/blog/posts/2026/cover.png
    $ find ~/blog -name '*.png' -newer last-run | imgsqueeze optimize --stdin
    $ imgsqueeze check ~/blog/images
    $ imgsqueeze pin ~/blog/images/diagram.png
    $ imgsqueeze doctor ~/blog/images --delete-orphans
    $ imgsqueeze setup


.. _cli-optimize:

optimize
------------------------------------------------------------------------------

Compress every image that is not done yet, and write its sidecar.

.. list-table::
    :header-rows: 1

    * - Option
      - Default
      - Meaning
    * - ``--preset``
      - ``normal``
      - ``light``, ``normal`` or ``aggressive``; see :ref:`presets`.
    * - ``--min-gain F``
      - 0.05 for PNG and JPEG, 0.10 for WebP
      - Keep a result only if it saves at least this fraction of the bytes.
        ``0.05`` means 5%. Applies to every format when given.
    * - ``--jobs N``
      - number of CPUs
      - Worker processes. A single image is processed without a pool.
    * - ``--dry-run``
      - off
      - Compress and report, but write no image and no sidecar.
    * - ``--stdin``
      - off
      - Also read paths from stdin, one per line.
    * - ``--json``
      - off
      - Print a JSON report instead of text.

Each image ends in one of these states:

.. list-table::
    :header-rows: 1

    * - Status
      - Meaning
      - Sidecar written
    * - ``optimized``
      - Compressed, and the image was replaced.
      - yes
    * - ``no_gain``
      - The gain was below ``--min-gain``, so the original was kept.
      - yes
    * - ``already_done``
      - The sidecar matches the image, so it was skipped (this includes pinned images).
      - already there
    * - ``conflict``
      - Another process changed the image while it was compressed. Run again.
      - no
    * - ``unsupported``
      - An animated image, or a format other than PNG, JPEG and WebP.
      - no
    * - ``error``
      - The file is missing, cannot be decoded, a tool failed, or pngquant or oxipng is unavailable.
      - no

The format comes from the file content, not its name. A WebP image saved as
``cover.png`` is compressed as WebP, keeps its name, and gets a warning.


JSON output
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

With ``--json``, stdout carries exactly one JSON document, and messages go to
stderr:

.. code-block:: json

    {
      "results": [
        {
          "path": "/Users/me/blog/images/cover.jpg",
          "status": "optimized",
          "format": "jpeg",
          "preset": "normal",
          "before": 419423,
          "after": 76176,
          "gain": 0.8184,
          "warnings": []
        }
      ],
      "summary": {
        "total": 1,
        "optimized": 1,
        "no_gain": 0,
        "already_done": 0,
        "conflict": 0,
        "unsupported": 0,
        "error": 0,
        "bytes_saved": 343247
      },
      "dry_run": false
    }

- ``already_done`` results also have ``sidecar_status``: ``optimized``,
  ``no_gain`` or ``pinned``.
- ``error`` and ``unsupported`` results also have ``error``, the reason.
- ``tools`` lists the path and version of pngquant and oxipng. It is present
  only when a PNG was compressed.


check
------------------------------------------------------------------------------

Hash each image and compare it with its sidecar, without compressing.
It exits with 1 while some image is not done, which makes it a pre-commit
hook that blocks images nobody has compressed yet:

.. code-block:: console

    $ imgsqueeze check ~/blog/images
    done (optimized)    /Users/me/blog/images/cover.jpg
    pending             /Users/me/blog/images/new-post.png
    2 images: 1 pending


pin
------------------------------------------------------------------------------

Write a ``pinned`` sidecar for the current content of each image, so
``optimize`` skips it from now on. Use it for an image you want to keep
exactly as it is. Any file can be pinned, including a format
``imgsqueeze`` does not support, which also keeps ``check`` quiet about it.
An image whose sidecar already matches is left alone.


doctor
------------------------------------------------------------------------------

Find problems in a folder:

- **orphan sidecars**, whose image was renamed or deleted;
- **pending images**, as in ``check``;
- **temporary files** left by an interrupted run, named like
  ``.cover.png.k3j9x2a1.tmp``.

``--delete-orphans`` deletes the orphan sidecars. Temporary files are only
reported, because another run may still be using them. When you rename an
image, rename its sidecar too; otherwise the image is compressed again as a
new one, which normally ends as ``no_gain``.


setup
------------------------------------------------------------------------------

Install the pinned pngquant and oxipng with mise, and print where they are.
``optimize`` does the same on demand, so this is only for preparing a
machine ahead of time.


.. _exit-codes:

Exit codes
------------------------------------------------------------------------------

.. list-table::
    :header-rows: 1

    * - Command
      - 0
      - 1
      - 2
      - 3
    * - ``optimize``
      - no error
      - at least one ``error``
      - bad arguments
      - some PNG was not processed because pngquant or oxipng is unavailable
    * - ``check``
      - every image is done
      - some image is not done
      - bad arguments
      -
    * - ``pin``
      - success
      - at least one failure
      - bad arguments
      -
    * - ``doctor``
      - nothing left to fix
      - problems found
      - bad arguments
      -
    * - ``setup``
      - success
      -
      - bad arguments
      - mise is missing, or the install failed

``already_done``, ``no_gain``, ``conflict`` and ``unsupported`` are not
failures: running ``optimize`` again is always safe. With exit code 3, the
other images in the batch were still processed; the message on stderr says
how to install the missing tool.
