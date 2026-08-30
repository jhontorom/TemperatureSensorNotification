from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import TimedOut

from room_monitor.alerts import AlertTracker
from room_monitor.monitoring import MonitoringService
from room_monitor.sensor import SensorReadError, SensorReading
from room_monitor.state_store import JsonStateStore


@pytest.fixture(autouse=True)
def run_threads_inline(monkeypatch):
    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr("room_monitor.monitoring.asyncio.to_thread", run_inline)


def context_with_bot(*side_effects):
    bot = SimpleNamespace(send_message=AsyncMock())
    if side_effects:
        bot.send_message.side_effect = list(side_effects)
    return SimpleNamespace(bot=bot)


@pytest.mark.asyncio
async def test_restart_does_not_repeat_persisted_alert(tmp_path):
    state_path = tmp_path / "alert-state.json"
    context = context_with_bot()
    reading = lambda: SensorReading(30.0, 45.0)

    first_process = MonitoringService(reading, AlertTracker(JsonStateStore(state_path)), 123)
    await first_process.check_alerts(context)

    restarted_process = MonitoringService(reading, AlertTracker(JsonStateStore(state_path)), 123)
    await restarted_process.check_alerts(context)

    context.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_restart_sends_recovery_from_persisted_alert_state(tmp_path):
    state_path = tmp_path / "alert-state.json"
    alert_context = context_with_bot()
    first_process = MonitoringService(
        lambda: SensorReading(30.0, 45.0), AlertTracker(JsonStateStore(state_path)), 123
    )
    await first_process.check_alerts(alert_context)

    recovery_context = context_with_bot()
    restarted_process = MonitoringService(
        lambda: SensorReading(20.0, 45.0), AlertTracker(JsonStateStore(state_path)), 123
    )
    await restarted_process.check_alerts(recovery_context)

    message = recovery_context.bot.send_message.await_args.args[1]
    assert "RECOVERY: Temperature returned to normal" in message


@pytest.mark.asyncio
async def test_sensor_reconnect_resumes_checks_without_flooding(tmp_path):
    readings = iter(
        [
            SensorReadError("disconnected"),
            SensorReading(30.0, 45.0),
            SensorReading(30.0, 45.0),
        ]
    )

    def read_sensor():
        result = next(readings)
        if isinstance(result, Exception):
            raise result
        return result

    context = context_with_bot()
    service = MonitoringService(
        read_sensor, AlertTracker(JsonStateStore(tmp_path / "alert-state.json")), 123
    )

    await service.check_alerts(context)
    await service.check_alerts(context)
    await service.check_alerts(context)

    context.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_reconnect_retries_transition_once(tmp_path):
    context = context_with_bot(TimedOut("offline"), None)
    service = MonitoringService(
        lambda: SensorReading(30.0, 45.0),
        AlertTracker(JsonStateStore(tmp_path / "alert-state.json")),
        123,
    )

    await service.check_alerts(context)
    await service.check_alerts(context)
    await service.check_alerts(context)

    assert context.bot.send_message.await_count == 2
