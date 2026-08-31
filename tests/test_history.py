from room_monitor.database import DatabaseError
from room_monitor.history import HistoryRecorder
from room_monitor.sensor import SensorReading


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


def test_recorder_converts_celsius_and_rate_limits(monkeypatch, tmp_path):
    saved = []
    clock = Clock()
    monkeypatch.setattr("room_monitor.history.initialize_database", lambda _path: None)
    monkeypatch.setattr(
        "room_monitor.history.save_sensor_reading",
        lambda temperature, humidity, path: saved.append((temperature, humidity, path)),
    )
    recorder = HistoryRecorder(tmp_path / "history.db", 60, clock)
    recorder.initialize()
    assert recorder.record(SensorReading(25.0, 48.0)) is True
    clock.value = 30.0
    assert recorder.record(SensorReading(26.0, 49.0)) is False
    clock.value = 60.0
    assert recorder.record(SensorReading(26.0, 49.0)) is True
    assert saved[0][0] == 77.0
    assert saved[0][1] == 48.0
    assert saved[1][0] == 78.8


def test_database_failure_does_not_escape_and_retries_after_interval(monkeypatch, tmp_path):
    attempts = []
    clock = Clock()
    monkeypatch.setattr("room_monitor.history.initialize_database", lambda _path: None)

    def fail_save(*_args):
        attempts.append(clock.value)
        raise DatabaseError("database unavailable")

    monkeypatch.setattr("room_monitor.history.save_sensor_reading", fail_save)
    recorder = HistoryRecorder(tmp_path / "history.db", 60, clock)
    recorder.initialize()
    assert recorder.record(SensorReading(20.0, 45.0)) is False
    clock.value = 1.0
    assert recorder.record(SensorReading(20.0, 45.0)) is False
    clock.value = 60.0
    assert recorder.record(SensorReading(20.0, 45.0)) is False
    assert attempts == [0.0, 60.0]


def test_failed_initialization_is_retried_without_crashing(monkeypatch, tmp_path):
    clock = Clock()
    initialization_attempts = []

    def initialize(_path):
        initialization_attempts.append(clock.value)
        if len(initialization_attempts) == 1:
            raise DatabaseError("directory unavailable")

    monkeypatch.setattr("room_monitor.history.initialize_database", initialize)
    monkeypatch.setattr("room_monitor.history.save_sensor_reading", lambda *_args: None)
    recorder = HistoryRecorder(tmp_path / "history.db", 60, clock)
    assert recorder.record(SensorReading(20.0, 45.0)) is False
    clock.value = 60.0
    assert recorder.record(SensorReading(20.0, 45.0)) is True
    assert initialization_attempts == [0.0, 60.0]
