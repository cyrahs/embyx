from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if __package__ and __package__.startswith('src.'):
    from src.core import logger
else:
    from core import logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

log = logger.get('cleanup')


def _get_loaded_module(*names: str) -> Any | None:
    for name in names:
        module = sys.modules.get(name)
        if module is not None:
            return module
    return None


async def _run_async_cleanup(name: str, cleanup: Callable[[], Awaitable[None]]) -> None:
    try:
        await cleanup()
    except Exception:  # noqa: BLE001
        log.warning('Failed to close %s client', name, exc_info=True)


def _run_sync_cleanup(name: str, cleanup: Callable[[], None]) -> None:
    try:
        cleanup()
    except Exception:  # noqa: BLE001
        log.warning('Failed to close %s client', name, exc_info=True)


async def aclose_all() -> None:
    web_module: Any = _get_loaded_module('src.utils.web', 'utils.web')
    if web_module is not None:
        await _run_async_cleanup('javbus', web_module.javbus.aclose)

    magnet_module: Any = _get_loaded_module('src.utils.magnet', 'utils.magnet')
    if magnet_module is not None:
        await _run_async_cleanup('sukebei', magnet_module.sukebei.aclose)
        _run_sync_cleanup('magnet_logger', magnet_module.close_magnet_logger)

    emby_module: Any = _get_loaded_module('src.utils.emby', 'utils.emby')
    if emby_module is not None:
        await _run_async_cleanup('emby', emby_module.aclose_client)

    translator_module: Any = _get_loaded_module('src.utils.translator', 'utils.translator')
    if translator_module is not None:
        await _run_async_cleanup('translator', translator_module.aclose_client)

    freshrss_module: Any = _get_loaded_module('src.utils.freshrss', 'utils.freshrss')
    if freshrss_module is not None:
        _run_sync_cleanup('freshrss', freshrss_module.close_client)

    clouddrive_module: Any = _get_loaded_module('src.utils.clouddrive.clouddrive', 'utils.clouddrive.clouddrive')
    if clouddrive_module is not None:
        _run_sync_cleanup('clouddrive', clouddrive_module.clouddrive.close)
