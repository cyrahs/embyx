import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def import_mapping(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
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

    monkeypatch.setitem(sys.modules, 'src.core', core_module)
    monkeypatch.setitem(sys.modules, 'src.utils', utils_module)
    monkeypatch.delitem(sys.modules, 'src.mapping', raising=False)
    module = importlib.import_module('src.mapping')
    monkeypatch.setitem(sys.modules, 'src.mapping', module)
    return module


def test_map_strm_path_builds_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mapping = import_mapping(monkeypatch, tmp_path)
    src_dir = tmp_path / 'src'
    dst_dir = tmp_path / 'dst'
    src_dir.mkdir()
    dst_dir.mkdir()
    src_path = src_dir / 'a' / 'ABC-123.strm'
    monkeypatch.setattr(mapping, 'get_avid', lambda _: 'ABC-123')

    dst_path = mapping.map_strm_path(src_path, src_dir, dst_dir)

    assert dst_path == dst_dir / 'a' / 'ABC-123' / 'ABC-123.strm'


def test_update_one_copies_and_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mapping = import_mapping(monkeypatch, tmp_path)
    src_dir = tmp_path / 'src'
    dst_dir = tmp_path / 'dst'
    src_path = src_dir / 'a' / 'ABC-123.strm'
    src_path.parent.mkdir(parents=True)
    dst_dir.mkdir()
    src_path.write_text('data', encoding='utf-8')
    monkeypatch.setattr(mapping, 'get_avid', lambda _: 'ABC-123')
    mapping.reset_counter()

    mapping.update_one(src_path, src_dir, dst_dir)

    dst_path = dst_dir / 'a' / 'ABC-123' / 'ABC-123.strm'
    assert dst_path.read_text(encoding='utf-8') == 'data'
    assert mapping.counter.files_updated == 1

    mapping.update_one(src_path, src_dir, dst_dir)

    assert mapping.counter.files_skipped == 1


def test_delete_one_removes_file_and_empty_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mapping = import_mapping(monkeypatch, tmp_path)
    src_dir = tmp_path / 'src'
    dst_dir = tmp_path / 'dst'
    src_path = src_dir / 'a' / 'ABC-123.strm'
    dst_path = dst_dir / 'a' / 'ABC-123' / 'ABC-123.strm'
    dst_path.parent.mkdir(parents=True)
    dst_path.write_text('data', encoding='utf-8')
    monkeypatch.setattr(mapping, 'get_avid', lambda _: 'ABC-123')
    mapping.reset_counter()

    mapping.delete_one(src_path, src_dir, dst_dir)

    assert not dst_path.exists()
    assert not (dst_dir / 'a' / 'ABC-123').exists()
    assert not (dst_dir / 'a').exists()
    assert mapping.counter.files_deleted == 1
