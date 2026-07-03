from __future__ import annotations

import asyncio
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


def test_get_magnet_safely_keeps_exception_local(monkeypatch: pytest.MonkeyPatch) -> None:
    rss_module = import_rss(monkeypatch)
    avid_magnet = {}

    async def failing_get_magnet(_avid: str, _items: list[dict], _avid_magnet: dict[str, str]) -> None:
        msg = 'boom'
        raise RuntimeError(msg)

    monkeypatch.setattr(rss_module, 'get_magnet', failing_get_magnet)

    asyncio.run(rss_module.get_magnet_safely('BAD-001', [{'id': '1'}], avid_magnet))

    assert avid_magnet == {}


def test_failed_magnet_task_does_not_cancel_successful_task(monkeypatch: pytest.MonkeyPatch) -> None:
    rss_module = import_rss(monkeypatch)
    monkeypatch.setattr(rss_module, 'get_avid', lambda title: title)
    rss_module.freshrss.get_items.return_value = [
        {'id': '1', 'title': 'GOOD-001'},
        {'id': '2', 'title': 'BAD-001'},
    ]
    add_mock = Mock()
    refresh_mock = Mock()
    monkeypatch.setattr(rss_module, 'add_magnets_and_read', add_mock)
    monkeypatch.setattr(rss_module, 'refresh_finished_magnets', refresh_mock)
    rss_module.FAILED_AVID_COOLDOWN.clear()

    async def fake_get_magnet(avid: str, _items: list[dict], avid_magnet: dict[str, str]) -> None:
        if avid == 'BAD-001':
            msg = 'boom'
            raise RuntimeError(msg)
        avid_magnet[avid] = 'magnet:?xt=urn:btih:abc'

    monkeypatch.setattr(rss_module, 'get_magnet', fake_get_magnet)

    asyncio.run(rss_module.main())

    added_magnets = add_mock.call_args.args[0]
    assert added_magnets == {'GOOD-001': 'magnet:?xt=urn:btih:abc'}
    assert 'BAD-001' in rss_module.FAILED_AVID_COOLDOWN
    refresh_mock.assert_called_once()


def test_main_uses_rank_label(monkeypatch: pytest.MonkeyPatch) -> None:
    rss_module = import_rss(monkeypatch)
    refresh_mock = Mock()
    rss_module.freshrss.get_items.return_value = []
    monkeypatch.setattr(rss_module, 'refresh_finished_magnets', refresh_mock)

    asyncio.run(rss_module.main(rank=True))

    rss_module.freshrss.get_items.assert_called_once_with('Rank')
    refresh_mock.assert_called_once()


def test_add_magnets_and_read_batches_twenty(monkeypatch: pytest.MonkeyPatch) -> None:
    rss_module = import_rss(monkeypatch)
    avid_magnet = {f'ABC-{i:03d}': f'magnet:?xt=urn:btih:{i:03d}' for i in range(21)}
    avid_item = {avid: [{'id': avid}] for avid in avid_magnet}
    batch_sizes = []

    def fake_add_magnets(magnets: list[str]) -> list[dict[str, str]]:
        batch_sizes.append(len(magnets))
        return [{'type': 'success', 'link': magnet} for magnet in magnets]

    monkeypatch.setattr(rss_module, 'add_magnets', fake_add_magnets)
    monkeypatch.setattr(rss_module.time, 'sleep', Mock())

    rss_module.add_magnets_and_read(avid_magnet, avid_item)

    assert batch_sizes == [20, 1]
    assert rss_module.freshrss.read_items.call_count == 2


def test_main_skips_avid_in_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    rss_module = import_rss(monkeypatch)
    monkeypatch.setattr(rss_module, 'get_avid', lambda title: title)
    rss_module.freshrss.get_items.return_value = [{'id': '1', 'title': 'ABC-001'}]
    get_magnet_mock = Mock()
    refresh_mock = Mock()
    monkeypatch.setattr(rss_module, 'get_magnet', get_magnet_mock)
    monkeypatch.setattr(rss_module, 'refresh_finished_magnets', refresh_mock)
    rss_module.FAILED_AVID_COOLDOWN.clear()
    rss_module.FAILED_AVID_COOLDOWN['ABC-001'] = rss_module.time.time()

    asyncio.run(rss_module.main())

    get_magnet_mock.assert_not_called()
    refresh_mock.assert_called_once()


def test_main_retries_expired_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    rss_module = import_rss(monkeypatch)
    monkeypatch.setattr(rss_module, 'get_avid', lambda title: title)
    rss_module.freshrss.get_items.return_value = [{'id': '1', 'title': 'ABC-001'}]
    add_mock = Mock()
    refresh_mock = Mock()
    monkeypatch.setattr(rss_module, 'add_magnets_and_read', add_mock)
    monkeypatch.setattr(rss_module, 'refresh_finished_magnets', refresh_mock)
    rss_module.FAILED_AVID_COOLDOWN.clear()
    rss_module.FAILED_AVID_COOLDOWN['ABC-001'] = rss_module.time.time() - rss_module.COOLDOWN_SECONDS - 1

    async def fake_get_magnet(avid: str, _items: list[dict], avid_magnet: dict[str, str]) -> None:
        avid_magnet[avid] = 'magnet:?xt=urn:btih:abc'

    monkeypatch.setattr(rss_module, 'get_magnet', fake_get_magnet)

    asyncio.run(rss_module.main())

    assert 'ABC-001' not in rss_module.FAILED_AVID_COOLDOWN
    add_mock.assert_called_once()
    refresh_mock.assert_called_once()
