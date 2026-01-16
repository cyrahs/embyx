from threading import Event, Lock
from unittest.mock import patch

from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileMovedEvent

from src.monitor import StrmChangeHandler


def build_handler() -> tuple[StrmChangeHandler, Event, dict[str, float], dict[str, int]]:
    trigger_event = Event()
    last_event_time = {'value': 0.0}
    event_counter = {'value': 0}
    lock = Lock()
    handler = StrmChangeHandler(trigger_event, last_event_time, event_counter, lock)
    return handler, trigger_event, last_event_time, event_counter


def test_strm_change_handler_marks_strm_event() -> None:
    handler, trigger_event, last_event_time, event_counter = build_handler()
    with patch('src.monitor.time.monotonic', return_value=123.0):
        handler.on_created(FileCreatedEvent('/tmp/video.strm'))
    assert trigger_event.is_set()
    assert last_event_time['value'] == 123.0
    assert event_counter['value'] == 1


def test_strm_change_handler_ignores_non_strm() -> None:
    handler, trigger_event, last_event_time, event_counter = build_handler()
    with patch('src.monitor.time.monotonic', return_value=456.0):
        handler.on_created(FileCreatedEvent('/tmp/video.txt'))
    assert not trigger_event.is_set()
    assert last_event_time['value'] == 0.0
    assert event_counter['value'] == 0


def test_strm_change_handler_ignores_directories() -> None:
    handler, trigger_event, last_event_time, event_counter = build_handler()
    with patch('src.monitor.time.monotonic', return_value=789.0):
        handler.on_created(DirCreatedEvent('/tmp/videos'))
    assert not trigger_event.is_set()
    assert last_event_time['value'] == 0.0
    assert event_counter['value'] == 0


def test_strm_change_handler_tracks_move_destination() -> None:
    handler, trigger_event, last_event_time, event_counter = build_handler()
    with patch('src.monitor.time.monotonic', return_value=321.0):
        handler.on_moved(FileMovedEvent('/tmp/old.txt', '/tmp/new.strm'))
    assert trigger_event.is_set()
    assert last_event_time['value'] == 321.0
    assert event_counter['value'] == 1
