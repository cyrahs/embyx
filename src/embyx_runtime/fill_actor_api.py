"""Configuration-light compatibility API for the Fill Actor web service."""

import os
from collections.abc import Awaitable, Callable
from pathlib import Path

from src.utils import magnet, web
from src.utils.avid import get_brand

_runtime_log_dir = os.environ.get('EMBYX_RUNTIME_LOG_DIR')
magnet.configure_log_dir(Path(_runtime_log_dir).expanduser() if _runtime_log_dir else None)


PageProgressCallback = Callable[[int, int | None, int | None], Awaitable[None] | None]


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


async def aclose() -> None:
    """Close clients and logging resources owned by this runtime module."""
    try:
        await web.javbus.aclose()
    finally:
        try:
            await magnet.sukebei.aclose()
        finally:
            magnet.close_magnet_logger()
