"""Historical persistence for scheduled sensor measurements."""

from __future__ import annotations

import logging
from pathlib import Path
import threading

from room_monitor.database import DatabaseError, initialize_database, save_sensor_reading
from room_monitor.sensor import SensorReading


LOGGER = logging.getLogger(__name__)


class HistoryRecorder:
    """Persist each reading requested by the history scheduler."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._lock = threading.RLock()
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
        """Persist one scheduled reading; return whether a row was written."""
        with self._lock:
            if not self._database_ready and not self.initialize():
                return False
            try:
                save_sensor_reading(
                    reading.raw_temperature_f,
                    reading.humidity_pct,
                    self._database_path,
                )
            except (DatabaseError, ValueError) as exc:
                self._database_ready = False
                LOGGER.warning("Historical sensor reading was not stored: %s", exc)
                return False
            return True
