import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

if __package__:
    from src import mapping
else:
    import mapping
from src.core import logger

log = logger.get('mapping-monitor')

DEBOUNCE_SECONDS = 5


class StrmChangeHandler(FileSystemEventHandler):
    def __init__(self, trigger_event: threading.Event, last_event_time: dict[str, float], lock: threading.Lock) -> None:
        self._trigger_event = trigger_event
        self._last_event_time = last_event_time
        self._lock = lock

    def _mark(self, path: str | None, *, is_directory: bool) -> None:
        if is_directory or not path:
            return
        if Path(path).suffix.lower() != '.strm':
            return
        with self._lock:
            self._last_event_time['value'] = time.monotonic()
        self._trigger_event.set()

    def on_created(self, event) -> None:  # noqa: ANN001
        self._mark(event.src_path, is_directory=event.is_directory)

    def on_modified(self, event) -> None:  # noqa: ANN001
        self._mark(event.src_path, is_directory=event.is_directory)

    def on_deleted(self, event) -> None:  # noqa: ANN001
        self._mark(event.src_path, is_directory=event.is_directory)

    def on_moved(self, event) -> None:  # noqa: ANN001
        self._mark(event.src_path, is_directory=event.is_directory)
        dest_path = getattr(event, 'dest_path', None)
        self._mark(dest_path, is_directory=event.is_directory)


def run_mapping() -> bool:
    try:
        mapping.main()
    except Exception:
        log.exception('Mapping run failed')
        return False
    return True


def should_clear_trigger(*, success: bool, run_started: float, last_after: float) -> bool:
    return success and last_after <= run_started


def clear_trigger_if_stable(
    trigger_event: threading.Event,
    last_event_time: dict[str, float],
    lock: threading.Lock,
    *,
    success: bool,
    run_started: float,
) -> bool:
    with lock:
        last_after = last_event_time['value']
        if not should_clear_trigger(success=success, run_started=run_started, last_after=last_after):
            return False
        trigger_event.clear()
        return True


def main() -> None:
    log.info('Starting mapping monitor')
    src_dir = mapping.cfg.src_dir
    trigger_event = threading.Event()
    last_event_time = {'value': 0.0}
    lock = threading.Lock()
    handler = StrmChangeHandler(trigger_event, last_event_time, lock)
    observer = Observer()
    observer.schedule(handler, str(src_dir), recursive=True)
    observer.start()
    try:
        while not run_mapping():
            log.info('Retrying mapping in %d seconds', DEBOUNCE_SECONDS)
            time.sleep(DEBOUNCE_SECONDS)

        while True:
            trigger_event.wait()
            while True:
                with lock:
                    last_seen = last_event_time['value']
                since = time.monotonic() - last_seen
                if since < DEBOUNCE_SECONDS:
                    time.sleep(DEBOUNCE_SECONDS - since)
                    continue
                run_started = time.monotonic()
                log.info('Detected changes in %s, running mapping', src_dir)
                success = run_mapping()
                clear_trigger = clear_trigger_if_stable(
                    trigger_event,
                    last_event_time,
                    lock,
                    success=success,
                    run_started=run_started,
                )
                if not clear_trigger:
                    if not success:
                        log.info('Retrying mapping in %d seconds', DEBOUNCE_SECONDS)
                        time.sleep(DEBOUNCE_SECONDS)
                    continue
                break
    except KeyboardInterrupt:
        log.info('Mapping monitor interrupted, exiting')
    finally:
        observer.stop()
        observer.join()


if __name__ == '__main__':
    main()
