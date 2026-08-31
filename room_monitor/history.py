"""Rate-limited historical recording for valid sensor measurements."""

from __future__ import annotations

import logging
from pathlib import Path
import threading
import time
from collections.abc import Callable

from room_monitor.database import DatabaseError, initialize_database, save_sensor_reading
from room_monitor.sensor import SensorReading, temperature_to_fahrenheit


LOGGER = logging.getLogger(__name__)


class HistoryRecorder:
    """Store no more than one reading per configured monotonic interval."""

    def __init__(
        self,
        database_path: Path,
        interval_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if interval_seconds < 1:
            raise ValueError("interval_seconds must be at least 1")
        self._database_path = database_path
        self._interval_seconds = interval_seconds
        self._clock = clock
        self._lock = threading.RLock()
        self._last_attempt: float | None = None
        self._database_ready = False

    def initialize(self) -> bool:
        with self._lock:
            try:
                initialize_database(self._database_path)
            except DatabaseError:
                self._database_ready = False
                return False
            self._database_ready = True
            return True

    def record(self, reading: SensorReading) -> bool:
        """Persist a due reading; return whether a row was written."""
        with self._lock:
            now = self._clock()
            if (
                self._last_attempt is not None
                and now - self._last_attempt < self._interval_seconds
            ):
                return False
            self._last_attempt = now
            if not self._database_ready and not self.initialize():
                return False
            try:
                save_sensor_reading(
                    temperature_to_fahrenheit(reading.temperature_c),
                    reading.humidity_pct,
                    self._database_path,
                )
            except (DatabaseError, ValueError) as exc:
                self._database_ready = False
                LOGGER.warning("Historical sensor reading was not stored: %s", exc)
                return False
            return True
