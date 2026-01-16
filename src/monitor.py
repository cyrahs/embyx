import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

if __package__:
    from src import archive, mapping, rss
    from src.core import logger
else:
    import archive
    import mapping
    import rss
    from core import logger

main_log = logger.get('monitor')
update_log = logger.get('update-monitor')
mapping_log = logger.get('mapping-monitor')

RUN_INTERVAL_SECONDS = 30 * 60
DEBOUNCE_SECONDS = 2


class StrmChangeHandler(FileSystemEventHandler):
    def __init__(
        self,
        trigger_event: threading.Event,
        last_event_time: dict[str, float],
        event_counter: dict[str, int],
        lock: threading.Lock,
    ) -> None:
        self._trigger_event = trigger_event
        self._last_event_time = last_event_time
        self._event_counter = event_counter
        self._lock = lock

    def _mark(self, path: str | None, is_directory: bool) -> None:
        if is_directory or not path:
            return
        if Path(path).suffix.lower() != '.strm':
            return
        with self._lock:
            self._last_event_time['value'] = time.monotonic()
            self._event_counter['value'] += 1
        self._trigger_event.set()

    def on_created(self, event) -> None:  # noqa: ANN001
        self._mark(event.src_path, event.is_directory)

    def on_modified(self, event) -> None:  # noqa: ANN001
        self._mark(event.src_path, event.is_directory)

    def on_deleted(self, event) -> None:  # noqa: ANN001
        self._mark(event.src_path, event.is_directory)

    def on_moved(self, event) -> None:  # noqa: ANN001
        self._mark(event.src_path, event.is_directory)
        dest_path = getattr(event, 'dest_path', None)
        self._mark(dest_path, event.is_directory)


def run_mapping() -> bool:
    try:
        mapping.main()
    except Exception:
        mapping_log.exception('Mapping run failed')
        return False
    return True


def run_update_once() -> None:
    rss.main()
    archive.main()


def run_update_loop(stop_event: threading.Event) -> None:
    update_log.info('Starting update loop with %d second interval', RUN_INTERVAL_SECONDS)
    while not stop_event.is_set():
        start = time.monotonic()
        try:
            run_update_once()
        except Exception:
            update_log.exception('Update monitor run failed')
        elapsed = time.monotonic() - start
        sleep_for = max(0, RUN_INTERVAL_SECONDS - elapsed)
        update_log.info('Sleeping %d seconds before next update run', int(sleep_for))
        if stop_event.wait(timeout=sleep_for):
            break
    update_log.info('Update loop exiting')


def run_mapping_loop(stop_event: threading.Event) -> None:
    mapping_log.info('Starting mapping monitor')
    src_dir = mapping.cfg.src_dir
    trigger_event = threading.Event()
    last_event_time = {'value': 0.0}
    event_counter = {'value': 0}
    lock = threading.Lock()
    handler = StrmChangeHandler(trigger_event, last_event_time, event_counter, lock)
    observer = Observer()
    observer.schedule(handler, str(src_dir), recursive=True)
    observer.start()
    try:
        while not stop_event.is_set() and not run_mapping():
            mapping_log.info('Retrying mapping in %d seconds', DEBOUNCE_SECONDS)
            if stop_event.wait(timeout=DEBOUNCE_SECONDS):
                return

        while not stop_event.is_set():
            if not trigger_event.wait(timeout=0.5):
                continue
            while not stop_event.is_set():
                with lock:
                    last_seen = last_event_time['value']
                since = time.monotonic() - last_seen
                if since < DEBOUNCE_SECONDS:
                    if stop_event.wait(timeout=DEBOUNCE_SECONDS - since):
                        return
                    continue
                run_started = time.monotonic()
                mapping_log.info('Detected changes in %s, running mapping', src_dir)
                run_mapping()
                with lock:
                    last_after = last_event_time['value']
                    counter_after = event_counter['value']
                if last_after > run_started:
                    continue
                trigger_event.clear()
                with lock:
                    if event_counter['value'] > counter_after:
                        trigger_event.set()
                        continue
                break
    finally:
        observer.stop()
        observer.join()


def main() -> None:
    main_log.info('Starting combined monitor')
    stop_event = threading.Event()
    update_thread = threading.Thread(target=run_update_loop, args=(stop_event,), name='update-monitor', daemon=True)
    update_thread.start()
    try:
        run_mapping_loop(stop_event)
    except KeyboardInterrupt:
        main_log.info('Monitor interrupted, exiting')
    finally:
        stop_event.set()
        update_thread.join()


if __name__ == '__main__':
    main()
