"""Crash-safe persistence and synchronized access for alert thresholds."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import tempfile
import threading

from room_monitor.thresholds import AlertThresholds, DEFAULT_THRESHOLDS


LOGGER = logging.getLogger(__name__)
THRESHOLD_VERSION = 1


class ThresholdPersistenceError(RuntimeError):
    """Raised when threshold configuration cannot be read or written safely."""


class JsonThresholdStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> AlertThresholds:
        try:
            with self._path.open(encoding="utf-8") as threshold_file:
                return _decode_thresholds(json.load(threshold_file))
        except FileNotFoundError:
            return DEFAULT_THRESHOLDS
        except (json.JSONDecodeError, UnicodeError, TypeError, ValueError, KeyError) as exc:
            LOGGER.warning("Ignoring invalid threshold file %s: %s", self._path, exc)
            return DEFAULT_THRESHOLDS
        except OSError as exc:
            raise ThresholdPersistenceError(
                f"Unable to read threshold file {self._path}: {exc}"
            ) from exc

    def save(self, thresholds: AlertThresholds) -> None:
        parent = self._path.parent
        temporary_path: Path | None = None
        try:
            parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=".thresholds-", dir=parent)
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as threshold_file:
                json.dump(
                    _encode_thresholds(thresholds),
                    threshold_file,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                threshold_file.write("\n")
                threshold_file.flush()
                os.fsync(threshold_file.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self._path)
            temporary_path = None
            directory_descriptor = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except OSError as exc:
            raise ThresholdPersistenceError(
                f"Unable to save threshold file {self._path}: {exc}"
            ) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


class ThresholdManager:
    """Persist threshold updates and expose a synchronized current snapshot."""

    def __init__(self, store: JsonThresholdStore) -> None:
        self._store = store
        self._lock = threading.RLock()
        self._thresholds = store.load()

    def get(self) -> AlertThresholds:
        with self._lock:
            return self._thresholds

    def set_temperature(self, low_c: float, high_c: float) -> AlertThresholds:
        with self._lock:
            updated = AlertThresholds(
                low_c,
                high_c,
                self._thresholds.humidity_low_pct,
                self._thresholds.humidity_high_pct,
            )
            self._store.save(updated)
            self._thresholds = updated
            return updated

    def set_humidity(self, low_pct: float, high_pct: float) -> AlertThresholds:
        with self._lock:
            updated = AlertThresholds(
                self._thresholds.temperature_low_c,
                self._thresholds.temperature_high_c,
                low_pct,
                high_pct,
            )
            self._store.save(updated)
            self._thresholds = updated
            return updated


def _encode_thresholds(thresholds: AlertThresholds) -> dict[str, float | int]:
    return {
        "version": THRESHOLD_VERSION,
        "temperature_low_c": thresholds.temperature_low_c,
        "temperature_high_c": thresholds.temperature_high_c,
        "humidity_low_pct": thresholds.humidity_low_pct,
        "humidity_high_pct": thresholds.humidity_high_pct,
    }


def _decode_thresholds(payload: object) -> AlertThresholds:
    if not isinstance(payload, dict) or payload.get("version") != THRESHOLD_VERSION:
        raise ValueError("unsupported or missing threshold version")
    return AlertThresholds(
        temperature_low_c=float(payload["temperature_low_c"]),
        temperature_high_c=float(payload["temperature_high_c"]),
        humidity_low_pct=float(payload["humidity_low_pct"]),
        humidity_high_pct=float(payload["humidity_high_pct"]),
    )
