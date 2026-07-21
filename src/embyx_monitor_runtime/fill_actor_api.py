"""Configuration-light compatibility API for the Fill Actor web service."""

import asyncio
import os
import posixpath
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from src.utils import magnet, web
from src.utils.avid import get_brand


def _get_runtime_env(name: str) -> str | None:
    """Read a renamed runtime variable, falling back to its legacy name."""
    value = os.environ.get(f'EMBYX_MONITOR_RUNTIME_{name}')
    if value is not None:
        return value
    return os.environ.get(f'EMBYX_RUNTIME_{name}')


_runtime_log_dir = _get_runtime_env('LOG_DIR')
magnet.configure_log_dir(Path(_runtime_log_dir).expanduser() if _runtime_log_dir else None)


PageProgressCallback = Callable[[int, int | None, int | None], Awaitable[None] | None]
CloudFile = dict[str, object]

_cloud_client: Any | None = None
_TRUE_VALUES = frozenset({'1', 'true', 'yes', 'on'})
_FALSE_VALUES = frozenset({'0', 'false', 'no', 'off'})
_ASCII_CONTROL_LIMIT = 32
_ASCII_DELETE = 127


async def list_actor_video_ids(
    actor_id: str,
    progress_callback: PageProgressCallback | None = None,
) -> tuple[str, ...]:
    """Return the video IDs published for one JavBus actor."""
    if progress_callback is None:
        return tuple(await web.javbus.scrape(actor_id))
    return tuple(await web.javbus.scrape(actor_id, progress_callback=progress_callback))


def resolve_brand(video_id: str) -> str | None:
    """Resolve the brand directory segment for a video ID."""
    return get_brand(video_id)


async def find_sukebei_magnet(video_id: str) -> str | None:
    """Return the preferred Sukebei magnet for a video ID, if one exists."""
    return await magnet.sukebei.get_magnet(video_id)


async def list_cloud_directory(api_dir: str) -> tuple[CloudFile, ...]:
    """Return fresh CloudDrive metadata for one API-native directory path."""
    directory = _validate_api_path(api_dir, allow_root=True)
    files = await _run_sync_complete(
        _get_cloud_client().get_sub_files,
        directory,
        force_refresh=True,
    )
    return tuple(_cloud_file_to_dict(file) for file in files)


async def stat_cloud_file(api_path: str) -> CloudFile | None:
    """Return fresh metadata for an exact CloudDrive API path, if it exists."""
    path = _validate_api_path(api_path, allow_root=False)
    parent, name = posixpath.split(path)
    try:
        files = await list_cloud_directory(parent)
    except FileNotFoundError:
        return None
    return next(
        (file for file in files if file['name'] == name and file['full_path'] == path),
        None,
    )


async def ensure_cloud_directory(parent_api_dir: str, folder_name: str) -> dict[str, object]:
    """Ensure one direct child directory exists and verify it through a fresh listing."""
    parent = _validate_api_path(parent_api_dir, allow_root=True)
    name = _validate_path_segment(folder_name)
    expected_path = posixpath.join(parent, name)
    files = await list_cloud_directory(parent)
    existing = next(
        (file for file in files if file['full_path'] == expected_path and file['name'] == name),
        None,
    )
    if existing is not None:
        return {'success': bool(existing['is_directory']), 'created': False, 'path': expected_path}

    create_error: Exception | None = None
    try:
        await _run_sync_complete(_get_cloud_client().create_folder, parent, name)
    except Exception as exc:  # noqa: BLE001  # Follow-up listing resolves timeout/already-exists ambiguity.
        create_error = exc
    files = await list_cloud_directory(parent)
    created = next(
        (file for file in files if file['full_path'] == expected_path and file['name'] == name),
        None,
    )
    if created is not None and bool(created['is_directory']):
        return {'success': True, 'created': True, 'path': expected_path}
    if create_error is not None:
        raise create_error
    return {'success': False, 'created': False, 'path': expected_path}


async def move_cloud_file(source_api_path: str, destination_api_dir: str) -> dict[str, object]:
    """Move one CloudDrive file without overwriting an existing destination."""
    source = _validate_api_path(source_api_path, allow_root=False)
    destination = _validate_api_path(destination_api_dir, allow_root=True)
    result = await _run_sync_complete(
        _get_cloud_client().move_file,
        [source],
        destination,
        2,
    )
    return {
        'success': bool(result.success),
        'error_message': str(result.errorMessage),
        'result_file_paths': tuple(str(path) for path in result.resultFilePaths),
    }


