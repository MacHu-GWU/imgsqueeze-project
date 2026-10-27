# -*- coding: utf-8 -*-

"""
Fixtures shared by several test files.
"""

import shutil
import uuid

import pytest

from imgsqueeze.paths import path_enum
from imgsqueeze.tools import OXIPNG
from imgsqueeze.tools import PNGQUANT
from imgsqueeze.tools import resolve_tool


@pytest.fixture
def img_dir():
    """
    Copy ``tests/img-raw`` into a fresh folder under ``tests/tmp``, and delete
    the copy afterwards. ``tests/img-raw`` itself is never modified.
    """
    path = path_enum.dir_unit_test_tmp / uuid.uuid4().hex
    shutil.copytree(path_enum.dir_unit_test_img_raw, path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def png_tools():
    """
    The real pngquant and oxipng, resolved (and installed if needed) by mise.

    Tests that use it are skipped when mise is not on PATH.
    """
    if shutil.which("mise") is None:
        pytest.skip("mise is not on PATH, so pngquant and oxipng are unavailable")
    return resolve_tool(PNGQUANT), resolve_tool(OXIPNG)
