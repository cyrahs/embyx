from importlib import import_module
from typing import Any

from .avid import get_avid, get_brand
from .type_check import has_video_suffix, is_video

__all__ = ['cleanup', 'clouddrive', 'freshrss', 'get_avid', 'get_brand', 'has_video_suffix', 'is_video', 'magnet', 'translator', 'web']

_LAZY_EXPORTS = {
    'cleanup': ('src.utils.cleanup', None),
    'clouddrive': ('src.utils.clouddrive.clouddrive', 'clouddrive'),
    'freshrss': ('src.utils.freshrss', None),
    'magnet': ('src.utils.magnet', None),
    'translator': ('src.utils.translator', None),
    'web': ('src.utils.web', None),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        msg = f'module {__name__!r} has no attribute {name!r}'
        raise AttributeError(msg)
    module_name, attr_name = _LAZY_EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name) if attr_name else module
    globals()[name] = value
    return value
