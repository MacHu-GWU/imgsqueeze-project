# -*- coding: utf-8 -*-

from imgsqueeze.example_package_1.example_module_2 import (
    multi_two,
)


def test_multi_two():
    assert multi_two(2, 3) == 6


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.example_package_1.example_module_2",
        preview=False,
    )
