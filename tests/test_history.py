from room_monitor.database import DatabaseError
from room_monitor.history import HistoryRecorder
from room_monitor.sensor import SensorReading


def test_recorder_converts_and_stores_every_scheduled_reading(monkeypatch, tmp_path):
    saved = []
    monkeypatch.setattr("room_monitor.history.initialize_database", lambda _path: None)
    monkeypatch.setattr(
        "room_monitor.history.save_sensor_reading",
        lambda temperature, humidity, path: saved.append((temperature, humidity, path)),
    )
    recorder = HistoryRecorder(tmp_path / "history.db")
    recorder.initialize()
    assert recorder.record(SensorReading(25.0, 48.0)) is True
    assert recorder.record(SensorReading(26.0, 49.0)) is True
    assert saved[0][0] == 77.0
    assert saved[0][1] == 48.0
    assert saved[1][0] == 78.8
    assert saved[0][0] != 74.15


def test_database_failure_does_not_escape_and_retries_on_next_scheduled_call(
    monkeypatch, tmp_path
):
    attempts = []
    monkeypatch.setattr("room_monitor.history.initialize_database", lambda _path: None)

    def fail_save(*_args):
        attempts.append("save")
        raise DatabaseError("database unavailable")

    monkeypatch.setattr("room_monitor.history.save_sensor_reading", fail_save)
    recorder = HistoryRecorder(tmp_path / "history.db")
    recorder.initialize()
    assert recorder.record(SensorReading(20.0, 45.0)) is False
    assert recorder.record(SensorReading(20.0, 45.0)) is False
    assert attempts == ["save", "save"]


def test_failed_initialization_is_retried_without_crashing(monkeypatch, tmp_path):
    initialization_attempts = []

    def initialize(_path):
        initialization_attempts.append("initialize")
        if len(initialization_attempts) == 1:
            raise DatabaseError("directory unavailable")

    monkeypatch.setattr("room_monitor.history.initialize_database", initialize)
    monkeypatch.setattr("room_monitor.history.save_sensor_reading", lambda *_args: None)
    recorder = HistoryRecorder(tmp_path / "history.db")
    assert recorder.record(SensorReading(20.0, 45.0)) is False
    assert recorder.record(SensorReading(20.0, 45.0)) is True
    assert initialization_attempts == ["initialize", "initialize"]
