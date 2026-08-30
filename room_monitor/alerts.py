"""Alert transitions for temperature and humidity readings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from collections.abc import Callable
from typing import Protocol

from room_monitor.sensor import SensorReading
from room_monitor.thresholds import (
    AlertThresholds,
    DEFAULT_THRESHOLDS,
    RangeState,
    classify_humidity,
    classify_temperature,
)


class Metric(str, Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"


class EventKind(str, Enum):
    ALERT = "alert"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class AlertState:
    temperature: RangeState = RangeState.NORMAL
    humidity: RangeState = RangeState.NORMAL


@dataclass(frozen=True)
class AlertEvent:
    metric: Metric
    kind: EventKind
    previous: RangeState
    current: RangeState
    value: float


@dataclass(frozen=True)
class AlertEvaluation:
    previous_state: AlertState
    current_state: AlertState
    events: tuple[AlertEvent, ...]


class StateStore(Protocol):
    def load(self) -> AlertState: ...

    def save(self, state: AlertState) -> None: ...


class AlertTracker:
    """Evaluate crossings and explicitly persist accepted transitions."""

    def __init__(
        self,
        store: StateStore,
        threshold_provider: Callable[[], AlertThresholds] = lambda: DEFAULT_THRESHOLDS,
    ) -> None:
        self._store = store
        self._state = store.load()
        self._threshold_provider = threshold_provider

    @property
    def state(self) -> AlertState:
        return self._state

    def evaluate(self, reading: SensorReading) -> AlertEvaluation:
        return evaluate_alerts(self._state, reading, self._threshold_provider())

    def commit(self, evaluation: AlertEvaluation) -> None:
        if evaluation.previous_state != self._state:
            raise ValueError("Cannot commit a stale alert evaluation")
        if evaluation.current_state == self._state:
            return
        self._store.save(evaluation.current_state)
        self._state = evaluation.current_state


def evaluate_alerts(
    previous_state: AlertState,
    reading: SensorReading,
    thresholds: AlertThresholds = DEFAULT_THRESHOLDS,
) -> AlertEvaluation:
    current_state = AlertState(
        temperature=classify_temperature(reading.temperature_c, thresholds),
        humidity=classify_humidity(reading.humidity_pct, thresholds),
    )
    events: list[AlertEvent] = []
    _append_transition(
        events,
        Metric.TEMPERATURE,
        previous_state.temperature,
        current_state.temperature,
        reading.temperature_c,
    )
    _append_transition(
        events,
        Metric.HUMIDITY,
        previous_state.humidity,
        current_state.humidity,
        reading.humidity_pct,
    )
    return AlertEvaluation(previous_state, current_state, tuple(events))


def _append_transition(
    events: list[AlertEvent],
    metric: Metric,
    previous: RangeState,
    current: RangeState,
    value: float,
) -> None:
    if current is previous:
        return
    kind = EventKind.RECOVERY if current is RangeState.NORMAL else EventKind.ALERT
    events.append(AlertEvent(metric, kind, previous, current, value))