async def aclose() -> None:
    """Close clients and logging resources owned by this runtime module."""
    try:
        await web.javbus.aclose()
    finally:
        try:
            await magnet.sukebei.aclose()
        finally:
            try:
                magnet.close_magnet_logger()
            finally:
                _close_cloud_client()


def _get_cloud_client() -> Any:
    global _cloud_client
    if _cloud_client is not None:
        return _cloud_client

    address = _get_runtime_env('CLOUDDRIVE_ADDRESS')
    api_token = _get_runtime_env('CLOUDDRIVE_API_TOKEN')
    if not address:
        msg = 'EMBYX_MONITOR_RUNTIME_CLOUDDRIVE_ADDRESS is required for CloudDrive operations'
        raise RuntimeError(msg)
    if not api_token:
        msg = 'EMBYX_MONITOR_RUNTIME_CLOUDDRIVE_API_TOKEN is required for CloudDrive operations'
        raise RuntimeError(msg)
    secure_value = _get_runtime_env('CLOUDDRIVE_SECURE')
    secure = _parse_boolean_env(
        'EMBYX_MONITOR_RUNTIME_CLOUDDRIVE_SECURE',
        secure_value if secure_value is not None else 'true',
    )

    from src.utils.clouddrive.clouddrive import CloudDriveClient  # noqa: PLC0415

    _cloud_client = CloudDriveClient(address=address, api_token=api_token, secure=secure)
    return _cloud_client


def _close_cloud_client() -> None:
    global _cloud_client
    if _cloud_client is None:
        return
    try:
        _cloud_client.close()
    finally:
        _cloud_client = None


def _parse_boolean_env(name: str, raw: str) -> bool:
    value = raw.casefold()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    msg = f'{name} must be a boolean'
    raise ValueError(msg)


def _validate_api_path(value: str, *, allow_root: bool) -> str:
    if (
        not value.startswith('/')
        or value.startswith('//')
        or '\x00' in value
        or '\\' in value
        or any(ord(character) < _ASCII_CONTROL_LIMIT or ord(character) == _ASCII_DELETE for character in value)
        or posixpath.normpath(value) != value
        or (not allow_root and value == '/')
    ):
        msg = 'CloudDrive API path must be a canonical absolute POSIX path'
        raise ValueError(msg)
    return value


def _validate_path_segment(value: str) -> str:
    if (
        not value
        or value in {'.', '..'}
        or '/' in value
        or '\\' in value
        or '\x00' in value
        or any(ord(character) < _ASCII_CONTROL_LIMIT or ord(character) == _ASCII_DELETE for character in value)
    ):
        msg = 'CloudDrive folder name must be one safe path segment'
        raise ValueError(msg)
    return value


def _cloud_file_to_dict(file: Any) -> CloudFile:
    write_time: dict[str, int] | None = None
    if file.HasField('writeTime'):
        write_time = {
            'seconds': int(file.writeTime.seconds),
            'nanos': int(file.writeTime.nanos),
        }
    return {
        'id': str(file.id),
        'name': str(file.name),
        'full_path': str(file.fullPathName),
        'size': int(file.size),
        'is_directory': bool(file.isDirectory),
        'write_time': write_time,
        'hashes': dict(sorted((str(key), str(value)) for key, value in file.fileHashes.items())),
    }


async def _run_sync_complete(function: Callable[..., Any], *args: object, **kwargs: object) -> Any:
    """Wait for a sync gRPC call to finish even when its asyncio caller is cancelled."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    completed = asyncio.get_running_loop().create_future()

    def notify_done(_task: asyncio.Task[Any]) -> None:
        if not completed.done():
            completed.set_result(None)

    task.add_done_callback(notify_done)
    cancelled = False
    while not completed.done():
        try:
            await asyncio.shield(completed)
        except asyncio.CancelledError:
            cancelled = True
    if cancelled:
        with suppress(Exception):
            task.result()
        raise asyncio.CancelledError
    return task.result()
