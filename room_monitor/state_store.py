"""Crash-safe persistence for room-monitor alert state."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import tempfile

from room_monitor.alerts import AlertState
from room_monitor.thresholds import RangeState


LOGGER = logging.getLogger(__name__)
STATE_VERSION = 1


class StatePersistenceError(RuntimeError):
    """Raised when alert state cannot be read or written safely."""


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> AlertState:
        try:
            with self._path.open(encoding="utf-8") as state_file:
                payload = json.load(state_file)
            return _decode_state(payload)
        except FileNotFoundError:
            return AlertState()
        except (json.JSONDecodeError, UnicodeError, TypeError, ValueError, KeyError) as exc:
            LOGGER.warning("Ignoring invalid alert state file %s: %s", self._path, exc)
            return AlertState()
        except OSError as exc:
            raise StatePersistenceError(f"Unable to read alert state file {self._path}: {exc}") from exc

    def save(self, state: AlertState) -> None:
        parent = self._path.parent
        temporary_path: Path | None = None
        try:
            parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=".alert-state-", dir=parent)
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as state_file:
                json.dump(_encode_state(state), state_file, sort_keys=True, separators=(",", ":"))
                state_file.write("\n")
                state_file.flush()
                os.fsync(state_file.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self._path)
            temporary_path = None
            directory_descriptor = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except OSError as exc:
            raise StatePersistenceError(f"Unable to save alert state file {self._path}: {exc}") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def _encode_state(state: AlertState) -> dict[str, str | int]:
    return {
        "version": STATE_VERSION,
        "temperature": state.temperature.value,
        "humidity": state.humidity.value,
    }


def _decode_state(payload: object) -> AlertState:
    if not isinstance(payload, dict) or payload.get("version") != STATE_VERSION:
        raise ValueError("unsupported or missing state version")
    return AlertState(
        temperature=RangeState(payload["temperature"]),
        humidity=RangeState(payload["humidity"]),
    )
