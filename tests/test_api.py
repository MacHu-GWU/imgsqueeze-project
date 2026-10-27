# -*- coding: utf-8 -*-

from imgsqueeze import api


def test():
    _ = api.Result
    _ = api.RESULT_STATUSES
    _ = api.STATUS_ALREADY_DONE
    _ = api.STATUS_CONFLICT
    _ = api.STATUS_ERROR
    _ = api.STATUS_UNSUPPORTED
    _ = api.check
    _ = api.CheckItem
    _ = api.doctor
    _ = api.DoctorReport
    _ = api.pin
    _ = api.PIN_ALREADY_DONE
    _ = api.PIN_ERROR
    _ = api.PIN_PINNED
    _ = api.PinItem
    _ = api.DEFAULT_MIN_GAIN
    _ = api.DEFAULT_PRESET
    _ = api.get_preset
    _ = api.Preset
    _ = api.PRESET_NAMES
    _ = api.PRESETS
    _ = api.optimize
    _ = api.Report
    _ = api.InvalidSidecarError
    _ = api.read_sidecar
    _ = api.Sidecar
    _ = api.sidecar_path
    _ = api.STATUS_NO_GAIN
    _ = api.STATUS_OPTIMIZED
    _ = api.STATUS_PINNED
    _ = api.OXIPNG
    _ = api.PNGQUANT
    _ = api.resolve_tool
    _ = api.ResolvedTool
    _ = api.ToolSpec
    _ = api.ToolUnavailableError


if __name__ == "__main__":
    from imgsqueeze.tests import run_cov_test

    run_cov_test(
        __file__,
        "imgsqueeze.api",
        preview=False,
    )
