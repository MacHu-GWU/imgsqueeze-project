.. _python-api:

Python API
==============================================================================

Every command is also a function. Import them from ``imgsqueeze.api``, the
only public module; anything else may change in any release.

.. code-block:: python

    import imgsqueeze.api as imgsqueeze


Compress
------------------------------------------------------------------------------

:func:`~imgsqueeze.runner.optimize` takes the same inputs and options as the
``optimize`` command, and returns a :class:`~imgsqueeze.runner.Report`:

.. code-block:: python

    from pathlib import Path

    import imgsqueeze.api as imgsqueeze

    if __name__ == "__main__":
        report = imgsqueeze.optimize([Path("~/blog/images").expanduser()], preset="normal")
        for result in report.results:
            print(result.status, result.path, result.before, result.after, result.gain)
        print(report.summary)  # {"total": 3, "optimized": 2, ..., "bytes_saved": 390991}

- ``optimize`` compresses several images in worker processes. On macOS and
  Windows a worker starts by importing your script again, so call
  ``optimize`` from a script under ``if __name__ == "__main__":``, as above;
  otherwise it fails with ``RuntimeError``.

- Each :class:`~imgsqueeze.core.Result` has a ``status`` from
  :attr:`~imgsqueeze.core.RESULT_STATUSES`, such as
  :attr:`~imgsqueeze.sidecar.STATUS_OPTIMIZED` or
  :attr:`~imgsqueeze.core.STATUS_ERROR`, and ``error`` and ``warnings``
  explaining it.
- :attr:`Report.missing_tools <imgsqueeze.runner.Report.missing_tools>` is
  ``True`` when some PNG was skipped because pngquant or oxipng is
  unavailable; the CLI exits with 3 in that case.
- Problems with a single image never raise. ``optimize`` raises
  :class:`ValueError` only for a bad argument, such as an unknown preset.


Check, pin, and doctor
------------------------------------------------------------------------------

.. code-block:: python

    items = imgsqueeze.check([Path("images")])
    pending = [item.path for item in items if not item.done]

    imgsqueeze.pin([Path("images/diagram.png")])

    report = imgsqueeze.doctor([Path("images")], delete_orphans=True)
    print(report.orphans, report.pending, report.temp_files, report.ok)


Sidecars and presets
------------------------------------------------------------------------------

.. code-block:: python

    sidecar = imgsqueeze.read_sidecar(Path("images/cover.png"))  # None if missing
    print(sidecar.status, sidecar.original_size, sidecar.final_size)

    preset = imgsqueeze.get_preset("light")
    print(preset.png_quality, preset.jpeg_quality, preset.webp_quality)


All public functions and classes
------------------------------------------------------------------------------

Constants are listed on their module pages, under
:ref:`by Structure <modindex>`.

.. jinja:: doc_data

    .. list-table::
        :header-rows: 1

        * - Name
          - Summary
        {% for row in doc_data.public_api %}
        * - :{{ row.role }}:`~{{ row.target }}`
          - {{ row.summary }}
        {% endfor %}
