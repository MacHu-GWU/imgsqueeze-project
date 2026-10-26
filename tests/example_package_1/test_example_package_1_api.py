# -*- coding: utf-8 -*-

from imgsqueeze.example_package_1 import api


def test():
    _ = api
    _ = api.multi_two


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.example_package_1.api",
        preview=False,
    )
