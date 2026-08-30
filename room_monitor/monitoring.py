"""Continuous room monitoring and local-time job scheduling."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, time, tzinfo
import logging
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram.error import TelegramError
from telegram.ext import JobQueue

from room_monitor.alerts import AlertEvaluation, AlertEvent, AlertTracker, EventKind, Metric
from room_monitor.sensor import SensorReadError, SensorReading, temperature_to_fahrenheit
from room_monitor.state_store import StatePersistenceError
from room_monitor.thresholds import RangeState


LOGGER = logging.getLogger(__name__)
FIRST_REPORT_HOUR = 8
LAST_REPORT_HOUR = 17


class MonitoringService:
    """Read the sensor and deliver scheduled or transition-based messages."""

    def __init__(self, sensor_reader: Callable[[], SensorReading], tracker: AlertTracker, chat_id: int) -> None:
        self._sensor_reader = sensor_reader
        self._tracker = tracker
        self._chat_id = chat_id
        self._sensor_lock = asyncio.Lock()
        self._alert_lock = asyncio.Lock()
        self._pending_commit: AlertEvaluation | None = None

    async def send_hourly_report(self, context) -> None:
        reading = await self._read_sensor("hourly report")
        if reading is None:
            return
        try:
            await context.bot.send_message(self._chat_id, format_status_message(reading))
        except TelegramError as exc:
            LOGGER.warning("Unable to send hourly room report: %s", exc)

    async def check_alerts(self, context) -> None:
        async with self._alert_lock:
            if self._pending_commit is not None:
                if not await self._commit(self._pending_commit):
                    return
                self._pending_commit = None

            reading = await self._read_sensor("alert check")
            if reading is None:
                return
            evaluation = self._tracker.evaluate(reading)
            if not evaluation.events:
                await self._commit(evaluation)
                return

            try:
                await context.bot.send_message(self._chat_id, format_alert_message(evaluation.events))
            except TelegramError as exc:
                LOGGER.warning("Unable to send room alert; transition remains pending: %s", exc)
                return

            if not await self._commit(evaluation):
                self._pending_commit = evaluation

    async def _read_sensor(self, purpose: str) -> SensorReading | None:
        try:
            async with self._sensor_lock:
                return await asyncio.to_thread(self._sensor_reader)
        except (OSError, SensorReadError) as exc:
            LOGGER.warning("Unable to read sensor for %s: %s", purpose, exc)
            return None

    async def _commit(self, evaluation: AlertEvaluation) -> bool:
        try:
            await asyncio.to_thread(self._tracker.commit, evaluation)
            return True
        except (OSError, StatePersistenceError) as exc:
            LOGGER.error("Unable to persist alert state; delivery is paused: %s", exc)
            return False


def format_status_message(reading: SensorReading) -> str:
    return (
        "Current room status:\n"
        f"Temperature: {reading.temperature_c:.2f} C / "
        f"{temperature_to_fahrenheit(reading.temperature_c):.2f} F\n"
        f"Relative humidity: {reading.humidity_pct:.2f}%"
    )


def format_alert_message(events: tuple[AlertEvent, ...]) -> str:
    lines = ["Room monitor update:"]
    lines.extend(_format_event(event) for event in events)
    return "\n".join(lines)


def _format_event(event: AlertEvent) -> str:
    label = "Temperature" if event.metric is Metric.TEMPERATURE else "Humidity"
    value = _format_event_value(event)
    if event.kind is EventKind.RECOVERY:
        return f"RECOVERY: {label} returned to normal ({value})."
    direction = "below the low limit" if event.current is RangeState.LOW else "above the high limit"
    return f"ALERT: {label} is {direction} ({value})."


def _format_event_value(event: AlertEvent) -> str:
    if event.metric is Metric.TEMPERATURE:
        return f"{event.value:.2f} C / {temperature_to_fahrenheit(event.value):.2f} F"
    return f"{event.value:.2f}% RH"


def register_monitoring_jobs(
    job_queue: JobQueue,
    service: MonitoringService,
    alert_interval_seconds: int,
    local_tz: tzinfo | None = None,
) -> None:
    if alert_interval_seconds < 1:
        raise ValueError("alert_interval_seconds must be at least 1")
    timezone = local_tz or get_local_timezone()
    job_queue.run_repeating(
        service.check_alerts,
        interval=alert_interval_seconds,
        first=1,
        name="room-monitor-alert-check",
    )
    for hour in range(FIRST_REPORT_HOUR, LAST_REPORT_HOUR + 1):
        job_queue.run_daily(
            service.send_hourly_report,
            time=time(hour=hour, tzinfo=timezone),
            name=f"room-monitor-hourly-{hour:02d}00",
        )


def is_hourly_report_time(moment: datetime) -> bool:
    return moment.minute == 0 and moment.second == 0 and FIRST_REPORT_HOUR <= moment.hour <= LAST_REPORT_HOUR


def get_local_timezone() -> tzinfo:
    try:
        zone_path = Path("/etc/localtime").resolve()
        zone_name = zone_path.relative_to("/usr/share/zoneinfo").as_posix()
        return ZoneInfo(zone_name)
    except (OSError, ValueError, ZoneInfoNotFoundError):
        fallback = datetime.now().astimezone().tzinfo
        if fallback is None:
            raise RuntimeError("Unable to determine the local time zone")
        return fallback
