from datetime import datetime
import sqlite3

import pytest

from room_monitor.database import (
    InvalidReadingError,
    get_readings_between_dates,
    get_recent_readings,
    initialize_database,
    save_sensor_reading,
)


def test_initialize_creates_database_and_future_ready_tables(tmp_path):
    path = tmp_path / "data" / "temperature_monitor.db"
    initialize_database(path)
    assert path.is_file()
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = ?", ("table",)
            )
        }
    assert "sensor_readings" in tables
    assert "energy_bills" in tables


def test_insert_and_retrieve_sensor_reading(tmp_path):
    path = tmp_path / "temperature_monitor.db"
    initialize_database(path)
    row_id = save_sensor_reading(74.2, 48.0, path)
    readings = get_recent_readings(10, path)
    assert row_id == 1
    assert len(readings) == 1
    assert readings[0].temperature_f == 74.2
    assert readings[0].humidity == 48.0
    assert readings[0].timestamp


def test_readings_persist_after_reconnecting(tmp_path):
    path = tmp_path / "temperature_monitor.db"
    initialize_database(path)
    save_sensor_reading(72.0, 44.0, path)
    initialize_database(path)
    save_sensor_reading(73.0, 45.0, path)
    readings = get_recent_readings(10, path)
    assert [reading.temperature_f for reading in readings] == [73.0, 72.0]


def test_readings_between_dates_are_parameterized_and_ordered(tmp_path):
    path = tmp_path / "temperature_monitor.db"
    initialize_database(path)
    save_sensor_reading(70.0, 40.0, path, timestamp=datetime(2026, 8, 30, 8, 0))
    save_sensor_reading(71.0, 41.0, path, timestamp=datetime(2026, 8, 30, 9, 0))
    save_sensor_reading(72.0, 42.0, path, timestamp=datetime(2026, 8, 30, 10, 0))
    readings = get_readings_between_dates(
        "2026-08-30 08:30:00", "2026-08-30 10:00:00", path
    )
    assert [reading.temperature_f for reading in readings] == [71.0, 72.0]


@pytest.mark.parametrize(
    ("temperature", "humidity"),
    [
        ("hot", 50.0),
        (70.0, "wet"),
        (float("nan"), 50.0),
        (300.0, 50.0),
        (70.0, -1.0),
        (70.0, 101.0),
        (True, 50.0),
    ],
)
def test_invalid_sensor_values_are_rejected_without_inserting(tmp_path, temperature, humidity):
    path = tmp_path / "temperature_monitor.db"
    initialize_database(path)
    with pytest.raises(InvalidReadingError):
        save_sensor_reading(temperature, humidity, path)
    assert get_recent_readings(10, path) == []


def test_initialize_is_idempotent_and_does_not_delete_existing_rows(tmp_path):
    path = tmp_path / "temperature_monitor.db"
    initialize_database(path)
    save_sensor_reading(75.0, 49.0, path)
    initialize_database(path)
    assert len(get_recent_readings(10, path)) == 1
