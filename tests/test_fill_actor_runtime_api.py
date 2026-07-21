import asyncio
import importlib
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from src.embyx_monitor_runtime import fill_actor_api
from src.utils.clouddrive import clouddrive_pb2


def test_legacy_runtime_import_path_is_preserved() -> None:
    legacy_api = importlib.import_module('src.embyx_runtime.fill_actor_api')

    assert legacy_api is fill_actor_api


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
    close_cloud = Mock()
    monkeypatch.setattr(fill_actor_api.web.javbus, 'aclose', close_web)
    monkeypatch.setattr(fill_actor_api.magnet.sukebei, 'aclose', close_sukebei)
    monkeypatch.setattr(fill_actor_api.magnet, 'close_magnet_logger', close_logger)
    monkeypatch.setattr(fill_actor_api, '_cloud_client', SimpleNamespace(close=close_cloud))

    await fill_actor_api.aclose()

    close_web.assert_awaited_once()
    close_sukebei.assert_awaited_once()
    close_logger.assert_called_once()
    close_cloud.assert_called_once()


@pytest.mark.asyncio
async def test_cloud_file_metadata_uses_fresh_exact_parent_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    matching = clouddrive_pb2.CloudDriveFile(
        id='file-id',
        name='ABC-001.mp4',
        fullPathName='/cloud/library/source-b/ABC/ABC-001.mp4',
        size=123,
        isDirectory=False,
    )
    matching.writeTime.seconds = 456
    matching.writeTime.nanos = 789
    matching.fileHashes[2] = 'sha1-value'
    other = clouddrive_pb2.CloudDriveFile(
        id='other-id',
        name='ABC-001.mp4',
        fullPathName='/different/path/ABC-001.mp4',
    )
    get_sub_files = Mock(return_value=[other, matching])
    monkeypatch.setattr(fill_actor_api, '_cloud_client', SimpleNamespace(get_sub_files=get_sub_files))

    listing = await fill_actor_api.list_cloud_directory('/cloud/library/source-b/ABC')
    metadata = await fill_actor_api.stat_cloud_file('/cloud/library/source-b/ABC/ABC-001.mp4')

    assert listing[1] == {
        'id': 'file-id',
        'name': 'ABC-001.mp4',
        'full_path': '/cloud/library/source-b/ABC/ABC-001.mp4',
        'size': 123,
        'is_directory': False,
        'write_time': {'seconds': 456, 'nanos': 789},
        'hashes': {'2': 'sha1-value'},
    }
    assert metadata == listing[1]
    assert get_sub_files.call_args_list == [
        call('/cloud/library/source-b/ABC', force_refresh=True),
        call('/cloud/library/source-b/ABC', force_refresh=True),
    ]


@pytest.mark.asyncio
async def test_cloud_file_stat_returns_none_for_missing_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    get_sub_files = Mock(side_effect=FileNotFoundError)
    monkeypatch.setattr(fill_actor_api, '_cloud_client', SimpleNamespace(get_sub_files=get_sub_files))

    assert await fill_actor_api.stat_cloud_file('/cloud/library/source-b/ABC/missing.mp4') is None


@pytest.mark.asyncio
async def test_move_cloud_file_always_uses_skip_conflict_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    result = clouddrive_pb2.FileOperationResult(
        success=True,
        resultFilePaths=['/cloud/library/move-in/ABC/ABC-001.mp4'],
    )
    move_file = Mock(return_value=result)
    monkeypatch.setattr(fill_actor_api, '_cloud_client', SimpleNamespace(move_file=move_file))

    response = await fill_actor_api.move_cloud_file(
        '/cloud/library/source-b/ABC/ABC-001.mp4',
        '/cloud/library/move-in/ABC',
    )

    assert response == {
        'success': True,
        'error_message': '',
        'result_file_paths': ('/cloud/library/move-in/ABC/ABC-001.mp4',),
    }
    move_file.assert_called_once_with(
        ['/cloud/library/source-b/ABC/ABC-001.mp4'],
        '/cloud/library/move-in/ABC',
        2,
    )


@pytest.mark.asyncio
async def test_ensure_cloud_directory_creates_and_force_refreshes_one_safe_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = clouddrive_pb2.CloudDriveFile(
        id='folder-id',
        name='ABC',
        fullPathName='/cloud/library/move-in/ABC',
        isDirectory=True,
    )
    get_sub_files = Mock(side_effect=[[], [folder]])
    create_folder = Mock(return_value=clouddrive_pb2.CreateFolderResult())
    monkeypatch.setattr(
        fill_actor_api,
        '_cloud_client',
        SimpleNamespace(get_sub_files=get_sub_files, create_folder=create_folder),
    )

    result = await fill_actor_api.ensure_cloud_directory('/cloud/library/move-in', 'ABC')

    assert result == {'success': True, 'created': True, 'path': '/cloud/library/move-in/ABC'}
    create_folder.assert_called_once_with('/cloud/library/move-in', 'ABC')
    assert get_sub_files.call_args_list == [
        call('/cloud/library/move-in', force_refresh=True),
        call('/cloud/library/move-in', force_refresh=True),
    ]


