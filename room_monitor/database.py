"""SQLite persistence for historical room-monitor data."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import logging
import math
from pathlib import Path
import sqlite3
from typing import Iterator

LOGGER = logging.getLogger(__name__)
DEFAULT_DATABASE_PATH = Path("data/temperature_monitor.db")
MIN_TEMPERATURE_F = -40.0
MAX_TEMPERATURE_F = 257.0
MIN_HUMIDITY = 0.0
MAX_HUMIDITY = 100.0


class DatabaseError(RuntimeError):
    """Raised when a database operation cannot be completed."""


class InvalidReadingError(ValueError):
    """Raised when a reading is not safe to persist."""


@dataclass(frozen=True)
class StoredSensorReading:
    id: int
    timestamp: str
    temperature_f: float
    humidity: float

    @property
    def raw_temperature_f(self) -> float:
        return self.temperature_f



@contextmanager
def _connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            yield connection
    finally:
        if connection is not None:
            connection.close()


def initialize_database(database_path: Path = DEFAULT_DATABASE_PATH) -> None:
    """Create the database schema without changing existing rows."""
    path = Path(database_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _connection(path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                    temperature_f REAL NOT NULL CHECK (temperature_f BETWEEN -40.0 AND 257.0),
                    humidity REAL NOT NULL CHECK (humidity BETWEEN 0.0 AND 100.0)
                );

                CREATE INDEX IF NOT EXISTS idx_sensor_readings_timestamp
                    ON sensor_readings(timestamp);

                CREATE TABLE IF NOT EXISTS energy_bills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    billing_start TEXT NOT NULL,
                    billing_end TEXT NOT NULL,
                    total_kwh REAL NOT NULL,
                    total_cost REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
                );
                """
            )
    except sqlite3.Error as exc:
        LOGGER.error("Unable to initialize SQLite database %s: %s", path, exc)
        raise DatabaseError(f"Unable to initialize database {path}") from exc
    except OSError as exc:
        LOGGER.error("Unable to create SQLite database directory for %s: %s", path, exc)
        raise DatabaseError(f"Unable to initialize database {path}") from exc


def save_sensor_reading(
    temperature_f: float,
    humidity: float,
    database_path: Path = DEFAULT_DATABASE_PATH,
    *,
    timestamp: datetime | str | None = None,
) -> int:
    """Validate and insert one sensor reading, returning its row id."""
    temperature, relative_humidity = _validate_reading(temperature_f, humidity)
    path = Path(database_path)
    try:
        with _connection(path) as connection:
            if timestamp is None:
                cursor = connection.execute(
                    "INSERT INTO sensor_readings (temperature_f, humidity) VALUES (?, ?)",
                    (temperature, relative_humidity),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO sensor_readings (timestamp, temperature_f, humidity)
                    VALUES (?, ?, ?)
                    """,
                    (_normalize_timestamp(timestamp), temperature, relative_humidity),
                )
            return int(cursor.lastrowid)
    except sqlite3.Error as exc:
        LOGGER.error("Unable to save sensor reading to %s: %s", path, exc)
        raise DatabaseError(f"Unable to save sensor reading to {path}") from exc


def get_recent_readings(
    limit: int = 20, database_path: Path = DEFAULT_DATABASE_PATH
) -> list[StoredSensorReading]:
    """Return the newest readings first."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    return _query_readings(
        """
        SELECT id, timestamp, temperature_f, humidity
        FROM sensor_readings
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
        """,
        (limit,),
        Path(database_path),
    )


def get_readings_between_dates(
    start: datetime | str,
    end: datetime | str,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> list[StoredSensorReading]:
    """Return readings within an inclusive timestamp range, oldest first."""
    start_value = _normalize_timestamp(start)
    end_value = _normalize_timestamp(end)
    if start_value > end_value:
        raise ValueError("start must not be after end")
    return _query_readings(
        """
        SELECT id, timestamp, temperature_f, humidity
        FROM sensor_readings
        WHERE timestamp BETWEEN ? AND ?
        ORDER BY timestamp ASC, id ASC
        """,
        (start_value, end_value),
        Path(database_path),
    )


def _query_readings(
    query: str, parameters: tuple[object, ...], database_path: Path
) -> list[StoredSensorReading]:
    try:
        with _connection(database_path) as connection:
            rows = connection.execute(query, parameters).fetchall()
    except sqlite3.Error as exc:
        LOGGER.error("Unable to query sensor readings from %s: %s", database_path, exc)
        raise DatabaseError(f"Unable to query sensor readings from {database_path}") from exc
    return [
        StoredSensorReading(
            id=int(row["id"]),
            timestamp=str(row["timestamp"]),
            temperature_f=float(row["temperature_f"]),
            humidity=float(row["humidity"]),
        )
        for row in rows
    ]


def _validate_reading(temperature_f: float, humidity: float) -> tuple[float, float]:
    if isinstance(temperature_f, bool) or not isinstance(temperature_f, (int, float)):
        raise InvalidReadingError("temperature_f must be numeric")
    if isinstance(humidity, bool) or not isinstance(humidity, (int, float)):
        raise InvalidReadingError("humidity must be numeric")
    temperature = float(temperature_f)
    relative_humidity = float(humidity)
    if not math.isfinite(temperature) or not MIN_TEMPERATURE_F <= temperature <= MAX_TEMPERATURE_F:
        raise InvalidReadingError("temperature_f is outside the valid sensor range")
    if (
        not math.isfinite(relative_humidity)
        or not MIN_HUMIDITY <= relative_humidity <= MAX_HUMIDITY
    ):
        raise InvalidReadingError("humidity is outside the valid sensor range")
    return temperature, relative_humidity


def _normalize_timestamp(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError("timestamp must be a datetime or non-empty string")
