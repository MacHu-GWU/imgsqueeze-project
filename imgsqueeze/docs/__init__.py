# -*- coding: utf-8 -*-

"""
Data passed to the ``.. jinja:: doc_data`` directive in the docs
(see ``jinja_contexts`` in ``docs/source/conf.py``).
"""

import inspect

from .. import api


def _row(name: str) -> dict:
    obj = getattr(api, name)
    return {
        "role": "class" if inspect.isclass(obj) else "func",
        "target": f"{obj.__module__}.{obj.__qualname__}",
        "summary": (obj.__doc__ or "").strip().splitlines()[0],
    }


#: One row per public function and class of ``api.py``, in the order of
#: ``api.py``: the Sphinx role, the full dotted target, and the first line of
#: its docstring. Constants are documented on the API pages instead.
public_api = [
    _row(name)
    for name in vars(api)
    if not name.startswith("_")
    and (inspect.isclass(getattr(api, name)) or inspect.isfunction(getattr(api, name)))
]

doc_data = {
    "public_api": public_api,
}
