from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

from src import merge


def _write_strm(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('/media/video.mp4', encoding='utf-8')
    return path


@pytest.fixture
def merge_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr(merge, 'log', Mock())
    monkeypatch.setattr(merge, 'get_avid', lambda name: name.split('-cd', maxsplit=1)[0])
    return merge


def test_get_cds_sorts_complete_cd_sets(merge_module: ModuleType, tmp_path: Path) -> None:
    search_dir = tmp_path / 'search'
    cd2 = _write_strm(search_dir / 'ABC-123-cd2.strm')
    cd1 = _write_strm(search_dir / 'ABC-123-cd1.strm')

    result = merge_module.get_cds(search_dir, '')

    assert result == {'ABC-123': [cd1, cd2]}


def test_get_cds_skips_missing_cd_sets(merge_module: ModuleType, tmp_path: Path) -> None:
    search_dir = tmp_path / 'search'
    _write_strm(search_dir / 'ABC-123-cd1.strm')
    _write_strm(search_dir / 'ABC-123-cd3.strm')

    result = merge_module.get_cds(search_dir, '')

    assert result == {}
    merge_module.log.error.assert_called_once()


def test_get_cds_skips_cd_sets_without_cd1(merge_module: ModuleType, tmp_path: Path) -> None:
    search_dir = tmp_path / 'search'
    _write_strm(search_dir / 'ABC-123-cd2.strm')
    _write_strm(search_dir / 'ABC-123-cd3.strm')

    result = merge_module.get_cds(search_dir, '')

    assert result == {}
    merge_module.log.error.assert_called_once()


def test_get_cds_applies_filter_pattern(merge_module: ModuleType, tmp_path: Path) -> None:
    search_dir = tmp_path / 'search'
    kept = _write_strm(search_dir / 'ABC-123-cd1.strm')
    _write_strm(search_dir / 'XYZ-999-cd1.strm')

    result = merge_module.get_cds(search_dir, '^ABC')

    assert result == {'ABC-123': [kept]}