@pytest.mark.asyncio
async def test_ensure_cloud_directory_accepts_verified_folder_after_create_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = clouddrive_pb2.CloudDriveFile(
        id='folder-id',
        name='ABC',
        fullPathName='/cloud/library/move-in/ABC',
        isDirectory=True,
    )
    get_sub_files = Mock(side_effect=[[], [folder]])
    create_folder = Mock(side_effect=TimeoutError)
    monkeypatch.setattr(
        fill_actor_api,
        '_cloud_client',
        SimpleNamespace(get_sub_files=get_sub_files, create_folder=create_folder),
    )

    result = await fill_actor_api.ensure_cloud_directory('/cloud/library/move-in', 'ABC')

    assert result == {'success': True, 'created': True, 'path': '/cloud/library/move-in/ABC'}
    create_folder.assert_called_once_with('/cloud/library/move-in', 'ABC')
    assert get_sub_files.call_args_list == [
        call('/cloud/library/move-in', force_refresh=True),
        call('/cloud/library/move-in', force_refresh=True),
    ]


@pytest.mark.asyncio
async def test_ensure_cloud_directory_rejects_same_named_file_without_creating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file = clouddrive_pb2.CloudDriveFile(
        id='file-id',
        name='ABC',
        fullPathName='/cloud/library/move-in/ABC',
        isDirectory=False,
    )
    get_sub_files = Mock(return_value=[file])
    create_folder = Mock()
    monkeypatch.setattr(
        fill_actor_api,
        '_cloud_client',
        SimpleNamespace(get_sub_files=get_sub_files, create_folder=create_folder),
    )

    result = await fill_actor_api.ensure_cloud_directory('/cloud/library/move-in', 'ABC')

    assert result == {'success': False, 'created': False, 'path': '/cloud/library/move-in/ABC'}
    create_folder.assert_not_called()
    get_sub_files.assert_called_once_with('/cloud/library/move-in', force_refresh=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['', '.', '..', 'nested/ABC', 'bad\\name', 'bad\nname'])
async def test_ensure_cloud_directory_rejects_unsafe_child_name(name: str) -> None:
    with pytest.raises(ValueError, match='safe path segment'):
        await fill_actor_api.ensure_cloud_directory('/cloud/library/move-in', name)


@pytest.mark.asyncio
async def test_cloud_runtime_builds_injected_insecure_client_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    cloud_module = importlib.import_module('src.utils.clouddrive.clouddrive')
    client = SimpleNamespace(get_sub_files=Mock(return_value=[]))
    constructor = Mock(return_value=client)
    monkeypatch.setattr(cloud_module, 'CloudDriveClient', constructor)
    monkeypatch.setattr(fill_actor_api, '_cloud_client', None)
    monkeypatch.setenv('EMBYX_MONITOR_RUNTIME_CLOUDDRIVE_ADDRESS', 'clouddrive.internal:80')
    monkeypatch.setenv('EMBYX_MONITOR_RUNTIME_CLOUDDRIVE_API_TOKEN', 'test-token')
    monkeypatch.setenv('EMBYX_MONITOR_RUNTIME_CLOUDDRIVE_SECURE', 'false')

    assert await fill_actor_api.list_cloud_directory('/cloud/library') == ()

    constructor.assert_called_once_with(
        address='clouddrive.internal:80',
        api_token='test-token',  # noqa: S106
        secure=False,
    )


@pytest.mark.asyncio
async def test_cancelled_cloud_move_waits_for_sync_call_before_returning(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    release = threading.Event()
    close = Mock()

    def move_file(_source: list[str], _destination: str, _policy: int) -> clouddrive_pb2.FileOperationResult:
        started.set()
        assert release.wait(timeout=2)
        msg = 'late gRPC failure'
        raise RuntimeError(msg)

    monkeypatch.setattr(
        fill_actor_api,
        '_cloud_client',
        SimpleNamespace(move_file=move_file, close=close),
    )
    task = asyncio.create_task(
        fill_actor_api.move_cloud_file(
            '/cloud/library/source-b/ABC/ABC-001.mp4',
            '/cloud/library/move-in/ABC',
        ),
    )
    assert await asyncio.to_thread(started.wait, 1)

    task.cancel()
    await asyncio.sleep(0.01)
    assert not task.done()
    close.assert_not_called()

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
@pytest.mark.parametrize('value', ['relative/path', '//host/path', '/path/../escape', '/path/', '/path\nname'])
async def test_cloud_runtime_rejects_noncanonical_api_paths(value: str) -> None:
    with pytest.raises(ValueError, match='canonical absolute POSIX path'):
        await fill_actor_api.list_cloud_directory(value)


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
from src.embyx_monitor_runtime import fill_actor_api as api

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
    env['EMBYX_MONITOR_RUNTIME_LOG_DIR'] = str(tmp_path)
    env.pop('EMBYX_MONITOR_USE_REAL_CONFIG', None)
    env.pop('EMBYX_USE_REAL_CONFIG', None)
    env.pop('EMBYX_MONITOR_RUNTIME_CLOUDDRIVE_ADDRESS', None)
    env.pop('EMBYX_MONITOR_RUNTIME_CLOUDDRIVE_API_TOKEN', None)
    env.pop('EMBYX_MONITOR_RUNTIME_CLOUDDRIVE_SECURE', None)
    env.pop('EMBYX_RUNTIME_CLOUDDRIVE_ADDRESS', None)
    env.pop('EMBYX_RUNTIME_CLOUDDRIVE_API_TOKEN', None)
    env.pop('EMBYX_RUNTIME_CLOUDDRIVE_SECURE', None)
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
