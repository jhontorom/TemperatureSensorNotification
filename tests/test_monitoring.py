from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
from telegram.error import TimedOut

from room_monitor.alerts import AlertState, AlertTracker
from room_monitor.monitoring import (
    MonitoringService,
    format_alert_message,
    is_hourly_report_time,
    register_monitoring_jobs,
)
from room_monitor.sensor import SensorReadError, SensorReading


class MemoryStore:
    def __init__(self):
        self.state = AlertState()
        self.saved = []
        self.failure = None

    def load(self):
        return self.state

    def save(self, state):
        if self.failure:
            raise self.failure
        self.state = state
        self.saved.append(state)


@pytest.fixture(autouse=True)
def run_threads_inline(monkeypatch):
    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr("room_monitor.monitoring.asyncio.to_thread", run_inline)


def context_with_bot():
    return SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))


@pytest.mark.asyncio
async def test_hourly_report_contains_all_measurements():
    context = context_with_bot()
    service = MonitoringService(
        Mock(return_value=SensorReading(25.0, 48.5)), AlertTracker(MemoryStore()), 123
    )

    await service.send_hourly_report(context)

    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.await_args.args[0] == 123
    message = context.bot.send_message.await_args.args[1]
    assert "23.42 C / 74.15 F" in message
    assert "48.50%" in message


@pytest.mark.asyncio
async def test_hourly_telegram_failure_does_not_crash():
    context = context_with_bot()
    context.bot.send_message.side_effect = TimedOut("offline")
    service = MonitoringService(
        Mock(return_value=SensorReading(25.0, 48.5)), AlertTracker(MemoryStore()), 123
    )

    await service.send_hourly_report(context)

    context.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_first_crossing_sends_once_and_commits_state():
    context = context_with_bot()
    store = MemoryStore()
    service = MonitoringService(
        Mock(return_value=SensorReading(30.0, 45.0)), AlertTracker(store), 123
    )

    await service.check_alerts(context)
    await service.check_alerts(context)

    context.bot.send_message.assert_awaited_once()
    assert "ALERT: Temperature is above the high limit" in context.bot.send_message.await_args.args[1]
    assert len(store.saved) == 1


@pytest.mark.asyncio
async def test_recovery_is_sent_after_alert_state():
    context = context_with_bot()
    store = MemoryStore()
    readings = iter([SensorReading(30.0, 45.0), SensorReading(20.0, 45.0)])
    service = MonitoringService(lambda: next(readings), AlertTracker(store), 123)

    await service.check_alerts(context)
    await service.check_alerts(context)

    assert context.bot.send_message.await_count == 2
    assert "RECOVERY: Temperature returned to normal" in context.bot.send_message.await_args.args[1]


@pytest.mark.asyncio
async def test_telegram_failure_leaves_transition_for_retry():
    context = context_with_bot()
    context.bot.send_message.side_effect = [TimedOut("offline"), None]
    store = MemoryStore()
    service = MonitoringService(
        Mock(return_value=SensorReading(30.0, 45.0)), AlertTracker(store), 123
    )

    await service.check_alerts(context)
    await service.check_alerts(context)

    assert context.bot.send_message.await_count == 2
    assert len(store.saved) == 1


@pytest.mark.asyncio
async def test_persistence_failure_pauses_delivery_until_commit_succeeds():
    context = context_with_bot()
    store = MemoryStore()
    store.failure = OSError("disk unavailable")
    service = MonitoringService(
        Mock(return_value=SensorReading(30.0, 45.0)), AlertTracker(store), 123
    )

    await service.check_alerts(context)
    await service.check_alerts(context)
    store.failure = None
    await service.check_alerts(context)
    await service.check_alerts(context)

    context.bot.send_message.assert_awaited_once()
    assert len(store.saved) == 1


@pytest.mark.asyncio
async def test_sensor_failure_does_not_send_or_crash():
    context = context_with_bot()
    service = MonitoringService(
        Mock(side_effect=SensorReadError("disconnected")), AlertTracker(MemoryStore()), 123
    )

    await service.check_alerts(context)
    await service.send_hourly_report(context)

    context.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_collection_reads_sensor_without_sending_telegram():
    context = context_with_bot()
    sensor_reader = Mock(return_value=SensorReading(25.0, 48.5))
    history_recorder = Mock()
    service = MonitoringService(
        sensor_reader, AlertTracker(MemoryStore()), 123, history_recorder
    )

    await service.collect_history(context)

    sensor_reader.assert_called_once_with()
    history_recorder.record.assert_called_once_with(SensorReading(25.0, 48.5))
    context.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_each_history_job_persists_one_reading():
    context = context_with_bot()
    sensor_reader = Mock(return_value=SensorReading(25.0, 48.5))
    history_recorder = Mock()
    service = MonitoringService(
        sensor_reader, AlertTracker(MemoryStore()), 123, history_recorder
    )

    await service.collect_history(context)
    await service.collect_history(context)

    assert sensor_reader.call_count == 2
    assert history_recorder.record.call_count == 2


def test_temperature_alert_message_uses_calibrated_values():
    result = AlertTracker(MemoryStore()).evaluate(SensorReading(30.0, 45.0))

    message = format_alert_message(result.events)

    assert "28.42 C / 83.15 F" in message
    assert "30.00 C / 86.00 F" not in message


@pytest.mark.parametrize("hour", range(8, 18))
def test_hourly_report_rule_includes_8_am_through_5_pm(hour):
    assert is_hourly_report_time(datetime(2026, 9, 2, hour, 0, 0))


@pytest.mark.parametrize(
    "moment",
    [
        datetime(2026, 9, 2, 7, 0, 0),
        datetime(2026, 9, 2, 18, 0, 0),
        datetime(2026, 9, 2, 8, 0, 1),
        datetime(2026, 9, 2, 17, 30, 0),
    ],
)
def test_hourly_report_rule_excludes_other_times(moment):
    assert not is_hourly_report_time(moment)


def test_job_registration_uses_local_hours_and_all_day_repeating_alerts():
    queue = Mock()
    service = Mock()
    timezone = ZoneInfo("America/Detroit")

    register_monitoring_jobs(queue, service, 60, timezone)

    assert queue.run_repeating.call_count == 2
    queue.run_repeating.assert_any_call(
        service.check_alerts,
        interval=60,
        first=1,
        name="room-monitor-alert-check",
    )
    queue.run_repeating.assert_any_call(
        service.collect_history,
        interval=60,
        first=1,
        name="room-monitor-history-collection",
    )
    assert queue.run_daily.call_count == 10
    scheduled_times = [call.kwargs["time"] for call in queue.run_daily.call_args_list]
    assert [scheduled.hour for scheduled in scheduled_times] == list(range(8, 18))
    assert all(scheduled.tzinfo == timezone for scheduled in scheduled_times)
