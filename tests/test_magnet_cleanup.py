import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.utils import magnet


def test_close_magnet_logger_removes_file_handler(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    monkeypatch.setattr(magnet, '_configured_log_dir', tmp_path)

    magnet._get_magnet_logger()  # noqa: SLF001

    magnet_logger = logging.getLogger('magnet_chosen')
    handlers = [handler for handler in magnet_logger.handlers if getattr(handler, magnet._MAGNET_HANDLER_MARKER, False)]  # noqa: SLF001
    assert handlers

    magnet.close_magnet_logger()

    assert not [handler for handler in magnet_logger.handlers if getattr(handler, magnet._MAGNET_HANDLER_MARKER, False)]  # noqa: SLF001


def test_configure_log_dir_can_disable_file_logging(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    monkeypatch.setattr(magnet, '_configured_log_dir', tmp_path)
    magnet._get_magnet_logger()  # noqa: SLF001

    magnet.configure_log_dir(None)

    magnet_logger = logging.getLogger('magnet_chosen')
    assert not [handler for handler in magnet_logger.handlers if getattr(handler, magnet._MAGNET_HANDLER_MARKER, False)]  # noqa: SLF001
    assert magnet._get_magnet_logger() is magnet_logger  # noqa: SLF001


def test_unconfigured_log_dir_uses_legacy_config_lazily(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    from src.core import config  # noqa: PLC0415

    monkeypatch.setattr(config, 'log_dir', tmp_path)
    monkeypatch.setattr(magnet, '_configured_log_dir', magnet._LOG_DIR_UNSET)  # noqa: SLF001

    magnet._get_magnet_logger().info('legacy')  # noqa: SLF001
    magnet.close_magnet_logger()

    assert (tmp_path / 'magnets.log').read_text(encoding='utf-8') == 'legacy\n'


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
