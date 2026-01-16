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
FULL_SYNC_INTERVAL_SECONDS = 24 * 60 * 60
FULL_SYNC_RETRY_SECONDS = 5 * 60


class StrmChangeHandler(FileSystemEventHandler):
    def __init__(
        self,
        trigger_event: threading.Event,
        last_event_time: dict[str, float],
        event_counter: dict[str, int],
        changed_paths: set[Path],
        deleted_paths: set[Path],
        lock: threading.Lock,
    ) -> None:
        self._trigger_event = trigger_event
        self._last_event_time = last_event_time
        self._event_counter = event_counter
        self._changed_paths = changed_paths
        self._deleted_paths = deleted_paths
        self._lock = lock

    def _record_event(self, path: str | None, is_directory: bool, *, deleted: bool) -> None:
        if is_directory or not path:
            return
        if Path(path).suffix.lower() != '.strm':
            return
        path_obj = Path(path)
        with self._lock:
            self._last_event_time['value'] = time.monotonic()
            self._event_counter['value'] += 1
            if deleted:
                self._changed_paths.discard(path_obj)
                self._deleted_paths.add(path_obj)
            else:
                self._deleted_paths.discard(path_obj)
                self._changed_paths.add(path_obj)
        self._trigger_event.set()

    def on_created(self, event) -> None:  # noqa: ANN001
        self._record_event(event.src_path, event.is_directory, deleted=False)

    def on_modified(self, event) -> None:  # noqa: ANN001
        self._record_event(event.src_path, event.is_directory, deleted=False)

    def on_deleted(self, event) -> None:  # noqa: ANN001
        self._record_event(event.src_path, event.is_directory, deleted=True)

    def on_moved(self, event) -> None:  # noqa: ANN001
        self._record_event(event.src_path, event.is_directory, deleted=True)
        dest_path = getattr(event, 'dest_path', None)
        self._record_event(dest_path, event.is_directory, deleted=False)


def run_mapping_full() -> bool:
    try:
        mapping.main()
    except Exception:
        mapping_log.exception('Mapping run failed')
        return False
    return True


def run_mapping_incremental(changed_paths: set[Path], deleted_paths: set[Path]) -> tuple[set[Path], set[Path]]:
    if not changed_paths and not deleted_paths:
        return set(), set()
    failed_changed: set[Path] = set()
    failed_deleted: set[Path] = set()
    mapping.reset_counter()
    src_dir = mapping.cfg.src_dir
    dst_dir = mapping.cfg.dst_dir
    for path in sorted(deleted_paths):
        try:
            mapping.delete_one(path, src_dir, dst_dir)
        except Exception:
            mapping_log.exception('Incremental delete failed for %s', path)
            failed_deleted.add(path)
    for path in sorted(changed_paths):
        try:
            mapping.update_one(path, src_dir, dst_dir)
        except Exception:
            mapping_log.exception('Incremental update failed for %s', path)
            failed_changed.add(path)
    mapping_log.info(
        'Incremental mapping updated=%d skipped=%d deleted=%d dirs_deleted=%d',
        mapping.counter.files_updated,
        mapping.counter.files_skipped,
        mapping.counter.files_deleted,
        mapping.counter.dirs_deleted,
    )
    return failed_changed, failed_deleted


def should_clear_full_sync(success: bool, counter_before: int, counter_after: int) -> bool:
    return success and counter_before == counter_after


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
    changed_paths: set[Path] = set()
    deleted_paths: set[Path] = set()
    lock = threading.Lock()
    handler = StrmChangeHandler(
        trigger_event,
        last_event_time,
        event_counter,
        changed_paths,
        deleted_paths,
        lock,
    )
    observer = Observer()
    observer.schedule(handler, str(src_dir), recursive=True)
    observer.start()
    try:
        while not stop_event.is_set() and not run_mapping_full():
            mapping_log.info('Retrying mapping in %d seconds', DEBOUNCE_SECONDS)
            if stop_event.wait(timeout=DEBOUNCE_SECONDS):
                return
        next_full_sync = time.monotonic() + FULL_SYNC_INTERVAL_SECONDS

        while not stop_event.is_set():
            if time.monotonic() >= next_full_sync:
                with lock:
                    counter_before = event_counter['value']
                mapping_log.info('Running scheduled full mapping sync')
                success = run_mapping_full()
                cleared = False
                with lock:
                    counter_after = event_counter['value']
                    if should_clear_full_sync(success, counter_before, counter_after):
                        changed_paths.clear()
                        deleted_paths.clear()
                        trigger_event.clear()
                        cleared = True
                if not cleared:
                    trigger_event.set()
                interval = FULL_SYNC_INTERVAL_SECONDS if success else FULL_SYNC_RETRY_SECONDS
                next_full_sync = time.monotonic() + interval
                continue
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
                with lock:
                    changed_snapshot = set(changed_paths)
                    deleted_snapshot = set(deleted_paths)
                    changed_paths.clear()
                    deleted_paths.clear()
                    counter_snapshot = event_counter['value']
                if changed_snapshot or deleted_snapshot:
                    mapping_log.info('Detected changes in %s, running incremental mapping', src_dir)
                    failed_changed, failed_deleted = run_mapping_incremental(changed_snapshot, deleted_snapshot)
                    if failed_changed or failed_deleted:
                        mapping_log.warning(
                            'Incremental mapping failed for %d paths, requeueing',
                            len(failed_changed) + len(failed_deleted),
                        )
                        with lock:
                            changed_paths.update(failed_changed)
                            deleted_paths.update(failed_deleted)
                            last_event_time['value'] = time.monotonic()
                        trigger_event.set()
                        break
                with lock:
                    last_after = last_event_time['value']
                    counter_after = event_counter['value']
                if last_after > run_started or counter_after > counter_snapshot:
                    continue
                trigger_event.clear()
                with lock:
                    if event_counter['value'] > counter_after or changed_paths or deleted_paths:
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
