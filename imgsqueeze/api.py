# -*- coding: utf-8 -*-

"""
Public API. Users import from here::

    from imgsqueeze.api import optimize
    import imgsqueeze.api as imgsqueeze

Anything not listed here is internal and may change in any release.
"""

from .core import Result
from .core import RESULT_STATUSES
from .core import STATUS_ALREADY_DONE
from .core import STATUS_CONFLICT
from .core import STATUS_ERROR
from .core import STATUS_UNSUPPORTED
from .housekeeping import check
from .housekeeping import CheckItem
from .housekeeping import doctor
from .housekeeping import DoctorReport
from .housekeeping import pin
from .housekeeping import PIN_ALREADY_DONE
from .housekeeping import PIN_ERROR
from .housekeeping import PIN_PINNED
from .housekeeping import PinItem
from .presets import DEFAULT_MIN_GAIN
from .presets import DEFAULT_PRESET
from .presets import get_preset
from .presets import Preset
from .presets import PRESET_NAMES
from .presets import PRESETS
from .runner import optimize
from .runner import Report
from .sidecar import InvalidSidecarError
from .sidecar import read_sidecar
from .sidecar import Sidecar
from .sidecar import sidecar_path
from .sidecar import STATUS_NO_GAIN
from .sidecar import STATUS_OPTIMIZED
from .sidecar import STATUS_PINNED
from .tools import OXIPNG
from .tools import PNGQUANT
from .tools import resolve_tool
from .tools import ResolvedTool
from .tools import ToolSpec
from .tools import ToolUnavailableError
