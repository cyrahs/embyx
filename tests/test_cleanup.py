import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.utils.cleanup import aclose_all


@pytest.mark.asyncio
async def test_aclose_all_closes_loaded_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    javbus_close = AsyncMock()
    sukebei_close = AsyncMock()
    magnet_logger_close = Mock()
    emby_close = AsyncMock()
    translator_close = AsyncMock()
    freshrss_close = Mock()
    clouddrive_close = Mock()

    monkeypatch.setitem(sys.modules, 'src.utils.web', SimpleNamespace(javbus=SimpleNamespace(aclose=javbus_close)))
    monkeypatch.setitem(
        sys.modules,
        'src.utils.magnet',
        SimpleNamespace(sukebei=SimpleNamespace(aclose=sukebei_close), close_magnet_logger=magnet_logger_close),
    )
    monkeypatch.setitem(sys.modules, 'src.utils.emby', SimpleNamespace(aclose_client=emby_close))
    monkeypatch.setitem(sys.modules, 'src.utils.translator', SimpleNamespace(aclose_client=translator_close))
    monkeypatch.setitem(sys.modules, 'src.utils.freshrss', SimpleNamespace(close_client=freshrss_close))
    monkeypatch.setitem(sys.modules, 'src.utils.clouddrive.clouddrive', SimpleNamespace(clouddrive=SimpleNamespace(close=clouddrive_close)))

    await aclose_all()

    javbus_close.assert_awaited_once()
    sukebei_close.assert_awaited_once()
    magnet_logger_close.assert_called_once()
    emby_close.assert_awaited_once()
    translator_close.assert_awaited_once()
    freshrss_close.assert_called_once()
    clouddrive_close.assert_called_once()


@pytest.mark.asyncio
async def test_aclose_all_continues_after_cleanup_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    javbus_close = AsyncMock(side_effect=OSError('boom'))
    sukebei_close = AsyncMock()
    magnet_logger_close = Mock()

    monkeypatch.setitem(sys.modules, 'src.utils.web', SimpleNamespace(javbus=SimpleNamespace(aclose=javbus_close)))
    monkeypatch.setitem(
        sys.modules,
        'src.utils.magnet',
        SimpleNamespace(sukebei=SimpleNamespace(aclose=sukebei_close), close_magnet_logger=magnet_logger_close),
    )

    await aclose_all()

    javbus_close.assert_awaited_once()
    sukebei_close.assert_awaited_once()
    magnet_logger_close.assert_called_once()
