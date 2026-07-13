"""Configuration-light compatibility API for the Fill Actor web service."""

import os
from pathlib import Path

from src.utils import magnet, web
from src.utils.avid import get_brand

_runtime_log_dir = os.environ.get('EMBYX_RUNTIME_LOG_DIR')
magnet.configure_log_dir(Path(_runtime_log_dir).expanduser() if _runtime_log_dir else None)


async def list_actor_video_ids(actor_id: str) -> tuple[str, ...]:
    """Return the video IDs published for one JavBus actor."""
    return tuple(await web.javbus.scrape(actor_id))


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
