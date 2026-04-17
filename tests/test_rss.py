from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

if TYPE_CHECKING:
    import pytest


class DummyLogger:
    def debug(self, *_args, **_kwargs) -> None:
        return None

    def info(self, *_args, **_kwargs) -> None:
        return None

    def warning(self, *_args, **_kwargs) -> None:
        return None

    def notice(self, *_args, **_kwargs) -> None:
        return None

    def exception(self, *_args, **_kwargs) -> None:
        return None

    def error(self, *_args, **_kwargs) -> None:
        return None


def import_rss(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    core_module = ModuleType('src.core')
    core_module.config = SimpleNamespace(
        clouddrive=SimpleNamespace(task_dir_path='/tasks'),
    )
    core_module.logger = SimpleNamespace(get=lambda _name: DummyLogger())

    utils_module = ModuleType('src.utils')
    utils_module.clouddrive = SimpleNamespace(
        get_sub_files=Mock(),
        list_finished_offline_files_by_path=Mock(),
        clear_finished_offline_files=Mock(),
    )
    utils_module.freshrss = SimpleNamespace(get_items=Mock(), read_items=Mock())
    utils_module.get_avid = Mock(return_value='')
    utils_module.magnet = SimpleNamespace(
        rss=SimpleNamespace(get_magnet=Mock(return_value=None)),
        sukebei=SimpleNamespace(get_magnet=Mock()),
    )
    utils_module.web = SimpleNamespace(javbus=SimpleNamespace(get_magnets=Mock()))

    monkeypatch.setitem(sys.modules, 'src.core', core_module)
    monkeypatch.setitem(sys.modules, 'src.utils', utils_module)
    monkeypatch.delitem(sys.modules, 'src.rss', raising=False)
    rss_module = importlib.import_module('src.rss')
    monkeypatch.setitem(sys.modules, 'src.rss', rss_module)
    return rss_module


def test_refresh_finished_magnets_retries_clouddrive_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    rss_module = import_rss(monkeypatch)

    class DummyRpcError(rss_module.RpcError):
        pass

    refresh_attempts = {'/tasks': 0, '/tasks/task-a': 0}

    def get_sub_files(path: str, *, force_refresh: bool) -> list:
        assert force_refresh is True
        refresh_attempts[path] += 1
        if refresh_attempts[path] == 1:
            message = 'temporary failure'
            raise DummyRpcError(message)
        return []

    list_mock = Mock(
        side_effect=[
            DummyRpcError('temporary failure'),
            SimpleNamespace(offlineFiles=[SimpleNamespace(name='task-a')]),
        ],
    )
    clear_mock = Mock(side_effect=[DummyRpcError('temporary failure'), None])

    monkeypatch.setattr(rss_module, 'clouddrive', SimpleNamespace(
        get_sub_files=Mock(side_effect=get_sub_files),
        list_finished_offline_files_by_path=list_mock,
        clear_finished_offline_files=clear_mock,
    ))
    monkeypatch.setattr(rss_module.refresh_task_dir.retry, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(rss_module.list_finished_targets.retry, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(rss_module.refresh_finished_target.retry, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(rss_module.clear_finished_magnets.retry, 'sleep', lambda _seconds: None)

    rss_module.refresh_finished_magnets()

    assert refresh_attempts == {'/tasks': 2, '/tasks/task-a': 2}
    assert list_mock.call_count == 2
    assert clear_mock.call_count == 2
