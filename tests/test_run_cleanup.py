import asyncio

import pytest

import run


@pytest.mark.asyncio
async def test_sync_runner_schedules_cleanup_inside_running_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    cleaned = asyncio.Event()

    async def cleanup() -> None:
        cleaned.set()

    monkeypatch.setattr(run, 'aclose_all', cleanup)

    run._run_sync_with_cleanup(lambda: None)  # noqa: SLF001
    await asyncio.sleep(0)

    assert cleaned.is_set()
