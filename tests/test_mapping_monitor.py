import importlib
import sys
from pathlib import Path
from threading import Event, Lock
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest
from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileDeletedEvent, FileMovedEvent


def import_monitor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
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

    core_module = ModuleType('src.core')
    core_module.config = SimpleNamespace(
        mapping=SimpleNamespace(src_dir=tmp_path / 'src', dst_dir=tmp_path / 'dst'),
        log_dir=tmp_path / 'logs',
    )
    def get_logger(_name: str) -> DummyLogger:
        return DummyLogger()

    core_module.logger = SimpleNamespace(get=get_logger)

    def get_avid(_value: str) -> str:
        return ''

    utils_module = ModuleType('src.utils')
    utils_module.get_avid = get_avid

    def noop() -> None:
        return None

    def noop_rss(*_args, **_kwargs) -> None:
        return None

    archive_module = ModuleType('src.archive')
    archive_module.main = noop
    rss_module = ModuleType('src.rss')
    rss_module.main = noop_rss

    monkeypatch.setitem(sys.modules, 'src.core', core_module)
    monkeypatch.setitem(sys.modules, 'src.utils', utils_module)
    monkeypatch.setitem(sys.modules, 'src.archive', archive_module)
    monkeypatch.setitem(sys.modules, 'src.rss', rss_module)
    monkeypatch.delitem(sys.modules, 'src.mapping', raising=False)
    monkeypatch.delitem(sys.modules, 'src.monitor', raising=False)
    mapping_module = importlib.import_module('src.mapping')
    monkeypatch.setitem(sys.modules, 'src.mapping', mapping_module)
    monitor_module = importlib.import_module('src.monitor')
    monkeypatch.setitem(sys.modules, 'src.monitor', monitor_module)
    return monitor_module


def build_handler(
    monitor_module: ModuleType,
) -> tuple[object, Event, dict[str, float], dict[str, int], set, set]:
    trigger_event = Event()
    last_event_time = {'value': 0.0}
    event_counter = {'value': 0}
    changed_paths = set()
    deleted_paths = set()
    lock = Lock()
    handler = monitor_module.StrmChangeHandler(trigger_event, last_event_time, event_counter, changed_paths, deleted_paths, lock)
    return handler, trigger_event, last_event_time, event_counter, changed_paths, deleted_paths


def test_strm_change_handler_marks_strm_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monitor_module = import_monitor(monkeypatch, tmp_path)
    handler, trigger_event, last_event_time, event_counter, changed_paths, deleted_paths = build_handler(monitor_module)
    with patch('src.monitor.time.monotonic', return_value=123.0):
        handler.on_created(FileCreatedEvent('/tmp/video.strm'))
    assert trigger_event.is_set()
    assert last_event_time['value'] == 123.0
    assert event_counter['value'] == 1
    assert Path('/tmp/video.strm') in changed_paths
    assert not deleted_paths


def test_strm_change_handler_ignores_non_strm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monitor_module = import_monitor(monkeypatch, tmp_path)
    handler, trigger_event, last_event_time, event_counter, changed_paths, deleted_paths = build_handler(monitor_module)
    with patch('src.monitor.time.monotonic', return_value=456.0):
        handler.on_created(FileCreatedEvent('/tmp/video.txt'))
    assert not trigger_event.is_set()
    assert last_event_time['value'] == 0.0
    assert event_counter['value'] == 0
    assert not changed_paths
    assert not deleted_paths


def test_strm_change_handler_ignores_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monitor_module = import_monitor(monkeypatch, tmp_path)
    handler, trigger_event, last_event_time, event_counter, changed_paths, deleted_paths = build_handler(monitor_module)
    with patch('src.monitor.time.monotonic', return_value=789.0):
        handler.on_created(DirCreatedEvent('/tmp/videos'))
    assert not trigger_event.is_set()
    assert last_event_time['value'] == 0.0
    assert event_counter['value'] == 0
    assert not changed_paths
    assert not deleted_paths


def test_strm_change_handler_tracks_move_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monitor_module = import_monitor(monkeypatch, tmp_path)
    handler, trigger_event, last_event_time, event_counter, changed_paths, deleted_paths = build_handler(monitor_module)
    with patch('src.monitor.time.monotonic', return_value=321.0):
        handler.on_moved(FileMovedEvent('/tmp/old.txt', '/tmp/new.strm'))
    assert trigger_event.is_set()
    assert last_event_time['value'] == 321.0
    assert event_counter['value'] == 1
    assert Path('/tmp/new.strm') in changed_paths
    assert Path('/tmp/old.txt') not in deleted_paths


def test_strm_change_handler_tracks_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monitor_module = import_monitor(monkeypatch, tmp_path)
    handler, trigger_event, last_event_time, event_counter, changed_paths, deleted_paths = build_handler(monitor_module)
    with patch('src.monitor.time.monotonic', return_value=654.0):
        handler.on_deleted(FileDeletedEvent('/tmp/old.strm'))
    assert trigger_event.is_set()
    assert last_event_time['value'] == 654.0
    assert event_counter['value'] == 1
    assert Path('/tmp/old.strm') in deleted_paths
    assert Path('/tmp/old.strm') not in changed_paths


def test_should_clear_full_sync_success_no_new_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monitor_module = import_monitor(monkeypatch, tmp_path)
    assert monitor_module.should_clear_full_sync(True, 10, 10)


def test_should_clear_full_sync_success_with_new_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monitor_module = import_monitor(monkeypatch, tmp_path)
    assert not monitor_module.should_clear_full_sync(True, 10, 11)


def test_should_clear_full_sync_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monitor_module = import_monitor(monkeypatch, tmp_path)
    assert not monitor_module.should_clear_full_sync(False, 10, 10)


def test_run_mapping_incremental_returns_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monitor_module = import_monitor(monkeypatch, tmp_path)
    src_dir = tmp_path / 'src'
    dst_dir = tmp_path / 'dst'
    src_dir.mkdir()
    dst_dir.mkdir()
    monkeypatch.setattr(monitor_module.mapping, 'cfg', SimpleNamespace(src_dir=src_dir, dst_dir=dst_dir))

    def boom(*_args, **_kwargs) -> None:
        raise OSError('boom')

    monkeypatch.setattr(monitor_module.mapping, 'update_one', boom)
    monkeypatch.setattr(monitor_module.mapping, 'delete_one', boom)

    failed_changed, failed_deleted = monitor_module.run_mapping_incremental({Path('/tmp/a.strm')}, {Path('/tmp/b.strm')})

    assert failed_changed == {Path('/tmp/a.strm')}
    assert failed_deleted == {Path('/tmp/b.strm')}
