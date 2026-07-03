from importlib import import_module
from typing import Any

__all__ = ['CloudDriveClient', 'CloudDriveProxy', 'clouddrive', 'get_client']


def __getattr__(name: str) -> Any:
    module = import_module('src.utils.clouddrive.clouddrive')
    if hasattr(module, name):
        return getattr(module, name)
    return getattr(module.clouddrive, name)
