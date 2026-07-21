"""Compatibility package for the renamed embyx-monitor runtime API."""

import sys

from src.embyx_monitor_runtime import fill_actor_api

sys.modules[f'{__name__}.fill_actor_api'] = fill_actor_api

__all__ = ['fill_actor_api']
