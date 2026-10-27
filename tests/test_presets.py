# -*- coding: utf-8 -*-

from imgsqueeze.presets import DEFAULT_MIN_GAIN
from imgsqueeze.presets import DEFAULT_PRESET
from imgsqueeze.presets import PRESET_NAMES
from imgsqueeze.presets import get_preset

import pytest


def test_default_preset_is_a_known_name():
    assert DEFAULT_PRESET in PRESET_NAMES


def test_preset_names_go_from_light_to_aggressive():
    assert PRESET_NAMES == ("light", "normal", "aggressive")


@pytest.mark.parametrize(
    "name, png_quality, jpeg_quality, webp_quality",
    [
        ("light", (80, 95), 88, 88),
        ("normal", (65, 80), 80, 80),
        ("aggressive", (50, 70), 70, 70),
    ],
)
def test_get_preset(name, png_quality, jpeg_quality, webp_quality):
    preset = get_preset(name)
    assert preset.name == name
    assert preset.png_quality == png_quality
    assert preset.jpeg_quality == jpeg_quality
    assert preset.webp_quality == webp_quality


def test_get_preset_unknown_name():
    with pytest.raises(ValueError, match="unknown preset 'huge'"):
        get_preset("huge")


def test_default_min_gain_per_format():
    assert DEFAULT_MIN_GAIN == {"png": 0.05, "jpeg": 0.05, "webp": 0.10}


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.presets",
        preview=False,
    )
