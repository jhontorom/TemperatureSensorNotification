import pytest

from room_monitor.alerts import AlertState, AlertTracker, EventKind, Metric, evaluate_alerts
from room_monitor.sensor import SensorReading
from room_monitor.thresholds import RangeState


class MemoryStore:
    def __init__(self, state=AlertState()):
        self.state = state
        self.saved = []

    def load(self):
        return self.state

    def save(self, state):
        self.state = state
        self.saved.append(state)


class FailingStore(MemoryStore):
    def save(self, state):
        raise OSError("state storage unavailable")


@pytest.mark.parametrize(
    ("temperature", "humidity"),
    [(10.0, 30.0), (27.0, 60.0), (20.0, 45.0)],
)
def test_limit_values_are_normal(temperature, humidity):
    result = evaluate_alerts(AlertState(), SensorReading(temperature, humidity))

    assert result.current_state == AlertState()
    assert result.events == ()


@pytest.mark.parametrize(
    ("reading", "metric", "state"),
    [
        (SensorReading(9.99, 45.0), Metric.TEMPERATURE, RangeState.LOW),
        (SensorReading(27.01, 45.0), Metric.TEMPERATURE, RangeState.HIGH),
        (SensorReading(20.0, 29.99), Metric.HUMIDITY, RangeState.LOW),
        (SensorReading(20.0, 60.01), Metric.HUMIDITY, RangeState.HIGH),
    ],
)
def test_first_crossing_creates_one_alert(reading, metric, state):
    result = evaluate_alerts(AlertState(), reading)

    assert len(result.events) == 1
    assert result.events[0].metric is metric
    assert result.events[0].kind is EventKind.ALERT
    assert result.events[0].current is state


def test_repeated_out_of_range_reading_creates_no_duplicate():
    previous = AlertState(temperature=RangeState.HIGH)

    result = evaluate_alerts(previous, SensorReading(30.0, 45.0))

    assert result.events == ()


@pytest.mark.parametrize("previous", [RangeState.LOW, RangeState.HIGH])
def test_return_to_normal_creates_recovery(previous):
    state = AlertState(temperature=previous)

    result = evaluate_alerts(state, SensorReading(20.0, 45.0))

    assert len(result.events) == 1
    assert result.events[0].kind is EventKind.RECOVERY
    assert result.events[0].previous is previous
    assert result.events[0].current is RangeState.NORMAL


def test_direct_low_to_high_transition_creates_new_alert_without_recovery():
    previous = AlertState(temperature=RangeState.LOW)

    result = evaluate_alerts(previous, SensorReading(30.0, 45.0))

    assert [(event.kind, event.current) for event in result.events] == [
        (EventKind.ALERT, RangeState.HIGH)
    ]


def test_temperature_and_humidity_transition_independently():
    result = evaluate_alerts(AlertState(), SensorReading(8.0, 65.0))

    assert [event.metric for event in result.events] == [Metric.TEMPERATURE, Metric.HUMIDITY]
    assert result.current_state == AlertState(RangeState.LOW, RangeState.HIGH)


def test_tracker_commits_state_and_restores_it_after_restart():
    store = MemoryStore()
    tracker = AlertTracker(store)
    evaluation = tracker.evaluate(SensorReading(30.0, 45.0))
    tracker.commit(evaluation)

    restarted_tracker = AlertTracker(store)
    repeated = restarted_tracker.evaluate(SensorReading(31.0, 45.0))

    assert repeated.events == ()
    assert restarted_tracker.state.temperature is RangeState.HIGH


def test_uncommitted_transition_remains_retryable():
    tracker = AlertTracker(MemoryStore())
    reading = SensorReading(30.0, 45.0)

    first = tracker.evaluate(reading)
    retry = tracker.evaluate(reading)

    assert first.events == retry.events
    assert tracker.state == AlertState()


def test_failed_commit_does_not_advance_in_memory_state():
    tracker = AlertTracker(FailingStore())
    evaluation = tracker.evaluate(SensorReading(30.0, 45.0))

    with pytest.raises(OSError, match="storage unavailable"):
        tracker.commit(evaluation)

    assert tracker.state == AlertState()


def test_unchanged_state_is_not_rewritten():
    store = MemoryStore()
    tracker = AlertTracker(store)

    tracker.commit(tracker.evaluate(SensorReading(20.0, 45.0)))

    assert store.saved == []


def test_tracker_rejects_stale_evaluation():
    tracker = AlertTracker(MemoryStore())
    first = tracker.evaluate(SensorReading(30.0, 45.0))
    stale = tracker.evaluate(SensorReading(8.0, 45.0))
    tracker.commit(first)

    with pytest.raises(ValueError, match="stale"):
        tracker.commit(stale)
