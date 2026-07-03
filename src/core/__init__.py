from importlib import import_module
from typing import Any

from .config import config

__all__ = ['config', 'logger']


def __getattr__(name: str) -> Any:
    if name == 'logger':
        return import_module('src.core.logger')
    msg = f'module {__name__!r} has no attribute {name!r}'
    raise AttributeError(msg)
