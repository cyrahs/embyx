import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from src.embyx_runtime import fill_actor_api


@pytest.mark.asyncio
async def test_fill_actor_api_delegates_to_runtime_callables(monkeypatch: pytest.MonkeyPatch) -> None:
    scrape = AsyncMock(return_value=['ABC-001', 'ABC-002'])
    get_magnet = AsyncMock(return_value='magnet:?xt=urn:btih:abc')
    monkeypatch.setattr(fill_actor_api.web.javbus, 'scrape', scrape)
    monkeypatch.setattr(fill_actor_api.magnet.sukebei, 'get_magnet', get_magnet)

    assert await fill_actor_api.list_actor_video_ids('actor-1') == ('ABC-001', 'ABC-002')
    assert fill_actor_api.resolve_brand('ABC-001') == 'ABC'
    assert await fill_actor_api.find_sukebei_magnet('ABC-001') == 'magnet:?xt=urn:btih:abc'
    scrape.assert_awaited_once_with('actor-1')
    get_magnet.assert_awaited_once_with('ABC-001')


@pytest.mark.asyncio
async def test_fill_actor_api_forwards_optional_page_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    scrape = AsyncMock(return_value=['ABC-001'])
    progress = AsyncMock()
    monkeypatch.setattr(fill_actor_api.web.javbus, 'scrape', scrape)

    assert await fill_actor_api.list_actor_video_ids('actor-1', progress_callback=progress) == ('ABC-001',)
    scrape.assert_awaited_once_with('actor-1', progress_callback=progress)


@pytest.mark.asyncio
async def test_fill_actor_api_closes_all_owned_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    close_web = AsyncMock()
    close_sukebei = AsyncMock()
    close_logger = Mock()
    monkeypatch.setattr(fill_actor_api.web.javbus, 'aclose', close_web)
    monkeypatch.setattr(fill_actor_api.magnet.sukebei, 'aclose', close_sukebei)
    monkeypatch.setattr(fill_actor_api.magnet, 'close_magnet_logger', close_logger)

    await fill_actor_api.aclose()

    close_web.assert_awaited_once()
    close_sukebei.assert_awaited_once()
    close_logger.assert_called_once()


def test_runtime_import_and_calls_do_not_load_legacy_config(tmp_path: Path) -> None:
    script = """
import asyncio
import importlib.abc
import sys
from unittest.mock import AsyncMock

class ConfigImportBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'src.core.config':
            raise AssertionError('legacy config import attempted')
        return None

sys.meta_path.insert(0, ConfigImportBlocker())
from src.embyx_runtime import fill_actor_api as api

api.web.javbus.get_total_page = AsyncMock(return_value=1)
api.web.javbus.scrape_one_page = AsyncMock(return_value=['ABC-001'])
api.magnet.sukebei.search = AsyncMock(return_value=[{
    'size': '1 GiB',
    'magnet': 'magnet:?xt=urn:btih:abc',
    'type': 'trusted',
    'name': 'ABC-001',
}])

async def main():
    assert await api.list_actor_video_ids('actor-1') == ('ABC-001',)
    assert api.resolve_brand('ABC-001') == 'ABC'
    assert await api.find_sukebei_magnet('ABC-001') == 'magnet:?xt=urn:btih:abc&dn=ABC-001'
    await api.aclose()

asyncio.run(main())
assert 'src.core.config' not in sys.modules
"""
    env = os.environ.copy()
    env['EMBYX_RUNTIME_LOG_DIR'] = str(tmp_path)
    env.pop('EMBYX_USE_REAL_CONFIG', None)
    result = subprocess.run(  # noqa: S603
        [sys.executable, '-c', script],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'magnets.log').read_text(encoding='utf-8') == 'magnet:?xt=urn:btih:abc&dn=ABC-001\n'
