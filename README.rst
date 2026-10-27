
.. image:: https://readthedocs.org/projects/imgsqueeze/badge/?version=latest
    :target: https://imgsqueeze.readthedocs.io/en/latest/
    :alt: Documentation Status

.. image:: https://github.com/MacHu-GWU/imgsqueeze-project/actions/workflows/main.yml/badge.svg
    :target: https://github.com/MacHu-GWU/imgsqueeze-project/actions?query=workflow:CI

.. image:: https://codecov.io/gh/MacHu-GWU/imgsqueeze-project/branch/main/graph/badge.svg
    :target: https://codecov.io/gh/MacHu-GWU/imgsqueeze-project

.. image:: https://img.shields.io/pypi/v/imgsqueeze.svg
    :target: https://pypi.python.org/pypi/imgsqueeze

.. image:: https://img.shields.io/pypi/l/imgsqueeze.svg
    :target: https://pypi.python.org/pypi/imgsqueeze

.. image:: https://img.shields.io/pypi/pyversions/imgsqueeze.svg
    :target: https://pypi.python.org/pypi/imgsqueeze

.. image:: https://img.shields.io/badge/✍️_Release_History!--None.svg?style=social&logo=github
    :target: https://github.com/MacHu-GWU/imgsqueeze-project/blob/main/release-history.rst

.. image:: https://img.shields.io/badge/⭐_Star_me_on_GitHub!--None.svg?style=social&logo=github
    :target: https://github.com/MacHu-GWU/imgsqueeze-project

------

.. image:: https://img.shields.io/badge/Link-API-blue.svg
    :target: https://imgsqueeze.readthedocs.io/en/latest/py-modindex.html

.. image:: https://img.shields.io/badge/Link-Install-blue.svg
    :target: `install`_

.. image:: https://img.shields.io/badge/Link-GitHub-blue.svg
    :target: https://github.com/MacHu-GWU/imgsqueeze-project

.. image:: https://img.shields.io/badge/Link-Submit_Issue-blue.svg
    :target: https://github.com/MacHu-GWU/imgsqueeze-project/issues

.. image:: https://img.shields.io/badge/Link-Request_Feature-blue.svg
    :target: https://github.com/MacHu-GWU/imgsqueeze-project/issues

.. image:: https://img.shields.io/badge/Link-Download-blue.svg
    :target: https://pypi.org/pypi/imgsqueeze#files


Welcome to ``imgsqueeze`` Documentation
==============================================================================
.. image:: https://imgsqueeze.readthedocs.io/en/latest/_static/imgsqueeze-logo.png
    :target: https://imgsqueeze.readthedocs.io/en/latest/

``imgsqueeze`` compresses the PNG, JPEG and WebP images of a blog **once**, and
remembers that they are done.

- **Visually lossless presets.** PNG goes through `pngquant <https://pngquant.org/>`_
  and `oxipng <https://github.com/shssoichiro/oxipng>`_; JPEG and WebP are
  re-encoded with `Pillow <https://python-pillow.org/>`_. A result is kept
  only when it saves enough bytes; otherwise the original stays untouched.
- **Done is done.** Each image gets a small ``<image>.json`` sidecar that
  records the hash of its final content. Running again skips it, whatever
  the preset, so no image is ever compressed twice.
- **Safe to run anywhere, any time.** Files are replaced atomically, and an
  image changed by another process while it was compressed is left alone.
- **Made for agents.** ``--json`` output, stable exit codes, and a ``check``
  command for pre-commit hooks.

.. code-block:: console

    $ imgsqueeze optimize ~/blog/images
    optimized     /Users/me/blog/images/cover.jpg 419423 -> 76176 bytes (81.8% saved)
    optimized     /Users/me/blog/images/diagram.png 55537 -> 7793 bytes (86.0% saved)
    no_gain       /Users/me/blog/images/hero.webp 373482 -> 373482 bytes (0.0% saved)
    3 images: 2 optimized, 1 no_gain; saved 390991 bytes

Commit the images together with their ``.json`` sidecars. Read the full
documentation at https://imgsqueeze.readthedocs.io/.


.. _install:

Install
------------------------------------------------------------------------------
``imgsqueeze`` needs Python 3.11+ and `mise <https://mise.jdx.dev/getting-started.html>`_.
mise installs the pinned pngquant and oxipng the first time a PNG is
compressed; JPEG and WebP need nothing else. Run it without installing:

.. code-block:: console

    $ uvx imgsqueeze optimize ~/blog/images

Or install it from PyPI:

.. code-block:: console

    $ pip install imgsqueeze

To install pngquant and oxipng ahead of time:

.. code-block:: console

    $ imgsqueeze setup


License
------------------------------------------------------------------------------
``imgsqueeze`` is MIT licensed. It runs pngquant, by Kornel Lesiński and
contributors, as a separate program and never bundles it; pngquant is
dual-licensed under `GPL-3.0 or a commercial license <https://pngquant.org/>`_,
and the images it produces are not covered by its license.
