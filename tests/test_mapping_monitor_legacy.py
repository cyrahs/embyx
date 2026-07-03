import threading

from src import mapping_monitor


def test_should_clear_trigger_only_after_success_without_new_events() -> None:
    assert mapping_monitor.should_clear_trigger(success=True, run_started=10.0, last_after=10.0)
    assert not mapping_monitor.should_clear_trigger(success=False, run_started=10.0, last_after=10.0)
    assert not mapping_monitor.should_clear_trigger(success=True, run_started=10.0, last_after=10.1)


def test_clear_trigger_if_stable_clears_inside_lock() -> None:
    trigger_event = threading.Event()
    lock = threading.Lock()
    last_event_time = {'value': 10.0}
    trigger_event.set()

    cleared = mapping_monitor.clear_trigger_if_stable(
        trigger_event,
        last_event_time,
        lock,
        success=True,
        run_started=10.0,
    )

    assert cleared
    assert not trigger_event.is_set()


def test_clear_trigger_if_stable_keeps_new_event_set() -> None:
    trigger_event = threading.Event()
    lock = threading.Lock()
    last_event_time = {'value': 10.1}
    trigger_event.set()

    cleared = mapping_monitor.clear_trigger_if_stable(
        trigger_event,
        last_event_time,
        lock,
        success=True,
        run_started=10.0,
    )

    assert not cleared
    assert trigger_event.is_set()
