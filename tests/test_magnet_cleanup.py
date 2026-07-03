import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.utils import magnet


def test_close_magnet_logger_removes_file_handler(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    monkeypatch.setattr(magnet.config, 'log_dir', tmp_path)

    magnet._get_magnet_logger()  # noqa: SLF001

    magnet_logger = logging.getLogger('magnet_chosen')
    handlers = [handler for handler in magnet_logger.handlers if getattr(handler, magnet._MAGNET_HANDLER_MARKER, False)]  # noqa: SLF001
    assert handlers

    magnet.close_magnet_logger()

    assert not [handler for handler in magnet_logger.handlers if getattr(handler, magnet._MAGNET_HANDLER_MARKER, False)]  # noqa: SLF001


@pytest.mark.asyncio
async def test_sukebei_aclose_resets_client_and_semaphore(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SimpleNamespace(aclose=AsyncMock())
    semaphore = object()
    monkeypatch.setattr(magnet.sukebei, '_client', client)
    monkeypatch.setattr(magnet.sukebei, '_semaphore', semaphore)
    monkeypatch.setattr(magnet.sukebei, '_semaphore_loop', object())

    await magnet.sukebei.aclose()

    client.aclose.assert_awaited_once()
    assert magnet.sukebei._client is None  # noqa: SLF001
    assert magnet.sukebei._semaphore is None  # noqa: SLF001
    assert magnet.sukebei._semaphore_loop is None  # noqa: SLF001
