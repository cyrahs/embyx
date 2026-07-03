import importlib
import sys
from types import SimpleNamespace

import pytest


def test_clouddrive_subpackage_delegates_to_lazy_client(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        'src.utils',
        'src.utils.clouddrive',
        'src.utils.clouddrive.clouddrive',
    ]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    clouddrive_package = importlib.import_module('src.utils.clouddrive')
    clouddrive_module = importlib.import_module('src.utils.clouddrive.clouddrive')

    sentinel = SimpleNamespace(get_sub_files=object())
    monkeypatch.setattr(clouddrive_module, 'get_client', lambda: sentinel)

    assert clouddrive_package.get_sub_files is sentinel.get_sub_files
