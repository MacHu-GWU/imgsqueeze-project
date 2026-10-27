# -*- coding: utf-8 -*-

from imgsqueeze import api


def test():
    _ = api


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.api",
        preview=False,
    )
